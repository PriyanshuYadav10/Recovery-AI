from __future__ import annotations

import uuid
from typing import Any, Optional

from app.ai.confidence_engine import ConfidenceEngine
from app.ai.escalation_engine import EscalationEngine
from app.ai.field_extractor import FieldExtractor
from app.ai.groq_provider import GroqProvider
from app.ai.guardrail_engine import GuardrailEngine
from app.ai.intent_engine import IntentEngine
from app.ai.script_engine import ScriptEngine
from app.audit.logger import AuditLog
from app.audit.recorder import CallRecorder
from app.core.state_machine import StateMachine
from app.journey.engine import JourneyEngine, JourneySubmissionService
from app.journey.submitter import JourneySubmitClient
from app.metrics.engine import MetricsEngine
from app.models.enums import CallState, EscalationSignal, Mood
from app.models.schemas import (
    ConfidenceSnapshot,
    HandoffBrief,
    Lead,
    SubmissionReceipt,
    TurnResult,
    WhyAction,
    utc_now,
)
from app.services.dnc import DNCService
from app.services.handoff_queue import HandoffQueue
from app.services.store import Store
from app.telephony.adapters import TelephonyAdapter, get_adapter


class ConversationManager:
    def __init__(
        self,
        metrics: MetricsEngine,
        groq: Optional[GroqProvider] = None,
        voice_mode: str = "BROWSER",
        *,
        handoffs: Optional[HandoffQueue] = None,
        store: Optional[Store] = None,
        recorder: Optional[CallRecorder] = None,
        submitter: Optional[JourneySubmitClient] = None,
    ):
        self.metrics = metrics
        self.groq = groq or GroqProvider()
        self.journey = JourneyEngine()
        self.submission = JourneySubmissionService(self.journey)
        self.scripts = ScriptEngine()
        self.guardrails = GuardrailEngine()
        self.intent_engine = IntentEngine()
        self.extractor = FieldExtractor()
        self.confidence = ConfidenceEngine()
        self.escalation = EscalationEngine()
        self.dnc = DNCService()
        self.audit = AuditLog()
        self.telephony: TelephonyAdapter = get_adapter(voice_mode)
        self.submitter = submitter or JourneySubmitClient()
        self.handoffs = handoffs
        self.store = store
        self.recorder = recorder or CallRecorder()

        self.call_id = str(uuid.uuid4())
        self.sm = StateMachine()
        self.lead: Optional[Lead] = None
        self.fields: dict[str, Any] = {}
        self.consent = False
        self.recording_disclosed = False
        self.dnc_checked = False
        self.declined = False
        self.field_retries: dict[str, int] = {}
        self.pending_clarify_value: Any = None
        self.transcript: list[dict[str, Any]] = []
        self.why_log: list[WhyAction] = []
        self.last_customer_text = ""
        self.handoff_brief: Optional[HandoffBrief] = None
        self.handoff_ticket_id: Optional[str] = None
        self.transfer_result: dict[str, Any] = {}
        self.dial_result: dict[str, Any] = {}
        self.payload = None
        self.receipt: Optional[SubmissionReceipt] = None
        self.recording_path: Optional[str] = None
        self.interruptions = 0
        self.turns = 0
        self.voice_mode = voice_mode
        self.demo_scenario: Optional[str] = None
        self.handoff_phase: Optional[str] = None

    async def start(
        self, lead_id: str, voice_mode: str = "BROWSER", phone_override: str | None = None
    ) -> TurnResult:
        self.voice_mode = voice_mode
        self.telephony = get_adapter(voice_mode)
        lead = self.journey.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Unknown lead {lead_id}")
        self.lead = lead
        self.fields = dict(lead.known_fields or {})
        self.metrics.start_journey(self.call_id)
        self.audit.emit("CALL_STARTED", self.call_id, lead_id=lead_id, voice_mode=voice_mode)

        # DNC gates the dial - the check has to happen before the phone rings,
        # not after, or the gate is decorative.
        self.sm.transition(CallState.DNC_CHECK, "start")
        dnc = self.dnc.check(lead)
        self.dnc_checked = True
        self.audit.emit("DNC_CHECK", self.call_id, **dnc)
        if not dnc["eligible"]:
            self.sm.transition(CallState.ENDED, "dnc_blocked")
            msg = self.scripts.render("dnc_blocked")
            self._assistant(msg)
            self.audit.emit("CALL_ENDED", self.call_id, status="dnc_blocked")
            self._finalise("dnc_blocked")
            return self._result(
                msg,
                ended=True,
                why=self._why(
                    "STOP",
                    f"DNC gate blocked the dial before anything was collected ({dnc['reason']}).",
                    "dnc",
                ),
            )

        # phone_override lets a demo dial a real, presenter-controlled number
        # while every other field (known_fields, last_completed_step, script
        # personalisation) still comes from the lead record - the synthetic
        # leads' own "phone" numbers are fabricated and can never ring anything.
        to_number = phone_override or lead.phone
        self.dial_result = await self.telephony.start_call(
            to_number, {"lead_id": lead_id, "call_id": self.call_id}
        )
        self.audit.emit("DIALLED", self.call_id, dial=self.dial_result)

        self.sm.transition(CallState.DISCLOSURE, "eligible")
        self.recording_disclosed = True
        self.audit.emit("DISCLOSURE_GIVEN", self.call_id)
        msg = self.scripts.render("disclosure", first_name=lead.first_name)
        self.sm.transition(CallState.CONSENT, "await_consent")
        self._assistant(msg)
        self._why(
            "ASKED_DISCLOSURE",
            "Consent-first guardrail: recording must be disclosed before collecting information.",
            "consent",
        )
        return self._result(msg)

    async def handle_utterance(
        self,
        text: str,
        *,
        speech_confidence: float = 0.95,
    ) -> TurnResult:
        self.turns += 1
        self.metrics.add_turns(1)
        self.last_customer_text = text
        self._customer(text)

        if self.sm.state in {CallState.ENDED, CallState.HANDOFF, CallState.COMPLETED, CallState.DECLINED}:
            return self._result("This call has ended.", ended=True, speak=False)

        # Guardrails first - deterministic
        collecting = self.sm.state in {
            CallState.COLLECTING,
            CallState.CLARIFYING,
            CallState.CONFIRMING,
            CallState.RECOVER_CONTEXT,
        }
        gr = self.guardrails.evaluate(
            text,
            consent_granted=self.consent or self.sm.state in {CallState.CONSENT, CallState.DISCLOSURE},
            collecting=collecting and self.sm.state not in {CallState.CONSENT, CallState.DISCLOSURE},
        )

        # Consent phase special-case: allow yes/no before consent flag
        if self.sm.state == CallState.CONSENT:
            return await self._handle_consent(text, speech_confidence)

        if gr.action == "end" and gr.rule == "RESPECT_NO":
            return await self._decline(text)

        # Registered once here if the guardrail already classified this signal,
        # so the intent-event branches below do not double-count it and burn
        # through the "two strikes" grace (anger_hits >= 2, OFF_SCRIPT score) in
        # a single utterance.
        gr_decision = None
        if gr.action == "escalate" or (gr.signal and gr.signal.value):
            if gr.signal:
                gr_decision = self.escalation.register(gr.signal, gr.reason)
                if gr_decision.should_escalate or gr.rule in {"NO_PAYMENT", "HUMAN_REQUEST"}:
                    return await self._escalate(gr.reason or gr_decision.reason, gr.signal)

        llm_hint = await self.groq.enrich_turn(
            {
                "text": text,
                "state": self.sm.state.value,
                "current_field": (self.journey.next_step(self.fields) or {}).get("id"),
                "known_fields": self.fields,
            }
        )

        intent = self.intent_engine.detect(
            text,
            state=self.sm.state.value,
            current_field=(self.journey.next_step(self.fields) or {}).get("id"),
            llm_hint=llm_hint if llm_hint else None,
        )

        event = intent["event"]
        intent_conf = float(intent.get("confidence", 0.7))

        if event == "CUSTOMER_NOT_INTERESTED":
            return await self._decline(text)
        if event == "CUSTOMER_HUMAN_REQUEST":
            self.escalation.register(EscalationSignal.HUMAN_REQUEST)
            return await self._escalate("Customer explicitly requested a human", EscalationSignal.HUMAN_REQUEST)
        if event == "CUSTOMER_PAYMENT":
            self.escalation.register(EscalationSignal.SENSITIVE)
            return await self._escalate("Payment/card information mentioned", EscalationSignal.SENSITIVE)
        if event == "CUSTOMER_ANGER":
            already = gr_decision is not None and gr.signal == EscalationSignal.ANGER
            decision = gr_decision if already else self.escalation.register(
                EscalationSignal.ANGER, "Anger detected"
            )
            if decision.should_escalate:
                return await self._escalate(decision.reason, EscalationSignal.ANGER)
        if event == "CUSTOMER_ADVICE":
            already = gr_decision is not None and gr.signal == EscalationSignal.OFF_SCRIPT
            decision = gr_decision if already else self.escalation.register(
                EscalationSignal.OFF_SCRIPT, "Advice requested"
            )
            msg = self.scripts.render("advice_limit")
            self._assistant(msg)
            if decision.should_escalate:
                return await self._escalate(decision.reason, EscalationSignal.OFF_SCRIPT)
            return self._result(msg, intent=intent["intent"])

        if event == "CUSTOMER_BUSY":
            msg = self.scripts.render("busy")
            self._assistant(msg)
            self._why("HANDLED_BUSY", "Customer indicated they are busy - offered brief continue or later human.", "interruption")
            return self._result(msg, event=event, intent=intent["intent"])

        if event == "CUSTOMER_INTERRUPT":
            self.interruptions += 1
            self.metrics.interruption()
            self.audit.emit("INTERRUPTION", self.call_id, text=text)
            msg = self.scripts.render("interrupt_ack")
            self._assistant(msg)
            return self._result(msg, event=event, intent=intent["intent"])

        if event == "CUSTOMER_REPEAT":
            last_ai = next((t["text"] for t in reversed(self.transcript) if t["role"] == "assistant"), "")
            msg = last_ai or self.scripts.render("low_confidence")
            self._assistant(msg)
            return self._result(msg, event=event, intent=intent["intent"])

        if event == "CUSTOMER_QUESTION":
            decision = self.escalation.register(EscalationSignal.OFF_SCRIPT, "Off-script question")
            msg = "I can help finish the Energy comparison details. For anything outside that, I can bring a person in."
            self._assistant(msg)
            if decision.should_escalate:
                return await self._escalate(decision.reason, EscalationSignal.OFF_SCRIPT)
            return self._result(msg, event=event, intent=intent["intent"])

        if self.sm.state == CallState.CLARIFYING:
            return await self._handle_clarification(text, speech_confidence, intent_conf, llm_hint)

        if self.sm.state == CallState.CONFIRMING:
            return await self._handle_confirm(text, intent)

        if self.sm.state in {CallState.WELCOME, CallState.RECOVER_CONTEXT, CallState.COLLECTING}:
            return await self._handle_collect(text, speech_confidence, intent_conf, llm_hint, event)

        msg = self.scripts.render("low_confidence")
        self._assistant(msg)
        return self._result(msg, intent=intent["intent"])

    async def _handle_consent(self, text: str, speech_confidence: float) -> TurnResult:
        decision = self.guardrails.check_consent_response(text)
        # also respect hard declines during consent
        gr = self.guardrails.evaluate(text, consent_granted=False, collecting=False)
        if gr.rule == "RESPECT_NO" or decision == "no":
            self.audit.emit("CONSENT_DENIED", self.call_id, text=text)
            self.metrics.decline()
            self.declined = True
            self.sm.transition(CallState.DECLINED, "consent_denied")
            msg = self.scripts.render("consent_denied")
            self._assistant(msg)
            self.sm.transition(CallState.ENDED, "after_decline")
            return self._result(
                msg,
                ended=True,
                why=self._why("STOP", "Customer declined recording consent - no further collection.", "consent"),
            )

        if decision == "yes":
            self.consent = True
            self.audit.emit("CONSENT_GRANTED", self.call_id)
            self.sm.transition(CallState.WELCOME, "consent_yes")
            last_step = self.lead.last_completed_step or "the start"
            msg = self.scripts.render("welcome", last_step=last_step.replace("_", " "))
            self._assistant(msg)
            self.sm.transition(CallState.RECOVER_CONTEXT, "welcome_done")

            known = ", ".join(self.fields.keys()) or "nothing yet"
            nxt = self.journey.next_step(self.fields)
            next_label = nxt.get("label", "the next detail") if nxt else "final confirmation"
            recover = self.scripts.render(
                "recover_context",
                known_fields=known,
                next_field=next_label.lower(),
            )
            self._assistant(recover)
            self.sm.transition(CallState.COLLECTING, "begin_collection")
            ask = self.scripts.ask_field(nxt, self.fields) if nxt else self.scripts.render("confirm_summary", summary=self._summary())
            if not nxt:
                self.sm.transition(CallState.CONFIRMING, "nothing_missing")
            self._assistant(ask)
            combined = f"{msg} {recover} {ask}"
            self._why(
                "ASKED_FIELD",
                f"{next_label} is required by the Energy journey and was not present in the recovered lead."
                if nxt
                else "All fields present - confirming before submit.",
                "journey",
            )
            return self._result(combined, intent="consent_yes")

        # unclear consent
        self.metrics.low_confidence()
        self.audit.emit("LOW_CONFIDENCE", self.call_id, phase="consent")
        msg = "Just to confirm - is it okay that this call is recorded?"
        self._assistant(msg)
        return self._result(
            msg,
            why=self._why("CLARIFY", "Consent response was unclear - must get an explicit yes/no.", "consent"),
        )

    async def _handle_collect(
        self,
        text: str,
        speech_confidence: float,
        intent_conf: float,
        llm_hint: dict,
        event: str,
    ) -> TurnResult:
        step = self.journey.next_step(self.fields)
        if not step:
            self.sm.transition(CallState.CONFIRMING, "all_fields")
            msg = self.scripts.render("confirm_summary", summary=self._summary())
            self._assistant(msg)
            return self._result(msg)

        if event == "CUSTOMER_CORRECTION":
            candidates = []
            nxt_id = (self.journey.next_step(self.fields) or {}).get("id")
            for step_def in self.journey.steps:
                if step_def["id"] in self.fields or step_def["id"] == nxt_id:
                    candidates.append(step_def)
            for step_def in reversed(candidates):
                extracted = self.extractor.extract(text, step_def, llm_hint if llm_hint else None)
                if extracted.get("value") is None:
                    continue
                old = self.fields.get(step_def["id"])
                if old == extracted["value"]:
                    continue
                # Prefer enum/structured fields when values clearly match validation
                if step_def.get("validation", {}).get("type") in {"enum", "regex", "integer"} or step_def["id"] in self.fields:
                    self.fields[step_def["id"]] = extracted["value"]
                    self.audit.emit("FIELD_CORRECTED", self.call_id, field=step_def["id"], value=extracted["value"])
                    msg = self.scripts.render(
                        "correction_ack",
                        field=step_def.get("label", step_def["id"]),
                        value=extracted["value"],
                    )
                    self._assistant(msg)
                    nxt = self.journey.next_step(self.fields)
                    if nxt:
                        ask = self.scripts.ask_field(nxt, self.fields)
                        self._assistant(ask)
                        return self._result(f"{msg} {ask}", event=event, intent="correction")
                    self.sm.transition(CallState.CONFIRMING, "after_correction")
                    confirm = self.scripts.render("confirm_summary", summary=self._summary())
                    self._assistant(confirm)
                    return self._result(f"{msg} {confirm}", event=event, intent="correction")
            # fall through to normal collect if we couldn't map a correction
            pass

        extracted = self.extractor.extract(text, step, llm_hint if llm_hint else None)
        field_conf = float(extracted.get("confidence", 0.2))
        snap, low, reason = self.confidence.evaluate(
            speech=speech_confidence,
            intent=intent_conf,
            field=field_conf,
            journey=0.9 if extracted.get("value") is not None else 0.5,
        )

        if extracted.get("value") is None or low or extracted.get("needs_clarification"):
            self.metrics.low_confidence()
            self.metrics.clarification()
            self.audit.emit("LOW_CONFIDENCE", self.call_id, field=step["id"], reason=reason)
            retries = self.field_retries.get(step["id"], 0) + 1
            self.field_retries[step["id"]] = retries
            decision = self.escalation.register(EscalationSignal.CONFUSION, reason)
            self.escalation.confusion_streak = retries
            if retries > 2 or decision.should_escalate:
                return await self._escalate(
                    f"Repeated confusion capturing {step['id']}",
                    EscalationSignal.CONFUSION,
                )
            self.sm.transition(CallState.CLARIFYING, "low_confidence")
            if extracted.get("value") is not None:
                self.pending_clarify_value = extracted["value"]
                msg = self.scripts.render("clarification", value=extracted["value"])
            else:
                msg = self.scripts.render("low_confidence")
            self._assistant(msg)
            self.audit.emit("CLARIFICATION", self.call_id, field=step["id"])
            return self._result(
                msg,
                confidence=snap,
                field=step["id"],
                why=self._why("CLARIFY", reason, "confidence"),
            )

        # success
        self.fields[step["id"]] = extracted["value"]
        self.field_retries[step["id"]] = 0
        self.escalation.note_success()
        self.audit.emit(
            "FIELD_CAPTURED",
            self.call_id,
            field=step["id"],
            value=extracted["value"],
            confidence=field_conf,
        )
        ack = self.scripts.acknowledge(step.get("label", step["id"]), extracted["value"])
        self._assistant(ack)

        nxt = self.journey.next_step(self.fields)
        if not nxt:
            self.sm.transition(CallState.CONFIRMING, "last_field")
            confirm = self.scripts.render("confirm_summary", summary=self._summary())
            self._assistant(confirm)
            return self._result(
                f"{ack} {confirm}",
                field=step["id"],
                value=extracted["value"],
                confidence=snap,
                why=self._why(
                    "ASKED_CONFIRM",
                    "All required Energy fields captured - confirming before submission.",
                    "journey",
                ),
            )

        self.sm.transition(CallState.COLLECTING, f"next:{nxt['id']}")
        ask = self.scripts.ask_field(nxt, self.fields)
        self._assistant(ask)
        return self._result(
            f"{ack} {ask}",
            field=step["id"],
            value=extracted["value"],
            confidence=snap,
            why=self._why(
                "ASKED_FIELD",
                f"{nxt.get('label')} is required by the Energy journey and was not present in the recovered lead.",
                "journey",
            ),
        )

    async def _handle_clarification(
        self,
        text: str,
        speech_confidence: float,
        intent_conf: float,
        llm_hint: dict,
    ) -> TurnResult:
        yes = self.guardrails.check_consent_response(text)
        step = self.journey.next_step(self.fields)
        if yes == "yes" and self.pending_clarify_value is not None and step:
            self.fields[step["id"]] = self.pending_clarify_value
            self.pending_clarify_value = None
            self.audit.emit("FIELD_CAPTURED", self.call_id, field=step["id"], via="clarification")
            self.sm.transition(CallState.COLLECTING, "clarified")
            self.escalation.note_success()
            ack = self.scripts.acknowledge(step.get("label", step["id"]), self.fields[step["id"]])
            nxt = self.journey.next_step(self.fields)
            if not nxt:
                self.sm.transition(CallState.CONFIRMING, "after_clarify")
                confirm = self.scripts.render("confirm_summary", summary=self._summary())
                self._assistant(f"{ack} {confirm}")
                return self._result(f"{ack} {confirm}")
            ask = self.scripts.ask_field(nxt, self.fields)
            self._assistant(f"{ack} {ask}")
            return self._result(f"{ack} {ask}")

        if yes == "no":
            self.pending_clarify_value = None
            self.sm.transition(CallState.COLLECTING, "clarify_rejected")
            msg = self.scripts.ask_field(step, self.fields, retries=1) if step else self.scripts.render("low_confidence")
            self._assistant(msg)
            return self._result(msg)

        # treat as new answer
        self.sm.transition(CallState.COLLECTING, "retry_collect")
        return await self._handle_collect(text, speech_confidence, intent_conf, llm_hint, "CUSTOMER_PROVIDE_INFO")

    async def _handle_confirm(self, text: str, intent: dict) -> TurnResult:
        event = intent.get("event")
        if event == "CUSTOMER_CONFIRM_YES" or self.guardrails.check_consent_response(text) == "yes":
            return await self._submit()
        if event == "CUSTOMER_CONFIRM_NO":
            # wipe last field for correction
            if self.fields:
                last = list(self.fields.keys())[-1]
                del self.fields[last]
            self.sm.transition(CallState.COLLECTING, "confirm_no")
            step = self.journey.next_step(self.fields)
            msg = self.scripts.ask_field(step, self.fields) if step else "Which detail should we fix?"
            self._assistant(msg)
            return self._result(msg)
        msg = self.scripts.render("confirm_summary", summary=self._summary())
        self._assistant(msg)
        return self._result(msg)

    async def _submit(self) -> TurnResult:
        assert self.lead
        self.sm.transition(CallState.SUBMITTING, "confirmed")
        self._assistant(self.scripts.render("submitting"))
        try:
            payload = self.submission.build(
                self.lead,
                self.fields,
                status="completed",
                consent=self.consent,
                dnc_checked=self.dnc_checked,
                recording_disclosed=self.recording_disclosed,
            )
        except ValueError as exc:
            self.sm.transition(CallState.ESCALATING, "submit_invalid")
            return await self._escalate(f"Submission validation failed: {exc}", EscalationSignal.LOW_CONFIDENCE)

        self.payload = payload
        self.audit.emit(
            "JOURNEY_SUBMITTED",
            self.call_id,
            endpoint=self.submitter.url,
            payload=payload.model_dump(),
        )

        receipt = await self.submitter.submit(payload)
        self.receipt = receipt

        if not receipt.accepted:
            self.metrics.submission_rejected()
            self.audit.emit(
                "JOURNEY_REJECTED",
                self.call_id,
                status_code=receipt.status_code,
                error=receipt.error,
            )
            # Never tell the customer it is done when the sandbox refused it.
            return await self._escalate(
                f"Journey submission was not accepted: {receipt.error}",
                EscalationSignal.LOW_CONFIDENCE,
            )

        self.metrics.submission_accepted()
        self.audit.emit(
            "JOURNEY_ACCEPTED",
            self.call_id,
            reference=receipt.reference,
            latency_ms=receipt.latency_ms,
            attempts=receipt.attempts,
        )
        self.sm.transition(CallState.COMPLETED, "submitted")
        msg = (
            self.scripts.render("completed_with_reference", reference=receipt.reference)
            if receipt.reference
            else self.scripts.render("completed")
        )
        self._assistant(msg)
        self.audit.emit("JOURNEY_COMPLETED", self.call_id)
        self.metrics.complete(
            self.call_id,
            len(self.fields),
            len(self.journey.steps),
            transcript_words=self._transcript_words(),
            turns=self.turns,
        )
        self.sm.transition(CallState.ENDED, "done")
        self.audit.emit("CALL_ENDED", self.call_id, status="completed")
        self._finalise("completed")
        return self._result(
            msg,
            ended=True,
            payload=payload,
            why=self._why(
                "SUBMIT",
                f"All validations passed - consent, DNC, required fields, no payment data. "
                f"Sandbox accepted it as {receipt.reference}.",
                "submit",
            ),
        )

    async def _decline(self, text: str) -> TurnResult:
        self.declined = True
        self.metrics.decline()
        self.audit.emit("CONSENT_DENIED" if not self.consent else "CALL_ENDED", self.call_id, reason="declined", text=text)
        self.sm.transition(CallState.DECLINED, "customer_no")
        msg = self.scripts.render("not_interested")
        self._assistant(msg)
        self.sm.transition(CallState.ENDED, "declined")
        self.metrics.abandon(self.call_id)
        try:
            self.payload = self.submission.build(
                self.lead,
                self.fields,
                status="declined",
                consent=self.consent,
                dnc_checked=self.dnc_checked,
                recording_disclosed=self.recording_disclosed,
            )
        except Exception:
            pass
        self._finalise("declined")
        return self._result(
            msg,
            ended=True,
            why=self._why("STOP", "Customer declined - respect-no guardrail. No pressure loops.", "guardrail"),
        )

    async def _escalate(self, reason: str, signal: EscalationSignal) -> TurnResult:
        assert self.lead
        self.handoff_phase = "FRUSTRATION_DETECTED" if signal == EscalationSignal.ANGER else "HUMAN_REQUEST"
        self.sm.transition(CallState.ESCALATING, reason)
        self.audit.emit("ESCALATION_TRIGGERED", self.call_id, reason=reason, signal=signal.value)
        if signal == EscalationSignal.HUMAN_REQUEST:
            self.audit.emit("HUMAN_REQUEST", self.call_id)
        if signal == EscalationSignal.SENSITIVE:
            self.audit.emit("PAYMENT_DETECTED", self.call_id)
            msg = self.scripts.render("payment_handoff")
        elif signal == EscalationSignal.ANGER:
            msg = self.scripts.render("frustration_handoff")
        else:
            msg = self.scripts.render("human_handoff")
        self._assistant(msg)

        self.handoff_phase = "HANDOFF_PREPARING"
        context = {
            "customer_name": f"{self.lead.first_name} {self.lead.last_name}",
            "fields": self.fields,
            "consent": self.consent,
            "reason": reason,
            "current_stage": self.journey.stage_name(self.fields),
            "transcript_tail": self.transcript[-8:],
        }
        summary = await self.groq.summarize_handoff(context)
        self.handoff_phase = "CONTEXT_PACKAGED"

        brief = HandoffBrief(
            customer=f"{self.lead.first_name} {self.lead.last_name}",
            journey="Energy Comparison",
            current_stage=self.journey.stage_name(self.fields),
            reason=reason,
            confidence=0.92,
            customer_mood=self.escalation.mood().value,
            fields_collected=list(self.fields.keys()),
            last_customer_statement=self.last_customer_text,
            recommended_opening=summary.get(
                "recommended_opening",
                "Hi, I can see what you've already provided, so you won't need to repeat those details.",
            ),
            conversation_summary=summary.get(
                "conversation_summary",
                "Customer contacted for Energy dropout recovery. Context preserved for human.",
            ),
            next_action=summary.get("next_action", f"Continue from {self.journey.stage_name(self.fields)}."),
            signals=self.escalation.signals and [s.value for s in self.escalation.signals] or [signal.value],
        )
        self.handoff_brief = brief
        self.sm.transition(CallState.HANDOFF, "brief_ready")

        # Move the live call to a human where the channel supports it.
        transfer = await self.telephony.transfer_call(self.call_id, "human_queue")
        self.transfer_result = transfer or {}
        self.audit.emit("CALL_TRANSFERRED", self.call_id, transfer=self.transfer_result)
        self.metrics.handoff()

        # Raise the ticket a human actually picks up, carrying everything collected.
        if self.handoffs:
            ticket = self.handoffs.raise_ticket(
                call_id=self.call_id,
                lead_id=self.lead.lead_id,
                customer=f"{self.lead.first_name} {self.lead.last_name}",
                phone=self.lead.phone,
                reason=reason,
                signals=[s.value for s in self.escalation.signals] or [signal.value],
                brief=brief,
                fields=self.fields,
                transcript=self.transcript,
                voice_mode=self.voice_mode,
                transfer=self.transfer_result,
            )
            self.handoff_ticket_id = ticket.ticket_id
            self.audit.emit("HANDOFF_QUEUED", self.call_id, ticket_id=ticket.ticket_id)

        self.handoff_phase = "HUMAN_READY"

        try:
            payload = self.submission.build(
                self.lead,
                self.fields,
                status="escalated",
                consent=self.consent,
                dnc_checked=self.dnc_checked,
                recording_disclosed=self.recording_disclosed,
            )
            self.payload = payload
        except Exception:
            payload = None

        # Record the partial journey too, unless a submission already failed here.
        if payload is not None and self.receipt is None:
            escalated_receipt = await self.submitter.submit(payload)
            self.receipt = escalated_receipt
            self.audit.emit(
                "JOURNEY_SUBMITTED",
                self.call_id,
                status="escalated",
                accepted=escalated_receipt.accepted,
                reference=escalated_receipt.reference,
            )

        self._why("ESCALATE", reason, "escalation")
        self.audit.emit("CALL_ENDED", self.call_id, status="handoff")
        self._finalise("handoff")
        return self._result(
            msg,
            escalated=True,
            handoff_brief=brief,
            payload=payload,
            ended=True,
            intent=signal.value.lower(),
        )

    def _transcript_words(self) -> int:
        return sum(len(str(t.get("text", "")).split()) for t in self.transcript)

    def _finalise(self, status: str) -> None:
        """Write the call artifact the recording disclosure promises, and persist."""
        try:
            self.recording_path = self.recorder.write(
                self.call_id,
                lead_id=self.lead.lead_id if self.lead else "",
                status=status,
                voice_mode=self.voice_mode,
                transcript=self.transcript,
                audit=[e.model_dump() for e in self.audit.events],
                why=[w.model_dump() for w in self.why_log],
                fields=self.fields,
                payload=self.payload.model_dump() if self.payload else None,
                receipt=self.receipt.model_dump() if self.receipt else None,
                handoff_brief=self.handoff_brief.model_dump() if self.handoff_brief else None,
                provider_recording_url=(self.transfer_result or {}).get("recordingUrl"),
            )
            self.audit.emit("RECORDING_STORED", self.call_id, path=self.recording_path)
        except Exception:
            self.recording_path = None

        if self.store:
            try:
                self.store.save_call(
                    self.call_id,
                    self.lead.lead_id if self.lead else "",
                    status,
                    self.voice_mode,
                    self.snapshot(),
                )
                if self.payload and self.receipt:
                    self.store.save_submission(
                        self.call_id,
                        self.lead.lead_id if self.lead else "",
                        self.payload.model_dump(),
                        self.receipt.model_dump(),
                    )
            except Exception:
                pass

    def _summary(self) -> str:
        parts = [f"{k.replace('_', ' ')} {v}" for k, v in self.fields.items()]
        return ", ".join(parts) if parts else "no fields yet"

    def _assistant(self, text: str) -> None:
        self.transcript.append({"role": "assistant", "text": text, "ts": utc_now()})

    def _customer(self, text: str) -> None:
        self.transcript.append({"role": "customer", "text": text, "ts": utc_now()})

    def _why(self, action: str, reason: str, category: str) -> WhyAction:
        item = WhyAction(action=action, reason=reason, category=category)
        self.why_log.append(item)
        return item

    def radar(self) -> dict[str, Any]:
        total = len(self.journey.steps)
        captured = sum(1 for s in self.journey.steps if s["id"] in self.fields)
        mood = self.escalation.mood().value
        if self.sm.state == CallState.HANDOFF:
            mood = Mood.ESCALATION.value
        return {
            "customer_mood": mood,
            "confidence": round(
                (
                    0.9
                    if self.consent
                    else 0.5
                ),
                2,
            ),
            "conversation_health": "Good"
            if self.escalation.risk_label() == "Low"
            else ("Watch" if self.escalation.risk_label() == "Medium" else "At Risk"),
            "interruptions": self.interruptions,
            "clarifications": self.metrics.snap.clarifications,
            "fields_captured": f"{captured} / {total}",
            "escalation_risk": self.escalation.risk_label(),
            "escalation_score": self.escalation.score,
            "handoff_phase": self.handoff_phase,
            "voice_mode": self.voice_mode,
            "ai_mode": self.groq.mode,
        }

    def recovery_context(self) -> dict[str, Any]:
        assert self.lead
        missing = [s["id"] for s in self.journey.missing_fields(self.fields)]
        return {
            "lead_id": self.lead.lead_id,
            "customer": f"{self.lead.first_name} {self.lead.last_name}",
            "last_completed_step": self.lead.last_completed_step,
            "previously_known_fields": list((self.lead.known_fields or {}).keys()),
            "missing_fields": missing,
            "recovery_objective": f"Collect {', '.join(missing) or 'confirmation'} and submit Energy journey",
            "known_fields": self.fields,
        }

    def _result(
        self,
        message: str,
        *,
        intent: str = "",
        event: str | None = None,
        field: str | None = None,
        value: Any = None,
        confidence: ConfidenceSnapshot | None = None,
        why: WhyAction | None = None,
        escalated: bool = False,
        handoff_brief: HandoffBrief | None = None,
        payload=None,
        ended: bool = False,
        speak: bool = True,
    ) -> TurnResult:
        progress = self.journey.progress(self.fields)
        # mark consent
        for p in progress:
            if p["id"] == "consent":
                p["status"] = "done" if self.consent else ("active" if self.sm.state == CallState.CONSENT else "pending")
            elif p["id"] in self.fields:
                p["status"] = "done"
            elif self.journey.next_step(self.fields) and p["id"] == self.journey.next_step(self.fields)["id"]:
                p["status"] = "active"

        return TurnResult(
            assistant_message=message,
            state=self.sm.state.value,
            intent=intent,
            event=event,
            field=field,
            value=value,
            confidence=confidence or ConfidenceSnapshot(),
            why=why or (self.why_log[-1] if self.why_log else None),
            escalated=escalated,
            handoff_brief=handoff_brief or self.handoff_brief,
            payload=payload or self.payload,
            receipt=self.receipt,
            handoff_ticket_id=self.handoff_ticket_id,
            ended=ended,
            speak=speak,
            radar=self.radar(),
            journey_progress=progress,
            extracted_fields=dict(self.fields),
            audit_tail=self.audit.tail(30),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "state": self.sm.state.value,
            "lead": self.lead.model_dump() if self.lead else None,
            "fields": self.fields,
            "consent": self.consent,
            "transcript": self.transcript,
            "why": [w.model_dump() for w in self.why_log],
            "radar": self.radar(),
            "recovery": self.recovery_context() if self.lead else None,
            "handoff_brief": self.handoff_brief.model_dump() if self.handoff_brief else None,
            "handoff_ticket_id": self.handoff_ticket_id,
            "transfer": self.transfer_result,
            "payload": self.payload.model_dump() if self.payload else None,
            "receipt": self.receipt.model_dump() if self.receipt else None,
            "recording_path": self.recording_path,
            "state_history": self.sm.history,
            "voice_mode": self.voice_mode,
            "groq": self.groq.status(),
            "audit": [e.model_dump() for e in self.audit.tail(100)],
        }

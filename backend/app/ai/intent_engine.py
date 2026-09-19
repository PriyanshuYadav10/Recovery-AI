from __future__ import annotations

import re
from typing import Any, Optional

from app.ai.guardrail_engine import GuardrailEngine
from app.models.enums import CustomerEvent


class IntentEngine:
    def __init__(self):
        self.guardrails = GuardrailEngine()

    def detect(
        self,
        text: str,
        *,
        state: str,
        current_field: Optional[str] = None,
        llm_hint: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        t = (text or "").strip()
        lowered = t.lower()

        if llm_hint and llm_hint.get("intent"):
            intent = llm_hint["intent"]
            confidence = float(llm_hint.get("confidence", 0.8))
            event = self._intent_to_event(intent)
            return {
                "intent": intent,
                "event": event.value if isinstance(event, CustomerEvent) else event,
                "confidence": confidence,
                "source": "llm",
            }

        g = self.guardrails.evaluate(t, consent_granted=True, collecting=False)
        if g.rule == "NO_PAYMENT":
            return self._pack("payment_mention", CustomerEvent.CUSTOMER_PAYMENT, 0.99)
        if g.rule == "RESPECT_NO":
            return self._pack("not_interested", CustomerEvent.CUSTOMER_NOT_INTERESTED, 0.98)
        if g.rule == "HUMAN_REQUEST":
            return self._pack("human_request", CustomerEvent.CUSTOMER_HUMAN_REQUEST, 0.99)
        if g.rule == "ANGER":
            return self._pack("anger", CustomerEvent.CUSTOMER_ANGER, 0.95)
        if g.rule == "NO_ADVICE":
            return self._pack("advice_request", CustomerEvent.CUSTOMER_ADVICE, 0.95)

        if self.guardrails.is_busy(t):
            return self._pack("busy", CustomerEvent.CUSTOMER_BUSY, 0.93)

        if re.search(r"\b(i meant|correction|actually (it'?s|i meant|no)|no i said|change that|not a )\b", lowered):
            return self._pack("correction", CustomerEvent.CUSTOMER_CORRECTION, 0.9)

        # Pure interrupt markers only (busy already handled above)
        if re.search(r"\b(wait|hold on|hang on|before that)\b", lowered) and not self.guardrails.is_busy(t):
            return self._pack("interrupt", CustomerEvent.CUSTOMER_INTERRUPT, 0.9)

        if re.search(r"\b(repeat|say that again|what did you say|pardon|come again|sorry,? what)\b", lowered):
            return self._pack("repeat", CustomerEvent.CUSTOMER_REPEAT, 0.92)

        if re.search(r"\b(why|how|what about|can you explain|who are you)\b", lowered):
            return self._pack("question", CustomerEvent.CUSTOMER_QUESTION, 0.8)

        if state in {"CONSENT", "DISCLOSURE"}:
            c = self.guardrails.check_consent_response(t)
            if c == "yes":
                return self._pack("consent_yes", CustomerEvent.CUSTOMER_CONSENT_YES, 0.95)
            if c == "no":
                return self._pack("consent_no", CustomerEvent.CUSTOMER_CONSENT_NO, 0.95)

        if state == "CONFIRMING":
            if self.guardrails.check_consent_response(t) == "yes" or re.search(
                r"\b(correct|looks good|that'?s right|confirm)\b", lowered
            ):
                return self._pack("confirm_yes", CustomerEvent.CUSTOMER_CONFIRM_YES, 0.93)
            if self.guardrails.check_consent_response(t) == "no" or re.search(
                r"\b(wrong|incorrect|not right)\b", lowered
            ):
                return self._pack("confirm_no", CustomerEvent.CUSTOMER_CONFIRM_NO, 0.9)

        return self._pack("provide_information", CustomerEvent.CUSTOMER_PROVIDE_INFO, 0.75)

    @staticmethod
    def _pack(intent: str, event: CustomerEvent, confidence: float) -> dict[str, Any]:
        return {
            "intent": intent,
            "event": event.value,
            "confidence": confidence,
            "source": "rules",
        }

    @staticmethod
    def _intent_to_event(intent: str) -> CustomerEvent:
        mapping = {
            "consent_yes": CustomerEvent.CUSTOMER_CONSENT_YES,
            "consent_no": CustomerEvent.CUSTOMER_CONSENT_NO,
            "not_interested": CustomerEvent.CUSTOMER_NOT_INTERESTED,
            "human_request": CustomerEvent.CUSTOMER_HUMAN_REQUEST,
            "anger": CustomerEvent.CUSTOMER_ANGER,
            "busy": CustomerEvent.CUSTOMER_BUSY,
            "interrupt": CustomerEvent.CUSTOMER_INTERRUPT,
            "correction": CustomerEvent.CUSTOMER_CORRECTION,
            "repeat": CustomerEvent.CUSTOMER_REPEAT,
            "question": CustomerEvent.CUSTOMER_QUESTION,
            "payment_mention": CustomerEvent.CUSTOMER_PAYMENT,
            "advice_request": CustomerEvent.CUSTOMER_ADVICE,
            "confirm_yes": CustomerEvent.CUSTOMER_CONFIRM_YES,
            "confirm_no": CustomerEvent.CUSTOMER_CONFIRM_NO,
            "provide_information": CustomerEvent.CUSTOMER_PROVIDE_INFO,
            "off_script": CustomerEvent.CUSTOMER_OFF_SCRIPT,
        }
        return mapping.get(intent, CustomerEvent.UNKNOWN)

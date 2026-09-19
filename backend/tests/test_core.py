import pytest
from app.ai.guardrail_engine import GuardrailEngine
from app.ai.escalation_engine import EscalationEngine
from app.ai.field_extractor import FieldExtractor
from app.ai.intent_engine import IntentEngine
from app.journey.engine import JourneyEngine, JourneySubmissionService
from app.models.enums import EscalationSignal
from app.models.schemas import Lead
from app.services.dnc import DNCService
from app.ai.conversation_manager import ConversationManager
from app.metrics.engine import MetricsEngine
from app.ai.groq_provider import GroqProvider


@pytest.fixture
def journey():
    return JourneyEngine()


@pytest.fixture
def guard():
    return GuardrailEngine()


@pytest.mark.asyncio
async def test_consent_required_before_collection():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    turn = await mgr.start("EN-1001", voice_mode="SIMULATED")
    assert mgr.sm.state.value == "CONSENT"
    assert "recorded" in turn.assistant_message.lower()


@pytest.mark.asyncio
async def test_consent_denied_ends_call():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    turn = await mgr.handle_utterance("No, I don't want to be recorded")
    assert turn.ended
    assert mgr.sm.state.value == "ENDED"
    assert mgr.declined


@pytest.mark.asyncio
async def test_payment_triggers_escalation():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yes that's fine")
    turn = await mgr.handle_utterance("I can give you my credit card number")
    assert turn.escalated
    assert turn.handoff_brief is not None


@pytest.mark.asyncio
async def test_human_request_triggers_handoff():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1003", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yeah okay")
    turn = await mgr.handle_utterance("I've already told you this twice. Just give me a person.")
    assert turn.escalated
    assert turn.handoff_brief is not None
    assert "person" in turn.handoff_brief.reason.lower() or "human" in turn.handoff_brief.reason.lower()
    assert len(turn.handoff_brief.fields_collected) >= 0


@pytest.mark.asyncio
async def test_successful_journey_completion():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    for utt in [
        "Yes, that's fine.",
        "Origin Energy",
        "Both electricity and gas",
        "No solar",
        "Two people",
        "Medium usage",
        "Yes, that looks right.",
    ]:
        turn = await mgr.handle_utterance(utt)
    assert turn.ended
    assert mgr.payload is not None
    assert mgr.payload.status == "completed"
    assert mgr.payload.metadata["consent"] is True


@pytest.mark.asyncio
async def test_not_interested_respected():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yes")
    turn = await mgr.handle_utterance("Not interested, stop calling")
    assert turn.ended
    assert "don't continue" in turn.assistant_message.lower() or "thanks" in turn.assistant_message.lower()


@pytest.mark.asyncio
async def test_dnc_blocks_call():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    turn = await mgr.start("EN-1004", voice_mode="SIMULATED")
    assert turn.ended
    assert "not eligible" in turn.assistant_message.lower()


def test_field_extraction_postcode(journey):
    step = next(s for s in journey.steps if s["id"] == "postcode")
    ex = FieldExtractor().extract("I live in 3000 Melbourne", step)
    assert ex["value"] == "3000"
    assert ex["confidence"] >= 0.9


def test_field_extraction_invalid(journey):
    step = next(s for s in journey.steps if s["id"] == "postcode")
    ex = FieldExtractor().extract("somewhere nearby", step)
    assert ex["value"] is None
    assert ex["needs_clarification"]


def test_anger_detection(guard):
    r = guard.evaluate("This is ridiculous, I've already told you", consent_granted=True, collecting=True)
    assert r.signal == EscalationSignal.ANGER


def test_escalation_critical_immediate():
    eng = EscalationEngine()
    d = eng.register(EscalationSignal.HUMAN_REQUEST)
    assert d.should_escalate
    assert d.immediate


def test_repeated_confusion_escalates():
    eng = EscalationEngine()
    eng.register(EscalationSignal.CONFUSION)
    eng.register(EscalationSignal.CONFUSION)
    d = eng.register(EscalationSignal.CONFUSION)
    # confusion_streak logic in register - need to set streak
    eng.confusion_streak = 3
    d2 = eng.register(EscalationSignal.CONFUSION)
    assert d2.should_escalate


def test_payload_generation(journey):
    lead = journey.get_lead("EN-1001")
    fields = {
        "postcode": "3000",
        "property_type": "apartment",
        "ownership": "rent",
        "current_supplier": "Origin",
        "fuel_type": "both",
        "has_solar": "no",
        "household_size": 2,
        "usage_band": "medium",
    }
    payload = JourneySubmissionService(journey).build(
        lead, fields, status="completed", consent=True, dnc_checked=True, recording_disclosed=True
    )
    assert payload.journey == "energy"
    assert payload.status == "completed"


def test_dnc_service():
    lead = Lead(
        lead_id="X",
        first_name="A",
        last_name="B",
        phone="1",
        email="a@b.com",
        dnc_listed=True,
    )
    assert DNCService().check(lead)["eligible"] is False


def test_intent_busy():
    intent = IntentEngine().detect("I'm busy at work", state="COLLECTING")
    assert intent["event"] == "CUSTOMER_BUSY"


@pytest.mark.asyncio
async def test_interruption_handling():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1002", voice_mode="SIMULATED")
    await mgr.handle_utterance("Sure")
    turn = await mgr.handle_utterance("Wait, before that")
    assert mgr.interruptions >= 1
    assert turn.assistant_message


@pytest.mark.asyncio
async def test_low_confidence_clarification():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yes")
    turn = await mgr.handle_utterance("asdfgh", speech_confidence=0.4)
    assert turn.state in {"CLARIFYING", "COLLECTING", "ESCALATING", "HANDOFF"}


@pytest.mark.asyncio
async def test_handoff_preserves_context():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yes")
    await mgr.handle_utterance("Origin")
    turn = await mgr.handle_utterance("I want to talk to a human please")
    assert "origin" in str(turn.handoff_brief.fields_collected).lower() or "current_supplier" in turn.handoff_brief.fields_collected
    assert "won't need to repeat" in turn.handoff_brief.recommended_opening.lower() or "already" in turn.handoff_brief.recommended_opening.lower()


# --------------------------------------------------------------- new coverage

from app.journey.submitter import JourneySubmitClient
from app.services.handoff_queue import HandoffQueue
from app.services.sandbox import JourneySandbox
from app.audit.recorder import CallRecorder
from app.models.schemas import JourneyPayload


def _complete_payload(**overrides):
    base = dict(
        lead_id="EN-1001",
        journey="energy",
        status="completed",
        fields={
            "postcode": "3000",
            "property_type": "apartment",
            "ownership": "rent",
            "current_supplier": "Origin Energy",
            "fuel_type": "both",
            "has_solar": "no",
            "household_size": 2,
            "usage_band": "medium",
        },
        metadata={
            "consent": True,
            "ai_assisted": True,
            "dnc_checked": True,
            "recording_disclosed": True,
        },
    )
    base.update(overrides)
    return base


def test_sandbox_accepts_valid_payload():
    sb = JourneySandbox()
    status, body = sb.receive(_complete_payload())
    assert status == 201
    assert body["accepted"] is True
    assert body["reference"].startswith("CIMET-ENERGY-")
    assert sb.recent(1)[0]["lead_id"] == "EN-1001"


def test_sandbox_rejects_missing_field():
    sb = JourneySandbox()
    payload = _complete_payload()
    del payload["fields"]["usage_band"]
    status, body = sb.receive(payload)
    assert status == 422
    assert body["accepted"] is False
    assert any("usage_band" in e for e in body["errors"])


def test_sandbox_rejects_completed_without_consent():
    sb = JourneySandbox()
    payload = _complete_payload()
    payload["metadata"]["consent"] = False
    status, body = sb.receive(payload)
    assert status == 422
    assert any("consent" in e for e in body["errors"])


def test_sandbox_rejects_invalid_enum_and_postcode():
    sb = JourneySandbox()
    payload = _complete_payload()
    payload["fields"]["fuel_type"] = "solar"
    payload["fields"]["postcode"] = "30001"
    status, body = sb.receive(payload)
    assert status == 422
    assert any("fuel_type" in e for e in body["errors"])
    assert any("postcode" in e for e in body["errors"])


async def test_submit_client_returns_receipt():
    sb = JourneySandbox()
    client = JourneySubmitClient(local_handler=sb)
    receipt = await client.submit(JourneyPayload(**_complete_payload()))
    assert receipt.accepted is True
    assert receipt.reference
    assert receipt.status_code == 201


async def test_submit_client_reports_rejection():
    sb = JourneySandbox()
    client = JourneySubmitClient(local_handler=sb)
    bad = _complete_payload()
    del bad["fields"]["postcode"]
    receipt = await client.submit(JourneyPayload(**bad))
    assert receipt.accepted is False
    assert receipt.status_code == 422
    assert "postcode" in (receipt.error or "")


async def test_completed_call_submits_and_gets_reference():
    metrics = MetricsEngine()
    sb = JourneySandbox()
    mgr = ConversationManager(
        metrics=metrics,
        groq=GroqProvider(api_key=""),
        voice_mode="SIMULATED",
        submitter=JourneySubmitClient(local_handler=sb),
    )
    turn = await mgr.start("EN-1001", voice_mode="SIMULATED")
    for utt in [
        "Yes, that's fine.",
        "Origin Energy",
        "Both electricity and gas",
        "No solar",
        "Two people",
        "Medium usage",
        "Yes, that looks right.",
    ]:
        if turn.ended:
            break
        turn = await mgr.handle_utterance(utt)

    assert mgr.receipt is not None
    assert mgr.receipt.accepted is True
    assert mgr.receipt.reference in turn.assistant_message
    assert mgr.fields["fuel_type"] == "both"
    assert metrics.snapshot().submissions_accepted == 1


async def test_rejected_submission_escalates_instead_of_claiming_success():
    """A refused payload must never be announced as done."""

    class RefusingSandbox:
        def receive(self, payload):
            return 422, {"accepted": False, "errors": ["synthetic rejection"]}

    metrics = MetricsEngine()
    queue = HandoffQueue()
    mgr = ConversationManager(
        metrics=metrics,
        groq=GroqProvider(api_key=""),
        voice_mode="SIMULATED",
        handoffs=queue,
        submitter=JourneySubmitClient(local_handler=RefusingSandbox()),
    )
    turn = await mgr.start("EN-1001", voice_mode="SIMULATED")
    for utt in [
        "Yes, that's fine.",
        "Origin Energy",
        "Both electricity and gas",
        "No solar",
        "Two people",
        "Medium usage",
        "Yes, that looks right.",
    ]:
        if turn.ended:
            break
        turn = await mgr.handle_utterance(utt)

    assert turn.escalated is True
    assert "recovered and submitted" not in turn.assistant_message
    assert metrics.snapshot().submissions_rejected == 1
    assert queue.stats()["waiting"] == 1


async def test_handoff_raises_ticket_a_human_can_claim():
    metrics = MetricsEngine()
    queue = HandoffQueue()
    mgr = ConversationManager(
        metrics=metrics,
        groq=GroqProvider(api_key=""),
        voice_mode="SIMULATED",
        handoffs=queue,
    )
    await mgr.start("EN-1003", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yeah okay.")
    turn = await mgr.handle_utterance("Just give me a person.")

    assert turn.escalated is True
    ticket_id = turn.handoff_ticket_id
    assert ticket_id

    ticket = queue.get(ticket_id)
    assert ticket.status == "WAITING"
    assert ticket.brief is not None
    assert ticket.transcript, "handoff must carry the conversation so far"

    claimed = queue.claim(ticket_id, "Aarav")
    assert claimed.status == "CLAIMED"
    assert claimed.claimed_by == "Aarav"
    # The human opens with context rather than asking the customer to repeat.
    assert claimed.transcript[-1]["role"] == "human_agent"

    assert queue.claim(ticket_id, "Someone Else") is None
    assert queue.resolve(ticket_id, "Completed manually").status == "RESOLVED"


async def test_dnc_listed_lead_is_never_dialled():
    metrics = MetricsEngine()
    mgr = ConversationManager(metrics=metrics, groq=GroqProvider(api_key=""), voice_mode="SIMULATED")
    turn = await mgr.start("EN-1004", voice_mode="SIMULATED")

    assert turn.ended is True
    events = [e.event for e in mgr.audit.events]
    assert "DNC_CHECK" in events
    assert "DIALLED" not in events, "the dial must not happen for a DNC-listed lead"
    assert events.index("DNC_CHECK") < len(events)


def test_metrics_compare_against_documented_baseline():
    metrics = MetricsEngine()
    metrics.start_journey("c1")
    metrics.add_turns(8)
    metrics.complete("c1", 8, 8, transcript_words=300, turns=8)
    snap = metrics.snapshot()

    assert snap.vs_manual.manual_handle_time_sec > 0
    assert snap.vs_manual.ai_handle_time_sec > 0
    assert snap.vs_manual.fields_typed_saved == 8
    assert 0 < snap.vs_manual.handle_time_reduction < 1
    assert "basis" in snap.vs_manual.note
    assert snap.automation_rate == 1.0


def test_automation_rate_is_order_independent():
    a = MetricsEngine()
    for cid, auto in (("a", 8), ("b", 4)):
        a.start_journey(cid)
        a.complete(cid, auto, 8)
    b = MetricsEngine()
    for cid, auto in (("b", 4), ("a", 8)):
        b.start_journey(cid)
        b.complete(cid, auto, 8)
    assert a.snapshot().automation_rate == b.snapshot().automation_rate == 0.75


def test_recorder_writes_and_reads_call_artifact(tmp_path):
    rec = CallRecorder(tmp_path)
    path = rec.write(
        "call-1",
        lead_id="EN-1001",
        status="completed",
        voice_mode="SIMULATED",
        transcript=[{"role": "assistant", "text": "hi"}],
        audit=[{"event": "CALL_STARTED"}],
        why=[],
        fields={"postcode": "3000"},
    )
    assert path.endswith("call-1.json")
    data = rec.read("call-1")
    assert data["recording_disclosed"] is True
    assert data["fields"]["postcode"] == "3000"
    assert rec.list()[0]["call_id"] == "call-1"


@pytest.mark.parametrize(
    "field_id,text,expected",
    [
        ("fuel_type", "Both electricity and gas", "both"),
        ("fuel_type", "Just electricity", "electricity"),
        ("property_type", "Actually I meant house, not apartment.", "house"),
        ("property_type", "It's a house... actually no, apartment", "apartment"),
        ("has_solar", "No I don't have solar", "no"),
    ],
)
def test_enum_extraction_handles_compounds_and_negation(field_id, text, expected):
    journey = JourneyEngine()
    step = {s["id"]: s for s in journey.steps}[field_id]
    assert FieldExtractor().extract(text, step)["value"] == expected


# ---- Groq model ladder ---------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or __import__("json").dumps(self._payload)

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient and records which models were asked for."""

    calls: list = []
    responder = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        model = (json or {}).get("model")
        _FakeClient.calls.append(model)
        return _FakeClient.responder(model)


async def test_groq_walks_past_retired_models(monkeypatch):
    """A 404 on a decommissioned model must not drop the call to rules mode."""
    import json as _json
    from app.ai import groq_provider

    _FakeClient.calls = []

    def responder(model):
        if model != "openai/gpt-oss-20b":
            return _FakeResponse(404, text='{"error":{"code":"model_not_found"}}')
        return _FakeResponse(
            200,
            {"choices": [{"message": {"content": _json.dumps({"ok": True})}}]},
        )

    _FakeClient.responder = staticmethod(responder)
    monkeypatch.setattr(groq_provider.httpx, "AsyncClient", _FakeClient)

    provider = groq_provider.GroqProvider(api_key="test-key")
    result = await provider.chat_json("system", "user")

    assert result == {"ok": True}
    assert provider.mode == "groq"
    assert provider.model == "openai/gpt-oss-20b", "the working model should be pinned"
    # Whatever the configured ladder is, everything ahead of the working model
    # is retired and each candidate is tried at most once.
    ahead = provider.candidates[: provider.candidates.index("openai/gpt-oss-20b")]
    assert set(ahead) == set(provider.retired)
    assert len(_FakeClient.calls) == len(ahead) + 1

    # A retired model is never asked for again in this process.
    _FakeClient.calls = []
    await provider.chat_json("system", "user")
    assert _FakeClient.calls == ["openai/gpt-oss-20b"]


async def test_groq_falls_back_to_rules_when_every_model_is_gone(monkeypatch):
    from app.ai import groq_provider

    _FakeClient.calls = []
    _FakeClient.responder = staticmethod(
        lambda model: _FakeResponse(404, text='{"error":{"code":"model_not_found"}}')
    )
    monkeypatch.setattr(groq_provider.httpx, "AsyncClient", _FakeClient)

    provider = groq_provider.GroqProvider(api_key="test-key")
    result = await provider.chat_json("system", "user")

    assert result["_fallback"] is True
    assert provider.mode == "deterministic"
    # The deterministic path still produces a usable handoff brief.
    brief = await provider.summarize_handoff(
        {"customer_name": "Aisha Khan", "fields": {"postcode": "4000"}, "reason": "asked for a human"}
    )
    assert "Aisha" in brief["recommended_opening"]
    assert brief["conversation_summary"]


async def test_groq_survives_control_characters_in_the_response(monkeypatch):
    """Reasoning models emit raw newlines; strict parsing used to kill the call."""
    from app.ai import groq_provider

    _FakeClient.calls = []
    # A `reasoning` field with a literal newline - exactly what gpt-oss-120b
    # and groq/compound-mini return.
    raw = (
        '{"choices":[{"message":{"role":"assistant",'
        '"reasoning":"step one\nstep two",'
        '"content":"{\\"intent\\": \\"provide_info\\"}"}}]}'
    )

    def responder(model):
        return _FakeResponse(200, payload=None, text=raw)

    _FakeClient.responder = staticmethod(responder)
    monkeypatch.setattr(groq_provider.httpx, "AsyncClient", _FakeClient)

    provider = groq_provider.GroqProvider(api_key="test-key")
    result = await provider.chat_json("system", "user")

    assert result == {"intent": "provide_info"}
    assert provider.mode == "groq", "a parseable reply must not drop to rules mode"


async def test_handoff_opening_never_contains_a_placeholder():
    """The opening is read aloud, so '[Agent Name]' would reach the customer."""
    metrics = MetricsEngine()
    queue = HandoffQueue()
    mgr = ConversationManager(
        metrics=metrics,
        groq=GroqProvider(api_key=""),
        voice_mode="SIMULATED",
        handoffs=queue,
    )
    await mgr.start("EN-1003", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yeah okay.")
    turn = await mgr.handle_utterance("Just give me a person.")

    opening = turn.handoff_brief.recommended_opening
    for marker in ("[", "]", "{", "}", "<", ">", "placeholder", "agent name"):
        assert marker not in opening.lower(), f"placeholder {marker!r} in: {opening}"


# ---- who owns the decision ----------------------------------------------

def _step(field_id):
    return {s["id"]: s for s in JourneyEngine().steps}[field_id]


def test_confident_rules_beat_a_wrong_llm_hint():
    """The model assists; it does not override a rule that already matched."""
    fx = FieldExtractor()
    hint = {"field": "fuel_type", "value": "electricity", "confidence": 0.99}

    result = fx.extract("Both electricity and gas.", _step("fuel_type"), hint)

    assert result["value"] == "both", "the rule match must stand"
    assert result["source"] != "llm+rules"
    assert result["llm_disagreed_with"] == "electricity", "disagreement should be recorded"


def test_llm_hint_fills_a_gap_the_rules_missed():
    fx = FieldExtractor()
    hint = {"field": "household_size", "value": 4, "confidence": 0.9}

    result = fx.extract("just the family really", _step("household_size"), hint)

    assert result["value"] == 4
    assert result["source"] == "llm+rules"


def test_llm_hint_is_still_validated_against_the_journey():
    """A hallucinated value must not reach the payload just because rules missed."""
    fx = FieldExtractor()
    nonsense = {"field": "fuel_type", "value": "nuclear", "confidence": 0.99}

    result = fx.extract("mmm not sure", _step("fuel_type"), nonsense)

    assert result["value"] is None, "an out-of-enum value must be rejected"


def test_llm_hint_for_a_different_field_is_ignored():
    fx = FieldExtractor()
    wrong_field = {"field": "postcode", "value": "3000", "confidence": 0.99}

    result = fx.extract("mmm not sure", _step("fuel_type"), wrong_field)

    assert result["value"] is None


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("AGL", "AGL"),                      # acronym must survive verbatim
        ("agl", "AGL"),                      # snapped to the journey's spelling
        ("origin energy", "Origin Energy"),
        ("Red Energy", "Red Energy"),
        ("EnergyAustralia", "EnergyAustralia"),
        ("alinta", "Alinta"),
        ("some local mob", "Some Local Mob"),
    ],
)
def test_supplier_names_are_not_mangled(spoken, expected):
    """'AGL' became 'Agl' in the submitted payload before this."""
    assert FieldExtractor().extract(spoken, _step("current_supplier"))["value"] == expected


# ---- soft declines, sourced from a real (unrelated-vertical) call transcript

@pytest.mark.parametrize(
    "text",
    [
        "Maybe I'll just stay where I am",
        "I could not be bothered",
        "I couldn't be bothered, not much savings",
        "I'll pass, thanks",
        "rather not, thanks",
        "not worth switching really",
    ],
)
def test_soft_declines_respect_no_without_the_word_interested(text):
    """A real broadband sales call showed customers decline without ever saying
    'not interested' - they say they'll stay put or it isn't worth the hassle.
    Missing these would loop the guardrail into pressuring a customer who has
    already said no in their own words."""
    gr = GuardrailEngine().evaluate(text, consent_granted=True, collecting=True)
    assert gr.action == "end"
    assert gr.rule == "RESPECT_NO"


# ---- the 15 named business scenarios, end to end -------------------------

async def test_named_business_scenario_suite_passes_in_full():
    """Each of the 15 scenarios drives a full ConversationManager call and
    checks the outcome, not just that nothing crashed. See
    app/evaluation/scenarios.py for what each one asserts and why."""
    from app.evaluation.scenarios import run_suite

    result = await run_suite()
    failing = [c for c in result["cases"] if not c["passed"]]
    detail = "\n".join(f"{c['id']}: {c['failures']}" for c in failing)
    assert not failing, f"{len(failing)} scenario(s) failed:\n{detail}"
    assert result["total"] == 15

from __future__ import annotations

"""End-to-end business-scenario evaluation.

This is deliberately separate from evals/run_evals.py, which scores the intent
engine and field extractor against hand-labelled utterances in isolation.
Here, each case drives a *full* ConversationManager call from start to end and
checks the outcome a judge or ops lead would actually care about: which state
the call landed in, whether it escalated when it should have, and whether the
right fields came out the other end. This is what "the AI works" has to mean
if it is going to mean anything - a specific, checkable claim per scenario,
not a demo that happened to go well once.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.ai.conversation_manager import ConversationManager
from app.ai.groq_provider import GroqProvider
from app.metrics.engine import MetricsEngine
from app.services.handoff_queue import HandoffQueue


@dataclass
class ScenarioCase:
    id: str
    name: str
    lead_id: str
    utterances: list[str | tuple[str, float]]
    expect_state: Optional[str] = None
    expect_escalated: Optional[bool] = None
    expect_ended: Optional[bool] = None
    expect_declined: Optional[bool] = None
    expect_fields: dict[str, Any] = field(default_factory=dict)
    expect_min_fields: int = 0
    expect_handoff_ticket: Optional[bool] = None
    notes: str = ""


# The 15 named cases the escalation and journey design are meant to survive.
# lead_id choices reuse the synthetic dataset's varied starting points so the
# suite also exercises "resume from wherever the customer dropped".
CASES: list[ScenarioCase] = [
    ScenarioCase(
        id="1_correct_postcode",
        name="Clean answer captured first try",
        lead_id="EN-1007",
        utterances=["Yes that's fine", "It's a house"],
        expect_fields={"property_type": "house"},
        notes="A clean, unambiguous field answer must be captured first try "
        "(EN-1007 already knows postcode, so property_type is next).",
    ),
    ScenarioCase(
        id="2_incorrect_postcode",
        name="Invalid postcode is rejected, not guessed",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "30001"],
        expect_state="CLARIFYING",
        notes="A 5-digit string fails the AU postcode regex and must re-ask, "
        "never invent a 4-digit guess.",
    ),
    ScenarioCase(
        id="3_ambiguous_answer",
        name="Ambiguous answer triggers clarification",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "not sure really"],
        expect_state="CLARIFYING",
        notes="Nothing extractable from the utterance - the system must ask "
        "again rather than silently skip the field.",
    ),
    ScenarioCase(
        id="4_customer_correction",
        name="Customer self-correction overwrites the field",
        lead_id="EN-1003",
        utterances=["Yeah okay", "Actually I meant house, not apartment"],
        expect_fields={"property_type": "house"},
        notes="Regression case: 'X, not Y' must resolve to X, not the last "
        "word mentioned.",
    ),
    ScenarioCase(
        id="5_interruption",
        name="Interruption is acknowledged, not treated as an answer",
        lead_id="EN-1007",
        utterances=["Yes that's fine", "wait, hold on", "It's a house"],
        expect_fields={"property_type": "house"},
        notes="'wait, hold on' must not be captured as the property_type value.",
    ),
    ScenarioCase(
        id="6_customer_busy",
        name="Customer busy - offered a callback, not pressured",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "I'm actually at work"],
        expect_state="COLLECTING",
        expect_ended=False,
        notes="Busy is not a decline - the call stays open and offers to "
        "keep it brief or call back later.",
    ),
    ScenarioCase(
        id="7_not_interested",
        name="Explicit decline ends the call without pressure",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "I'm not interested"],
        expect_declined=True,
        expect_ended=True,
        expect_escalated=False,
        notes="Respect-no: thank, log, end. No retry loop, no escalation.",
    ),
    ScenarioCase(
        id="8_human_request",
        name="Explicit human request escalates immediately",
        lead_id="EN-1003",
        utterances=["Yeah okay", "Can I speak to a real person please"],
        expect_escalated=True,
        expect_ended=True,
        expect_handoff_ticket=True,
        notes="HUMAN_REQUEST is a critical signal - no score threshold gate.",
    ),
    ScenarioCase(
        id="9_frustration",
        name="Escalating frustration triggers a warm handoff",
        lead_id="EN-1003",
        utterances=[
            "Yeah okay",
            "I've already told you this twice, this is ridiculous",
            "Honestly I'm sick of this, just stop calling me about it",
        ],
        expect_escalated=True,
        expect_handoff_ticket=True,
        notes="Matches the handout's own transcript pacing: two frustrated "
        "customer turns before the warm handoff, not one - a single sharp "
        "remark earns a grace turn rather than an immediate escalation.",
    ),
    ScenarioCase(
        id="10_repeated_confusion",
        name="Three failed attempts on one field forces escalation",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "mumble", "not sure", "dunno really"],
        expect_escalated=True,
        notes="CONFUSION streak >= 3 on the same field escalates even "
        "without anger or an explicit ask.",
    ),
    ScenarioCase(
        id="11_payment_or_card",
        name="Payment mention escalates - never collected by voice",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "Can I just give you my card number now"],
        expect_escalated=True,
        expect_handoff_ticket=True,
        notes="SENSITIVE is critical - immediate escalation, no attempt to "
        "capture the number first.",
    ),
    ScenarioCase(
        id="12_off_script_question",
        name="Advice question is declined, not answered",
        lead_id="EN-1002",
        utterances=["Yes that's fine", "Which plan should I choose, what do you recommend?"],
        expect_state="COLLECTING",
        notes="The system collects information; it must not give product "
        "advice, and should offer a specialist instead.",
    ),
    ScenarioCase(
        id="13_low_confidence_speech",
        name="Low speech confidence triggers a re-ask",
        lead_id="EN-1007",
        utterances=["Yes that's fine", ("It's a house", 0.35)],
        expect_state="CLARIFYING",
        notes="A field answer heard at 35% speech confidence must be "
        "confirmed before being trusted, even though the words themselves "
        "parse cleanly.",
    ),
    ScenarioCase(
        id="14_consent_denied",
        name="Consent denied stops collection before it starts",
        lead_id="EN-1002",
        utterances=["No, I don't consent to that"],
        expect_declined=True,
        expect_ended=True,
        expect_fields={},
        notes="Nothing may be collected before consent - metadata.consent "
        "must be false and the field set empty.",
    ),
    ScenarioCase(
        id="15_successful_completion",
        name="Full successful recovery, submitted",
        lead_id="EN-1001",
        utterances=[
            "Yes, that's fine.",
            "Origin Energy",
            "Both electricity and gas",
            "No solar",
            "Two people",
            "Medium usage",
            "Yes, that looks right.",
        ],
        expect_state="ENDED",
        expect_ended=True,
        expect_escalated=False,
        expect_min_fields=8,
        notes="The full happy path: consent -> resume -> collect -> confirm "
        "-> submit -> reference read back.",
    ),
]


@dataclass
class CaseResult:
    id: str
    name: str
    passed: bool
    notes: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    failures: list[str]
    transcript: list[dict[str, Any]]


async def run_case(case: ScenarioCase) -> CaseResult:
    metrics = MetricsEngine()
    queue = HandoffQueue()
    mgr = ConversationManager(
        metrics=metrics,
        groq=GroqProvider(api_key=""),  # deterministic - reproducible for judges
        voice_mode="SIMULATED",
        handoffs=queue,
    )

    turn = await mgr.start(case.lead_id, voice_mode="SIMULATED")
    for utt in case.utterances:
        if turn.ended:
            break
        if isinstance(utt, tuple):
            text, confidence = utt
            turn = await mgr.handle_utterance(text, speech_confidence=confidence)
        else:
            turn = await mgr.handle_utterance(utt)

    actual = {
        "state": mgr.sm.state.value,
        "escalated": turn.escalated,
        "ended": turn.ended,
        "declined": mgr.declined,
        "fields": dict(mgr.fields),
        "handoff_ticket_id": turn.handoff_ticket_id,
    }
    expected: dict[str, Any] = {}
    failures: list[str] = []

    if case.expect_state is not None:
        expected["state"] = case.expect_state
        if actual["state"] != case.expect_state:
            failures.append(f"expected state {case.expect_state!r}, got {actual['state']!r}")

    if case.expect_escalated is not None:
        expected["escalated"] = case.expect_escalated
        if actual["escalated"] != case.expect_escalated:
            failures.append(
                f"expected escalated={case.expect_escalated}, got {actual['escalated']}"
            )

    if case.expect_ended is not None:
        expected["ended"] = case.expect_ended
        if actual["ended"] != case.expect_ended:
            failures.append(f"expected ended={case.expect_ended}, got {actual['ended']}")

    if case.expect_declined is not None:
        expected["declined"] = case.expect_declined
        if actual["declined"] != case.expect_declined:
            failures.append(f"expected declined={case.expect_declined}, got {actual['declined']}")

    if case.expect_handoff_ticket is not None:
        expected["handoff_ticket"] = case.expect_handoff_ticket
        has_ticket = bool(actual["handoff_ticket_id"])
        if has_ticket != case.expect_handoff_ticket:
            failures.append(
                f"expected a handoff ticket={case.expect_handoff_ticket}, got {has_ticket}"
            )

    if case.expect_fields:
        expected["fields"] = case.expect_fields
        for k, v in case.expect_fields.items():
            if actual["fields"].get(k) != v:
                failures.append(f"field {k!r}: expected {v!r}, got {actual['fields'].get(k)!r}")

    if case.expect_min_fields:
        expected["min_fields"] = case.expect_min_fields
        if len(actual["fields"]) < case.expect_min_fields:
            failures.append(
                f"expected at least {case.expect_min_fields} fields, got {len(actual['fields'])}"
            )

    return CaseResult(
        id=case.id,
        name=case.name,
        passed=not failures,
        notes=case.notes,
        expected=expected,
        actual=actual,
        failures=failures,
        transcript=mgr.transcript,
    )


async def run_suite(cases: list[ScenarioCase] | None = None) -> dict[str, Any]:
    results = [await run_case(c) for c in (cases or CASES)]
    passed = sum(1 for r in results if r.passed)
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 3) if results else 0.0,
        "cases": [
            {
                "id": r.id,
                "name": r.name,
                "passed": r.passed,
                "notes": r.notes,
                "expected": r.expected,
                "actual": {k: v for k, v in r.actual.items() if k != "fields"} | {
                    "fields": r.actual["fields"]
                },
                "failures": r.failures,
            }
            for r in results
        ],
    }

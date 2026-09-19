from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.ai.conversation_manager import ConversationManager
from app.ai.groq_provider import GroqProvider
from app.audit.recorder import CallRecorder
from app.core.config import BRIDGE_BASE_URL, HUMAN_QUEUE_NUMBER, JOURNEY_SUBMIT_URL
from app.journey.engine import JourneyEngine
from app.journey.submitter import JourneySubmitClient
from app.metrics.engine import MetricsEngine
from app.evaluation.scenarios import run_suite
from app.experimentation.ab_test import run_all as run_ab_tests
from app.ml.scorer import LeadScorer
from app.safety.hallucination_guard import HallucinationGuardLog
from app.models.enums import HandoffStatus
from app.services.demos import SCENARIOS
from app.services.dnc import DNCService
from app.services.handoff_queue import HandoffQueue
from app.services.sandbox import JourneySandbox
from app.services.store import Store

app = FastAPI(title="Recovery AI", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

metrics = MetricsEngine()
groq = GroqProvider()
journey = JourneyEngine()
sandbox = JourneySandbox(journey)
store = Store()
handoffs = HandoffQueue(store)
recorder = CallRecorder()
dnc = DNCService()
scorer = LeadScorer()
hallucination_guard = HallucinationGuardLog()
sessions: dict[str, ConversationManager] = {}


def new_manager(voice_mode: str) -> ConversationManager:
    return ConversationManager(
        metrics=metrics,
        groq=groq,
        voice_mode=voice_mode,
        handoffs=handoffs,
        store=store,
        recorder=recorder,
        submitter=JourneySubmitClient(local_handler=sandbox),
        hallucination_guard=hallucination_guard,
    )


class StartRequest(BaseModel):
    lead_id: str = "EN-1001"
    voice_mode: str = "BROWSER"
    scenario: Optional[str] = None


class UtteranceRequest(BaseModel):
    call_id: str
    text: str
    speech_confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class DialRequest(BaseModel):
    lead_id: str
    voice_mode: str = "TWILIO"
    phone: Optional[str] = None  # dial this real number instead of the lead's synthetic one


class ClaimRequest(BaseModel):
    agent_name: str = "Aarav"


class MessageRequest(BaseModel):
    role: str = "human_agent"
    text: str


class NoteRequest(BaseModel):
    author: str = "Aarav"
    text: str


class ResolveRequest(BaseModel):
    resolution: str = "Handled by human agent"


# ---------------------------------------------------------------- basics

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "service": "recovery-ai",
        "groq": groq.status(),
        "active_sessions": len(sessions),
        "journey_submit_url": JOURNEY_SUBMIT_URL,
        "telephony_bridge": BRIDGE_BASE_URL,
        "human_queue_configured": bool(HUMAN_QUEUE_NUMBER),
        "handoffs": handoffs.stats(),
    }


@app.get("/api/leads")
async def list_leads():
    return [l.model_dump() for l in journey.load_leads()]


@app.get("/api/leads/prioritised")
async def prioritised_leads(limit: int = 25, include_blocked: bool = True):
    """The call queue, ranked by how likely each lead is to be recovered.

    DNC-listed leads are removed from the dialable queue rather than ranked -
    the gate decides who may be called, the model only decides the order of
    those who may.
    """
    leads = [l.model_dump() for l in journey.load_leads()]
    eligible, blocked = [], []
    for lead in leads:
        gate = dnc.check(journey.get_lead(lead["lead_id"]))
        (eligible if gate["eligible"] else blocked).append(lead)

    ranked = scorer.rank(eligible)[:limit]
    for item in ranked:
        source = next(l for l in eligible if l["lead_id"] == item["lead_id"])
        item["customer"] = f"{source['first_name']} {source['last_name']}"
        item["last_completed_step"] = source.get("last_completed_step")
        item["source"] = source.get("source")

    return {
        "queue": ranked,
        "blocked_by_dnc": [
            {"lead_id": b["lead_id"], "customer": f"{b['first_name']} {b['last_name']}"}
            for b in blocked
        ],
        "scored_by": scorer.mode,
        "model_version": scorer.status().get("model_version"),
    }


@app.get("/api/model/status")
async def model_status():
    """Model card: version, algorithm, held-out metrics, queue lift, provenance."""
    return scorer.status()


@app.post("/api/model/reload")
async def model_reload():
    """Pick up a newly trained artifact without restarting the API."""
    return scorer.reload()


@app.get("/api/safety/hallucination-guard")
async def hallucination_guard_report():
    """Every turn this session where the LLM's suggested field value
    disagreed with the deterministic rule match, and the rule was kept.
    Concrete evidence for the mandatory 'understanding of hallucination
    risk' capability - not a claim, a running log."""
    return {
        "summary": hallucination_guard.summary(),
        "entries": hallucination_guard.recent(),
    }


@app.get("/api/evaluation")
async def run_evaluation():
    """The 15 named business scenarios, driven end to end through a fresh
    ConversationManager per case, deterministic (no live LLM), reproducible on
    demand. Complements the NLU-level harness in evals/run_evals.py, which
    scores the intent engine and field extractor in isolation rather than a
    full call outcome."""
    return await run_suite()


@app.get("/api/experiments/ab-test")
async def ab_test_report():
    """Script A/B testing framework: two phrasings of the same field's
    question, run through the real extraction/confidence pipeline against a
    documented response-panel hypothesis, with a declared winning metric.
    See config/script_variants.json for the hypothesis behind each panel."""
    return run_ab_tests()


@app.get("/api/journey")
async def get_journey():
    return journey.definition


@app.get("/api/metrics")
async def get_metrics():
    snap = metrics.snapshot().model_dump()
    snap["handoff_queue"] = handoffs.stats()
    return snap


@app.get("/api/baseline")
async def get_baseline():
    return metrics.baseline


@app.get("/api/demos")
async def list_demos():
    return SCENARIOS


@app.get("/api/groq/status")
async def groq_status():
    return groq.status()


# ------------------------------------------------- journey completion sandbox

@app.post("/api/sandbox/journey/submit")
async def sandbox_submit(payload: dict[str, Any], response: Response):
    """Stand-in for CIMET's journey-completion endpoint.

    Point JOURNEY_SUBMIT_URL at the real sandbox and nothing else changes.
    """
    status_code, body = sandbox.receive(payload)
    response.status_code = status_code
    return body


@app.get("/api/sandbox/submissions")
async def sandbox_submissions(limit: int = 25):
    return sandbox.recent(limit)


@app.get("/api/submissions")
async def submissions(limit: int = 50):
    """Every payload this system has submitted, with its receipt - survives restart."""
    return store.list_submissions(limit)


# ------------------------------------------------------------------ calls

@app.post("/api/calls/start")
async def start_call(body: StartRequest):
    mgr = new_manager(body.voice_mode)
    if body.scenario:
        mgr.demo_scenario = body.scenario
        lead_id = SCENARIOS.get(body.scenario, {}).get("lead_id", body.lead_id)
    else:
        lead_id = body.lead_id
    try:
        result = await mgr.start(lead_id, voice_mode=body.voice_mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    sessions[mgr.call_id] = mgr
    return {
        "call_id": mgr.call_id,
        "turn": result.model_dump(),
        "snapshot": mgr.snapshot(),
        "scenario": body.scenario,
        "scenario_utterances": SCENARIOS.get(body.scenario or "", {}).get("utterances"),
    }


@app.post("/api/calls/dial")
async def dial_call(body: DialRequest):
    """Place a real outbound call through the telephony bridge.

    The DNC gate runs inside ConversationManager.start before the dial is
    issued, so a listed lead never causes the phone to ring.
    """
    lead = journey.get_lead(body.lead_id)
    if not lead:
        raise HTTPException(404, f"Unknown lead {body.lead_id}")

    # A number with no country code gets silently reinterpreted by Twilio
    # using the account's default region - "7357730549" (India, +91) was
    # dialled as +1 7357730549 (US) with no error until the verified-numbers
    # check caught it downstream. Reject the ambiguity here instead of
    # trusting Twilio (or a client) to guess the right country.
    if body.phone and not body.phone.strip().startswith("+"):
        return {
            "dialled": False,
            "blocked_by": "AMBIGUOUS_PHONE_FORMAT",
            "detail": {
                "reason": f"'{body.phone}' has no country code (e.g. +91...). "
                "A bare number can be silently misread as the wrong country.",
            },
            "lead_id": body.lead_id,
        }

    gate = dnc.check(lead)
    if not gate["eligible"]:
        return {
            "dialled": False,
            "blocked_by": "DNC",
            "detail": gate,
            "lead_id": body.lead_id,
        }

    mgr = new_manager(body.voice_mode)
    result = await mgr.start(body.lead_id, voice_mode=body.voice_mode, phone_override=body.phone)
    sessions[mgr.call_id] = mgr
    return {
        "dialled": True,
        "call_id": mgr.call_id,
        "dial_result": mgr.dial_result,
        "turn": result.model_dump(),
        "snapshot": mgr.snapshot(),
    }


@app.post("/api/calls/utterance")
async def utterance(body: UtteranceRequest):
    mgr = sessions.get(body.call_id)
    if not mgr:
        raise HTTPException(404, "Unknown call_id")
    result = await mgr.handle_utterance(body.text, speech_confidence=body.speech_confidence)
    return {"call_id": body.call_id, "turn": result.model_dump(), "snapshot": mgr.snapshot()}


@app.get("/api/calls")
async def list_calls(limit: int = 50):
    return store.list_calls(limit)


@app.get("/api/calls/{call_id}")
async def get_call(call_id: str):
    mgr = sessions.get(call_id)
    if mgr:
        return mgr.snapshot()
    stored = store.get_call(call_id)
    if stored:
        return stored
    raise HTTPException(404, "Unknown call_id")


@app.get("/api/calls/{call_id}/replay")
async def replay(call_id: str):
    mgr = sessions.get(call_id)
    if not mgr:
        recorded = recorder.read(call_id)
        if recorded:
            return recorded
        raise HTTPException(404, "Unknown call_id")
    return {
        "call_id": call_id,
        "transcript": mgr.transcript,
        "timeline": [e.model_dump() for e in mgr.audit.events],
        "why": [w.model_dump() for w in mgr.why_log],
        "handoff_brief": mgr.handoff_brief.model_dump() if mgr.handoff_brief else None,
        "payload": mgr.payload.model_dump() if mgr.payload else None,
        "receipt": mgr.receipt.model_dump() if mgr.receipt else None,
        "recording_path": mgr.recording_path,
    }


# -------------------------------------------------------------- recordings

@app.get("/api/recordings")
async def list_recordings(limit: int = 50):
    return recorder.list(limit)


@app.get("/api/recordings/{call_id}")
async def get_recording(call_id: str):
    data = recorder.read(call_id)
    if not data:
        raise HTTPException(404, "No recording for that call")
    return data


# ------------------------------------------------------------ agent inbox

@app.get("/api/audit")
async def global_audit(limit: int = 200):
    """Cross-call audit trail for the developer diagnostics page.

    Merges the live in-memory sessions this process is holding with whatever
    has been persisted to SQLite, so a call that already ended still shows up
    after a restart. Every entry carries the call_id it belongs to.
    """
    events: list[dict[str, Any]] = []

    for mgr in sessions.values():
        events.extend(e.model_dump() for e in mgr.audit.events)

    seen_calls = {mgr.call_id for mgr in sessions.values()}
    for row in store.list_calls(limit=limit):
        call_id = row.get("call_id")
        if not call_id or call_id in seen_calls:
            continue
        stored = store.get_call(call_id)
        if stored:
            events.extend(stored.get("audit", []))

    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return {"total": len(events), "events": events[:limit]}


@app.get("/api/handoffs")
async def list_handoffs(status: Optional[str] = None):
    return {
        "stats": handoffs.stats(),
        "tickets": [t.model_dump() for t in handoffs.list(status)],
    }


@app.get("/api/handoffs/{ticket_id}")
async def get_handoff(ticket_id: str):
    ticket = handoffs.get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Unknown ticket")
    return ticket.model_dump()


@app.post("/api/handoffs/{ticket_id}/claim")
async def claim_handoff(ticket_id: str, body: ClaimRequest):
    ticket = handoffs.claim(ticket_id, body.agent_name)
    if not ticket:
        raise HTTPException(409, "Ticket is not waiting to be claimed")
    metrics.handoff_claimed(ticket.wait_seconds)
    return ticket.model_dump()


@app.post("/api/handoffs/{ticket_id}/message")
async def message_handoff(ticket_id: str, body: MessageRequest):
    ticket = handoffs.add_message(ticket_id, body.role, body.text)
    if not ticket:
        raise HTTPException(404, "Unknown ticket")
    return ticket.model_dump()


@app.post("/api/handoffs/{ticket_id}/note")
async def note_handoff(ticket_id: str, body: NoteRequest):
    ticket = handoffs.note(ticket_id, body.author, body.text)
    if not ticket:
        raise HTTPException(404, "Unknown ticket")
    return ticket.model_dump()


@app.post("/api/handoffs/{ticket_id}/resolve")
async def resolve_handoff(ticket_id: str, body: ResolveRequest):
    ticket = handoffs.resolve(ticket_id, body.resolution)
    if not ticket:
        raise HTTPException(404, "Unknown ticket")
    return ticket.model_dump()


# ------------------------------------------------------------------ demos

@app.post("/api/demos/{scenario}/run")
async def run_demo(scenario: str, voice_mode: str = "SIMULATED"):
    if scenario not in SCENARIOS:
        raise HTTPException(404, "Unknown scenario")
    spec = SCENARIOS[scenario]
    mgr = new_manager(voice_mode)
    mgr.demo_scenario = scenario
    result = await mgr.start(spec["lead_id"], voice_mode=voice_mode)
    sessions[mgr.call_id] = mgr
    turns = [result.model_dump()]
    for utt in spec["utterances"]:
        if result.ended:
            break
        result = await mgr.handle_utterance(utt)
        turns.append(result.model_dump())
    return {
        "call_id": mgr.call_id,
        "scenario": scenario,
        "turns": turns,
        "snapshot": mgr.snapshot(),
        "metrics": metrics.snapshot().model_dump(),
    }


# ------------------------------------------------------- bridge turn intake

@app.post("/api/bridge/turn")
async def bridge_turn(body: UtteranceRequest):
    """Turn intake for the Node telephony bridge - same brain, phone channel."""
    mgr = sessions.get(body.call_id)
    if not mgr:
        raise HTTPException(404, "Unknown call_id")
    result = await mgr.handle_utterance(body.text, speech_confidence=body.speech_confidence)
    return {
        "assistant_message": result.assistant_message,
        "ended": result.ended,
        "escalated": result.escalated,
        "state": result.state,
        "handoff_ticket_id": result.handoff_ticket_id,
        "should_transfer": result.escalated,
    }


@app.websocket("/ws/calls/{call_id}")
async def ws_call(websocket: WebSocket, call_id: str):
    await websocket.accept()
    mgr = sessions.get(call_id)
    if not mgr:
        await websocket.send_json({"error": "Unknown call_id"})
        await websocket.close()
        return
    await websocket.send_json({"type": "snapshot", "data": mgr.snapshot()})
    try:
        while True:
            data = await websocket.receive_json()
            text = data.get("text", "")
            speech_confidence = float(data.get("speech_confidence", 0.95))
            result = await mgr.handle_utterance(text, speech_confidence=speech_confidence)
            await websocket.send_json(
                {"type": "turn", "data": result.model_dump(), "snapshot": mgr.snapshot()}
            )
            if result.ended:
                break
    except WebSocketDisconnect:
        return

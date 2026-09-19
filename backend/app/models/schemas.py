from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Lead(BaseModel):
    lead_id: str
    first_name: str
    last_name: str
    phone: str
    email: str
    journey: str = "energy"
    last_completed_step: Optional[str] = None
    dnc_listed: bool = False
    known_fields: dict[str, Any] = Field(default_factory=dict)
    scenario_hint: Optional[str] = None
    dropped_at: Optional[str] = None
    source: str = "econnex"
    prior_attempts: int = 0


class FieldCapture(BaseModel):
    field: str
    value: Any
    confidence: float
    status: str = "CONFIRMED"
    source: str = "customer"


class ConfidenceSnapshot(BaseModel):
    speech_confidence: float = 1.0
    intent_confidence: float = 1.0
    field_confidence: float = 1.0
    journey_confidence: float = 1.0

    @property
    def overall(self) -> float:
        return round(
            (
                self.speech_confidence
                + self.intent_confidence
                + self.field_confidence
                + self.journey_confidence
            )
            / 4,
            3,
        )


class AuditEvent(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    event: str
    call_id: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class WhyAction(BaseModel):
    timestamp: str = Field(default_factory=utc_now)
    action: str
    reason: str
    category: str = "general"


class HandoffBrief(BaseModel):
    customer: str
    journey: str
    current_stage: str
    reason: str
    confidence: float
    customer_mood: str
    fields_collected: list[str]
    last_customer_statement: str
    recommended_opening: str
    conversation_summary: str
    next_action: str
    signals: list[str] = Field(default_factory=list)


class JourneyPayload(BaseModel):
    lead_id: str
    journey: str = "energy"
    status: str
    fields: dict[str, Any]
    metadata: dict[str, Any]


class SubmissionReceipt(BaseModel):
    """Proof the journey payload reached the completion sandbox."""

    accepted: bool
    reference: Optional[str] = None
    endpoint: str = ""
    transport: str = "http"
    status_code: Optional[int] = None
    attempts: int = 0
    latency_ms: Optional[int] = None
    received_at: Optional[str] = None
    error: Optional[str] = None
    response: dict[str, Any] = Field(default_factory=dict)


class HandoffTicket(BaseModel):
    """A warm handoff waiting in the human agent queue."""

    ticket_id: str
    call_id: str
    lead_id: str
    customer: str
    phone: str
    status: str = "WAITING"
    reason: str = ""
    signals: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    claimed_at: Optional[str] = None
    claimed_by: Optional[str] = None
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None
    wait_seconds: float = 0.0
    voice_mode: str = "BROWSER"
    transfer: dict[str, Any] = Field(default_factory=dict)
    brief: Optional[HandoffBrief] = None
    fields: dict[str, Any] = Field(default_factory=dict)
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)


class ManualComparison(BaseModel):
    """AI run measured against the documented manual baseline."""

    baseline_source: str = ""
    manual_handle_time_sec: float = 0.0
    ai_handle_time_sec: float = 0.0
    handle_time_saved_sec: float = 0.0
    handle_time_reduction: float = 0.0
    manual_fields_typed: int = 0
    ai_fields_typed: int = 0
    fields_typed_saved: int = 0
    typing_effort_reduction: float = 0.0
    manual_script_lookups: int = 0
    ai_script_lookups: int = 0
    manual_journeys_per_agent_hour: float = 0.0
    ai_journeys_per_agent_hour: float = 0.0
    throughput_multiple: float = 0.0
    calls_measured: int = 0
    note: str = ""


class MetricsSnapshot(BaseModel):
    journeys_started: int = 0
    journeys_completed: int = 0
    journeys_abandoned: int = 0
    successful_recoveries: int = 0
    human_handoffs: int = 0
    customer_declines: int = 0
    clarifications: int = 0
    interruptions: int = 0
    low_confidence_events: int = 0
    average_turns: float = 0.0
    average_completion_time_sec: float = 0.0
    fields_captured: int = 0
    manual_fields_required: int = 0
    automation_rate: float = 0.0
    manual_effort_reduction: float = 0.0
    submissions_accepted: int = 0
    submissions_rejected: int = 0
    handoffs_claimed: int = 0
    average_handoff_wait_sec: float = 0.0
    vs_manual: ManualComparison = Field(default_factory=ManualComparison)


class TurnResult(BaseModel):
    assistant_message: str
    state: str
    intent: str
    event: Optional[str] = None
    field: Optional[str] = None
    value: Any = None
    confidence: ConfidenceSnapshot = Field(default_factory=ConfidenceSnapshot)
    why: Optional[WhyAction] = None
    escalated: bool = False
    handoff_brief: Optional[HandoffBrief] = None
    payload: Optional[JourneyPayload] = None
    receipt: Optional[SubmissionReceipt] = None
    handoff_ticket_id: Optional[str] = None
    ended: bool = False
    speak: bool = True
    radar: dict[str, Any] = Field(default_factory=dict)
    journey_progress: list[dict[str, Any]] = Field(default_factory=list)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    audit_tail: list[AuditEvent] = Field(default_factory=list)

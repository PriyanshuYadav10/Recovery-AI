from __future__ import annotations

from typing import Optional
from app.models.enums import CallState


ALLOWED_TRANSITIONS: dict[CallState, set[CallState]] = {
    CallState.INITIALIZING: {CallState.DNC_CHECK, CallState.ENDED},
    CallState.DNC_CHECK: {CallState.DISCLOSURE, CallState.ENDED},
    CallState.DISCLOSURE: {CallState.CONSENT},
    CallState.CONSENT: {CallState.WELCOME, CallState.DECLINED},
    CallState.WELCOME: {CallState.RECOVER_CONTEXT, CallState.COLLECTING},
    CallState.RECOVER_CONTEXT: {CallState.COLLECTING},
    CallState.COLLECTING: {
        CallState.COLLECTING,
        CallState.CLARIFYING,
        CallState.CONFIRMING,
        CallState.ESCALATING,
        CallState.DECLINED,
        CallState.ENDED,
    },
    CallState.CLARIFYING: {
        CallState.COLLECTING,
        CallState.CLARIFYING,
        CallState.ESCALATING,
        CallState.DECLINED,
    },
    CallState.CONFIRMING: {
        CallState.SUBMITTING,
        CallState.COLLECTING,
        CallState.ESCALATING,
        CallState.DECLINED,
    },
    CallState.SUBMITTING: {CallState.COMPLETED, CallState.ESCALATING},
    CallState.COMPLETED: {CallState.ENDED},
    CallState.ESCALATING: {CallState.HANDOFF},
    CallState.HANDOFF: {CallState.ENDED},
    CallState.DECLINED: {CallState.ENDED},
    CallState.ENDED: set(),
}


class StateMachine:
    def __init__(self, initial: CallState = CallState.INITIALIZING):
        self.state = initial
        self.history: list[dict] = [{"from": None, "to": initial.value, "reason": "init"}]

    def transition(self, to: CallState, reason: str = "") -> CallState:
        if to == self.state:
            return self.state
        allowed = ALLOWED_TRANSITIONS.get(self.state, set())
        if to not in allowed and to not in {
            CallState.ESCALATING,
            CallState.DECLINED,
            CallState.ENDED,
        }:
            # Force-allow safety exits and escalation from anywhere collecting-related
            if to not in {CallState.ESCALATING, CallState.DECLINED, CallState.ENDED, CallState.HANDOFF}:
                raise ValueError(f"Illegal transition {self.state} -> {to}")
        prev = self.state
        self.state = to
        self.history.append({"from": prev.value, "to": to.value, "reason": reason})
        return self.state

    def can(self, to: CallState) -> bool:
        return to in ALLOWED_TRANSITIONS.get(self.state, set()) or to in {
            CallState.ESCALATING,
            CallState.DECLINED,
            CallState.ENDED,
        }

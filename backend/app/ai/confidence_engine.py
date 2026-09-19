from __future__ import annotations

from app.core.config import (
    FIELD_CONFIDENCE_THRESHOLD,
    INTENT_CONFIDENCE_THRESHOLD,
    SPEECH_CONFIDENCE_THRESHOLD,
)
from app.models.schemas import ConfidenceSnapshot


class ConfidenceEngine:
    def evaluate(
        self,
        *,
        speech: float = 1.0,
        intent: float = 1.0,
        field: float = 1.0,
        journey: float = 1.0,
    ) -> tuple[ConfidenceSnapshot, bool, str]:
        snap = ConfidenceSnapshot(
            speech_confidence=speech,
            intent_confidence=intent,
            field_confidence=field,
            journey_confidence=journey,
        )
        if speech < SPEECH_CONFIDENCE_THRESHOLD:
            return snap, True, f"Speech confidence was {int(speech*100)}%"
        if intent < INTENT_CONFIDENCE_THRESHOLD:
            return snap, True, f"Intent confidence was {int(intent*100)}%"
        if field < FIELD_CONFIDENCE_THRESHOLD:
            return snap, True, f"Field confidence was {int(field*100)}%"
        return snap, False, "Confidence acceptable"

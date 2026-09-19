from __future__ import annotations

from dataclasses import dataclass, field
from app.models.enums import EscalationSignal, Mood


WEIGHTS = {
    EscalationSignal.ANGER: 35,
    EscalationSignal.CONFUSION: 25,
    EscalationSignal.OFF_SCRIPT: 30,
    EscalationSignal.SENSITIVE: 100,
    EscalationSignal.HUMAN_REQUEST: 100,
    EscalationSignal.LOW_CONFIDENCE: 30,
}

CRITICAL = {
    EscalationSignal.SENSITIVE,
    EscalationSignal.HUMAN_REQUEST,
}


@dataclass
class EscalationDecision:
    should_escalate: bool
    score: int
    signals: list[str] = field(default_factory=list)
    reason: str = ""
    immediate: bool = False
    mood: Mood = Mood.NEUTRAL


class EscalationEngine:
    def __init__(self, threshold: int = 60):
        self.threshold = threshold
        self.score = 0
        self.signals: list[EscalationSignal] = []
        self.confusion_streak = 0
        self.anger_hits = 0

    def reset(self) -> None:
        self.score = 0
        self.signals = []
        self.confusion_streak = 0
        self.anger_hits = 0

    def register(self, signal: EscalationSignal, note: str = "") -> EscalationDecision:
        weight = WEIGHTS.get(signal, 20)
        self.score += weight
        self.signals.append(signal)

        if signal == EscalationSignal.CONFUSION:
            self.confusion_streak += 1
        else:
            # confusion streak only counts consecutive failures
            pass

        if signal == EscalationSignal.ANGER:
            self.anger_hits += 1

        immediate = signal in CRITICAL or self.confusion_streak >= 3 or self.anger_hits >= 2
        should = immediate or self.score >= self.threshold

        mood = Mood.NEUTRAL
        if should:
            mood = Mood.ESCALATION
        elif self.anger_hits or EscalationSignal.ANGER in self.signals:
            mood = Mood.FRUSTRATED
        elif self.score >= 30:
            mood = Mood.FRUSTRATED
        elif self.score == 0:
            mood = Mood.CALM

        reason = note or f"{signal.value} (+{weight})"
        if immediate and signal in CRITICAL:
            reason = f"Critical signal: {signal.value}"
        elif self.confusion_streak >= 3:
            reason = "Repeated confusion on the same field"
            should = True
            immediate = True

        return EscalationDecision(
            should_escalate=should,
            score=self.score,
            signals=[s.value for s in self.signals],
            reason=reason,
            immediate=immediate,
            mood=mood,
        )

    def note_success(self) -> None:
        self.confusion_streak = 0

    def risk_label(self) -> str:
        if self.score >= self.threshold or any(s in CRITICAL for s in self.signals):
            return "High"
        if self.score >= 30:
            return "Medium"
        return "Low"

    def mood(self) -> Mood:
        if any(s in CRITICAL for s in self.signals) or self.score >= self.threshold:
            return Mood.ESCALATION
        if self.anger_hits or self.score >= 30:
            return Mood.FRUSTRATED
        if self.score == 0:
            return Mood.CALM
        return Mood.NEUTRAL

from __future__ import annotations

import re
from dataclasses import dataclass
from app.models.enums import EscalationSignal


PAYMENT_PATTERNS = [
    r"\bcard\b",
    r"\bcredit\s*card\b",
    r"\bdebit\b",
    r"\bcvv\b",
    r"\bexpiry\b",
    r"\bvisa\b",
    r"\bmastercard\b",
    r"\bamex\b",
    r"\bpayment\b",
    r"\bbank\s*account\b",
    r"\bbank\s*details?\b",
    r"\bbanking\s*details?\b",
    r"\bbsb\b",
    r"\baccount\s*(number|details?)\b",
    r"\bdirect\s*debit\b",
    r"\bpay\b.*\b(card|now|online)\b",
    r"\bsort\s*code\b",
    r"\bpan\b",
]

DECLINE_PATTERNS = [
    r"\bnot interested\b",
    r"\bdon'?t call\b",
    r"\bdo not call\b",
    r"\bstop calling\b",
    r"\bleave me alone\b",
    r"\bno thanks\b",
    r"\bremove me\b",
    r"\btake me off\b",
    r"\bunsubscribe\b",
    r"\bstop\b.*\bcall",
    r"\bnot keen\b",
    r"\bno longer interested\b",
    # Real call evidence: customers decline without ever saying "not interested" -
    # they say they'll stay put or that it isn't worth the hassle.
    r"\bstay where i am\b",
    r"\b(could not|couldn'?t|can'?t) be bothered\b",
    r"\bnot worth (it|the hassle|switching)\b",
    r"\b(i'?ll|i will) pass\b",
    r"\brather not\b",
]

HUMAN_PATTERNS = [
    r"\bhuman\b",
    r"\breal person\b",
    r"\bagent\b",
    r"\boperator\b",
    r"\bspeak to someone\b",
    r"\btalk to someone\b",
    r"\bgive me a person\b",
    r"\btransfer me\b",
    r"\blive agent\b",
    r"\brepresentative\b",
]

ANGER_PATTERNS = [
    r"\bf+u+c+k+\b",
    r"\bshit\b",
    r"\bdamn\b",
    r"\bstupid\b",
    r"\bridiculous\b",
    r"\bwaste of (my )?time\b",
    r"\bi'?ve already told\b",
    r"\bi already (told|explained)\b",
    r"\bthis is the second call\b",
    r"\bi'?m done\b",
    r"\bso frustrating\b",
    r"\bangry\b",
    r"\bsick of\b",
    r"\bfed up\b",
    r"\btired of\b",
    r"\bhow many times\b",
    r"\bagain\?\b",
]

ADVICE_PATTERNS = [
    r"\bwhich (plan|one|provider) (is|should|do)\b",
    r"\brecommend\b",
    r"\bbest (deal|plan|provider)\b",
    r"\bshould i (switch|choose|get)\b",
    r"\bfinancial advice\b",
    r"\bwhat do you think\b",
    r"\bis (this|that) a good\b",
    r"\bworth (it|switching)\b",
    r"\bwhat would you do\b",
    r"\bcheaper\b.*\?",
]

BUSY_PATTERNS = [
    r"\bi'?m busy\b",
    r"\bat work\b",
    r"\bin a meeting\b",
    r"\bdriving\b",
    r"\bcan'?t talk (long|right now)\b",
    r"\bcall (me )?(back )?later\b",
    r"\bcall me back\b",
    r"\bbad time\b",
    r"\bnot a good time\b",
    r"\banother time\b",
    r"\bon my way\b",
]

CONSENT_YES = [
    r"\byes\b",
    r"\byeah\b",
    r"\byep\b",
    r"\bsure\b",
    r"\bok(ay)?\b",
    r"\bfine\b",
    r"\ball right\b",
    r"\bgo ahead\b",
    r"\bthat'?s fine\b",
    r"\bof course\b",
]

CONSENT_NO = [
    r"\bno\b",
    r"\bnope\b",
    r"\bnot okay\b",
    r"\bnot ok\b",
    r"\bi don'?t (consent|agree)\b",
    r"\bdon'?t record\b",
]


@dataclass
class GuardrailResult:
    blocked: bool = False
    action: str = "continue"  # continue | end | escalate | clarify
    signal: EscalationSignal | None = None
    reason: str = ""
    rule: str = ""


class GuardrailEngine:
    """Deterministic safety rules - not LLM-controlled."""

    def evaluate(
        self,
        text: str,
        *,
        consent_granted: bool,
        collecting: bool,
    ) -> GuardrailResult:
        t = (text or "").strip().lower()
        if not t:
            return GuardrailResult(action="clarify", reason="Empty utterance", rule="EMPTY")

        if self._match(t, PAYMENT_PATTERNS):
            return GuardrailResult(
                blocked=True,
                action="escalate",
                signal=EscalationSignal.SENSITIVE,
                reason="Payment/card data mentioned - AI must not collect it",
                rule="NO_PAYMENT",
            )

        if self._match(t, DECLINE_PATTERNS):
            return GuardrailResult(
                blocked=True,
                action="end",
                reason="Customer declined / asked to stop",
                rule="RESPECT_NO",
            )

        if self._match(t, HUMAN_PATTERNS):
            return GuardrailResult(
                blocked=True,
                action="escalate",
                signal=EscalationSignal.HUMAN_REQUEST,
                reason="Customer explicitly requested a human",
                rule="HUMAN_REQUEST",
            )

        if self._match(t, ANGER_PATTERNS):
            return GuardrailResult(
                action="escalate",
                signal=EscalationSignal.ANGER,
                reason="Anger/frustration language detected",
                rule="ANGER",
            )

        if self._match(t, ADVICE_PATTERNS):
            return GuardrailResult(
                action="escalate",
                signal=EscalationSignal.OFF_SCRIPT,
                reason="Customer requested product/financial advice",
                rule="NO_ADVICE",
            )

        if collecting and not consent_granted:
            return GuardrailResult(
                blocked=True,
                action="end",
                reason="Attempted collection without consent",
                rule="CONSENT_FIRST",
            )

        return GuardrailResult()

    def check_consent_response(self, text: str) -> str | None:
        t = (text or "").lower()
        if self._match(t, CONSENT_YES) and not self._match(t, CONSENT_NO):
            return "yes"
        if self._match(t, CONSENT_NO):
            return "no"
        return None

    def is_busy(self, text: str) -> bool:
        return self._match((text or "").lower(), BUSY_PATTERNS)

    @staticmethod
    def _match(text: str, patterns: list[str]) -> bool:
        return any(re.search(p, text, re.I) for p in patterns)

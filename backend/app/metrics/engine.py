from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from app.core.config import BASELINE_PATH
from app.models.schemas import ManualComparison, MetricsSnapshot


# A simulated run finishes in milliseconds, which would make any time saving
# look absurd. Below this, handle time is estimated from the transcript instead
# of measured, and the comparison says which basis it used.
MIN_REAL_CALL_SECONDS = 20.0
WORDS_PER_MINUTE = 165.0
PER_TURN_LATENCY_SEC = 1.2


class MetricsEngine:
    def __init__(self, baseline_path: Optional[Path] = None):
        self.snap = MetricsSnapshot()
        self._turn_total = 0
        self._call_count = 0
        self._completion_times: list[float] = []
        self._handle_times: list[float] = []
        self._handle_basis: list[str] = []
        self._active_starts: dict[str, float] = {}
        self._fields_auto_total = 0
        self._fields_required_total = 0
        self.baseline = self._load_baseline(baseline_path or BASELINE_PATH)
        self._recompute_comparison()

    @staticmethod
    def _load_baseline(path: Path) -> dict[str, Any]:
        try:
            return json.loads(Path(path).read_text())
        except Exception:
            return {"source": "baseline file unavailable", "manual": {}}

    # ---- lifecycle -------------------------------------------------------

    def start_journey(self, call_id: str) -> None:
        self.snap.journeys_started += 1
        self._active_starts[call_id] = time.time()

    def complete(
        self,
        call_id: str,
        fields_auto: int,
        fields_total: int,
        *,
        transcript_words: int = 0,
        turns: int = 0,
    ) -> None:
        self.snap.journeys_completed += 1
        self.snap.successful_recoveries += 1
        self.snap.fields_captured += fields_auto
        self._update_automation(fields_auto, fields_total)
        elapsed = self._finish_timing(call_id)
        self._record_handle_time(elapsed, transcript_words, turns)
        self._recompute_comparison()

    def abandon(self, call_id: str) -> None:
        self.snap.journeys_abandoned += 1
        self._finish_timing(call_id)
        self._recompute_comparison()

    def decline(self) -> None:
        self.snap.customer_declines += 1

    def handoff(self) -> None:
        self.snap.human_handoffs += 1

    def handoff_claimed(self, wait_seconds: float) -> None:
        self.snap.handoffs_claimed += 1
        total = self.snap.average_handoff_wait_sec * (self.snap.handoffs_claimed - 1) + wait_seconds
        self.snap.average_handoff_wait_sec = round(total / self.snap.handoffs_claimed, 2)

    def submission_accepted(self) -> None:
        self.snap.submissions_accepted += 1

    def submission_rejected(self) -> None:
        self.snap.submissions_rejected += 1

    def clarification(self) -> None:
        self.snap.clarifications += 1

    def interruption(self) -> None:
        self.snap.interruptions += 1

    def low_confidence(self) -> None:
        self.snap.low_confidence_events += 1

    def add_turns(self, n: int = 1) -> None:
        self._turn_total += n
        self._call_count = max(self._call_count, self.snap.journeys_started)
        if self.snap.journeys_started:
            self.snap.average_turns = round(self._turn_total / self.snap.journeys_started, 2)

    # ---- derived ---------------------------------------------------------

    def _update_automation(self, auto: int, total: int) -> None:
        if total <= 0:
            return
        # Cumulative, not an average of averages - order of calls must not matter.
        self._fields_auto_total += auto
        self._fields_required_total += total
        self.snap.automation_rate = round(self._fields_auto_total / self._fields_required_total, 3)
        self.snap.manual_fields_required = max(0, total - auto)

    def _finish_timing(self, call_id: str) -> float:
        start = self._active_starts.pop(call_id, None)
        if start is None:
            return 0.0
        elapsed = time.time() - start
        self._completion_times.append(elapsed)
        self.snap.average_completion_time_sec = round(
            sum(self._completion_times) / len(self._completion_times), 2
        )
        return elapsed

    def _record_handle_time(self, elapsed: float, transcript_words: int, turns: int) -> None:
        if elapsed >= MIN_REAL_CALL_SECONDS:
            self._handle_times.append(elapsed)
            self._handle_basis.append("measured")
            return
        estimated = (transcript_words / WORDS_PER_MINUTE) * 60.0 + turns * PER_TURN_LATENCY_SEC
        self._handle_times.append(max(estimated, 1.0))
        self._handle_basis.append("estimated_from_transcript")

    def _recompute_comparison(self) -> None:
        manual = self.baseline.get("manual", {})
        manual_aht = float(manual.get("average_handle_time_sec", 0) or 0)
        manual_wrap = float(manual.get("wrap_up_time_sec", 0) or 0)
        manual_fields = int(manual.get("fields_typed_per_call", 0) or 0)
        manual_lookups = int(manual.get("script_lookups_per_call", 0) or 0)
        manual_throughput = float(manual.get("journeys_completed_per_agent_hour", 0) or 0)

        ai_aht = round(sum(self._handle_times) / len(self._handle_times), 2) if self._handle_times else 0.0
        basis = "measured" if "measured" in self._handle_basis else (
            "estimated_from_transcript" if self._handle_basis else "no completed calls yet"
        )

        # An autonomous call needs no agent minutes at all, so throughput is
        # bounded by the call itself, not by the agent's wrap-up.
        ai_throughput = round(3600 / ai_aht, 2) if ai_aht else 0.0

        note = (
            f"AI handle time basis: {basis}"
            + (
                f" (transcript at {int(WORDS_PER_MINUTE)} wpm + {PER_TURN_LATENCY_SEC}s per turn)"
                if basis == "estimated_from_transcript"
                else ""
            )
            + ". Manual baseline: "
            + str(self.baseline.get("source", "unknown"))
        )

        self.snap.vs_manual = ManualComparison(
            baseline_source=str(self.baseline.get("source", "")),
            manual_handle_time_sec=manual_aht + manual_wrap,
            ai_handle_time_sec=ai_aht,
            handle_time_saved_sec=round(manual_aht + manual_wrap - ai_aht, 2) if ai_aht else 0.0,
            handle_time_reduction=round((manual_aht + manual_wrap - ai_aht) / (manual_aht + manual_wrap), 3)
            if (manual_aht + manual_wrap) and ai_aht
            else 0.0,
            manual_fields_typed=manual_fields,
            ai_fields_typed=0,
            fields_typed_saved=manual_fields,
            typing_effort_reduction=1.0 if manual_fields else 0.0,
            manual_script_lookups=manual_lookups,
            ai_script_lookups=0,
            manual_journeys_per_agent_hour=manual_throughput,
            ai_journeys_per_agent_hour=ai_throughput,
            throughput_multiple=round(ai_throughput / manual_throughput, 2)
            if manual_throughput and ai_throughput
            else 0.0,
            calls_measured=len(self._handle_times),
            note=note,
        )
        # Manual effort reduction is now measured against the baseline rather
        # than restated from the automation rate.
        self.snap.manual_effort_reduction = self.snap.vs_manual.handle_time_reduction

    def snapshot(self) -> MetricsSnapshot:
        return self.snap.model_copy(deep=True)

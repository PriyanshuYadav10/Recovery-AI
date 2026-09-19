from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

# The feature contract. Training and serving both import this list, so a model
# can never be scored with columns in a different order than it was fitted on.
NUMERIC_FEATURES = [
    "progress_ratio",
    "fields_completed",
    "hours_since_drop",
    "prior_attempts",
    "dropped_hour",
    "dropped_is_weekend",
]
CATEGORICAL_FEATURES = ["source"]
FEATURE_ORDER = NUMERIC_FEATURES + CATEGORICAL_FEATURES

TARGET = "recovered"

SOURCES = ["econnex", "campaign", "affiliate"]

# Human-readable reasons, used to explain a score back to the ops team.
FEATURE_LABELS = {
    "progress_ratio": "how far through the journey they got",
    "fields_completed": "fields already captured",
    "hours_since_drop": "hours since they dropped out",
    "prior_attempts": "previous call attempts",
    "dropped_hour": "time of day they dropped",
    "dropped_is_weekend": "dropped on a weekend",
    "source": "acquisition source",
}


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build_features(
    lead: dict[str, Any],
    *,
    total_fields: int = 8,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Turn one lead record into the feature row the model expects.

    Everything here is knowable before the call is placed - no leakage from the
    outcome of the call we are trying to predict.
    """
    now = now or datetime.now(timezone.utc)
    known = lead.get("known_fields") or {}
    completed = len(known)
    dropped = _parse_ts(lead.get("dropped_at"))

    if dropped:
        hours = max(0.0, (now - dropped).total_seconds() / 3600.0)
        hour_of_day = dropped.hour
        is_weekend = 1 if dropped.weekday() >= 5 else 0
    else:
        hours, hour_of_day, is_weekend = 48.0, 12, 0

    source = str(lead.get("source") or "econnex").lower()
    if source not in SOURCES:
        source = "econnex"

    return {
        "progress_ratio": round(completed / total_fields, 4) if total_fields else 0.0,
        "fields_completed": completed,
        "hours_since_drop": round(hours, 2),
        "prior_attempts": int(lead.get("prior_attempts") or 0),
        "dropped_hour": hour_of_day,
        "dropped_is_weekend": is_weekend,
        "source": source,
    }

from __future__ import annotations

"""Synthetic historical leads for the recovery-propensity model.

There is no real CIMET outcome data, and the handout forbids real customer PII,
so training data is generated from an explicit, seeded process documented below.

The generating process encodes assumptions any agent-team lead would recognise:

  * the further into the journey someone got, the more likely they are to finish
  * propensity decays with time since the drop-off
  * each previous failed attempt lowers the odds and annoys the customer
  * traffic from our own site converts better than campaign, which beats affiliate
  * calls land better inside business hours, worse late at night

Because the structure is known, the evaluation in train.py measures whether the
model recovers a signal that was deliberately put there. That is a real check of
the pipeline - it is NOT evidence of real-world accuracy. Retrain on genuine
outcome data before believing any number here.
"""

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.ml.features import SOURCES

SOURCE_WEIGHTS = {"econnex": 0.55, "campaign": 0.30, "affiliate": 0.15}
SOURCE_EFFECT = {"econnex": 0.45, "campaign": 0.0, "affiliate": -0.40}

FIRST_NAMES = ["Priya", "Marcus", "Aisha", "Jordan", "Nikhil", "Chloe", "Sam", "Ruby",
               "Diego", "Mei", "Omar", "Hannah", "Tom", "Anika", "Leo", "Zara"]
LAST_NAMES = ["Sharma", "Chen", "Khan", "Lee", "Patel", "Nguyen", "Brown", "Singh",
              "Garcia", "Wong", "Ali", "Taylor", "Walker", "Rao", "Murphy", "Costa"]


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def recovery_probability(
    progress_ratio: float,
    hours_since_drop: float,
    prior_attempts: int,
    source: str,
    dropped_hour: int,
    is_weekend: int,
) -> float:
    """The true propensity the model is asked to learn."""
    # Business hours land best; very early and very late land worst.
    hour_penalty = -0.5 if dropped_hour < 7 or dropped_hour >= 21 else 0.15
    logit = (
        -0.85
        + 2.6 * progress_ratio
        - 0.011 * min(hours_since_drop, 240)
        - 0.55 * prior_attempts
        + SOURCE_EFFECT.get(source, 0.0)
        + hour_penalty
        - 0.20 * is_weekend
    )
    return _sigmoid(logit)


def generate(n: int = 4000, seed: int = 20260919) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    now = datetime(2026, 9, 19, 9, 0, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []

    for i in range(n):
        completed = rng.choices(
            population=[0, 1, 2, 3, 4, 5, 6, 7],
            weights=[6, 14, 20, 20, 15, 12, 8, 5],
            k=1,
        )[0]
        progress_ratio = completed / 8
        hours = round(rng.triangular(0.5, 240.0, 18.0), 2)
        prior_attempts = rng.choices([0, 1, 2, 3], weights=[62, 24, 10, 4], k=1)[0]
        source = rng.choices(SOURCES, weights=[SOURCE_WEIGHTS[s] for s in SOURCES], k=1)[0]
        dropped_at = now - timedelta(hours=hours)
        dropped_hour = dropped_at.hour
        is_weekend = 1 if dropped_at.weekday() >= 5 else 0

        p = recovery_probability(
            progress_ratio, hours, prior_attempts, source, dropped_hour, is_weekend
        )
        # Label noise - real call outcomes are never a clean function of features.
        p = min(0.97, max(0.03, p + rng.gauss(0, 0.06)))
        recovered = 1 if rng.random() < p else 0

        rows.append(
            {
                "lead_id": f"HIST-{i:05d}",
                "first_name": rng.choice(FIRST_NAMES),
                "last_name": rng.choice(LAST_NAMES),
                "known_field_count": completed,
                "known_fields": {f"field_{j}": "x" for j in range(completed)},
                "dropped_at": dropped_at.isoformat(),
                "prior_attempts": prior_attempts,
                "source": source,
                "recovered": recovered,
            }
        )
    return rows


def write(path: Path | None = None, n: int = 4000, seed: int = 20260919) -> Path:
    target = path or (DATA_DIR / "lead_history.json")
    rows = generate(n=n, seed=seed)
    target.write_text(json.dumps(rows, indent=1))
    return target


if __name__ == "__main__":
    out = write()
    data = json.loads(out.read_text())
    rate = sum(r["recovered"] for r in data) / len(data)
    print(f"wrote {len(data)} rows to {out}")
    print(f"base recovery rate: {rate:.3f}")

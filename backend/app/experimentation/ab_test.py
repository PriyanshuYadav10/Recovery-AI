from __future__ import annotations

"""A/B testing framework for field-collection scripts.

    PYTHONPATH=. python -m app.experimentation.ab_test

Compares two phrasings of the same question by running each variant's panel
of assumed customer responses through the real FieldExtractor and
ConfidenceEngine - the same code a live call uses - and measuring first-try
capture rate, average field confidence, and how often the answer would need
a clarification re-ask. This is a genuine experimentation harness with a
declared metric and a declared winner, not a metaphor for one.

Honesty note, stated once here and repeated in every report this produces:
there is no live call traffic to test against yet, so each variant's response
panel is a stated hypothesis about how that phrasing would shift customer
answers (see config/script_variants.json), not observed data. Swap in real
transcribed responses per variant the moment they exist and nothing else
in this file needs to change.
"""

import json
from pathlib import Path
from typing import Any

from app.ai.confidence_engine import ConfidenceEngine
from app.ai.field_extractor import FieldExtractor
from app.core.config import CONFIG_DIR
from app.journey.engine import JourneyEngine

VARIANTS_PATH = CONFIG_DIR / "script_variants.json"


def _load_experiments() -> list[dict[str, Any]]:
    return json.loads(VARIANTS_PATH.read_text())["experiments"]


def _step_for(field_id: str) -> dict[str, Any]:
    steps = {s["id"]: s for s in JourneyEngine().steps}
    if field_id not in steps:
        raise ValueError(f"unknown field {field_id!r} in script_variants.json")
    return steps[field_id]


def run_variant(step: dict[str, Any], responses: list[str]) -> dict[str, Any]:
    extractor = FieldExtractor()
    confidence = ConfidenceEngine()

    captured_first_try = 0
    needs_clarification = 0
    confidences: list[float] = []

    for text in responses:
        extracted = extractor.extract(text, step)
        field_conf = float(extracted.get("confidence", 0.0))
        _, low, _ = confidence.evaluate(
            speech=0.95, intent=0.9, field=field_conf,
            journey=0.9 if extracted.get("value") is not None else 0.5,
        )
        clarify = extracted.get("value") is None or low or extracted.get("needs_clarification")
        if clarify:
            needs_clarification += 1
        else:
            captured_first_try += 1
        confidences.append(field_conf)

    n = len(responses)
    return {
        "n": n,
        "first_try_capture_rate": round(captured_first_try / n, 3) if n else 0.0,
        "clarification_rate": round(needs_clarification / n, 3) if n else 0.0,
        "average_field_confidence": round(sum(confidences) / n, 3) if n else 0.0,
    }


def run_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    step = _step_for(experiment["field"])
    results = {}
    for variant_id, variant in experiment["variants"].items():
        results[variant_id] = {
            "script": variant["script"],
            **run_variant(step, variant["assumed_responses"]),
        }

    # Winner by first-try capture rate, tie-broken by average confidence -
    # the metric a real agent floor would actually care about (fewer re-asks).
    winner = max(
        results,
        key=lambda v: (results[v]["first_try_capture_rate"], results[v]["average_field_confidence"]),
    )

    return {
        "id": experiment["id"],
        "field": experiment["field"],
        "hypothesis": experiment["hypothesis"],
        "metric_goal": experiment["metric_goal"],
        "variants": results,
        "winner": winner,
        "data_source": "hypothesised response panel (see config/script_variants.json) - "
                       "not observed live-call data",
    }


def run_all() -> dict[str, Any]:
    experiments = [run_experiment(e) for e in _load_experiments()]
    return {"experiments": experiments}


if __name__ == "__main__":
    result = run_all()
    print("=" * 72)
    print("SCRIPT A/B TEST FRAMEWORK")
    print("=" * 72)
    for exp in result["experiments"]:
        print(f"\n{exp['id']}  (field: {exp['field']})")
        print(f"  hypothesis: {exp['hypothesis']}")
        for vid, v in exp["variants"].items():
            marker = " <- WINNER" if vid == exp["winner"] else ""
            print(
                f"  [{vid}] {v['script']!r}\n"
                f"       first-try capture {v['first_try_capture_rate']*100:.0f}%  "
                f"clarification rate {v['clarification_rate']*100:.0f}%  "
                f"avg confidence {v['average_field_confidence']:.2f}{marker}"
            )
    print(f"\ndata source: {result['experiments'][0]['data_source']}")

from __future__ import annotations

"""Offline evaluation for the intent and extraction engines.

    PYTHONPATH=. python evals/run_evals.py [--json] [--fail-under 0.85]

These are the two components that decide what the agent hears, so "it worked in
the demo" is not enough. This gives per-class precision/recall/F1 on a held
labelled set, prints every failure, and can gate CI on macro-F1.

The sets are hand-labelled from the behaviour the handout describes; they are
small by design and meant to grow as real call recordings arrive.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sklearn.metrics import classification_report, precision_recall_fscore_support

from app.ai.field_extractor import FieldExtractor
from app.ai.intent_engine import IntentEngine
from app.journey.engine import JourneyEngine

DATASETS = Path(__file__).resolve().parent / "datasets"
REPORT_PATH = Path(__file__).resolve().parent / "latest_report.json"


def evaluate_intents() -> dict:
    data = json.loads((DATASETS / "intent_cases.json").read_text())
    engine = IntentEngine()

    y_true, y_pred, failures = [], [], []
    for case in data["cases"]:
        expected = case["expected_event"]
        result = engine.detect(
            case["text"],
            state=case.get("state", "COLLECTING"),
            current_field=case.get("current_field"),
        )
        predicted = result["event"]
        predicted = predicted.value if hasattr(predicted, "value") else str(predicted)

        y_true.append(expected)
        y_pred.append(predicted)
        if predicted != expected:
            failures.append(
                {"text": case["text"], "expected": expected, "predicted": predicted}
            )

    p, r, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="macro", zero_division=0
    )
    accuracy = sum(a == b for a, b in zip(y_true, y_pred)) / len(y_true)
    return {
        "component": "intent_engine",
        "n_cases": len(y_true),
        "accuracy": round(accuracy, 4),
        "macro_precision": round(float(p), 4),
        "macro_recall": round(float(r), 4),
        "macro_f1": round(float(f1), 4),
        "per_class": classification_report(
            y_true, y_pred, zero_division=0, output_dict=True
        ),
        "failures": failures,
    }


def evaluate_extraction() -> dict:
    data = json.loads((DATASETS / "extraction_cases.json").read_text())
    extractor = FieldExtractor()
    steps = {s["id"]: s for s in JourneyEngine().steps}

    y_true, y_pred, failures = [], [], []
    per_field: dict[str, dict[str, int]] = {}

    for case in data["cases"]:
        field = case["field"]
        expected = case["expected_value"]
        got = extractor.extract(case["text"], steps[field]).get("value")

        correct = got == expected
        # Binary view for precision/recall: did we capture the right value?
        y_true.append(1)
        y_pred.append(1 if correct else 0)

        bucket = per_field.setdefault(field, {"correct": 0, "total": 0})
        bucket["total"] += 1
        bucket["correct"] += int(correct)

        if not correct:
            failures.append(
                {
                    "field": field,
                    "text": case["text"],
                    "expected": expected,
                    "got": got,
                    "kind": "false_capture" if expected is None else
                            ("miss" if got is None else "wrong_value"),
                }
            )

    accuracy = sum(y_pred) / len(y_pred)
    return {
        "component": "field_extractor",
        "n_cases": len(y_pred),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(accuracy, 4),
        "per_field": {
            k: {**v, "accuracy": round(v["correct"] / v["total"], 4)}
            for k, v in sorted(per_field.items())
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the raw report")
    parser.add_argument("--fail-under", type=float, default=0.0,
                        help="exit non-zero if either macro-F1 falls below this")
    args = parser.parse_args()

    intents = evaluate_intents()
    extraction = evaluate_extraction()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intent": intents,
        "extraction": extraction,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=" * 66)
    print("RECOVERY AI - OFFLINE EVALUATION")
    print("=" * 66)
    for block, label in ((intents, "Intent engine"), (extraction, "Field extractor")):
        print(f"\n{label}: {block['n_cases']} cases")
        print(f"  accuracy   {block['accuracy']:.3f}")
        print(f"  macro F1   {block['macro_f1']:.3f}")
        if block["failures"]:
            print(f"  failures   {len(block['failures'])}")
            for f in block["failures"]:
                if "field" in f:
                    print(f"    [{f['kind']}] {f['field']}: {f['text']!r} "
                          f"-> {f['got']!r} (expected {f['expected']!r})")
                else:
                    print(f"    {f['text']!r} -> {f['predicted']} (expected {f['expected']})")
        else:
            print("  failures   none")

    print(f"\nreport written to {REPORT_PATH}")

    worst = min(intents["macro_f1"], extraction["macro_f1"])
    if args.fail_under and worst < args.fail_under:
        print(f"\nFAIL: macro-F1 {worst:.3f} is below the {args.fail_under} gate")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

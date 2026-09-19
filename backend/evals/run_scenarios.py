from __future__ import annotations

"""End-to-end business-scenario suite - the 15 named cases the escalation and
journey design are meant to survive, each driven through a full
ConversationManager call rather than a unit-level check.

    PYTHONPATH=. python evals/run_scenarios.py [--json]

Complements evals/run_evals.py, which scores the intent engine and field
extractor in isolation. This scores outcomes: which state a full call landed
in, whether it escalated when it should have, whether the right fields came
out the other end.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.evaluation.scenarios import run_suite

REPORT_PATH = Path(__file__).resolve().parent / "latest_scenario_report.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(run_suite())
    REPORT_PATH.write_text(json.dumps(result, indent=2, default=str))

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["failed"] == 0 else 1

    print("=" * 70)
    print(f"BUSINESS SCENARIO SUITE - {result['passed']}/{result['total']} passed "
          f"({result['pass_rate']*100:.0f}%)")
    print("=" * 70)
    for c in result["cases"]:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"[{mark}] {c['id']:<26} {c['name']}")
        if not c["passed"]:
            for f in c["failures"]:
                print(f"       - {f}")
    print(f"\nreport written to {REPORT_PATH}")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

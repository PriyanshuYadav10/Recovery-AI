from __future__ import annotations

"""Per-call cost estimate: what running this on Groq + Twilio actually costs,
compared against a human agent's handle time from config/manual_baseline.json.

Every AI-side rate is a real, dated, cited unit price - see
config/cost_estimate.json. The human-side dollar figure needs a real CIMET
labour cost to mean anything; until then it's flagged as a placeholder in the
response itself, not just in the config file, so it can never be quoted
without the caveat attached.
"""

import json
from pathlib import Path
from typing import Any

from app.core.config import BASELINE_PATH, CONFIG_DIR

COST_CONFIG_PATH = CONFIG_DIR / "cost_estimate.json"


def compute() -> dict[str, Any]:
    cost = json.loads(COST_CONFIG_PATH.read_text())
    baseline = json.loads(Path(BASELINE_PATH).read_text()).get("manual", {})

    llm = cost["ai_side"]["llm"]
    tel = cost["ai_side"]["telephony"]

    llm_cost = (
        llm["assumed_tokens_per_call"]["input"] / 1_000_000 * llm["input_usd_per_million_tokens"]
        + llm["assumed_tokens_per_call"]["output"] / 1_000_000 * llm["output_usd_per_million_tokens"]
    )
    telephony_cost_us = tel["assumed_call_minutes"] * tel["usd_per_minute"]["us"]
    telephony_cost_in = tel["assumed_call_minutes"] * tel["usd_per_minute"]["india"]

    ai_total_us = round(llm_cost + telephony_cost_us, 4)
    ai_total_in = round(llm_cost + telephony_cost_in, 4)

    manual_seconds = float(baseline.get("average_handle_time_sec", 0)) + float(
        baseline.get("wrap_up_time_sec", 0)
    )
    placeholder_hourly = cost["human_side"]["fully_loaded_hourly_cost_placeholder_value"]
    human_cost_placeholder = round((manual_seconds / 3600) * placeholder_hourly, 2)

    return {
        "ai_cost_per_call_usd": {
            "calling_a_us_number": ai_total_us,
            "calling_an_india_number": ai_total_in,
            "breakdown": {
                "llm_groq": round(llm_cost, 5),
                "telephony_twilio_us": round(telephony_cost_us, 5),
                "telephony_twilio_india": round(telephony_cost_in, 5),
            },
        },
        "human_cost_per_call_usd_placeholder": human_cost_placeholder,
        "human_cost_is_placeholder": True,
        "manual_handle_time_sec_used": manual_seconds,
        "note": (
            "AI-side rates are real, dated, cited unit prices (see "
            "config/cost_estimate.json) applied to a stated per-call usage "
            "assumption - not a measurement. The human-side dollar figure "
            "uses a PLACEHOLDER hourly labour cost and must not be presented "
            "as a real comparison until CIMET supplies an actual figure."
        ),
        "sources": {
            "groq": llm["source"],
            "twilio": tel["source"],
        },
    }

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import CONFIG_DIR


class ScriptEngine:
    def __init__(self, scripts_path: Path | None = None):
        path = scripts_path or (CONFIG_DIR / "scripts.json")
        self.scripts = json.loads(path.read_text())

    def render(self, key: str, **kwargs: Any) -> str:
        template = self.scripts.get(key, "")
        try:
            return template.format(**{k: v for k, v in kwargs.items() if v is not None})
        except KeyError:
            return template

    def ask_field(self, step: dict[str, Any], known: dict[str, Any], retries: int = 0) -> str:
        if retries > 0:
            return f"Sorry, could you share your {step.get('label', step['id']).lower()} again?"
        q = step.get("question", f"What is your {step['id']}?")
        if known.get("postcode") and step["id"] != "postcode" and "Melbourne" in str(known.values()):
            return step.get("follow_up", q)
        if step["id"] == "postcode" and any("melbourne" in str(v).lower() for v in known.values()):
            return "Thanks. And what's the postcode for that property?"
        return q

    def acknowledge(self, label: str, value: Any) -> str:
        return self.render("field_ack", label=label, value=value)

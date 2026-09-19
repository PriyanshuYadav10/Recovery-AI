from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

from app.core.config import GROQ_DEFAULT_MODEL, GROQ_FALLBACK_MODELS


class GroqProvider:
    """Groq chat provider with deterministic local fallback."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        # `None` means "use the environment"; an explicit "" is a deliberate
        # request for deterministic mode (used by every scenario/eval suite so
        # results are reproducible for judges). Treating "" the same as "not
        # given" - via `api_key or os.getenv(...)` - silently pulled the real
        # key back in in any process where .env had already been loaded,
        # which made /api/evaluation flake against the live LLM instead of
        # staying deterministic the way its own docstring promised.
        self.api_key = os.getenv("GROQ_API_KEY", "").strip() if api_key is None else api_key
        self.model = model or os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL)
        # Groq retires model ids without notice, so keep a ladder to walk down
        # rather than dropping to deterministic mode on the first 404.
        self.candidates = [self.model] + [m for m in GROQ_FALLBACK_MODELS if m != self.model]
        self.retired: list[str] = []
        self.base_url = "https://api.groq.com/openai/v1"
        self.available = bool(self.api_key)
        self.last_error: Optional[str] = None
        self.mode = "groq" if self.available else "deterministic"

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.available and self.mode == "groq",
            "mode": self.mode,
            "model": self.model if self.available else None,
            "retired_models": self.retired,
            "last_error": self.last_error,
        }

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if not self.api_key:
            self.mode = "deterministic"
            return {"_fallback": True, "error": "GROQ_API_KEY missing"}

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        for candidate in [m for m in self.candidates if m not in self.retired]:
            payload = {
                "model": candidate,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": messages,
            }
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if resp.status_code >= 400:
                    body = resp.text[:200]
                    self.last_error = f"HTTP {resp.status_code}: {body}"
                    # A retired or unavailable model is permanent for this
                    # process - stop asking for it and try the next one.
                    if resp.status_code in (400, 404) and "model" in body.lower():
                        self.retired.append(candidate)
                        continue
                    self.mode = "deterministic"
                    return {"_fallback": True, "error": self.last_error}

                # Some reasoning models return a `reasoning` field containing
                # raw control characters, which the strict JSON parser rejects.
                # Parsing leniently keeps a working model from being discarded.
                data = json.loads(resp.text, strict=False)
                parsed = json.loads(
                    data["choices"][0]["message"]["content"], strict=False
                )
                self.model = candidate  # pin whichever one answered
                self.mode = "groq"
                self.last_error = None
                return parsed
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.mode = "deterministic"
                return {"_fallback": True, "error": self.last_error}

        self.mode = "deterministic"
        self.last_error = self.last_error or "no usable Groq model"
        return {"_fallback": True, "error": self.last_error}

    async def summarize_handoff(self, context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You generate warm handoff briefs for Energy recovery calls. "
            "Return JSON with keys: conversation_summary, recommended_opening, next_action. "
            "Never invent fields not present. No product or financial advice. "
            # The brief is read aloud by a human, so a placeholder in it reaches
            # the customer. The agent introduces themselves; do not name them.
            "recommended_opening must be a sentence the human agent can say "
            "verbatim. Never use placeholders, brackets or template markers such "
            "as [Agent Name] or [Name]. Do not invent or state the agent's name. "
            "Do not ask the customer for anything already collected. "
            "This is a live phone call, never a chat - do not refer to chat, "
            "messages or typing."
        )
        user = json.dumps(context)
        result = await self.chat_json(system, user)
        if result.get("_fallback"):
            fields = list((context.get("fields") or {}).keys())
            name = context.get("customer_name", "the customer")
            return {
                "conversation_summary": (
                    f"{name} started an Energy comparison and was contacted for dropout recovery. "
                    f"Consent status: {context.get('consent')}. "
                    f"Fields collected: {', '.join(fields) or 'none'}. "
                    f"Escalation reason: {context.get('reason')}."
                ),
                "recommended_opening": (
                    f"Hi, I can see what {name.split()[0]} has already provided, "
                    "so you won't need to repeat those details."
                ),
                "next_action": f"Continue from {context.get('current_stage', 'current step')}.",
            }
        return result

    async def enrich_turn(self, context: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You assist an Energy journey recovery voice agent. "
            "Return JSON only with: intent, field, value, confidence (0-1), "
            "needs_clarification (bool), mood, objection. "
            "Do not give product/financial advice. Do not invent payment data."
        )
        result = await self.chat_json(system, json.dumps(context))
        if result.get("_fallback"):
            return {}
        return result

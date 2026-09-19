from __future__ import annotations

import uuid
from typing import Any

from app.journey.engine import JourneyEngine
from app.models.schemas import utc_now


class JourneySandbox:
    """Stand-in for CIMET's journey-completion endpoint.

    Validates the payload the way a real consumer would - required keys,
    known status, every required Energy field present and consent recorded -
    then issues a reference. Swap JOURNEY_SUBMIT_URL to bypass this entirely.
    """

    VALID_STATUSES = {"completed", "abandoned", "escalated", "declined"}

    def __init__(self, journey: JourneyEngine | None = None):
        self.journey = journey or JourneyEngine()
        self.submissions: list[dict[str, Any]] = []

    def validate(self, payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in ("lead_id", "journey", "status", "fields", "metadata"):
            if key not in payload:
                errors.append(f"missing key: {key}")
        if errors:
            return errors

        if payload["journey"] != "energy":
            errors.append(f"unsupported journey: {payload['journey']}")
        if payload["status"] not in self.VALID_STATUSES:
            errors.append(f"unsupported status: {payload['status']}")
        if not isinstance(payload["fields"], dict):
            errors.append("fields must be an object")
        if not isinstance(payload["metadata"], dict):
            errors.append("metadata must be an object")
        if errors:
            return errors

        metadata = payload["metadata"]
        fields = payload["fields"]

        if payload["status"] == "completed":
            if not metadata.get("consent"):
                errors.append("consent must be true for a completed journey")
            if not metadata.get("recording_disclosed"):
                errors.append("recording_disclosed must be true")
            if not metadata.get("dnc_checked"):
                errors.append("dnc_checked must be true")
            for step in self.journey.steps:
                if step.get("required") and step["id"] not in fields:
                    errors.append(f"missing required field: {step['id']}")

        for step in self.journey.steps:
            if step["id"] in fields:
                errors.extend(self._validate_field(step, fields[step["id"]]))

        return errors

    def _validate_field(self, step: dict[str, Any], value: Any) -> list[str]:
        rules = step.get("validation") or {}
        vtype = rules.get("type")
        fid = step["id"]

        if vtype == "enum":
            allowed = rules.get("values", [])
            if str(value).lower() not in [str(v).lower() for v in allowed]:
                return [f"{fid}: '{value}' not in {allowed}"]
        elif vtype == "regex":
            import re

            if not re.match(rules.get("pattern", ".*"), str(value)):
                return [f"{fid}: '{value}' fails {rules.get('pattern')}"]
        elif vtype == "integer":
            try:
                n = int(value)
            except (TypeError, ValueError):
                return [f"{fid}: '{value}' is not an integer"]
            if "min" in rules and n < rules["min"]:
                return [f"{fid}: {n} below minimum {rules['min']}"]
            if "max" in rules and n > rules["max"]:
                return [f"{fid}: {n} above maximum {rules['max']}"]
        elif vtype == "text":
            if len(str(value).strip()) < rules.get("min_length", 0):
                return [f"{fid}: shorter than {rules.get('min_length')} characters"]
        return []

    def receive(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        errors = self.validate(payload)
        if errors:
            return 422, {"accepted": False, "errors": errors, "received_at": utc_now()}

        reference = f"CIMET-ENERGY-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "accepted": True,
            "reference": reference,
            "lead_id": payload["lead_id"],
            "status": payload["status"],
            "field_count": len(payload["fields"]),
            "received_at": utc_now(),
        }
        self.submissions.append({**record, "payload": payload})
        return 201, record

    def recent(self, limit: int = 25) -> list[dict[str, Any]]:
        return self.submissions[-limit:][::-1]

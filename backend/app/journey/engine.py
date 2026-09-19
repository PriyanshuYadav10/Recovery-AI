from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.core.config import CONFIG_DIR, DATA_DIR
from app.models.schemas import JourneyPayload, Lead
from app.services.store import Store


class JourneyEngine:
    def __init__(self, leads_store: Optional[Store] = None):
        self.definition = json.loads((CONFIG_DIR / "energy_journey.json").read_text())
        self.steps: list[dict[str, Any]] = self.definition["steps"]
        self.step_index = {s["id"]: i for i, s in enumerate(self.steps)}
        self.leads_store = leads_store

    def load_leads(self) -> list[Lead]:
        raw = json.loads((DATA_DIR / "synthetic_leads.json").read_text())
        leads = [Lead(**item) for item in raw]
        if self.leads_store is not None:
            leads.extend(Lead(**item) for item in self.leads_store.list_uploaded_leads())
        return leads

    def get_lead(self, lead_id: str) -> Lead | None:
        for lead in self.load_leads():
            if lead.lead_id == lead_id:
                return lead
        return None

    def missing_fields(self, known: dict[str, Any]) -> list[dict[str, Any]]:
        return [s for s in self.steps if s.get("required") and s["id"] not in known]

    def next_step(self, known: dict[str, Any]) -> dict[str, Any] | None:
        missing = self.missing_fields(known)
        return missing[0] if missing else None

    def progress(self, known: dict[str, Any]) -> list[dict[str, Any]]:
        items = [{"id": "consent", "label": "Consent", "status": "pending"}]
        for s in self.steps:
            status = "done" if s["id"] in known else "pending"
            items.append({"id": s["id"], "label": s.get("label", s["id"]), "status": status})
        return items

    def stage_name(self, known: dict[str, Any]) -> str:
        nxt = self.next_step(known)
        if not nxt:
            return "Confirmation"
        section = nxt.get("section", "collection")
        return {
            "property": "Property Details",
            "supply": "Supply Details",
            "usage": "Usage Details",
        }.get(section, nxt.get("label", "Collection"))

    def validate_for_submit(self, known: dict[str, Any], *, consent: bool, declined: bool) -> list[str]:
        errors = []
        if declined:
            errors.append("Customer declined")
        if not consent:
            errors.append("Consent required")
        for s in self.steps:
            if s.get("required") and s["id"] not in known:
                errors.append(f"Missing required field: {s['id']}")
        return errors


class JourneySubmissionService:
    def __init__(self, journey: JourneyEngine):
        self.journey = journey

    def build(
        self,
        lead: Lead,
        fields: dict[str, Any],
        *,
        status: str,
        consent: bool,
        dnc_checked: bool,
        recording_disclosed: bool,
    ) -> JourneyPayload:
        errors = []
        if status == "completed":
            errors = self.journey.validate_for_submit(fields, consent=consent, declined=False)
            if errors:
                raise ValueError("; ".join(errors))
        return JourneyPayload(
            lead_id=lead.lead_id,
            journey="energy",
            status=status,
            fields=fields,
            metadata={
                "consent": consent,
                "ai_assisted": True,
                "dnc_checked": dnc_checked,
                "recording_disclosed": recording_disclosed,
                "vertical": "Energy",
            },
        )

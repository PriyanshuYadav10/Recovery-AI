from __future__ import annotations

from typing import Any

from app.models.schemas import Lead


class DNCService:
    """Do-Not-Call gate. Stubbed for hackathon with clear architecture."""

    def check(self, lead: Lead) -> dict[str, Any]:
        eligible = not bool(lead.dnc_listed)
        return {
            "eligible": eligible,
            "source": "mock_acma_stub",
            "lead_id": lead.lead_id,
            "reason": None if eligible else "Number present on DNC register (synthetic)",
        }

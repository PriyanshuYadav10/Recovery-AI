from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from app.models.enums import HandoffStatus
from app.models.schemas import HandoffBrief, HandoffTicket, utc_now
from app.services.store import Store


class HandoffQueue:
    """Where a warm handoff actually lands.

    The AI escalates, a ticket is raised here with the brief and full context,
    and a human agent claims it from the Agent Inbox. The customer never
    repeats themselves because everything collected travels with the ticket.
    """

    def __init__(self, store: Optional[Store] = None):
        self.store = store
        self.tickets: dict[str, HandoffTicket] = {}
        self._created_monotonic: dict[str, float] = {}
        if store:
            for raw in store.list_handoffs():
                try:
                    ticket = HandoffTicket(**raw)
                    self.tickets[ticket.ticket_id] = ticket
                except Exception:
                    continue

    def raise_ticket(
        self,
        *,
        call_id: str,
        lead_id: str,
        customer: str,
        phone: str,
        reason: str,
        signals: list[str],
        brief: HandoffBrief | None,
        fields: dict[str, Any],
        transcript: list[dict[str, Any]],
        voice_mode: str = "BROWSER",
        transfer: dict[str, Any] | None = None,
    ) -> HandoffTicket:
        ticket = HandoffTicket(
            ticket_id=f"HO-{uuid.uuid4().hex[:6].upper()}",
            call_id=call_id,
            lead_id=lead_id,
            customer=customer,
            phone=phone,
            status=HandoffStatus.WAITING.value,
            reason=reason,
            signals=signals,
            brief=brief,
            fields=dict(fields),
            transcript=list(transcript),
            voice_mode=voice_mode,
            transfer=transfer or {},
        )
        self.tickets[ticket.ticket_id] = ticket
        self._created_monotonic[ticket.ticket_id] = time.monotonic()
        self._persist(ticket)
        return ticket

    def list(self, status: str | None = None) -> list[HandoffTicket]:
        items = list(self.tickets.values())
        if status:
            items = [t for t in items if t.status == status.upper()]
        return sorted(items, key=lambda t: t.created_at, reverse=True)

    def get(self, ticket_id: str) -> Optional[HandoffTicket]:
        return self.tickets.get(ticket_id)

    def claim(self, ticket_id: str, agent_name: str) -> Optional[HandoffTicket]:
        ticket = self.tickets.get(ticket_id)
        if not ticket or ticket.status != HandoffStatus.WAITING.value:
            return None
        started = self._created_monotonic.get(ticket_id)
        ticket.wait_seconds = round(time.monotonic() - started, 2) if started else 0.0
        ticket.status = HandoffStatus.CLAIMED.value
        ticket.claimed_at = utc_now()
        ticket.claimed_by = agent_name
        ticket.transcript.append(
            {
                "role": "human_agent",
                "text": ticket.brief.recommended_opening if ticket.brief else
                        "Hi, I can see everything so far - no need to repeat anything.",
                "ts": utc_now(),
            }
        )
        self._persist(ticket)
        return ticket

    def add_message(self, ticket_id: str, role: str, text: str) -> Optional[HandoffTicket]:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        ticket.transcript.append({"role": role, "text": text, "ts": utc_now()})
        self._persist(ticket)
        return ticket

    def update_fields(self, ticket_id: str, fields: dict[str, Any]) -> Optional[HandoffTicket]:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        ticket.fields.update(fields)
        self._persist(ticket)
        return ticket

    def note(self, ticket_id: str, author: str, text: str) -> Optional[HandoffTicket]:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        ticket.notes.append({"author": author, "text": text, "ts": utc_now()})
        self._persist(ticket)
        return ticket

    def resolve(self, ticket_id: str, resolution: str) -> Optional[HandoffTicket]:
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            return None
        ticket.status = HandoffStatus.RESOLVED.value
        ticket.resolved_at = utc_now()
        ticket.resolution = resolution
        self._persist(ticket)
        return ticket

    def stats(self) -> dict[str, Any]:
        claimed = [t for t in self.tickets.values() if t.claimed_at]
        waits = [t.wait_seconds for t in claimed if t.wait_seconds]
        return {
            "total": len(self.tickets),
            "waiting": len([t for t in self.tickets.values() if t.status == HandoffStatus.WAITING.value]),
            "claimed": len(claimed),
            "resolved": len([t for t in self.tickets.values() if t.status == HandoffStatus.RESOLVED.value]),
            "average_wait_sec": round(sum(waits) / len(waits), 2) if waits else 0.0,
        }

    def _persist(self, ticket: HandoffTicket) -> None:
        if self.store:
            try:
                self.store.save_handoff(ticket.model_dump())
            except Exception:
                pass

from __future__ import annotations

from typing import Any
from app.models.schemas import AuditEvent


class AuditLog:
    def __init__(self):
        self.events: list[AuditEvent] = []

    def emit(self, event: str, call_id: str | None = None, **details: Any) -> AuditEvent:
        item = AuditEvent(event=event, call_id=call_id, details=details)
        self.events.append(item)
        return item

    def tail(self, n: int = 50) -> list[AuditEvent]:
        return self.events[-n:]

    def clear(self) -> None:
        self.events.clear()

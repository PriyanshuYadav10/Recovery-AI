from __future__ import annotations

import json
from typing import Any, Optional

from app.core.config import RECORDINGS_DIR
from app.models.schemas import utc_now


class CallRecorder:
    """Writes the call artifact the disclosure promises.

    The consent line says the call is recorded, so every call leaves a durable
    record: full transcript, audit timeline, decisions and payload. When the
    Twilio bridge is live it also carries the provider recording URL.
    """

    def __init__(self, directory=None):
        self.dir = directory or RECORDINGS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        call_id: str,
        *,
        lead_id: str,
        status: str,
        voice_mode: str,
        transcript: list[dict[str, Any]],
        audit: list[dict[str, Any]],
        why: list[dict[str, Any]],
        fields: dict[str, Any],
        payload: Optional[dict[str, Any]] = None,
        receipt: Optional[dict[str, Any]] = None,
        handoff_brief: Optional[dict[str, Any]] = None,
        provider_recording_url: Optional[str] = None,
    ) -> str:
        record = {
            "call_id": call_id,
            "lead_id": lead_id,
            "status": status,
            "voice_mode": voice_mode,
            "recorded_at": utc_now(),
            "recording_disclosed": True,
            "provider_recording_url": provider_recording_url,
            "transcript": transcript,
            "audit": audit,
            "why": why,
            "fields": fields,
            "payload": payload,
            "receipt": receipt,
            "handoff_brief": handoff_brief,
        }
        path = self.dir / f"{call_id}.json"
        path.write_text(json.dumps(record, indent=2, default=str))
        return str(path)

    def read(self, call_id: str) -> Optional[dict[str, Any]]:
        path = self.dir / f"{call_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        files = sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        out = []
        for f in files:
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            out.append(
                {
                    "call_id": data.get("call_id"),
                    "lead_id": data.get("lead_id"),
                    "status": data.get("status"),
                    "recorded_at": data.get("recorded_at"),
                    "turns": len(data.get("transcript", [])),
                    "path": str(f),
                }
            )
        return out

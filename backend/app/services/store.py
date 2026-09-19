from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Optional

from app.core.config import DB_PATH
from app.models.schemas import utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_id TEXT PRIMARY KEY,
    lead_id TEXT,
    status TEXT,
    voice_mode TEXT,
    created_at TEXT,
    updated_at TEXT,
    snapshot TEXT
);
CREATE TABLE IF NOT EXISTS handoffs (
    ticket_id TEXT PRIMARY KEY,
    call_id TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    ticket TEXT
);
CREATE TABLE IF NOT EXISTS submissions (
    reference TEXT PRIMARY KEY,
    call_id TEXT,
    lead_id TEXT,
    accepted INTEGER,
    created_at TEXT,
    payload TEXT,
    receipt TEXT
);
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    raw TEXT,
    status TEXT,
    last_call_id TEXT,
    last_outcome TEXT,
    uploaded_at TEXT,
    updated_at TEXT
);
"""


class Store:
    """SQLite persistence so a backend restart never loses a demo."""

    def __init__(self, path: Optional[str] = None):
        self.path = str(path or DB_PATH)
        self._lock = threading.Lock()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def save_call(self, call_id: str, lead_id: str, status: str, voice_mode: str, snapshot: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO calls (call_id, lead_id, status, voice_mode, created_at, updated_at, snapshot)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(call_id) DO UPDATE SET
                     status=excluded.status,
                     voice_mode=excluded.voice_mode,
                     updated_at=excluded.updated_at,
                     snapshot=excluded.snapshot""",
                (call_id, lead_id, status, voice_mode, now, now, json.dumps(snapshot, default=str)),
            )

    def get_call(self, call_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT snapshot FROM calls WHERE call_id = ?", (call_id,)).fetchone()
        return json.loads(row["snapshot"]) if row else None

    def list_calls(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT call_id, lead_id, status, voice_mode, updated_at FROM calls ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_handoff(self, ticket: dict[str, Any]) -> None:
        now = utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO handoffs (ticket_id, call_id, status, created_at, updated_at, ticket)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticket_id) DO UPDATE SET
                     status=excluded.status,
                     updated_at=excluded.updated_at,
                     ticket=excluded.ticket""",
                (
                    ticket["ticket_id"],
                    ticket.get("call_id", ""),
                    ticket.get("status", "WAITING"),
                    ticket.get("created_at", now),
                    now,
                    json.dumps(ticket, default=str),
                ),
            )

    def list_handoffs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticket FROM handoffs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r["ticket"]) for r in rows]

    def save_submission(
        self, call_id: str, lead_id: str, payload: dict[str, Any], receipt: dict[str, Any]
    ) -> None:
        reference = receipt.get("reference") or f"unref-{call_id}"
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO submissions (reference, call_id, lead_id, accepted, created_at, payload, receipt)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(reference) DO UPDATE SET
                     accepted=excluded.accepted,
                     payload=excluded.payload,
                     receipt=excluded.receipt""",
                (
                    reference,
                    call_id,
                    lead_id,
                    1 if receipt.get("accepted") else 0,
                    utc_now(),
                    json.dumps(payload, default=str),
                    json.dumps(receipt, default=str),
                ),
            )

    # ------------------------------------------------ uploaded lead sheets

    def upsert_leads(self, leads: list[dict[str, Any]]) -> None:
        """Adds/refreshes uploaded leads. Re-uploading a sheet updates the
        contact details but never resets a lead already mid-workflow -
        call status and history survive a corrected re-upload."""
        now = utc_now()
        with self._lock, self._connect() as conn:
            for lead in leads:
                conn.execute(
                    """INSERT INTO leads (lead_id, raw, status, last_call_id, last_outcome, uploaded_at, updated_at)
                       VALUES (?, ?, 'NOT_CALLED', NULL, NULL, ?, ?)
                       ON CONFLICT(lead_id) DO UPDATE SET
                         raw=excluded.raw,
                         updated_at=excluded.updated_at""",
                    (lead["lead_id"], json.dumps(lead, default=str), now, now),
                )

    def list_uploaded_leads(self) -> list[dict[str, Any]]:
        """Plain Lead-shaped dicts (no status) - for the call-start pipeline,
        which only needs contact details and journey context."""
        with self._connect() as conn:
            rows = conn.execute("SELECT raw FROM leads").fetchall()
        return [json.loads(r["raw"]) for r in rows]

    def list_leads_with_status(self) -> list[dict[str, Any]]:
        """The CRM view: contact details plus where each lead stands."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT raw, status, last_call_id, last_outcome, uploaded_at, updated_at "
                "FROM leads ORDER BY uploaded_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            item = json.loads(r["raw"])
            item["status"] = r["status"] or "NOT_CALLED"
            item["last_call_id"] = r["last_call_id"]
            item["last_outcome"] = r["last_outcome"]
            item["uploaded_at"] = r["uploaded_at"]
            item["updated_at"] = r["updated_at"]
            out.append(item)
        return out

    def update_lead_status(
        self, lead_id: str, status: str, call_id: Optional[str] = None, outcome: Optional[str] = None
    ) -> None:
        """No-op for a lead_id the leads table has never seen (e.g. the
        built-in synthetic demo leads) - only uploaded leads are tracked."""
        with self._lock, self._connect() as conn:
            conn.execute(
                """UPDATE leads SET status = ?,
                     last_call_id = COALESCE(?, last_call_id),
                     last_outcome = COALESCE(?, last_outcome),
                     updated_at = ?
                   WHERE lead_id = ?""",
                (status, call_id, outcome, utc_now(), lead_id),
            )

    def delete_lead(self, lead_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM leads WHERE lead_id = ?", (lead_id,))

    def clear_leads(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM leads")

    def list_submissions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT reference, call_id, lead_id, accepted, created_at, payload, receipt
                   FROM submissions ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["accepted"] = bool(item["accepted"])
            item["payload"] = json.loads(item["payload"])
            item["receipt"] = json.loads(item["receipt"])
            out.append(item)
        return out

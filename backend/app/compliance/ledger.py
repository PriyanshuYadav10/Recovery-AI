from __future__ import annotations

import hashlib
import json
from typing import Any

# Distinguishes this ledger's genesis block from any other hash chain that
# happens to start from the same call_id.
_GENESIS_SEED = "RECOVERY-AI-COMPLIANCE-LEDGER"


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def genesis_hash(call_id: str) -> str:
    return hashlib.sha256(f"{_GENESIS_SEED}:{call_id}".encode("utf-8")).hexdigest()


def _field(event: Any, name: str, default: Any = None) -> Any:
    """Audit events arrive either as AuditEvent objects (live sessions) or
    plain dicts (persisted snapshots) - read either shape the same way."""
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def build_ledger(call_id: str, events: list[Any]) -> list[dict[str, Any]]:
    """Hash-chains a call's own audit trail - consent, the DNC check, every
    field captured, every guardrail and escalation decision, the submission
    outcome - into an append-only ledger.

    Each record's hash covers its own content plus the previous record's
    hash, so altering or reordering any single event breaks every hash that
    follows it. This doesn't add new events to track; it makes the events
    already being recorded for compliance provable rather than just trusted.
    """
    records: list[dict[str, Any]] = []
    prev = genesis_hash(call_id)
    for i, event in enumerate(events):
        body = {
            "index": i,
            "timestamp": _field(event, "timestamp"),
            "event": _field(event, "event"),
            "details": _field(event, "details", {}) or {},
            "prev_hash": prev,
        }
        record_hash = _hash(body)
        record = dict(body)
        record["hash"] = record_hash
        records.append(record)
        prev = record_hash
    return records


def verify_ledger(call_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Recomputes the chain from the genesis block and reports whether it
    still matches what's stored - the actual point of a tamper-evident log
    is being able to prove nothing was edited after the fact, not just
    claiming it wasn't."""
    prev = genesis_hash(call_id)
    for record in records:
        if record.get("prev_hash") != prev:
            return {
                "valid": False,
                "broken_at": record.get("index"),
                "reason": f"Record {record.get('index')} does not chain from the previous hash.",
                "record_count": len(records),
            }
        body = {
            "index": record.get("index"),
            "timestamp": record.get("timestamp"),
            "event": record.get("event"),
            "details": record.get("details"),
            "prev_hash": record.get("prev_hash"),
        }
        if _hash(body) != record.get("hash"):
            return {
                "valid": False,
                "broken_at": record.get("index"),
                "reason": f"Record {record.get('index')} ({record.get('event')}) was altered after it was written.",
                "record_count": len(records),
            }
        prev = record["hash"]
    return {
        "valid": True,
        "broken_at": None,
        "reason": None,
        "record_count": len(records),
        "final_hash": prev,
    }

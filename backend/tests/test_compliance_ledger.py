import copy

import pytest

from app.ai.conversation_manager import ConversationManager
from app.ai.groq_provider import GroqProvider
from app.compliance.ledger import build_ledger, genesis_hash, verify_ledger
from app.metrics.engine import MetricsEngine


def _events():
    return [
        {"timestamp": "t0", "event": "CALL_STARTED", "details": {"lead_id": "EN-1001"}},
        {"timestamp": "t1", "event": "DNC_CHECK", "details": {"eligible": True}},
        {"timestamp": "t2", "event": "CONSENT_GRANTED", "details": {}},
        {"timestamp": "t3", "event": "FIELD_CAPTURED", "details": {"field": "postcode", "value": "2000"}},
    ]


def test_chain_links_each_record_to_the_previous_hash():
    ledger = build_ledger("call-1", _events())
    assert len(ledger) == 4
    assert ledger[0]["prev_hash"] == genesis_hash("call-1")
    for i in range(1, len(ledger)):
        assert ledger[i]["prev_hash"] == ledger[i - 1]["hash"]


def test_clean_ledger_verifies():
    ledger = build_ledger("call-1", _events())
    result = verify_ledger("call-1", ledger)
    assert result["valid"] is True
    assert result["broken_at"] is None
    assert result["record_count"] == 4


def test_editing_a_captured_value_is_detected():
    ledger = build_ledger("call-1", _events())
    tampered = copy.deepcopy(ledger)
    tampered[3]["details"]["value"] = "9999"  # silently rewrite a captured field
    result = verify_ledger("call-1", tampered)
    assert result["valid"] is False
    assert result["broken_at"] == 3


def test_reordering_records_is_detected():
    ledger = build_ledger("call-1", _events())
    swapped = [ledger[0], ledger[2], ledger[1], ledger[3]]
    result = verify_ledger("call-1", swapped)
    assert result["valid"] is False
    assert result["broken_at"] is not None


def test_wrong_call_id_fails_verification():
    """A ledger is bound to the call it came from - replaying one call's
    chain under another call_id must not verify."""
    ledger = build_ledger("call-1", _events())
    result = verify_ledger("call-2", ledger)
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_real_call_produces_a_verifiable_ledger():
    mgr = ConversationManager(metrics=MetricsEngine(), groq=GroqProvider(api_key=""))
    await mgr.start("EN-1001", voice_mode="SIMULATED")
    await mgr.handle_utterance("Yes, that's fine.")
    snap = mgr.snapshot()
    ledger = snap["ledger"]
    assert len(ledger) >= 3  # at least CALL_STARTED, DNC_CHECK, DISCLOSURE_GIVEN
    events_seen = {r["event"] for r in ledger}
    assert "CALL_STARTED" in events_seen
    assert "DNC_CHECK" in events_seen
    assert verify_ledger(mgr.call_id, ledger)["valid"] is True

    # Tampering with the persisted chain (as the tamper-demo endpoint does on
    # a copy) must be caught, not silently accepted.
    tampered = copy.deepcopy(ledger)
    mid = len(tampered) // 2
    tampered[mid]["details"] = {**tampered[mid]["details"], "_edited": True}
    assert verify_ledger(mgr.call_id, tampered)["valid"] is False

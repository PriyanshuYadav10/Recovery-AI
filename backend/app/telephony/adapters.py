from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import BRIDGE_BASE_URL, HUMAN_QUEUE_NUMBER


class TelephonyAdapter(ABC):
    mode: str

    @abstractmethod
    async def start_call(self, to_number: str, metadata: dict[str, Any] | None = None) -> dict:
        ...

    @abstractmethod
    async def end_call(self, call_id: str) -> dict:
        ...

    @abstractmethod
    async def transfer_call(self, call_id: str, target: str) -> dict:
        ...

    @abstractmethod
    async def send_audio(self, call_id: str, audio: bytes) -> None:
        ...

    @abstractmethod
    async def receive_audio(self, call_id: str) -> bytes | None:
        ...


class BrowserVoiceAdapter(TelephonyAdapter):
    mode = "BROWSER"

    async def start_call(self, to_number: str, metadata: dict[str, Any] | None = None) -> dict:
        return {
            "status": "connected",
            "mode": self.mode,
            "to": to_number,
            "note": "Browser microphone + Web Speech / SpeechSynthesis",
        }

    async def end_call(self, call_id: str) -> dict:
        return {"status": "ended", "call_id": call_id, "mode": self.mode}

    async def transfer_call(self, call_id: str, target: str) -> dict:
        return {"status": "transfer_simulated", "call_id": call_id, "target": target}

    async def send_audio(self, call_id: str, audio: bytes) -> None:
        return None

    async def receive_audio(self, call_id: str) -> bytes | None:
        return None


class MockTelephonyAdapter(TelephonyAdapter):
    mode = "SIMULATED"

    async def start_call(self, to_number: str, metadata: dict[str, Any] | None = None) -> dict:
        return {
            "status": "simulated",
            "mode": self.mode,
            "to": to_number,
            "note": "No PSTN - simulated phone path for demos",
        }

    async def end_call(self, call_id: str) -> dict:
        return {"status": "ended", "call_id": call_id, "mode": self.mode}

    async def transfer_call(self, call_id: str, target: str) -> dict:
        return {"status": "warm_handoff_simulated", "call_id": call_id, "target": target}

    async def send_audio(self, call_id: str, audio: bytes) -> None:
        return None

    async def receive_audio(self, call_id: str) -> bytes | None:
        return None


class ViciDialAdapter(TelephonyAdapter):
    """Stub ready for CIMET ViciDial/SIP credentials."""

    mode = "VICIDIAL"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.configured = bool(self.config.get("host") and self.config.get("api_user"))

    async def start_call(self, to_number: str, metadata: dict[str, Any] | None = None) -> dict:
        if not self.configured:
            return {
                "status": "not_configured",
                "mode": self.mode,
                "error": "ViciDial credentials not supplied - use BrowserVoiceAdapter",
            }
        return {"status": "ready_to_dial", "mode": self.mode, "to": to_number}

    async def end_call(self, call_id: str) -> dict:
        return {"status": "ended", "call_id": call_id, "mode": self.mode}

    async def transfer_call(self, call_id: str, target: str) -> dict:
        return {"status": "transfer_pending_config", "call_id": call_id, "target": target}

    async def send_audio(self, call_id: str, audio: bytes) -> None:
        raise NotImplementedError("ViciDial audio bridge requires on-site credentials")

    async def receive_audio(self, call_id: str) -> bytes | None:
        raise NotImplementedError("ViciDial audio bridge requires on-site credentials")


class TwilioBridgeAdapter(TelephonyAdapter):
    """Real PSTN via the Node media-stream bridge in telephony/bridge.

    Audio never passes through Python: Twilio streams it to the bridge, the
    bridge transcribes and calls this backend for every turn. Dial and
    transfer are control-plane calls to the bridge's REST API.
    """

    mode = "TWILIO"

    def __init__(self, base_url: str | None = None, human_queue: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or BRIDGE_BASE_URL).rstrip("/")
        self.human_queue = human_queue if human_queue is not None else HUMAN_QUEUE_NUMBER
        self.timeout = timeout
        self.provider_call_sid: str | None = None

    async def _post(self, path: str, body: dict[str, Any]) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=body)
            data = resp.json() if resp.content else {}
            data.setdefault("status", "ok" if resp.is_success else "error")
            data["http_status"] = resp.status_code
            return data
        except Exception as exc:
            return {
                "status": "bridge_unavailable",
                "mode": self.mode,
                "error": f"{type(exc).__name__}: {exc}",
                "hint": f"Start the Node bridge at {self.base_url} (see telephony/bridge/README.md)",
            }

    async def start_call(self, to_number: str, metadata: dict[str, Any] | None = None) -> dict:
        result = await self._post("/dial", {"to": to_number, "metadata": metadata or {}})
        self.provider_call_sid = result.get("callSid")
        result.setdefault("mode", self.mode)
        return result

    async def end_call(self, call_id: str) -> dict:
        return await self._post("/hangup", {"callId": call_id, "callSid": self.provider_call_sid})

    async def transfer_call(self, call_id: str, target: str) -> dict:
        """Warm transfer: Twilio re-issues TwiML that dials the human queue."""
        if not self.human_queue:
            return {
                "status": "transfer_unconfigured",
                "mode": self.mode,
                "error": "HUMAN_QUEUE_NUMBER is not set - ticket raised in the Agent Inbox instead",
                "call_id": call_id,
            }
        return await self._post(
            "/transfer",
            {"callId": call_id, "callSid": self.provider_call_sid, "target": target or self.human_queue},
        )

    async def send_audio(self, call_id: str, audio: bytes) -> None:
        # The bridge owns the audio path; Python never touches call media.
        return None

    async def receive_audio(self, call_id: str) -> bytes | None:
        return None


def get_adapter(mode: str = "BROWSER") -> TelephonyAdapter:
    mode = (mode or "BROWSER").upper()
    if mode == "TWILIO":
        return TwilioBridgeAdapter()
    if mode == "VICIDIAL":
        return ViciDialAdapter()
    if mode == "SIMULATED":
        return MockTelephonyAdapter()
    return BrowserVoiceAdapter()

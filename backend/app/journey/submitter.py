from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.core.config import (
    JOURNEY_SUBMIT_RETRIES,
    JOURNEY_SUBMIT_TIMEOUT,
    JOURNEY_SUBMIT_TOKEN,
    JOURNEY_SUBMIT_URL,
)
from app.models.schemas import JourneyPayload, SubmissionReceipt, utc_now


class JourneySubmitClient:
    """POSTs the completed journey to the completion sandbox and keeps the receipt.

    Defaults to the built-in mock at /api/sandbox/journey/submit. Point
    JOURNEY_SUBMIT_URL at CIMET's sandbox and nothing else changes.
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        timeout: float | None = None,
        retries: int | None = None,
        token: str | None = None,
        local_handler: Any = None,
    ):
        self.url = url or JOURNEY_SUBMIT_URL
        self.timeout = timeout if timeout is not None else JOURNEY_SUBMIT_TIMEOUT
        self.retries = retries if retries is not None else JOURNEY_SUBMIT_RETRIES
        self.token = token if token is not None else JOURNEY_SUBMIT_TOKEN
        # When the target is the built-in mock, resolve it in process so nothing
        # depends on the API being reachable from itself. Any other URL
        # (including CIMET's sandbox) goes over the wire.
        if self._is_builtin_mock(self.url):
            self.local_handler = local_handler or self._default_sandbox()
        else:
            self.local_handler = None

    @staticmethod
    def _default_sandbox():
        from app.services.sandbox import JourneySandbox

        return JourneySandbox()

    @staticmethod
    def _is_builtin_mock(url: str) -> bool:
        return url.rstrip("/").endswith("/api/sandbox/journey/submit")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def submit(self, payload: JourneyPayload) -> SubmissionReceipt:
        body = payload.model_dump()
        attempts = 0
        last_error: Optional[str] = None
        started = time.time()

        if self.local_handler is not None:
            status_code, data = self.local_handler.receive(body)
            return SubmissionReceipt(
                accepted=200 <= status_code < 300,
                reference=data.get("reference"),
                endpoint=self.url,
                transport="in-process",
                status_code=status_code,
                attempts=1,
                latency_ms=int((time.time() - started) * 1000),
                received_at=data.get("received_at") or utc_now(),
                error=None if 200 <= status_code < 300 else str(data.get("errors") or data),
                response=data,
            )

        while attempts < max(1, self.retries):
            attempts += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(self.url, json=body, headers=self._headers())
                latency = int((time.time() - started) * 1000)
                data: dict[str, Any]
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:500]}

                if 200 <= resp.status_code < 300:
                    return SubmissionReceipt(
                        accepted=True,
                        reference=data.get("reference") or data.get("id"),
                        endpoint=self.url,
                        status_code=resp.status_code,
                        attempts=attempts,
                        latency_ms=latency,
                        received_at=data.get("received_at") or utc_now(),
                        response=data,
                    )

                last_error = f"HTTP {resp.status_code}: {data}"
                # 4xx is a bad payload - retrying will not help.
                if 400 <= resp.status_code < 500:
                    return SubmissionReceipt(
                        accepted=False,
                        endpoint=self.url,
                        status_code=resp.status_code,
                        attempts=attempts,
                        latency_ms=latency,
                        error=last_error,
                        response=data,
                    )
            except Exception as exc:  # network down, sandbox not running
                last_error = f"{type(exc).__name__}: {exc}"

        return SubmissionReceipt(
            accepted=False,
            endpoint=self.url,
            attempts=attempts,
            latency_ms=int((time.time() - started) * 1000),
            error=last_error or "submission failed",
        )

"""acquisition/v2/http.py: deterministic GET with retry/throttle (pattern of acquisition/v1_1/alpaca_client.py).

401/403 are fatal and never retried. Credentials are sent as headers only and never returned in records.
"""

from __future__ import annotations

import time
from typing import Any, Callable

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_SLEEPS_S = (2.0, 5.0, 15.0)
FATAL_STATUSES = frozenset({401, 403})
MAX_PAGES = 100


class AlpacaRequestError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, fatal: bool = False):
        super().__init__(message)
        self.status = status
        self.fatal = fatal


class RequestGuardError(RuntimeError):
    """A request outside the frozen Stage R contract was refused before any network call."""


class HttpClient:
    def __init__(self, api_key: str, secret_key: str, *, get: Callable[..., Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 min_interval_s: float = 0.35, timeout_s: float = 30.0) -> None:
        if not api_key or not secret_key:
            raise ValueError("Alpaca credentials are missing")
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key, "Accept": "application/json"}
        if get is None:
            import requests
            get = requests.get
        self._get = get
        self._sleep = sleep
        self._clock = clock
        self._min_interval = min_interval_s
        self._timeout = timeout_s
        self._last_call: float | None = None

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def get_json(self, url: str, params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        for attempt in range(len(RETRY_SLEEPS_S) + 1):
            if attempt:
                self._sleep(RETRY_SLEEPS_S[attempt - 1])
            self._throttle()
            try:
                resp = self._get(url, params=dict(params), headers=self._headers, timeout=self._timeout)
            except OSError as exc:
                attempts.append({"attempt": attempt + 1, "error": type(exc).__name__})
                continue
            status = int(resp.status_code)
            rid = resp.headers.get("X-Request-ID") if resp.headers else None
            attempts.append({"attempt": attempt + 1, "status": status, "request_id": rid})
            if status == 200:
                return resp.json(), {"status": status, "request_id": rid, "attempts": attempts}
            body = (resp.text or "")[:300]
            if status in FATAL_STATUSES:
                raise AlpacaRequestError(f"HTTP {status}: {body}", status=status, fatal=True)
            if status not in RETRY_STATUSES:
                raise AlpacaRequestError(f"HTTP {status}: {body}", status=status)
        raise AlpacaRequestError(f"retries exhausted: {attempts}", status=None)

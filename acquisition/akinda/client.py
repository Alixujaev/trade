"""acquisition/akinda/client.py: GET /compliance/{TICKER} with bounded attempts (pattern of acquisition/v2/http.py).

- The key is sent only as the X-API-Key header; it never appears in URLs, records, errors or stored bodies.
- 401 / 403 (bad key / plan lacks endpoint) -> AkindaError(kind="auth"); never retried; the caller stops the batch.
- 429 (rate or quota exceeded) -> AkindaError(kind="rate_limited") at once; never retried.
- 5xx and network errors -> at most MAX_ATTEMPTS_PER_TICKER attempts in total.
- Every attempt first calls `before_attempt(ticker)` (daily-budget ledger), which may raise AkindaError("quota").
- Any other status (e.g. 404 "not in our coverage") is returned to the caller, which writes no record.
- Redirects are never followed (allow_redirects=False): requests strips only `Authorization` on a cross-host
  redirect, so the custom X-API-Key header would otherwise reach the redirect target. A 3xx gets no record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable

from acquisition.akinda.contract import (
    API_KEY_HEADER,
    BASE_URL,
    MAX_ATTEMPTS_PER_TICKER,
    RETRY_SLEEP_S,
    TICKER_RE,
    TIMEOUT_S,
)


class AkindaError(RuntimeError):
    def __init__(self, message: str, *, kind: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


@dataclass
class FetchResult:
    ticker: str
    http_status: int | None                  # None -> attempts exhausted without an HTTP response worth keeping
    body: bytes | None                       # redacted body bytes as stored in evidence
    attempts: list[dict[str, Any]] = field(default_factory=list)


def redact(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def compliance_url(ticker: str) -> str:
    if not isinstance(ticker, str) or not TICKER_RE.match(ticker):
        raise ValueError(f"invalid ticker {ticker!r}")
    url = f"{BASE_URL}/compliance/{ticker}"
    if not url.startswith(BASE_URL + "/compliance/"):
        raise ValueError(f"refusing URL outside the pinned endpoint: {url}")
    return url


class AkindaClient:
    def __init__(self, api_key: str, *, get: Callable[..., Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 before_attempt: Callable[[str], None] = lambda _t: None, timeout_s: float = TIMEOUT_S) -> None:
        if not api_key:
            raise AkindaError("Akinda API key is missing", kind="config")
        if get is None:
            import requests
            get = requests.get
        self._key = api_key
        self._headers = {API_KEY_HEADER: api_key, "Accept": "application/json"}
        self._get, self._sleep, self._before, self._timeout = get, sleep, before_attempt, timeout_s

    def _body(self, resp: Any) -> bytes:
        raw = resp.content if isinstance(resp.content, bytes) else str(resp.content).encode("utf-8")
        return raw.replace(self._key.encode("utf-8"), b"***")

    def fetch(self, ticker: str) -> FetchResult:
        url = compliance_url(ticker)
        res = FetchResult(ticker, None, None)
        for n in range(MAX_ATTEMPTS_PER_TICKER):
            if n:
                self._sleep(RETRY_SLEEP_S)
            self._before(ticker)
            try:
                resp = self._get(url, headers=dict(self._headers), timeout=self._timeout,
                                 allow_redirects=False)                # requests keeps X-API-Key on redirects
            except OSError as exc:                                   # requests' errors subclass OSError
                res.attempts.append({"attempt": n + 1, "error": type(exc).__name__})
                continue
            status = int(resp.status_code)
            body = self._body(resp)
            res.attempts.append({"attempt": n + 1, "status": status})
            snippet = body[:300].decode("utf-8", "replace")
            if status in (401, 403):
                raise AkindaError(f"HTTP {status} (key or plan): {snippet}", kind="auth", status=status)
            if status == 429:
                raise AkindaError(f"HTTP 429 (rate or quota exceeded): {snippet}", kind="rate_limited", status=429)
            if status >= 500:
                continue
            res.http_status, res.body = status, body
            return res
        return res

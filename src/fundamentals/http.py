"""GET JSON from the public data sources, with retries and a per-host rate limit."""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx


class RateLimiter:
    """At most ``rps`` calls per second, shared by the threads that use it."""

    def __init__(self, rps: float):
        self.min_interval = 1.0 / rps
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.min_interval
        if delay > 0:
            time.sleep(delay)


class UpstreamError(Exception):
    """A data source answered with an error that retrying will not fix."""

    def __init__(self, source: str, status: int, detail: str = ""):
        super().__init__(f"{source} answered {status} {detail}".strip())
        self.source, self.status, self.detail = source, status, detail


def get_json(
    url: str,
    *,
    source: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    limiter: RateLimiter | None = None,
    client: httpx.Client | None = None,
    retries: int = 4,
) -> Any:
    """GET ``url`` and decode its JSON body. Retries transport errors, 429 and 5xx."""
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    try:
        for attempt in range(retries):
            if limiter:
                limiter.wait()
            try:
                resp = client.get(url, params=params, headers=headers)
            except httpx.TransportError:
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(min(float(resp.headers.get("retry-after", 2**attempt)), 10))
                continue
            if resp.status_code >= 400:
                raise UpstreamError(source, resp.status_code, resp.text[:200])
            return resp.json()
        raise UpstreamError(source, 0, "no answer after retries")
    finally:
        if own:
            client.close()

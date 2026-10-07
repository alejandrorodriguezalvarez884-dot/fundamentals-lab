"""The public service: the site and the API, from one origin.

    GET /api/health
    GET /api/search?q=                  companies whose ticker or name matches
    GET /api/stock/{ticker}             the full report (fundamentals, valuation, forward, technical)
    GET /api/stock/{ticker}/stream      the same, step by step as it is built
    GET /api/stock/{ticker}/reading     the AI reading of the report (may call the model)
    GET /api/compare?tickers=A,B,C      side-by-side comparison of 2 to 5 companies
    GET /api/compare/reading?tickers=   the AI reading of the comparison (may call the model)
    GET /api/me                         who is signed in to Market Hub, and the hub's address

Everything else is the static site, when FUNDAMENTALS_STATIC_DIR points at its build.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .budget import Budget, BudgetReached
from .compare import compare
from .config import COMPARE_MAX, COMPARE_MIN, PER_IP_PER_HOUR
from .fmp import SourceUnavailable
from .hubauth import HubGate
from .hubauth import settings as hub_settings
from .http import UpstreamError
from .reading import Reader, ReadingRefused, ReadingUnavailable
from .report import NoData, Reporter, compact
from .sec import Directory, UnknownCompany
from .store import Store, default_store

log = logging.getLogger("fundamentals.api")


class RateLimiter:
    """At most ``limit`` calls per address in any ``window`` seconds. Per instance, in memory."""

    def __init__(self, limit: int, window: float = 3600.0):
        self.limit, self.window = limit, window
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, who: str) -> bool:
        now = time.monotonic()
        with self._lock:
            calls = self._calls[who]
            while calls and now - calls[0] > self.window:
                calls.popleft()
            if len(calls) >= self.limit:
                return False
            calls.append(now)
            return True


def _client_address(request: Request) -> str:
    # Cloud Run puts the caller first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _failure(exc: Exception, ticker: str = "") -> HTTPException:
    """What the visitor is told when something cannot be done. Upstream error bodies never reach
    the visitor or the logs: they could carry request details."""
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, UnknownCompany):
        return HTTPException(404, "No US-listed company with that ticker. Search by name to find it.")
    if isinstance(exc, NoData):
        return HTTPException(404, "No financial statements found for this company.")
    if isinstance(exc, BudgetReached):
        return HTTPException(429, "The AI reading has reached its spending limit for now. The numbers "
                                  "and charts keep working; readings already written are still shown.")
    if isinstance(exc, ReadingUnavailable):
        return HTTPException(503, "The AI reading is not switched on yet. The numbers and charts work.")
    if isinstance(exc, ReadingRefused):
        return HTTPException(502, "The model could not write a reading for this request.")
    if isinstance(exc, SourceUnavailable):
        log.warning("market data unavailable for %s", ticker)
        return HTTPException(503, "The market data provider is not available right now.")
    if isinstance(exc, (UpstreamError, httpx.HTTPError, anthropic.APIConnectionError, anthropic.APIStatusError)):
        log.warning("upstream failure for %s: %s", ticker, type(exc).__name__)
        return HTTPException(502, "A data source did not answer. Try again in a moment.")
    log.exception("request for %s failed", ticker)
    return HTTPException(500, "Something failed. Try again in a moment.")


def _tickers(raw: str) -> list[str]:
    tickers = []
    for t in raw.split(","):
        t = t.strip().upper()
        if t and t not in tickers:
            tickers.append(t)
    if not COMPARE_MIN <= len(tickers) <= COMPARE_MAX:
        raise HTTPException(400, f"Compare between {COMPARE_MIN} and {COMPARE_MAX} companies.")
    return tickers


def create_app(store: Store | None = None, directory: Directory | None = None,
               reporter: Reporter | None = None, reader: Reader | None = None,
               static_dir: str | None = None, hub: tuple[str, str] | None | bool = True) -> FastAPI:
    """App factory. Tests pass their own pieces, so they need no network.

    ``hub`` is (hub URL, hub session secret) to admit only people signed in to Market Hub; by
    default it comes from HUB_URL and HUB_SESSION_SECRET, and None leaves the service public."""
    logging.basicConfig(level=logging.INFO)
    # httpx logs every request URL at INFO, and FMP takes the key in the query string: keep the
    # key out of the logs. yfinance prints what Yahoo answers when it has no such symbol.
    for noisy in ("httpx", "httpcore", "yfinance"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    app = FastAPI(title="Fundamentals Lab", docs_url=None, redoc_url=None, openapi_url=None)

    origins = [o.strip() for o in os.environ.get("FUNDAMENTALS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])
    hub = hub_settings() if hub is True else hub or None
    if hub:
        app.add_middleware(HubGate, hub_url=hub[0], secret=hub[1])

    store = store or default_store()
    directory = directory or Directory()
    reporter = reporter or Reporter(store)
    reader = reader or Reader(store, Budget(store))
    data_limiter = RateLimiter(PER_IP_PER_HOUR * 4)  # reports cost provider quota, not money
    reading_limiter = RateLimiter(PER_IP_PER_HOUR)

    def allow(request: Request, limiter: RateLimiter) -> None:
        # Behind the hub's sign-in there is no per-address limit (the owner's choice); the
        # spending caps of the reading still apply.
        if hub:
            return
        if not limiter.allow(_client_address(request)):
            raise HTTPException(429, "Too many requests from this address. Try again in an hour.")

    def report_for(ticker: str) -> dict:
        company = directory.get(ticker)
        return reporter.build(company)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request) -> dict:
        return {"user": getattr(request.state, "user", None), "hub": hub[0] if hub else None}

    @app.get("/api/search")
    def search(q: str = Query(min_length=1, max_length=60)) -> dict:
        try:
            found = directory.search(q)
        except Exception as exc:
            raise _failure(exc) from None
        return {"companies": [{"ticker": c.ticker, "name": c.name} for c in found]}

    @app.get("/api/stock/{ticker}")
    def stock(ticker: str, request: Request) -> dict:
        allow(request, data_limiter)
        try:
            return report_for(ticker)
        except Exception as exc:
            raise _failure(exc, ticker) from None

    @app.get("/api/stock/{ticker}/stream")
    def stock_stream(ticker: str, request: Request) -> StreamingResponse:
        """One JSON object per line as each step happens; the last is ``done`` or ``error``."""
        allow(request, data_limiter)
        try:
            company = directory.get(ticker)
        except Exception as exc:
            raise _failure(exc, ticker) from None

        def lines() -> Iterator[str]:
            try:
                for event in reporter.run(company):
                    yield json.dumps(event, default=str) + "\n"
            except Exception as exc:
                failure = _failure(exc, ticker)
                yield json.dumps({"step": "error", "status": failure.status_code, "detail": failure.detail}) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/stock/{ticker}/reading", response_model=None)
    def stock_reading(ticker: str, request: Request, cached_only: bool = False) -> dict | Response:
        """``cached_only`` returns today's reading if someone already paid for it, or 204: the page
        uses it on load so that opening a page never spends."""
        try:
            company = directory.get(ticker)
            cached = reader.cached("company", company.ticker)
            if cached:
                return {**cached, "read_now": False}
            if cached_only:
                return Response(status_code=204)
            allow(request, reading_limiter)
            report = reporter.build(company)
            return reader.company(compact(report))
        except Exception as exc:
            raise _failure(exc, ticker) from None

    def reports_for(tickers: list[str]) -> list[dict]:
        companies = [directory.get(t) for t in tickers]
        with ThreadPoolExecutor(max_workers=len(companies)) as pool:
            return list(pool.map(reporter.build, companies))

    @app.get("/api/compare")
    def compare_view(request: Request, tickers: str = Query(max_length=60)) -> dict:
        wanted = _tickers(tickers)
        allow(request, data_limiter)
        try:
            return compare(reports_for(wanted))
        except Exception as exc:
            raise _failure(exc, ",".join(wanted)) from None

    @app.get("/api/compare/reading", response_model=None)
    def compare_reading(request: Request, tickers: str = Query(max_length=60),
                        cached_only: bool = False) -> dict | Response:
        wanted = _tickers(tickers)
        try:
            subject = "-".join(sorted(wanted))
            cached = reader.cached("compare", subject)
            if cached:
                return {**cached, "read_now": False}
            if cached_only:
                return Response(status_code=204)
            allow(request, reading_limiter)
            return reader.comparison(compare(reports_for(wanted))["companies"])
        except Exception as exc:
            raise _failure(exc, ",".join(wanted)) from None

    @app.get("/api/budget")
    def budget() -> dict:
        return reader.budget.status()

    static_dir = static_dir or os.environ.get("FUNDAMENTALS_STATIC_DIR", "")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="site")
    return app

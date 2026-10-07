"""The company report: everything the stock page shows, built from the sources and kept a few
hours in the store so repeated visits do not spend the data provider's quota."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

from . import metrics, technical
from .backfill import backfill
from .config import ANNUAL_YEARS, BENCHMARK, PRICE_YEARS, QUARTERS, REPORT_TTL_HOURS
from .fmp import FmpClient, SourceUnavailable
from .http import UpstreamError
from .forward import forward_multiples
from .sec import Company, fetch_annual
from .store import Store
from .yahoo import default_source

log = logging.getLogger("fundamentals.report")

REPORT_VERSION = 1


class NoData(Exception):
    """Neither source has statements for this company."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh(report: dict | None, hours: float = REPORT_TTL_HOURS) -> bool:
    if not report or report.get("version") != REPORT_VERSION:
        return False
    built = datetime.fromisoformat(report["built_utc"])
    return _now() - built < timedelta(hours=hours)


class Reporter:
    def __init__(self, store: Store, fmp: FmpClient | None = None, sec_annual=fetch_annual):
        self.store = store
        self.fmp = fmp or default_source()  # the source of market data: Yahoo, or FMP
        self.sec_annual = sec_annual

    def cached(self, ticker: str) -> dict | None:
        report = self.store.get(f"report/{ticker.upper()}")
        return report if _fresh(report) else None

    def build(self, company: Company) -> dict:
        result = None
        for event in self.run(company):
            if event["step"] == "done":
                result = event["report"]
        return result

    def run(self, company: Company) -> Iterator[dict]:
        """Build the report step by step, yielding each step as it happens. The last event is
        ``done`` with the report."""
        cached = self.cached(company.ticker)
        if cached:
            yield {"step": "cache", "detail": f"Built {cached['built_utc'][:16].replace('T', ' ')} UTC"}
            yield {"step": "done", "report": cached}
            return

        ticker = company.ticker
        source = getattr(self.fmp, "name", "FMP")
        sources: dict[str, str] = {}
        notes: list[str] = []
        profile: dict = {}
        annual: list[dict] = []
        quarters: list[dict] = []

        yield {"step": "profile", "detail": "Company profile and price"}
        try:
            profile = self.fmp.profile(ticker)
            sources["profile"] = source
        except SourceUnavailable as exc:
            notes.append(f"Profile not available: {exc}")
        profile = {"ticker": ticker, "name": company.name, "cik": company.cik, **{k: v for k, v in profile.items() if v not in (None, "")}}

        yield {"step": "statements", "detail": f"Income statement, balance sheet and cash flow ({ANNUAL_YEARS} years, {QUARTERS} quarters)"}
        try:
            annual = self.fmp.statements(ticker, "annual", ANNUAL_YEARS)
            sources["statements"] = source
        except (SourceUnavailable, UpstreamError) as exc:
            # The visitor sees the notes: never put an upstream error body in them.
            log.warning("%s statements for %s failed: %s", source, ticker, type(exc).__name__)
            notes.append(f"Statements from {source} were not available; using the SEC XBRL filings.")
        if not annual:
            try:
                annual = [{k: v for k, v in row.items() if k != "per_share_filed"} for row in self.sec_annual(company.cik, ANNUAL_YEARS)]
                sources["statements"] = "SEC EDGAR (XBRL)"
            except Exception as exc:  # noqa: BLE001 - the fallback must not hide the main error
                log.warning("SEC facts for %s failed: %s", ticker, type(exc).__name__)
        if not annual:
            raise NoData(ticker)
        # A source with a short history (Yahoo: four fiscal years) gets the older years from the
        # SEC, when the two agree on the years they share. One year more than the report shows,
        # so growth over ten years has its first year.
        if sources.get("statements") == source and hasattr(self.fmp, "splits") and len(annual) <= ANNUAL_YEARS:
            try:
                longer = backfill(annual, self.sec_annual(company.cik, ANNUAL_YEARS + 1), self.fmp.splits(ticker), ANNUAL_YEARS + 1)
            except Exception as exc:  # noqa: BLE001 - a longer history is an extra: the report stands without it
                log.warning("longer history for %s failed: %s", ticker, type(exc).__name__)
                longer = annual
            if len(longer) > len(annual):
                sources["statements"] = f"{source}; SEC EDGAR (XBRL) before fiscal {annual[0]['fiscal_year']}"
                annual = longer
        try:
            quarters = self.fmp.statements(ticker, "quarter", QUARTERS)
        except SourceUnavailable as exc:
            notes.append(f"Quarterly statements not available: {exc}")
        cap = getattr(self.fmp, "period_cap", None)
        if cap and sources.get("statements") == source:
            notes.append(f"The data plan gives {cap} periods of statements: {cap} years and {cap} quarters instead of "
                         f"{ANNUAL_YEARS} and {QUARTERS}.")
        depth = getattr(self.fmp, "depth_note", None)
        if depth and sources.get("statements") == source:
            notes.append(depth)

        yield {"step": "prices", "detail": f"{PRICE_YEARS} years of daily prices for {ticker} and {BENCHMARK}"}
        start = (date.today() - timedelta(days=365 * PRICE_YEARS + 10)).isoformat()
        bars: list[dict] = []
        bench: list[dict] = []
        try:
            bars = self.fmp.prices(ticker, start)
            bench = self.benchmark(start)
            sources["prices"] = source
        except SourceUnavailable as exc:
            notes.append(f"Prices not available: {exc}")
        if bars and profile.get("price") is None:
            profile["price"] = bars[-1]["close"]

        yield {"step": "estimates", "detail": "Analyst consensus for the coming fiscal years"}
        estimates: list[dict] = []
        try:
            estimates = self.fmp.estimates(ticker)
            sources["estimates"] = source
        except SourceUnavailable as exc:
            notes.append(f"Analyst estimates not available: {exc}")

        yield {"step": "compute", "detail": "Ratios, multiples and indicators"}
        t = metrics.ttm(quarters, annual)
        current = metrics.current_multiples(profile, t)
        history = metrics.historical_multiples(annual, bars)
        report = {
            "version": REPORT_VERSION,
            "built_utc": _now().isoformat(timespec="seconds"),
            "ticker": ticker,
            "profile": profile,
            "sources": sources,
            "notes": notes,
            "annual": annual,
            "quarters": quarters,
            "annual_ratios": metrics.period_ratios(annual),
            "quarter_ratios": metrics.period_ratios(quarters),
            "ttm": t,
            "valuation": current,
            "history": history,
            "forward": forward_multiples(estimates, annual, current, history),
            "growth": _growth_summary(annual),
            "technical": technical.analyse(bars, bench),
        }
        self.store.put(f"report/{ticker}", report)
        yield {"step": "done", "report": report}

    def benchmark(self, start: str) -> list[dict]:
        key = f"prices/{BENCHMARK}"
        cached = self.store.get(key)
        if _fresh(cached):
            return cached["bars"]
        bars = self.fmp.prices(BENCHMARK, start)
        self.store.put(key, {"version": REPORT_VERSION, "built_utc": _now().isoformat(timespec="seconds"), "bars": bars})
        return bars


def _growth_summary(annual: list[dict]) -> dict:
    """Compound growth over 3, 5 and 10 years for the main lines."""
    out = {}
    for field in ("revenue", "eps_diluted", "free_cash_flow", "net_income"):
        out[field] = {}
        for years in (3, 5, 10):
            if len(annual) > years:
                out[field][f"{years}y"] = metrics.cagr(annual[-1].get(field), annual[-1 - years].get(field), years)
            else:
                out[field][f"{years}y"] = None
    return out


def compact(report: dict) -> dict:
    """The numbers the comparison and the AI reading need, without the chart series."""
    tech = report["technical"].get("summary", {}) if report["technical"].get("available") else {}
    last = report["annual_ratios"][-1] if report["annual_ratios"] else {}
    fwd = report["forward"]
    p = report["profile"]
    return {
        "ticker": report["ticker"],
        "name": p.get("name"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "price": report["valuation"].get("price"),
        "market_cap": report["valuation"].get("market_cap"),
        "ttm": {k: report["ttm"].get(k) for k in ("revenue", "operating_income", "net_income", "free_cash_flow",
                                                  "eps_diluted", "source_period")},
        "last_fiscal_year": last.get("fiscal_year"),
        "margins": {k: last.get(k) for k in ("gross_margin", "operating_margin", "net_margin", "fcf_margin")},
        "returns": {k: last.get(k) for k in ("roe", "roic")},
        "balance": {k: last.get(k) for k in ("net_debt", "net_debt_to_ebitda", "current_ratio", "interest_coverage")},
        "growth": report["growth"],
        "valuation": {k: report["valuation"].get(k) for k in ("pe", "ev_ebitda", "ev_sales", "p_fcf", "p_book",
                                                              "fcf_yield", "dividend_yield", "shareholder_yield")},
        "history_median": {k: (report["history"]["summary"].get(k) or {}).get("median")
                           for k in ("pe", "ev_ebitda", "ev_sales", "p_fcf")},
        "forward": {
            "available": fwd.get("available", False),
            "years": [{k: y.get(k) for k in ("fiscal_year", "pe", "ev_ebitda", "ev_sales", "eps_growth",
                                             "revenue_growth", "analysts")} for y in fwd.get("years", [])],
            "eps_cagr": fwd.get("eps_cagr"),
            "peg": fwd.get("peg"),
        },
        "technical": {k: tech.get(k) for k in ("return_1m", "return_3m", "return_1y", "return_ytd", "vs_sma200",
                                               "rsi14", "from_high_52w", "volatility_1y", "beta_1y",
                                               "max_drawdown_1y", "relative_1y")},
        "technical_states": [s["label"] for s in tech.get("states", [])],
    }

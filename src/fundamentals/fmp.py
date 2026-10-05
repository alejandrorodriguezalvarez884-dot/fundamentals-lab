"""Financial Modeling Prep (stable API): profile, statements, prices and analyst estimates.

Every function returns plain dicts in this project's own field names (see ``statements.py``), so
the rest of the code never sees FMP's names. The API key goes as a query parameter and is never
logged.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .config import FMP_BASE
from .http import UpstreamError, get_json


class FmpUnavailable(Exception):
    """No FMP key, or the plan does not include what was asked."""


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def _first(row: dict, *keys: str) -> float | None:
    """The first of ``keys`` present in ``row`` with a number. FMP renamed some fields over
    time, so a few lines accept more than one name."""
    for key in keys:
        if key in row and row[key] is not None:
            value = _num(row[key])
            if value is not None:
                return value
    return None


def _positive(value: float | None) -> float | None:
    """Cash out (capex, dividends, buybacks) as a positive amount, whatever sign FMP used."""
    return None if value is None else abs(value)


# The free plan answers statements only up to this many periods; asking for more is refused.
BASIC_PLAN_PERIODS = 5


class FmpClient:
    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("FMP_API_KEY", "").strip()
        # Set once the plan has refused a longer history and answered a shorter one: later
        # companies ask for that many periods straight away.
        self.period_cap: int | None = None
        self.client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, **params: Any) -> Any:
        if not self.api_key:
            raise FmpUnavailable("FMP_API_KEY is not set.")
        try:
            return get_json(f"{FMP_BASE}/{path}", source="FMP", params={**params, "apikey": self.api_key},
                            client=self.client)
        except UpstreamError as exc:
            # 402 and 403 are FMP's "not in your plan" answers.
            if exc.status in (401, 402, 403):
                raise FmpUnavailable(f"FMP refused {path} ({exc.status}).") from None
            raise

    # --- Search and profile ----------------------------------------------------------------

    def search(self, query: str, limit: int = 10) -> list[dict]:
        rows: list[dict] = []
        for path in ("search-symbol", "search-name"):
            found = self._get(path, query=query, limit=limit) or []
            rows.extend(found)
        out, seen = [], set()
        for row in rows:
            symbol = (row.get("symbol") or "").upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            out.append({"ticker": symbol, "name": row.get("name") or symbol,
                        "exchange": row.get("exchange") or row.get("exchangeShortName") or ""})
        return out[:limit]

    def profile(self, ticker: str) -> dict:
        rows = self._get("profile", symbol=ticker) or []
        if not rows:
            return {}
        row = rows[0]
        return {
            "ticker": (row.get("symbol") or ticker).upper(),
            "name": row.get("companyName") or ticker,
            "price": _num(row.get("price")),
            "change_pct": _first(row, "changePercentage", "changesPercentage"),
            "market_cap": _first(row, "marketCap", "mktCap"),
            "beta": _num(row.get("beta")),
            "currency": row.get("currency") or "USD",
            "exchange": row.get("exchange") or row.get("exchangeShortName") or "",
            "sector": row.get("sector") or "",
            "industry": row.get("industry") or "",
            "country": row.get("country") or "",
            "employees": _num(row.get("fullTimeEmployees")),
            "ceo": row.get("ceo") or "",
            "website": row.get("website") or "",
            "description": row.get("description") or "",
            "ipo_date": row.get("ipoDate") or "",
            "cik": row.get("cik") or "",
            "is_etf": bool(row.get("isEtf")),
        }

    # --- Statements ------------------------------------------------------------------------

    def statements(self, ticker: str, period: str, limit: int) -> list[dict]:
        """Income, balance sheet and cash flow merged by period end, oldest first.
        ``period`` is ``annual`` or ``quarter``."""
        limit = min(limit, self.period_cap or limit)
        try:
            income = self._get("income-statement", symbol=ticker, period=period, limit=limit) or []
        except FmpUnavailable:
            if limit <= BASIC_PLAN_PERIODS:
                raise
            limit = BASIC_PLAN_PERIODS
            income = self._get("income-statement", symbol=ticker, period=period, limit=limit) or []
            self.period_cap = limit
        balance = self._get("balance-sheet-statement", symbol=ticker, period=period, limit=limit) or []
        cash = self._get("cash-flow-statement", symbol=ticker, period=period, limit=limit) or []
        by_date: dict[str, dict] = {}
        for row in income:
            by_date.setdefault(row["date"], {}).update(_income(row))
        for row in balance:
            if row.get("date") in by_date:
                by_date[row["date"]].update(_balance(row))
        for row in cash:
            if row.get("date") in by_date:
                by_date[row["date"]].update(_cash_flow(row))
        return [by_date[d] for d in sorted(by_date)]

    # --- Prices ----------------------------------------------------------------------------

    def prices(self, ticker: str, start: str) -> list[dict]:
        """Daily bars from ``start`` (YYYY-MM-DD), oldest first."""
        data = self._get("historical-price-eod/full", symbol=ticker, **{"from": start})
        rows = data.get("historical", []) if isinstance(data, dict) else (data or [])
        bars = []
        for row in rows:
            close = _first(row, "adjClose", "close")
            if close is None or not row.get("date"):
                continue
            # Scale open/high/low by the same adjustment as the close, so splits don't leave gaps.
            raw_close = _num(row.get("close")) or close
            k = close / raw_close if raw_close else 1.0
            bars.append({
                "date": row["date"][:10],
                "open": (_num(row.get("open")) or raw_close) * k,
                "high": (_num(row.get("high")) or raw_close) * k,
                "low": (_num(row.get("low")) or raw_close) * k,
                "close": close,
                "volume": _num(row.get("volume")) or 0.0,
            })
        bars.sort(key=lambda b: b["date"])
        return bars

    # --- Analyst estimates -----------------------------------------------------------------

    def estimates(self, ticker: str, limit: int = 10) -> list[dict]:
        """Annual consensus estimates, oldest first."""
        rows = self._get("analyst-estimates", symbol=ticker, period="annual", page=0, limit=limit) or []
        out = []
        for row in rows:
            out.append({
                "date": row.get("date", "")[:10],
                "revenue_avg": _first(row, "revenueAvg", "estimatedRevenueAvg"),
                "revenue_low": _first(row, "revenueLow", "estimatedRevenueLow"),
                "revenue_high": _first(row, "revenueHigh", "estimatedRevenueHigh"),
                "ebitda_avg": _first(row, "ebitdaAvg", "estimatedEbitdaAvg"),
                "ebit_avg": _first(row, "ebitAvg", "estimatedEbitAvg"),
                "net_income_avg": _first(row, "netIncomeAvg", "estimatedNetIncomeAvg"),
                "eps_avg": _first(row, "epsAvg", "estimatedEpsAvg"),
                "eps_low": _first(row, "epsLow", "estimatedEpsLow"),
                "eps_high": _first(row, "epsHigh", "estimatedEpsHigh"),
                "analysts_eps": _first(row, "numAnalystsEps", "numberAnalystsEstimatedEps"),
                "analysts_revenue": _first(row, "numAnalystsRevenue", "numberAnalystEstimatedRevenue"),
            })
        out = [r for r in out if r["date"]]
        out.sort(key=lambda r: r["date"])
        return out


def _income(row: dict) -> dict:
    return {
        "date": row["date"][:10],
        "fiscal_year": str(row.get("fiscalYear") or row.get("calendarYear") or row["date"][:4]),
        "period": row.get("period") or "FY",
        "currency": row.get("reportedCurrency") or "USD",
        "filing_date": (row.get("filingDate") or row.get("fillingDate") or "")[:10],
        "revenue": _first(row, "revenue"),
        "cost_of_revenue": _first(row, "costOfRevenue"),
        "gross_profit": _first(row, "grossProfit"),
        "rnd": _first(row, "researchAndDevelopmentExpenses"),
        "sga": _first(row, "sellingGeneralAndAdministrativeExpenses"),
        "operating_income": _first(row, "operatingIncome"),
        "interest_expense": _positive(_first(row, "interestExpense")),
        "pretax_income": _first(row, "incomeBeforeTax"),
        "income_tax": _first(row, "incomeTaxExpense"),
        "net_income": _first(row, "netIncome"),
        "ebitda": _first(row, "ebitda"),
        "d_and_a": _first(row, "depreciationAndAmortization"),
        "eps": _first(row, "eps"),
        "eps_diluted": _first(row, "epsDiluted", "epsdiluted"),
        "shares_diluted": _first(row, "weightedAverageShsOutDil", "weightedAverageShsOut"),
    }


def _balance(row: dict) -> dict:
    return {
        "cash": _first(row, "cashAndCashEquivalents"),
        "short_term_investments": _first(row, "shortTermInvestments"),
        "receivables": _first(row, "netReceivables"),
        "inventory": _first(row, "inventory"),
        "total_current_assets": _first(row, "totalCurrentAssets"),
        "total_assets": _first(row, "totalAssets"),
        "goodwill_intangibles": _first(row, "goodwillAndIntangibleAssets"),
        "total_current_liabilities": _first(row, "totalCurrentLiabilities"),
        "total_liabilities": _first(row, "totalLiabilities"),
        "total_debt": _first(row, "totalDebt"),
        "total_equity": _first(row, "totalStockholdersEquity", "totalEquity"),
    }


def _cash_flow(row: dict) -> dict:
    ocf = _first(row, "operatingCashFlow", "netCashProvidedByOperatingActivities")
    capex = _positive(_first(row, "capitalExpenditure", "investmentsInPropertyPlantAndEquipment"))
    fcf = _first(row, "freeCashFlow")
    if fcf is None and ocf is not None and capex is not None:
        fcf = ocf - capex
    return {
        "operating_cash_flow": ocf,
        "capex": capex,
        "free_cash_flow": fcf,
        "dividends_paid": _positive(_first(row, "commonDividendsPaid", "dividendsPaid", "netDividendsPaid")),
        "buybacks": _positive(_first(row, "commonStockRepurchased")),
        "sbc": _first(row, "stockBasedCompensation"),
    }

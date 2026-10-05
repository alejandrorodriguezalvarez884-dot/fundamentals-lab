"""SEC EDGAR: the company list behind the search, and XBRL facts as a fallback for statements.

Both are free and official. The facts only cover US filers and only the lines below, so they are
the fallback when FMP is not available, not the main source.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date

import httpx

from .config import SEC_COMPANYFACTS_URL, SEC_RPS, SEC_TICKERS_URL
from .http import RateLimiter, get_json

_limiter = RateLimiter(SEC_RPS)


def _headers() -> dict[str, str]:
    agent = os.environ.get("SEC_USER_AGENT", "").strip() or "fundamentals-lab contact@example.com"
    return {"User-Agent": agent, "Accept-Encoding": "gzip, deflate"}


def sec_get(url: str, client: httpx.Client | None = None):
    return get_json(url, source="SEC", headers=_headers(), limiter=_limiter, client=client)


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    cik: int


class UnknownCompany(Exception):
    pass


def _norm(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\b(inc|corp|corporation|co|company|ltd|plc|holdings?|group|the|class [a-z])\b", " ", text)
    return " ".join(text.split())


class Directory:
    """Search by ticker or by name over the SEC list of listed companies.

    The list is downloaded once and refreshed every day. Tests pass ``companies`` directly.
    """

    def __init__(self, companies: list[Company] | None = None, client: httpx.Client | None = None,
                 ttl_seconds: float = 86400):
        self._companies = companies
        self._loaded_at = time.monotonic() if companies is not None else 0.0
        self._fixed = companies is not None
        self._client = client
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def _all(self) -> list[Company]:
        with self._lock:
            stale = time.monotonic() - self._loaded_at > self._ttl
            if self._companies is None or (stale and not self._fixed):
                data = sec_get(SEC_TICKERS_URL, self._client)
                rows = data.values() if isinstance(data, dict) else data
                seen, companies = set(), []
                for row in rows:
                    ticker = str(row["ticker"]).upper()
                    if ticker in seen:
                        continue
                    seen.add(ticker)
                    companies.append(Company(ticker, str(row["title"]), int(row["cik_str"])))
                self._companies, self._loaded_at = companies, time.monotonic()
            return self._companies

    def get(self, ticker: str) -> Company:
        wanted = ticker.strip().upper().replace(".", "-")
        for company in self._all():
            if company.ticker == wanted:
                return company
        raise UnknownCompany(ticker)

    def search(self, query: str, limit: int = 8) -> list[Company]:
        """Exact ticker first, then tickers that start with the query, then names.

        The SEC list is ordered roughly by size, so within each group the bigger companies come
        first, which is what someone typing "app" most likely wants."""
        q = query.strip()
        if not q:
            return []
        q_ticker = q.upper().replace(".", "-")
        q_name = _norm(q)
        exact, prefix, name_start, name_word, name_in = [], [], [], [], []
        for company in self._all():
            name = _norm(company.name)
            if company.ticker == q_ticker:
                exact.append(company)
            elif company.ticker.startswith(q_ticker) and len(q_ticker) >= 1 and q_ticker.isalnum():
                prefix.append(company)
            elif q_name and name.startswith(q_name):
                name_start.append(company)
            elif q_name and f" {q_name}" in f" {name}":
                name_word.append(company)
            elif q_name and len(q_name) >= 3 and q_name in name:
                name_in.append(company)
        # A short query is more often the start of a name than of a ticker ("micro" -> Microsoft).
        groups = [exact, name_start, prefix, name_word, name_in] if len(q) > 4 else \
                 [exact, prefix, name_start, name_word, name_in]
        out: list[Company] = []
        for group in groups:
            for company in group:
                if company not in out:
                    out.append(company)
                if len(out) >= limit:
                    return out
        return out


# --- XBRL facts: a minimal fallback for annual statements -------------------------------------

# Each line, with the us-gaap tags that may carry it, in order of preference.
_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "income_tax": ("IncomeTaxExpenseBenefit",),
    "net_income": ("NetIncomeLoss",),
    "rnd": ("ResearchAndDevelopmentExpense",),
    "interest_expense": ("InterestExpense",),
    "d_and_a": ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization"),
    "eps_diluted": ("EarningsPerShareDiluted",),
    "shares_diluted": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "short_term_investments": ("ShortTermInvestments", "MarketableSecuritiesCurrent"),
    "total_current_assets": ("AssetsCurrent",),
    "total_assets": ("Assets",),
    "total_current_liabilities": ("LiabilitiesCurrent",),
    "total_liabilities": ("Liabilities",),
    "total_equity": ("StockholdersEquity",),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "short_term_debt": ("LongTermDebtCurrent", "DebtCurrent"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "dividends_paid": ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
    "buybacks": ("PaymentsForRepurchaseOfCommonStock",),
    "sbc": ("ShareBasedCompensation",),
}
_INSTANT = {"cash", "short_term_investments", "total_current_assets", "total_assets",
            "total_current_liabilities", "total_liabilities", "total_equity", "long_term_debt", "short_term_debt"}


def annual_from_facts(facts: dict, years: int = 10) -> list[dict]:
    """Annual statements from a companyfacts document, oldest first.

    Only values from 10-K filings are used. A flow (revenue, cash flow...) must span about a
    year; a balance (cash, debt...) is taken at the fiscal year end. When a later 10-K restates
    a year, the later filing wins."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    by_end: dict[str, dict] = {}
    for line, tags in _TAGS.items():
        for tag in tags:
            units = gaap.get(tag, {}).get("units", {})
            values = units.get("USD") or units.get("USD/shares") or units.get("shares") or []
            picked: dict[str, tuple[str, float]] = {}
            for v in values:
                if not str(v.get("form", "")).startswith("10-K") or v.get("fp") != "FY":
                    continue
                end = v.get("end")
                if not end:
                    continue
                if line not in _INSTANT:
                    start = v.get("start")
                    if not start:
                        continue
                    if not 350 <= _days(start, end) <= 380:
                        continue
                filed = v.get("filed", "")
                if end not in picked or filed > picked[end][0]:
                    picked[end] = (filed, float(v["val"]))
            # Companies switch tags over the years (Revenues -> RevenueFromContract...): merge
            # them, keeping the preferred tag where both report the same year.
            for end, (_, val) in picked.items():
                by_end.setdefault(end, {}).setdefault(line, val)
    rows = []
    for end in sorted(by_end):
        row = by_end[end]
        if row.get("revenue") is None and row.get("net_income") is None:
            continue
        debt = (row.pop("long_term_debt", None) or 0.0) + (row.pop("short_term_debt", None) or 0.0)
        row["total_debt"] = debt or None
        ocf, capex = row.get("operating_cash_flow"), row.get("capex")
        row["free_cash_flow"] = ocf - capex if ocf is not None and capex is not None else None
        if row.get("operating_income") is not None and row.get("d_and_a") is not None:
            row["ebitda"] = row["operating_income"] + row["d_and_a"]
        rows.append({"date": end, "fiscal_year": end[:4], "period": "FY", "currency": "USD", **row})
    return rows[-years:]


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


def fetch_annual(cik: int, years: int = 10, client: httpx.Client | None = None) -> list[dict]:
    return annual_from_facts(sec_get(SEC_COMPANYFACTS_URL.format(cik=cik), client), years)

"""Yahoo Finance, read with the yfinance library: profile, statements, prices and analyst estimates.

The same four answers as ``fmp.FmpClient``, in this project's own field names. It takes no key
and has no daily quota, but it is not an official API: yfinance asks the addresses Yahoo's own
pages ask, and Yahoo can refuse an address that asks too much. Yahoo gives four fiscal years and
five quarters of statements, and the consensus for the fiscal year under way and the next one.
Nothing is sent to Yahoo but the ticker.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .fmp import FmpClient, SourceUnavailable

log = logging.getLogger("fundamentals.yahoo")

INFO_TTL_SECONDS = 600


class YahooUnavailable(SourceUnavailable):
    """Yahoo did not answer, or has nothing for what was asked."""


# This project's line -> Yahoo's names for it, in order of preference.
_INCOME = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "cost_of_revenue": ("Cost Of Revenue", "Reconciled Cost Of Revenue"),
    "gross_profit": ("Gross Profit",),
    "rnd": ("Research And Development",),
    "sga": ("Selling General And Administration",),
    "operating_income": ("Operating Income", "Total Operating Income As Reported"),
    "interest_expense": ("Interest Expense", "Interest Expense Non Operating"),
    "pretax_income": ("Pretax Income",),
    "income_tax": ("Tax Provision",),
    "net_income": ("Net Income", "Net Income Common Stockholders"),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "d_and_a": ("Reconciled Depreciation", "Depreciation And Amortization In Income Statement"),
    "eps": ("Basic EPS",),
    "eps_diluted": ("Diluted EPS",),
    "shares_diluted": ("Diluted Average Shares", "Basic Average Shares"),
}
_BALANCE = {
    "cash": ("Cash And Cash Equivalents",),
    "short_term_investments": ("Other Short Term Investments",),
    "receivables": ("Receivables", "Accounts Receivable"),
    "inventory": ("Inventory",),
    "total_current_assets": ("Current Assets",),
    "total_assets": ("Total Assets",),
    "goodwill_intangibles": ("Goodwill And Other Intangible Assets",),
    "total_current_liabilities": ("Current Liabilities",),
    "total_liabilities": ("Total Liabilities Net Minority Interest",),
    "total_debt": ("Total Debt",),
    "total_equity": ("Stockholders Equity", "Common Stock Equity"),
}
_CASH = {
    "operating_cash_flow": ("Operating Cash Flow",),
    "capex": ("Capital Expenditure",),
    "free_cash_flow": ("Free Cash Flow",),
    "dividends_paid": ("Cash Dividends Paid", "Common Stock Dividend Paid"),
    "buybacks": ("Repurchase Of Capital Stock",),
    "sbc": ("Stock Based Compensation",),
}
# Cash out, as a positive amount whatever sign Yahoo gives it.
_OUTFLOWS = ("interest_expense", "capex", "dividends_paid", "buybacks")


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # NaN is how a table says "nothing here"


def _table(frame) -> dict[str, dict[str, float]]:
    """A statement of yfinance (a column per period end, a row per line) by period end."""
    if frame is None or getattr(frame, "empty", True):
        return {}
    out: dict[str, dict[str, float]] = {}
    for column in frame.columns:
        values = {str(line): _num(v) for line, v in frame[column].items()}
        out[column.strftime("%Y-%m-%d")] = {k: v for k, v in values.items() if v is not None}
    return out


def _lines(values: dict[str, float], names: dict[str, tuple[str, ...]]) -> dict[str, float | None]:
    out = {line: next((values[n] for n in yahoo if n in values), None) for line, yahoo in names.items()}
    return {k: abs(v) if v is not None and k in _OUTFLOWS else v for k, v in out.items()}


def _cell(frame, row: str, column: str) -> float | None:
    try:
        return _num(frame.loc[row, column])
    except (KeyError, AttributeError, TypeError):
        return None


def _day(epoch: Any) -> date | None:
    seconds = _num(epoch)
    # Counted from 1970 by hand: a date before it (a share first traded in 1919) is a negative
    # number of seconds, which not every system turns into a date.
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).date() if seconds else None


def _a_year_on(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


class YahooClient:
    name = "Yahoo Finance"
    configured = True
    period_cap = None
    # What the report says when the statements are Yahoo's: it asks for more history than there is.
    depth_note = "Yahoo Finance gives four fiscal years and five quarters of statements."

    def __init__(self, yf=None):
        self._yf = yf  # the yfinance module; tests pass a stand-in
        self._infos: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    @property
    def yf(self):
        with self._lock:
            if self._yf is None:
                import yfinance  # slow to import (pandas): only when the first report is built

                try:
                    yfinance.config.debug.hide_exceptions = False  # a missing ticker raises instead of printing
                except AttributeError:
                    pass
                self._yf = yfinance
            return self._yf

    def _ask(self, what: str, ask):
        try:
            got = ask()
        except Exception as exc:  # yfinance raises its own errors and those of the HTTP library under it
            # The error's name only: its text can carry the address that was asked.
            log.warning("yahoo %s -> %s", what, type(exc).__name__)
            raise YahooUnavailable("Yahoo Finance did not answer.") from None
        log.info("yahoo %s -> ok", what)
        return got

    def _info(self, ticker: str) -> dict:
        hit = self._infos.get(ticker)
        if hit and time.monotonic() - hit[0] < INFO_TTL_SECONDS:
            return hit[1]
        info = self._ask(f"info {ticker}", lambda: dict(self.yf.Ticker(ticker).info or {}))
        self._infos[ticker] = (time.monotonic(), info)
        return info

    # --- Profile ---------------------------------------------------------------------------

    def profile(self, ticker: str) -> dict:
        info = self._info(ticker)
        name = info.get("longName") or info.get("shortName")
        if not name:
            return {}
        boss = next((o.get("name") for o in info.get("companyOfficers") or [] if "CEO" in str(o.get("title") or "")), "")
        first_trade = _day((_num(info.get("firstTradeDateMilliseconds")) or 0) / 1000)
        return {
            "ticker": ticker.upper(), "name": name,
            "price": _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice")),
            "change_pct": _num(info.get("regularMarketChangePercent")),
            "market_cap": _num(info.get("marketCap")), "beta": _num(info.get("beta")),
            "currency": info.get("currency") or "USD",
            "exchange": info.get("fullExchangeName") or info.get("exchange") or "",
            "sector": info.get("sector") or "", "industry": info.get("industry") or "", "country": info.get("country") or "",
            "employees": _num(info.get("fullTimeEmployees")), "ceo": boss or "", "website": info.get("website") or "",
            "description": info.get("longBusinessSummary") or "",
            "ipo_date": first_trade.isoformat() if first_trade else "", "cik": "",
            "is_etf": str(info.get("quoteType") or "").upper() in ("ETF", "MUTUALFUND"),
        }

    # --- Statements ------------------------------------------------------------------------

    def statements(self, ticker: str, period: str, limit: int) -> list[dict]:
        """Income, balance sheet and cash flow merged by period end, oldest first.
        ``period`` is ``annual`` or ``quarter``."""
        t = self.yf.Ticker(ticker)
        annual = period == "annual"
        income = _table(self._ask(f"income {period} {ticker}", lambda: t.income_stmt if annual else t.quarterly_income_stmt))
        if not income:
            raise YahooUnavailable("Yahoo Finance has no statements for this company.")
        balance = _table(self._ask(f"balance {period} {ticker}", lambda: t.balance_sheet if annual else t.quarterly_balance_sheet))
        cash = _table(self._ask(f"cash flow {period} {ticker}", lambda: t.cashflow if annual else t.quarterly_cashflow))
        try:
            info = self._info(ticker)
        except YahooUnavailable:
            info = {}
        year_end = _day(info.get("lastFiscalYearEnd"))
        # The month the fiscal year ends in places each quarter in its fiscal year.
        end_month = year_end.month if year_end else 12
        rows = []
        for day in sorted(income)[-limit:]:
            when = date.fromisoformat(day)
            if annual:
                fiscal_year, label = when.year, "FY"
            else:
                fiscal_year = when.year if when.month <= end_month else when.year + 1
                label = f"Q{round(((when.month - end_month) % 12) / 3) % 4 or 4}"
            row = {"date": day, "fiscal_year": str(fiscal_year), "period": label, "currency": info.get("financialCurrency") or "USD",
                   "filing_date": "", **_lines(income[day], _INCOME), **_lines(balance.get(day, {}), _BALANCE),
                   **_lines(cash.get(day, {}), _CASH)}
            if row["revenue"] is None and row["net_income"] is None:
                continue  # Yahoo sometimes lists an older period with nothing in it
            if row["free_cash_flow"] is None and row["operating_cash_flow"] is not None and row["capex"] is not None:
                row["free_cash_flow"] = row["operating_cash_flow"] - row["capex"]
            rows.append(row)
        return rows

    def splits(self, ticker: str) -> list[tuple[str, float]]:
        """Every split of the share: its day and how many new shares one old share became."""
        series = self._ask(f"splits {ticker}", lambda: self.yf.Ticker(ticker).splits)
        if series is None or getattr(series, "empty", True):
            return []
        return [(stamp.strftime("%Y-%m-%d"), float(ratio)) for stamp, ratio in series.items()]

    # --- Prices ----------------------------------------------------------------------------

    def prices(self, ticker: str, start: str) -> list[dict]:
        """Daily bars from ``start`` (YYYY-MM-DD), oldest first, adjusted for splits and dividends."""
        frame = self._ask(f"prices {ticker}", lambda: self.yf.Ticker(ticker).history(start=start, interval="1d", auto_adjust=True, actions=False))
        if frame is None or getattr(frame, "empty", True):
            raise YahooUnavailable("Yahoo Finance has no prices for this company.")
        columns = [frame[c].tolist() for c in ("Open", "High", "Low", "Close", "Volume")]
        bars = []
        for stamp, o, h, lo, c, v in zip(frame.index, *columns):
            close = _num(c)
            if close is None:
                continue
            bars.append({"date": stamp.strftime("%Y-%m-%d"), "open": _num(o) or close, "high": _num(h) or close,
                         "low": _num(lo) or close, "close": close, "volume": _num(v) or 0.0})
        return bars

    # --- Analyst estimates -----------------------------------------------------------------

    def estimates(self, ticker: str, limit: int = 10) -> list[dict]:
        """Annual consensus estimates, oldest first: the fiscal year under way and the next one."""
        t = self.yf.Ticker(ticker)
        eps = self._ask(f"eps estimates {ticker}", lambda: t.earnings_estimate)
        revenue = self._ask(f"revenue estimates {ticker}", lambda: t.revenue_estimate)
        info = self._info(ticker)
        # The year under way ends on the date Yahoo gives; without it, a year after the last one closed.
        closes = _day(info.get("nextFiscalYearEnd"))
        if not closes and _day(info.get("lastFiscalYearEnd")):
            closes = _a_year_on(_day(info.get("lastFiscalYearEnd")), 1)
        if not closes:
            return []
        out = []
        for ahead, key in enumerate(("0y", "+1y")):
            row = {
                "date": _a_year_on(closes, ahead).isoformat(),
                "revenue_avg": _cell(revenue, key, "avg"), "revenue_low": _cell(revenue, key, "low"), "revenue_high": _cell(revenue, key, "high"),
                # Yahoo publishes the consensus for sales and for earnings per share, nothing else.
                "ebitda_avg": None, "ebit_avg": None, "net_income_avg": None,
                "eps_avg": _cell(eps, key, "avg"), "eps_low": _cell(eps, key, "low"), "eps_high": _cell(eps, key, "high"),
                "analysts_eps": _cell(eps, key, "numberOfAnalysts"), "analysts_revenue": _cell(revenue, key, "numberOfAnalysts"),
            }
            if row["eps_avg"] is not None or row["revenue_avg"] is not None:
                out.append(row)
        return out[:limit]


def default_source():
    """The source of profiles, statements, prices and estimates. MARKET_DATA names it: "yahoo"
    (the default) or "fmp"."""
    if os.environ.get("MARKET_DATA", "yahoo").strip().lower() == "fmp":
        return FmpClient()
    return YahooClient()

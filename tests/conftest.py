"""Synthetic data shaped like the providers' answers, so no test needs the network."""

from __future__ import annotations

import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from fundamentals.sec import Company, Directory
from fundamentals.store import MemoryStore

COMPANIES = [
    Company("AAPL", "Apple Inc.", 320193),
    Company("MSFT", "MICROSOFT CORP", 789019),
    Company("GOOGL", "Alphabet Inc.", 1652044),
    Company("APP", "AppLovin Corp", 1751008),
    Company("BRK-B", "BERKSHIRE HATHAWAY INC", 1067983),
]


def make_bars(days: int = 1300, start: float = 100.0, drift: float = 0.0004, seed: int = 1) -> list[dict]:
    """Business-day bars with a gentle trend and a deterministic wiggle."""
    bars, price, d = [], start, date.today() - timedelta(days=int(days * 1.45))
    i = 0
    while len(bars) < days:
        d += timedelta(days=1)
        if d.weekday() >= 5:
            continue
        i += 1
        price *= 1 + drift + 0.012 * math.sin(i * 0.37 + seed) + 0.006 * math.cos(i * 1.7 + seed)
        bars.append({"date": d.isoformat(), "open": price * 0.997, "high": price * 1.01,
                     "low": price * 0.99, "close": price, "volume": 1_000_000 + 1000 * (i % 50)})
    return bars


def make_annual(years: int = 6, revenue0: float = 100e9, growth: float = 0.08, end_month_day: str = "09-30") -> list[dict]:
    rows = []
    this_year = date.today().year
    for k in range(years):
        y = this_year - years + k
        rev = revenue0 * (1 + growth) ** k
        ni = rev * 0.25
        rows.append({
            "date": f"{y}-{end_month_day}", "fiscal_year": str(y), "period": "FY", "currency": "USD",
            "revenue": rev, "cost_of_revenue": rev * 0.55, "gross_profit": rev * 0.45, "rnd": rev * 0.07,
            "sga": rev * 0.06, "operating_income": rev * 0.30, "interest_expense": 2e9, "pretax_income": rev * 0.30,
            "income_tax": rev * 0.05, "net_income": ni, "ebitda": rev * 0.34, "d_and_a": rev * 0.04,
            "eps": ni / 15e9, "eps_diluted": ni / 15.2e9, "shares_diluted": 15.2e9,
            "cash": 30e9, "short_term_investments": 20e9, "total_current_assets": 140e9, "total_assets": 350e9,
            "total_current_liabilities": 130e9, "total_liabilities": 280e9, "total_debt": 100e9,
            "total_equity": 70e9, "operating_cash_flow": rev * 0.30, "capex": rev * 0.03,
            "free_cash_flow": rev * 0.27, "dividends_paid": 15e9, "buybacks": 80e9, "sbc": rev * 0.03,
        })
    return rows


def make_quarters(annual: list[dict], n: int = 8) -> list[dict]:
    """Each fiscal year split into four equal quarters."""
    flows = ("revenue", "cost_of_revenue", "gross_profit", "rnd", "sga", "operating_income", "interest_expense",
             "pretax_income", "income_tax", "net_income", "ebitda", "d_and_a", "eps", "eps_diluted",
             "operating_cash_flow", "capex", "free_cash_flow", "dividends_paid", "buybacks", "sbc")
    out = []
    for row in annual[-(n // 4):]:
        y = int(row["date"][:4])
        for q, md in enumerate(("12-31", "03-31", "06-30", "09-30"), start=1):
            yy = y - 1 if q == 1 else y
            qrow = {**row, "date": f"{yy}-{md}", "period": f"Q{q}"}
            for f in flows:
                qrow[f] = row[f] / 4
            out.append(qrow)
    return out


def make_estimates(annual: list[dict], years: int = 3, growth: float = 0.10) -> list[dict]:
    last = annual[-1]
    y = int(last["date"][:4])
    out = []
    for k in range(1, years + 1):
        eps = last["eps_diluted"] * (1 + growth) ** k
        rev = last["revenue"] * (1 + growth * 0.8) ** k
        out.append({"date": f"{y + k}{last['date'][4:]}", "revenue_avg": rev, "revenue_low": rev * 0.95,
                    "revenue_high": rev * 1.05, "ebitda_avg": rev * 0.35, "ebit_avg": rev * 0.31,
                    "net_income_avg": rev * 0.26, "eps_avg": eps, "eps_low": eps * 0.9, "eps_high": eps * 1.1,
                    "analysts_eps": 30, "analysts_revenue": 28})
    return out


class FakeFmp:
    """Stands in for FmpClient with the same method names and the normalised output."""

    def __init__(self, seed_by_ticker: dict[str, int] | None = None, fail: set[str] | None = None):
        self.calls: list[tuple] = []
        self.seed = seed_by_ticker or {}
        self.fail = fail or set()

    def _check(self, what: str):
        if what in self.fail:
            from fundamentals.fmp import FmpUnavailable

            raise FmpUnavailable(f"FMP refused {what} (402).")

    def profile(self, ticker):
        self.calls.append(("profile", ticker))
        self._check("profile")
        bars = self.prices(ticker, "")
        self.calls.pop()
        price = bars[-1]["close"]
        return {"ticker": ticker, "name": f"{ticker} Inc.", "price": price, "market_cap": price * 15e9,
                "sector": "Technology", "industry": "Consumer Electronics", "currency": "USD"}

    def statements(self, ticker, period, limit):
        self.calls.append(("statements", ticker, period))
        self._check(f"statements-{period}")
        annual = make_annual(growth=0.05 + 0.01 * self.seed.get(ticker, 0))
        return annual if period == "annual" else make_quarters(annual)

    def prices(self, ticker, start):
        self.calls.append(("prices", ticker))
        self._check("prices")
        return make_bars(seed=self.seed.get(ticker, 0) + (7 if ticker == "SPY" else 0))

    def estimates(self, ticker, limit=10):
        self.calls.append(("estimates", ticker))
        self._check("estimates")
        return make_estimates(make_annual(growth=0.05 + 0.01 * self.seed.get(ticker, 0)))


class FakeAnthropic:
    """Records the request and answers with a fixed reading."""

    def __init__(self, text: str | None = None, stop_reason: str = "end_turn", model: str = "claude-opus-5-5"):
        self.requests: list[dict] = []
        self.text = text or ('{"headline":"Revenue grew 8% a year.","sections":[{"title":"Business and growth",'
                             '"body":"Revenue grew."}],"points_to_check":["Buybacks exceed free cash flow."]}')
        self.stop_reason = stop_reason
        self.model = model
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.text)],
            stop_reason=self.stop_reason,
            model=self.model,
            usage=SimpleNamespace(input_tokens=4000, output_tokens=1500),
        )


@pytest.fixture
def directory():
    return Directory(companies=list(COMPANIES))


@pytest.fixture
def store():
    return MemoryStore()

"""Yahoo as the source: its tables in this project's own names, no network."""

import pandas as pd
import pytest

from fundamentals.fmp import FmpClient, SourceUnavailable
from fundamentals.report import Reporter
from fundamentals.yahoo import YahooClient, YahooUnavailable, default_source

ANNUAL = ["2022-09-30", "2023-09-30", "2024-09-30", "2025-09-30"]
QUARTERS = ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]


def table(dates, lines):
    """A statement as yfinance gives it: a column per period end, newest first; a row per line."""
    columns = [pd.Timestamp(d) for d in reversed(dates)]
    return pd.DataFrame({c: [values[len(dates) - 1 - i] for values in lines.values()] for i, c in enumerate(columns)}, index=list(lines))


def income(dates, scale=1.0):
    n = len(dates)
    grow = [scale * (100.0 + 10 * i) for i in range(n)]
    return table(dates, {
        "Total Revenue": [g * 1e9 for g in grow], "Cost Of Revenue": [g * 0.55e9 for g in grow], "Gross Profit": [g * 0.45e9 for g in grow],
        "Research And Development": [g * 0.08e9 for g in grow], "Selling General And Administration": [g * 0.07e9 for g in grow],
        "Operating Income": [g * 0.30e9 for g in grow], "Interest Expense": [float("nan")] * (n - 1) + [-2e9],
        "Pretax Income": [g * 0.29e9 for g in grow], "Tax Provision": [g * 0.05e9 for g in grow], "Net Income": [g * 0.24e9 for g in grow],
        "EBITDA": [g * 0.33e9 for g in grow], "Reconciled Depreciation": [g * 0.03e9 for g in grow],
        "Basic EPS": [g * 0.0161 for g in grow], "Diluted EPS": [g * 0.016 for g in grow], "Diluted Average Shares": [15e9] * n})


def balance(dates):
    n = len(dates)
    return table(dates, {"Cash And Cash Equivalents": [30e9] * n, "Other Short Term Investments": [20e9] * n, "Receivables": [25e9] * n,
                         "Inventory": [6e9] * n, "Current Assets": [130e9] * n, "Total Assets": [350e9] * n, "Current Liabilities": [140e9] * n,
                         "Total Liabilities Net Minority Interest": [280e9] * n, "Total Debt": [100e9] * n, "Stockholders Equity": [70e9] * n})


def cash(dates, scale=1.0):
    n = len(dates)
    return table(dates, {"Operating Cash Flow": [scale * 110e9] * n, "Capital Expenditure": [scale * -12e9] * n,
                         "Cash Dividends Paid": [scale * -15e9] * n, "Repurchase Of Capital Stock": [scale * -80e9] * n,
                         "Stock Based Compensation": [scale * 11e9] * n})


class FakeTicker:
    def __init__(self, yf, symbol):
        self.yf, self.symbol = yf, symbol

    def _known(self, what):
        self.yf.calls.append(what)
        if self.yf.down:
            raise RuntimeError("Too Many Requests")
        return self.symbol != "NOPE"

    @property
    def info(self):
        if not self._known("info"):
            return {"trailingPegRatio": None}
        return {"longName": "Apple Inc.", "currentPrice": 333.63, "regularMarketChangePercent": 0.22, "marketCap": 4.87e12, "beta": 1.07,
                "currency": "USD", "financialCurrency": "USD", "fullExchangeName": "NasdaqGS", "sector": "Technology",
                "industry": "Consumer Electronics", "country": "United States", "fullTimeEmployees": 150000, "website": "https://www.apple.com",
                "longBusinessSummary": "Makes phones.", "firstTradeDateMilliseconds": 345479400000, "quoteType": "EQUITY",
                "lastFiscalYearEnd": 1758931200, "nextFiscalYearEnd": 1790467200,  # 2025-09-27 and 2026-09-27
                "companyOfficers": [{"name": "Kevan Parekh", "title": "Senior VP & CFO"}, {"name": "John Ternus", "title": "CEO & Director"}]}

    income_stmt = property(lambda self: income(ANNUAL) if self._known("income") else pd.DataFrame())
    quarterly_income_stmt = property(lambda self: income(QUARTERS, 0.25) if self._known("income") else pd.DataFrame())
    balance_sheet = property(lambda self: balance(ANNUAL) if self._known("balance") else pd.DataFrame())
    quarterly_balance_sheet = property(lambda self: balance(QUARTERS) if self._known("balance") else pd.DataFrame())
    cashflow = property(lambda self: cash(ANNUAL) if self._known("cash") else pd.DataFrame())
    quarterly_cashflow = property(lambda self: cash(QUARTERS, 0.25) if self._known("cash") else pd.DataFrame())

    @property
    def earnings_estimate(self):
        self._known("estimates")
        return pd.DataFrame({"avg": [1.98, 2.91, 8.82, 9.58], "low": [1.93, 2.56, 8.28, 8.69], "high": [2.07, 3.42, 8.94, 10.67],
                             "numberOfAnalysts": [27, 22, 39, 40]}, index=["0q", "+1q", "0y", "+1y"])

    @property
    def revenue_estimate(self):
        return pd.DataFrame({"avg": [1.1e11, 1.5e11, 4.78e11, 5.28e11], "low": [1.1e11, 1.3e11, 4.72e11, 4.98e11],
                             "high": [1.2e11, 1.7e11, 4.84e11, 5.95e11], "numberOfAnalysts": [27, 19, 40, 40]}, index=["0q", "+1q", "0y", "+1y"])

    def history(self, start, interval, auto_adjust, actions):
        self._known("prices")
        assert auto_adjust is True  # adjusted for splits and dividends
        days = pd.bdate_range(end="2026-10-06", periods=600, tz="America/New_York")
        closes = [100.0 + 0.3 * i for i in range(len(days))]
        return pd.DataFrame({"Open": closes, "High": [c + 1 for c in closes], "Low": [c - 1 for c in closes], "Close": closes,
                             "Volume": [1e6] * len(days)}, index=days)


class FakeYf:
    def __init__(self):
        self.calls: list[str] = []
        self.down = False

    def Ticker(self, symbol):  # noqa: N802 (yfinance's name)
        return FakeTicker(self, symbol)


def test_statements_in_this_projects_names():
    y = YahooClient(FakeYf())
    annual = y.statements("AAPL", "annual", 10)
    assert [r["date"] for r in annual] == ANNUAL and {r["period"] for r in annual} == {"FY"}
    last = annual[-1]
    assert last["fiscal_year"] == "2025" and last["revenue"] == 130e9 and last["eps_diluted"] == pytest.approx(2.08)
    assert last["interest_expense"] == 2e9 and annual[0]["interest_expense"] is None  # cash out is positive; a gap stays a gap
    assert last["capex"] == 12e9 and last["dividends_paid"] == 15e9 and last["buybacks"] == 80e9
    assert last["free_cash_flow"] == 98e9  # Yahoo gave none here: operating cash flow less capex
    assert last["total_debt"] == 100e9 and last["total_equity"] == 70e9 and last["goodwill_intangibles"] is None


def test_quarters_sit_in_the_companys_fiscal_year():
    quarters = YahooClient(FakeYf()).statements("AAPL", "quarter", 12)
    # The fiscal year ends in September: the quarter to December opens the next one.
    assert [(q["date"], q["period"], q["fiscal_year"]) for q in quarters] == [
        ("2025-06-30", "Q3", "2025"), ("2025-09-30", "Q4", "2025"), ("2025-12-31", "Q1", "2026"),
        ("2026-03-31", "Q2", "2026"), ("2026-06-30", "Q3", "2026")]


def test_profile_prices_and_estimates():
    y = YahooClient(FakeYf())
    p = y.profile("AAPL")
    assert p["name"] == "Apple Inc." and p["price"] == 333.63 and p["sector"] == "Technology" and p["ceo"] == "John Ternus"
    assert p["ipo_date"] == "1980-12-12" and p["is_etf"] is False and p["employees"] == 150000
    bars = y.prices("AAPL", "2021-01-01")
    assert len(bars) == 600 and bars[-1]["date"] == "2026-10-06" and bars[0]["close"] < bars[-1]["close"]
    estimates = y.estimates("AAPL")
    assert [e["date"] for e in estimates] == ["2026-09-27", "2027-09-27"]  # the year under way and the next
    assert estimates[0]["eps_avg"] == 8.82 and estimates[0]["revenue_avg"] == 4.78e11 and estimates[0]["analysts_eps"] == 39
    assert estimates[0]["ebitda_avg"] is None and estimates[0]["net_income_avg"] is None


def test_what_yahoo_does_not_have_or_does_not_answer():
    y = YahooClient(FakeYf())
    assert y.profile("NOPE") == {}
    with pytest.raises(YahooUnavailable):
        y.statements("NOPE", "annual", 10)
    down = FakeYf()
    down.down = True
    with pytest.raises(SourceUnavailable) as failed:
        YahooClient(down).statements("AAPL", "annual", 10)
    assert "Too Many" not in str(failed.value)  # what the visitor reads carries nothing of the provider's answer


def test_a_report_built_from_yahoo(directory, store):
    report = Reporter(store, YahooClient(FakeYf())).build(directory.get("AAPL"))
    assert set(report["sources"].values()) == {"Yahoo Finance"}
    assert report["notes"] == ["Yahoo Finance gives four fiscal years and five quarters of statements."]
    assert len(report["annual"]) == 4 and len(report["quarters"]) == 5
    assert report["ttm"]["source_period"] == "4 quarters to 2026-06-30" and report["valuation"]["pe"] > 0
    forward = report["forward"]
    assert forward["available"] and [y["fiscal_year"] for y in forward["years"]] == ["2026", "2027"]
    assert forward["years"][0]["pe"] == pytest.approx(333.63 / 8.82) and forward["years"][0]["ev_ebitda"] is None
    assert report["technical"]["available"]


def test_yahoo_is_the_source_unless_the_environment_names_fmp(monkeypatch):
    monkeypatch.delenv("MARKET_DATA", raising=False)
    assert isinstance(default_source(), YahooClient)
    monkeypatch.setenv("MARKET_DATA", "fmp")
    assert isinstance(default_source(), FmpClient)

"""The FMP and SEC parsers, against answers shaped like the real ones."""

import httpx
import pytest

from fundamentals.fmp import FmpClient, FmpUnavailable
from fundamentals.sec import annual_from_facts

INCOME = [
    {"date": "2024-09-28", "symbol": "AAPL", "reportedCurrency": "USD", "fiscalYear": "2024", "period": "FY",
     "filingDate": "2024-11-01", "revenue": 391035000000, "costOfRevenue": 210352000000,
     "grossProfit": 180683000000, "researchAndDevelopmentExpenses": 31370000000,
     "sellingGeneralAndAdministrativeExpenses": 26097000000, "operatingIncome": 123216000000,
     "interestExpense": 0, "incomeBeforeTax": 123485000000, "incomeTaxExpense": 29749000000,
     "netIncome": 93736000000, "ebitda": 134661000000, "depreciationAndAmortization": 11445000000,
     "eps": 6.11, "epsDiluted": 6.08, "weightedAverageShsOutDil": 15408095000},
]
BALANCE = [{"date": "2024-09-28", "cashAndCashEquivalents": 29943000000, "shortTermInvestments": 35228000000,
            "totalCurrentAssets": 152987000000, "totalAssets": 364980000000, "totalCurrentLiabilities": 176392000000,
            "totalLiabilities": 308030000000, "totalDebt": 106629000000, "totalStockholdersEquity": 56950000000}]
CASH = [{"date": "2024-09-28", "operatingCashFlow": 118254000000, "capitalExpenditure": -9447000000,
         "freeCashFlow": 108807000000, "commonDividendsPaid": -15234000000, "commonStockRepurchased": -94949000000,
         "stockBasedCompensation": 11688000000}]
PRICES = [
    {"symbol": "AAPL", "date": "2024-06-11", "open": 193.65, "high": 207.16, "low": 193.63, "close": 207.15, "volume": 172373300},
    {"symbol": "AAPL", "date": "2024-06-10", "open": 196.9, "high": 197.3, "low": 192.15, "close": 193.12, "volume": 97262100},
]
ESTIMATES = [{"symbol": "AAPL", "date": "2026-09-27", "revenueLow": 400e9, "revenueHigh": 460e9, "revenueAvg": 430e9,
              "ebitdaAvg": 150e9, "ebitAvg": 135e9, "netIncomeAvg": 110e9, "epsAvg": 7.4, "epsHigh": 7.9,
              "epsLow": 6.9, "numAnalystsRevenue": 25, "numAnalystsEps": 30}]


def _client(status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["apikey"] == "test-key"
        path = request.url.path.rsplit("/stable/", 1)[1]
        if status != 200:
            return httpx.Response(status, json={"Error Message": "Premium endpoint"})
        body = {
            "income-statement": INCOME, "balance-sheet-statement": BALANCE, "cash-flow-statement": CASH,
            "historical-price-eod/full": PRICES, "analyst-estimates": ESTIMATES,
            "profile": [{"symbol": "AAPL", "companyName": "Apple Inc.", "price": 250.0, "marketCap": 3.7e12,
                         "sector": "Technology", "changePercentage": 1.2}],
            "search-symbol": [{"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"}],
            "search-name": [{"symbol": "AAPL", "name": "Apple Inc."}, {"symbol": "APLE", "name": "Apple Hospitality"}],
        }[path]
        return httpx.Response(200, json=body)

    return FmpClient("test-key", httpx.Client(transport=httpx.MockTransport(handler)))


def test_statements_merge_and_signs():
    rows = _client().statements("AAPL", "annual", 5)
    assert len(rows) == 1
    r = rows[0]
    assert r["revenue"] == 391035000000 and r["eps_diluted"] == 6.08
    assert r["cash"] == 29943000000 and r["total_equity"] == 56950000000
    # Cash going out is positive in this project's fields.
    assert r["capex"] == 9447000000 and r["dividends_paid"] == 15234000000 and r["buybacks"] == 94949000000
    assert r["fiscal_year"] == "2024"


def test_prices_are_oldest_first():
    bars = _client().prices("AAPL", "2024-01-01")
    assert [b["date"] for b in bars] == ["2024-06-10", "2024-06-11"]


def test_estimates_and_profile_and_search():
    c = _client()
    e = c.estimates("AAPL")[0]
    assert e["eps_avg"] == 7.4 and e["analysts_eps"] == 30
    assert c.profile("AAPL")["market_cap"] == 3.7e12
    assert [r["ticker"] for r in c.search("apple")] == ["AAPL", "APLE"]


def test_plan_refusals_become_unavailable():
    with pytest.raises(FmpUnavailable):
        _client(402).estimates("AAPL")


def test_no_key_means_unavailable():
    with pytest.raises(FmpUnavailable):
        FmpClient("").profile("AAPL")


def _fact(val, end, start=None, form="10-K", fp="FY", filed="2024-11-01"):
    out = {"val": val, "end": end, "form": form, "fp": fp, "filed": filed}
    if start:
        out["start"] = start
    return out


def test_sec_facts_take_annual_10k_values_and_latest_restatement():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [_fact(260e9, "2019-09-28", "2018-09-30", filed="2019-10-31")]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _fact(383e9, "2023-09-30", "2022-10-01", filed="2023-11-03"),
            _fact(391e9, "2024-09-28", "2023-10-01"),
            _fact(95e9, "2024-06-29", "2024-03-31", form="10-Q", fp="Q3"),
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            _fact(97e9, "2023-09-30", "2022-10-01", filed="2023-11-03"),
            _fact(96.9e9, "2023-09-30", "2022-10-01", filed="2024-11-01"),  # restated in the next 10-K
            _fact(93.7e9, "2024-09-28", "2023-10-01"),
        ]}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [_fact(29.9e9, "2024-09-28")]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_fact(118e9, "2024-09-28", "2023-10-01")]}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [_fact(9.4e9, "2024-09-28", "2023-10-01")]}},
    }}}
    rows = annual_from_facts(facts)
    by_end = {r["date"]: r for r in rows}
    assert by_end["2019-09-28"]["revenue"] == 260e9  # older tag still used for older years
    assert by_end["2024-09-28"]["revenue"] == 391e9  # the 10-Q is ignored
    assert by_end["2023-09-30"]["net_income"] == 96.9e9  # the later filing wins
    assert by_end["2024-09-28"]["free_cash_flow"] == pytest.approx(118e9 - 9.4e9)
    assert by_end["2024-09-28"]["cash"] == 29.9e9

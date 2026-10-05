"""Report, comparison, reading, budget and API, with the fakes from conftest."""

import json

import pytest
from fastapi.testclient import TestClient

from conftest import FakeAnthropic, FakeFmp
from fundamentals.api import create_app
from fundamentals.budget import Budget, BudgetReached
from fundamentals.compare import compare
from fundamentals.reading import SYSTEM, Reader
from fundamentals.report import Reporter, compact


def test_search_by_ticker_and_name(directory):
    assert directory.search("AAPL")[0].ticker == "AAPL"
    assert directory.search("aapl")[0].ticker == "AAPL"
    assert directory.search("apple")[0].ticker == "AAPL"
    assert directory.search("microsoft")[0].ticker == "MSFT"
    assert directory.search("alphabet")[0].ticker == "GOOGL"
    assert directory.search("berkshire hathaway")[0].ticker == "BRK-B"
    assert directory.get("brk.b").ticker == "BRK-B"
    # "APP" is a ticker of its own and the start of Apple's ticker.
    assert [c.ticker for c in directory.search("APP")][:2] == ["APP", "AAPL"]


def test_report_has_every_section_and_is_cached(directory, store):
    fmp = FakeFmp()
    reporter = Reporter(store, fmp)
    report = reporter.build(directory.get("AAPL"))
    for key in ("profile", "annual", "quarters", "annual_ratios", "ttm", "valuation", "history", "forward",
                "growth", "technical"):
        assert key in report
    assert report["ttm"]["period"] == "TTM"
    assert report["forward"]["available"]
    assert report["technical"]["available"]
    calls = len(fmp.calls)
    reporter.build(directory.get("AAPL"))
    assert len(fmp.calls) == calls  # second build served from the store


def test_report_steps_are_streamed(directory, store):
    steps = [e["step"] for e in Reporter(store, FakeFmp()).run(directory.get("MSFT"))]
    assert steps == ["profile", "statements", "prices", "estimates", "compute", "done"]


def test_report_falls_back_to_sec_and_degrades_without_estimates(directory, store):
    fmp = FakeFmp(fail={"statements-annual", "statements-quarter", "estimates"})
    from conftest import make_annual

    sec_rows = make_annual()
    reporter = Reporter(store, fmp, sec_annual=lambda cik, years: sec_rows)
    report = reporter.build(directory.get("AAPL"))
    assert report["sources"]["statements"] == "SEC EDGAR (XBRL)"
    assert report["forward"]["available"] is False
    assert report["notes"]
    assert all("402" not in n or "FMP refused" in n for n in report["notes"])


def test_compare_marks_extremes_without_ranking(directory, store):
    reporter = Reporter(store, FakeFmp(seed_by_ticker={"AAPL": 0, "MSFT": 3, "GOOGL": 6}))
    result = compare([reporter.build(directory.get(t)) for t in ("AAPL", "MSFT", "GOOGL")])
    assert result["tickers"] == ["AAPL", "MSFT", "GOOGL"]
    growth = next(r for r in result["table"] if r["key"] == "growth.revenue.5y")
    assert growth["highest"] == growth["values"][2] and growth["lowest"] == growth["values"][0]
    prices = result["prices"]
    assert prices["dates"] and all(series[0] == 100.0 for series in prices["series"].values())


def test_reading_uses_only_the_compact_numbers_and_is_cached(directory, store):
    report = Reporter(store, FakeFmp()).build(directory.get("AAPL"))
    fake = FakeAnthropic()
    reader = Reader(store, Budget(store, daily_max=1.0, total_max=5.0, request_max=0.15), client=fake)
    data = compact(report)
    first = reader.company(data)
    assert first["read_now"] and first["headline"]
    request = fake.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert "series" not in request["messages"][0]["content"]
    assert "never advise" in SYSTEM
    # The worst case of the call stays under the per-request cap.
    assert request["max_tokens"] * 20 / 1e6 < 0.15
    second = reader.company(data)
    assert second["read_now"] is False and len(fake.requests) == 1
    assert reader.budget.status()["calls"] == 1


def test_budget_caps(store):
    budget = Budget(store, daily_max=0.20, total_max=1.0, request_max=0.15)
    budget.check()
    budget.book(0.10)
    with pytest.raises(BudgetReached):
        budget.check()


def test_api_end_to_end(directory, store):
    fake = FakeAnthropic()
    app = create_app(store=store, directory=directory, reporter=Reporter(store, FakeFmp()),
                     reader=Reader(store, Budget(store, 1.0, 5.0, 0.15), client=fake))
    client = TestClient(app)
    assert client.get("/api/health").json() == {"ok": True}
    assert client.get("/api/search", params={"q": "apple"}).json()["companies"][0]["ticker"] == "AAPL"
    assert client.get("/api/stock/NOPE").status_code == 404

    lines = [json.loads(l) for l in client.get("/api/stock/AAPL/stream").text.strip().splitlines()]
    assert lines[-1]["step"] == "done" and lines[-1]["report"]["ticker"] == "AAPL"

    assert client.get("/api/stock/AAPL").json()["valuation"]["pe"] > 0
    # Opening the page never spends: without a reading for today, cached_only answers 204.
    assert client.get("/api/stock/AAPL/reading", params={"cached_only": 1}).status_code == 204
    assert not fake.requests
    reading = client.get("/api/stock/AAPL/reading").json()
    assert client.get("/api/stock/AAPL/reading", params={"cached_only": 1}).json()["headline"] == reading["headline"]
    assert reading["headline"]
    assert client.get("/api/compare", params={"tickers": "AAPL"}).status_code == 400
    result = client.get("/api/compare", params={"tickers": "AAPL,MSFT"}).json()
    assert result["tickers"] == ["AAPL", "MSFT"]
    assert client.get("/api/compare/reading", params={"tickers": "MSFT,AAPL"}).json()["kind"] == "compare"
    assert len(fake.requests) == 2


def test_api_reports_spending_limit(directory, store):
    reader = Reader(store, Budget(store, daily_max=0.01, total_max=5.0, request_max=0.15), client=FakeAnthropic())
    app = create_app(store=store, directory=directory, reporter=Reporter(store, FakeFmp()), reader=reader)
    response = TestClient(app).get("/api/stock/AAPL/reading")
    assert response.status_code == 429
    assert "spending limit" in response.json()["detail"]


def test_without_a_key_the_reading_is_off_and_says_so(directory, store, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(store=store, directory=directory, reporter=Reporter(store, FakeFmp()),
                     reader=Reader(store, Budget(store, 1.0, 5.0, 0.15)), hub=None)
    client = TestClient(app)
    assert client.get("/api/stock/AAPL").status_code == 200
    response = client.get("/api/stock/AAPL/reading")
    assert response.status_code == 503 and "not switched on" in response.json()["detail"]


def test_the_provider_key_never_reaches_the_logs(directory, store):
    # FMP takes the key in the query string, and httpx logs request URLs at INFO.
    import logging

    create_app(store=store, directory=directory, reporter=Reporter(store, FakeFmp()), hub=None)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING

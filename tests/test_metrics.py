import pytest

from conftest import make_annual, make_bars, make_quarters
from fundamentals import metrics


def test_margins_and_returns():
    annual = make_annual()
    r = metrics.period_ratios(annual)[-1]
    assert r["gross_margin"] == pytest.approx(0.45)
    assert r["operating_margin"] == pytest.approx(0.30)
    assert r["net_margin"] == pytest.approx(0.25)
    assert r["fcf_margin"] == pytest.approx(0.27)
    assert r["revenue_growth"] == pytest.approx(0.08)
    # ROE over the average equity of the two years (both 70B).
    assert r["roe"] == pytest.approx(annual[-1]["net_income"] / 70e9)
    # Net debt: 100B debt - 30B cash - 20B short-term investments.
    assert r["net_debt"] == pytest.approx(50e9)
    assert r["interest_coverage"] == pytest.approx(annual[-1]["operating_income"] / 2e9)


def test_ratios_are_none_not_zero_when_missing():
    row = {"date": "2024-12-31", "period": "FY", "revenue": None, "net_income": -5.0, "total_equity": 10.0}
    r = metrics.period_ratios([row])[0]
    assert r["gross_margin"] is None
    assert r["roe"] == pytest.approx(-0.5)  # losses on positive equity: a negative return
    assert r["revenue_growth"] is None
    negative_equity = metrics.period_ratios([{**row, "net_income": 5.0, "total_equity": -10.0}])[0]
    assert negative_equity["roe"] is None  # no meaningful return on negative equity


def test_quarterly_growth_is_against_the_same_quarter_a_year_earlier():
    quarters = make_quarters(make_annual(), n=8)
    r = metrics.period_ratios(quarters)
    assert r[3]["revenue_growth"] is None
    assert r[4]["revenue_growth"] == pytest.approx(0.08)


def test_ttm_sums_four_quarters_and_falls_back_to_the_fiscal_year():
    annual = make_annual()
    quarters = make_quarters(annual, n=8)
    t = metrics.ttm(quarters, annual)
    assert t["period"] == "TTM"
    assert t["revenue"] == pytest.approx(annual[-1]["revenue"])
    assert t["total_debt"] == quarters[-1]["total_debt"]
    t2 = metrics.ttm(quarters[:2], annual)
    assert t2["period"] == "FY" and t2["revenue"] == annual[-1]["revenue"]


def test_current_multiples():
    annual = make_annual()
    t = metrics.ttm([], annual)
    profile = {"price": 200.0, "market_cap": 200.0 * 15e9}
    m = metrics.current_multiples(profile, t)
    assert m["enterprise_value"] == pytest.approx(3000e9 + 50e9)
    assert m["pe"] == pytest.approx(200.0 / annual[-1]["eps_diluted"])
    assert m["ev_ebitda"] == pytest.approx(3050e9 / annual[-1]["ebitda"])
    assert m["dividend_yield"] == pytest.approx(15e9 / 3000e9)


def test_pe_is_none_with_losses():
    m = metrics.current_multiples({"price": 10.0, "market_cap": 100.0}, {"eps_diluted": -1.0, "net_income": -10.0})
    assert m["pe"] is None
    assert m["earnings_yield"] == pytest.approx(-0.1)


def test_price_on_uses_the_last_session_and_ignores_gaps():
    bars = [{"date": "2024-09-27", "close": 10.0}, {"date": "2024-10-01", "close": 11.0}]
    assert metrics.price_on(bars, "2024-09-29") == 10.0
    assert metrics.price_on(bars, "2024-09-01") is None
    assert metrics.price_on(bars, "2024-12-31") is None  # more than ten days after the last bar


def test_historical_multiples_use_the_fiscal_year_end_price():
    annual = make_annual()
    bars = make_bars()
    h = metrics.historical_multiples(annual, bars)
    assert h["years"], "expected some years inside the price history"
    y = h["years"][-1]
    row = next(a for a in annual if a["date"] == y["date"])
    assert y["pe"] == pytest.approx(metrics.price_on(bars, row["date"]) / row["eps_diluted"])
    assert h["summary"]["pe"]["median"] is not None


def test_cagr():
    assert metrics.cagr(121.0, 100.0, 2) == pytest.approx(0.10)
    assert metrics.cagr(100.0, -5.0, 2) is None

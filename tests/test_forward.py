import pytest

from conftest import make_annual, make_bars, make_estimates
from fundamentals import metrics
from fundamentals.forward import forward_multiples


def _inputs():
    annual = make_annual()
    estimates = make_estimates(annual, growth=0.10)
    current = metrics.current_multiples({"price": 150.0, "market_cap": 150.0 * 15e9}, metrics.ttm([], annual))
    history = metrics.historical_multiples(annual, make_bars())
    return annual, estimates, current, history


def test_forward_pe_is_price_over_consensus_eps():
    annual, estimates, current, history = _inputs()
    f = forward_multiples(estimates, annual, current, history)
    assert f["available"]
    y1 = f["years"][0]
    assert y1["pe"] == pytest.approx(150.0 / estimates[0]["eps_avg"])
    # The P/E range swaps ends: high EPS gives the low P/E.
    assert y1["pe_low"] < y1["pe"] < y1["pe_high"]
    assert y1["eps_growth"] == pytest.approx(0.10)
    assert y1["ev_ebitda"] == pytest.approx(current["enterprise_value"] / estimates[0]["ebitda_avg"])
    assert f["eps_cagr"] == pytest.approx(0.10)
    assert f["peg"] == pytest.approx(y1["pe"] / 10.0)


def test_forward_multiples_fall_as_earnings_grow_at_a_constant_price():
    annual, estimates, current, history = _inputs()
    pes = [y["pe"] for y in forward_multiples(estimates, annual, current, history)["years"]]
    assert pes == sorted(pes, reverse=True)


def test_only_years_after_the_last_reported_one():
    annual, estimates, current, history = _inputs()
    past = {**estimates[0], "date": annual[-1]["date"]}
    f = forward_multiples([past] + estimates, annual, current, history)
    assert all(y["fiscal_year_end"] > annual[-1]["date"] for y in f["years"])
    assert len(f["years"]) == 3


def test_no_estimates():
    annual, _, current, history = _inputs()
    assert forward_multiples([], annual, current, history)["available"] is False


def test_negative_consensus_eps_gives_no_pe():
    annual, estimates, current, history = _inputs()
    estimates[0]["eps_avg"] = -1.0
    f = forward_multiples(estimates, annual, current, history)
    assert f["years"][0]["pe"] is None
    assert f["peg"] is None

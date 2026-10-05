import pytest

from conftest import make_bars
from fundamentals import technical as t


def test_sma_and_ema():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert t.sma(values, 3) == [None, None, 2.0, 3.0, 4.0]
    e = t.ema(values, 3)
    assert e[2] == 2.0
    assert e[3] == pytest.approx(4 * 0.5 + 2.0 * 0.5)


def test_rsi_extremes():
    up = [float(i) for i in range(1, 40)]
    assert t.rsi(up)[-1] == 100.0
    down = list(reversed(up))
    assert t.rsi(down)[-1] == pytest.approx(0.0)
    flat = [5.0] * 40
    assert t.rsi(flat)[-1] == 50.0


def test_rsi_matches_wilder_reference():
    # The classic example from Wilder's book as reproduced in many references: RSI(14) on these
    # closes is about 70.46 at the 15th value.
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    assert t.rsi(closes)[14] == pytest.approx(70.46, abs=0.05)


def test_macd_on_a_trend_is_positive():
    closes = [100 * 1.01**i for i in range(80)]
    m = t.macd(closes)
    assert m["macd"][-1] > 0
    assert m["signal"][-1] is not None
    assert m["hist"][-1] == pytest.approx(m["macd"][-1] - m["signal"][-1])
    assert m["signal"][33] is not None and m["signal"][32] is None  # 26 + 9 - 1 = 34th value


def test_bollinger_band_width_is_zero_on_flat_prices():
    bb = t.bollinger([10.0] * 25)
    assert bb["upper"][-1] == bb["lower"][-1] == 10.0


def test_max_drawdown():
    assert t.max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(90 / 120 - 1)


def test_last_cross():
    dates = ["d0", "d1", "d2", "d3"]
    assert t.last_cross([1, 2, 4, 5], [3, 3, 3, 3], dates) == {"date": "d2", "kind": "golden"}
    assert t.last_cross([4, 5, 6, 7], [3, 3, 3, 3], dates) is None


def test_key_levels_sit_on_each_side_of_the_price():
    bars = make_bars(300)
    levels = t.key_levels(bars)
    price = bars[-1]["close"]
    assert all(s["level"] < price for s in levels["supports"])
    assert all(r["level"] > price for r in levels["resistances"])


def test_analyse_summary_and_neutral_labels():
    bars = make_bars(600)
    bench = make_bars(600, seed=8)
    result = t.analyse(bars, bench)
    assert result["available"]
    s = result["summary"]
    assert s["price"] == bars[-1]["close"]
    assert s["beta_1y"] is not None and -1 < s["correlation_1y"] <= 1
    assert len(result["series"]["date"]) == 600
    words = " ".join(x["label"].lower() for x in s["states"])
    for advice in ("buy", "sell", "should"):
        assert advice not in words


def test_beta_of_the_benchmark_against_itself_is_one():
    bench = make_bars(400)
    beta, corr = t.beta_and_correlation(bench, bench)
    assert beta == pytest.approx(1.0)
    assert corr == pytest.approx(1.0)


def test_analyse_needs_history():
    assert t.analyse(make_bars(10))["available"] is False

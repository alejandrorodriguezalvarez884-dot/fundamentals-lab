"""Technical analysis of daily bars. Pure functions, no network.

Everything here describes what the price has done. Nothing is a signal to buy or sell, and the
labels say where an indicator stands ("RSI above 70"), never what to do about it.
"""

from __future__ import annotations

import math
from datetime import date

TRADING_DAYS = 252


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


def ema(values: list[float], n: int) -> list[float | None]:
    """Exponential average seeded with the simple average of the first ``n`` values."""
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        change = closes[i] - closes[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / n, losses / n
    out[n] = _rsi_value(avg_gain, avg_loss)
    for i in range(n + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (n - 1) + max(change, 0.0)) / n
        avg_loss = (avg_loss * (n - 1) + max(-change, 0.0)) / n
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(gain: float, loss: float) -> float:
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[float | None]]:
    f, s = ema(closes, fast), ema(closes, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    sig_tail = ema([v for v in line[start:]], signal) if start < len(line) else []
    sig = [None] * start + sig_tail
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return {"macd": line, "signal": sig, "hist": hist}


def bollinger(closes: list[float], n: int = 20, k: float = 2.0) -> dict[str, list[float | None]]:
    mid = sma(closes, n)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((x - m) ** 2 for x in window) / n)
        upper[i], lower[i] = m + k * sd, m - k * sd
    return {"middle": mid, "upper": upper, "lower": lower}


def atr(bars: list[dict], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(bars)
    if len(bars) <= n:
        return out
    trs = [bars[0]["high"] - bars[0]["low"]]
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    value = sum(trs[1:n + 1]) / n
    out[n] = value
    for i in range(n + 1, len(bars)):
        value = (value * (n - 1) + trs[i]) / n
        out[i] = value
    return out


def daily_returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1] > 0]


def period_return(bars: list[dict], sessions: int) -> float | None:
    if len(bars) <= sessions:
        return None
    return bars[-1]["close"] / bars[-1 - sessions]["close"] - 1


def ytd_return(bars: list[dict]) -> float | None:
    year = bars[-1]["date"][:4]
    before = [b for b in bars if b["date"][:4] < year]
    if not before:
        return None
    return bars[-1]["close"] / before[-1]["close"] - 1


def max_drawdown(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak, worst = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        worst = min(worst, c / peak - 1)
    return worst


def beta_and_correlation(bars: list[dict], bench: list[dict], sessions: int = TRADING_DAYS) -> tuple[float | None, float | None]:
    """Beta and correlation of daily returns against the benchmark, on the dates both share."""
    by_date = {b["date"]: b["close"] for b in bench}
    pairs = [(b["close"], by_date[b["date"]]) for b in bars[-(sessions + 1):] if b["date"] in by_date]
    if len(pairs) < 60:
        return None, None
    ra = [pairs[i][0] / pairs[i - 1][0] - 1 for i in range(1, len(pairs))]
    rb = [pairs[i][1] / pairs[i - 1][1] - 1 for i in range(1, len(pairs))]
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((a - ma) * (b - mb) for a, b in zip(ra, rb)) / (len(ra) - 1)
    va = sum((a - ma) ** 2 for a in ra) / (len(ra) - 1)
    vb = sum((b - mb) ** 2 for b in rb) / (len(rb) - 1)
    if vb == 0 or va == 0:
        return None, None
    return cov / vb, cov / math.sqrt(va * vb)


def pivots(bars: list[dict], window: int = 5) -> tuple[list[float], list[float]]:
    """Swing lows and highs: a bar whose low (high) is the lowest (highest) of ``window`` bars on
    each side."""
    lows, highs = [], []
    for i in range(window, len(bars) - window):
        span = bars[i - window:i + window + 1]
        if bars[i]["low"] == min(b["low"] for b in span):
            lows.append(bars[i]["low"])
        if bars[i]["high"] == max(b["high"] for b in span):
            highs.append(bars[i]["high"])
    return lows, highs


def cluster(levels: list[float], tolerance: float = 0.015) -> list[dict]:
    """Group levels within ``tolerance`` of each other; a level touched more often is stronger."""
    groups: list[list[float]] = []
    for level in sorted(levels):
        if groups and level <= groups[-1][0] * (1 + tolerance):
            groups[-1].append(level)
        else:
            groups.append([level])
    return [{"level": sum(g) / len(g), "touches": len(g)} for g in groups]


def key_levels(bars: list[dict], sessions: int = 126) -> dict:
    """Nearest support below and resistance above the last close, from the swing points of the
    last ``sessions`` bars (six months by default)."""
    recent = bars[-sessions:]
    if len(recent) < 20:
        return {"supports": [], "resistances": []}
    price = recent[-1]["close"]
    lows, highs = pivots(recent)
    levels = cluster(lows + highs)
    supports = sorted([l for l in levels if l["level"] < price], key=lambda l: -l["level"])[:3]
    resistances = sorted([l for l in levels if l["level"] > price], key=lambda l: l["level"])[:3]
    for l in supports + resistances:
        l["distance"] = l["level"] / price - 1
    return {"supports": supports, "resistances": resistances}


def last_cross(fast: list[float | None], slow: list[float | None], dates: list[str]) -> dict | None:
    """The most recent day the fast average crossed the slow one."""
    for i in range(len(fast) - 1, 0, -1):
        a0, b0, a1, b1 = fast[i - 1], slow[i - 1], fast[i], slow[i]
        if None in (a0, b0, a1, b1):
            return None
        if (a0 - b0) * (a1 - b1) < 0:
            return {"date": dates[i], "kind": "golden" if a1 > b1 else "death"}
    return None


def analyse(bars: list[dict], bench: list[dict] | None = None) -> dict:
    """Indicator series for the charts and a summary of where each indicator stands today."""
    if len(bars) < 30:
        return {"available": False, "reason": "Not enough price history."}
    closes = [b["close"] for b in bars]
    dates = [b["date"] for b in bars]
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    r = rsi(closes)
    m = macd(closes)
    bb = bollinger(closes)
    a = atr(bars)
    price = closes[-1]
    year = bars[-TRADING_DAYS:]
    high52 = max(b["high"] for b in year)
    low52 = min(b["low"] for b in year)
    rets = daily_returns([b["close"] for b in year])
    vol = (math.sqrt(sum((x - sum(rets) / len(rets)) ** 2 for x in rets) / (len(rets) - 1)) * math.sqrt(TRADING_DAYS)
           if len(rets) > 20 else None)
    beta, corr = beta_and_correlation(bars, bench or [])
    bench_1y = period_return(bench, TRADING_DAYS) if bench else None
    own_1y = period_return(bars, TRADING_DAYS)
    avg_vol_50 = sum(b["volume"] for b in bars[-50:]) / min(50, len(bars))

    summary = {
        "date": dates[-1],
        "price": price,
        "sma20": s20[-1], "sma50": s50[-1], "sma200": s200[-1],
        "vs_sma50": price / s50[-1] - 1 if s50[-1] else None,
        "vs_sma200": price / s200[-1] - 1 if s200[-1] else None,
        "rsi14": r[-1],
        "macd": m["macd"][-1], "macd_signal": m["signal"][-1], "macd_hist": m["hist"][-1],
        "bollinger_upper": bb["upper"][-1], "bollinger_lower": bb["lower"][-1],
        "bollinger_position": _position(price, bb["lower"][-1], bb["upper"][-1]),
        "atr14": a[-1], "atr_pct": a[-1] / price if a[-1] else None,
        "high_52w": high52, "low_52w": low52,
        "from_high_52w": price / high52 - 1, "from_low_52w": price / low52 - 1,
        "return_1m": period_return(bars, 21), "return_3m": period_return(bars, 63),
        "return_6m": period_return(bars, 126), "return_1y": own_1y,
        "return_3y": period_return(bars, 3 * TRADING_DAYS), "return_ytd": ytd_return(bars),
        "volatility_1y": vol,
        "max_drawdown_1y": max_drawdown([b["close"] for b in year]),
        "beta_1y": beta, "correlation_1y": corr,
        "benchmark_return_1y": bench_1y,
        "relative_1y": (1 + own_1y) / (1 + bench_1y) - 1 if own_1y is not None and bench_1y is not None else None,
        "volume_vs_avg50": bars[-1]["volume"] / avg_vol_50 if avg_vol_50 else None,
        "last_cross_50_200": last_cross(s50, s200, dates),
    }
    summary["states"] = states(summary)
    return {
        "available": True,
        "summary": summary,
        "levels": key_levels(bars),
        "series": {
            "date": dates,
            "open": [b["open"] for b in bars], "high": [b["high"] for b in bars],
            "low": [b["low"] for b in bars], "close": closes,
            "volume": [b["volume"] for b in bars],
            "sma20": s20, "sma50": s50, "sma200": s200,
            "bb_upper": bb["upper"], "bb_lower": bb["lower"],
            "rsi14": r, "macd": m["macd"], "macd_signal": m["signal"], "macd_hist": m["hist"],
        },
    }


def _position(price: float, low: float | None, high: float | None) -> float | None:
    """0 at the lower band, 1 at the upper."""
    if low is None or high is None or high == low:
        return None
    return (price - low) / (high - low)


def states(s: dict) -> list[dict]:
    """Where the indicators stand, in neutral words. ``tone`` only picks a colour."""
    out = []

    def add(label: str, tone: str) -> None:
        out.append({"label": label, "tone": tone})

    if s["sma200"]:
        add(f"Price {'above' if s['price'] > s['sma200'] else 'below'} its 200-day average "
            f"({s['vs_sma200']:+.1%})", "up" if s["price"] > s["sma200"] else "down")
    if s["sma50"] and s["sma200"]:
        add(f"50-day average {'above' if s['sma50'] > s['sma200'] else 'below'} the 200-day",
            "up" if s["sma50"] > s["sma200"] else "down")
    if s["rsi14"] is not None:
        r = s["rsi14"]
        if r >= 70:
            add(f"RSI {r:.0f}, above 70 (overbought zone)", "warn")
        elif r <= 30:
            add(f"RSI {r:.0f}, below 30 (oversold zone)", "warn")
        else:
            add(f"RSI {r:.0f}, between 30 and 70", "neutral")
    if s["macd"] is not None and s["macd_signal"] is not None:
        add(f"MACD {'above' if s['macd'] > s['macd_signal'] else 'below'} its signal line",
            "up" if s["macd"] > s["macd_signal"] else "down")
    pos = s["bollinger_position"]
    if pos is not None and (pos > 1 or pos < 0):
        add(f"Close {'above the upper' if pos > 1 else 'below the lower'} Bollinger band", "warn")
    if s["from_high_52w"] is not None and s["from_high_52w"] > -0.02:
        add("Within 2% of its 52-week high", "up")
    elif s["from_low_52w"] is not None and s["from_low_52w"] < 0.02:
        add("Within 2% of its 52-week low", "down")
    cross = s["last_cross_50_200"]
    if cross and (date.fromisoformat(s["date"]) - date.fromisoformat(cross["date"])).days <= 30:
        add(f"{'Golden' if cross['kind'] == 'golden' else 'Death'} cross on {cross['date']}",
            "up" if cross["kind"] == "golden" else "down")
    return out

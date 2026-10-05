"""Ratios and multiples computed from the statements. Pure functions, no network.

Conventions: margins and returns are fractions (0.25 = 25 %), money is in the reporting
currency, a ratio that cannot be computed is ``None`` (never 0), and a multiple over a negative
denominator (a P/E with losses) is ``None`` too, because it means nothing.
"""

from __future__ import annotations

import bisect
from datetime import date
from statistics import mean, median

FLOW_FIELDS = (
    "revenue", "cost_of_revenue", "gross_profit", "rnd", "sga", "operating_income", "interest_expense",
    "pretax_income", "income_tax", "net_income", "ebitda", "d_and_a", "eps", "eps_diluted",
    "operating_cash_flow", "capex", "free_cash_flow", "dividends_paid", "buybacks", "sbc",
)


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def positive_multiple(value: float | None, base: float | None) -> float | None:
    """``value / base`` only when the base is positive."""
    if value is None or base is None or base <= 0:
        return None
    return value / base


def growth(new: float | None, old: float | None) -> float | None:
    """Relative change. Undefined when the old value is zero or negative."""
    if new is None or old is None or old <= 0:
        return None
    return new / old - 1


def cagr(new: float | None, old: float | None, years: float) -> float | None:
    if new is None or old is None or old <= 0 or new <= 0 or years <= 0:
        return None
    return (new / old) ** (1 / years) - 1


def tax_rate(row: dict) -> float:
    rate = div(row.get("income_tax"), row.get("pretax_income"))
    if rate is None or rate < 0 or rate > 0.5:
        return 0.21  # US statutory rate when the reported one is meaningless
    return rate


def ebitda(row: dict) -> float | None:
    if row.get("ebitda") is not None:
        return row["ebitda"]
    if row.get("operating_income") is not None and row.get("d_and_a") is not None:
        return row["operating_income"] + row["d_and_a"]
    return None


def cash_like(row: dict) -> float | None:
    if row.get("cash") is None and row.get("short_term_investments") is None:
        return None
    return (row.get("cash") or 0.0) + (row.get("short_term_investments") or 0.0)


def net_debt(row: dict) -> float | None:
    if row.get("total_debt") is None and cash_like(row) is None:
        return None
    return (row.get("total_debt") or 0.0) - (cash_like(row) or 0.0)


def period_ratios(rows: list[dict]) -> list[dict]:
    """Margins, returns, leverage and growth for each period. ``rows`` oldest first, all of one
    kind (annual, or quarterly: growth is then against the same quarter a year earlier)."""
    quarterly = any(r.get("period", "FY") != "FY" for r in rows)
    lag = 4 if quarterly else 1
    out = []
    for i, row in enumerate(rows):
        prev = rows[i - 1] if i >= 1 else None
        year_ago = rows[i - lag] if i >= lag else None
        revenue = row.get("revenue")
        e = ebitda(row)
        nopat = row["operating_income"] * (1 - tax_rate(row)) if row.get("operating_income") is not None else None
        invested = None
        if row.get("total_equity") is not None:
            invested = row["total_equity"] + (row.get("total_debt") or 0.0) - (cash_like(row) or 0.0)
        avg_equity = row.get("total_equity")
        if prev and prev.get("total_equity") is not None and avg_equity is not None:
            avg_equity = (avg_equity + prev["total_equity"]) / 2
        annualise = 4 if quarterly else 1
        out.append({
            "date": row["date"],
            "fiscal_year": row.get("fiscal_year"),
            "period": row.get("period", "FY"),
            "gross_margin": div(row.get("gross_profit"), revenue),
            "operating_margin": div(row.get("operating_income"), revenue),
            "ebitda_margin": div(e, revenue),
            "net_margin": div(row.get("net_income"), revenue),
            "fcf_margin": div(row.get("free_cash_flow"), revenue),
            "rnd_to_revenue": div(row.get("rnd"), revenue),
            "sbc_to_revenue": div(row.get("sbc"), revenue),
            "capex_to_revenue": div(row.get("capex"), revenue),
            "roe": _times(positive_multiple(row.get("net_income"), avg_equity), annualise),
            "roic": _times(positive_multiple(nopat, invested), annualise),
            "roa": _times(div(row.get("net_income"), row.get("total_assets")), annualise),
            "fcf_conversion": positive_multiple(row.get("free_cash_flow"), row.get("net_income")),
            "net_debt": net_debt(row),
            "net_debt_to_ebitda": positive_multiple(net_debt(row), _times(e, annualise)) if e and e > 0 else None,
            "debt_to_equity": positive_multiple(row.get("total_debt"), row.get("total_equity")),
            "current_ratio": div(row.get("total_current_assets"), row.get("total_current_liabilities")),
            "interest_coverage": positive_multiple(row.get("operating_income"), row.get("interest_expense")),
            "payout_ratio": positive_multiple(row.get("dividends_paid"), row.get("net_income")),
            "revenue_growth": growth(revenue, year_ago.get("revenue") if year_ago else None),
            "eps_growth": growth(row.get("eps_diluted"), year_ago.get("eps_diluted") if year_ago else None),
            "fcf_growth": growth(row.get("free_cash_flow"), year_ago.get("free_cash_flow") if year_ago else None),
            "share_count_change": growth(row.get("shares_diluted"), year_ago.get("shares_diluted") if year_ago else None),
        })
    return out


def _times(value: float | None, k: float) -> float | None:
    return None if value is None else value * k


def ttm(quarters: list[dict], annual: list[dict]) -> dict:
    """Trailing twelve months: flows summed over the last four quarters, balances from the last
    one. Falls back to the last fiscal year when there are not four consecutive quarters."""
    last4 = quarters[-4:]
    if len(last4) == 4 and all(q.get("revenue") is not None for q in last4):
        out = dict(last4[-1])
        for field in FLOW_FIELDS:
            values = [q.get(field) for q in last4]
            out[field] = sum(values) if all(v is not None for v in values) else None
        out["period"] = "TTM"
        out["shares_diluted"] = last4[-1].get("shares_diluted")
        out["source_period"] = f"4 quarters to {last4[-1]['date']}"
        return out
    if annual:
        out = dict(annual[-1])
        out["source_period"] = f"fiscal year to {annual[-1]['date']}"
        return out
    return {}


def current_multiples(profile: dict, t: dict) -> dict:
    """Valuation today from the price and the trailing twelve months."""
    price = profile.get("price")
    market_cap = profile.get("market_cap")
    if market_cap is None and price is not None and t.get("shares_diluted"):
        market_cap = price * t["shares_diluted"]
    nd = net_debt(t)
    ev = market_cap + nd if market_cap is not None and nd is not None else market_cap
    e = ebitda(t)
    return {
        "price": price,
        "market_cap": market_cap,
        "enterprise_value": ev,
        "net_debt": nd,
        "pe": positive_multiple(price, t.get("eps_diluted")),
        "ev_ebitda": positive_multiple(ev, e),
        "ev_sales": positive_multiple(ev, t.get("revenue")),
        "ev_ebit": positive_multiple(ev, t.get("operating_income")),
        "p_fcf": positive_multiple(market_cap, t.get("free_cash_flow")),
        "p_book": positive_multiple(market_cap, t.get("total_equity")),
        "p_sales": positive_multiple(market_cap, t.get("revenue")),
        "earnings_yield": div(t.get("net_income"), market_cap),
        "fcf_yield": div(t.get("free_cash_flow"), market_cap),
        "dividend_yield": div(t.get("dividends_paid"), market_cap),
        "buyback_yield": div(t.get("buybacks"), market_cap),
        "shareholder_yield": div((t.get("dividends_paid") or 0.0) + (t.get("buybacks") or 0.0), market_cap)
        if market_cap else None,
    }


def price_on(bars: list[dict], day: str) -> float | None:
    """Close on ``day`` or the last session before it."""
    dates = [b["date"] for b in bars]
    i = bisect.bisect_right(dates, day) - 1
    if i < 0:
        return None
    # A close more than ten days before the date belongs to a gap in the data, not to that date.
    if (_ordinal(day) - _ordinal(dates[i])) > 10:
        return None
    return bars[i]["close"]


def _ordinal(day: str) -> int:
    return date.fromisoformat(day[:10]).toordinal()


def historical_multiples(annual: list[dict], bars: list[dict]) -> dict:
    """Each fiscal year's multiples at the price of its fiscal year end, and their average and
    median over the years with prices. Shares are that year's weighted diluted average."""
    years = []
    for row in annual:
        price = price_on(bars, row["date"])
        sh = row.get("shares_diluted")
        if price is None or not sh:
            continue
        cap = price * sh
        nd = net_debt(row)
        ev = cap + nd if nd is not None else cap
        years.append({
            "date": row["date"],
            "fiscal_year": row.get("fiscal_year"),
            "price": price,
            "pe": positive_multiple(price, row.get("eps_diluted")),
            "ev_ebitda": positive_multiple(ev, ebitda(row)),
            "ev_sales": positive_multiple(ev, row.get("revenue")),
            "p_fcf": positive_multiple(cap, row.get("free_cash_flow")),
        })
    summary = {}
    for key in ("pe", "ev_ebitda", "ev_sales", "p_fcf"):
        values = [y[key] for y in years if y[key] is not None]
        summary[key] = {
            "mean": mean(values) if values else None,
            "median": median(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "years": len(values),
        }
    return {"years": years, "summary": summary}

"""Forward multiples: today's price over the analysts' consensus for the coming fiscal years.

This is the market's consensus as published by the data provider, not a forecast of ours. The
price is held at today's: the question each row answers is "if the consensus is met and the
price does not move, what multiple would the stock trade at?". No price target is derived.
"""

from __future__ import annotations

from .metrics import cagr, ebitda, growth, positive_multiple


def forward_multiples(estimates: list[dict], annual: list[dict], current: dict, history: dict,
                      max_years: int = 3) -> dict:
    """``estimates`` and ``annual`` oldest first; ``current`` from ``metrics.current_multiples``;
    ``history`` from ``metrics.historical_multiples``."""
    if not estimates:
        return {"available": False, "reason": "No analyst estimates for this company."}
    last_reported = annual[-1]["date"] if annual else ""
    future = [e for e in estimates if e["date"] > last_reported][:max_years]
    if not future:
        return {"available": False, "reason": "No estimates for fiscal years after the last one reported."}

    price, ev, cap = current.get("price"), current.get("enterprise_value"), current.get("market_cap")
    base = annual[-1] if annual else {}
    prev_eps, prev_rev, prev_ebitda = base.get("eps_diluted"), base.get("revenue"), ebitda(base) if base else None
    rows = []
    for e in future:
        rows.append({
            "fiscal_year_end": e["date"],
            "fiscal_year": e["date"][:4],
            "eps": e["eps_avg"], "eps_low": e["eps_low"], "eps_high": e["eps_high"],
            "revenue": e["revenue_avg"], "ebitda": e["ebitda_avg"], "net_income": e["net_income_avg"],
            "analysts": e["analysts_eps"] or e["analysts_revenue"],
            "pe": positive_multiple(price, e["eps_avg"]),
            # A higher EPS gives a lower P/E, so the range swaps ends.
            "pe_low": positive_multiple(price, e["eps_high"]),
            "pe_high": positive_multiple(price, e["eps_low"]),
            "ev_ebitda": positive_multiple(ev, e["ebitda_avg"]),
            "ev_sales": positive_multiple(ev, e["revenue_avg"]),
            "p_earnings_total": positive_multiple(cap, e["net_income_avg"]),
            "eps_growth": growth(e["eps_avg"], prev_eps),
            "revenue_growth": growth(e["revenue_avg"], prev_rev),
            "ebitda_growth": growth(e["ebitda_avg"], prev_ebitda),
            "net_margin": e["net_income_avg"] / e["revenue_avg"] if e["net_income_avg"] is not None and e["revenue_avg"] else None,
        })
        prev_eps, prev_rev, prev_ebitda = e["eps_avg"], e["revenue_avg"], e["ebitda_avg"]

    years = len(rows)
    eps_cagr = cagr(rows[-1]["eps"], base.get("eps_diluted"), years) if base else None
    revenue_cagr = cagr(rows[-1]["revenue"], base.get("revenue"), years) if base else None
    next_pe = rows[0]["pe"]
    peg = next_pe / (eps_cagr * 100) if next_pe is not None and eps_cagr and eps_cagr > 0 else None

    # Where each forward multiple sits against the company's own history.
    vs_history = {}
    for key in ("pe", "ev_ebitda", "ev_sales"):
        avg = (history.get("summary", {}).get(key) or {}).get("median")
        vs_history[key] = {
            "historical_median": avg,
            "current": current.get(key),
            "next_year": rows[0][key],
            "next_year_vs_median": rows[0][key] / avg - 1 if rows[0][key] is not None and avg else None,
        }
    return {
        "available": True,
        "price": price,
        "last_reported_fiscal_year_end": last_reported or None,
        "years": rows,
        "eps_cagr": eps_cagr,
        "revenue_cagr": revenue_cagr,
        "peg": peg,
        "vs_history": vs_history,
        "note": "Consensus estimates from the data provider at today's price. Not a forecast and "
                "not a price target.",
    }

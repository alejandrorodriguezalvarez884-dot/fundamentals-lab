"""Side-by-side comparison of 2 to 5 companies, from their reports."""

from __future__ import annotations

from .report import compact

# Which way is "more" for each line, only to mark the extremes in the table. It says nothing about
# which company is better: a low P/E is "lowest", not "cheapest" or "best".
COLUMNS = (
    ("market_cap", "Market cap"),
    ("valuation.pe", "P/E (TTM)"),
    ("forward.years.0.pe", "P/E next FY"),
    ("valuation.ev_ebitda", "EV/EBITDA"),
    ("valuation.ev_sales", "EV/Sales"),
    ("valuation.p_fcf", "P/FCF"),
    ("valuation.fcf_yield", "FCF yield"),
    ("valuation.dividend_yield", "Dividend yield"),
    ("forward.peg", "PEG"),
    ("growth.revenue.5y", "Revenue CAGR 5y"),
    ("growth.eps_diluted.5y", "EPS CAGR 5y"),
    ("forward.eps_cagr", "EPS CAGR (consensus)"),
    ("margins.gross_margin", "Gross margin"),
    ("margins.operating_margin", "Operating margin"),
    ("margins.net_margin", "Net margin"),
    ("margins.fcf_margin", "FCF margin"),
    ("returns.roe", "ROE"),
    ("returns.roic", "ROIC"),
    ("balance.net_debt_to_ebitda", "Net debt / EBITDA"),
    ("technical.return_1y", "Return 1y"),
    ("technical.return_ytd", "Return YTD"),
    ("technical.volatility_1y", "Volatility 1y"),
    ("technical.beta_1y", "Beta 1y"),
    ("technical.max_drawdown_1y", "Max drawdown 1y"),
)


def pick(data: dict, path: str):
    value = data
    for part in path.split("."):
        if isinstance(value, list):
            idx = int(part)
            value = value[idx] if idx < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
        if value is None:
            return None
    return value


def normalised_prices(reports: list[dict], sessions: int = 252) -> dict:
    """Closes rebased to 100 on the first date all companies share within the last ``sessions``."""
    series = {}
    for r in reports:
        tech = r["technical"]
        if not tech.get("available"):
            continue
        s = tech["series"]
        series[r["ticker"]] = dict(zip(s["date"][-sessions:], s["close"][-sessions:]))
    if not series:
        return {"dates": [], "series": {}}
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    if not common:
        return {"dates": [], "series": {}}
    out = {t: [round(v[d] / v[common[0]] * 100, 2) for d in common] for t, v in series.items()}
    return {"dates": common, "series": out}


def compare(reports: list[dict]) -> dict:
    companies = [compact(r) for r in reports]
    rows = []
    for path, label in COLUMNS:
        values = [pick(c, path) for c in companies]
        numbers = [v for v in values if isinstance(v, (int, float))]
        rows.append({
            "key": path,
            "label": label,
            "values": values,
            "highest": max(numbers) if len(numbers) >= 2 else None,
            "lowest": min(numbers) if len(numbers) >= 2 else None,
        })
    return {
        "tickers": [c["ticker"] for c in companies],
        "companies": companies,
        "table": rows,
        "prices": normalised_prices(reports),
        "scatter": [{"ticker": c["ticker"], "pe_next": pick(c, "forward.years.0.pe"),
                     "eps_cagr": pick(c, "forward.eps_cagr"), "revenue_cagr_5y": pick(c, "growth.revenue.5y"),
                     "ev_sales": pick(c, "valuation.ev_sales")} for c in companies],
    }

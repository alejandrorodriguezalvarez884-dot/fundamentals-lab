"""A longer annual history: the years a source no longer carries, from the SEC's XBRL filings.

Yahoo gives four fiscal years of statements; the SEC's facts go back more than ten. The older
years are added in front of the source's own, under two conditions. The years both have must
agree (sales, net income and earnings per share), which says the two count the same things for
this company; if they do not, nothing is added. And what is counted per share is put in today's
shares: a 10-K states it in the shares of its day, so every split after that filing is applied.
"""

from __future__ import annotations

from datetime import date, timedelta

# Two sources agree on a figure when they are this close, as a fraction.
TOLERANCE = 0.03
# A fiscal year end is the same one in both when the dates are this near: one source gives the
# day the books closed, the other the end of that month.
SAME_YEAR_DAYS = 10


def _day(text: str) -> date:
    return date.fromisoformat(text[:10])


def _close(a: float | None, b: float | None) -> bool | None:
    """Whether two figures agree; None when one of them is missing."""
    if a is None or b is None:
        return None
    if a == b:
        return True
    return abs(a - b) <= TOLERANCE * max(abs(a), abs(b))


def split_factor(splits: list[tuple[str, float]], filed: str) -> float:
    """How many of today's shares one share of ``filed`` (YYYY-MM-DD) has become."""
    factor = 1.0
    for day, ratio in splits:
        if filed and day > filed and ratio > 0:
            factor *= ratio
    return factor


def in_todays_shares(row: dict, splits: list[tuple[str, float]]) -> dict:
    """A row of the SEC with its per-share lines restated for the splits that came after it."""
    filed = row.get("per_share_filed") or {}
    out = {k: v for k, v in row.items() if k != "per_share_filed"}
    if out.get("eps_diluted") is not None:
        out["eps_diluted"] = out["eps_diluted"] / split_factor(splits, filed.get("eps_diluted", ""))
    if out.get("shares_diluted") is not None:
        out["shares_diluted"] = out["shares_diluted"] * split_factor(splits, filed.get("shares_diluted", ""))
    return out


def fiscal_year(day: str) -> str:
    """The year a fiscal year is named after: that of the month it closes in. Books closed in the
    first days of a month belong to the month before."""
    d = _day(day)
    return str((d - timedelta(days=d.day) if d.day <= 7 else d).year)


def backfill(recent: list[dict], filed: list[dict], splits: list[tuple[str, float]], years: int) -> list[dict]:
    """``recent`` (the source's fiscal years, oldest first) with the older years of ``filed`` (the
    SEC's) in front, up to ``years`` in all. ``recent`` comes back as it is when the two do not
    agree on the years they share, or share none."""
    if not recent or not filed:
        return recent
    older, shared = [], 0
    first = _day(recent[0]["date"])
    for row in (in_todays_shares(r, splits) for r in filed):
        day = _day(row["date"])
        twin = next((r for r in recent if abs((_day(r["date"]) - day).days) <= SAME_YEAR_DAYS), None)
        if twin:
            checks = [_close(row.get(k), twin.get(k)) for k in ("revenue", "net_income", "eps_diluted")]
            if False in checks or checks[0] is None:
                return recent  # the two do not count the same things for this company
            shared += 1
        elif day < first:
            older.append(row | {"fiscal_year": fiscal_year(row["date"])})
    if not shared:
        return recent
    # Growth over N years counts N rows back: the years must follow one another. Going back from
    # the source's first one, the history stops at the first year that is missing or has no sales.
    kept: list[dict] = []
    after = first
    for row in sorted(older, key=lambda r: r["date"], reverse=True):
        gap = (after - _day(row["date"])).days
        if row.get("revenue") is None or not 330 <= gap <= 400:
            break
        kept.insert(0, row)
        after = _day(row["date"])
    return (kept + recent)[-years:] if kept else recent

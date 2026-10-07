"""The older fiscal years, from the SEC, in front of a source's own: when the two agree."""

import pytest

from fundamentals.backfill import backfill, fiscal_year, in_todays_shares, split_factor
from fundamentals.sec import annual_from_facts

SPLITS = [("2014-06-09", 7.0), ("2020-08-31", 4.0)]


def recent():
    """A source's four fiscal years, dated at the end of the month."""
    return [{"date": f"{y}-09-30", "fiscal_year": str(y), "period": "FY", "revenue": 100e9 + 10e9 * i, "net_income": 24e9 + 2e9 * i,
             "eps_diluted": 1.6 + 0.1 * i, "shares_diluted": 15e9} for i, y in enumerate(range(2022, 2026))]


def filed():
    """The SEC's years, dated the day the books closed. 2019 was last filed before the 2020 split."""
    rows = [
        {"date": "2019-09-28", "revenue": 70e9, "net_income": 16e9, "eps_diluted": 3.6, "shares_diluted": 4.5e9,
         "per_share_filed": {"eps_diluted": "2019-10-30", "shares_diluted": "2019-10-30"}},
        {"date": "2020-09-26", "revenue": 80e9, "net_income": 19e9, "eps_diluted": 1.1, "shares_diluted": 17e9,
         "per_share_filed": {"eps_diluted": "2022-10-28", "shares_diluted": "2022-10-28"}},
        {"date": "2021-09-25", "revenue": 90e9, "net_income": 21e9, "eps_diluted": 1.3, "shares_diluted": 16e9,
         "per_share_filed": {"eps_diluted": "2023-11-03", "shares_diluted": "2023-11-03"}},
    ]
    for i, y in enumerate(range(2022, 2026)):
        rows.append({"date": f"{y}-09-2{4 + i}", "revenue": 100e9 + 10e9 * i, "net_income": 24e9 + 2e9 * i, "eps_diluted": 1.6 + 0.1 * i,
                     "shares_diluted": 15e9, "per_share_filed": {"eps_diluted": f"{y + 1}-10-30", "shares_diluted": f"{y + 1}-10-30"}})
    return [r | {"fiscal_year": r["date"][:4], "period": "FY", "currency": "USD"} for r in rows]


def test_a_share_of_an_old_filing_in_todays_shares():
    assert split_factor(SPLITS, "2013-10-30") == 28.0 and split_factor(SPLITS, "2019-10-30") == 4.0
    assert split_factor(SPLITS, "2020-10-29") == 1.0 and split_factor(SPLITS, "") == 1.0  # no filing date: left as it is
    row = in_todays_shares(filed()[0], SPLITS)
    assert row["eps_diluted"] == pytest.approx(0.9) and row["shares_diluted"] == 18e9 and "per_share_filed" not in row
    assert row["revenue"] == 70e9  # what is not per share does not move


def test_older_years_go_in_front_when_the_shared_ones_agree():
    rows = backfill(recent(), filed(), SPLITS, 11)
    assert [r["fiscal_year"] for r in rows] == ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
    assert rows[0]["eps_diluted"] == pytest.approx(0.9) and rows[1]["eps_diluted"] == 1.1  # only 2019 predates the split
    assert rows[3:] == recent() and all("per_share_filed" not in r for r in rows)  # the source's own years stay its own
    assert [r["fiscal_year"] for r in backfill(recent(), filed(), SPLITS, 5)] == ["2021", "2022", "2023", "2024", "2025"]


def test_nothing_is_added_when_the_two_do_not_agree_or_share_no_year():
    other = filed()
    other[4]["revenue"] *= 1.2  # the two count sales differently
    assert backfill(recent(), other, SPLITS, 11) == recent()
    unadjusted = filed()
    unadjusted[5]["eps_diluted"] *= 4  # a per-share figure the splits do not explain
    assert backfill(recent(), unadjusted, SPLITS, 11) == recent()
    assert backfill(recent(), filed()[:3], SPLITS, 11) == recent()  # no year in common to check against
    assert backfill(recent(), [], SPLITS, 11) == recent() and backfill([], filed(), SPLITS, 11) == []


def test_a_year_closed_in_the_first_days_of_january_is_named_after_december():
    assert fiscal_year("2022-01-01") == "2021" and fiscal_year("2022-01-30") == "2022" and fiscal_year("2025-09-27") == "2025"


def test_the_secs_rows_say_when_their_per_share_figures_were_filed():
    def fact(val, filed_on, start="2018-10-01", end="2019-09-28"):
        return {"form": "10-K", "fp": "FY", "start": start, "end": end, "filed": filed_on, "val": val}

    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [fact(70e9, "2019-10-30")]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [fact(3.6, "2019-10-30"), fact(0.9, "2020-10-29")]}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [fact(4.5e9, "2019-10-30")]}},
    }}}
    row = annual_from_facts(facts)[0]
    # The later 10-K restated the earnings per share for the split; the share count was only filed before it.
    assert row["eps_diluted"] == 0.9 and row["per_share_filed"] == {"eps_diluted": "2020-10-29", "shares_diluted": "2019-10-30"}
    adjusted = in_todays_shares(row, SPLITS)
    assert adjusted["eps_diluted"] == 0.9 and adjusted["shares_diluted"] == 18e9


def test_the_history_stops_at_a_missing_year_or_one_without_sales():
    gap = [r for r in filed() if r["date"] != "2020-09-26"]  # 2019 is there, but 2020 is not: growth would skip a year
    assert [r["fiscal_year"] for r in backfill(recent(), gap, SPLITS, 11)] == ["2021", "2022", "2023", "2024", "2025"]
    blank = filed()
    blank[1]["revenue"] = None
    assert [r["fiscal_year"] for r in backfill(recent(), blank, SPLITS, 11)] == ["2021", "2022", "2023", "2024", "2025"]

"""The spending ledger for the AI reading: what was spent today and in total, kept in the store.

Before a call the reading reserves its worst case (``request_max``); after it, the real cost is
booked. With two instances the ledger can lag by one request each, which the per-request cap
keeps small.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from .config import MODEL_PRICES, READING_DAILY_MAX_USD, READING_REQUEST_MAX_USD, READING_TOTAL_MAX_USD
from .store import Store

LEDGER_KEY = "ledger/reading"


class BudgetReached(Exception):
    """A cap would be passed. Readings already written keep being served."""


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = MODEL_PRICES.get(model, max(MODEL_PRICES.values()))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class Budget:
    def __init__(self, store: Store, daily_max: float = READING_DAILY_MAX_USD,
                 total_max: float = READING_TOTAL_MAX_USD, request_max: float = READING_REQUEST_MAX_USD):
        self.store = store
        self.daily_max, self.total_max, self.request_max = daily_max, total_max, request_max
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _ledger(self) -> dict:
        return self.store.get(LEDGER_KEY) or {"total_usd": 0.0, "days": {}, "calls": 0}

    def check(self) -> None:
        """Raise if one more request at its worst case would pass a cap."""
        with self._lock:
            ledger = self._ledger()
            today = ledger["days"].get(self._today(), 0.0)
            if today + self.request_max > self.daily_max:
                raise BudgetReached("daily")
            if ledger["total_usd"] + self.request_max > self.total_max:
                raise BudgetReached("total")

    def book(self, usd: float) -> dict:
        with self._lock:
            ledger = self._ledger()
            day = self._today()
            ledger["days"][day] = ledger["days"].get(day, 0.0) + usd
            ledger["total_usd"] += usd
            ledger["calls"] += 1
            # Keep the last 60 days; the total carries the rest.
            ledger["days"] = dict(sorted(ledger["days"].items())[-60:])
            self.store.put(LEDGER_KEY, ledger)
            return ledger

    def status(self) -> dict:
        ledger = self._ledger()
        return {
            "today_usd": round(ledger["days"].get(self._today(), 0.0), 4),
            "total_usd": round(ledger["total_usd"], 4),
            "daily_max_usd": self.daily_max,
            "total_max_usd": self.total_max,
            "calls": ledger["calls"],
        }

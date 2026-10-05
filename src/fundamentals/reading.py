"""The AI reading: Claude writes, in plain words, what the computed numbers show.

The model receives only numbers this code computed and is told to use only those. It describes;
it does not recommend, forecast or set price targets. Each reading is kept for the day, so a
company costs at most one call a day whoever asks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import anthropic

from .budget import Budget, cost_usd
from .config import MODEL_PRICES, READING_EFFORT, READING_MAX_TOKENS, READING_MODEL
from .store import Store

log = logging.getLogger("fundamentals.reading")

SYSTEM = """You write the "reading" section of a financial data website. You receive a JSON \
document with numbers already computed from a company's filings, market prices and the analysts' \
consensus. Your job is to say, in clear plain English, what those numbers show.

Rules:
- Use only the numbers in the document. Do not add facts, news, figures or context you know from \
elsewhere, and do not guess missing values: if something is null, leave it out.
- Describe; never advise. Do not say or imply that anyone should buy, sell, hold, accumulate or \
avoid a stock, and do not call a stock cheap, expensive, undervalued, overvalued, attractive or a \
good investment. Say what a multiple is and how it compares with the company's own history, with \
the consensus, or with the other companies.
- Do not forecast prices or returns and do not compute price targets. Forward multiples are the \
analysts' consensus at today's price; say so when you use them.
- Technical indicators describe past price behaviour. Report them as states ("the RSI is 74, above \
70"), never as signals.
- Fractions in the document are ratios: 0.253 is 25.3%. Money is in the reporting currency; write \
large amounts as $1.2B or $350M.
- Be concrete and brief: each paragraph two to four sentences, numbers rounded sensibly."""

COMPANY_TASK = """Write the reading for this company. Sections, in this order: "Business and growth", \
"Profitability", "Balance sheet and cash", "Valuation" (today, against its own history, and the \
consensus years), "Price behaviour". Then up to four short "points to check": things in the \
numbers a careful reader would want to look into (for example a gap between earnings and free \
cash flow, or a multiple far from its history). The headline is one sentence that summarises \
what the numbers show, with no advice."""

COMPARE_TASK = """Write the reading of this comparison between companies. Sections, in this order: \
"Size and growth", "Profitability", "Valuation", "Balance sheet", "Price behaviour". In each, \
compare the companies with each other using the numbers; name the highest and the lowest where it \
helps, without calling one better. Then up to four short "points to check". The headline is one \
sentence on what most separates these companies in the numbers, with no advice."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        },
        "points_to_check": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "sections", "points_to_check"],
    "additionalProperties": False,
}


class ReadingRefused(Exception):
    pass


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


class Reader:
    def __init__(self, store: Store, budget: Budget | None = None, client: anthropic.Anthropic | None = None,
                 model: str = READING_MODEL, effort: str = READING_EFFORT):
        self.store = store
        self.budget = budget or Budget(store)
        self._client = client
        self.model, self.effort = model, effort

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            # The key is the owner's ANTHROPIC_API_KEY. The base URL is pinned so a stray
            # ANTHROPIC_BASE_URL in the shell (a dev proxy, say) never receives it.
            self._client = anthropic.Anthropic(base_url=os.environ.get("READING_BASE_URL", "https://api.anthropic.com"))
        return self._client

    def key(self, kind: str, subject: str) -> str:
        return f"reading/{kind}/{_today()}/{subject}"

    def cached(self, kind: str, subject: str) -> dict | None:
        return self.store.get(self.key(kind, subject))

    def company(self, data: dict) -> dict:
        return self._read("company", data["ticker"], COMPANY_TASK, data)

    def comparison(self, data: list[dict]) -> dict:
        subject = "-".join(sorted(c["ticker"] for c in data))
        return self._read("compare", subject, COMPARE_TASK, {"companies": data})

    def _read(self, kind: str, subject: str, task: str, data: dict) -> dict:
        cached = self.cached(kind, subject)
        if cached:
            return {**cached, "read_now": False}
        self.budget.check()
        document = json.dumps(data, separators=(",", ":"), default=str)
        max_tokens = self._max_tokens(document)
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=SYSTEM,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            # On a refusal the API re-runs the request on its recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": f"{task}\n\n<data>\n{document}\n</data>"}],
        )
        usage = response.usage
        # Priced at the model that served it (a fallback may differ); unknown models at the dearest rate.
        spent = cost_usd(response.model or self.model, usage.input_tokens, usage.output_tokens)
        self.budget.book(spent)
        log.info("reading %s/%s tokens_in=%s tokens_out=%s usd=%.4f stop=%s", kind, subject,
                 usage.input_tokens, usage.output_tokens, spent, response.stop_reason)
        if response.stop_reason == "refusal":
            raise ReadingRefused(subject)
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            # Cut off at max_tokens: nothing usable to show.
            raise ReadingRefused(subject) from None
        reading = {
            **body,
            "kind": kind,
            "subject": subject,
            "model": response.model,
            "read_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_digest": _digest(data),
            "spent_usd": round(spent, 5),
        }
        self.store.put(self.key(kind, subject), reading)
        return {**reading, "read_now": True}

    def _max_tokens(self, document: str) -> int:
        """Output tokens that keep the worst case of this call under the per-request cap.
        Input is estimated at three characters per token, which overestimates it for JSON."""
        price_in, price_out = MODEL_PRICES.get(self.model, max(MODEL_PRICES.values()))
        input_usd = (len(document) + len(SYSTEM) + 1000) / 3 * price_in / 1_000_000
        room = (self.budget.request_max - input_usd) / price_out * 1_000_000
        return max(1000, min(READING_MAX_TOKENS, int(room)))

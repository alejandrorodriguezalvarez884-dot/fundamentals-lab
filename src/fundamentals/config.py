"""Constants of the service. Spending caps live here and in the environment, nowhere else."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("FUNDAMENTALS_DATA_DIR", ROOT / "data"))

# --- Data sources --------------------------------------------------------------------------

FMP_BASE = "https://financialmodelingprep.com/stable"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
# The SEC asks for at most 10 requests per second and a contact in the User-Agent.
SEC_RPS = 8.0

# How much history the report asks for.
ANNUAL_YEARS = 10
QUARTERS = 12
PRICE_YEARS = 5
# The index the technical analysis compares against (an ETF, so it has volume and EOD bars).
BENCHMARK = "SPY"

# A company report is rebuilt at most once a day; prices move, statements don't.
REPORT_TTL_HOURS = 12

# --- Comparison ----------------------------------------------------------------------------

COMPARE_MIN = 2
COMPARE_MAX = 5

# --- AI reading (Claude) -------------------------------------------------------------------

# The model that writes the reading of the numbers. It never computes them: every figure in the
# prompt comes from the code, and the model is told to use only those.
READING_MODEL = os.environ.get("READING_MODEL", "claude-opus-5-5")
READING_EFFORT = os.environ.get("READING_EFFORT", "low")
READING_MAX_TOKENS = 6000
# USD per million tokens (input, output) for the cost ledger. Thinking tokens bill as output.
MODEL_PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Caps so nobody spends the owner's key. The daily and total caps are set at deploy time.
READING_DAILY_MAX_USD = float(os.environ.get("READING_DAILY_MAX_USD", "0.50"))
READING_TOTAL_MAX_USD = float(os.environ.get("READING_TOTAL_MAX_USD", "5.00"))
READING_REQUEST_MAX_USD = 0.15
# Requests per address per hour, for every endpoint that may call a paid API.
PER_IP_PER_HOUR = 30

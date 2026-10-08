// The shapes the API returns (see src/fundamentals/report.py and compare.py).
export type N = number | null;

export type Period = {
  date: string;
  fiscal_year: string;
  period: string;
  revenue: N;
  gross_profit: N;
  operating_income: N;
  net_income: N;
  ebitda: N;
  eps_diluted: N;
  shares_diluted: N;
  free_cash_flow: N;
  operating_cash_flow: N;
  capex: N;
  cash: N;
  short_term_investments: N;
  total_debt: N;
  total_equity: N;
  total_assets: N;
  total_liabilities: N;
  dividends_paid: N;
  buybacks: N;
  sbc: N;
  rnd: N;
  [key: string]: unknown;
};

export type Ratios = {
  date: string;
  fiscal_year: string;
  period: string;
  gross_margin: N;
  operating_margin: N;
  ebitda_margin: N;
  net_margin: N;
  fcf_margin: N;
  rnd_to_revenue: N;
  sbc_to_revenue: N;
  roe: N;
  roic: N;
  roa: N;
  fcf_conversion: N;
  net_debt: N;
  net_debt_to_ebitda: N;
  debt_to_equity: N;
  current_ratio: N;
  interest_coverage: N;
  payout_ratio: N;
  revenue_growth: N;
  eps_growth: N;
  fcf_growth: N;
  share_count_change: N;
};

export type Valuation = {
  price: N;
  market_cap: N;
  enterprise_value: N;
  net_debt: N;
  pe: N;
  ev_ebitda: N;
  ev_sales: N;
  ev_ebit: N;
  p_fcf: N;
  p_book: N;
  p_sales: N;
  earnings_yield: N;
  fcf_yield: N;
  dividend_yield: N;
  buyback_yield: N;
  shareholder_yield: N;
};

export type MultipleKey = "pe" | "ev_ebitda" | "ev_sales" | "p_fcf";
export type History = {
  years: ({ date: string; fiscal_year: string; price: number } & Record<MultipleKey, N>)[];
  summary: Record<MultipleKey, { mean: N; median: N; min: N; max: N; years: number }>;
};

export type ForwardYear = {
  fiscal_year_end: string;
  fiscal_year: string;
  eps: N;
  eps_low: N;
  eps_high: N;
  revenue: N;
  ebitda: N;
  net_income: N;
  analysts: N;
  pe: N;
  pe_low: N;
  pe_high: N;
  ev_ebitda: N;
  ev_sales: N;
  eps_growth: N;
  revenue_growth: N;
  ebitda_growth: N;
  net_margin: N;
};

export type Forward =
  | { available: false; reason: string }
  | {
      available: true;
      price: N;
      last_reported_fiscal_year_end: string | null;
      years: ForwardYear[];
      eps_cagr: N;
      revenue_cagr: N;
      peg: N;
      vs_history: Record<"pe" | "ev_ebitda" | "ev_sales", { historical_median: N; current: N; next_year: N; next_year_vs_median: N }>;
      note: string;
    };

export type Level = { level: number; touches: number; distance: number };
export type TechSummary = {
  date: string;
  price: number;
  sma20: N;
  sma50: N;
  sma200: N;
  vs_sma50: N;
  vs_sma200: N;
  rsi14: N;
  macd: N;
  macd_signal: N;
  macd_hist: N;
  bollinger_upper: N;
  bollinger_lower: N;
  bollinger_position: N;
  atr14: N;
  atr_pct: N;
  high_52w: number;
  low_52w: number;
  from_high_52w: number;
  from_low_52w: number;
  return_1m: N;
  return_3m: N;
  return_6m: N;
  return_1y: N;
  return_3y: N;
  return_ytd: N;
  volatility_1y: N;
  max_drawdown_1y: N;
  beta_1y: N;
  correlation_1y: N;
  benchmark_return_1y: N;
  relative_1y: N;
  volume_vs_avg50: N;
  last_cross_50_200: { date: string; kind: "golden" | "death" } | null;
  states: { label: string; tone: "up" | "down" | "warn" | "neutral" }[];
};
export type Series = Record<
  "open" | "high" | "low" | "close" | "volume" | "sma20" | "sma50" | "sma200" | "bb_upper" | "bb_lower" | "rsi14" | "macd" | "macd_signal" | "macd_hist",
  N[]
> & { date: string[] };
export type Technical =
  | { available: false; reason: string }
  | { available: true; summary: TechSummary; levels: { supports: Level[]; resistances: Level[] }; series: Series };

export type Profile = {
  ticker: string;
  name: string;
  price?: N;
  change_pct?: N;
  market_cap?: N;
  beta?: N;
  currency?: string;
  exchange?: string;
  sector?: string;
  industry?: string;
  country?: string;
  employees?: N;
  ceo?: string;
  website?: string;
  description?: string;
  ipo_date?: string;
};

export type Report = {
  built_utc: string;
  ticker: string;
  profile: Profile;
  sources: Record<string, string>;
  notes: string[];
  annual: Period[];
  quarters: Period[];
  annual_ratios: Ratios[];
  quarter_ratios: Ratios[];
  ttm: Period & { source_period?: string };
  valuation: Valuation;
  history: History;
  forward: Forward;
  growth: Record<"revenue" | "eps_diluted" | "free_cash_flow" | "net_income", Record<"3y" | "5y" | "10y", N>>;
  technical: Technical;
};

export type Step = { step: string; detail?: string } | { step: "done"; report: Report } | { step: "error"; status: number; detail: string };

export type Reading = {
  headline: string;
  sections: { title: string; body: string }[];
  points_to_check: string[];
  model: string;
  read_utc: string;
  read_now: boolean;
  spent_usd: number;
};

export type Compact = {
  ticker: string;
  name: string;
  sector: string;
  price: N;
  market_cap: N;
  forward: { available: boolean; years: { fiscal_year: string; pe: N }[]; eps_cagr: N; peg: N };
  [key: string]: unknown;
};

export type Comparison = {
  tickers: string[];
  companies: Compact[];
  table: { key: string; label: string; values: (N | undefined)[]; highest: N; lowest: N }[];
  prices: { dates: string[]; series: Record<string, number[]> };
  scatter: { ticker: string; pe_next: N; eps_cagr: N; revenue_cagr_5y: N; ev_sales: N }[];
};

// Rendering of the stock page from a report. Each tab is a function that returns its element.
import { barChart, lineChart } from "./charts";
import { add, card, h, stat, toneOf } from "./dom";
import { fmt, mult, money, pct, price, shortDate, signedPct, type Kind } from "./format";
import { technicalChart } from "./pricechart";
import { API, compareUrl, tidyName } from "./site";
import type { MultipleKey, Period, Ratios, Reading, Report } from "./types";

const yearLabel = (p: { fiscal_year: string; period: string; date: string }) =>
  p.period === "FY" || p.period === "TTM" ? `FY${p.fiscal_year?.slice(-2) ?? p.date.slice(2, 4)}` : `${p.period} ${p.date.slice(2, 7)}`;

export function header(r: Report): HTMLElement {
  const p = r.profile;
  const el = h("header", "mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between");
  const left = add(
    h("div", "min-w-0"),
    add(h("div", "flex flex-wrap items-baseline gap-x-3"),
      h("h1", "font-serif text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl", tidyName(p.name)),
      h("span", "text-lg font-semibold text-stone-500", r.ticker)),
    h("p", "mt-1 text-sm text-stone-500", [p.sector, p.industry, p.exchange].filter(Boolean).join(" · ")),
  );
  const v = r.valuation;
  const right = add(
    h("div", "flex items-end gap-6"),
    stat("Price", price(v.price), p.change_pct != null ? `${signedPct(p.change_pct / 100, 2)} today` : undefined),
    stat("Market cap", money(v.market_cap)),
    add(h("a", "mb-1 rounded-full border border-stone-300 px-3 py-1.5 text-sm font-medium text-stone-700 hover:border-stone-500"), "Compare…"),
  );
  (right.lastChild as HTMLAnchorElement).href = compareUrl([r.ticker]);
  return add(el, left, right);
}

export function meta(r: Report): HTMLElement {
  const src = Object.entries(r.sources).map(([k, v]) => `${k}: ${v}`).join(" · ");
  const el = h("div", "mt-8 space-y-1 text-xs text-stone-500");
  add(el, h("p", "", `Built ${r.built_utc.slice(0, 16).replace("T", " ")} UTC · ${src}`));
  for (const n of r.notes) el.append(h("p", "text-amber-700", n));
  return el;
}

// --- Overview -----------------------------------------------------------------------------

export function overview(r: Report): HTMLElement {
  const el = h("div", "grid min-w-0 gap-4");
  el.append(readingCard(r));
  const v = r.valuation;
  const last = r.annual_ratios[r.annual_ratios.length - 1];
  const t = r.technical.available ? r.technical.summary : null;
  const f = r.forward.available ? r.forward : null;
  const k = card("Key numbers", `Trailing twelve months (${r.ttm.source_period ?? "last fiscal year"}) and last fiscal year`);
  const grid = h("div", "grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4");
  add(grid,
    stat("Revenue (TTM)", money(r.ttm.revenue)),
    stat("Net income (TTM)", money(r.ttm.net_income)),
    stat("Free cash flow (TTM)", money(r.ttm.free_cash_flow)),
    stat("EPS diluted (TTM)", r.ttm.eps_diluted == null ? "—" : `$${r.ttm.eps_diluted.toFixed(2)}`),
    stat("P/E (TTM)", mult(v.pe)),
    stat("P/E next FY (consensus)", mult(f?.years[0]?.pe ?? null), f ? `FY${f.years[0].fiscal_year}` : undefined),
    stat("EV/EBITDA", mult(v.ev_ebitda)),
    stat("FCF yield", pct(v.fcf_yield)),
    stat("Operating margin", pct(last?.operating_margin), last ? `FY${last.fiscal_year}` : undefined),
    stat("ROIC", pct(last?.roic), last ? `FY${last.fiscal_year}` : undefined),
    stat("Revenue CAGR 5y", pct(r.growth.revenue["5y"])),
    stat("Net debt / EBITDA", mult(last?.net_debt_to_ebitda), last?.net_debt != null && last.net_debt < 0 ? "Net cash" : undefined),
    stat("Return 1y", signedPct(t?.return_1y), undefined, toneOf(t?.return_1y)),
    stat("vs S&P 500 (1y)", signedPct(t?.relative_1y), undefined, toneOf(t?.relative_1y)),
    stat("From 52-week high", signedPct(t?.from_high_52w)),
    stat("Dividend yield", pct(v.dividend_yield)),
  );
  k.body.append(grid);
  el.append(k.el);
  if (r.profile.description) {
    const about = card("About");
    add(about.body, h("p", "text-sm leading-relaxed text-stone-600", r.profile.description));
    const facts = [r.profile.ceo && `CEO ${r.profile.ceo}`, r.profile.employees && `${Math.round(r.profile.employees).toLocaleString("en-US")} employees`, r.profile.country, r.profile.ipo_date && `listed ${shortDate(r.profile.ipo_date)}`].filter(Boolean);
    if (facts.length) about.body.append(h("p", "mt-3 text-xs text-stone-500", facts.join(" · ")));
    el.append(about.el);
  }
  return el;
}

export function renderReading(body: HTMLElement, reading: Reading) {
  body.replaceChildren(
    h("p", "font-serif text-xl leading-snug text-stone-900", reading.headline),
    add(h("div", "mt-5 grid gap-5 sm:grid-cols-2"),
      ...reading.sections.map((s) => add(h("div"), h("h4", "text-sm font-semibold text-stone-900", s.title), h("p", "mt-1 text-sm leading-relaxed text-stone-600", s.body)))),
    reading.points_to_check.length
      ? add(h("div", "mt-5 rounded-xl bg-stone-50 p-4"), h("h4", "text-sm font-semibold text-stone-900", "Points to check"),
          add(h("ul", "mt-2 list-disc space-y-1 pl-5 text-sm text-stone-600"), ...reading.points_to_check.map((p) => h("li", "", p))))
      : "",
    h("p", "mt-4 text-xs text-stone-400", `Written by ${reading.model} on ${reading.read_utc.slice(0, 16).replace("T", " ")} UTC from the numbers on this page. It describes them; it is not advice.`),
  );
}

export function readingCard(r: Report, path = `/api/stock/${encodeURIComponent(r.ticker)}/reading`): HTMLElement {
  const c = card("AI reading", "Claude reads the numbers computed on this page and says what they show. Descriptive only.");
  const button = h("button", "rounded-xl bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700", "Write the reading");
  button.type = "button";
  const status = h("p", "mt-2 text-sm text-stone-500");
  c.body.append(add(h("div"), button, status));
  const load = async (spend: boolean) => {
    button.disabled = true;
    if (spend) status.textContent = "Reading the numbers… (about 15 seconds)";
    try {
      const res = await fetch(`${API}${path}${path.includes("?") ? "&" : "?"}${spend ? "" : "cached_only=1"}`);
      if (res.status === 204) {
        button.disabled = false;
        return;
      }
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "The reading failed.");
      renderReading(c.body, body as Reading);
    } catch (e) {
      button.disabled = false;
      status.textContent = e instanceof Error ? e.message : "The reading failed.";
    }
  };
  button.addEventListener("click", () => load(true));
  load(false); // shows today's reading if someone already asked for it
  return c.el;
}

// --- Fundamentals -------------------------------------------------------------------------

type Row = { label: string; kind: Kind; get: (p: Period, q: Ratios) => number | null | undefined } | { group: string };
const ROWS: Row[] = [
  { group: "Income statement" },
  { label: "Revenue", kind: "money", get: (p) => p.revenue },
  { label: "Gross profit", kind: "money", get: (p) => p.gross_profit },
  { label: "Operating income", kind: "money", get: (p) => p.operating_income },
  { label: "EBITDA", kind: "money", get: (p) => p.ebitda as number | null },
  { label: "Net income", kind: "money", get: (p) => p.net_income },
  { label: "EPS diluted", kind: "price", get: (p) => p.eps_diluted },
  { label: "Diluted shares", kind: "num", get: (p) => (p.shares_diluted == null ? null : p.shares_diluted / 1e6) },
  { group: "Margins" },
  { label: "Gross margin", kind: "pct", get: (_, q) => q.gross_margin },
  { label: "Operating margin", kind: "pct", get: (_, q) => q.operating_margin },
  { label: "Net margin", kind: "pct", get: (_, q) => q.net_margin },
  { label: "FCF margin", kind: "pct", get: (_, q) => q.fcf_margin },
  { label: "R&D / revenue", kind: "pct", get: (_, q) => q.rnd_to_revenue },
  { label: "Stock comp / revenue", kind: "pct", get: (_, q) => q.sbc_to_revenue },
  { group: "Growth (year on year)" },
  { label: "Revenue", kind: "spct", get: (_, q) => q.revenue_growth },
  { label: "EPS diluted", kind: "spct", get: (_, q) => q.eps_growth },
  { label: "Free cash flow", kind: "spct", get: (_, q) => q.fcf_growth },
  { label: "Share count", kind: "spct", get: (_, q) => q.share_count_change },
  { group: "Cash flow" },
  { label: "Operating cash flow", kind: "money", get: (p) => p.operating_cash_flow },
  { label: "Capex", kind: "money", get: (p) => p.capex },
  { label: "Free cash flow", kind: "money", get: (p) => p.free_cash_flow },
  { label: "Dividends paid", kind: "money", get: (p) => p.dividends_paid },
  { label: "Buybacks", kind: "money", get: (p) => p.buybacks },
  { label: "Stock-based comp", kind: "money", get: (p) => p.sbc },
  { group: "Balance sheet" },
  { label: "Cash and short-term investments", kind: "money", get: (p) => (p.cash == null && p.short_term_investments == null ? null : (p.cash ?? 0) + (p.short_term_investments ?? 0)) },
  { label: "Total debt", kind: "money", get: (p) => p.total_debt },
  { label: "Net debt", kind: "money", get: (_, q) => q.net_debt },
  { label: "Total assets", kind: "money", get: (p) => p.total_assets },
  { label: "Shareholders' equity", kind: "money", get: (p) => p.total_equity },
  { group: "Returns and solvency" },
  { label: "ROE", kind: "pct", get: (_, q) => q.roe },
  { label: "ROIC", kind: "pct", get: (_, q) => q.roic },
  { label: "ROA", kind: "pct", get: (_, q) => q.roa },
  { label: "Net debt / EBITDA", kind: "mult", get: (_, q) => q.net_debt_to_ebitda },
  { label: "Current ratio", kind: "num", get: (_, q) => q.current_ratio },
  { label: "Interest coverage", kind: "mult", get: (_, q) => q.interest_coverage },
  { label: "Payout ratio", kind: "pct", get: (_, q) => q.payout_ratio },
];

function table(periods: Period[], ratios: Ratios[]): HTMLElement {
  const wrap = h("div", "overflow-x-auto");
  const t = h("table", "data-table");
  const head = add(h("tr"), h("th", "", ""), ...periods.map((p) => h("th", "", yearLabel(p))));
  const body = h("tbody");
  for (const row of ROWS) {
    if ("group" in row) {
      const td = h("td", "group", row.group);
      td.colSpan = periods.length + 1;
      body.append(add(h("tr"), td));
      continue;
    }
    body.append(add(h("tr"), h("td", "text-stone-700", row.label + (row.label === "Diluted shares" ? " (M)" : "")),
      ...periods.map((p, i) => h("td", "text-stone-900", fmt(row.kind, row.get(p, ratios[i]) ?? null)))));
  }
  add(t, add(h("thead"), head), body);
  return add(wrap, t);
}

export function fundamentals(r: Report): HTMLElement {
  const el = h("div", "grid min-w-0 gap-4");
  const bar = h("div", "flex gap-1");
  const content = h("div", "grid gap-4");
  const draw = (kind: "annual" | "quarter") => {
    const periods = kind === "annual" ? r.annual : r.quarters;
    const ratios = kind === "annual" ? r.annual_ratios : r.quarter_ratios;
    if (!periods.length) return content.replaceChildren(h("p", "text-sm text-stone-500", "No quarterly statements on the current data plan."));
    const labels = periods.map(yearLabel);
    const scale = card("Revenue, net income and free cash flow");
    scale.body.append(barChart(labels, [
      { name: "Revenue", values: periods.map((p) => p.revenue) },
      { name: "Net income", values: periods.map((p) => p.net_income) },
      { name: "Free cash flow", values: periods.map((p) => p.free_cash_flow) },
    ]));
    const margins = card("Margins");
    margins.body.append(lineChart(labels, [
      { name: "Gross", values: ratios.map((q) => q.gross_margin) },
      { name: "Operating", values: ratios.map((q) => q.operating_margin) },
      { name: "Net", values: ratios.map((q) => q.net_margin) },
      { name: "Free cash flow", values: ratios.map((q) => q.fcf_margin) },
    ], "pct"));
    const returns = card("Returns on capital", kind === "quarter" ? "Quarterly figures annualised" : undefined);
    returns.body.append(lineChart(labels, [
      { name: "ROIC", values: ratios.map((q) => q.roic) },
      { name: "ROE", values: ratios.map((q) => q.roe) },
    ], "pct"));
    const cash = card("Where the cash went", "Free cash flow against dividends and buybacks");
    cash.body.append(barChart(labels, [
      { name: "Free cash flow", values: periods.map((p) => p.free_cash_flow) },
      { name: "Dividends", values: periods.map((p) => p.dividends_paid) },
      { name: "Buybacks", values: periods.map((p) => p.buybacks) },
    ]));
    const all = card(kind === "annual" ? "Annual statements" : "Quarterly statements");
    all.body.append(table(periods, ratios));
    const g = r.growth;
    const growth = card("Compound annual growth");
    const gt = h("table", "data-table");
    add(gt, add(h("thead"), add(h("tr"), h("th", "", ""), h("th", "", "3 years"), h("th", "", "5 years"), h("th", "", "10 years"))),
      add(h("tbody"), ...([["Revenue", g.revenue], ["EPS diluted", g.eps_diluted], ["Net income", g.net_income], ["Free cash flow", g.free_cash_flow]] as const).map(([name, v]) =>
        add(h("tr"), h("td", "", name), h("td", "", pct(v["3y"])), h("td", "", pct(v["5y"])), h("td", "", pct(v["10y"]))))));
    growth.body.append(add(h("div", "overflow-x-auto"), gt));
    content.replaceChildren(
      add(h("div", "grid min-w-0 gap-4 lg:grid-cols-2"), scale.el, margins.el, returns.el, cash.el),
      kind === "annual" ? growth.el : "",
      all.el,
    );
  };
  const buttons = (["annual", "quarter"] as const).map((k) => {
    const b = h("button", "tab-btn", k === "annual" ? "Annual" : "Quarterly");
    b.type = "button";
    b.addEventListener("click", () => {
      buttons.forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      draw(k);
    });
    return b;
  });
  buttons[0].setAttribute("aria-selected", "true");
  bar.append(...buttons);
  draw("annual");
  return add(el, bar, content);
}

// --- Valuation and forward multiples ------------------------------------------------------

const MULTIPLES: { key: MultipleKey; label: string }[] = [
  { key: "pe", label: "P/E" },
  { key: "ev_ebitda", label: "EV/EBITDA" },
  { key: "ev_sales", label: "EV/Sales" },
  { key: "p_fcf", label: "P/FCF" },
];

export function valuation(r: Report): HTMLElement {
  const el = h("div", "grid min-w-0 gap-4");
  const v = r.valuation;
  const today = card("Valuation today", `At ${price(v.price)}, on the trailing twelve months`);
  add(today.body, add(h("div", "grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4"),
    stat("P/E", mult(v.pe)), stat("EV/EBITDA", mult(v.ev_ebitda)), stat("EV/Sales", mult(v.ev_sales)), stat("P/FCF", mult(v.p_fcf)),
    stat("P/Book", mult(v.p_book)), stat("EV/EBIT", mult(v.ev_ebit)), stat("Earnings yield", pct(v.earnings_yield)), stat("FCF yield", pct(v.fcf_yield)),
    stat("Dividend yield", pct(v.dividend_yield)), stat("Buyback yield", pct(v.buyback_yield)), stat("Enterprise value", money(v.enterprise_value)), stat("Net debt", money(v.net_debt), v.net_debt != null && v.net_debt < 0 ? "Net cash" : undefined),
  ));
  el.append(today.el);

  // History, today and the consensus years on one line, per multiple.
  const f = r.forward.available ? r.forward : null;
  const path = card("Multiples through time", "At each fiscal year end, today (TTM), and at today's price on the consensus for the coming years (dashed)");
  const picker = h("div", "mb-3 flex flex-wrap gap-1");
  const chartBox = h("div");
  const note = h("p", "mt-3 text-sm text-stone-600");
  const draw = (key: MultipleKey) => {
    const hist = r.history.years;
    const labels = [...hist.map((y) => `FY${y.fiscal_year.slice(-2)}`), "Today"];
    const values: (number | null)[] = [...hist.map((y) => y[key]), v[key]];
    let dashedFrom: number | undefined;
    if (f && key !== "p_fcf") {
      dashedFrom = labels.length - 1;
      for (const y of f.years) {
        labels.push(`FY${y.fiscal_year.slice(-2)}e`);
        values.push(y[key as "pe" | "ev_ebitda" | "ev_sales"]);
      }
    }
    const med = r.history.summary[key]?.median;
    chartBox.replaceChildren(lineChart(labels, [{ name: MULTIPLES.find((m) => m.key === key)!.label, values, dashedFrom }], "mult",
      med != null ? { value: med, label: "Median" } : undefined));
    const s = r.history.summary[key];
    const next = f && key !== "p_fcf" ? f.years[0]?.[key as "pe"] : null;
    note.textContent = s?.median != null
      ? `${MULTIPLES.find((m) => m.key === key)!.label} ranged from ${mult(s.min)} to ${mult(s.max)} over ${s.years} fiscal year ends (median ${mult(s.median)}). Today: ${mult(v[key])}.` +
        (next != null ? ` On the consensus for FY${f!.years[0].fiscal_year}, at today's price: ${mult(next)}.` : "")
      : "Not enough history to compute this multiple.";
  };
  const buttons = MULTIPLES.map((m) => {
    const b = h("button", "tab-btn", m.label);
    b.type = "button";
    b.addEventListener("click", () => {
      buttons.forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      draw(m.key);
    });
    return b;
  });
  buttons[0].setAttribute("aria-selected", "true");
  picker.append(...buttons);
  add(path.body, picker, chartBox, note);
  draw("pe");
  el.append(path.el);

  const fw = card("Consensus years", f ? f.note : undefined);
  if (!f) {
    fw.body.append(h("p", "text-sm text-stone-500", (r.forward as { reason: string }).reason));
  } else {
    const t = h("table", "data-table");
    const cols = f.years;
    const row = (label: string, cells: string[]) => add(h("tr"), h("td", "text-stone-700", label), ...cells.map((c) => h("td", "text-stone-900", c)));
    add(t,
      add(h("thead"), add(h("tr"), h("th", "", ""), ...cols.map((y) => h("th", "", `FY${y.fiscal_year} (${shortDate(y.fiscal_year_end)})`)))),
      add(h("tbody"),
        row("Analysts (EPS)", cols.map((y) => (y.analysts == null ? "—" : String(Math.round(y.analysts))))),
        row("EPS consensus", cols.map((y) => price(y.eps))),
        row("EPS range", cols.map((y) => `${price(y.eps_low)} – ${price(y.eps_high)}`)),
        row("EPS growth", cols.map((y) => signedPct(y.eps_growth))),
        row("Revenue consensus", cols.map((y) => money(y.revenue))),
        row("Revenue growth", cols.map((y) => signedPct(y.revenue_growth))),
        row("Net margin implied", cols.map((y) => pct(y.net_margin))),
        row("P/E at today's price", cols.map((y) => mult(y.pe))),
        row("P/E range", cols.map((y) => `${mult(y.pe_low)} – ${mult(y.pe_high)}`)),
        row("EV/EBITDA", cols.map((y) => mult(y.ev_ebitda))),
        row("EV/Sales", cols.map((y) => mult(y.ev_sales))),
      ));
    add(fw.body, add(h("div", "overflow-x-auto"), t),
      add(h("div", "mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4"),
        stat("EPS CAGR (consensus)", pct(f.eps_cagr), `to FY${cols[cols.length - 1].fiscal_year}`),
        stat("Revenue CAGR (consensus)", pct(f.revenue_cagr)),
        stat("PEG", f.peg == null ? "—" : f.peg.toFixed(2), "next FY P/E ÷ EPS CAGR"),
        stat("Next FY P/E vs median", signedPct(f.vs_history.pe.next_year_vs_median), "against its own history"),
      ));
  }
  el.append(fw.el);
  return el;
}

// --- Technical ----------------------------------------------------------------------------

export function technical(r: Report): HTMLElement {
  const el = h("div", "grid min-w-0 gap-4");
  if (!r.technical.available) return add(el, h("p", "text-sm text-stone-500", r.technical.reason));
  const { summary: s, levels, series } = r.technical;
  const chips = h("div", "flex flex-wrap gap-2");
  const tone = { up: "bg-emerald-50 text-emerald-800 border-emerald-200", down: "bg-rose-50 text-rose-800 border-rose-200", warn: "bg-amber-50 text-amber-800 border-amber-200", neutral: "bg-stone-100 text-stone-700 border-stone-200" };
  for (const st of s.states) chips.append(h("span", `rounded-full border px-3 py-1 text-xs font-medium ${tone[st.tone]}`, st.label));
  const top = card("Where the indicators stand", `Close of ${shortDate(s.date)}. Descriptions of past price behaviour, not signals.`);
  top.body.append(chips);
  el.append(top.el);

  const chart = card("Price and indicators");
  chart.body.append(technicalChart(series));
  el.append(chart.el);

  const stats = card("Performance and risk");
  add(stats.body, add(h("div", "grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4"),
    stat("1 month", signedPct(s.return_1m), undefined, toneOf(s.return_1m)),
    stat("3 months", signedPct(s.return_3m), undefined, toneOf(s.return_3m)),
    stat("Year to date", signedPct(s.return_ytd), undefined, toneOf(s.return_ytd)),
    stat("1 year", signedPct(s.return_1y), s.benchmark_return_1y != null ? `S&P 500 ${signedPct(s.benchmark_return_1y)}` : undefined, toneOf(s.return_1y)),
    stat("3 years", signedPct(s.return_3y), undefined, toneOf(s.return_3y)),
    stat("Volatility (1y, annualised)", pct(s.volatility_1y)),
    stat("Max drawdown (1y)", pct(s.max_drawdown_1y)),
    stat("Beta vs S&P 500 (1y)", s.beta_1y == null ? "—" : s.beta_1y.toFixed(2), s.correlation_1y != null ? `correlation ${s.correlation_1y.toFixed(2)}` : undefined),
    stat("52-week range", `${price(s.low_52w)} – ${price(s.high_52w)}`),
    stat("RSI (14)", s.rsi14 == null ? "—" : s.rsi14.toFixed(0)),
    stat("ATR (14)", price(s.atr14), s.atr_pct != null ? `${pct(s.atr_pct)} of price` : undefined),
    stat("Volume vs 50-day avg", s.volume_vs_avg50 == null ? "—" : `${s.volume_vs_avg50.toFixed(2)}×`),
  ));
  el.append(stats.el);

  const lv = card("Swing levels", "Prices where the stock turned in the last six months, grouped when within 1.5% of each other. More touches, more often the price turned there.");
  const list = (title: string, items: typeof levels.supports) => add(h("div"), h("h4", "mb-2 text-sm font-semibold text-stone-900", title),
    items.length ? add(h("ul", "space-y-1 text-sm"), ...items.map((l) => add(h("li", "flex justify-between gap-4 tabular-nums"),
      h("span", "font-medium text-stone-900", price(l.level)), h("span", "text-stone-500", `${signedPct(l.distance)} · ${l.touches} touch${l.touches > 1 ? "es" : ""}`))))
      : h("p", "text-sm text-stone-500", "None in the last six months."));
  add(lv.body, add(h("div", "grid gap-6 sm:grid-cols-2"), list("Below the price", levels.supports), list("Above the price", levels.resistances)));
  el.append(lv.el);
  return el;
}

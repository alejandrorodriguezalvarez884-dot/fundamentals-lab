// Price charts on lightweight-charts: candles with averages and bands, volume, RSI and MACD in
// their own panes; and the rebased lines of the comparison.
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { add, h } from "./dom";
import { SERIES } from "./charts";
import type { Series } from "./types";

const UP = "#15803d";
const DOWN = "#be123c";

const base = (el: HTMLElement, height: number) =>
  createChart(el, {
    height,
    autoSize: true,
    layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#78716c", fontFamily: "Inter, system-ui, sans-serif", fontSize: 11, panes: { separatorColor: "#e7e5e4" } },
    grid: { vertLines: { color: "#f5f5f4" }, horzLines: { color: "#f5f5f4" } },
    rightPriceScale: { borderColor: "#e7e5e4" },
    timeScale: { borderColor: "#e7e5e4" },
    crosshair: { mode: CrosshairMode.Normal },
  });

function line(values: (number | null)[], dates: string[]) {
  const out: { time: Time; value: number }[] = [];
  values.forEach((v, i) => {
    if (v !== null) out.push({ time: dates[i] as Time, value: v });
  });
  return out;
}

const RANGES: [string, number][] = [["3M", 63], ["6M", 126], ["1Y", 252], ["3Y", 756], ["5Y", 100000]];

function rangeButtons(chart: IChartApi, n: number, initial = "1Y"): HTMLElement {
  const bar = h("div", "flex gap-1");
  const buttons: HTMLButtonElement[] = [];
  const pick = (label: string, sessions: number) => {
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - sessions), to: n - 1 + 3 });
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === label)));
  };
  for (const [label, sessions] of RANGES) {
    const b = h("button", "range-btn", label);
    b.type = "button";
    b.addEventListener("click", () => pick(label, sessions));
    buttons.push(b);
    bar.append(b);
  }
  requestAnimationFrame(() => pick(initial, RANGES.find((r) => r[0] === initial)![1]));
  return bar;
}

function toggle(label: string, on: boolean, change: (on: boolean) => void, color: string): HTMLElement {
  const lab = h("label", "inline-flex cursor-pointer items-center gap-1.5 text-xs text-stone-600");
  const box = h("input") as HTMLInputElement;
  box.type = "checkbox";
  box.checked = on;
  box.className = "accent-stone-800";
  box.addEventListener("change", () => change(box.checked));
  const sw = h("span", "inline-block h-[3px] w-4 rounded-full");
  sw.style.background = color;
  return add(lab, box, sw, label);
}

export function technicalChart(s: Series): HTMLElement {
  const wrap = h("div");
  const controls = h("div", "mb-3 flex flex-wrap items-center justify-between gap-3");
  const el = h("div", "w-full");
  el.style.height = "640px";
  add(wrap, controls, el);
  const chart = base(el, 640);
  const dates = s.date;

  const candles = chart.addSeries(CandlestickSeries, { upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN, priceLineVisible: false });
  candles.setData(dates.map((d, i) => ({ time: d as Time, open: s.open[i]!, high: s.high[i]!, low: s.low[i]!, close: s.close[i]! })));

  const overlay = (values: (number | null)[], color: string, style = LineStyle.Solid, visible = true) => {
    const series = chart.addSeries(LineSeries, { color, lineWidth: 2, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, visible });
    series.setData(line(values, dates));
    return series;
  };
  const sma50 = overlay(s.sma50, SERIES[0]);
  const sma200 = overlay(s.sma200, SERIES[1]);
  const bbU = overlay(s.bb_upper, "#a8a29e", LineStyle.Dashed, false);
  const bbL = overlay(s.bb_lower, "#a8a29e", LineStyle.Dashed, false);

  const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false }, 1);
  volume.setData(dates.map((d, i) => ({ time: d as Time, value: s.volume[i] ?? 0, color: (s.close[i] ?? 0) >= (s.open[i] ?? 0) ? "#86efac" : "#fda4af" })));

  const rsi = chart.addSeries(LineSeries, { color: "#4a3aa7", lineWidth: 2, priceLineVisible: false }, 2);
  rsi.setData(line(s.rsi14, dates));
  for (const level of [70, 30]) rsi.createPriceLine({ price: level, color: "#a8a29e", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "" });

  const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 3);
  hist.setData(dates.flatMap((d, i) => (s.macd_hist[i] === null ? [] : [{ time: d as Time, value: s.macd_hist[i]!, color: s.macd_hist[i]! >= 0 ? "#86efac" : "#fda4af" }])));
  const macdLine = chart.addSeries(LineSeries, { color: SERIES[0], lineWidth: 2, priceLineVisible: false, lastValueVisible: false }, 3);
  macdLine.setData(line(s.macd, dates));
  const signal = chart.addSeries(LineSeries, { color: SERIES[1], lineWidth: 2, priceLineVisible: false, lastValueVisible: false }, 3);
  signal.setData(line(s.macd_signal, dates));

  // Pane heights only hold once the chart has its size, so set them after it is laid out.
  const sizePanes = () => {
    const panes = chart.panes();
    if (panes.length < 4) return;
    panes[1].setHeight(70);
    panes[2].setHeight(110);
    panes[3].setHeight(110);
  };
  new ResizeObserver(sizePanes).observe(el);

  const show = (series: ISeriesApi<"Line">[]) => (on: boolean) => series.forEach((x) => x.applyOptions({ visible: on }));
  const toggles = add(
    h("div", "flex flex-wrap items-center gap-x-4 gap-y-1"),
    toggle("50-day average", true, show([sma50]), SERIES[0]),
    toggle("200-day average", true, show([sma200]), SERIES[1]),
    toggle("Bollinger bands (20, 2)", false, show([bbU, bbL]), "#a8a29e"),
  );
  add(controls, toggles, rangeButtons(chart, dates.length));
  const panesLegend = add(
    h("div", "mt-2 flex flex-wrap gap-x-4 text-xs text-stone-500"),
    h("span", "", "Panes, top to bottom: price · volume · RSI (14) with 30 and 70 · MACD (12, 26, 9): MACD blue, signal orange, histogram"),
  );
  wrap.append(panesLegend);
  return wrap;
}

export function compareChart(dates: string[], series: Record<string, number[]>, tickers: string[]): HTMLElement {
  const wrap = h("div");
  const legend = h("div", "mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-600");
  const el = h("div", "w-full");
  el.style.height = "340px";
  add(wrap, legend, el);
  const chart = base(el, 340);
  tickers.forEach((t, k) => {
    if (!series[t]) return;
    const color = SERIES[k];
    const s = chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false, title: t });
    s.setData(series[t].map((v, i) => ({ time: dates[i] as Time, value: v })));
    const sw = h("span", "inline-block h-[3px] w-4 rounded-full");
    sw.style.background = color;
    add(legend, add(h("span", "inline-flex items-center gap-1.5 font-medium"), sw, t));
  });
  const base100 = chart.addSeries(LineSeries, { color: "#a8a29e", lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  if (dates.length) base100.setData([{ time: dates[0] as Time, value: 100 }, { time: dates[dates.length - 1] as Time, value: 100 }]);
  // Fit once the chart has its width; fitting a zero-width chart leaves the lines squeezed.
  const fit = new ResizeObserver(() => {
    if (el.clientWidth) chart.timeScale().fitContent();
  });
  fit.observe(el);
  return wrap;
}

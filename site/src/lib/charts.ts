// Small SVG charts (bars by period, lines with a dashed forecast part, a labelled scatter), with
// a hover tooltip. Dark theme, like the rest of the site.
import { add, h, svg } from "./dom";
import { fmt, type Kind } from "./format";

// Categorical slots in fixed order (validated palette from the dataviz reference).
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"];
const GRID = "#2a2e39";
const AXIS_TEXT = "#868993";

export type BarSeries = { name: string; values: (number | null)[]; color?: string };
export type LineSeries = {
  name: string;
  values: (number | null)[];
  color?: string;
  // Indexes from which the line is drawn dashed (consensus years).
  dashedFrom?: number;
};

type Frame = { width: number; height: number; left: number; right: number; top: number; bottom: number };
let FRAME: Frame = { width: 640, height: 260, left: 52, right: 12, top: 12, bottom: 28 };

// Charts are drawn at their real pixel width, so text stays at 11px on every screen, and redrawn
// when the box changes size.
function responsive(draw: () => HTMLElement): HTMLElement {
  const host = h("div", "w-full");
  let last = 0;
  const render = () => {
    const width = Math.round(host.clientWidth);
    if (!width || width === last) return;
    last = width;
    FRAME = { width, height: width < 480 ? 220 : 260, left: 52, right: 12, top: 12, bottom: 28 };
    host.replaceChildren(draw());
  };
  new ResizeObserver(render).observe(host);
  return host;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    max = min + 1;
  }
  const span = max - min;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

function frame(): { root: HTMLElement; plot: SVGSVGElement; tip: HTMLElement } {
  const root = h("div", "chart relative");
  const plot = svg("svg", { viewBox: `0 0 ${FRAME.width} ${FRAME.height}`, width: FRAME.width, height: FRAME.height, class: "block overflow-visible", role: "img" });
  const tip = h("div", "chart-tip");
  tip.hidden = true;
  add(root, plot, tip);
  return { root, plot, tip };
}

function legend(items: { name: string; color: string; dashed?: boolean }[]): HTMLElement {
  const el = h("div", "mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted");
  for (const it of items) {
    const sw = h("span", "inline-block h-[3px] w-4 rounded-full align-middle");
    sw.style.background = it.dashed ? `repeating-linear-gradient(90deg, ${it.color} 0 4px, transparent 4px 7px)` : it.color;
    add(el, add(h("span", "inline-flex items-center gap-1.5"), sw, it.name));
  }
  return el;
}

function yAxis(plot: SVGSVGElement, ticks: number[], y: (v: number) => number, kind: Kind) {
  for (const t of ticks) {
    const yy = y(t);
    plot.append(svg("line", { x1: FRAME.left, x2: FRAME.width - FRAME.right, y1: yy, y2: yy, stroke: t === 0 ? "#5d606b" : GRID, "stroke-width": 1 }));
    const label = svg("text", { x: FRAME.left - 8, y: yy + 4, "text-anchor": "end", "font-size": 11, fill: AXIS_TEXT });
    label.textContent = fmt(kind, t);
    plot.append(label);
  }
}

function xLabels(plot: SVGSVGElement, labels: string[], x: (i: number) => number) {
  const every = Math.ceil(labels.length / Math.max(3, Math.floor((FRAME.width - FRAME.left) / 56)));
  labels.forEach((l, i) => {
    if (i % every !== 0 && i !== labels.length - 1) return;
    const t = svg("text", { x: x(i), y: FRAME.height - 8, "text-anchor": "middle", "font-size": 11, fill: AXIS_TEXT });
    t.textContent = l;
    plot.append(t);
  });
}

function tooltip(plot: SVGSVGElement, tip: HTMLElement, n: number, x: (i: number) => number,
                 render: (i: number) => (string | HTMLElement)[], onHover?: (i: number | null) => void) {
  const hit = svg("rect", { x: FRAME.left, y: FRAME.top, width: FRAME.width - FRAME.left - FRAME.right, height: FRAME.height - FRAME.top - FRAME.bottom, fill: "transparent" });
  plot.append(hit);
  const move = (e: PointerEvent) => {
    const box = plot.getBoundingClientRect();
    const vx = ((e.clientX - box.left) / box.width) * FRAME.width;
    let best = 0;
    for (let i = 1; i < n; i++) if (Math.abs(x(i) - vx) < Math.abs(x(best) - vx)) best = i;
    tip.replaceChildren(...render(best));
    tip.hidden = false;
    const px = (x(best) / FRAME.width) * box.width;
    tip.style.left = `${Math.min(Math.max(px, 70), box.width - 70)}px`;
    onHover?.(best);
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerleave", () => ((tip.hidden = true), onHover?.(null)));
}

function tipRow(name: string, value: string, color?: string): HTMLElement {
  const row = h("div", "flex items-center justify-between gap-4");
  const left = h("span", "inline-flex items-center gap-1.5 text-muted");
  if (color) {
    const dot = h("span", "inline-block h-2 w-2 rounded-full");
    dot.style.background = color;
    left.append(dot);
  }
  left.append(name);
  return add(row, left, h("span", "font-semibold tabular-nums text-ink-strong", value));
}

// Grouped bars: one group per period, one bar per series.
export const barChart = (labels: string[], series: BarSeries[], kind: Kind = "money") =>
  responsive(() => drawBars(labels, series, kind));

function drawBars(labels: string[], series: BarSeries[], kind: Kind): HTMLElement {
  const { root, plot, tip } = frame();
  const all = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  if (!all.length) return h("p", "text-sm text-muted", "No data.");
  const ticks = niceTicks(Math.min(0, ...all), Math.max(0, ...all));
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const innerH = FRAME.height - FRAME.top - FRAME.bottom;
  const y = (v: number) => FRAME.top + ((hi - v) / (hi - lo)) * innerH;
  const innerW = FRAME.width - FRAME.left - FRAME.right;
  const band = innerW / labels.length;
  const x = (i: number) => FRAME.left + band * (i + 0.5);
  yAxis(plot, ticks, y, kind);
  const gap = 2;
  const barW = Math.max(3, Math.min(28, (band * 0.72 - gap * (series.length - 1)) / series.length));
  const groupW = barW * series.length + gap * (series.length - 1);
  series.forEach((s, k) => {
    const color = s.color ?? SERIES[k];
    s.values.forEach((v, i) => {
      if (v === null) return;
      const x0 = x(i) - groupW / 2 + k * (barW + gap);
      const y0 = y(Math.max(v, 0)), y1 = y(Math.min(v, 0));
      const r = Math.min(4, barW / 2, (y1 - y0) / 2);
      // Rounded on the data end, square on the baseline.
      const path = v >= 0
        ? `M${x0},${y1} V${y0 + r} Q${x0},${y0} ${x0 + r},${y0} H${x0 + barW - r} Q${x0 + barW},${y0} ${x0 + barW},${y0 + r} V${y1} Z`
        : `M${x0},${y0} V${y1 - r} Q${x0},${y1} ${x0 + r},${y1} H${x0 + barW - r} Q${x0 + barW},${y1} ${x0 + barW},${y1 - r} V${y0} Z`;
      plot.append(svg("path", { d: path, fill: color }));
    });
  });
  xLabels(plot, labels, x);
  tooltip(plot, tip, labels.length, x, (i) => [
    h("div", "mb-1 font-medium text-ink-strong", labels[i]),
    ...series.map((s, k) => tipRow(s.name, fmt(kind, s.values[i]), s.color ?? SERIES[k])),
  ]);
  return add(h("div"), series.length > 1 ? legend(series.map((s, k) => ({ name: s.name, color: s.color ?? SERIES[k] }))) : null, root);
}

// Lines over periods. A series can turn dashed from an index on (the consensus years), and a
// horizontal reference (the historical median) can be drawn.
export const lineChart = (labels: string[], series: LineSeries[], kind: Kind = "pct", reference?: { value: number; label: string }) =>
  responsive(() => drawLines(labels, series, kind, reference));

function drawLines(labels: string[], series: LineSeries[], kind: Kind, reference?: { value: number; label: string }): HTMLElement {
  const { root, plot, tip } = frame();
  const all = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  if (reference) all.push(reference.value);
  if (!all.length) return h("p", "text-sm text-muted", "No data.");
  const minV = Math.min(...all), maxV = Math.max(...all);
  const pad = (maxV - minV) * 0.08 || Math.abs(maxV) * 0.1 || 1;
  const ticks = niceTicks(kind === "mult" ? Math.max(0, minV - pad) : minV - pad, maxV + pad);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const innerH = FRAME.height - FRAME.top - FRAME.bottom;
  const y = (v: number) => FRAME.top + ((hi - v) / (hi - lo)) * innerH;
  const innerW = FRAME.width - FRAME.left - FRAME.right;
  const x = (i: number) => FRAME.left + (labels.length === 1 ? innerW / 2 : (innerW * i) / (labels.length - 1));
  yAxis(plot, ticks, y, kind);
  if (reference) {
    const yy = y(reference.value);
    plot.append(svg("line", { x1: FRAME.left, x2: FRAME.width - FRAME.right, y1: yy, y2: yy, stroke: "#868993", "stroke-width": 1, "stroke-dasharray": "2 3" }));
    const t = svg("text", { x: FRAME.left + 6, y: yy - 6, "text-anchor": "start", "font-size": 11, fill: "#d1d4dc", "paint-order": "stroke", stroke: "#1e222d", "stroke-width": 3 });
    t.textContent = `${reference.label} ${fmt(kind, reference.value)}`;
    plot.append(t);
  }
  const markers: SVGCircleElement[][] = [];
  series.forEach((s, k) => {
    const color = s.color ?? SERIES[k];
    const segments: { d: string; dashed: boolean }[] = [];
    let prev: number | null = null;
    s.values.forEach((v, i) => {
      if (v === null) {
        prev = null;
        return;
      }
      if (prev !== null) {
        const dashed = s.dashedFrom !== undefined && i > s.dashedFrom;
        segments.push({ d: `M${x(prev)},${y(s.values[prev]!)} L${x(i)},${y(v)}`, dashed });
      }
      prev = i;
    });
    for (const seg of segments) {
      plot.append(svg("path", { d: seg.d, stroke: color, "stroke-width": 2, fill: "none", "stroke-linecap": "round", ...(seg.dashed ? { "stroke-dasharray": "5 4" } : {}) }));
    }
    const dots: SVGCircleElement[] = [];
    s.values.forEach((v, i) => {
      const c = svg("circle", { cx: x(i), cy: v === null ? -100 : y(v), r: 4, fill: s.dashedFrom !== undefined && i > s.dashedFrom ? "#1e222d" : color, stroke: color, "stroke-width": 2 });
      c.style.opacity = labels.length <= 16 ? "1" : "0";
      if (v === null) c.style.display = "none";
      plot.append(c);
      dots.push(c);
    });
    markers.push(dots);
  });
  xLabels(plot, labels, x);
  const cross = svg("line", { y1: FRAME.top, y2: FRAME.height - FRAME.bottom, stroke: "#5d606b", "stroke-width": 1 });
  cross.style.display = "none";
  plot.append(cross);
  tooltip(plot, tip, labels.length, x, (i) => [
    h("div", "mb-1 font-medium text-ink-strong", labels[i]),
    ...series.map((s, k) => tipRow(s.dashedFrom !== undefined && i > s.dashedFrom ? `${s.name} (consensus)` : s.name, fmt(kind, s.values[i]), s.color ?? SERIES[k])),
  ], (i) => {
    cross.style.display = i === null ? "none" : "";
    if (i !== null) cross.setAttribute("x1", String(x(i))), cross.setAttribute("x2", String(x(i)));
    markers.forEach((dots) => dots.forEach((d, j) => d.setAttribute("r", j === i ? "5.5" : "4")));
  });
  const items = series.map((s, k) => ({ name: s.name, color: s.color ?? SERIES[k] }));
  const dashedNote = series.some((s) => s.dashedFrom !== undefined)
    ? [{ name: "Analysts' consensus at today's price", color: "#868993", dashed: true }]
    : [];
  return add(h("div"), items.length > 1 || dashedNote.length ? legend([...(items.length > 1 ? items : []), ...dashedNote]) : null, root);
}

// A scatter with each point labelled by its ticker (identity never rests on colour alone).
export const scatter = (points: { label: string; x: number | null; y: number | null; color: string }[],
                        xName: string, yName: string, xKind: Kind, yKind: Kind) =>
  responsive(() => drawScatter(points, xName, yName, xKind, yKind));

function drawScatter(points: { label: string; x: number | null; y: number | null; color: string }[],
                        xName: string, yName: string, xKind: Kind, yKind: Kind): HTMLElement {
  const ok = points.filter((p) => p.x !== null && p.y !== null) as { label: string; x: number; y: number; color: string }[];
  if (ok.length < 2) return h("p", "text-sm text-muted", "Not enough data for this chart.");
  const { root, plot, tip } = frame();
  const xs = ok.map((p) => p.x), ys = ok.map((p) => p.y);
  const padX = (Math.max(...xs) - Math.min(...xs)) * 0.15 || 0.05;
  const padY = (Math.max(...ys) - Math.min(...ys)) * 0.15 || 1;
  const xt = niceTicks(Math.min(...xs) - padX, Math.max(...xs) + padX);
  const yt = niceTicks(Math.min(...ys) - padY, Math.max(...ys) + padY);
  const innerW = FRAME.width - FRAME.left - FRAME.right, innerH = FRAME.height - FRAME.top - FRAME.bottom - 14;
  const x = (v: number) => FRAME.left + ((v - xt[0]) / (xt[xt.length - 1] - xt[0])) * innerW;
  const y = (v: number) => FRAME.top + ((yt[yt.length - 1] - v) / (yt[yt.length - 1] - yt[0])) * innerH;
  yAxis(plot, yt, y, yKind);
  for (const t of xt) {
    const label = svg("text", { x: x(t), y: FRAME.height - 22, "text-anchor": "middle", "font-size": 11, fill: AXIS_TEXT });
    label.textContent = fmt(xKind, t);
    plot.append(label);
  }
  const xl = svg("text", { x: FRAME.left + innerW / 2, y: FRAME.height - 4, "text-anchor": "middle", "font-size": 11, fill: "#868993" });
  xl.textContent = xName;
  plot.append(xl);
  for (const p of ok) {
    const g = svg("g");
    g.append(svg("circle", { cx: x(p.x), cy: y(p.y), r: 6, fill: p.color, stroke: "#1e222d", "stroke-width": 2 }));
    const t = svg("text", { x: x(p.x) + 10, y: y(p.y) + 4, "font-size": 12, "font-weight": 600, fill: "#f0f3fa" });
    t.textContent = p.label;
    g.append(t);
    const hit = svg("circle", { cx: x(p.x), cy: y(p.y), r: 16, fill: "transparent" });
    hit.addEventListener("pointerenter", () => {
      tip.replaceChildren(h("div", "mb-1 font-medium text-ink-strong", p.label), tipRow(xName, fmt(xKind, p.x)), tipRow(yName, fmt(yKind, p.y)));
      tip.hidden = false;
      tip.style.left = `${(x(p.x) / FRAME.width) * plot.getBoundingClientRect().width}px`;
    });
    hit.addEventListener("pointerleave", () => (tip.hidden = true));
    g.append(hit);
    plot.append(g);
  }
  return add(h("div"), h("div", "mb-2 text-xs text-muted", yName), root);
}

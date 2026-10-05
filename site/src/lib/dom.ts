// Tiny DOM helpers. Everything that comes from the API or the address bar goes in as text, never
// as markup.
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function add<T extends Element>(parent: T, ...children: (Node | string | null | undefined | false)[]): T {
  for (const c of children) if (c) parent.append(c);
  return parent;
}

export function svg<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}): SVGElementTagNameMap[K] {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

// A titled card: the building block of every section.
export function card(title: string, subtitle?: string, cls = ""): { el: HTMLElement; body: HTMLElement } {
  const el = h("section", `min-w-0 rounded-2xl border border-stone-200 bg-white p-4 sm:p-6 ${cls}`);
  const head = add(h("header", "mb-4"), h("h3", "font-serif text-lg font-semibold text-stone-900", title));
  if (subtitle) head.append(h("p", "mt-1 text-sm text-stone-500", subtitle));
  const body = h("div");
  add(el, head, body);
  return { el, body };
}

// A small figure: label above, value below.
export function stat(label: string, value: string, note?: string, tone: "up" | "down" | "" = ""): HTMLElement {
  const color = tone === "up" ? "text-emerald-700" : tone === "down" ? "text-rose-700" : "text-stone-900";
  return add(
    h("div", "min-w-0"),
    h("div", "text-xs font-medium uppercase tracking-wide text-stone-500", label),
    h("div", `mt-1 text-xl font-semibold tabular-nums ${color}`, value),
    note ? h("div", "mt-0.5 text-xs text-stone-500", note) : null,
  );
}

export const toneOf = (v: number | null | undefined): "up" | "down" | "" =>
  typeof v === "number" ? (v > 0 ? "up" : v < 0 ? "down" : "") : "";

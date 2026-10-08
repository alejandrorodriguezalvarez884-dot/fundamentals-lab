// Site-wide constants and links.
export const SITE_NAME = "Fundamentals Lab";
export const REPO_URL = "https://github.com/alejandrorodriguezalvarez884-dot/fundamentals-lab";
export const AUTHOR_URL = "https://alejandrorodriguez.dev/";

// The tool is a section of Market Hub: its header is the portal's, and a company's page links to
// the same company in the portal and in the Earnings Radar.
const site = (v: string | undefined, fallback: string) => (v ?? fallback).replace(/\/$/, "");
export const HUB_URL = site(import.meta.env.PUBLIC_HUB_URL, "https://themarkethub.app");
export const RADAR_URL = site(import.meta.env.PUBLIC_RADAR_URL, "https://radar.themarkethub.app");
export const PEERS_URL = site(import.meta.env.PUBLIC_PEERS_URL, "https://peers.themarkethub.app");
export const PLAYGROUND_URL = site(import.meta.env.PUBLIC_PLAYGROUND_URL, "https://playground.themarkethub.app");
export const hubQuoteUrl = (ticker: string) => `${HUB_URL}/quote/?t=${encodeURIComponent(ticker)}`;
export const radarUrl = (ticker: string) => `${RADAR_URL}/analyze/?ticker=${encodeURIComponent(ticker)}`;

// Every internal link goes through here, so the site works under a sub-path too.
export function link(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}${path}`;
}

// The API lives on the same origin in production; in development it is another port.
export const API = (import.meta.env.PUBLIC_API_URL ?? "").replace(/\/$/, "");

export const stockUrl = (ticker: string) => `${link("/stock/")}?t=${encodeURIComponent(ticker)}`;
export const compareUrl = (tickers: string[]) => `${link("/compare/")}?t=${tickers.map(encodeURIComponent).join(",")}`;

// Company names as the SEC writes them ("APPLE INC") read better in title case.
export function tidyName(name: string): string {
  if (name !== name.toUpperCase()) return name;
  const keep = new Set(["LLC", "PLC", "NV", "SA", "AG", "SE", "LP", "ETF", "REIT", "USA", "II", "III"]);
  return name
    .toLowerCase()
    .split(/(\s+|-|\/)/)
    .map((w) => (keep.has(w.toUpperCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join("")
    .replace(/\b(Inc|Corp|Co|Ltd)\b(?!\.)/g, "$1.");
}

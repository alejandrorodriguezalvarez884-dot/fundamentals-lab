"""Command line: build a report or a reading on this machine, without the web.

    fundamentals search apple
    fundamentals report AAPL            build the report and print the key numbers (no model)
    fundamentals compare AAPL MSFT      the comparison table (no model)
    fundamentals reading AAPL --yes     the AI reading: calls the model, spends up to the request cap
    fundamentals budget                 what the readings have spent
    fundamentals peers fetch            the peer map, step 1: each company's Business section, from the SEC
    fundamentals peers embed            step 2: one vector per company, with a model on this machine
    fundamentals peers build            step 3: neighbours and map, into src/fundamentals/peers.json
    fundamentals peers show NVDA        a company's neighbours on the map as built
"""

from __future__ import annotations

import argparse
import json
import sys

from .budget import Budget
from .compare import compare
from .config import PEERS_UNIVERSE, READING_MODEL, READING_REQUEST_MAX_USD
from .reading import Reader
from .report import Reporter, compact
from .sec import Directory
from .store import default_store


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.4g}" if abs(value) < 1000 else f"{value:,.0f}"
    return str(value)


def _peers(args) -> int:
    # Imported here: the batch is the only part that needs it.
    from . import peerbuild
    from .peers import PeerMap

    if args.step == "fetch":
        print(json.dumps(peerbuild.fetch(args.size, retry=args.retry), indent=2))
    elif args.step == "embed":
        peerbuild.embed()
    elif args.step == "build":
        peerbuild.build()
    elif args.step == "status":
        print(json.dumps(peerbuild.summary(), indent=2))
    else:
        found = PeerMap.load().get(args.ticker or "")
        if not found:
            print("Not on the map.", file=sys.stderr)
            return 1
        print(f"{found['ticker']} — {found['name']} ({found['industry']})  {found['form']} filed {found['filed']}")
        for peer in found["peers"]:
            print(f"  {peer['similarity']:.3f}  {peer['ticker']:7} {peer['name']}  ({peer['industry']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fundamentals")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search")
    p.add_argument("query")
    p = sub.add_parser("report")
    p.add_argument("ticker")
    p.add_argument("--json", action="store_true", help="print the compact report as JSON")
    p = sub.add_parser("compare")
    p.add_argument("tickers", nargs="+")
    p = sub.add_parser("reading")
    p.add_argument("ticker")
    p.add_argument("--yes", action="store_true", help="confirm the call to the model")
    sub.add_parser("budget")
    p = sub.add_parser("peers", help="build the peer map on this machine (no paid API)")
    p.add_argument("step", choices=("fetch", "embed", "build", "status", "show"))
    p.add_argument("ticker", nargs="?", help="for show: the company whose neighbours to print")
    p.add_argument("--size", type=int, default=PEERS_UNIVERSE, help="how many companies to read")
    p.add_argument("--retry", action="store_true", help="fetch: read again the companies that were skipped")
    args = parser.parse_args(argv)

    if args.command == "peers":
        return _peers(args)

    store = default_store()
    directory = Directory()
    if args.command == "search":
        for c in directory.search(args.query):
            print(f"{c.ticker:8} {c.name}")
        return 0
    if args.command == "budget":
        print(json.dumps(Budget(store).status(), indent=2))
        return 0

    reporter = Reporter(store)
    if args.command == "report":
        report = reporter.build(directory.get(args.ticker))
        data = compact(report)
        if args.json:
            print(json.dumps(data, indent=2, default=str))
            return 0
        print(f"{data['ticker']} — {data['name']} ({data['sector']})  sources: {report['sources']}")
        for note in report["notes"]:
            print(f"  note: {note}")
        for group in ("valuation", "history_median", "margins", "returns", "balance", "technical"):
            print(f"\n{group}")
            for k, v in data[group].items():
                print(f"  {k:22} {_fmt(v)}")
        print("\nforward")
        for y in data["forward"]["years"]:
            print(f"  FY{y['fiscal_year']}: P/E {_fmt(y['pe'])}  EV/EBITDA {_fmt(y['ev_ebitda'])}  "
                  f"EPS growth {_fmt(y['eps_growth'])}  analysts {_fmt(y['analysts'])}")
        return 0
    if args.command == "compare":
        result = compare([reporter.build(directory.get(t)) for t in args.tickers])
        print(f"{'':24}" + "".join(f"{t:>12}" for t in result["tickers"]))
        for row in result["table"]:
            print(f"{row['label']:24}" + "".join(f"{_fmt(v):>12}" for v in row["values"]))
        return 0
    if args.command == "reading":
        if not args.yes:
            print(f"This calls {READING_MODEL} and spends up to ${READING_REQUEST_MAX_USD:.2f}. "
                  "Add --yes to go ahead.", file=sys.stderr)
            return 2
        report = reporter.build(directory.get(args.ticker))
        reading = Reader(store).company(compact(report))
        print(json.dumps(reading, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

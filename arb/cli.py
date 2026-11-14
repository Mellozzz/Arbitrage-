"""Command-line interface.

  python -m arb calc 2.10 2.05 --stake 100
  python -m arb scan --sports upcoming --regions us,uk,eu --stake 100
  python -m arb sports
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .core import DEFAULT_COMMISSION, Leg, calculate_stakes, implied_total, parse_odds, profit_margin
from .odds_api import OddsAPIError, get_odds, list_sports
from .scanner import find_opportunities


def print_plan(legs: list[Leg], stake: float, round_to: float) -> None:
    plan = calculate_stakes(legs, stake, round_to)
    for leg, s, p in zip(plan.legs, plan.stakes, plan.payouts):
        book = f" @ {leg.bookmaker}" if leg.bookmaker else ""
        price = f"{leg.quoted:.2f} (net {leg.odds:.2f})" if leg.quoted else f"{leg.odds:.2f}"
        print(f"    {leg.outcome:<28} odds {price:>16}{book:<22} stake {s:>9.2f}  -> returns {p:>9.2f}")
    print(f"    total staked {plan.total_stake:.2f} | guaranteed profit {plan.min_profit:+.2f} "
          f"({plan.roi:+.2%})" + (f" up to {plan.max_profit:+.2f}" if plan.max_profit - plan.min_profit > 0.01 else ""))
    if plan.min_profit <= 0:
        print("    WARNING: after rounding this is NOT risk-free - use a smaller --round or bigger --stake")


def cmd_calc(args: argparse.Namespace) -> int:
    odds = [parse_odds(o) for o in args.odds]
    legs = [Leg(f"Outcome {i + 1}", o) for i, o in enumerate(odds)]
    total = implied_total(odds)
    print(f"Implied probability total: {total:.4f}")
    if total >= 1:
        print(f"NO arbitrage - bookmaker margin {total - 1:.2%}. You would lose {1 - 1/total:.2%} guaranteed.")
        return 1
    print(f"ARBITRAGE: {profit_margin(odds):.2%} guaranteed return")
    print_plan(legs, args.stake, args.round)
    return 0


def parse_commission(text: str) -> dict[str, float]:
    """'betfair_ex_au=0.06,smarkets=0' -> defaults updated with these rates."""
    rates = dict(DEFAULT_COMMISSION)
    for item in filter(None, text.split(",")):
        key, _, val = item.partition("=")
        rate = float(val)
        rates[key.strip()] = rate / 100 if rate >= 1 else rate  # accept 5 or 0.05
    return rates


def scan_once(args: argparse.Namespace) -> int:
    exclude = set(filter(None, args.exclude.split(",")))
    commission = parse_commission(args.commission)
    total_found = 0
    for sport in args.sports.split(","):
        try:
            events, quota = get_odds(sport, args.regions, args.markets)
        except OddsAPIError as e:
            print(f"[{sport}] error: {e}", file=sys.stderr)
            continue
        opps = find_opportunities(events, min_margin=args.min_margin / 100, exclude_books=exclude,
                                  commission=commission)
        print(f"[{sport}] {len(events)} events scanned, {len(opps)} arbs "
              f"(API quota remaining: {quota.get('remaining')})")
        for o in opps:
            total_found += 1
            line = f" {o.line:+g}" if o.line is not None else ""
            print(f"\n  {o.margin:+.2%}  {o.sport} | {o.event} | {o.market}{line} | starts {o.commence_time}")
            print_plan(o.legs, args.stake, args.round)
    if total_found == 0:
        print("\nNo arbitrage opportunities right now. That's normal - they are rare and short-lived.")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    if args.watch <= 0:
        return scan_once(args)
    while True:
        print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
        scan_once(args)
        time.sleep(args.watch)


def cmd_sports(_: argparse.Namespace) -> int:
    for s in list_sports():
        if s.get("active"):
            print(f"{s['key']:<40} {s['title']}")
    return 0


def cmd_file(args: argparse.Namespace) -> int:
    """Scan a saved Odds-API-format JSON file (offline / testing)."""
    with open(args.path) as f:
        events = json.load(f)
    opps = find_opportunities(events, min_margin=args.min_margin / 100,
                              commission=parse_commission(args.commission))
    for o in opps:
        line = f" {o.line:+g}" if o.line is not None else ""
        print(f"\n  {o.margin:+.2%}  {o.event} | {o.market}{line}")
        print_plan(o.legs, args.stake, args.round)
    print(f"\n{len(opps)} arbitrage opportunities found.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arb", description="Sports betting arbitrage finder")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--stake", type=float, default=100, help="total amount to spread across all legs")
        sp.add_argument("--round", type=float, default=0, help="round stakes to this increment, e.g. 1 or 5")

    def commission_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--commission", default="",
                        help="override exchange commission, e.g. betfair_ex_au=6,smarkets=2 "
                             "(defaults: Betfair 5%%, Smarkets/Matchbook 2%%)")

    c = sub.add_parser("calc", help="check odds you found yourself, e.g. 2.10 2.05 or +110 -105")
    c.add_argument("odds", nargs="+")
    common(c)
    c.set_defaults(func=cmd_calc)

    s = sub.add_parser("scan", help="scan live bookmaker odds (needs ODDS_API_KEY)")
    s.add_argument("--sports", default="upcoming", help="comma list of sport keys (see `arb sports`)")
    s.add_argument("--regions", default="us,uk,eu,au", help="bookmaker regions: us,us2,uk,eu,au")
    s.add_argument("--markets", default="h2h", help="h2h,spreads,totals")
    s.add_argument("--min-margin", type=float, default=0.5, help="minimum profit %% to show")
    s.add_argument("--exclude", default="", help="comma list of bookmaker keys to ignore")
    s.add_argument("--watch", type=int, default=0, help="rescan every N seconds (uses API quota!)")
    common(s)
    commission_arg(s)
    s.set_defaults(func=cmd_scan)

    f = sub.add_parser("file", help="scan a saved JSON odds file")
    f.add_argument("path")
    f.add_argument("--min-margin", type=float, default=0.0)
    common(f)
    commission_arg(f)
    f.set_defaults(func=cmd_file)

    sp = sub.add_parser("sports", help="list available sport keys")
    sp.set_defaults(func=cmd_sports)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (OddsAPIError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

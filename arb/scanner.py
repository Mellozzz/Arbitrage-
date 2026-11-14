"""Find the best price per outcome across bookmakers and detect arbitrage."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .core import DEFAULT_COMMISSION, Leg, implied_total, net_odds, profit_margin


@dataclass
class Opportunity:
    sport: str
    event: str
    commence_time: str
    market: str
    line: float | None
    legs: list[Leg]

    @property
    def margin(self) -> float:
        return profit_margin([leg.odds for leg in self.legs])

    @property
    def implied(self) -> float:
        return implied_total([leg.odds for leg in self.legs])


def _line_key(market: str, outcome: dict, home_team: str) -> float | None:
    point = outcome.get("point")
    if point is None:
        return None
    if market == "spreads":
        # Pair "Home -1.5" with "Away +1.5": key every spread by the home line.
        return point if outcome["name"] == home_team else -point
    return point  # totals: Over 2.5 pairs with Under 2.5


def find_opportunities(
    events: list[dict],
    min_margin: float = 0.0,
    exclude_books: set[str] | None = None,
    commission: dict[str, float] | None = None,
) -> list[Opportunity]:
    """events: The Odds API v4 /odds response format.

    commission: bookmaker key -> rate on winnings (defaults to DEFAULT_COMMISSION).
    Exchange prices are compared net of commission, so only real profits show.
    """
    exclude_books = exclude_books or set()
    commission = DEFAULT_COMMISSION if commission is None else commission
    found: list[Opportunity] = []
    now = datetime.now(timezone.utc)

    for ev in events:
        commence = ev.get("commence_time", "")
        try:
            if datetime.fromisoformat(commence.replace("Z", "+00:00")) <= now:
                continue  # skip live/started games: odds move too fast
        except ValueError:
            pass
        home = ev.get("home_team", "")
        # (market, line) -> {outcome_name: Leg}
        best: dict[tuple[str, float | None], dict[str, Leg]] = {}
        # (market, line) -> max number of outcomes any single book lists
        n_outcomes: dict[tuple[str, float | None], int] = {}

        for book in ev.get("bookmakers", []):
            if book["key"] in exclude_books:
                continue
            for mkt in book.get("markets", []):
                key_name = mkt["key"]
                if key_name.endswith("_lay"):
                    continue  # exchange lay prices are bets AGAINST an outcome, not backable odds
                per_line: dict[float | None, int] = {}
                for out in mkt.get("outcomes", []):
                    price = out.get("price")
                    if not price or price <= 1:
                        continue
                    line = _line_key(key_name, out, home)
                    k = (key_name, line)
                    per_line[line] = per_line.get(line, 0) + 1
                    slot = best.setdefault(k, {})
                    cur = slot.get(out["name"])
                    rate = commission.get(book["key"], 0.0)
                    eff = net_odds(float(price), rate)
                    if cur is None or eff > cur.odds:
                        slot[out["name"]] = Leg(out["name"], eff, book.get("title", book["key"]),
                                                quoted=float(price) if rate else None)
                for line, n in per_line.items():
                    k = (key_name, line)
                    n_outcomes[k] = max(n_outcomes.get(k, 0), n)

        for (market, line), legs_by_name in best.items():
            legs = list(legs_by_name.values())
            # Every outcome must be covered, otherwise it's not a true arb.
            if len(legs) < 2 or len(legs) < n_outcomes.get((market, line), 0):
                continue
            opp = Opportunity(
                sport=ev.get("sport_title", ev.get("sport_key", "")),
                event=f"{ev.get('away_team', '')} @ {home}",
                commence_time=commence,
                market=market,
                line=line,
                legs=legs,
            )
            if opp.implied < 1.0 and opp.margin >= min_margin:
                found.append(opp)

    found.sort(key=lambda o: o.margin, reverse=True)
    return found

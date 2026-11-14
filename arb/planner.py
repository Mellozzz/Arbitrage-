"""Spend a limited API budget where arbitrage is most likely to be found.

Listing sports and events is free on The Odds API; fetching odds costs
(markets x regions) credits per sport. So: count upcoming events per sport
for free, then buy odds for the (sport, market) pairs with the most games.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Relative value of each market. Match result is the most liquid and most
# often mispriced across books; totals/spreads add coverage once h2h is bought.
MARKET_WEIGHT = {"h2h": 1.0, "totals": 0.6, "spreads": 0.5}


@dataclass
class SportPlan:
    sport: str
    markets: list[str]
    events: int

    def cost(self, n_regions: int) -> int:
        return len(self.markets) * n_regions


def count_upcoming(events: list[dict], hours: float, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)
    n = 0
    for ev in events:
        try:
            t = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if now < t <= end:
            n += 1
    return n


def plan(event_counts: dict[str, int], budget: int, n_regions: int,
         markets: list[str]) -> list[SportPlan]:
    """Greedy: highest (events x market weight) first until the budget is spent."""
    candidates = sorted(
        ((count * MARKET_WEIGHT.get(m, 0.3), sport, m)
         for sport, count in event_counts.items() if count > 0
         for m in markets),
        key=lambda c: (-c[0], c[1], c[2]),
    )
    chosen: dict[str, list[str]] = {}
    spent = 0
    for _, sport, market in candidates:
        if spent + n_regions > budget:
            break
        chosen.setdefault(sport, []).append(market)
        spent += n_regions
    return [SportPlan(s, ms, event_counts[s]) for s, ms in chosen.items()]


def count_all(sport_keys: list[str], get_events, hours: float, workers: int = 6) -> dict[str, int]:
    """Count upcoming events for every sport in parallel (free API calls)."""
    def one(key: str) -> tuple[str, int]:
        try:
            return key, count_upcoming(get_events(key), hours)
        except Exception:
            return key, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(one, sport_keys))

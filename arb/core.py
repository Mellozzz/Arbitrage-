"""Pure arbitrage math: odds conversion, detection, and stake sizing."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def american_to_decimal(american: float) -> float:
    if american == 0 or -100 < american < 100:
        raise ValueError(f"invalid American odds: {american}")
    return 1 + (american / 100 if american > 0 else 100 / -american)


def fractional_to_decimal(frac: str) -> float:
    num, den = frac.split("/")
    return 1 + float(num) / float(den)


def parse_odds(text: str) -> float:
    """Accept decimal (2.10), American (+110 / -150) or fractional (11/10)."""
    s = text.strip()
    if "/" in s:
        return fractional_to_decimal(s)
    if s.startswith(("+", "-")):
        return american_to_decimal(float(s))
    value = float(s)
    if value <= 1:
        raise ValueError(f"decimal odds must be > 1, got {value}")
    return value


@dataclass
class Leg:
    outcome: str
    odds: float          # decimal odds actually paid (after any commission)
    bookmaker: str = ""
    quoted: float | None = None  # price shown by the book, if different from `odds`


@dataclass
class StakePlan:
    legs: list[Leg]
    stakes: list[float]
    total_stake: float
    payouts: list[float] = field(default_factory=list)

    @property
    def min_profit(self) -> float:
        return min(self.payouts) - self.total_stake

    @property
    def max_profit(self) -> float:
        return max(self.payouts) - self.total_stake

    @property
    def roi(self) -> float:
        return self.min_profit / self.total_stake if self.total_stake else 0.0


# Commission charged on net winnings by betting exchanges (The Odds API bookmaker keys).
# Defaults are standard base rates; override with --commission if yours differ.
DEFAULT_COMMISSION = {
    "betfair_ex_uk": 0.05,
    "betfair_ex_eu": 0.05,
    "betfair_ex_au": 0.05,
    "smarkets": 0.02,
    "matchbook": 0.02,
}


def net_odds(odds: float, commission: float) -> float:
    """Effective decimal odds after commission is taken from the winnings."""
    return 1 + (odds - 1) * (1 - commission)


def implied_total(odds: list[float]) -> float:
    """Sum of implied probabilities. < 1.0 means an arbitrage exists."""
    return sum(1 / o for o in odds)


def is_arbitrage(odds: list[float]) -> bool:
    return implied_total(odds) < 1.0


def profit_margin(odds: list[float]) -> float:
    """Guaranteed return on total stake, e.g. 0.02 == 2%."""
    return 1 / implied_total(odds) - 1


def calculate_stakes(legs: list[Leg], total_stake: float, round_to: float = 0.0) -> StakePlan:
    """Split total_stake so every outcome pays the same amount.

    round_to: round each stake to this increment (e.g. 1 or 5) so bets look
    natural; the plan's payouts/profit are recomputed after rounding.
    """
    if len(legs) < 2:
        raise ValueError("need at least two outcomes")
    inv = [1 / leg.odds for leg in legs]
    total_inv = sum(inv)
    exact = [total_stake * i / total_inv for i in inv]
    if round_to <= 0:
        return _plan(legs, [round(s, 2) for s in exact])
    # Try rounding each stake down or up; keep the combo with the best worst-case
    # return on stake (2^n combos, n is 2-3 in practice).
    best: StakePlan | None = None
    for mask in range(1 << len(legs)):
        stakes = [(math.ceil(s / round_to) if mask >> i & 1 else math.floor(s / round_to)) * round_to
                  for i, s in enumerate(exact)]
        if min(stakes) <= 0:
            continue
        cand = _plan(legs, stakes)
        if best is None or cand.roi > best.roi + 1e-12:
            best = cand
    return best or _plan(legs, [round(s, 2) for s in exact])


def _plan(legs: list[Leg], stakes: list[float]) -> StakePlan:
    stakes = [round(s, 2) for s in stakes]
    payouts = [round(s * leg.odds, 2) for s, leg in zip(stakes, legs)]
    return StakePlan(legs=legs, stakes=stakes, total_stake=round(sum(stakes), 2), payouts=payouts)

import unittest

from arb.core import Leg, american_to_decimal, calculate_stakes, is_arbitrage, parse_odds, profit_margin
from arb.planner import count_upcoming, plan
from arb.scanner import find_opportunities

FUTURE = "2099-01-01T00:00:00Z"


def book(key, outcomes, market="h2h"):
    return {"key": key, "title": key.title(), "markets": [{"key": market, "outcomes": outcomes}]}


class TestCore(unittest.TestCase):
    def test_parse(self):
        self.assertAlmostEqual(parse_odds("2.5"), 2.5)
        self.assertAlmostEqual(parse_odds("+150"), 2.5)
        self.assertAlmostEqual(parse_odds("-200"), 1.5)
        self.assertAlmostEqual(parse_odds("3/2"), 2.5)
        with self.assertRaises(ValueError):
            american_to_decimal(50)

    def test_detection(self):
        self.assertTrue(is_arbitrage([2.10, 2.05]))
        self.assertFalse(is_arbitrage([1.91, 1.91]))
        self.assertAlmostEqual(profit_margin([2.10, 2.10]), 0.05)

    def test_stakes_equal_payout(self):
        plan = calculate_stakes([Leg("A", 2.10), Leg("B", 2.05)], 100)
        self.assertAlmostEqual(plan.payouts[0], plan.payouts[1], delta=0.03)
        self.assertGreater(plan.min_profit, 0)

    def test_rounding_still_profitable(self):
        plan = calculate_stakes([Leg("A", 2.20), Leg("B", 2.00)], 500, round_to=5)
        self.assertTrue(all(s % 5 == 0 for s in plan.stakes))
        self.assertGreater(plan.min_profit, 0)

    def test_smart_rounding_keeps_profit(self):
        # Nearest-dollar rounding gives 79/21 -> loss; smart rounding finds a profitable split.
        plan = calculate_stakes([Leg("A", 1.28), Leg("B", 4.75)], 100, round_to=1)
        self.assertGreater(plan.min_profit, 0)
        self.assertTrue(all(float(s).is_integer() for s in plan.stakes))


class TestScanner(unittest.TestCase):
    def test_two_way_arb(self):
        ev = {"home_team": "H", "away_team": "A", "commence_time": FUTURE, "bookmakers": [
            book("b1", [{"name": "H", "price": 2.15}, {"name": "A", "price": 1.80}]),
            book("b2", [{"name": "H", "price": 1.85}, {"name": "A", "price": 2.10}]),
        ]}
        opps = find_opportunities([ev])
        self.assertEqual(len(opps), 1)
        self.assertEqual({l.bookmaker for l in opps[0].legs}, {"B1", "B2"})

    def test_missing_draw_not_arb(self):
        # Soccer: one book lists the draw, so all 3 outcomes must be covered.
        ev = {"home_team": "H", "away_team": "A", "commence_time": FUTURE, "bookmakers": [
            book("b1", [{"name": "H", "price": 2.5}, {"name": "A", "price": 3.0}, {"name": "Draw", "price": 3.2}]),
            book("b2", [{"name": "H", "price": 3.0}, {"name": "A", "price": 3.5}]),
        ]}
        for o in find_opportunities([ev]):
            self.assertEqual(len(o.legs), 3)

    def test_totals_pair_same_line(self):
        ev = {"home_team": "H", "away_team": "A", "commence_time": FUTURE, "bookmakers": [
            book("b1", [{"name": "Over", "price": 2.10, "point": 2.5}, {"name": "Under", "price": 1.75, "point": 2.5}], "totals"),
            book("b2", [{"name": "Over", "price": 1.80, "point": 3.5}, {"name": "Under", "price": 2.10, "point": 3.5}], "totals"),
        ]}
        self.assertEqual(find_opportunities([ev]), [])  # different lines -> no arb

    def test_ignores_lay_markets(self):
        ev = {"home_team": "H", "away_team": "A", "commence_time": FUTURE, "bookmakers": [
            book("ex", [{"name": "H", "price": 2.8}, {"name": "A", "price": 1.6}], "h2h_lay"),
        ]}
        self.assertEqual(find_opportunities([ev]), [])

    def test_exchange_commission_kills_thin_arb(self):
        # 2.66 / 1.62 is a 0.68% arb on raw prices, but not after 5% Betfair commission.
        ev = {"home_team": "H", "away_team": "A", "commence_time": FUTURE, "bookmakers": [
            book("betfair_ex_au", [{"name": "H", "price": 1.55}, {"name": "A", "price": 2.66}]),
            book("sportsbet", [{"name": "H", "price": 1.62}, {"name": "A", "price": 2.40}]),
        ]}
        self.assertEqual(find_opportunities([ev]), [])
        self.assertEqual(len(find_opportunities([ev], commission={})), 1)

    def test_exchange_net_odds_used_for_stakes(self):
        ev = {"home_team": "H", "away_team": "A", "commence_time": FUTURE, "bookmakers": [
            book("smarkets", [{"name": "H", "price": 2.30}, {"name": "A", "price": 1.50}]),
            book("b2", [{"name": "H", "price": 1.70}, {"name": "A", "price": 2.10}]),
        ]}
        [opp] = find_opportunities([ev])
        leg = next(l for l in opp.legs if l.bookmaker == "Smarkets")
        self.assertAlmostEqual(leg.odds, 1 + 1.30 * 0.98)
        self.assertEqual(leg.quoted, 2.30)

    def test_skips_started_games(self):
        ev = {"home_team": "H", "away_team": "A", "commence_time": "2000-01-01T00:00:00Z", "bookmakers": [
            book("b1", [{"name": "H", "price": 3.0}, {"name": "A", "price": 3.0}]),
        ]}
        self.assertEqual(find_opportunities([ev]), [])


class TestPlanner(unittest.TestCase):
    def test_budget_respected_and_busiest_first(self):
        counts = {"nba": 10, "afl": 0, "epl": 6, "nbl": 2}
        p = plan(counts, budget=4, n_regions=1, markets=["h2h", "totals"])
        self.assertEqual(sum(x.cost(1) for x in p), 4)
        self.assertNotIn("afl", [x.sport for x in p])
        by = {x.sport: x.markets for x in p}
        self.assertEqual(by["nba"], ["h2h", "totals"])   # 10, 6
        self.assertEqual(by["epl"], ["h2h", "totals"])   # 6, 3.6 beat nbl's 2

    def test_regions_multiply_cost(self):
        p = plan({"nba": 5, "epl": 4}, budget=5, n_regions=2, markets=["h2h"])
        self.assertEqual([x.sport for x in p], ["nba", "epl"])
        self.assertEqual(sum(x.cost(2) for x in p), 4)

    def test_count_upcoming_window(self):
        from datetime import datetime, timezone
        now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        evs = [{"commence_time": "2030-01-01T05:00:00Z"}, {"commence_time": "2030-01-05T00:00:00Z"},
               {"commence_time": "2029-12-31T00:00:00Z"}]
        self.assertEqual(count_upcoming(evs, 48, now), 1)


if __name__ == "__main__":
    unittest.main()

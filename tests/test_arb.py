import unittest

from arb.core import Leg, american_to_decimal, calculate_stakes, is_arbitrage, parse_odds, profit_margin
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

    def test_skips_started_games(self):
        ev = {"home_team": "H", "away_team": "A", "commence_time": "2000-01-01T00:00:00Z", "bookmakers": [
            book("b1", [{"name": "H", "price": 3.0}, {"name": "A", "price": 3.0}]),
        ]}
        self.assertEqual(find_opportunities([ev]), [])


if __name__ == "__main__":
    unittest.main()

# Arbitrage Bet Finder

Finds **sports betting arbitrage** ("surebets"): cases where different bookmakers disagree
enough that backing *every* outcome, each at a different book, guarantees a profit no matter who wins.

## How it works

Convert each outcome's best available decimal odds to an implied probability (`1 / odds`) and add them up.

* Sum **≥ 1.00**: normal market. The bookmakers keep the margin.
* Sum **< 1.00**: arbitrage. Return = `1 / sum - 1`.

Example: Team A at **2.10** (Book X), Team B at **2.05** (Book Y).
`1/2.10 + 1/2.05 = 0.964` gives a **3.73% guaranteed return**. Stake each side in proportion to
`1/odds` so both sides pay the same:

| Bet | Odds | Stake | Returns |
|---|---|---|---|
| Team A @ Book X | 2.10 | $49.40 | $103.74 |
| Team B @ Book Y | 2.05 | $50.60 | $103.73 |

## Usage (Python 3.10+, no dependencies)

```bash
# 1. Check odds you found by hand (decimal, American +110/-105, or fractional 11/10)
python -m arb calc 2.10 2.05 --stake 100
python -m arb calc +110 -105 2/1 --stake 250 --round 1    # 3-way market

# 2. Scan live odds from 40+ bookmakers automatically
export ODDS_API_KEY=your_key        # free tier at https://the-odds-api.com (500 requests/month)
python -m arb sports                                   # list sport keys
python -m arb scan --stake 100                         # all upcoming games, h2h markets
python -m arb scan --sports basketball_nba,soccer_epl --markets h2h,totals,spreads \
                   --regions us,uk,eu --min-margin 1 --round 1
python -m arb scan --exclude betfair_ex_uk,matchbook    # skip books you don't have accounts at
python -m arb scan --watch 300                         # rescan every 5 min (uses quota)

# Run tests
python -m unittest discover -s tests
```

Each request costs `markets × regions` API credits, so keep `--watch` intervals long on the free tier.

## Read this before betting real money

Arbitrage math is risk-free. **Executing it is not.** Things that actually go wrong:

1. **Odds move.** If one leg's price changes before you place it, you're left holding a normal bet.
   Re-check both prices on the bookmaker sites and place the **less liquid / more likely to move** leg first.
2. **Stake limits and rejections.** A book may accept only part of your stake.
3. **Account restrictions.** Bookmakers detect arbers (odd stake sizes, only betting on mispriced lines)
   and limit or close accounts. `--round` makes stakes look more natural, but check that rounding keeps the profit positive.
4. **Different rules.** Books settle differently on overtime, retirements (tennis), postponements and
   voided legs. Make sure both sides cover the exact same market (e.g. "including overtime" vs "regulation").
5. **Palpable errors.** A price that looks too good (e.g. a 10%+ arb) is often a mistake the book will void,
   leaving your other leg unhedged. Treat big margins with suspicion.
6. **Fees and exchange commission.** The scanner already prices exchanges net of commission
   (Betfair 5%, Smarkets/Matchbook 2%) and shows e.g. `2.66 (net 2.58)`. If your rate differs, pass
   `--commission betfair_ex_au=6,smarkets=0`. Exchange "lay" markets are ignored.
7. **Legality.** Make sure online betting, and each bookmaker, is legal where you live.

Realistic margins are **0.5–3%** per arb, so this grinds out small gains on capital spread across many accounts.
It is not a way to get rich fast.

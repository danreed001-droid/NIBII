# Validation tools

Two checks a reviewer asked for in October 2026. Neither changes the strategy; they test it. Both run against
the backtest engine that `research/backtest/refresh.sh` sets up (the `robustness` worktree with `overlay/`
copied over it), after a backtest run has filled the engine's data cache.

## `friction_test.py`: trading-cost stress test

Replays the plan's exact holdings schedule with higher costs per round trip and reports return a year and
worst drop for the whole run and for 2016–2020, 2021–2023 and 2024 on, plus the round-trip cost at which the
plan would only match SPY.

```
# in the engine folder: write the default plan's schedule
env HARNESS_SIDE=<side folder> NIBII_REPO=<repo> START=2000-01-03 FROM=1998-06-01 EXCLUDE=EP,CPWR BOOST_ONLY=1 \
    ONLY=NBup DUMP_SCHED=NBup_boost TAG=_fric python scripts/improve.py
# then, from the repo
python research/validation/friction_test.py --engine <engine folder> --sched <engine folder>/data/sched_NBup_boost_fric.json
```

Result on Oct 15, 2026 (default plan, 2000 to Oct 6, 2026, before tax; worst drop in brackets):

| Round-trip cost | 2000–2026 | 2016–2020 | 2021–2023 | 2024 on |
|---|---|---|---|---|
| 0.15% | 41.6% (−33%) | 42.1% (−19%) | 22.7% (−19%) | 119.4% (−23%) |
| 0.30% (engine default) | 37.8% (−33%) | 38.3% (−20%) | 18.9% (−20%) | 113.4% (−23%) |
| 0.50% | 32.8% (−40%) | 33.3% (−21%) | 14.0% (−22%) | 105.6% (−23%) |
| 1.0% | 21.1% (−58%) | 21.6% (−26%) | 2.7% (−32%) | 87.3% (−23%) |
| 5.0% | −41.9% (−100%) | −41.5% (−95%) | −55.3% (−93%) | −10.8% (−49%) |
| 10.0% | −66.7% (−100%) | −57.5% (−99%) | −36.0% (−75%) | −15.1% (−36%) |
| SPY | 8.4% (−55%) | 15.1% (−34%) | 10.0% (−24%) | 21.4% (−19%) |

The plan trades about 20 times its value a year, so each 0.1% of round-trip cost takes about 2 points a year
off. It matches SPY at about 1.6% per round trip. S&P 500 stocks cost a few hundredths of a percent to trade, so
the 0.30% default is already cautious; the 5% and 10% rows are micro-cap costs.

## `class_cpcv.py`: class layer on the weekly horizon, with CPCV

Builds a weekly panel (each Friday, every S&P 500 member at that date; target = the 5-trading-day return from
the next close, the horizon of a weekly trade), checks that each of five macro-sectors is at least 10% of the
full dataset, and asks whether a ranking that also learns macro-sector, size, volatility and market-season
interactions picks better top-5 stocks than the plain ranking. It uses combinatorial purged cross-validation
on 2000–2015 (6 time groups, 2 held out, 15 splits, 5 paths, 1 week purged before and 8 weeks embargoed after
each held-out group), a chronological check on 2016–2026, and a false-discovery check over every 1-, 2- and
3-class combination.

```
python research/validation/class_cpcv.py --engine <engine folder> --side <side folder> --repo . [--cpi CPIAUCSL.csv]
```

Result on Oct 15, 2026: every macro-sector passed the 10% check on the full dataset (Healthcare lowest, at
10.3% of trading value). The class-aware ranking did worse than the plain ranking on all 5 CPCV paths and in
both 2021–2023 and 2024 on, and none of 288 class combinations passed the false-discovery check. The plain
ranking stays.

The ranking signal in this panel is a simplified weekly version of the strategy's, without the risk layer,
so it measures stock selection only. The strategy itself is not re-fitted between periods, so CPCV paths of
the strategy alone would all reproduce the same backtest; CPCV matters for anything that is learned, like the
class layer here.

## Fading-energy filter (default since Oct 16, 2026)

`mtl/fade.py`. The default plan doesn't buy a top-5 stock whose trading volume over the last 21 sessions is under 70%
of the 105 sessions before **and** whose daily swings over the last 21 sessions are under 55% of its normal (the 189
sessions before the last 63). Its slot stays in cash (`buy_max_rank` in `mtl/momentum.py`) instead of going to the
next-ranked stock, until it drops out of the top 5 or stops fading. A stock already held is kept as usual. You-2
applies the same check to the viewer's stocks.

**Whipsaw shadow count (Oct 16, 2026).** The whipsaw switch reads the same Boost list run with the filter off: a
stock the filter skipped counts as if it had been bought and later sold, and an empty slot is never a sale. The
backtest engine had counted the empty slot as a sale that didn't lose and held it in T-bills (swapped to gold or
bonds), unlike the live scanner; in a run started Jan 2, 2020 that kept the half-switch off through most of the
Feb–Mar 2020 crash (worst drop −40% against −27% without the filter). The engine now matches the live scanner, the
half-switch turns on in the same weeks as without the filter, and the figures below are from the corrected engine
(first count: 40.5% from 2000, 67.6% from 2020).

**How it was found.** A study of the plan's 1,384 purchases since 2000 (return vs SPY over each holding): picks
bought while their volume had dried up trailed SPY by 10%+ about 14% of the time against 7–9% for the rest, and the
same held for shrinking swings, in both 2000–2012 and 2013–2026. Skipping them and buying the next-ranked stock
did **not** help (37.6% vs 37.8% a year): the replacements carried their own risk. Leaving the slot in cash did.
Because the pattern came from the same history it was tested on, it went through the overfitting checks first.

Results as tested, with the whipsaw switch moving half the account (engine `NBup` = with the filter, `NBnf` = without;
S&P 500 members at each date, 0.15% per side). With the whole-account switch adopted later the same day (next
section) the plan makes 41.0% a year from 2000 with the filter and 38.7% without it (43.2% vs 40.9% from 2010, 50.7% vs
47.9% from 2016, 74.8% vs 71.8% from 2020), t-statistic 2.2 on monthly returns.

| Check | Without | With |
|---|---|---|
| From 2000, a year before tax (after tax) | 37.8% (23.8%) | 40.3% (25.4%) |
| Worst drop from 2000 | −33% | −33% |
| From 2010 / 2016 / 2020 | 39.5% / 47.3% / 69.7% | 42.0% / 50.3% / 73.3% |
| Dashboard universe (with the 15 Nasdaq-100 additions), from 2000 | 37.9% | 39.4% |
| Ten separate periods (Holdout Review) | | better in 7, same in 2, worse in 1 (2010–2013) |
| Volume threshold 60% / 70% / 78% / 85% / 90% / 100% (volume alone) | 37.8% | 38.1 / 39.0 / 41.0 / 41.3 / 40.8 / 39.3% |
| Deflated Sharpe, 1,070 versions counted | 99.79% | 99.93% |
| Probability of backtest overfitting (CSCV), 1,070 versions | 1.4% | 1.4% |
| Abroad (Japan, UK, Germany, India, Hong Kong) | 15.1 / 13.4 / 5.5 / 32.8 / 27.1% | 15.1 / 13.2 / 5.9 / 32.5 / 27.1% |

Limits, stated plainly: the gain over the plan without it is not statistically proven once the ~55 versions tried
that day are counted (t-statistic of the monthly difference 2.3 on the S&P list and 1.3 on the dashboard's
universe, against about 3 needed); 2009 is a large part of it; and it does nothing abroad. It doesn't hurt in any
of the checks, so it went in on probation. The paper record shows the change as a listed update.

## Whipsaw switch: the whole account (default since Oct 16, 2026)

When the whipsaw check is on (65% or more of the Boost list's sales in the last 126 sessions were losers, at least 6
sales), the plan now holds 100% of whichever of TLT, GLD and SPY (TLT and GLD only since Oct 28, 2026) is up most
over 3 months (skipping weekly downtrends) instead of 50% of it next to the Boost list (`WHIP_SHARE` in `mtl/rotation.py`; engine `NBup` = whole
account, `NBhalf` = half). It came from asking how the switch did over its own days: across its 22 stretches since 2000
(251 sessions, about 4% of the time) the Boost list lost about 3% while the asset it picked gained about 13%.

| Check | Half (until Oct 16) | Whole account |
|---|---|---|
| From 2000, a year before tax (after tax) | 40.3% (25.4%) | 41.0% (25.8%) |
| Worst drop from 2000 / from 2020 | −33% / −27% | −34% / −23% |
| From 2010 / 2016 / 2020 | 42.0% / 50.3% / 73.3% | 43.2% / 50.7% / 74.8% |
| Dashboard universe (with the 15 Nasdaq-100 additions), from 2000 | 39.4% | 40.1% |
| Share of the account in the asset: 0 / 33 / 50 / 66 / 100%, from 2000 | | 39.3 / 40.0 / 40.3 / 40.5 / 41.0% |
| Ten separate periods (Holdout Review) | | better in 2 (2010–2013, 2016–2018), same in 7, worse in 1 (2013–2015) |
| Deflated Sharpe, 1,081 versions counted | 99.92% | 99.94% |
| Probability of backtest overfitting (CSCV), 1,081 versions | 1.4% | 1.4% |
| Monthly difference | | +0.6 points a year, t-statistic 0.9 (0.8 on the dashboard's universe) |
| Monte Carlo: beats the half switch over 5 / 10 / 20 years | | 63% / 73% / 85% |
| Abroad (Japan, UK, Germany, India, Hong Kong) | 15.1 / 13.2 / 5.9 / 32.5 / 27.1% | 16.2 / 13.1 / 5.5 / 33.7 / 26.2% |

Limits, stated plainly: most of the gain comes from two years (+16 points in 2011, +8 in 2016) and it gave back 6
points in 2015; the monthly difference is far from significant; abroad it helped in two markets and hurt in three,
all within about a point; and the share of the account was chosen on this history. It went in on probation, and the
paper record lists it as an update.

## No-T-bills pick by the 3-month change (default since Oct 19, 2026)

Wherever the rules would hold T-bills (the downtrend or lower-high exit with neither TLT nor GLD rising, the whipsaw
switch with nothing up, the narrow-market cash week), the plan now holds whichever of TLT / GLD is up more over 63
sessions, if it is up at all, else cash (`BILLS_LOOK` in `mtl/rotation.py`; engine `NBup` has `nobil_n=63`, `NBb6`
keeps 126). The rotation and the exits still pick by 6 months: moving them to 3 months as well did worse. Every
comparison in the audit (au7) was rebuilt on the new default with the same single change as before.

| Check | 6 months (until Oct 19) | 3 months |
|---|---|---|
| From 2000, a year before tax (after tax) | 41.0% (25.9%) | 42.4% (26.7%) |
| Worst drop from 2000 / from 2020 | −34% / −23% | −34% / −23% |
| From 2010 / 2016 / 2020 | 43.3% / 50.8% / 75.0% | 44.7% / 53.2% / 77.9% |
| Seven start years (2000, 2005, 2008, 2010, 2013, 2016, 2020) | | ahead in all seven, by 1.3 to 2.8 points |
| Look of 2 / 4 / 5 months instead, points vs 6 months | | −0.2 to −2.1 / +0.9 to +5.1 / −0.2 to +0.5 |
| Rolling windows from 2000: 3-year / 5-year ahead–behind | | 232–45 of 285 / 238–22 of 261 |
| 2000–2011 / 2013–2025 | 37.3% / 40.8% | 38.5% / 40.9% |
| Ten separate periods | | better in 6, about the same in 2, worse in 2 (2013–2015, 2018–2021) |
| Deflated Sharpe, 1,353 versions counted | 99.49% | 99.70% |
| Probability of backtest overfitting (CSCV), 1,353 versions | 2.2% | 2.2% |
| Monthly difference | | +0.9 points a year, t-statistic 1.2 (155 of 321 months differ) |
| Monte Carlo: beats the 6-month pick over 5 / 10 / 20 years | | 71% / 80% / 88% |
| Longest stretch below a peak | 24 months (2001–2003) | 25 months (Jul 2014 – Aug 2016) |
| Abroad (Japan, UK, Germany) | 18.1 / 12.1 / 4.9% | 18.6 / 12.6 / 5.0% |

The live code agrees with the engine: on all 252 days the 2000 run held plain cash, the live pick (`bills_pick`) also
gives cash, and the committed engine reproduces the test runs exactly from 2000, 2010, 2016 and 2020.

Limits, stated plainly: the gain swings by year (+26 points in 2026, +14 in 2009, +11 in 2017; −15 in 2025, −7 in
2008), 2013–2025 is about level, the monthly difference is not significant, and the look was chosen on this history
(4 months did as well). It went in on probation, and the paper record lists it in its Oct 19 update.

## Managed futures instead of cash (default since Oct 20, 2026)

Where the no-T-bills pick finds neither TLT nor GLD up over 3 months, the plan now holds DBMF, a fund that follows trends
in stock, bond, currency and commodity futures, instead of plain cash earning nothing (`CASH_FUND` in
`mtl/rotation.py`; engine `NBup` has `nobil_fb='DBMF'`, `NBc3` keeps plain cash). It applies only from the fund's first
close (May 8, 2019); before that the plan holds cash as before, so every gain below is from 2019 on. The fund's fees are
in its prices. Every comparison in the audit (aumf) was rebuilt on the new default with the same single change as before.

| Check | Plain cash (until Oct 20) | DBMF |
|---|---|---|
| From 2000, a year before tax (after tax) | 42.4% (26.7%) | 42.9% (27.0%) |
| Worst drop from 2000 / from 2020 | −34% / −23% | −34% / −23% |
| From 2010 / 2016 / 2020 | 44.7% / 53.2% / 77.9% | 45.6% / 54.6% / 80.5% |
| Strategy lab path from 2000 / 2010 / 2020 | 42.9% / 51.0% / 77.5% | 43.5% / 52.0% / 80.3% |
| Since May 2019, a year | 72.9% | 75.3% |
| Days held instead of cash since 2000 | | 194 (58 cash days before the fund began) |
| Years it changed (2019, 2022, 2023, 2024, 2025, 2026) | | better in all six: +0.4, +1.7, +4.3, +1.1, +2.6, +8.1 points |
| Rolling windows from 2000 that differ: 3-year / 5-year ahead–behind | | 80–3 / 80–3 |
| Monthly difference | | +0.4 points a year, t-statistic 1.2 (21 of 321 months differ: 14 better, 7 worse) |
| Monte Carlo: beats plain cash over 5 / 10 / 20 years | | 69% / 87% / 96% |
| Sharpe / Sortino | 1.30 / 1.98 | 1.31 / 2.00 |
| Deflated Sharpe, 1,388 versions counted | 99.63% | 99.69% |
| Probability of backtest overfitting (CSCV), 1,388 versions | 2.3% | 2.3% |

**Before the fund existed.** A trend-following stand-in rebuilt back to 2000 (12 markets: four stock indexes, long
Treasuries, gold, crude oil and six currencies; direction from 1-, 3- and 12-month returns, equal risk per group, scaled to
12% a year of volatility, cash earning T-bills; monthly correlation with DBMF 0.65) added 2.2 points a year from 2000 on
the Strategy lab path, worst drop −32% vs −36%. In place of cash abroad (each market's own stocks, the stand-in in local
currency) it was ahead in seven of nine markets: Japan 17.5% vs 16.7%, UK 14.6% vs 13.7%, Switzerland 11.7% vs 10.9%,
Brazil 22.0% vs 21.7%, Taiwan 39.4% vs 39.1%, India 33.8% vs 33.6%, Germany 5.8% vs 5.7%; behind in Korea (23.5% vs
23.6%) and Hong Kong (26.4% vs 26.8%); +0.3 a year on average. In place of gold and bonds as well it did worse, and an
inverse S&P fund in the cash week helped in the US only, so only the cash slot changed.

The live code agrees with the engine: on all 78 decisions since 2000 where the engine's default held its fallback (21 in
plain cash before May 2019, 57 in DBMF after), the live pick (`bills_pick`) gives the same.

Limits, stated plainly: the gain rests on about 200 days since 2019, more than half of it in 2023 and 2026; the monthly
difference is not significant; the years before 2019 rest on a stand-in, which is a model of such funds, not the fund. It
went in on probation, and the paper record lists it in its Oct 20 update.

## Paper record: the live forward test

`mtl/paper.py` keeps a frozen, time-stamped paper record of the default plan in `data/paper_ledger.json`, starting
Oct 14, 2026, the day the current default (with the rebound rule) went live. The first entry comes from that
evening's saved dashboard snapshot; every later one is added by the scheduled scanner run.

- **Logged after the close, never edited.** Each evening (`PAPER_LEDGER_WRITE=1` in `.github/workflows/scanner.yml`,
  and only once New York has closed) the run appends what the plan will hold after the next close: the mode, the
  whipsaw half and the Boost list, the weights that follow, the time it was logged and a fingerprint of the rule
  code. A day already logged is never rewritten; the repo's commit history time-stamps each entry independently.
- **Frozen rules.** The fingerprint covers the rule modules and the scanner's settings lines (not page code or file
  paths). The page says whether it still matches the one frozen on Oct 14; a rule change shows the date it happened.
  A deliberate change is listed in the ledger's `updates` (date, new fingerprint, what changed): the fading-energy
  filter on Oct 16, 2026. Entries logged before it keep their own fingerprint, and the replay check only compares
  entries logged under today's rules.
- **Cash slots.** Each stock on the list is a fifth of the account; a slot the fading filter leaves empty is cash.
- **Paper fills.** Each decision fills at the next session's close with 0.15% per side on what changes hands;
  positions drift between trades and are reset to their weights on the weekly trade.
- **Replay check.** Every run replays each logged day on that run's data and code and lists any day whose mode,
  half or list differs from what was logged.
- **Expected ranges.** The page compares the record with every 3-, 6- and 12-month window of the 2000–2026 backtest
  and warns only when the latest 3-, 6- or 12-month stretch (the longest reached) is below the backtest's 1-in-20
  floor for that length or trails SPY by more than its 1-in-10 margin, or when a drop is deeper than the backtest's
  worst (−33%).

The dashboard's universe is the S&P 500 plus the 15 Nasdaq-100 members outside it, so the ranges come from a
backtest of that universe (next section), not the S&P-only audit. Since Oct 16, 2026 the ranges come from that backtest with the fading-energy filter.

## `ndx_universe.py`: the default plan with the dashboard's Nasdaq-100 additions

The audit backtest uses S&P 500 members only; the dashboard also ranks the 15 Nasdaq-100 members outside the
S&P 500. This runs the default plan three ways on the same engine: S&P 500 only (`NBup`), plus the 15 only while
each was in the Nasdaq-100 (`NDXa`, join dates in `ndx_join_dates.json`, from Nasdaq's announcements), and plus
the 15 from their first price (`NDXh`, hindsight, as the dashboard's own replay treats them).

Result on Oct 15, 2026 (return a year before tax, worst drop in brackets, daily):

| Since | S&P 500 only | With the 15 from their join dates | With the 15 from their first price |
|---|---|---|---|
| 2000 | 37.8% (−33%) | 37.9% (−33%) | 37.4% |
| 2016 | 48.2% (−23%) | 48.6% (−25%) | |
| 2020 | 68.8% (−23%) | 69.5% (−25%) | |
| 2024 | 113.5% (−23%) | 118.8% (−25%) | |

After tax from 2000: 23.8%, 23.9% and 23.6%. With the join dates, one of the 15 was held after 98 of the 1,746 rebalances: MercadoLibre
(2017–2024), PDD (2020–2024), MicroStrategy (2025), Shopify (2025), and Arm, Astera Labs and Nebius (2026). The
3/6/12-month ranges barely move. Limits: all 15 joined the Nasdaq-100 in 2017 or later, and Nasdaq-100 members
outside the S&P 500 that later left the index (for example Zoom, DocuSign, Peloton and JD.com around 2020–2023)
are not included, so this checks the 15 as traded, not the full point-in-time Nasdaq-100.

## Fed-day hold (default since Oct 31, 2026)

When the rules decide to leave stocks and the trade would come at the close just before a scheduled Fed decision day,
the trade waits one session and happens at the decision day's close (`mtl/fedday.py`, dates in
`data/fomc_dates.json`; engine `NBup` = with it, `NBnofd` = without). It never moves the account into stocks.

It came from a search for reasons to act that don't come from prices (calendar, Fed liquidity, insider buying,
earnings timing, sector caps, analyst revisions): the others were lower from 2000 or are being tested forward. The plan's
stocks gained 0.45% a day on scheduled decision days against 0.10% on other days since 2000, in each of 2000-07,
2008-15 and 2016-26. Staying one more day after an exit normally costs the plan (-0.32% on average over 108 exits),
but before a decision day it gained in 6 of 7 cases (+1.08%; 2% of random picks of 7 other exits did as well). Those
counts are from the daily replay on the lists rebuilt from Wikipedia's changes; on the real member lists the engine's 6
cases paid 4 times (+1.33, +2.33, +0.70, -1.41, -0.17, +2.09% on the decision day, +0.8% on average), and the
scanner's own replay (today's stocks) 3 of 5 (+0.06% on average), so the case-by-case evidence is thinner than the
first count suggested.

Real member lists, 0.15% per side: 40.7% a year from 2000 vs 40.3% without it, 45.6% vs 45.4% from 2010, 58.2% vs
58.0% from 2016, 84.4% vs 83.7% from 2020, worst drop -35% either way (t-stat 1.6 on monthly returns); on the lists
rebuilt from Wikipedia's changes 46.2% vs 45.8%. It acted 6 times (Nov 2002, Apr 2009, Oct 2011, Mar 2017, Jun 2025,
Dec 2025). Holding 2-3 sessions before the decision added more on paper, all from one episode (Jan 2009); moving into
stocks for every decision day lost to trading costs (44.2% vs 45.8%). Few cases, so it went in on probation.

## Buying-volume weighting (default since Nov 2, 2026)

At each trade, a held stock in the top third of the eligible S&P 500 members by up-day volume over down-day volume
(shares traded on up closes / on the other closes over 63 sessions) gets twice the money of the others
(`mtl/volweight.py`; engine `NBup` = with it, `NBnovw` = without). The stocks, the slots (an empty slot stays a fifth in
cash) and the timing are unchanged; with no buying stock, or all of them, the split stays equal.

It came out of a search of stock-level signals as 2x weightings on the plan's own picks (64 single and paired signals:
volatility, volume trend, recent volume, volume spikes, up/down volume, 1/3/6-month strength, distance from the 52-week
high, top or bottom third). 21 beat the plan from 2000; the 10 that were ahead from 2000, 2010, 2016 and 2020 and in
both halves all used volume, and the opposite tilts (weight on falling volume, on more selling) lost. Price tilts
(strength, the 52-week high, volatility on its own) all lost: the plan already buys on strength.

Real member lists, 0.15% per side: 42.7% a year from 2000 vs 40.7% without it, 47.0% vs 45.5% from 2010, 60.0% vs
57.8% from 2016, 86.6% vs 83.8% from 2020, worst drop -34% vs -35%, Sharpe 1.30 vs 1.26 (the gain is not only more
risk), better in 15 of 27 years; without 2016 and 2025, 41.2% vs 39.5%; 2000-12 31.8% vs 29.8%, 2013-26 54.0% vs 51.9%.
At 0.30% per side 34.1% vs 32.7%. Robustness (all ahead from 2000): 1.5x, 2x and 3x; top quarter, third and half; up/down
volume over 1, 3 or 6 months (41.6-43.6%); paired with rising volume (3 months vs a year) 42.2-46.3%, the best but more
dependent on 2025. Against it: in a simple top-5 test on eight foreign markets (today's index members) it helped in 4
and hurt in 4 (a combined Europe pool also lagged), while in the same simple test on the S&P 500 it added 2.0 points a year; and it was found among many
tested ideas. So it went in on probation: `mtl/volweight_check.py` scores each live trade against equal parts and after
a year flags it for review if it trails by more than the backtest's 1-in-10 worst year.

## Earnings-jump weighting (default since Nov 2, 2026)

At each trade, a held stock that closed 3% or more higher on its last earnings report's reaction day (the report's own
session for one out before or during it, the next session for one after the close), within the last 63 sessions, gets
twice its money too (`mtl/earnjump.py`; it multiplies the buying-volume weighting: a stock with both gets 4 shares of
the stock money against 1 for one with neither). Report dates: SEC 8-K item 2.02 filings from 2004
(`data/earnings_dates.json`), kept current each night from Yahoo for the stocks the plan holds or ranks near the top.
Engine `NBup` = with it, `NBnoej` = without.

It came out of a search of about 20 second signals on top of the buying-volume weighting: smooth climbers (share of up
days), residual strength, the biggest one-day gain, last week's pullback, seasonality, insider buying, industry
strength, earnings disappointments and earnings jumps. Industry strength (top half) was also above t 1 (1.5) but
deepened the worst drop to -38%; the others were under t 1 or negative.

Real member lists, 0.15% per side: 44.7% a year from 2000 vs 42.7% without it, 49.4% vs 47.0% from 2010, 64.7% vs
60.0% from 2016, 94.9% vs 86.6% from 2020, worst drop -33% vs -34%, Sharpe 1.33 vs 1.30, t-stat 1.8 on monthly returns
(1.5 from 2005, when the dates start), better in 15 of 23 years. Nearby settings: jumps of 2% (t 2.0), 4% and 5%
(t 1.1), windows of 90 and 126 sessions (t 1.9), 1.5x (t 1.9) and 3x (t 1.1) all ahead; a 42-session window was level
(t 0.0). Against it: 2005-2015 was level (31.2% vs 31.1%), so nearly all of the gain is 2016-2026; there is no foreign
earnings data to check it abroad; and it was found in a search. On probation: `volweight_check.scorecard` scores each
live trade against the same trade without the rule, and after a year flags it if it trails by more than the scanner
replay's 1-in-10 worst year.

## Stretched-and-warned exit (default since Nov 2, 2026)

When 3 or more of the eight dominoes (`mtl/dominoes.py`: tech, small caps, banks, transports 10%+ under their 1-year
highs, junk bonds 3%+ under, the Fed funds rate 1 point+ above a year earlier, an inverted yield curve in the last year,
oil 50%+ above a year earlier; the three FRED series read a session late) are down and SPY's latest weekly close is 2 or
more standard errors above the straight line through its last 52 weekly closes (logs), the plan holds the haven pick for
20 sessions from the first close where both are true, if it holds stocks then (`mtl/stretchwarn.py`). Engine `NBup` =
with it, `NBnosw` = without; the dominoes count per session is `dominoes_counts.json` in the side data
(`research/backtest/side_data.py`).

It came out of a run of exits built on the dominoes (Nov 2, 2026): the dominoes count alone or with crash triggers
(0 of 40 ahead), the count arming a 10/15/20% stop on the plan (0 of 105), and the count with SPY or a haven at a
weekly-RSI, channel or 200-day extreme (71 combinations); only the channel extreme with the count was ahead.

Real member lists, 0.15% per side: 45.8% a year from 2000 vs 44.7% without it, the same from 2001 on, the same worst
drop (-33%, 2006), Sharpe 1.38 vs 1.33, after tax 28.8% vs 28.1%, t-stat 1.4 on monthly returns. 2000: +62.9% instead
of +31.8% (spring drop -17% instead of -33%). It acted once since 2000 (Mar 24, 2000; a second start, Apr 2009, found
the plan already out of stocks). Nearby settings: 2 dominoes 46.0% (it also acts twice in late 2006: -21.4% instead
of -24.1%, worst drop -31%), 4 dominoes 45.8%, 5 dominoes 44.7% (a start 3 sessions later in 2000, about level); a 1.5
line 43.2%, 14 starts, a loser; a 2.5 line never acts; 40 sessions 46.3%. SPY's stretch at the 2000 top was 2.05, just
over the line. As a replacement for the narrow-market cash week instead of an addition it lost (41.1% a year from
2000, 41.9% from 2010). So it rests on one trade caught by a line set after seeing it: on probation, kept because it
acts so rarely that it costs little when it is wrong.

## Near-the-high weighting, hot-commodity buy skip and unemployment step-aside (default since Nov 2, 2026)

Three rules added together, with a 40% cap on any one stock:
- **Near-the-high weighting** (`mtl/nearhigh.py`): a held stock within 3% of its highest close of the last year gets
  twice its money too. It multiplies with the buying-volume and earnings-jump weightings, and no stock may hold more than
  40% of the account (`mtl/volweight.CAP`; the excess is spread over the others).
- **Hot-commodity buy skip** (`mtl/hotcomm.py`): no new buy of a metals or energy stock (`data/industries_all.csv`)
  while copper (metals) or crude oil (energy) is up 50%+ over 126 sessions. The slot stays in cash, as with the fading
  filter, and the green light sets it aside.
- **Unemployment step-aside** (`mtl/jobwarn.py`): FRED's UNRATE, each month used 36 days after its first day. When the
  3-month average is 0.3 points+ above its low of the year before while SPY is under its 150-day average, the haven for
  21 sessions from the first such close, if in stocks then.

Engine `NBup` = with all three, `NBno3` = without (the side data gains `jobwarn.json`).

They came out of a Nov 2, 2026 search of about 100 versions (sector and industry limits, keep ranks, buy filters,
earnings-date filters, haven mixes, look-back windows, FRED macro and financial-stress signals as exits and as
stay-ins), in which nothing was robust on its own:
- near-the-high 2x at 3% / 5% gave 46.7% / 46.4% (t 0.6 / 0.5);
- the unemployment step-aside at 0.3 / 21 sessions gave 47.3% (t 1.05, ahead in 3 years and behind in 4);
- skipping metals and energy buys at 50% / 6 months gave 46.2% (t 1.5, nearly all of it 2021).

Combined, with the cap, on the real member lists, 0.15% per side:

| | 2000 | 2010 | 2016 | 2020 | 2000-12 / 2013-26 | Worst drop | Sharpe | After tax |
|---|---|---|---|---|---|---|---|---|
| With the three rules | 47.6% | 52.0% | 67.9% | 102.0% | 35.7 / 59.3 | -28% | 1.45 | 29.7% |
| Without them | 45.8% | 49.4% | 64.7% | 94.9% | 34.7 / 56.7 | -33% | 1.38 | 28.8% |

t-stat 0.9 on monthly returns; ahead in 14 years and behind in 13. Without the cap: 48.5% (t 1.35), but one stock
held up to 62% of the account, and 40% or more in 40% of trades.

Against it:
- each setting was the best of its own search;
- neighbours with the cap (near 2-7%, commodity 25-35% over 3 months, unemployment 0.4) gave 46.2-46.9% from 2000 but
  fell behind from 2016 and 2020;
- with unemployment at 0.5 it was behind from 2000 (45.1%);
- the unemployment figures are today's revised ones, because ALFRED's first-release vintages could not be downloaded.

So all three are on probation. The near-the-high rule is scored per trade like the other weightings
(`volweight_check`, the scanner's nearCard).

## Near-the-high doubling off in a down market (default since Nov 2, 2026)

In 2000-02 the near-the-high weighting cost the plan about 10 points against the version before it: in a falling
market a stock at its 1-year high is often about to roll over (MU at the 40% cap in Jul 2000, NTAP doubled in Oct
2000), and the plan took 25 months to get back to its Jul 2000 peak. So the doubling is now off while SPY closes under
its 150-day average (`mtl/nearhigh.MA`, the same average the unemployment step-aside and the exit gate use); the
earnings-jump and buying-volume weightings and the cap are unchanged. Engine `NBup` = with the switch, `NBno4` =
without (`vw.hi52.off`).

Real member lists, 0.15% per side:

| Doubling off when | 2000 | 2010 | 2016 | 2020 | Worst drop | Sharpe | After tax | t vs always on | Years +/- |
|---|---|---|---|---|---|---|---|---|---|
| SPY under its 150-day average (adopted) | 48.2% | 52.6% | 69.1% | 103.6% | -28% | 1.47 | 30.1% | 1.37 | 12 / 7 |
| SPY under its 200-day average | 48.2% | 52.6% | 69.1% | 103.8% | -28% | 1.47 | 30.1% | 1.31 | 11 / 7 |
| SPY lower than 6 months ago | 48.2% | 52.4% | 69.0% | 103.5% | -28% | 1.46 | 30.1% | 1.15 | 11 / 9 |
| SPY under its 100-day average | 48.0% | 52.3% | 68.3% | 103.5% | -28% | 1.46 | 30.0% | 0.82 | 9 / 10 |
| the unemployment flag | 48.0% | 52.5% | 68.5% | 103.1% | -28% | 1.46 | 30.0% | 1.35 | 4 / 2 |
| SPY under its 50-day average | 47.7% | 52.5% | 68.4% | 103.3% | -28% | 1.46 | 29.8% | 0.10 | 13 / 11 |
| never (the plan before) | 47.6% | 52.0% | 67.9% | 102.0% | -28% | 1.45 | 29.7% | - | - |
| SPY 15% or 20% under its 1-year high | 47.4-47.5% | 52.1% | 68.0% | 102.2-102.3% | -28% | 1.45 | 29.7% | -0.5 | - |

The gain: 2000 +57.7% instead of +49.6%, 2025 +9.2 points, 2008 +4.3; behind in 2007 (-2.8), 2015 (-2.3) and 2001
(-1.8). The 2000-02 wait for a new high is 19 months instead of 25. The 100-200 day averages all helped, but the
t-stat is only 1.4 and two years (2000, 2025) carry most of the gain: on probation.

## Overfitting among close versions (Nov 2, 2026)

The earlier overfitting checks (deflated Sharpe 99.69%, PBO 2.3%, 1,388 versions) pooled many quite different
strategies. On Nov 2, 2026 the same checks were run on close versions only: 324 distinct versions of the current plan
tried that day on the real member lists (every rule switched off in turn, the variations of each new rule, per-stock
exits, slower trading after losing streaks), monthly returns Jan 2000 - Oct 2026.

| Check | All 324 | The 295 within 10 points of the best |
|---|---|---|
| Deflated Sharpe (N = the pool, 2,700 or 10,000 tried) | 100% (luck ~0.41-0.55) | 100% (luck ~0.16-0.21) |
| PBO (CSCV, 16 blocks, 12,870 splits) | 51% | 56% |
| Walk-forward 2005-2026: best Sharpe so far each year vs the typical version | 45.3% vs 45.9% | 45.3% vs 46.2% |

The plan's monthly Sharpe (1.46) is far above what luck gives the best of that many tries, so the edge over doing
nothing holds. But choosing between close versions is a coin flip: the in-sample winner does no better than the median
out of sample, and the best Sharpe in the pool belongs to slow-trading variants that were rejected on their own merits.
So each small rule added on Nov 2 (about +0.5 to +2 points a year, t 0.9-1.4) is on probation and is judged on the
paper record, not the backtest.

## Rejected Nov 2, 2026: per-stock exits and slower trading after losing streaks (the 2006 problem)

In Jan-Apr 2006 the plan lost 8.8% while SPY gained 6.0% and every sector fund but health care rose: the 2005 leaders
(AMD, FCX, AAPL) rolled over one by one. Against the current plan (48.2% a year from 2000, 2006 -16.9%):
- **Per-stock exits** (22 versions: a 10-25% trailing stop, a close under the stock's own 50- or 100-day average, the
  stock 10-20% behind SPY over 1-3 months; each always or only while SPY is above its 150-day average): best 48.2%
  (behind SPY by 20% over 3 months, rising market only), behind from 2010, 2016 and 2020, 2006 -21.3%. The two that
  helped 2006 (-8.1%, -8.4%) made 44.0% and 32.4% a year. Strong stocks drop 10-20% on the way in most years; the stop
  sells the dip and the 20-session ban keeps the plan out.
- **Holding SPY when the plan trails it** (192 replay versions): best +0.3 points, 2006 unchanged.
- **Trading every 2, 4 or 8 weeks after a losing streak** (28 versions: 3 of 4 to 7 of 10 sales lost, or the last 5 or
  8 sales down 3% or 6% on average; while the streak lasts or for 1, 3 or 6 months): best 49.5% (4 of 6, every 2
  weeks) but ahead in 11 years and behind in 15, worst drop -31%, t 0.7, neighbours 43.5-49.0%; 2006 no better
  (-15.9% at best). Every 4- or 8-week version lost 2-8 points a year.

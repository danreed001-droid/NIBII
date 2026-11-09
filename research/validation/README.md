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

## Heavy-volume selling (default since Nov 3, 2026)

Two parts with one idea, staying away from a stock that big holders are dumping (`mtl/volsell.py`):
- no new buy of a stock with a down close on 4x+ its average volume of the 50 sessions before, in the last 5 sessions;
- a holding that closes 6%+ down on 4x+ that volume is sold at the next close (barred for the usual 4 weeks).

Engine `NBup` has `vz` (the buy part) and `vz2` (the sell part); `NBno5` = without. It came out of a Nov 2-3, 2026
search: three volume ideas (about 30 versions), each alone a near-miss (the buy part 49.0% a year from 2000, t 1.7,
mostly one 2018 trade; the sell part 49.1%, behind from 2010), then all 30 combinations of five near-misses, in which
this pair was the only one ahead from every start without a deeper drop.

| | 2000 | 2010 | 2016 | 2020 | Worst drop | Sharpe | After tax |
|---|---|---|---|---|---|---|---|
| With the rule | 50.0% | 53.6% | 71.0% | 104.4% | -27% | 1.50 | 31.2% |
| Without | 48.2% | 52.6% | 69.1% | 103.6% | -28% | 1.47 | 30.1% |

12 nearby settings: 10 ahead from 2000 (48.6-50.1%), 9 from 2010 and 2016, about level from 2020 (102.4-106.1%), worst
drop -27% in most; both losers had the sell part at 3x volume (47.2-47.9%), where it fires too often. Against it:
t-stat 1.2 (0.4-1.4 across the neighbours), the same few years carry every version (2013 +11.5, 2005 +10.9, 2007 +8.1
points; 2025 -10.9), and it is the best of about 60 versions tried that night, the case the close-versions overfitting
check (above) warns about: on probation, judged on the paper record.

## Rejected Nov 3, 2026: other market measures, a sector cap, removing the weakest rules

Against the current plan (50.0% a year from 2000, worst drop -27%), strict test:
- **SPY replaced in every market signal** by an index built from the members at each date (daily-curve figures, 49.9 /
  53.5 / 71.2 / 104.8% for the plan): equal weight (tracks RSP, daily correlation 0.993) 39.8 / 39.7 / 53.6 / 76.8%,
  worst drop -41%; dollar-volume weighted 38.0 / 44.7 / 57.7 / 79.2%, worst drop -61% (2008 -36.9%). The equal-weight
  index lags out of bottoms (2020 +64% instead of +153%); the plan's stocks are large companies that move with SPY.
- **No sector above 40 / 50 / 60% of the account** (`data/sectors.csv`, excess to the other sectors' stocks or to
  cash): 39.6-48.8% a year from 2000, 76.4-97.1% from 2020; days below -5% fall from 52 to 21-44, but the worst drop
  stays -27% and the worst day -11.8% (Jan 20, 2009, five sectors held); 2026 costs 53-117 points.
- **Removing the weakest rules in sets** (12 versions: the rate/gold regime, whipsaw switch, hot-commodity skip,
  rebound, break re-entry, surge exit, Fed-day hold, buy freeze / green light): 47.0-50.0% from 2000 but 90.2-102.3%
  from 2020 against 104.4%; even the rate/gold regime alone costs 2 points from 2020. The rules overlap: all kept.

The plan's worst single days since 2000: -11.8% (Jan 20, 2009) and -11.4% (Sep 1, 2009), then -7.0 to -8.3%; 52 days
below -5% and 10 below -7% in 6,737, nearly all from one theme held at 30-40% a stock while SPY moved 0-2.5%.

## Rule 18's sell only in a rising market (default since Nov 3, 2026)

The sell part of the heavy-volume selling rule now acts only while SPY closes at or above its 150-day average
(`mtl/volsell.MA`; engine `vz2.gate='spy150'`, `NBno6` = without). In a falling market a heavy-volume drop is often
panic near a bottom. The buy part is unchanged.

| Sell part acts | 2000 | 2010 | 2016 | 2020 | Worst drop | t | Years +/- |
|---|---|---|---|---|---|---|---|
| Only while SPY is above its 150-day average (adopted) | 50.5% | 55.1% | 72.4% | 105.1% | -27% | 0.6 | 6 / 4 |
| ... its 100-day average | 50.7% | 55.5% | 72.8% | 105.1% | -27% | 0.7 | 7 / 4 |
| ... its 200-day average | 50.5% | 54.7% | 72.4% | 105.1% | -27% | 0.7 | 4 / 3 |
| ... 150-day, at a 5% drop | 50.9% | 55.6% | 73.2% | 104.7% | -29% | 0.8 | 9 / 8 |
| ... 150-day, at 5x volume | 49.2-49.4% | 53.6-53.9% | 71.0-71.5% | 104.1-104.5% | -27% | -0.5 to -0.6 | 7 / 12-13 |
| Always (rule 18 as first adopted) | 50.0% | 53.6% | 71.0% | 104.4% | -27% | - | - |

At 4x volume every average (100 / 150 / 200-day) was ahead from every start; rebound years gained (2018 +9.9, 2004
+6.1, 2020 +5.8 points) and 2001, 2007 and 2008 gave a little back (-4 to -7). Small (+0.5 a year) and t 0.6: on
probation. Also tested that night and rejected: selling on a 5-15% one-day drop on normal (under 2x) or quiet (under
1.5x) volume or at any volume (34.8-50.3% a year; 15% on quiet volume was +0.3 but deepened the worst drop to -32%),
and adding such a sell to the rising-market version (45.3-49.1%).

## Rule order: re-entry over the unemployment step-aside, lower-high over rebound (default since Nov 3, 2026)

How often the rules clash since 2000: the unemployment step-aside overrode the break re-entry on 32 days (2002 and
2020) and the rebound rule on 2; the price-break rule overrode the re-entry on 4 days; the rebound rule overrode the
lower-high exit in 2008 and 2011. Flipping each clash (strict test, against 50.5% a year from 2000):

| Order change | 2000 | 2010 | 2016 | 2020 | Years +/- |
|---|---|---|---|---|---|
| Re-entry over the step-aside | 51.0% | 55.6% | 73.2% | 106.6% | 2 / 0 |
| Lower-high exit over the rebound rule | 50.9% | 55.2% | 72.4% | 105.1% | 2 / 0 |
| Both (adopted) | 51.4% | 55.7% | 73.2% | 106.6% | 4 / 0 |
| Rebound over the step-aside | 50.6% | 55.3% | 72.6% | 105.5% | 1 / 0 |
| Re-entry or rebound over the price break | 50.5% | (no change) | | | 0 / 0 |
| Every stay-in rule over every exit | 50.4% | 55.6% | 73.2% | 106.7% | 1 / 1 (2002 -8.3) |

The step-aside reads lagging unemployment figures and kept the plan in bonds after the re-entry signal had caught the
2020 and 2002 turns (+12.9 and +5.6 points); the rebound rule pulled the plan into a failed 2008 bounce (+9.0 with the
lower-high exit winning). Worst drop -27% either way, t-stat 1.9, but only four years change: on probation.
`scripts/momentum_scan.py` RULE_ORDER; engine `legrot.prec` (`re_over_jw`, `lh_over_reb`), `NBno7` = before.

## Candle re-entry (rule 19, default since Nov 5, 2026)

The owner's idea from a chart: two red days, then a day that closes above them, while SPY is down -> stocks for two
weeks whatever the other rules say. 11 versions first (strict test, against 51.4% a year from 2000):

| Version | 2000 | 2010 | 2016 | 2020 | Worst drop | Signals |
|---|---|---|---|---|---|---|
| Closes above both red opens, fresh 20-day low, 10%+ down | 52.0% | 56.6% | 73.7% | 107.6% | -26% | 22 |
| Green, closes above both red closes, fresh low, 10%+ down | 52.8% | 55.5% | 71.9% | 103.8% | -26% | 36 |
| ... the same, held 4 weeks | 49.3% | 54.8% | 71.0% | 100.5% | -51% | 36 |
| ... any day 20% / 15% / 10% down | 50.4 / 47.6 / 44.2% | | | | -39 to -56% | 30-97 |
| ... under the 150-day average | 44.6% | 50.5% | 64.9% | 95.8% | -56% | 136 |

Without the fresh-low condition it buys back into the 2008 crash (-86 points that year at 10%). Neighbour check of
the first row (27 versions: an 8 / 10 / 12% drop, a 15- / 20- / 30-day low, 5 / 10 / 15 sessions held): 20 ahead of
the plan from every start, all 9 at 12%; 3 weeks held is the weak spot. Adopted: 12%, 20-day low, 10 sessions.
52.6% a year from 2000 vs 51.4%, 57.5 / 75.4 / 110.8% from 2010 / 2016 / 2020 vs 55.7 / 73.2 / 106.6%, worst drop
-26% vs -27%, Sharpe 1.56 vs 1.54, ahead in 6 years and behind in 2, t-stat 1.0. 19-20 signals since 2000; October
2022 carries most of it (+25.8 points that year); 8 of the 13 times it moved the plan out of a haven, the plan went
back to the haven when the two weeks ended. At a 10% drop it also fired in April 2025 and lost 24 points; 12% skips
that, which may flatter the choice: on probation. `mtl/candle.py`; engine `legrot.candle`, `NBno8` = before.

Also tested that day and rejected, as exits (two weeks out of stocks; the other rules unchanged):
- the mirror image, two green days then a red day closing below both (their closes or opens), with the three days
  under the high of the 1 / 2 / 3 months before, out 2 / 3 / 4 weeks (18 versions): 26.7-44.0% a year, worst drop
  -26 to -40%; 132-282 signals, SPY afterwards no worse than on any day;
- a red day with a long upper wick within 1% of the 50- / 100- / 126- / 150-day high, then a red close under its
  close or low within a week (24 versions): 39.3-43.4%;
- either pattern only with a second warning: SPY under its 50- / 150-day average, 1.5x volume, a VIX jump, 2+
  dominoes, the narrow-market warning, an overbought RSI, the unemployment flag, gold / bonds / the dollar up, bonds
  down, rising 10-year yields (62 versions): best 51.9% (with the overbought RSI; -28% worst drop, behind in 7 years
  and ahead in 3), most 38-51%.

## Run-up skip (rule 20, default since Nov 6, 2026)

From a 2008 losing trade (a land-drilling contractor bought after a near-vertical run while SPY was falling) and the
trade table of all 1,450 trades since 2000 (stretched buys into a weak market did worse): while SPY trends down, skip a
new pick that has run up. First pass (28 versions): "up 40%+ in 3 months" with SPY under its 150-day average, or down
over 6 months, was ahead from every start with the same -26% worst drop; "up 20%+ in a month" and the RSI versions
gained more in some starts but deepened the worst drop (-28% to -34%). Neighbour check (36: a 30 / 40 / 50% run over 2
/ 3 / 4 months, SPY under its 100 / 150 / 200-day average or down over 6 months): 14 ahead from every start, 13 with
the same worst drop, and all 8 with a 40-50% run over 2 months. Adopted: up 50%+ in 42 sessions while SPY is lower than
126 sessions earlier. 54.1% a year from 2000 vs 52.6%, 58.5 / 77.1 / 114.1% from 2010 / 2016 / 2020 vs 57.5 / 75.4 /
110.8%, worst drop -26% either way, better in 6 years (2003 +21.3, 2026 +18.0, 2002 +6.5, 2023 +4.3, 2022 +3.4, 2009
+2.4) and worse in 1 (2001 -3.7), t-stat 1.8. The idea came from the same history: on probation. `mtl/runup.py`;
engine `nostretch_down` (`NBno9` = before).

Also tested Nov 5-6, 2026 and rejected (strict test against the plan of the day):
- SPY weekly RSI bearish divergence as a trigger for stricter exits, with or without volume (62 versions): 41.3-52.3%;
- that divergence plus a candle sell pattern on SPY (68 versions): one version acting twice in 26 years was +0.1, the
  rest 44.9-52.3%;
- a held stock's own weekly divergence + candle pattern + volume (12 versions, the slot to the next stock, cash or the
  haven): 50.3-53.2% on 1-30 sales, the cash and haven versions the same as the next stock;
- dominant-actor gauges (average stock correlation, stock-bond correlation, the best-vs-worst spread over 2-6 months)
  as switches to SPY, half SPY or the haven (42 versions): 32.8-52.7% (the one at 52.7% acted on 4 days); the plan
  earns most when the spread is wide and least when one force moves everything, but beats SPY in every bucket;
- no new buys within 1-4 weeks of an earnings report, always or by gauge (15 versions): 44.3-52.8%;
- SEC-filed financials as buy filters from 2011 (profitable, revenue / earnings growth, return on equity, debt,
  price-to-sales / earnings, 20 versions): 36.6-55.9% from 2011 against 58.2%;
- a pullback buy for stretched picks (13 versions): 44.2-51.0%; weighting tilts from the trade table (12 versions):
  51.8-53.0%, in-sample and t 0.0-0.6;
- selling on a falling resistance line with 3-5 touches (22 versions): 42.0-52.8%, the 4-touch ones break even;
- a broken rounded top, as a buy filter, a sell, or both (34 versions): 31.9-52.3%.

## Rule 19's 30% cap (default since Nov 7, 2026)

The candle re-entry rule (rule 19) was replayed abroad with the strict engine (UK, Germany, France, Canada, Australia
and Hong Kong, 2005-2026, today's index members, the local index in place of SPY, the US-only rules off). It cost
points in all six markets, mostly in 2008: the pattern fired 30-50% into the crash and bought back in before more
selling (Germany 2008 -48.5% with it vs -13.6% without, the worst drop -61% vs -40%). Nine stricter versions were run
in the US and in all six markets: a deeper fall (15% / 20%), a cap on the fall (25% / 30%), a confirming next close,
SPY's 50-day average down at most 2% / 4% over 10 sessions, and a 1-week hold.

| Version | US from 2000 | 2010 | 2016 | 2020 | Abroad, vs rule 19 as it was (6-market average) |
|---|---|---|---|---|---|
| Rule 19 capped at a 30% fall (adopted) | 54.3% | 58.5% | 77.1% | 114.1% | +0.5 points, ahead in 4, behind in 0 |
| Rule 19 as it was | 54.1% | 58.5% | 77.1% | 114.1% | - |
| Capped at 25% | 53.9% | 58.5% | 77.1% | 114.1% | +1.0, ahead in 4, behind in 1 |
| 50-day average down at most 2% | 54.2% | 58.4% | 77.1% | 114.1% | +0.2, ahead in 4, behind in 2 |
| A confirming next close | 53.1% | 57.0% | 74.9% | 109.8% | +0.7, ahead in 3, behind in 2 |
| 1-week hold | 53.2% | 57.5% | 75.4% | 110.7% | +0.4, ahead in 5, behind in 1 |
| No rule 19 | 52.6% | 56.7% | 74.9% | 109.8% | +1.2, ahead in 6, behind in 0 |

The cap skips Jul 24, 2002 and Mar 24, 2020 in the US (2002 gains 3.7 points; 2020 is unchanged) and keeps every
2008 and 2022 signal. Worst drop -26% either way; t-stat 0.55 against the uncapped rule. Abroad the capped rule is
still about 0.7 points a year worse than no rule 19, so it stays on probation. Wall Street tests (daily curve):
54.2% a year (34.0% after tax) vs 54.0%, Sharpe 1.57, Calmar 2.09 vs 2.08, worst 3 years +17.7% a year vs +16.6%.

## The per-stock cap raised to 50% (default since Nov 7, 2026)

After 2006 was traced to heavy single-stock weights in short-lived themes, the per-stock cap of the weighting rules
(mtl/volweight.CAP, 40% since Nov 2, 2026) was tested at 25, 30, 35, 38 and 50% and with no cap.

| Cap | 2000 | 2010 | 2016 | 2020 | Worst drop | Sharpe | After tax | 2006 |
|---|---|---|---|---|---|---|---|---|
| None | 54.9% | 59.6% | 79.4% | 116.9% | -25% | 1.60 | 34.2% | -14.4% |
| 50% (adopted) | 54.9% | 59.4% | 79.0% | 116.7% | -25% | 1.60 | 34.2% | -14.1% |
| 40% (before) | 54.3% | 58.5% | 77.1% | 114.1% | -26% | 1.59 | 33.8% | -15.1% |
| 38% | 54.0% | 58.1% | 76.5% | 113.1% | -26% | 1.59 | 33.6% | -15.4% |
| 35% | 53.5% | 57.4% | 75.6% | 111.7% | -26% | 1.58 | 33.3% | -16.1% |
| 30% | 52.4% | 56.2% | 73.9% | 109.2% | -27% | 1.56 | 32.7% | -17.5% |
| 25% | 51.4% | 55.4% | 72.1% | 106.3% | -29% | 1.54 | 32.1% | -19.6% |

Lower caps moved money to the weaker 4th and 5th picks and made 2006 worse, not better. With no cap one stock reached
62% of the account (Apr 2021); 50% keeps nearly all of the gain with no stock above half. The 50% cap is ahead in 16
years and behind in 10 (t-stat 1.7), most of the gain in 2025 (+10.6 points) and 2021 (+5.0); 2013 is the biggest
cost (-3.0). Wall Street tests (daily curve): 54.7% a year (34.3% after tax) vs 54.2%, Sharpe 1.58 vs 1.57, Calmar
2.17 vs 2.09, worst drop -25.2% vs -26.0%; Monte Carlo typical 51.9% over 20 years, beats the 40% cap 77 / 87 / 94%
(5 / 10 / 20 years). On probation.

## Market fitness: when stock picking works, and which way (information only, since Nov 8, 2026)

The plan's edge depends on a market that keeps producing good runners. Across 10 pools (the S&P 500 on its real member
lists; the Nasdaq-100, the Dow and the Russell 2000 on today's lists; the UK, Germany, France, Canada, Australia and Hong
Kong on today's index members) the readings that matter were:
- **runner quality:** of the stocks that doubled over a year, how many gave back half the gain within the next 6 months
  (S&P 500 about 13-16%, Russell 2000 31-33%, the foreign markets 4-22%);
- **which approach has worked there:** the full plan's own record against a simple top-5 pick on a 12-month look-back
  (kept while in the top 10, out to cash under the index's 10-month average) and the index.
Runner counts alone (doublers) misled: US droughts are temporary and come just before the plan's best years.

Walk-forward 2012-2026, reviewed each January from the previous 7 years, a change needing two reviews in a row
(mtl/market_fit.py): give-back above 25% -> the index; otherwise the full plan if it beat the 12-month pick over the 7
years, else the 12-month pick.

| Pool | Selector | Always the full plan | Always the 12-month pick | Index |
|---|---|---|---|---|
| S&P 500 (real lists) | 67.0% | 67.0% | 10.5% | 14.7% |
| Nasdaq-100 | 89.3% | 89.3% | 41.0% | 19.6% |
| Dow 30 | 15.0% | 14.1% | 15.0% | 12.3% |
| Russell 2000 | 10.4% | 4.8% | 8.3% | 10.4% |
| UK | 14.9% | 6.1% | 15.1% | 8.0% |
| Germany | 15.3% | 8.0% | 15.4% | 9.7% |
| France | 9.5% | -2.0% | 9.5% | 9.4% |
| Canada | 15.9% | 9.8% | 20.8% | 10.4% |
| Australia | 16.2% | 8.8% | 16.2% | 9.3% |
| Hong Kong | 18.9% | 14.6% | 17.0% | 4.4% |
| Average (worst drop) | 27.2% (-24%) | 22.0% (-39%) | 16.9% (-29%) | 10.8% (-28%) |

Earlier shapes did worse: 3+ doublers plus good quality 21.0% (the US fell to the 12-month pick in 2012-15 and
2018-23: 30.9%); a t-stat test on the pick's edge 14.0%; quality alone 22.6% (the foreign markets went to the full plan);
quality plus pool size 21.9% (the Nasdaq-100 went to the pick). A grid of 24 doubler cut-offs, windows and gates found
no setting better everywhere. Reviews every 6 / 3 / 1 months averaged 26.1 / 25.6 / 25.6-26.1% with 14-54 switches
against 5 for yearly. The foreign, Dow, Nasdaq-100 and Russell pools use today's member lists (survivorship), so their
levels are flattered. For the live S&P 500 plan the review is information only (data/market_fitness.json, rebuilt by
the track-record refresh; the January run is the review): it raises an alarm if two reviews in a row point away from
the full plan and never changes the plan. At the 2026 review: give-back 13%, a typical 5 doublers, the full plan
+99.7% a year over 2019-2025 against +12.9% for the 12-month pick: healthy.

### Update (Nov 8, 2026): the review now reads the doublers alone

On the owner's request the review no longer looks at past returns. The rule (mtl/market_fit.py): give-back above 25%
-> the index; otherwise 2 or more good doublers a month over the 7 years (doublers that kept at least half the gain over
the next 6 months) -> the full plan, fewer -> the simple 12-month pick. Good doublers separated the markets cleanly:
the S&P 500 read 2.9-8.2 a month at nearly every review (1.8 once, at the 2021 review, back to 5.1 a year later), the
Nasdaq-100 1.8-3.2, Hong Kong 1.6-5.4, the thin markets 0.1-1.7, the Russell 2000 6-25 but with give-back of 30-36%.

Walk-forward 2012-2026 on 13 pools (the 10 above plus Spain, Italy and Sweden from 2016):

| | S&P 500 | Nasdaq-100 | Russell | UK | Germany | France | Canada | Australia | Hong Kong | Spain | Italy | Sweden | Average |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Doublers and quality (cut-off 2) | 67.0% | 87.8% | 10.4% | 15.1% | 15.3% | 9.5% | 20.8% | 16.2% | 18.6% | 11.6% | 19.2% | 13.0% | 24.6% |
| The track-record version | 67.0% | 89.3% | 10.4% | 14.9% | 15.3% | 9.5% | 15.9% | 16.2% | 18.9% | 6.1% | 19.2% | 13.0% | 23.9% |
| Index | 14.7% | 19.6% | 10.4% | 8.0% | 9.7% | 9.4% | 10.4% | 9.3% | 4.4% | 10.1% | 13.3% | 11.9% | 11.0% |

(The Dow is 15.0% for both selectors and 12.3% for its index.) Ahead of the index in 12 of 13 pools; cut-offs of 1.5-2.5
gave nearly the same (24.6 / 24.6 / 22.8%). The track-record version was fooled in Spain: the plan's 2008 exits made
its 2005-2011 record look good, and it ran the full plan in 2012-2018 while the 12-month pick did better. The cut-off
was set after seeing the readings, and Spain, Italy and Sweden were seen before this version, so this is not a fresh
out-of-sample test.

New markets (Nov 8, 2026; today's members; dividends estimated for the price indexes): Spain (IBEX 35, 35 stocks) full
plan 9.4% a year from 2005, simple 12-month pick 10.5%, all members equal weight 11.4%, index 7.7%; Italy (FTSE MIB, 40)
9.3% / 18.5% (worst drop -18%) / 9.6% / 7.0%; Sweden (OMX Stockholm 30, from 2010) 3.8% / 14.0% / 16.6% / 11.0%. All three
are thin markets (typically 0 doublers); only Italy's pick clearly beat holding all members.

## Crash-rebound ranking (rule 21, default since Nov 9, 2026)

About 650 S&P 500 stocks doubled within a year in 2001-2025 (members as of each date, $5+). Most started as
beaten-down, volatile, low-priced stocks right after a crash: 9.2% of members doubled over the next 12 months when SPY
was 30%+ under its 1-year high, 0.9% when it was within 5% of it; volatility, beta, a recent big one-day gain, a deep
fall from the high and a low share price were the strongest traits, while the 6-month change (the plan's ranking) was
weak. The plan held 80% of the doublers that started as 6-month leaders but only 20% of the crash rebounders. The rule
(mtl/crashrank.py): within 126 sessions of SPY closing 30%+ under its 1-year high, while SPY is above its 50-day
average, the 10 stocks with the best rebound score (the average of their percentiles for high 3-month volatility, depth
under their own 1-year high and low share price) go to the front of the ranking and count as qualified; the rest keep
the plan's order and every other rule works as before.

| Version (strict test, real member lists) | 2000 | 2010 | 2016 | 2020 | Worst drop | Sharpe | After tax |
|---|---|---|---|---|---|---|---|
| 30% crash, SPY above its 50-day average (adopted) | 60.4% | 61.9% | 82.0% | 122.5% | -25% | 1.59 | 37.7% |
| 20% crash, SPY above its 50-day average | 60.7% | 60.3% | 80.4% | 119.4% | -25% | 1.59 | 37.9% |
| 20% crash, at most 2 rebound picks | 59.4% | 59.6% | 79.3% | 117.4% | -25% | 1.64 | 36.9% |
| 20% crash, no wait for SPY to turn up | 58.9% | 60.0% | 80.0% | 118.6% | -35% | 1.53 | 36.8% |
| Before (v12) | 54.9% | 59.4% | 79.0% | 116.7% | -25% | 1.60 | 34.2% |

The adopted version changes 6 years: 2009 +93.9 points, 2020 +53.9, 2003 +35.8, 2001 +27.0, 2010 +10.7 and 2002
-12.6 (t-stat 1.5). It was on about 8% of the sessions (late 2001 to 2003, the 2009 rebound, spring-summer 2020).
Without the turn-up check it bought into falling bear markets (2002, 2022) and the worst drop reached -35% to -45%; the
20% versions also fired in 2022 and lost 45 points there. An early run of these tests was wrong: the new code reused a
variable name another rule (the market-filter exit) reads, so a version that never switched on still differed; with the
names fixed, never-on versions match the plan exactly.

Abroad (UK, Germany, France, Canada, Australia, Hong Kong, Spain, Italy, Sweden; 2005-2026; today's members; the local
index for SPY; the rule never acts in Spain, Italy or Sweden, which have too few stocks to rank): on the 6-month plan
every version raised the average return (to 10.1-11.2% a year from 9.8%) but deepened the average worst drop by
0.3-1.7 points, Germany's 2008-09 false bottoms the worst case (-50% to -65%). On the 12-month plan with the times
doubled (SPY above its 100-day average, a 252-session window, settings(252)) the 30% version made 13.4% a year vs
12.6%, better in 5 markets and worse in 1 (Hong Kong), worst drop -38.7% vs -38.8% (Germany 10.6% vs 10.2%).

Wall Street tests (daily curve): 60.3% a year (37.8% after tax) vs 54.7%, Sharpe 1.58 either way, Sortino 2.57 vs
2.50, Calmar 2.39 vs 2.17, worst drop -25.2% either way, worst 3 years +19.0% a year vs +17.6%, but 22 drops of 15%+
vs 15 and an alpha t-stat of 5.9 vs 7.0; Monte Carlo typical 57.4% over 20 years, beats v12 75 / 87 / 95% (5 / 10 /
20 years). Most of the gain is in three episodes (2003, 2009, 2020): on probation.

## The foreign plan without the lower-high exit (rule 5 dropped abroad, Nov 9, 2026; the US keeps it)

Research only: the foreign plan is not traded. Strict engine, 9 markets (UK, Germany, France, Canada, Australia,
Hong Kong, Spain, Italy, Sweden), 2005-2026 (Australia from mid-2007, Sweden from 2010), today's index members, the
local index in place of SPY, gold and bonds in local currency, 0.15% a side.

| Version | 6-month plan, average | better / worse | 12-month plan, average | better / worse | 12-month worst drop (average) |
|---|---|---|---|---|---|
| As it was | 10.64% | – | 13.44% | – | -38.7% |
| Rule 5 dropped | 12.14% | 9 / 0 | 15.04% | 8 / 1 | -39.3% |
| Rule 2 dropped | 9.99% | 3 / 6 | 12.93% | 4 / 5 | -39.6% |
| Both dropped | 11.22% | 5 / 4 | 14.41% | 6 / 3 | -44.7% |

On the 12-month plan Germany went from 10.6% to 14.0% a year (worst drop -42% to -34%), the UK 13.6% to 14.3%,
France 10.7% to 13.2%; Canada slipped 24.0% to 23.1%. Rule 5's two weeks in a haven mostly sold dips that came back in
these thinner markets. In the US the same change cut 60.4% to 52.0% a year from 2000 and deepened the worst drop from
-25% to -38% (better in 5 years, worse in 11), so the US plan keeps rule 5.

Tried at the same time and not adopted (US from 2000 unless noted):
- Rule 2 loosened (any lower high; no slow-fall condition; both): US 55.6 / 57.7 / 50.8% vs 60.4%; abroad worse in 7-9
  of 9 markets on both plans.
- A big-drop pause (to the haven for 1-2 weeks after a one-day fall of 2.5-3 standard deviations, a 5-day one, or 7%
  in a week): US 49.7-57.5%; it overrode the haven the plan already held in Feb-Mar 2020 (the plan made +11.6% while
  SPY fell 19%).
- Longer haven timers (price break 20 sessions, rule 5 four weeks, all x2 / x3): US 47.2-58.6%.
- Back into stocks only after the index makes a higher high and a higher low (2-week or 1-month halves, with or
  without a 3-month cap): US 44.8-49.1%; it re-bought 10-15% higher, after the picks had already turned.
- An index-trend exit (under the 10-month average): US 33.2-39.6%; abroad 5.8-8.3% (6-month plan) and 8.1-11.1%
  (12-month plan).

Later the same day, each remaining exit was switched off on the foreign plan without rule 5 (12-month plan, 9 markets):
rule 3 (the whipsaw switch) off made 16.07% a year vs 15.04%, better in 6 of 9 markets (Germany 14.0% to 16.8%,
Australia 18.6% to 21.2%, Spain 9.2% to 11.9%, Canada 23.1% to 25.0% with its worst drop -39% to -28%; France worse,
13.2% to 12.4%, its 2022 -17% to -34%), average worst drop -39.5% vs -39.3%; on the 6-month plan 12.95% vs 12.14%
(7 of 9). After a run of losing sales it kept the whole account in gold or bonds through recoveries (the UK's 2023:
+12% without it vs +5% with it). So rule 3 is dropped from the foreign plan as well; the US plan keeps it. Rule 2 (the
downtrend exit) stays abroad: without it the 12-month plan's average worst drop went to -47% (Australia -60%, Spain
-65%) for 14.9% a year. Rules 8, 10 and 19 were about neutral abroad (16.2-16.6% on 7 markets vs 16.1%) and stay.

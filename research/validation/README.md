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
sales), the plan now holds 100% of whichever of TLT, GLD and SPY is up most over 3 months (skipping weekly
downtrends) instead of 50% of it next to the Boost list (`WHIP_SHARE` in `mtl/rotation.py`; engine `NBup` = whole
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

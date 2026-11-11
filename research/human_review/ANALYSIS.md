# What the review picks did, and whether they can be made into rules (Nov 11, 2026)

Research only; the live plan is unchanged. Figures marked "engine" are the strict test (S&P members as of each date,
0.15% a trade, from 2000). Figures marked "quick model" replace the plan's daily return with the haven's while a call
is on (same timing and cost); it reproduces the engine within about 1 point a year (63.7% against the engine's 63.5%
for the picks on daily values), and is what the searches and random-timing tests ran on. In the quick model the plan
is 60.5% and the picks 64.1%.

## 1. What each call earned (episodes.json)

- 38 times out of the plan, 1,262 days (26% of marked days). The haven beat the plan in 26 of 38; SPY fell in 32.
- By haven, summed advantage over the plan: TLT +111 log points (21 calls), DBMF +14, gold +9, cash -33 (7 calls,
  5 of them losers; the March 2026 cash call alone cost 1.7 points a year).
- Engine: picks without the cash calls 65.9% (worst drop -25%, Sharpe 1.79); only the TLT calls 66.0% (better in 13
  years, worse in 4, t 1.43); all picks 63.7%; plan 60.4%.
- The edge is concentrated: without the five best calls (May 2001, Nov 2007, Jan 2001, May 2010, May 2006, all TLT)
  the picks make 59.2%, below the plan.
- Calls made within 10% of SPY's 1-year high carry the edge (64.4% on their own); calls made deep in a bear market
  add nothing (60.2%).

## 2. What the markets were doing at the calls

- Leaving (34 spells against 737 ordinary weeks): SPY's daily RSI near 46 (59 on ordinary weeks), SPY down about 1%
  over the last week, in the bottom quarter of its short swing channel, about 3% under its last swing high, at its
  50-day average, with a haven ahead of SPY over the past month. The calls come just after a pullback has started.
- Coming back (31 against 261 weeks still out): SPY back in the upper part of its short channel, up over the last
  week, a new up leg under way.
- Haven: a simple picker (TLT when above its 50-day average, else the strongest haven over a month, else cash)
  matches the chosen haven in 24 of 39 calls, but at the same dates it makes 56.6%; the picks' own haven choices are
  worth about 7 points a year over always using TLT (57.4%).

## 3. Is the timing better than chance, and how exact must it be?

- Random timing: the same spells and havens placed on random dates (1,500 draws) make 46.6% (40.5-52.7%, best 57.0%).
  None beat the plan; none came near the picks.
- Shifting every call: 5 days later 57.1%, 10 days later 51.4%; 2 days earlier 67.5%, 5 days earlier 74.5%.
  A week's delay turns the edge into a loss.

## 4. Rules

- 425,355 rules of the form "out when 1-3 conditions hold, back when 1-2 hold", built from the readings above plus
  bear-market, plan-state and bond-trend conditions.
  - Fitted to match the picks: the best match (71-72% F1 on out-days) makes 33-35%; engine 36.4%. Matching the picks
    more closely goes with a lower return (correlation -0.11 and -0.34 in the two searches).
  - Fitted on half the years (even/odd, early/late), scored on the other half: 0 of the top 20 beat the plan on the
    unseen half in every one of the eight tests, whether chosen by match or by return (one exception: 5 of 20 in one
    return test).
  - Over all years 186 rules (0.04%) beat the plan in the quick model, by a median 0.4 points.
  - The best of them: out when SPY's 50-day average is under its 200-day, gold is up over a month and SPY closes
    under its swing channel; back when SPY is in the upper half of its short channel or above its last swing high.
    Engine: 63.2% (worst drop -26%, Sharpe 1.69, t 1.38, better in 8 years, worse in 4: 2001 +21 points, 2009 +79,
    2020 +63; 2008 -14, 2010 -12, 2015 -9). It is the best of 425,355 tried, so most of that margin is selection;
    watch list at most.
- A weighted model over all 109 readings, scored only on years it was not fitted on:
  - it recognises the out-days well (AUC 0.84): they are describable;
  - it cannot tell when a call is about to be made (AUC 0.54);
  - it cannot tell when the plan is about to lose to TLT (AUC 0.49) or to fall 5% (AUC 0.52): chance;
  - used as an overlay it makes 29-58%, always under the plan.

## 5. Reading

The picks' edge is real in the record but comes from exact timing and haven choice that these readings do not carry:
the same conditions occur several times as often as the calls, and the plan usually keeps rising through them.
What does carry over as guidance: leave for TLT rather than cash; act early in a pullback near the highs, not deep in
a bear market; a call a week late is worse than no call.

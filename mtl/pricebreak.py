"""The price-break haven rule of Boost + rotation (the default plan): a break of SPY's long average sends the account to the haven.

On the day SPY closes under its PB_SLOW (100) day average for the first time (it closed on or above it the day
before) while both that average and its PB_FAST (7) day average are lower than PB_SLOPE (5) sessions earlier, the
plan holds the haven pick instead of the Boost list: the better of TLT / GLD over 3 months if it is up, else managed
futures (DBMF), the same pick as no_bills. It holds from that decision day through PB_HOLD (10) sessions later (a new
break inside the stretch extends it); on any day the plan already holds a haven it changes nothing. Decided at the
close, traded at the next close, like the rest of the plan.

Backtest (Oct 24, 2026, S&P 500 members at each date, 0.05% per side): 45.8% a year from 2000 vs 44.3% without it,
52.5% vs 51.8% from 2010, 66.4% vs 65.7% from 2016, 90.5% vs 89.3% from 2020; worst drop -28% vs -32%, Sortino
2.17 vs 2.10. It changes the holding in 9 of 27 years (99 haven days): ahead in 2002 (+12.2 points), 2003 (+16.4),
2007, 2011 (+9.0) and 2022 (+5.6), behind in 2001, 2008, 2012 and 2015 (-0.9). Ahead in all three eras (2000s +2.6
points, 2010s +0.4, 2020s +1.2); monthly t-stat 1.5; a 6-month block bootstrap had the gain at zero or worse in 6% of
samples; holding 5 to 20 sessions gave 44.9% to 46.5%; the same signals moved 2 to 24 years in time (12 placebos)
never matched the gain (average -1.1 points a year). Other settings: a 5-day instead of 7-day average gave the same
(45.6%), 150 days instead of 100 gave 45.5%, 50 days 44.2%, 35 days 43.8%; applying it on every day the condition
holds instead of the break day cost 6 to 17 points a year. Abroad (local-currency havens) it was mixed: ahead in
Hong Kong, India, Germany and Canada, flat in the UK, behind in Korea, Taiwan, Switzerland, Japan and Brazil.
It was designed after looking at the same data, from one rule family tried many ways; treat it as on probation."""
from mtl.rotation import ROT_ASSETS, bills_pick, BILLS_LOOK

PB_SLOW = 100        # sessions in the long average
PB_FAST = 7          # sessions in the short average
PB_SLOPE = 5         # both averages must be lower than this many sessions earlier
PB_HOLD = 10         # sessions after the break day the haven is held (the break day included: 11 decision days)


def _avg(closes, k, n):
    win = closes[k - n + 1:k + 1] if k >= n - 1 else []
    return sum(win) / n if len(win) == n and None not in win else None


def reading(spy_closes, k):
    """At index k of the calendar-aligned SPY closes: dict(close, slow, fast, below, down, brk) or None."""
    need = PB_SLOW + PB_SLOPE
    if k < need or spy_closes[k] is None or spy_closes[k - 1] is None:
        return None
    s, s1, s5 = _avg(spy_closes, k, PB_SLOW), _avg(spy_closes, k - 1, PB_SLOW), _avg(spy_closes, k - PB_SLOPE, PB_SLOW)
    f, f5 = _avg(spy_closes, k, PB_FAST), _avg(spy_closes, k - PB_SLOPE, PB_FAST)
    if None in (s, s1, s5, f, f5):
        return None
    below = spy_closes[k] < s
    down = s < s5 and f < f5
    brk = bool(below and spy_closes[k - 1] >= s1 and down)
    return dict(close=spy_closes[k], slow=s, fast=f, below=bool(below), down=bool(down), brk=brk)


def break_days(spy_px, calendar, start):
    """The decision days from `start` on whose close is a break (see the module text); spy_px {date: close}."""
    closes = [spy_px.get(d) for d in calendar]
    return {d for k, d in enumerate(calendar) if d >= start and (r := reading(closes, k)) and r['brk']}


def hold_days(breaks, calendar, start):
    """The decision days the haven is held: each break day and the PB_HOLD sessions after it."""
    kidx = {d: i for i, d in enumerate(calendar)}
    out = set()
    for d in breaks:
        for k in range(kidx[d], min(len(calendar), kidx[d] + PB_HOLD + 1)):
            if calendar[k] >= start:
                out.add(calendar[k])
    return out


def apply_pricebreak(modes, why, half, days, closes, calendar, look=BILLS_LOOK, assets=ROT_ASSETS):
    """New (modes, why, half, held): on each of `days` where the plan would hold the Boost list, the haven pick
    (bills_pick: the better of TLT / GLD over `look` sessions if up, else DBMF, else cash) instead, with the switch reason
    'pricebreak' (into the haven) and 'pricebreak-end' (back to what the plan holds); held = the days the rule changed the
    holding. closes: {asset: {date: close}} (filled)."""
    kidx = {d: i for i, d in enumerate(calendar)}
    m, w, h = dict(modes), dict(why), dict(half or {})
    held, prev = set(), None
    for d in calendar:
        if d not in modes:
            continue
        if d in days and m.get(d, 'boost') == 'boost' and kidx[d] >= look:
            m[d] = bills_pick(closes, calendar, kidx[d], look, assets)
            h.pop(d, None)
            held.add(d)
            if prev != 'pricebreak':
                w[d] = 'pricebreak'
            prev = 'pricebreak'
        else:
            if prev == 'pricebreak' and m.get(d, 'boost') != m.get(calendar[kidx[d] - 1], 'boost') and d not in w:
                w[d] = 'pricebreak-end'
            prev = 'plan'
    return m, w, h, held


def pricebreak_state(spy_px, calendar, k, held, n=6):
    """For the scanner: today's reading, whether the rule is holding the haven today (active) and the last n stretches it
    did ([first, last] decision days)."""
    closes = [spy_px.get(d) for d in calendar]
    r = reading(closes, k) or dict(brk=False)
    runs = []
    for d in sorted(held):
        i = calendar.index(d)
        if runs and calendar.index(runs[-1][1]) == i - 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    return dict({a: (round(b, 4) if isinstance(b, float) else b) for a, b in r.items()}, active=calendar[k] in held,
                log=runs[::-1][:n], n=len(runs), slow_n=PB_SLOW, fast_n=PB_FAST, slope=PB_SLOPE, hold=PB_HOLD)

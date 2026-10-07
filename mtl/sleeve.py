"""The "best-of" sleeve and the levered plan that pairs it with the top-5 rule.

Sleeve: every week's last session, put the whole sleeve in whichever of
GLD / TLT / IEF / UUP / DBC / BIL had the best 6-month (126-session) return;
BIL (T-bills) wins when nothing beats cash.

Plan: `w_main` of the account in the top-5 rule and `w_sleeve` in the sleeve,
reset to those weights every week's last session; anything above 100% of the
account is borrowed at `rate` a year. 60/40 x1.3 = w_main 0.78, w_sleeve 0.52.

Pure and network-free; prices are {asset: {date: dividend-adjusted close}}.
"""
from mtl.momentum import last_sessions_of_weeks

ASSETS = ['GLD', 'TLT', 'IEF', 'UUP', 'DBC', 'BIL']
NAMES = {'GLD': 'Gold', 'TLT': 'Long Treasuries (20y+)', 'IEF': 'Treasuries (7-10y)',
         'UUP': 'US dollar', 'DBC': 'Commodities', 'BIL': 'T-bills (cash)'}


def filled(prices, calendar):
    """Carry each asset's last close over sessions it has none."""
    out = {}
    for t, s in prices.items():
        last, f = None, {}
        for d in calendar:
            last = s.get(d) or last
            f[d] = last
        out[t] = f
    return out


def six_month(f, calendar, k, look=126, assets=None):
    """{asset: return over the last `look` sessions to calendar[k]} (None if unknown)."""
    out = {}
    for t in assets or ASSETS:
        a, b = (f.get(t) or {}).get(calendar[max(0, k - look)]), (f.get(t) or {}).get(calendar[k])
        out[t] = b / a - 1 if a and b and k >= look else None
    return out


def best_of(f, calendar, k, look=126, assets=None):
    r = six_month(f, calendar, k, look, assets)
    return max((t for t in r if r[t] is not None), key=lambda t: r[t], default='BIL')


def sleeve_curve(prices, calendar, start, look=126, assets=None):
    """([[date, value]], [[rebalance date, asset]]) - the sleeve from `start`, value 1.0."""
    f = filled(prices, calendar)
    rebal = set(last_sessions_of_weeks(calendar))
    held, val, curve, picks = None, 1.0, [], []
    for k, d in enumerate(calendar):
        if d < start:
            continue
        if held is None:
            held = best_of(f, calendar, k, look, assets)
            picks.append([d, held])
        elif k:
            p = calendar[k - 1]
            val *= f[held][d] / f[held][p]
        curve.append([d, val])
        if d in rebal:
            nxt = best_of(f, calendar, k, look, assets)
            if nxt != held:
                picks.append([d, nxt])
            held = nxt
    return curve, picks


def plan_curve(main, sleeve, w_main, w_sleeve, calendar, rate=0.06):
    """Weekly-rebalanced w_main in `main` + w_sleeve in `sleeve` (both [[date, value]]);
    anything above 100% of the account is borrowed at `rate` a year, charged daily."""
    rebal = set(last_sessions_of_weeks(calendar))
    other = dict(sleeve)
    borrow = max(0.0, w_main + w_sleeve - 1)
    nav, a, b, debt = 1.0, w_main, w_sleeve, borrow
    out, prev = [], None
    for d, v in main:
        if d not in other:
            continue
        if prev:
            a *= v / prev[0]
            b *= other[d] / prev[1]
            debt *= 1 + rate / 252
            nav = a + b - debt
            if nav <= 0:
                out.append([d, 0.0])
                break
        out.append([d, nav])
        prev = (v, other[d])
        if d in rebal:
            a, b, debt = nav * w_main, nav * w_sleeve, nav * borrow
    return out


def plan_curve_dynamic(main, sleeve, calendar, split_at):
    """Top-5 / sleeve mix whose stock share is decided at each week's last
    session by split_at(date) and applied at the next session's close (Monday),
    like the live page's trades. Returns [[date, value]] from 1.0."""
    week_ends = last_sessions_of_weeks(calendar)
    idx = {d: i for i, d in enumerate(calendar)}
    reset = {calendar[idx[f] + 1]: split_at(f) for f in week_ends if idx[f] + 1 < len(calendar)}
    other = dict(sleeve)
    out, prev, a, b = [], None, None, None
    for d, v in main:
        if d not in other:
            continue
        if prev is None:
            a = split_at(d)
            b = 1 - a
        else:
            a *= v / prev[0]
            b *= other[d] / prev[1]
        nav = a + b
        out.append([d, nav])
        if d in reset:
            a, b = nav * reset[d], nav * (1 - reset[d])
        prev = (v, other[d])
    return out


def plan_curve_mix(parts, calendar, weights_at):
    """Several holdings mixed by weights decided at each week's last session and
    applied at the next session's close (Monday), like plan_curve_dynamic.
    parts: {name: [[date, value]]} (the first one sets the dates);
    weights_at(friday) -> {name: weight} (weights sum to 1).
    Returns [[date, value]] from 1.0."""
    week_ends = last_sessions_of_weeks(calendar)
    idx = {d: i for i, d in enumerate(calendar)}
    reset = {calendar[idx[f] + 1]: weights_at(f) for f in week_ends if idx[f] + 1 < len(calendar)}
    names = list(parts)
    val = {n: dict(c) for n, c in parts.items()}
    out, prev, held = [], None, None
    for d, _ in parts[names[0]]:
        if any(d not in val[n] for n in names):
            continue
        if prev is None:
            w = weights_at(d)
            held = {n: w.get(n, 0.0) for n in names}
        else:
            held = {n: held[n] * val[n][d] / val[n][prev] for n in names}
        nav = sum(held.values())
        out.append([d, nav])
        if d in reset:
            w = reset[d]
            held = {n: nav * w.get(n, 0.0) for n in names}
        prev = d
    return out


def plan_curve_scheduled(main, f, calendar, decisions, split_at, look=126, assets=None):
    """Top-5 / sleeve mix rebalanced only on the session after each decision date
    (e.g. month-ends): the stock share split_at(decision) and the sleeve asset
    (best 6-month return at the decision close) are both decided at that close
    and traded at the next session's close. main: [[date, value]] of the stock
    rule; f: filled sleeve prices (filled()). Returns [[date, value]] from 1.0."""
    idx = {d: i for i, d in enumerate(calendar)}
    trade = {calendar[idx[x] + 1]: x for x in decisions if x in idx and idx[x] + 1 < len(calendar)}
    out, prev, a, b, held = [], None, 1.0, 0.0, None
    for d, v in main:
        if prev is not None:
            a *= v / prev[1]
            if held:
                p0, p1 = f[held].get(prev[0]), f[held].get(d)
                if p0 and p1:
                    b *= p1 / p0
        nav = a + b
        out.append([d, nav])
        if d in trade:
            dec = trade[d]
            s = split_at(dec)
            held = best_of(f, calendar, idx[dec], look, assets) if s < 1 else None
            a, b = nav * s, nav * (1 - s)
        prev = (d, v)
    return out

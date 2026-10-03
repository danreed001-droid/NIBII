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

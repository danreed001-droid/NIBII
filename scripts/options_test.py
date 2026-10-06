#!/usr/bin/env python3
"""Call-option overlay on the live weekly rule: every 4 weeks a slice of the account
buys a 4-week call on the #1-ranked holding, strike = price + the call's own price
(stock 100, call 4 -> 104 strike), held to expiry. The rest runs the live plan.

No historical option prices are available, so calls are priced with Black-Scholes
on the stock's 63-day realized volatility x 1.15 (options usually price in more than
realized), r = T-bill-ish 2%, plus a 5% bid/ask cost on the premium. Point-in-time
S&P list, 0.15% slippage on the stock part. After tax: 37% on each calendar year's
net gain (losses carried forward) for both the overlay and the plain plan, on the
same 4-week grid. Writes data/options.json.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import improve as I  # noqa: E402
import robustness as R  # noqa: E402
from mtl.sleeve import ASSETS  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'options.json')
IV_MULT, RATE, SPREAD, DAYS = 1.15, 0.02, 0.05, 20


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_call(S, K, T, sig, r=RATE):
    if sig <= 0 or T <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2)


def strike_plus_premium(S, T, sig):
    K = S * 1.05
    for _ in range(60):
        K = S + bs_call(S, K, T, sig)
    return K


def vol(px, cal, k, n=63):
    pts = [px.get(cal[j]) for j in range(k - n, k + 1)]
    if not all(pts):
        return None
    r = [math.log(pts[i + 1] / pts[i]) for i in range(n)]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1)) * math.sqrt(252)


def after_tax(points, rate=0.37):
    """points: [(date, value)] on the period grid; 37% on each year's net gain, carryforward."""
    v, carry, yr, start_yr_val, out = points[0][1], 0.0, points[0][0][:4], points[0][1], [points[0]]
    a = points[0][1]
    for i in range(1, len(points)):
        d, x = points[i]
        g = x / points[i - 1][1]
        a *= g
        if d[:4] != yr:
            net = a - start_yr_val - carry
            if net > 0:
                a -= rate * net
                carry = 0.0
            else:
                carry = -net
            start_yr_val = a
            yr = d[:4]
        out.append((d, a))
    net = a - start_yr_val - carry
    if net > 0:
        a -= rate * net
    out[-1] = (out[-1][0], a)
    return out


def cagr(points):
    yrs = (int(points[-1][0][:4]) - int(points[0][0][:4])) + (int(points[-1][0][5:7]) - int(points[0][0][5:7])) / 12
    return (points[-1][1] / points[0][1]) ** (1 / yrs) - 1


def maxdd(points):
    pk, dd = points[0][1], 0.0
    for _, v in points:
        pk = max(pk, v)
        dd = min(dd, v / pk - 1)
    return dd


def main():
    D = R.load_data()
    P = R.prepare(D)
    I.G['P'] = P
    I.G['LEV'] = set()
    R.G['P'] = P
    cal = P['calendar']
    I.G['months'] = I.month_ends(cal)
    down = R.downtrend_fn(D['bars'])
    px_all = dict(P['prices'])
    px_all.update(P['sleeve_px'])
    kw = I.VARIANTS['ldt2x'][0]
    _, run = I.run_one(('live', kw, False, ()))
    sc = I.schedule(run, cal, P['sleeve_f'], down, R.START)
    pre = R.simulate(sc, px_all, cal, I.SLIP, taxes=False)
    curve = dict((d, v) for d, v in pre['curve'])
    idx = {d: i for i, d in enumerate(cal)}
    # the #1 holding at each trade: the double-weighted one
    trades = [(T, w) for T, w in run['weights'] if T >= R.START and w]
    tops = [(T, max(w, key=lambda t: w[t])) for T, w in trades]
    days = [d for d in cal if d >= R.START]

    def priced(T, top, ivm, tp=None, atm=False):
        k = idx[T]
        if k + DAYS >= len(cal) or top in ASSETS:
            return None
        S, E = P['prices'][top].get(T), P['prices'][top].get(cal[k + DAYS])
        if E is None:
            ks = [d for d in P['prices'][top] if d <= cal[k + DAYS]]
            E = P['prices'][top][max(ks)] if ks else None
        sig = vol(P['prices'][top], cal, k)
        if not (S and E and sig):
            return None
        sig *= ivm
        Tm = DAYS / 252
        K = S if atm else strike_plus_premium(S, Tm, sig)
        prem = bs_call(S, K, Tm, sig) * (1 + SPREAD)
        end, mult = cal[k + DAYS], max(0.0, E - K) / prem
        if tp:   # take profit: sell (after a 5% bid/ask cost) once the call is worth tp x what it cost
            px_t = P['prices'][top]
            for j in range(1, DAYS):
                Sj = px_t.get(cal[k + j])
                if not Sj:
                    continue
                v = bs_call(Sj, K, (DAYS - j) / 252, sig) * (1 - SPREAD)
                if v >= tp * prem:
                    end, mult = cal[k + j], v / prem
                    break
        return dict(d=T, end=end, t=top, S=round(S, 2), K=round(K, 2), premPct=round(prem / S, 4),
                    E=round(E, 2), mult=mult)

    def overlay(events, f):
        """Daily: the plan's value follows its curve; on each event f x total buys calls (taken
        from the plan), paid back into the plan at expiry. Open calls are carried at cost."""
        by_day = {}
        for e in events:
            by_day.setdefault(e['d'], []).append(e)
        plan_v, open_, pts, prev = 1.0, [], [], None
        for d in days:
            if d not in curve:
                continue
            if prev is not None:
                plan_v *= curve[d] / curve[prev]
            for o in [o for o in open_ if o[0] == d]:
                plan_v += o[1] * o[2]
                open_.remove(o)
            for e in by_day.get(d, []):
                amt = f * (plan_v + sum(o[1] for o in open_))
                plan_v -= amt
                open_.append((e['end'], amt, e['mult']))
            pts.append((d, plan_v + sum(o[1] for o in open_)))
            prev = d
        return pts

    res, ev_stats = {}, {}
    for mode, tp, atm in (('roll4', None, False), ('roll4', None, True), ('new1', None, False), ('new1', None, True)):
        for ivm in (1.15, 1.3, 1.5):
            if mode == 'roll4':
                src = tops[::4]
            else:
                src = [(T, t) for i_, (T, t) in enumerate(tops) if i_ == 0 or t != tops[i_ - 1][1]]
            events = [e for e in (priced(T, t, ivm, tp, atm) for T, t in src) if e]
            mode_k = mode + (f'_tp{int(round((tp - 1) * 100))}' if tp else '') + ('_atm' if atm else '')
            hits = [e for e in events if e['mult'] > 0]
            ev_stats[f'{mode_k}_{ivm}'] = dict(n=len(events), hit=round(len(hits) / max(1, len(events)), 3),
                                             avgMult=round(sum(e['mult'] for e in events) / max(1, len(events)), 3),
                                             perYear=round(len(events) / 16.75, 1))
            for f in (0.0, 0.02, 0.05):
                if f == 0.0 and (mode_k, ivm) != ('roll4', 1.15):
                    continue
                pts = overlay(events, f)
                at = after_tax(pts)
                first = [p for p in pts if p[0] <= '2019-12-31']
                second = [p for p in pts if p[0] >= '2019-12-31']
                key = 'plan' if f == 0.0 else f'{mode_k}_{ivm}_{f}'
                res[key] = dict(pre=round(cagr(pts), 4), after=round(cagr(at), 4), dd=round(maxdd(pts), 4),
                                first=round(cagr(first), 4), second=round(cagr(second), 4), final=round(pts[-1][1], 2))
                R.log(f"{key}: {res[key]}")
    R.log(f"events: {json.dumps(ev_stats)}")
    summary = ev_stats
    rows = []
    with open(OUT, 'w') as fh:
        json.dump(dict(results=res, summary=summary, rows=rows), fh, separators=(',', ':'))


if __name__ == '__main__':
    main()

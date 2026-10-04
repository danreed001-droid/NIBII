#!/usr/bin/env python3
"""Options-ONLY accounts (no stock), 2000-2026: which way of using options on the
top-5 signals works best, and how they compare with the current stock setup.

Signals are the dashboard's (S&P 500 + Nasdaq-100 by 6-1 month strength, top 5,
keep while top 10, signal Friday, trade at Monday's close), on the long-history
data of scripts/backtest_long_history.py (today's index lists - survivorship
flatters the early years for every top-5 line alike).

Strategies (90-day calls at delta 0.70 unless named; % = premium per new call):
  entries         buy a call when a stock ENTERS the top 5, sell when the model
                  drops it or 21 days before expiry (the earlier test's best)
  + roll          also buy a fresh call when the old one expires while the stock
                  is still held - so all 5 holdings always have a call on
  deep/long       roll version with delta 0.80, 180-day calls (rolled at 45 days)
  SPY filter      no new calls while SPY is below its 200-day average
  auto filter     half-size new calls while 2+ holdings are in a lower-low
                  downtrend (the dashboard's Auto read)
  guard filter    half-size new calls while SPY is below its close a year ago
  QQQ trend Nx    Nasdaq-100 calls (delta 0.70, 120 days, rolled at 30) sized
                  to N x the account's exposure, only while QQQ is above its
                  200-day average; the rest in cash
  sell puts       cash-secured puts on each top-5 holding: 45-day, delta -0.30,
                  1/5 of the account backing each; re-sold at expiry while held,
                  bought back when the model drops the stock

Pricing: no historical option prices, so Black-Scholes from the stock's 63-day
realized volatility + 10 points (floor 20%; QQQ + 4 points, floor 12%), 4% rate,
2% bid/ask each way. Sold puts get 5- and 0-point cushion checks too (selling gets
paid MORE when the cushion is higher, so a big cushion would flatter it).
Calibration: SPY 1-month at-the-money puts sold monthly vs the real CBOE PutWrite
index (^PUT), to see if the pricing is in the right ballpark. Cash earns 0%.

Usage:
    python scripts/backtest_options_only.py
"""
import math
import os
import sys
from bisect import bisect_right
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import START, load  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.options_sim import bs_call, bs_delta, strike_for_delta  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500  # noqa: E402
from study_big_moves import roll_std, volumes  # noqa: E402

RATE, SPREAD = 0.04, 0.02


def rolling_vol(c, w=63):
    r = np.full(len(c), np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        r[1:] = np.log(c[1:] / c[:-1])
    return roll_std(r, w) * math.sqrt(252)


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def put(s, k, t, v):
    return bs_call(s, k, t, v, RATE) - s + k * math.exp(-RATE * t)


def main():
    D = load()
    bars, bench = D['bars'], D['bench']
    sp, added = load_sp500(), load_added()
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    cal = [b[0] for b in bench['SPY']]
    n = len(cal)
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t not in sp or added.get(t, '0000') <= d)

    print("running the top-5 rule since 2000...", flush=True)
    r = run_momentum(prices, cal, START, look=126, skip=21, top_n=5, eligible=eligible, exec_next='close')
    idx = {d: i for i, d in enumerate(cal)}
    i0 = idx[r['picks'][0][0]]
    held_at = [()] * n
    pk = {idx[d]: tuple(h) for d, h in r['picks']}
    cur = ()
    for i in range(n):
        cur = pk.get(i, cur)
        held_at[i] = cur
    trade_days = set(pk)

    C, V, V20 = {}, {}, {}

    def series(t, src=None):
        if t not in C:
            p = src or prices[t]
            last, s = np.nan, np.empty(n)
            for i, d in enumerate(cal):
                v = p.get(d)
                last = v if v else last
                s[i] = last
            C[t], V[t], V20[t] = s, rolling_vol(s), rolling_vol(s, 20)
        return C[t]

    for t in {x for h in held_at for x in h}:
        series(t)
    series('QQQ', {b[0]: b[4] for b in bench['QQQ']})
    spy = series('SPY')
    spy200 = np.array([spy[max(0, i - 199):i + 1].mean() for i in range(n)])
    q = C['QQQ']
    q200 = np.array([q[max(0, i - 199):i + 1].mean() for i in range(n)])

    # panic signals (scripts/study_big_moves.py): Friday close with VIX 35+ ; stocks down 20%+ over the
    # last month, most beaten-down first, bought at the next session's close
    vix_px = volumes(sorted(bars)).get('^VIX', {})
    vix = np.array([vix_px.get(d, np.nan) for d in cal])
    vmax20 = np.array([np.nanmax(vix[max(0, i - 19):i + 1]) for i in range(n)])
    wd = [date.fromisoformat(d).weekday() for d in cal]

    def panic_signals(vix_min=35, drop=-0.20, fading=False, per_week=5):
        out = {}
        for i in range(max(i0, 300), n - 1):
            if wd[i + 1] > wd[i] or not vix[i] >= vix_min:
                continue
            if fading and not vix[i] <= 0.8 * vmax20[i]:
                continue
            cands = []
            for t, bs in bars.items():
                if not eligible(t, cal[i]):
                    continue
                c = series(t)
                if c[i] > 0 and c[i - 21] > 0 and c[i - 260] > 0 and c[i] / c[i - 21] - 1 <= drop:
                    cands.append((c[i] / c[i - 21] - 1, t))
            if cands:
                out[i + 1] = [t for _, t in sorted(cands)[:per_week]]
        return out

    # auto read: 2+ holdings in a daily lower-low downtrend at the previous close
    dates = {t: [b[0] for b in bs] for t, bs in bars.items()}
    dcache = {}

    def downs(i):
        f = cal[i - 1]
        if f not in dcache:
            k = 0
            for t in held_at[i - 1]:
                j = bisect_right(dates[t], f)
                k += structure_signal([tuple(b) for b in bars[t][max(0, j - 320):j]], n=3, lookback=2)['state'] == 'downtrend'
            dcache[f] = k
        return dcache[f]

    def iv(t, i, bump, fast=False):
        """fast: price off the higher of 20- and 63-day volatility (a panic shows up in 20-day first,
        and real option prices jump at once)."""
        v = max(V[t][i], V20[t][i]) if fast and not np.isnan(V20[t][i]) else V[t][i]
        if t == 'QQQ':
            return max(0.12, (0.20 if np.isnan(v) else v) + 0.04)
        return max(0.20, (0.40 if np.isnan(v) else v) + bump)

    def expiry(d, tenor):
        return date.fromordinal(date.fromisoformat(d).toordinal() + tenor).isoformat()

    def calls_on_top5(risk=0.10, delta=0.70, tenor=90, roll_at=21, roll=False, filt=None, bump=0.10,
                      top5=True, panic=None, p_risk=0.05, p_delta=0.50, p_tenor=90, p_roll=21, p_max=10, p_bump=0.10):
        """top5=False: no top-5 calls. panic: {entry index: [tickers]} - calls bought on those, held until
        p_roll days before expiry, p_risk of the account each, at most p_max open."""
        cash, pos, curve = 100.0, [], []
        for i in range(i0, n):
            d = cal[i]
            held = held_at[i] if top5 else ()
            keep, reopen = [], []
            for p in pos:
                s = C[p['t']][i]
                left = days(d, p['exp'])
                mid = bs_call(s, p['k'], max(0, left) / 365, iv(p['t'], i, p_bump if p.get('panic') else bump, p.get('panic')), RATE)
                if p.get('panic'):
                    if left <= p_roll:
                        cash += p['n'] * mid * (1 - SPREAD)
                    else:
                        p['mid'] = mid
                        keep.append(p)
                    continue
                if p['t'] not in held or left <= roll_at:
                    cash += p['n'] * mid * (1 - SPREAD)
                    if p['t'] in held and roll:
                        reopen.append(p['t'])
                else:
                    p['mid'] = mid
                    keep.append(p)
            pos = keep
            acct = cash + sum(p['n'] * p['mid'] for p in pos)
            have = {p['t'] for p in pos if not p.get('panic')}
            if panic and i in panic:
                npan = sum(1 for p in pos if p.get('panic'))
                for t in panic[i]:
                    if npan >= p_max or any(p['t'] == t and p.get('panic') for p in pos):
                        continue
                    s, v = C[t][i], iv(t, i, p_bump, True)
                    k = strike_for_delta(s, p_tenor / 365, v, RATE, p_delta)
                    mid = bs_call(s, k, p_tenor / 365, v, RATE)
                    spend = min(cash, acct * p_risk)
                    if spend <= acct * p_risk * 0.5 or mid <= 0:
                        continue
                    cash -= spend
                    npan += 1
                    pos.append(dict(t=t, k=k, exp=expiry(d, p_tenor), n=spend / (mid * (1 + SPREAD)), mid=mid, panic=True))
            new = [t for t in held if t not in have and (i in trade_days and t not in held_at[i - 1])]
            for t in list(dict.fromkeys(new + reopen)):
                size = risk
                if filt == 'spy200' and spy[i - 1] < spy200[i - 1]:
                    continue
                if filt == 'auto' and downs(i) >= 2:
                    size = risk / 2
                if filt == 'guard' and i >= 252 and spy[i - 1] < spy[i - 253]:
                    size = risk / 2
                s, v = C[t][i], iv(t, i, bump)
                if not s > 0:
                    continue
                k = strike_for_delta(s, tenor / 365, v, RATE, delta)
                mid = bs_call(s, k, tenor / 365, v, RATE)
                spend = min(cash, acct * size)
                if spend <= acct * size * 0.5 or mid <= 0:
                    continue
                cash -= spend
                pos.append(dict(t=t, k=k, exp=expiry(d, tenor), n=spend / (mid * (1 + SPREAD)), mid=mid))
            curve.append((d, cash + sum(p['n'] * p['mid'] for p in pos)))
        return curve

    def qqq_trend(lev, extra=None, delta=0.70, tenor=120, roll_at=30):
        """QQQ calls worth `lev` x the account in exposure while QQQ > 200-day; extra = a top-5 calls curve to add (same start)."""
        cash, pos, curve = 100.0, None, []
        for i in range(i0, n):
            d, s = cal[i], q[i]
            v = iv('QQQ', i, 0)
            if pos:
                left = days(d, pos['exp'])
                mid = bs_call(s, pos['k'], max(0, left) / 365, v, RATE)
                if left <= roll_at or q[i - 1] < q200[i - 1]:
                    cash += pos['n'] * mid * (1 - SPREAD)
                    pos = None
                else:
                    pos['mid'] = mid
            acct = cash + (pos['n'] * pos['mid'] if pos else 0)
            if pos is None and q[i - 1] > q200[i - 1]:
                k = strike_for_delta(s, tenor / 365, v, RATE, delta)
                mid = bs_call(s, k, tenor / 365, v, RATE)
                units = lev * acct / (bs_delta(s, k, tenor / 365, v, RATE) * s)
                cost = min(cash, units * mid * (1 + SPREAD))
                cash -= cost
                pos = dict(k=k, exp=expiry(d, tenor), n=cost / (mid * (1 + SPREAD)), mid=mid)
            curve.append((d, cash + (pos['n'] * pos['mid'] if pos else 0)))
        return curve

    def sell_puts(delta=0.70, tenor=45, bump=0.10, roll_at=0):
        """Cash-secured puts on each top-5 holding (strike = the delta-0.70 call strike -> put delta about -0.30)."""
        cash, pos, curve = 100.0, [], []
        for i in range(i0, n):
            d = cal[i]
            held = held_at[i]
            keep = []
            for p in pos:
                s = C[p['t']][i]
                left = days(d, p['exp'])
                mid = put(s, p['k'], max(0, left) / 365, iv(p['t'], i, bump))
                if p['t'] not in held or left <= roll_at:
                    cash -= p['n'] * mid * (1 + SPREAD if left > 0 else 1)
                else:
                    p['mid'] = mid
                    keep.append(p)
            pos = keep
            acct = cash - sum(p['n'] * p['mid'] for p in pos)
            have = {p['t'] for p in pos}
            for t in held:
                if t in have:
                    continue
                s, v = C[t][i], iv(t, i, bump)
                if not s > 0 or acct <= 0:
                    continue
                k = strike_for_delta(s, tenor / 365, v, RATE, delta)
                mid = put(s, k, tenor / 365, v)
                units = (acct / 5) / k
                cash += units * mid * (1 - SPREAD)
                pos.append(dict(t=t, k=k, exp=expiry(d, tenor), n=units, mid=mid))
            curve.append((d, cash - sum(p['n'] * p['mid'] for p in pos)))
        return curve

    def spy_putwrite():
        """Calibration: sell 1-month at-the-money SPY puts, fully cash-secured, every month (like CBOE ^PUT)."""
        cash, pos, curve = 100.0, None, []
        bump = 0.04
        for i in range(i0, n):
            d, s = cal[i], spy[i]
            v = max(0.10, (V['SPY'][i] if not np.isnan(V['SPY'][i]) else 0.2) + bump)
            if pos:
                left = days(d, pos['exp'])
                mid = put(s, pos['k'], max(0, left) / 365, v)
                if left <= 0:
                    cash -= pos['n'] * mid
                    pos = None
                else:
                    pos['mid'] = mid
            acct = cash - (pos['n'] * pos['mid'] if pos else 0)
            if pos is None:
                mid = put(s, s, 30 / 365, v)
                units = acct / s
                cash += units * mid * (1 - 0.005)
                pos = dict(k=s, exp=expiry(d, 30), n=units, mid=mid)
            curve.append((d, cash - (pos['n'] * pos['mid'] if pos else 0)))
        return curve

    print("simulating...", flush=True)
    t5 = r['curve']
    P35, P30, PF = panic_signals(), panic_signals(vix_min=30), panic_signals(vix_min=30, fading=True)
    print(f"panic weeks: VIX 35+ {len(P35)}, VIX 30+ {len(P30)}, fading {len(PF)}", flush=True)
    rows = {
        'calls on entries 10% (earlier best)': calls_on_top5(),
        'calls + roll 10%': calls_on_top5(roll=True),
        'calls + roll 15%': calls_on_top5(roll=True, risk=0.15),
        'calls + roll 20%': calls_on_top5(roll=True, risk=0.20),
        'calls + roll, deep 0.80 / 180d 10%': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45),
        'calls + roll, deep 0.80 / 180d 20%': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, risk=0.20),
        'calls on entries 10%, SPY filter': calls_on_top5(filt='spy200'),
        'deep 0.80 / 180d 10%, SPY filter': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, filt='spy200'),
        'deep 0.80 / 180d 15%, SPY filter': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, risk=0.15, filt='spy200'),
        'deep 0.80 / 180d 15%, guard filter': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, risk=0.15, filt='guard'),
        'calls + roll 15%, SPY filter': calls_on_top5(roll=True, risk=0.15, filt='spy200'),
        'PANIC calls only, 90d ATM 5%': calls_on_top5(top5=False, panic=P35),
        'PANIC calls only, 90d ATM 10%': calls_on_top5(top5=False, panic=P35, p_risk=0.10),
        'PANIC calls only, 45d ATM 5%': calls_on_top5(top5=False, panic=P35, p_tenor=45, p_roll=3),
        'PANIC calls only, 90d ITM.70 10%': calls_on_top5(top5=False, panic=P35, p_risk=0.10, p_delta=0.70),
        'PANIC calls only, VIX fading, 90d ATM 10%': calls_on_top5(top5=False, panic=PF, p_risk=0.10),
        'PANIC calls only, VIX 30+, 90d ATM 10%': calls_on_top5(top5=False, panic=P30, p_risk=0.10),
        'PANIC calls only 10% [pricier +25pt]': calls_on_top5(top5=False, panic=P35, p_risk=0.10, p_bump=0.25),
        'deep top-5 SPY filter + PANIC 5%': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, filt='spy200', panic=P35),
        'deep top-5 SPY filter + PANIC 10%': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, filt='spy200', panic=P35, p_risk=0.10),
        'deep top-5 SPY filter + PANIC 10% [pricier]': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, filt='spy200', panic=P35, p_risk=0.10, bump=0.20, p_bump=0.25),
        'deep 15% SPY filter + PANIC 10%': calls_on_top5(roll=True, delta=0.80, tenor=180, roll_at=45, risk=0.15, filt='spy200', panic=P35, p_risk=0.10),
        'calls + roll 15%, auto filter': calls_on_top5(roll=True, risk=0.15, filt='auto'),
        'calls + roll 15%, guard filter': calls_on_top5(roll=True, risk=0.15, filt='guard'),
        'calls + roll 15% [pricier +20pt]': calls_on_top5(roll=True, risk=0.15, bump=0.20),
        'QQQ trend calls 1x': qqq_trend(1),
        'QQQ trend calls 2x': qqq_trend(2),
        'QQQ trend calls 3x': qqq_trend(3),
        'sell puts on top 5 (cushion 10)': sell_puts(),
        'sell puts on top 5 (cushion 5)': sell_puts(bump=0.05),
        'sell puts on top 5 (cushion 0)': sell_puts(bump=0.0),
        'sell at-the-money puts (cushion 5)': sell_puts(delta=0.50, bump=0.05),
        'sell at-the-money puts (cushion 0)': sell_puts(delta=0.50, bump=0.0),
        'SPY put-writing (our pricing)': spy_putwrite(),
    }
    try:
        import yfinance as yf
        h = yf.Ticker('^PUT').history(start=cal[i0], auto_adjust=False)['Close']
        rows['SPY put-writing (real CBOE ^PUT)'] = [(d.strftime('%Y-%m-%d'), float(v)) for d, v in h.items()]
    except Exception as e:  # noqa: BLE001
        print("no ^PUT:", e)
    rows['top 5 in stock'] = [tuple(p[:2]) for p in t5]
    rows['buy & hold SPY'] = [(b[0], b[4]) for b in bench['SPY'] if b[0] >= cal[i0]]
    rows['buy & hold QQQ'] = [(b[0], b[4]) for b in bench['QQQ'] if b[0] >= cal[i0]]

    spans = [('since 2000', '2000-01-01', '2100'), ('2000-09', '2000-01-01', '2009-12-31'),
             ('2010-19', '2010-01-01', '2019-12-31'), ('since 2020', '2020-01-01', '2100')]
    head = ' | '.join(f"{lab:^22}" for lab, _, _ in spans)
    print(f"\n{'options-only account':38} | {head}")
    print(f"{'':38} | " + ' | '.join(f"{'total':>9} {'/yr':>5} {'worst':>6}" for _ in spans))
    for label, c in rows.items():
        out = []
        for _, a, b in spans:
            vals = [v for d, v in c if a <= d <= b]
            st = curve_stats(vals) if len(vals) > 200 else None
            out.append(f"{st['total']:+9.0%} {st['annual'] if st['annual'] is not None else -1:+5.0%} {st['maxDD']:6.0%}" if st else f"{'':>22}")
        print(f"{label:38} | " + ' | '.join(out), flush=True)

    years = sorted({d[:4] for d in cal[i0:]})
    pick = ['calls on entries 10% (earlier best)', 'calls + roll 15%', 'calls + roll 15%, guard filter',
            'deep 0.80 / 180d 10%, SPY filter', 'PANIC calls only, 90d ATM 10%', 'deep top-5 SPY filter + PANIC 10%', 'deep 15% SPY filter + PANIC 10%', 'QQQ trend calls 2x', 'sell puts on top 5 (cushion 5)', 'sell puts on top 5 (cushion 0)',
            'top 5 in stock', 'buy & hold QQQ']
    print(f"\n{'by year':38} " + ' '.join(f"{y:>6}" for y in years))
    for label in pick:
        c = rows[label]
        ye, prev, ys = {}, c[0][1], []
        for d, v in c:
            ye[d[:4]] = v
        for y in years:
            if y in ye and prev > 0:
                ys.append(f"{ye[y] / prev - 1:+6.0%}")
                prev = ye[y]
            else:
                ys.append(f"{'':>6}")
        print(f"{label:38} " + ' '.join(ys), flush=True)


if __name__ == '__main__':
    main()

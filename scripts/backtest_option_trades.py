#!/usr/bin/env python3
"""Call-buying trades on the top-5 signals: which option gives the best reward for the risk?

Every time a stock ENTERS the top 5 (S&P 500 + Nasdaq-100, 6-1 month strength,
same rule as the dashboard; signal Friday, trade at Monday's close) one call
trade is opened on it. It is closed when the model drops the stock, 21 days
before expiry, or - in the "TP/SL" versions - at +100% (take profit) or -50%
(stop). Variants: expiry 60 / 90 / 180 days; strike at delta 0.70 (in the
money), 0.50 (at the money), 0.30 (out of the money); or a call spread (buy
delta 0.60, sell 20% above the price).

No historical option prices are available, so calls are Black-Scholes priced
from each stock's 63-day realized volatility + a cushion (10 points, or 20 for
the "pricier options" check; floor 20%), 4% rate, 2% bid/ask paid each way
(each leg for spreads). Real fills, skew and earnings IV crush will differ.

Portfolio: each new trade risks 5% of the account (premium paid, the most it
can lose); the rest sits in cash (0% interest, to be conservative).

--account: an options-ONLY account (no stocks) that risks 5 / 10 / 15 / 20% of
its value on each new call, compared year by year with the dashboard's
current setup (auto mix), the top 5 in stock, SPY and QQQ.

Usage:
    python scripts/backtest_option_trades.py
    python scripts/backtest_option_trades.py --account
"""
import math
import os
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import START  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.options_sim import bs_call, strike_for_delta  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

RATE, SPREAD, RISK = 0.04, 0.02, 0.05


def realized(series, i, window=63):
    rets = [math.log(series[j] / series[j - 1]) for j in range(max(1, i - window + 1), i + 1) if series[j - 1] and series[j]]
    if len(rets) < 10:
        return 0.4
    m = sum(rets) / len(rets)
    return math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1) * 252)


def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    px = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    px.update({t: {b[0][:10]: b[4] for b in bs} for t, bs in extra.items()})
    px['SPY'] = dict(bench['SPY'])
    cal = [d for d, _ in bench['SPY']]
    idx = {d: i for i, d in enumerate(cal)}

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    r = run_momentum(px, cal, START, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    top5 = curve_stats([p[1] for p in r['curve']])
    # episodes: (ticker, entry day, model exit day or None)
    episodes, prev, open_at = [], [], {}
    for d, held in r['picks']:
        for t in held:
            if t not in prev:
                open_at[t] = d
        for t in prev:
            if t not in held:
                episodes.append((t, open_at.pop(t), d))
        prev = held
    for t, d in open_at.items():
        episodes.append((t, d, None))
    episodes.sort(key=lambda e: e[1])
    series = {}
    for t in {e[0] for e in episodes}:
        last, s = None, []
        for d in cal:
            last = px[t].get(d) or last
            s.append(last)
        series[t] = s

    def run(tenor, strike, tp=None, sl=None, bump=0.10, risk=RISK):
        """Returns (per-trade returns, portfolio curve)."""
        def iv(t, i):
            return max(0.20, realized(series[t], i) + bump)

        def value(pos, i):
            t, k1, k2, exp = pos['t'], pos['k1'], pos['k2'], pos['exp']
            s, tt, v = series[t][i], max(0.0, days(cal[i], exp) / 365), iv(t, i)
            c1 = bs_call(s, k1, tt, v, RATE)
            c2 = bs_call(s, k2, tt, v, RATE) if k2 else 0.0
            return c1, c2

        entries = {}
        for e in episodes:
            entries.setdefault(e[1], []).append(e)
        cash, openp, curve, rets = 100.0, [], [], []
        first = episodes[0][1]
        for i, d in enumerate(cal):
            if d < first:
                continue
            # exits
            keep = []
            for pos in openp:
                c1, c2 = value(pos, i)
                mid = c1 - c2
                bid = c1 * (1 - SPREAD) - c2 * (1 + SPREAD)
                why = None
                if pos['out'] == d:
                    why = 'model'
                elif days(d, pos['exp']) <= 21:
                    why = 'expiry'
                elif tp is not None and bid >= pos['cost'] * (1 + tp):
                    why = 'tp'
                elif sl is not None and bid <= pos['cost'] * (1 - sl):
                    why = 'sl'
                if why:
                    proceeds = max(0.0, bid)
                    cash += pos['n'] * proceeds
                    rets.append(proceeds / pos['cost'] - 1)
                else:
                    pos['mid'] = mid
                    keep.append(pos)
            openp = keep
            acct = cash + sum(p['n'] * p['mid'] for p in openp)
            # entries at this close
            for t, d0, out in entries.get(d, []):
                s, v = series[t][i], iv(t, i)
                exp_d = date.fromordinal(date.fromisoformat(d).toordinal() + tenor).isoformat()
                tt = tenor / 365
                if strike == 'spread':
                    k1, k2 = strike_for_delta(s, tt, v, RATE, 0.60), s * 1.20
                else:
                    k1, k2 = strike_for_delta(s, tt, v, RATE, strike), None
                c1 = bs_call(s, k1, tt, v, RATE)
                c2 = bs_call(s, k2, tt, v, RATE) if k2 else 0.0
                cost = c1 * (1 + SPREAD) - c2 * (1 - SPREAD)
                spend = min(cash, acct * risk)
                if cost <= 0 or spend <= 0:
                    continue
                n = spend / cost
                cash -= spend
                openp.append(dict(t=t, k1=k1, k2=k2, exp=exp_d, cost=cost, n=n, out=out, mid=c1 - c2))
            curve.append(cash + sum(p['n'] * p['mid'] for p in openp))
        return rets, curve, [cal[i] for i, d in enumerate(cal) if d >= first]

    if '--account' in sys.argv:
        return account(run, r, bench)
    # the same trades held as stock, for reference
    stock = []
    for t, d0, out in episodes:
        if out:
            stock.append(series[t][idx[out]] / series[t][idx[d0]] - 1)
    print(f"{len(episodes)} entries into the top 5 since {START}; holding the stock instead: "
          f"{sum(1 for x in stock if x > 0) / len(stock):.0%} winners, average {statistics.mean(stock):+.1%}, "
          f"median {statistics.median(stock):+.1%}\n")
    print(f"{'option trade':34} {'win%':>5} {'avg win':>8} {'avg loss':>8} {'payoff':>6} {'per $1':>7} {'median':>7} {'best':>7} | "
          f"{'5%/trade acct':>13} {'/yr':>5} {'worst':>6}")
    labels = {0.70: 'ITM d.70', 0.50: 'ATM d.50', 0.30: 'OTM d.30', 'spread': 'spread d.60/+20%'}
    results = []
    for tenor in (60, 90, 180):
        for strike in (0.70, 0.50, 0.30, 'spread'):
            for tp, sl in ((None, None), (1.0, 0.5)):
                rets, curve, _ = run(tenor, strike, tp, sl)
                wins, losses = [x for x in rets if x > 0], [x for x in rets if x <= 0]
                st = curve_stats(curve)
                label = f"{tenor}d {labels[strike]}" + (' TP/SL' if tp else '')
                results.append((label, tenor, strike, tp, st))
                print(f"{label:34} {len(wins) / len(rets):5.0%} {statistics.mean(wins) if wins else 0:+8.0%} "
                      f"{statistics.mean(losses) if losses else 0:+8.0%} "
                      f"{(statistics.mean(wins) / -statistics.mean(losses)) if wins and losses else 0:6.2f} "
                      f"{statistics.mean(rets):+7.0%} {statistics.median(rets):+7.0%} {max(rets):+7.0%} | "
                      f"{st['total']:+13.0%} {st['annual']:+5.0%} {st['maxDD']:6.0%}", flush=True)
        print()
    print(f"{'top 5 stock model (all in)':34} {'':>53} | {top5['total']:+13.0%} {top5['annual']:+5.0%} {top5['maxDD']:6.0%}")
    best = sorted(results, key=lambda x: -x[4]['annual'])[:3]
    print("\nPricier options check (volatility cushion 20 points instead of 10) for the 3 best:")
    for label, tenor, strike, tp, _ in best:
        rets, curve, _ = run(tenor, strike, tp, 0.5 if tp else None, bump=0.20)
        st = curve_stats(curve)
        print(f"  {label:32} per $1 {statistics.mean(rets):+6.0%}   win {sum(1 for x in rets if x > 0) / len(rets):4.0%}   "
              f"account {st['total']:+7.0%} ({st['annual']:+.0%}/yr, worst {st['maxDD']:.0%})")


def account(run, r, bench):
    import json
    scan = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'momentum_scan.json')))
    rows = {}
    for tenor, strike, name in ((90, 0.70, '90d in-the-money'), (90, 0.50, '90d at-the-money'), (180, 0.70, '180d in-the-money')):
        for risk in (0.05, 0.10, 0.15, 0.20):
            for bump, tag in ((0.10, ''), (0.20, ' [pricier]')):
                if bump == 0.20 and risk not in (0.10, 0.20):
                    continue
                _, curve, dates = run(tenor, strike, risk=risk, bump=bump)
                rows[f"options only: {name}, {risk:.0%}/trade{tag}"] = list(zip(dates, curve))
    rows['current setup (auto mix)'] = scan['curves']['plan']
    rows['top 5 in stock'] = [p[:2] for p in r['curve']]
    for b in ('SPY', 'QQQ'):
        rows['buy & hold ' + b] = [[d, v] for d, v in bench[b] if d >= START]
    years = sorted({d[:4] for d, _ in rows['top 5 in stock']})
    print(f"{'since 2020':48} {'total':>9} {'/yr':>5} {'worst':>6} | " + ' '.join(f"{y:>6}" for y in years))
    for label, c in rows.items():
        c = [(d, v) for d, v in c]
        st = curve_stats([v for _, v in c])
        ye, prev, ys = {}, c[0][1], []
        for d, v in c:
            ye[d[:4]] = v
        for y in years:
            if y in ye:
                ys.append(f"{ye[y] / prev - 1:+6.0%}")
                prev = ye[y]
            else:
                ys.append(f"{'':>6}")
        print(f"{label:48} {st['total']:+9.0%} {st['annual']:+5.0%} {st['maxDD']:6.0%} | " + ' '.join(ys), flush=True)
        if label.startswith('options only') and label.endswith('20%/trade [pricier]'):
            print()


if __name__ == '__main__':
    main()

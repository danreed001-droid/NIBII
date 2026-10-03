#!/usr/bin/env python3
"""Top-5 strongest stocks from the S&P 500 + Nasdaq-100 combined vs the S&P 500
alone (mtl.momentum.run_momentum), from 2020, vs SPY and QQQ.

The 15 Nasdaq-100 members that are not in the S&P 500 have no published
join dates, so they are eligible from the day they have 6 months of
history - which lets in hindsight (a stock is in today's Nasdaq-100
partly BECAUSE it went up). The script reports how much of the gain came
from those 15, so the bias can be sized; the S&P-only run, which uses
each stock's real join date, is the fair result.

Usage:
    python scripts/backtest_combined.py
"""
import collections
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRA_CACHE = os.path.join(ROOT, 'data', '.ndx_extra.pkl')
NASDAQ_ONLY = ['ALAB', 'ALNY', 'ARM', 'ASML', 'CCEP', 'CRWV', 'FER', 'MELI', 'MSTR', 'NBIS',
               'PDD', 'RKLB', 'SHOP', 'SPCX', 'TRI']  # Nasdaq-100 members not in the S&P 500, Oct 2026


def load_extra():
    if os.path.exists(EXTRA_CACHE):
        with open(EXTRA_CACHE, 'rb') as f:
            return pickle.load(f)
    import yfinance as yf
    df = yf.download(NASDAQ_ONLY, interval='1d', start='2015-01-01', group_by='ticker', auto_adjust=False,
                     progress=False, threads=True)
    out = {}
    for t in NASDAQ_ONLY:
        d = df[t].dropna(subset=['Close'])
        out[t] = [(ts.isoformat(), float(o), float(h), float(l), float(c))
                  for ts, o, h, l, c in zip(d.index, d['Open'], d['High'], d['Low'], d['Close'])]
    with open(EXTRA_CACHE, 'wb') as f:
        pickle.dump(out, f)
    return out


def yearly(points):
    """{year: return} from [[date, value], ...], each year from the prior year's last value."""
    out, prev_end, cur_year, last = {}, None, None, None
    for d, v in points:
        y = d[:4]
        if y != cur_year:
            if cur_year is not None:
                out[cur_year] = last / (prev_end or first) - 1
                prev_end = last
            else:
                first = v
            cur_year = y
        last = v
    if cur_year is not None:
        out[cur_year] = last / (prev_end or first) - 1
    return out


def stats(curve, lo='2020-01-02', hi='9999'):
    return curve_stats([p[1] for p in curve if lo <= p[0] < hi])


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    sp = [t for t in names if t not in ETFS and t not in BROKEN]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp if raw[t].get('daily')}
    base['SPY'] = dict(bench['SPY'])
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]
    added = load_added()

    def eligible(t, d):
        return t in extra or added.get(t, '0000') <= d

    print(f"{'universe / score':40} {'total':>7} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>7} | {'2025-26':>7}")
    runs = {}
    for label, prices in (('S&P 500 only', base), ('S&P 500 + Nasdaq-100', comb)):
        for sname, (look, skip) in (('6-1m', (126, 21)), ('12-1m', (252, 21))):
            r = run_momentum(prices, calendar, '2020-01-02', look=look, skip=skip, top_n=5, eligible=eligible)
            runs[(label, sname)] = (r, prices)
            f, i, o = stats(r['curve']), stats(r['curve'], hi='2025-01-01'), stats(r['curve'], lo='2025-01-01')
            print(f"{label + ', top 5, ' + sname:40} {f['total']:+7.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | "
                  f"{i['total']:+7.0%} | {o['total']:+7.0%}")
    for b in ('SPY', 'QQQ'):
        pts = bench[b]
        f = curve_stats([c for d, c in pts if d >= '2020-01-02'])
        i = curve_stats([c for d, c in pts if '2020-01-02' <= d < '2025-01-01'])
        o = curve_stats([c for d, c in pts if d >= '2025-01-01'])
        print(f"{'buy & hold ' + b:40} {f['total']:+7.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | "
              f"{i['total']:+7.0%} | {o['total']:+7.0%}")

    cols = [('S&P top 5', [p[:2] for p in runs[('S&P 500 only', '6-1m')][0]['curve']]),
            ('S&P+NDX top 5', [p[:2] for p in runs[('S&P 500 + Nasdaq-100', '6-1m')][0]['curve']])]
    cols += [(b, [[d, c] for d, c in bench[b] if d >= '2019-12-31']) for b in ('SPY', 'QQQ')]
    years = {name: yearly(pts) for name, pts in cols}
    print(f"\nyear by year (6-month strength):\n{'year':6}" + ''.join(f"{n:>15}" for n, _ in cols))
    for y in sorted(years['S&P top 5']):
        print(f"{y:6}" + ''.join(f"{years[n].get(y, 0):+15.0%}" for n, _ in cols))

    r, prices = runs[('S&P 500 + Nasdaq-100', '6-1m')]
    val = {p[0]: p[1] for p in r['curve']}
    contrib, weeks = collections.Counter(), collections.Counter()
    for (d, h), (d2, _) in zip(r['picks'], r['picks'][1:]):
        for t in h:
            a, b = prices[t].get(d), prices[t].get(d2) or prices[t].get(d)
            contrib[t] += (b / a - 1) * val[d] / 5
            weeks[t] += 1
    tot = sum(contrib.values())
    ex = sum(v for t, v in contrib.items() if t in extra)
    print(f"\ncombined 6-1m: total gain ${tot:,.0f}; directly from the Nasdaq-only stocks ${ex:,.0f} ({ex / tot:.0%})")
    for t, v in sorted(((t, v) for t, v in contrib.items() if t in extra), key=lambda x: -x[1]):
        print(f"  {t:5} ${v:7,.0f}  held {weeks[t]} weeks")
    print(f"holds as of {r['picks'][-1][0]}: {', '.join(r['picks'][-1][1])}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Top-5 strongest, weekly, built from XLF / XLY / QQQ / SPY / XLE / XLK / GLD / TLT.

The stocks inside those ETFs are the S&P 500 (SPY already holds every
XLF/XLY/XLE/XLK stock) plus the Nasdaq-100 (QQQ); GLD and TLT hold gold
and Treasury bonds, not stocks. So two versions:

  A. stocks + ETFs: rank the stocks AND the eight ETFs together, so the
     portfolio can rotate into GLD / TLT / a sector ETF when they lead.
  B. your sectors: only financials, consumer discretionary, energy and
     technology S&P stocks, plus the Nasdaq-100.

Vs the S&P 500 + Nasdaq-100 stock-only top 5, SPY and QQQ, year by year.
A stock must beat SPY's score to qualify. S&P stocks count from their
join date; the 15 Nasdaq-only stocks have none (hindsight - see
backtest_combined.py). Prices are closes without dividends.

Usage:
    python scripts/backtest_etf_universe.py
"""
import collections
import csv
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETF_CACHE = os.path.join(ROOT, 'data', '.etf8.pkl')
ETF8 = ['XLF', 'XLY', 'QQQ', 'SPY', 'XLE', 'XLK', 'GLD', 'TLT']
SECTORS = {'Financials', 'Consumer Discretionary', 'Energy', 'Information Technology'}
BENCH = '^SPY'   # benchmark key, kept apart from the SPY ETF so SPY itself can be ranked


def load_etfs():
    if os.path.exists(ETF_CACHE):
        with open(ETF_CACHE, 'rb') as f:
            return pickle.load(f)
    import yfinance as yf
    df = yf.download(ETF8, interval='1d', start='2015-01-01', group_by='ticker', auto_adjust=False,
                     progress=False, threads=True)
    out = {t: [(ts.isoformat(), float(o), float(h), float(l), float(c))
               for ts, o, h, l, c in zip(df[t].index, df[t]['Open'], df[t]['High'], df[t]['Low'], df[t]['Close'])
               if c == c] for t in ETF8}
    with open(ETF_CACHE, 'wb') as f:
        pickle.dump(out, f)
    return out


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra, etfs = load_extra(), load_etfs()
    with open(os.path.join(ROOT, 'data', 'ndx100.csv'), newline='') as f:
        ndx = {r['symbol'] for r in csv.DictReader(f)}
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    stock_px = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    stock_px.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    etf_px = {t: {b[0][:10]: b[4] for b in bars} for t, bars in etfs.items()}
    calendar = [d for d, _ in bench['SPY']]

    def eligible(t, d):
        return t in extra or t in etf_px or added.get(t, '0000') <= d

    universes = {
        'S&P + Nasdaq-100 stocks (last test)': list(stock_px),
        'A. stocks + the 8 ETFs': list(stock_px) + ETF8,
        'B. fin/consumer/energy/tech + Nasdaq-100': [t for t in stock_px if t in ndx or names.get(t, ('', ''))[1] in SECTORS],
    }
    results = {}
    print(f"{'top 5, 6-month strength, from 2020':44} {'total':>7} {'CAGR':>5} {'maxDD':>6}")
    for label, members in universes.items():
        prices = {t: (etf_px[t] if t in etf_px else stock_px[t]) for t in members}
        prices[BENCH] = dict(bench['SPY'])
        r = run_momentum(prices, calendar, '2020-01-02', benchmark=BENCH, look=126, skip=21, top_n=5,
                         eligible=eligible)
        results[label] = r
        s = curve_stats([p[1] for p in r['curve']])
        print(f"{label:44} {s['total']:+7.0%} {s['annual']:+5.0%} {s['maxDD']:6.0%}")
    for b in ('SPY', 'QQQ'):
        s = curve_stats([c for d, c in bench[b] if d >= '2020-01-02'])
        print(f"{'buy & hold ' + b:44} {s['total']:+7.0%} {s['annual']:+5.0%} {s['maxDD']:6.0%}")

    cols = [(k.split(' (')[0][:22], [p[:2] for p in r['curve']]) for k, r in results.items()]
    cols += [(b, [[d, c] for d, c in bench[b] if d >= '2019-12-31']) for b in ('SPY', 'QQQ')]
    years = {n: yearly(p) for n, p in cols}
    print(f"\n{'year':6}" + ''.join(f"{n:>24}" for n, _ in cols))
    for y in sorted(years[cols[0][0]]):
        print(f"{y:6}" + ''.join(f"{years[n].get(y, 0):+24.0%}" for n, _ in cols))

    for label, r in results.items():
        held = collections.Counter(t for _, h in r['picks'] for t in h)
        etf_weeks = {t: held[t] for t in ETF8 if held[t]}
        print(f"\n{label}: ETF weeks held {etf_weeks or 'none'}; holds as of {r['picks'][-1][0]}: "
              f"{', '.join(r['picks'][-1][1])}")


if __name__ == '__main__':
    main()

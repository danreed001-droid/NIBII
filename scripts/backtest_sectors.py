#!/usr/bin/env python3
"""Sector (and industry) ranking filter for the top-5 rule, since 2020.

Each Friday, rank sectors by the median 6-1 month score of their stocks; only
buy stocks from the top N sectors; sell a holding whose sector has been out of
the top for more than one week (one week's grace), replacing it with the best
stock from a top sector. Sectors = GICS (S&P) / ICB mapped to GICS
(Nasdaq-only); industries = data/industries.csv.

Usage:
    python scripts/backtest_sectors.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra, yearly  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_protect import WINDOWS, window_return  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added, load_ndx, load_sp500  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START, SPLIT = '2020-01-02', '2025-01-01'
ICB_TO_GICS = {'Technology': 'Information Technology', 'Telecommunications': 'Communication Services',
               'Health Care': 'Health Care', 'Consumer Discretionary': 'Consumer Discretionary',
               'Consumer Staples': 'Consumer Staples', 'Industrials': 'Industrials', 'Financials': 'Financials',
               'Energy': 'Energy', 'Utilities': 'Utilities', 'Basic Materials': 'Materials', 'Real Estate': 'Real Estate'}


def main():
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sector = {t: sec for t, (_, sec) in load_sp500().items()}
    for t, (_, ind) in load_ndx().items():
        sector.setdefault(t, ICB_TO_GICS.get(ind, ind))
    with open(os.path.join(ROOT, 'data', 'industries.csv'), newline='') as f:
        industry = {r['symbol']: r['industry'] for r in csv.DictReader(f)}
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    base = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
    base['SPY'] = dict(bench['SPY'])
    comb = dict(base)
    comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()})
    calendar = [d for d, _ in bench['SPY']]

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    variants = {
        'current (no sector filter)': {},
        'top 1 sector': dict(sector_of=sector, top_sectors=1),
        'top 2 sectors': dict(sector_of=sector, top_sectors=2),
        'top 3 sectors': dict(sector_of=sector, top_sectors=3),
        'top 3 sectors, no grace': dict(sector_of=sector, top_sectors=3, sector_grace=0),
        'top 5 industries': dict(sector_of=industry, top_sectors=5, sector_min=2),
        'top 10 industries': dict(sector_of=industry, top_sectors=10, sector_min=2),
    }
    curves = {}
    for uni, prices in (('S&P 500 + Nasdaq-100', comb), ('S&P 500 only (fair)', base)):
        print(f"\n== {uni}, top 5, since 2020 ==")
        print(f"{'filter':30} {'total':>8} {'CAGR':>5} {'maxDD':>6} | {'2020-24':>8} {'2025-26':>8} | "
              + ' | '.join(f"{w:>15}" for w in WINDOWS) + " | turn/yr")
        for label, kw in variants.items():
            r = run_momentum(prices, calendar, START, look=126, skip=21, top_n=5, eligible=member, **kw)
            c = r['curve']
            f = curve_stats([p[1] for p in c])
            i = curve_stats([p[1] for p in c if p[0] < SPLIT])
            o = curve_stats([p[1] for p in c if p[0] >= SPLIT])
            curves[(uni, label)] = ([p[:2] for p in c], r['picks'])
            ws = ' | '.join(f"{window_return(c, a, b):+15.1%}" for a, b in WINDOWS.values())
            print(f"{label:30} {f['total']:+8.0%} {f['annual']:+5.0%} {f['maxDD']:6.0%} | {i['total']:+8.0%} "
                  f"{o['total']:+8.0%} | {ws} | {r['turnover']:5.1f}x", flush=True)
    keys = [('S&P 500 + Nasdaq-100', k) for k in ('current (no sector filter)', 'top 1 sector', 'top 2 sectors',
                                                   'top 3 sectors', 'top 10 industries')]
    years = {k: yearly(curves[k][0]) for k in keys}
    years['SPY'] = yearly([[d, c] for d, c in bench['SPY'] if d >= '2019-12-31'])
    years['QQQ'] = yearly([[d, c] for d, c in bench['QQQ'] if d >= '2019-12-31'])
    heads = ['current', 'top 1 sec', 'top 2 sec', 'top 3 sec', 'top 10 ind', 'SPY', 'QQQ']
    print(f"\nS&P 500 + Nasdaq-100, year by year\n{'year':6}" + ''.join(f"{h:>11}" for h in heads))
    for y in sorted(years[keys[0]]):
        print(f"{y:6}" + ''.join(f"{years[k].get(y, 0):+11.0%}" for k in keys + ['SPY', 'QQQ']))
    for k in keys[1:4]:
        d, h = curves[k][1][-1]
        print(f"{k[1]} holds as of {d}: {', '.join(f'{t} ({sector.get(t, chr(63))})' for t in h)}")


if __name__ == '__main__':
    main()

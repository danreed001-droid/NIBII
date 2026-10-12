#!/usr/bin/env python3
"""Strategy lab: new ideas built on the ignition scan and the research,
tested exactly like the dashboard's Top 5 rule and compared with it from
2000, 2010 and 2020 to today. Writes data/strategy_backtest.json for the
"Strategy lab" section of docs/scanner.html.

Every strategy: S&P 500 + Nasdaq-100 (today's lists; an S&P stock only from
the day it joined), ranked by 6-1 month strength, must beat SPY, top 5 in
equal weight, keep while top 10, signal at the week's last close, trade the
next session's close, 0.05% cost. They differ only in which stocks may be
bought (or jump the queue):

- Current: Top 5            - the dashboard rule.
- Current + news boost      - the dashboard's Boost list: a 12%+ news gap in the last
                              4 weeks replaces the weakest holding (mtl/news.py).
- Top 2 sectors             - only the 2 sectors with the strongest median score.
- Top 3 industries          - only the 3 strongest GICS industries ("hot industries").
- Ignition stocks only      - only stocks with an Ignition (mtl/ignition.py: gap 8%+
                              on 3x+ volume, in an uptrend) in the last 3 months.
- Ignition boost            - the Top 5, but an Ignition in the last 4 weeks replaces
                              the weakest holding.
- Repeat gappers            - only stocks with 2+ ignition / turnaround gaps in 12 months.
- Trend leaders near highs  - only stocks passing the trend template and within 5%
                              of their 52-week high.
- Semis & AI watchlist      - only data/watchlist.json's names. HINDSIGHT: the list was
                              picked in 2026 knowing AI won; it shows what the theme
                              was worth, not what you could have known in 2000.

BIG CAVEAT (same as scripts/backtest_long_history.py): stocks that left the
indexes or went bust are missing, which flatters every strategy, more so the
further back the start.

Usage:
    python scripts/backtest_strategies.py           # downloads ~26 years once (cached in data/.strategy_hist.pkl)
"""
import json
import os
import pickle
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_scan import blocked_dates, fetch  # noqa: E402
from mtl import ignition as ig  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.news import booster, news_gap_days  # noqa: E402
from mtl.universe import load_added, load_ndx, load_sp500, momentum_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.strategy_hist.pkl')
OUT = os.path.join(ROOT, 'data', 'strategy_backtest.json')
FROM = '1998-06-01'
STARTS = {'2000': '2000-01-03', '2010': '2010-01-04', '2020': '2020-01-02'}
IGN_RECENT, BOOST_WINDOW, REPEAT_MIN = 63, 21, 2
NEAR_HIGH = -0.05
ICB_TO_GICS = {'Technology': 'Information Technology', 'Telecommunications': 'Communication Services',
               'Health Care': 'Health Care', 'Consumer Discretionary': 'Consumer Discretionary',
               'Consumer Staples': 'Consumer Staples', 'Industrials': 'Industrials', 'Financials': 'Financials',
               'Energy': 'Energy', 'Utilities': 'Utilities', 'Basic Materials': 'Materials', 'Real Estate': 'Real Estate'}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def watchlist():
    with open(os.path.join(ROOT, 'data', 'watchlist.json')) as f:
        w = json.load(f)
    return {t for g, ts in w.items() if not g.startswith('_') for t in ts}


def load():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    names = momentum_universe(refresh=False)
    tick = sorted(set(names) | watchlist())
    vols = {}
    bars = fetch(tick, start=FROM, volumes=vols)
    bench = fetch(['SPY', 'QQQ'], start=FROM, adjusted=True)
    data = dict(names=names, bars=bars, vols=vols, bench=bench)
    with open(CACHE, 'wb') as f:
        pickle.dump(data, f)
    return data


def wide(bars, vols, cal):
    """Wide O/H/L/C/V DataFrames on the SPY calendar."""
    idx = pd.to_datetime(cal)
    cols = {k: {} for k in 'OHLCV'}
    for t, bs in bars.items():
        if not bs:
            continue
        d = pd.to_datetime([b[0] for b in bs])
        for k, j in zip('OHLC', (1, 2, 3, 4)):
            cols[k][t] = pd.Series([b[j] for b in bs], index=d)
        v = vols.get(t) or {}
        cols['V'][t] = pd.Series([v.get(b[0], float('nan')) for b in bs], index=d, dtype=float)
    return [pd.DataFrame(cols[k]).reindex(idx) for k in 'OHLCV']


def flag_days(flags, cal, kinds):
    """{ticker: sorted [session index, ...]} where any of `kinds` flagged."""
    out = {}
    for k in kinds:
        f = flags[k]
        for t in f.columns:
            rows = f.index[f[t].values].tolist()
            if rows:
                out.setdefault(t, []).extend(cal.index(r.date().isoformat()) for r in rows)
    return {t: sorted(set(v)) for t, v in out.items()}


def count_in(days, k, n):
    """How many of the sorted session indexes fall in (k - n, k]."""
    return bisect_right(days, k) - bisect_left(days, k - n + 1)


def main():
    D = load()
    names, bars, bench = D['names'], D['bars'], D['bench']
    cal = [b[0] for b in bench['SPY']]
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo('America/New_York'))
    if cal[-1] == now.date().isoformat() and (now.hour, now.minute) < (16, 30):
        cal = cal[:-1]                   # today's session isn't finished
    pos = {d: i for i, d in enumerate(cal)}
    sp, added = load_sp500(), load_added()
    wl = watchlist()
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    blocked = {t: blocked_dates(bs) for t, bs in bars.items() if bs}
    log(f'{len(bars)} stocks; computing ignition flags since {FROM}')

    O, H, L, C, V = wide({t: bs for t, bs in bars.items()}, D['vols'], cal)
    res = ig.compute(O, H, L, C, V)
    ign = flag_days(res['flags'], cal, ('ignition',))
    gaps = flag_days(res['flags'], cal, ('ignition', 'turnaround'))
    trend, hi52 = res['trend'], res['hi52']
    near = (C / hi52 - 1 >= NEAR_HIGH) & trend
    near_set = {(t, cal[i]) for t in near.columns for i in near[t].to_numpy().nonzero()[0]}

    sector = {t: sec for t, (_, sec) in sp.items()}
    for t, (_, ind) in load_ndx().items():
        sector.setdefault(t, ICB_TO_GICS.get(ind, ind))
    import csv
    with open(os.path.join(ROOT, 'data', 'industries.csv'), newline='') as f:
        industry = {r['symbol']: r['industry'] for r in csv.DictReader(f)}
    for t in names:
        industry.setdefault(t, sector.get(t, ''))

    def base_ok(t, d):
        if d in blocked.get(t, ()):
            return False
        if t in sp:
            return added.get(t, '0000') <= d
        return t in names        # Nasdaq-100-only names: no join dates (a little hindsight)

    def ok_ign(t, d):
        return base_ok(t, d) and count_in(ign.get(t, []), pos[d], IGN_RECENT) > 0

    def ok_repeat(t, d):
        return base_ok(t, d) and count_in(gaps.get(t, []), pos[d], 252) >= REPEAT_MIN

    def ok_near(t, d):
        return base_ok(t, d) and (t, d) in near_set

    def ok_watch(t, d):
        return t in wl and d not in blocked.get(t, ())

    news = booster({t: news_gap_days(bs) for t, bs in bars.items() if bs}, cal)
    ign_boost = booster({t: [cal[i] for i in ds] for t, ds in ign.items()}, cal, window=BOOST_WINDOW)
    force = dict(prefer_mode='force', prefer_rank=None, prefer_pool='all')
    strategies = {
        'Current: Top 5': dict(eligible=base_ok),
        'Current + news boost': dict(eligible=base_ok, prefer=news, **force),
        'Top 2 sectors': dict(eligible=base_ok, sector_of=sector, top_sectors=2),
        'Top 3 industries': dict(eligible=base_ok, sector_of=industry, top_sectors=3, sector_min=2),
        'Ignition stocks only': dict(eligible=ok_ign),
        'Ignition boost': dict(eligible=base_ok, prefer=ign_boost, **force),
        'Repeat gappers': dict(eligible=ok_repeat),
        'Trend leaders near highs': dict(eligible=ok_near),
        'Semis & AI watchlist': dict(eligible=ok_watch),
    }
    universe = {t: p for t, p in prices.items() if t in names or t in wl or t == 'SPY'}
    out = {}
    for label, start in STARTS.items():
        rows = {}
        for name, kw in strategies.items():
            r = run_momentum(universe, cal, start, look=126, skip=21, top_n=5, exec_next='close', **kw)
            c = r['curve']
            st = curve_stats([p[1] for p in c])
            rows[name] = dict(total=st['total'], annual=st['annual'], maxDD=st['maxDD'], turnover=r.get('turnover'),
                              holds=r['picks'][-1][1] if r.get('picks') else [])
            log(f"{label} {name:28} {st['total']:+9.0%} {st['annual']:+6.1%}/yr  maxDD {st['maxDD']:6.0%}")
        for b in ('SPY', 'QQQ'):
            v = [x[4] for x in bench[b] if start <= x[0] <= cal[-1]]
            st = curve_stats(v)
            rows[b] = dict(total=st['total'], annual=st['annual'], maxDD=st['maxDD'], bench=True)
            log(f"{label} {b:28} {st['total']:+9.0%} {st['annual']:+6.1%}/yr  maxDD {st['maxDD']:6.0%}")
        out[label] = dict(start=start, rows=rows)
    res_json = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), asOf=cal[-1], periods=out,
                    hindsight=['Semis & AI watchlist'])
    with open(OUT, 'w') as f:
        json.dump(res_json, f, indent=1)
    log(f'wrote {OUT}')


if __name__ == '__main__':
    main()

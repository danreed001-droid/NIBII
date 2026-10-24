#!/usr/bin/env python3
"""Strategy lab: new ideas built on the ignition scan and the research,
tested exactly like the dashboard's Top 5 rule and compared with it from
2000, 2010 and 2020 to today. Writes data/strategy_backtest.json for the
"Strategy lab" section of docs/scanner.html.

Every strategy: S&P 500 members (today's list, each stock only from the day it joined),
ranked by 6-1 month strength, must beat SPY, top 5 in equal weight, keep while top 10,
signal at the week's last close, trade the next session's close, 0.05% cost. All but the
last row then run inside the dashboard's default plan, through the same code the live scan
runs (scripts/momentum_scan.py plan_exits and plan_overlay): the blow-off and surge exits,
the fading-energy filter, the rotation into TLT / GLD, the lower-high exit, the whipsaw
half-switch (counting sales with the fading-energy filter off), the narrow-market cash week,
the rebound rule, no T-bills (gold or bonds if up over 3 months, else DBMF managed futures
from its start in May 2019, plain cash before), the price-break rule and the two-scale buy rules
(buy freeze, green light, no stock with weekly and daily lower highs; mtl/fractal.py). They differ only in which stocks may be
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
    python scripts/backtest_strategies.py --refresh # downloads again (to today's close)
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
from momentum_scan import blocked_dates, fetch, plan_exits, plan_overlay, plan_rules  # noqa: E402
from mtl import fractal  # noqa: E402
from mtl import ignition as ig  # noqa: E402
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.rotation import CASH_FUND, bills_pick, rotation_curve  # noqa: E402
from mtl.sleeve import ASSETS, filled  # noqa: E402
from mtl.news import booster, news_gap_days  # noqa: E402
from mtl.universe import load_added, load_ndx, load_sp500, momentum_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.strategy_hist.pkl')
OUT = os.path.join(ROOT, 'data', 'strategy_backtest.json')
FROM = '1998-06-01'
STARTS = {'2000': '2000-01-03', '2010': '2010-01-04', '2020': '2020-01-02'}
IGN_RECENT, BOOST_WINDOW, REPEAT_MIN = 63, 21, 2
NEAR_HIGH = -0.05
TAX, LT_TAX = 0.35, 0.20     # assumed short-term (weekly trading) and long-term (buy and hold) rates
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


def rotation_data():
    """OHLC of the sleeve / rotation ETFs, the 10-year yield (the whipsaw's regime check), and the
    equal-weight S&P 500 (RSP) and VIX closes (the narrow-market cash week)."""
    assets = fetch(ASSETS + [CASH_FUND], start=FROM, adjusted=True)   # + managed futures (no_bills' fallback for cash)
    rate = {b[0]: b[4] for b in (fetch(['^TNX'], start=FROM).get('^TNX') or []) if b[4]}
    rsp = {b[0]: b[4] for b in (fetch(['RSP'], start=FROM, adjusted=True).get('RSP') or []) if b[4]}
    vix = {b[0]: b[4] for b in (fetch(['^VIX'], start=FROM).get('^VIX') or []) if b[4]}
    return dict(assets=assets, rate=rate, rsp=rsp, vix=vix)


def load(refresh=False):
    if os.path.exists(CACHE) and not refresh:
        with open(CACHE, 'rb') as f:
            data = pickle.load(f)
        if 'rsp' not in data or CASH_FUND not in (data.get('assets') or {}):   # older cache without the rotation's assets, the cash week's data or DBMF
            data.update(rotation_data())
            with open(CACHE, 'wb') as f:
                pickle.dump(data, f)
        return data
    names = momentum_universe(refresh=False)
    tick = sorted(set(names) | watchlist())
    vols = {}
    bars = fetch(tick, start=FROM, volumes=vols)
    bench = fetch(['SPY', 'QQQ'], start=FROM, adjusted=True)
    data = dict(names=names, bars=bars, vols=vols, bench=bench, **rotation_data())
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
    D = load(refresh='--refresh' in sys.argv)
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
        return t in sp and added.get(t, '0000') <= d     # S&P 500 members only, as the live plan (since Oct 19, 2026)

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
    force = dict(prefer_mode='force', prefer_rank=None, prefer_pool='all', open_end=True)
    universe = {t: p for t, p in prices.items() if t in names or t in wl or t == 'SPY'}
    rules = plan_rules(bench['SPY'], bars, cal, min(STARTS.values()))   # the two-scale buy rules (mtl/fractal.py, Oct 24, 2026)
    exits = plan_exits(universe, D['vols'], cal, rules=rules)

    spy_c = [prices['SPY'].get(d) for d in cal]
    above = {}
    for i in range(199, len(cal)):
        w = [x for x in spy_c[i - 199:i + 1] if x]
        above[cal[i]] = bool(spy_c[i] and spy_c[i] > sum(w) / len(w))

    def spy_up(d):
        """Positive regime: SPY closed above its 200-day average."""
        return above.get(d, False)

    def ok_news(t, d):
        return base_ok(t, d) and news(t, pos[d])

    def inside(ok):
        """The current system's stock part (Boost list + blow-off / surge exits + fading-energy filter) with
        only stocks passing `ok` allowed - news-gap boosts included."""
        return dict(eligible=ok, prefer=lambda t, k: news(t, k) and ok(t, cal[k]), **force, **exits)
    strategies = {
        'Current system': dict(eligible=base_ok, prefer=news, **force, **exits),
        '+ Ignition boost': dict(eligible=base_ok, prefer=lambda t, k: news(t, k) or ign_boost(t, k), **force, **exits),
        'Top 2 sectors': dict(inside(base_ok), sector_of=sector, top_sectors=2),
        'Top 3 industries': dict(inside(base_ok), sector_of=industry, top_sectors=3, sector_min=2),
        'Ignition stocks only': inside(ok_ign),
        'Repeat gappers': inside(ok_repeat),
        'Trend leaders near highs': inside(ok_near),
        'Semis & AI watchlist': inside(ok_watch),
        'News gappers only': inside(ok_news),
        'News gappers when SPY up': dict(eligible=lambda t, d: ok_news(t, d) if spy_up(d) else base_ok(t, d),
                                         prefer=news, **force, **exits),
        'Boost only when SPY up': dict(eligible=base_ok, prefer=lambda t, k: spy_up(cal[k]) and news(t, k), **force, **exits),
        'News gappers, cash when SPY down': dict(inside(ok_news), risk_on=spy_up, _norot=True),
    }

    # everything above the stock list, exactly as the dashboard's default plan (scripts/momentum_scan.py plan_overlay):
    # the rotation, the lower-high exit, the whipsaw half-switch, the narrow-market cash week, the rebound rule and no T-bills
    A = D['assets']
    whip_px = {**filled({t: {b[0]: b[4] for b in bs} for t, bs in A.items() if bs}, cal), 'SPY': prices['SPY']}
    shadow = plan_exits(universe, D['vols'], cal, fade=False)    # the whipsaw counts sales with the fading-energy filter off

    out = {}
    for label, start in STARTS.items():
        rows = {}
        for name, kw in strategies.items():
            kw = dict(kw)
            norot = kw.pop('_norot', False)
            r = run_momentum(universe, cal, start, look=126, skip=21, top_n=5, exec_next='close', **kw)
            stock = [[d, v] for d, v, _ in r['curve']]
            if norot:
                curve = stock
            else:
                kw.update(shadow)
                kw.pop('buy_when', None)
                kw.pop('buy_max_rank', None)
                whip = run_momentum(universe, cal, start, look=126, skip=21, top_n=5, exec_next='close', **kw)['picks']
                ov = plan_overlay(bench['SPY'], A, whip_px, whip, universe, cal, start, D['rate'], D['rsp'], D['vix'],
                                  green=rules['green'])
                stock = fractal.slot_haven(stock, r['picks'], rules['frozen'], whip_px, cal, start,
                                           lambda k_: bills_pick(whip_px, cal, k_))   # empty slots inside a buy freeze: the haven pick
                curve = rotation_curve(stock, whip_px, cal, ov['modes'], half=ov['half'])
            rows[name] = summary(curve, holds=r['picks'][-1][1] if r.get('picks') else [])
            log(f"{label} {name:26} {rows[name]['annual']:+6.1%}/yr  after tax {rows[name]['afterTax']:+6.1%}  maxDD {rows[name]['maxDD']:6.0%}")
        r = run_momentum(universe, cal, start, look=126, skip=21, top_n=5, exec_next='close', eligible=base_ok, open_end=True)
        rows['Top 5 alone'] = dict(summary([[d, v] for d, v, _ in r['curve']]), ref=True)
        for b in ('SPY', 'QQQ'):
            rows[b] = dict(summary([[x[0], x[4]] for x in bench[b] if start <= x[0] <= cal[-1]], buy_hold=True), bench=True)
        for n_ in ('Top 5 alone', 'SPY', 'QQQ'):
            log(f"{label} {n_:26} {rows[n_]['annual']:+6.1%}/yr  after tax {rows[n_]['afterTax']:+6.1%}  maxDD {rows[n_]['maxDD']:6.0%}")
        out[label] = dict(start=start, rows=rows)
    res_json = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), asOf=cal[-1], periods=out,
                    hindsight=['Semis & AI watchlist'], taxRate=TAX, base='Current system')
    with open(OUT, 'w') as f:
        json.dump(res_json, f, indent=1)
    log(f'wrote {OUT}')


def after_tax(curve, rate=None, buy_hold=False):
    """Per-year return in a regular taxable account, roughly: each calendar year's gain is
    taxed at `rate` (short-term - these strategies trade weekly, so gains are realized
    within the year), losses carried forward against later gains. Buy-and-hold rows are
    taxed once at the end at the long-term rate instead."""
    rate = TAX if rate is None else rate
    if len(curve) < 2:
        return None
    years = (len(curve) - 1) / 252
    if buy_hold:
        g = curve[-1][1] / curve[0][1] - 1
        end = 1 + g - LT_TAX * max(g, 0)
        return end ** (1 / years) - 1
    ends, w, carry = {}, 1.0, 0.0
    for d, v in curve:
        ends[d[:4]] = v
    prev = curve[0][1]
    for y in sorted(ends):
        gain = w * (ends[y] / prev - 1)
        prev = ends[y]
        if gain < 0:
            carry += -gain
        else:
            used = min(carry, gain)
            carry -= used
            gain -= rate * (gain - used)
        w += gain
    return w ** (1 / years) - 1


def summary(curve, holds=None, buy_hold=False):
    st = curve_stats([p[1] for p in curve])
    out = dict(total=st['total'], annual=st['annual'], maxDD=st['maxDD'], afterTax=after_tax(curve, buy_hold=buy_hold))
    if holds is not None:
        out['holds'] = holds
    return out


if __name__ == '__main__':
    main()

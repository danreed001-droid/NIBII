#!/usr/bin/env python3
"""Backtests the scanner's daily and hourly setups (rules in mtl/backtest.py)
over the default universe (S&P 500 + the six ETFs), longs and shorts,
under both trend rules, then renders docs/backtest.html (results plotted
over time) and writes every trade to data/backtest_trades.csv.

History is capped by Yahoo's intraday limits, not by --start: 1h bars go
back ~730 trading days (the daily trade's trigger) and 15m bars ~60 days
(the hourly trade's). Weekly/daily context uses daily bars from 2015 so
the trend reads are warmed up from the first trigger bar. Prices are
split-adjusted (Yahoo's Close with auto_adjust=False - intraday and daily
on the same basis) so a split never reads as a crash; the buy-and-hold
benchmarks use Adj Close (dividends reinvested).

Usage:
    python scripts/backtest.py                       # full universe, from 2020-01-01
    python scripts/backtest.py AAPL NVDA XLF         # just these
    python scripts/backtest.py --stake 100 --start 2020-01-01
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.backtest import (ET, SETUPS, curve_stats, growth, portfolio_index, resample, simulate,
                          summarize, with_ends)
from mtl.universe import default_universe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODES = {'strict': 4, 'loose': 2}
# Buy-and-hold comparisons, drawn on the same "growth of $100" chart.
BENCHMARKS = {'SPY': 'S&P 500 (SPY)', 'QQQ': 'Nasdaq-100 (QQQ)', 'NVDA': 'Nvidia (NVDA)',
              'ARKK': 'ARK Innovation (ARKK)', 'BTC-USD': 'Bitcoin (BTC-USD)'}
FETCH = {'daily': ('1d', dict(start='2015-01-01')),
         '1h': ('60m', dict(period='730d')),
         '15m': ('15m', dict(period='60d'))}


def _download(tickers, interval, **kw):
    import yfinance as yf
    return yf.download(tickers, interval=interval, group_by='ticker', auto_adjust=False,
                       threads=True, progress=False, **kw)


def fetch_all(tickers, chunk=100):
    out = {t: {} for t in tickers}
    for tf, (interval, kw) in FETCH.items():
        for k in range(0, len(tickers), chunk):
            part = tickers[k:k + chunk]
            print(f"  {tf}: {k + len(part)}/{len(tickers)}", file=sys.stderr)
            df = _download(part, interval, **kw)
            for t in part:
                bars = []
                if df is not None and not df.empty and t in df.columns.get_level_values(0):
                    d = df[t]
                    for ts, o, h, l, c in zip(d.index, d['Open'], d['High'], d['Low'], d['Close']):
                        if c == c and h == h and l == l:
                            bars.append((ts.isoformat(), float(o), float(h), float(l), float(c)))
                out[t][tf] = bars
    return out


def fetch_benchmarks():
    """{ticker: [[date, adj_close], ...]} daily since 2015."""
    df = _download(list(BENCHMARKS), '1d', start='2015-01-01')
    out = {}
    for t in BENCHMARKS:
        d = df[t]
        out[t] = [[ts.date().isoformat(), float(c)] for ts, c in zip(d.index, d['Adj Close']) if c == c]
    return out


def thin(points, max_points=900):
    """Keeps every k-th point (and the last) so the page stays light."""
    if len(points) <= max_points:
        return points
    k = -(-len(points) // max_points)
    return points[::k] + ([points[-1]] if (len(points) - 1) % k else [])


def build_series(raw):
    daily = raw['daily']
    return {
        'weekly': resample(daily, 'W'),
        'daily': (daily, with_ends(daily)),
        '1h': (raw['1h'], with_ends(raw['1h'], timedelta(hours=1))),
        '15m': (raw['15m'], with_ends(raw['15m'], timedelta(minutes=15))),
    }


def curve(trades):
    """Cumulative P&L by exit date (closed trades only): [[date, cum, n_that_day], ...]."""
    by_day = {}
    for t in trades:
        if t['open']:
            continue
        d = t['exitTime'][:10]
        by_day.setdefault(d, [0.0, 0])
        by_day[d][0] += t['pnl']
        by_day[d][1] += 1
    cum, out = 0.0, []
    for d in sorted(by_day):
        cum += by_day[d][0]
        out.append([d, round(cum, 2), by_day[d][1]])
    return out


def yearly(trades):
    out = {}
    for t in trades:
        if t['open']:
            continue
        y = t['exitTime'][:4]
        r = out.setdefault(y, dict(trades=0, wins=0, pnl=0.0))
        r['trades'] += 1
        r['wins'] += t['ret'] > 0
        r['pnl'] += t['pnl']
    return out


def by_ticker(trades, k=10):
    agg = {}
    for t in trades:
        if t['open']:
            continue
        a = agg.setdefault(t['ticker'], dict(t=t['ticker'], trades=0, pnl=0.0, wins=0))
        a['trades'] += 1
        a['pnl'] += t['pnl']
        a['wins'] += t['ret'] > 0
    rows = sorted(agg.values(), key=lambda a: a['pnl'])
    return dict(best=rows[::-1][:k], worst=rows[:k])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tickers', nargs='*')
    ap.add_argument('--start', default='2020-01-01')
    ap.add_argument('--stake', type=float, default=100.0)
    ap.add_argument('--csv', default=os.path.join(ROOT, 'data', 'backtest_trades.csv'))
    ap.add_argument('--json', default=os.path.join(ROOT, 'data', 'backtest.json'))
    args = ap.parse_args()

    names = default_universe(refresh=not args.tickers)
    tickers = [t.upper() for t in args.tickers] or list(names)
    start = datetime.fromisoformat(args.start).replace(tzinfo=ET)
    print(f"Fetching history for {len(tickers)} tickers...", file=sys.stderr)
    raw = fetch_all(tickers)
    bench = fetch_benchmarks()
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    sessions = [d for d, _ in bench['SPY']]

    all_trades = []
    for tk in tickers:
        if not raw[tk].get('daily'):
            continue
        series = build_series(raw[tk])
        for mode, lookback in MODES.items():
            for name, setup in SETUPS.items():
                for t in simulate(series, setup, lookback, start, ticker=tk, stake=args.stake):
                    all_trades.append(dict(t, mode=mode, setup=name))

    fields = ['mode', 'setup', 'ticker', 'side', 'entryTime', 'entry', 'exitTime', 'exit',
              'ret', 'pnl', 'bars', 'open']
    with open(args.csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: t[k] for k in fields} for t in all_trades)
    print(f"wrote {args.csv} ({len(all_trades)} trades)", file=sys.stderr)

    results = {}
    for mode in MODES:
        for name in SETUPS:
            sub = [t for t in all_trades if t['mode'] == mode and t['setup'] == name]
            block = {}
            for side in ('long', 'short', 'all'):
                st = sub if side == 'all' else [t for t in sub if t['side'] == side]
                block[side] = dict(stats=summarize(st), curve=curve(st), years=yearly(st),
                                   tickers=by_ticker(st))
            entries = sorted(t['entryTime'] for t in sub)
            block['first'] = entries[0][:10] if entries else None
            block['last'] = max((t['exitTime'] for t in sub), default='')[:10] or None
            # One $100 account vs buy-and-hold, over this block's own window.
            block['growth'], block['bench'] = {}, {}
            if block['first']:
                cal = [d for d in sessions if block['first'] <= d <= block['last']]
                for side in ('long', 'short', 'all'):
                    st = sub if side == 'all' else [t for t in sub if t['side'] == side]
                    idx = portfolio_index(st, closes, cal)
                    block['growth'][side] = dict(
                        stats=dict(curve_stats([p[1] for p in idx]),
                                   exposure=sum(1 for p in idx if p[2]) / len(idx) if idx else None,
                                   avgOpen=sum(p[2] for p in idx) / len(idx) if idx else None),
                        curve=thin([[d, round(v, 3), n] for d, v, n in idx]))
                for b, pts in bench.items():
                    g = growth([p for p in pts if block['first'] <= p[0] <= block['last']])
                    block['bench'][b] = dict(stats=curve_stats([p[1] for p in g], 365 if b == 'BTC-USD' else 252),
                                             curve=thin([[d, round(v, 3)] for d, v in g]))
            results[f"{mode}:{name}"] = block
            s = block['all']['stats']
            if s.get('trades'):
                print(f"{mode:>6} {name:>6}: {s['trades']:>6} trades  win {s['winRate']:.0%}  "
                      f"avg {s['avgRet']:+.2%}  P&L ${s['totalPnl']:+,.0f}  "
                      f"(long ${block['long']['stats'].get('totalPnl', 0):+,.0f} / "
                      f"short ${block['short']['stats'].get('totalPnl', 0):+,.0f})")
                g = block['growth']['all']['stats']
                vs = '  '.join(f"{b} {block['bench'][b]['stats']['total']:+.0%}" for b in BENCHMARKS
                               if block['bench'][b]['stats']['total'] is not None)
                print(f"{'':>14}$100 account {g['total']:+.1%} (max DD {g['maxDD']:.1%}) vs {vs}")

    payload = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   start=args.start, stake=args.stake, tickers=len(tickers), modes=MODES,
                   setups={k: dict(v, context=list(v['context'])) for k, v in SETUPS.items()},
                   benchmarks=BENCHMARKS,
                   results=results)
    with open(args.json, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f"wrote {args.json}", file=sys.stderr)


if __name__ == '__main__':
    main()

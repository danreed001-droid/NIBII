#!/usr/bin/env python3
"""The three follow-up ideas from the variants test, each with an
in-sample / out-of-sample split:

1. Relative strength: the daily trade's buys (1h trigger, so Nov 2023 on)
   only on stocks beating SPY over the prior 3 or 6 months.
2. Trend hold (daily/weekly only, so from 2020): own a stock while its
   weekly and daily charts are both rising, sell on the first daily
   bearish break - alone and with the 6-month relative-strength filter.
3. Timing: hold QQQ / SPY, in cash only while weekly and daily are both
   in a downtrend - vs plain buy-and-hold.

Reuses the price cache from scripts/backtest_variants.py.

Usage:
    python scripts/backtest_next.py
"""
import json
import os
import sys
from bisect import bisect_left
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
from backtest_variants import load_data, regime_filter  # noqa: E402
from mtl.backtest import (ET, SETUPS, consistent, curve_stats, portfolio_index, resample,  # noqa: E402
                          simulate_variant, summarize, timing_curve, trend_hold, with_ends)
from mtl.universe import default_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rs_filter(ticker_closes, spy, days):
    """allow(side, when): the ticker's return over the prior `days` sessions
    beat SPY's, both measured to the session before the entry's date."""
    tdates = sorted(ticker_closes)
    sdates = [d for d, _ in spy]
    scl = [c for _, c in spy]

    def allow(side, when):
        d = when.date().isoformat()
        k = bisect_left(tdates, d) - 1
        s = bisect_left(sdates, d) - 1
        if k < days or s < days:
            return False
        tr = ticker_closes[tdates[k]] / ticker_closes[tdates[k - days]] - 1
        sr = scl[s] / scl[s - days] - 1
        return tr > sr
    return allow


def both(a, b):
    return lambda side, when: a(side, when) and b(side, when)


def report(label, trades, closes, sessions, first, split):
    rows = {}
    for name, sub, cal in (
            ('full', trades, [d for d in sessions if d >= first]),
            ('in', [t for t in trades if t['entryTime'][:10] < split], [d for d in sessions if first <= d < split]),
            ('out', [t for t in trades if t['entryTime'][:10] >= split], [d for d in sessions if d >= split])):
        s = summarize(sub)
        if not s.get('trades'):
            rows[name] = dict(trades=0)
            continue
        idx = portfolio_index(sub, closes, cal)
        g = curve_stats([p[1] for p in idx])
        rows[name] = dict(trades=s['trades'], winRate=s['winRate'], avgRet=s['avgRet'], pf=s['profitFactor'],
                          acct=g['total'], annual=g['annual'], maxDD=g['maxDD'],
                          avgOpen=sum(p[2] for p in idx) / len(idx))
    f, i, o = rows['full'], rows['in'], rows['out']
    print(f"{label:44} n={f.get('trades', 0):5} win {f.get('winRate', 0):.0%} avg {f.get('avgRet', 0):+.2%} "
          f"PF {f.get('pf') or 0:.2f} | acct {f.get('acct') or 0:+.0%} DD {f.get('maxDD') or 0:.0%} "
          f"open~{f.get('avgOpen', 0):.0f} | IN avg {i.get('avgRet', 0):+.2%} acct {i.get('acct') or 0:+.0%} "
          f"| OUT avg {o.get('avgRet', 0):+.2%} PF {o.get('pf') or 0:.2f} acct {o.get('acct') or 0:+.0%}", flush=True)
    return rows


def bench_line(label, pts, first, split):
    full = curve_stats([c for d, c in pts if d >= first])
    ins = curve_stats([c for d, c in pts if first <= d < split])
    out = curve_stats([c for d, c in pts if d >= split])
    print(f"{label:44} acct {full['total']:+.0%} DD {full['maxDD']:.0%} | IN {ins['total']:+.0%} | OUT {out['total']:+.0%}")
    return dict(full=full, inS=ins, out=out)


def main():
    names = default_universe()
    tickers = list(names)
    raw, bench = load_data(tickers)
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    ranges = {tk: {b[0][:10]: (b[3], b[2]) for b in raw[tk].get('daily', [])} for tk in tickers}
    sessions = [d for d, _ in bench['SPY']]
    spy = bench['SPY']
    out = {}

    # 1. relative strength on the daily trade (1h data -> Nov 2023 on), buys only
    print("\n== 1. Daily trade buys, relative-strength filter (split 2026-01-01) ==")
    start = datetime(2020, 1, 1, tzinfo=ET)
    series = {tk: bt.build_series(raw[tk]) for tk in tickers if raw[tk].get('daily')}
    regime = regime_filter(spy)
    for mode, lookback in bt.MODES.items():
        for label, mk in (('none', lambda tk: None),
                          ('RS 3m', lambda tk: rs_filter(closes[tk], spy, 63)),
                          ('RS 6m', lambda tk: rs_filter(closes[tk], spy, 126)),
                          ('RS 6m + SPY>200d', lambda tk: both(rs_filter(closes[tk], spy, 126), regime))):
            trades = []
            for tk, ser in series.items():
                for t in simulate_variant(ser, SETUPS['daily'], lookback, start, ticker=tk, allow=mk(tk)):
                    if t['side'] == 'long' and consistent(t, ranges):
                        trades.append(t)
            first = min(t['entryTime'] for t in trades)[:10]
            out[f"rs:{mode}:{label}"] = report(f"{mode} daily-trade buys, {label}", trades, closes, sessions, first, '2026-01-01')
    for b in ('SPY', 'QQQ'):
        bench_line(f"  buy & hold {b} (same window)", bench[b], '2023-11-08', '2026-01-01')

    # 2. trend hold from 2020 on daily/weekly charts
    print("\n== 2. Trend hold: own while weekly+daily rise, sell on daily break (from 2020, split 2025-01-01) ==")
    start = datetime(2020, 1, 1, tzinfo=ET)
    for mode, lookback in bt.MODES.items():
        for label, mk in (('all stocks', lambda tk: None), ('RS 6m', lambda tk: rs_filter(closes[tk], spy, 126))):
            trades = []
            for tk in tickers:
                daily = raw[tk].get('daily')
                if not daily:
                    continue
                trades += trend_hold((daily, with_ends(daily)), resample(daily, 'W'), lookback, start,
                                     ticker=tk, allow=mk(tk))
            out[f"hold:{mode}:{label}"] = report(f"{mode} trend hold, {label}", trades, closes, sessions, '2020-01-02', '2025-01-01')
    for b in ('SPY', 'QQQ', 'NVDA', 'ARKK', 'BTC-USD'):
        out[f"bh:{b}"] = bench_line(f"  buy & hold {b}", bench[b], '2020-01-02', '2025-01-01')

    # 3. timing QQQ / SPY (needs OHLC: fetch adjusted daily bars)
    print("\n== 3. Hold the ETF, cash only while weekly AND daily are both down (from 2020, split 2025-01-01) ==")
    import yfinance as yf
    df = yf.download(['QQQ', 'SPY'], interval='1d', start='2015-01-01', group_by='ticker', auto_adjust=True,
                     progress=False, threads=True)
    for etf in ('QQQ', 'SPY'):
        d = df[etf]
        bars = [(ts.isoformat(), float(o), float(h), float(l), float(c))
                for ts, o, h, l, c in zip(d.index, d['Open'], d['High'], d['Low'], d['Close']) if c == c]
        for mode, lookback in bt.MODES.items():
            curve = timing_curve((bars, with_ends(bars)), resample(bars, 'W'), lookback, start)
            vals = [p[1] for p in curve]
            full = curve_stats(vals)
            ins = curve_stats([p[1] for p in curve if p[0] < '2025-01-01'])
            outs = curve_stats([p[1] for p in curve if p[0] >= '2025-01-01'])
            cash = 1 - sum(p[2] for p in curve) / len(curve)
            out[f"timing:{etf}:{mode}"] = dict(full=full, inS=ins, out=outs, cash=cash)
            print(f"{etf} timed ({mode}){'':30} acct {full['total']:+.0%} DD {full['maxDD']:.0%} cash {cash:.0%} "
                  f"| IN {ins['total']:+.0%} DD {ins['maxDD']:.0%} | OUT {outs['total']:+.0%} DD {outs['maxDD']:.0%}")
        bh = curve_stats([b[4] for b in bars if b[0][:10] >= '2020-01-02'])
        bi = curve_stats([b[4] for b in bars if '2020-01-02' <= b[0][:10] < '2025-01-01'])
        bo = curve_stats([b[4] for b in bars if b[0][:10] >= '2025-01-01'])
        print(f"{etf} buy & hold{'':34} acct {bh['total']:+.0%} DD {bh['maxDD']:.0%} | IN {bi['total']:+.0%} DD {bi['maxDD']:.0%} | OUT {bo['total']:+.0%} DD {bo['maxDD']:.0%}")

    with open(os.path.join(ROOT, 'data', 'next_ideas.json'), 'w') as f:
        json.dump(out, f, default=str)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""RSI-50 backtest (mtl.backtest.simulate_rsi): buy when RSI(14) crosses
above 50, sell when it crosses back below. Longs only.

- daily chart, S&P 500 + ETFs, from 2020 (2025-26 = out-of-sample),
  plain / with SPY above its 200-day / with the weekly chart in an uptrend
- 1h chart, same universe, Nov 2023 on (2026 = out-of-sample)
- QQQ and SPY traded on their own RSI, daily from 2020 and 1h, vs holding

A stock only counts once it was in the S&P 500. Open trades are marked at
the last close and included. Reuses the cache from backtest_variants.py.

Usage:
    python scripts/backtest_rsi.py
"""
import os
import statistics
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
from backtest_variants import load_data, regime_filter  # noqa: E402
from mtl.backtest import (ET, SWING_N, Context, consistent, curve_stats, portfolio_index, resample,  # noqa: E402
                          simulate_rsi, with_ends)
from mtl.universe import default_universe, load_added  # noqa: E402


def describe(trades, closes, sessions, first, split, bar_days):
    def block(ts, cal):
        if not ts:
            return None
        marked = [dict(t, open=False) for t in ts]
        acct = curve_stats([p[1] for p in portfolio_index(marked, closes, cal)])
        rets = [t['ret'] for t in ts]
        return dict(n=len(ts), win=sum(r > 0 for r in rets) / len(rets), avg=statistics.mean(rets),
                    med=statistics.median(rets), days=statistics.mean(t['bars'] for t in ts) * bar_days,
                    acct=acct['total'], dd=acct['maxDD'])
    return (block(trades, [d for d in sessions if d >= first]),
            block([t for t in trades if t['entryTime'][:10] < split], [d for d in sessions if first <= d < split]),
            block([t for t in trades if t['entryTime'][:10] >= split], [d for d in sessions if d >= split]))


def line(label, res):
    f, i, o = res
    if not f:
        print(f"{label:46} no trades")
        return
    print(f"{label:46} {f['n']:6} {f['win']:5.0%} {f['avg']:+7.2%} {f['med']:+7.2%} {f['days']:6.1f} | "
          f"{f['acct']:+8.0%} {f['dd']:5.0%} | {i['acct'] if i else 0:+8.0%} | {o['acct'] if o else 0:+8.0%} {o['avg'] if o else 0:+7.2%}",
          flush=True)


def bench_line(label, pts, first, split):
    f = curve_stats([c for d, c in pts if d >= first])
    i = curve_stats([c for d, c in pts if first <= d < split])
    o = curve_stats([c for d, c in pts if d >= split])
    print(f"{label:46} {'':>37} | {f['total']:+8.0%} {f['maxDD']:5.0%} | {i['total']:+8.0%} | {o['total']:+8.0%}")


def header(split):
    print(f"{'version':46} {'trades':>6} {'win':>5} {'avg':>7} {'median':>7} {'days':>6} | {'account':>8} {'DD':>5} | "
          f"{'before ' + split[:4]:>8} | {'from ' + split[:4]:>8} {'avg':>7}")


def main():
    names = default_universe(refresh=False)
    tickers = list(names)
    raw, bench = load_data(tickers)
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    ranges = {tk: {b[0][:10]: (b[3], b[2]) for b in raw[tk].get('daily', [])} for tk in tickers}
    sessions = [d for d, _ in bench['SPY']]
    added = load_added()
    regime = regime_filter(bench['SPY'])
    start = datetime(2020, 1, 1, tzinfo=ET)

    def member(tk):
        return lambda side, when: added.get(tk, '0000') <= when.date().isoformat()

    print("\n== Daily chart, from 2020 (check: 2025-26) ==")
    header('2025-01-01')
    for label in ('plain', 'SPY above 200-day', 'weekly chart in uptrend'):
        trades = []
        for tk in tickers:
            daily = raw[tk].get('daily')
            if not daily:
                continue
            ends = with_ends(daily)
            m = member(tk)
            if label == 'plain':
                allow = m
            elif label.startswith('SPY'):
                allow = lambda s, w, m=m: m(s, w) and regime(s, w)
            else:
                wk = Context(*resample(daily, 'W'), SWING_N['weekly'], 2)
                allow = lambda s, w, m=m, wk=wk: m(s, w) and wk.at(w) == 'uptrend'
            trades += simulate_rsi(daily, ends, start, ticker=tk, allow=allow)
        line(f"S&P 500 stocks, daily RSI, {label}", describe(trades, closes, sessions, '2020-01-02', '2025-01-01', 1))
    for b in ('SPY', 'QQQ'):
        bench_line(f"  buy & hold {b}", bench[b], '2020-01-02', '2025-01-01')

    print("\n== 1-hour chart, Nov 2023 on (check: 2026) ==")
    header('2026-01-01')
    for label in ('plain', 'SPY above 200-day'):
        trades = []
        for tk in tickers:
            h = raw[tk].get('1h')
            if not h:
                continue
            m = member(tk)
            allow = m if label == 'plain' else (lambda s, w, m=m: m(s, w) and regime(s, w))
            for t in simulate_rsi(h, with_ends(h, bt.timedelta(hours=1)), start, ticker=tk, allow=allow):
                if consistent(t, ranges):
                    trades.append(t)
        line(f"S&P 500 stocks, 1h RSI, {label}", describe(trades, closes, sessions, '2023-11-08', '2026-01-01', 1 / 7))
    for b in ('SPY', 'QQQ'):
        bench_line(f"  buy & hold {b}", bench[b], '2023-11-08', '2026-01-01')

    print("\n== QQQ / SPY traded on their own RSI ==")
    import yfinance as yf
    for etf in ('QQQ', 'SPY'):
        for interval, kw, first, split, bar_days in (('1d', dict(start='2015-01-01'), '2020-01-02', '2025-01-01', 1),
                                                    ('60m', dict(period='730d'), '2023-11-08', '2026-01-01', 1 / 7)):
            d = yf.download(etf, interval=interval, auto_adjust=False, progress=False, **kw)
            d.columns = d.columns.get_level_values(0)
            bars = [(ts.isoformat(), float(o), float(h), float(l), float(c))
                    for ts, o, h, l, c in zip(d.index, d['Open'], d['High'], d['Low'], d['Close']) if c == c]
            ends = with_ends(bars) if interval == '1d' else with_ends(bars, bt.timedelta(hours=1))
            dl = yf.download(etf, interval='1d', start='2015-01-01', auto_adjust=False, progress=False)
            dl.columns = dl.columns.get_level_values(0)
            cl = {etf: {ts.date().isoformat(): float(c) for ts, c in zip(dl.index, dl['Close']) if c == c}}
            trades = simulate_rsi(bars, ends, datetime.fromisoformat(first).replace(tzinfo=ET), ticker=etf)
            if interval == '1d':
                header(split)
            line(f"{etf} {'daily' if interval == '1d' else '1h'} RSI 50 in/out", describe(trades, cl, sessions, first, split, bar_days))
            bench_line(f"  buy & hold {etf} (same window)", bench[etf], first, split)


if __name__ == '__main__':
    main()

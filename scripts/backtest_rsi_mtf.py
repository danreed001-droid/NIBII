#!/usr/bin/env python3
"""Hourly-RSI entries filtered by the daily RSI (mtl.backtest.simulate_rsi_mtf):
buy when the hourly RSI(14) crosses above 50 while the daily RSI is above
50; sell when the daily RSI crosses below 50 (the main rule), or - for
comparison - when the hourly RSI crosses back below 50. The daily RSI is
read either at each session's close or live (today's bar still forming).

QQQ, SPY, IWM and the S&P 500 stocks (point-in-time membership), Nov 2023
on (1h history limit), 2026 as the out-of-sample check, vs plain hourly
RSI and buy-and-hold. Reuses the cache from backtest_variants.py.

Usage:
    python scripts/backtest_rsi_mtf.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_rsi import describe, header, line  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import ET, consistent, curve_stats, simulate_rsi, simulate_rsi_mtf, with_ends  # noqa: E402
from mtl.universe import default_universe, load_added  # noqa: E402

FIRST, SPLIT = '2023-11-08', '2026-01-01'
VERSIONS = {
    'plain hourly RSI (before)': None,
    'YOUR RULE: daily RSI>50 at close; sell daily cross<50': dict(daily_mode='closed', exit='daily'),
    'daily RSI>50 live; sell when live daily <50': dict(daily_mode='live', exit='daily'),
    'daily RSI>50 at close; sell hourly cross<50': dict(daily_mode='closed', exit='hourly'),
    'daily RSI>50 live; sell hourly cross<50': dict(daily_mode='live', exit='hourly'),
}


def run(hourly, daily, kw, ticker, allow=None):
    start = datetime.fromisoformat(FIRST).replace(tzinfo=ET)
    if kw is None:
        return simulate_rsi(*hourly, start, ticker=ticker, allow=allow)
    return simulate_rsi_mtf(hourly, daily, start, ticker=ticker, allow=allow, **kw)


def bars_of(df):
    return [(ts.isoformat(), float(o), float(h), float(l), float(c))
            for ts, o, h, l, c in zip(df.index, df['Open'], df['High'], df['Low'], df['Close']) if c == c]


def main():
    import yfinance as yf
    names = default_universe(refresh=False)
    tickers = list(names)
    raw, bench = load_data(tickers)
    sessions = [d for d, _ in bench['SPY']]
    added = load_added()

    for etf in ('QQQ', 'SPY', 'IWM'):
        h = yf.download(etf, interval='60m', period='730d', auto_adjust=False, progress=False)
        d = yf.download(etf, interval='1d', start='2015-01-01', auto_adjust=False, progress=False)
        h.columns, d.columns = h.columns.get_level_values(0), d.columns.get_level_values(0)
        hb, db = bars_of(h), bars_of(d)
        hourly, daily = (hb, with_ends(hb, timedelta(hours=1))), (db, with_ends(db))
        closes = {etf: {b[0][:10]: b[4] for b in db}}
        print(f"\n== {etf} ==")
        header(SPLIT)
        for label, kw in VERSIONS.items():
            line(label, describe(run(hourly, daily, kw, etf), closes, sessions, FIRST, SPLIT, 1 / 7))
        adj = [(b[0][:10], b[4]) for b in db]
        f = curve_stats([c for dd, c in adj if dd >= FIRST])
        i = curve_stats([c for dd, c in adj if FIRST <= dd < SPLIT])
        o = curve_stats([c for dd, c in adj if dd >= SPLIT])
        print(f"{'  buy & hold ' + etf + ' (price only)':46} {'':>37} | {f['total']:+8.0%} {f['maxDD']:5.0%} | "
              f"{i['total']:+8.0%} | {o['total']:+8.0%}")

    print("\n== S&P 500 stocks ==")
    header(SPLIT)
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    ranges = {tk: {b[0][:10]: (b[3], b[2]) for b in raw[tk].get('daily', [])} for tk in tickers}
    for label, kw in VERSIONS.items():
        trades = []
        for tk in tickers:
            hb, db = raw[tk].get('1h'), raw[tk].get('daily')
            if not hb or not db:
                continue
            allow = (lambda tk: lambda s, w: added.get(tk, '0000') <= w.date().isoformat())(tk)
            for t in run((hb, with_ends(hb, timedelta(hours=1))), (db, with_ends(db)), kw, tk, allow):
                if consistent(t, ranges):
                    trades.append(t)
        line(label, describe(trades, closes, sessions, FIRST, SPLIT, 1 / 7))


if __name__ == '__main__':
    main()

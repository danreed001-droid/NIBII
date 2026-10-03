#!/usr/bin/env python3
"""Hourly RSI with a buy/sell band on QQQ, SPY and IWM: buy when RSI(14)
crosses above the buy level, sell when it crosses below the sell level.
Every band is reported; the "pick" is chosen on Nov 2023 - Dec 2025 only
and then checked on 2026, so a lucky fit shows up.

Usage:
    python scripts/backtest_rsi_band.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_rsi import describe, header, line  # noqa: E402
from backtest_rsi_mtf import FIRST, SPLIT, bars_of  # noqa: E402
from mtl.backtest import ET, curve_stats, simulate_rsi, with_ends  # noqa: E402

BANDS = [(50, 50), (52, 48), (55, 45), (55, 50), (50, 45), (60, 40)]


def main():
    import yfinance as yf
    spy = yf.download('SPY', interval='1d', start='2015-01-01', auto_adjust=False, progress=False)
    spy.columns = spy.columns.get_level_values(0)
    sessions = [ts.date().isoformat() for ts in spy.index]
    start = datetime.fromisoformat(FIRST).replace(tzinfo=ET)
    for etf in ('QQQ', 'SPY', 'IWM'):
        h = yf.download(etf, interval='60m', period='730d', auto_adjust=False, progress=False)
        d = yf.download(etf, interval='1d', start='2015-01-01', auto_adjust=False, progress=False)
        h.columns, d.columns = h.columns.get_level_values(0), d.columns.get_level_values(0)
        hb, db = bars_of(h), bars_of(d)
        closes = {etf: {b[0][:10]: b[4] for b in db}}
        print(f"\n== {etf} hourly RSI band ==")
        header(SPLIT)
        res = {}
        for buy, sell in BANDS:
            r = describe(simulate_rsi(hb, with_ends(hb, timedelta(hours=1)), start, ticker=etf,
                                      buy_level=buy, sell_level=sell), closes, sessions, FIRST, SPLIT, 1 / 7)
            res[(buy, sell)] = r
            line(f"buy >{buy} / sell <{sell}", r)
        pick = max(res, key=lambda k: res[k][1]['acct'] if res[k][1] else -9)
        f = curve_stats([b[4] for b in db if b[0][:10] >= FIRST])
        i = curve_stats([b[4] for b in db if FIRST <= b[0][:10] < SPLIT])
        o = curve_stats([b[4] for b in db if b[0][:10] >= SPLIT])
        print(f"{'  buy & hold ' + etf + ' (price only)':46} {'':>37} | {f['total']:+8.0%} {f['maxDD']:5.0%} | "
              f"{i['total']:+8.0%} | {o['total']:+8.0%}")
        print(f"  picked on 2023-25 alone: buy >{pick[0]} / sell <{pick[1]} -> 2026 check "
              f"{res[pick][2]['acct']:+.0%} vs plain 50/50 {res[(50, 50)][2]['acct']:+.0%} vs hold {o['total']:+.0%}")


if __name__ == '__main__':
    main()

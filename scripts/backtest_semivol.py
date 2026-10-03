#!/usr/bin/env python3
"""Up-move vs down-move volatility and choppiness backtest.

CHOP (mtl.backtest.simulate_choppiness): hold while the last N bars rise
more smoothly (higher efficiency ratio) than this chart's last 3 down legs
were choppy; sell when the smoothness falls to the downtrend's level.
Volatility (mtl.backtest.simulate_semivol):
hold while the typical up move is smaller than the typical down move
(steady rises), vs the opposite as a control, vs with a 50-bar trend
filter, over 20- and 50-bar windows.

Daily chart from 2020 (2025-26 = check) on QQQ, SPY, IWM and the S&P 500
stocks (point-in-time membership); hourly chart from Nov 2023 (2026 =
check) on QQQ, SPY, IWM. Reuses the cache from backtest_variants.py.

Usage:
    python scripts/backtest_semivol.py
    python scripts/backtest_semivol.py --chop    # just the choppiness versions
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_rsi import describe, header, line  # noqa: E402
from backtest_rsi_mtf import bars_of  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.backtest import ET, curve_stats, simulate_choppiness, simulate_semivol, with_ends  # noqa: E402
from mtl.universe import default_universe, load_added  # noqa: E402

VERSIONS = {
    'up-vol < down-vol, 20 bars': (simulate_semivol, dict(calm='up', window=20)),
    'up-vol < down-vol, 50 bars': (simulate_semivol, dict(calm='up', window=50)),
    'control: up-vol > down-vol, 20 bars': (simulate_semivol, dict(calm='down', window=20)),
    'CHOP: rise smoother than downtrends, 10 bars': (simulate_choppiness, dict(window=10)),
    'CHOP: rise smoother than downtrends, 20 bars': (simulate_choppiness, dict(window=20)),
    'CHOP like-for-like: 10 bars vs falling 10-bar stretches': (simulate_choppiness, dict(window=10, reference='windows')),
    'CHOP like-for-like: 20 bars vs falling 20-bar stretches': (simulate_choppiness, dict(window=20, reference='windows')),
    'CHOP control: any smooth rise, 10 bars': (simulate_choppiness, dict(window=10, compare_to_down=False)),
}
if '--chop' in sys.argv:
    VERSIONS = {k: v for k, v in VERSIONS.items() if k.startswith('CHOP')}


def hold_line(label, bars, first, split):
    f = curve_stats([b[4] for b in bars if b[0][:10] >= first])
    i = curve_stats([b[4] for b in bars if first <= b[0][:10] < split])
    o = curve_stats([b[4] for b in bars if b[0][:10] >= split])
    print(f"{label:46} {'':>37} | {f['total']:+8.0%} {f['maxDD']:5.0%} | {i['total']:+8.0%} | {o['total']:+8.0%}")


def main():
    import yfinance as yf
    names = default_universe(refresh=False)
    tickers = list(names)
    raw, bench = load_data(tickers)
    sessions = [d for d, _ in bench['SPY']]
    added = load_added()

    for interval, first, split, bar_days in (('1d', '2020-01-02', '2025-01-01', 1),
                                            ('60m', '2023-11-08', '2026-01-01', 1 / 7)):
        start = datetime.fromisoformat(first).replace(tzinfo=ET)
        for etf in ('QQQ', 'SPY', 'IWM'):
            kw = dict(start='2015-01-01') if interval == '1d' else dict(period='730d')
            b = yf.download(etf, interval=interval, auto_adjust=False, progress=False, **kw)
            d = yf.download(etf, interval='1d', start='2015-01-01', auto_adjust=False, progress=False)
            b.columns, d.columns = b.columns.get_level_values(0), d.columns.get_level_values(0)
            bars, dbars = bars_of(b), bars_of(d)
            ends = with_ends(bars) if interval == '1d' else with_ends(bars, timedelta(hours=1))
            closes = {etf: {x[0][:10]: x[4] for x in dbars}}
            print(f"\n== {etf}, {'daily from 2020' if interval == '1d' else 'hourly from Nov 2023'} ==")
            header(split)
            for label, (fn, kw2) in VERSIONS.items():
                line(label, describe(fn(bars, ends, start, ticker=etf, **kw2),
                                     closes, sessions, first, split, bar_days))
            hold_line(f"  buy & hold {etf} (price only)", dbars, first, split)

    print("\n== S&P 500 stocks, daily from 2020 ==")
    header('2025-01-01')
    closes = {tk: {b[0][:10]: b[4] for b in raw[tk].get('daily', [])} for tk in tickers}
    start = datetime(2020, 1, 1, tzinfo=ET)
    for label, (fn, kw) in VERSIONS.items():
        trades = []
        for tk in tickers:
            daily = raw[tk].get('daily')
            if not daily:
                continue
            allow = (lambda tk: lambda s, w: added.get(tk, '0000') <= w.date().isoformat())(tk)
            trades += fn(daily, with_ends(daily), start, ticker=tk, allow=allow, **kw)
        line(label, describe(trades, closes, sessions, '2020-01-02', '2025-01-01', 1))
    spy = [(d + 'T', 0, 0, 0, c) for d, c in bench['SPY']]
    hold_line("  buy & hold SPY (with dividends)", spy, '2020-01-02', '2025-01-01')


if __name__ == '__main__':
    main()

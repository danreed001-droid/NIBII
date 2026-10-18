"""data/track_record.json for the dashboard from the backtest engine's curve dump: the point-in-time backtest (2000 on,
the stocks in the S&P 500 at the time, EP / CPWR left out, 0.15% slippage) of the default plan, Boost 100%, the plain
top 5 and SPY / QQQ, daily closes rebased to 100, with each line's return a year and worst drop.

usage: python research/backtest/build_track.py <curves_dump.json> <data/track_record.json>"""
import json
import sys
from datetime import date

KEYS = {'rotation': 'NBup_boost', 'boost100': 'B1S_boost', 'strategy': 'N1_auto', 'SPY': 'spy', 'QQQ': 'qqq'}
SOURCE = ('Point-in-time backtest: the stocks in the S&P 500 at each date that have price history (58% of members in '
          '2000, 67% in 2010, 77% in 2015, over 90% since 2020; most companies bought out or delisted before then are '
          'missing, which likely flatters the early years; EP and CPWR left out for reused tickers), news gaps, 0.15% '
          'slippage a trade, TLT / GLD spliced onto a Treasury fund / gold futures before they existed.')


def main(src, dst):
    S = json.load(open(src))['series']
    series, stats = {}, {}
    for k, name in KEYS.items():
        c = S[name]['pre'] if isinstance(S[name], dict) else S[name]
        base = c[0][1]
        series[k] = [[d[:10], round(v / base * 100, 3)] for d, v in c]
        vals = [v for _, v in c]
        yrs = (date.fromisoformat(c[-1][0][:10]) - date.fromisoformat(c[0][0][:10])).days / 365.25
        pk, dd = vals[0], 0.0
        for v in vals:
            pk = max(pk, v)
            dd = min(dd, v / pk - 1)
        stats[k] = dict(annual=round((vals[-1] / vals[0]) ** (1 / yrs) - 1, 4), maxDD=round(dd, 4),
                        first=c[0][0][:10], last=c[-1][0][:10])
    out = dict(source=SOURCE, start=min(s['first'] for s in stats.values()), end=max(s['last'] for s in stats.values()),
               series=series, stats=stats)
    json.dump(out, open(dst, 'w'), separators=(',', ':'))
    for k, v in stats.items():
        print(f"{k:9} {v['annual'] * 100:5.1f}% a year, worst drop {v['maxDD'] * 100:4.0f}%, {v['first']} to {v['last']}")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

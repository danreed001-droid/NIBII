"""Build data/market_fitness.json: the yearly market-fitness reviews of the S&P 500 (mtl/market_fit.py) from the
point-in-time backtest data (the real member lists and prices) and the default plan's backtest curve.
    python research/backtest/build_fitness.py <engine .robust_*.pkl> <curves_dump_track.json> data/market_fitness.json
Run by the track record refresh (research/backtest/refresh.sh); the January run is the yearly review."""
import json
import os
import pickle
import sys
from bisect import bisect_left, bisect_right
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from mtl import market_fit  # noqa: E402


def main(pkl, curves, out):
    U = pickle.load(open(pkl, 'rb'))
    S = json.load(open(curves))['series']
    cal = [b[0][:10] for b in U['bench_raw']['SPY']]
    closes = {t: {b[0][:10]: b[4] for b in bs} for t, bs in U['bars'].items() if bs}
    iv = U['iv']

    def member(t, d):
        for a, b in iv.get(t, []):
            if (a is None or a <= d) and (b is None or d <= b):
                return True
        return False
    plan = {d[:10]: v for d, v in S['NBup_boost']['pre']}
    spy = {d[:10]: v for d, v in S['spy']['pre']}
    rows, events = market_fit.records(closes, cal, member, spy, plan)
    last = date.fromisoformat(cal[-1])
    years = list(range(2008, last.year + 1))
    s = market_fit.summary(rows, events, years, live_mode='plan')
    s.update(market='S&P 500 (real member lists)', asOf=cal[-1], review=f'{years[-1]}-01', live='plan',
             note='information only: the live plan is never changed by this review')
    with open(out, 'w') as fh:
        json.dump(s, fh, indent=1)
        fh.write('\n')
    for r in s['reviews']:
        print(r['year'], r['choice'], r['mode'], {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in ('giveBack', 'doublers', 'plan', 'pick', 'index')})
    print('mode', s['mode'], 'alarm', s['alarm'], s['why'])


if __name__ == '__main__':
    main(*sys.argv[1:4])

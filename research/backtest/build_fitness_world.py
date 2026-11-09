"""Build data/market_fitness_world.json: the yearly market-fitness readings (mtl/market_fit.py) of the S&P 500 next to
nine foreign markets, for the scanner page's "Runner quality by market" table. Information only.

    python research/backtest/build_fitness_world.py <abroad raw.pkl> [<more raw.pkl> ...] <curves dir pattern> <out.json>

Each raw.pkl holds {market: {'idx': index ticker, 'fx': fx ticker, 'bars': {ticker: [(date, o, h, l, c, ...)]}}}
(today's index members, local currency). The curves dir pattern has '{mk}' for the market code and points at a
curves dump with the 12-month foreign plan ('AB10L12_boost'). The S&P 500 row is copied from data/market_fitness.json
(real member lists). The foreign rows use today's members, so failures that left the index are missing: their
give-back reads a little better than it was."""
import json
import os
import pickle
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from mtl import market_fit  # noqa: E402

NAMES = {'UK': ('UK', 'FTSE 100'), 'DE': ('Germany', 'DAX'), 'FR': ('France', 'CAC 40'), 'CA': ('Canada', 'TSX 60'),
         'AU': ('Australia', 'ASX 50'), 'HK': ('Hong Kong', 'Hang Seng'), 'ES': ('Spain', 'IBEX 35'),
         'IT': ('Italy', 'FTSE MIB'), 'SE': ('Sweden', 'OMX 30')}
KEEP = ('year', 'giveBack', 'spike', 'doublers', 'good', 'events', 'plan', 'pick', 'index', 'choice', 'mode')


def _round(r):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k in KEEP}


def market(raw, curves):
    ib = raw['bars'][raw['idx']]
    cal = [b[0][:10] for b in ib]
    closes = {t: {b[0][:10]: b[4] for b in bs} for t, bs in raw['bars'].items()
              if t not in (raw['idx'], raw.get('fx')) and len(bs) > 300}
    plan = {}
    if curves and os.path.exists(curves):
        S = json.load(open(curves))['series']
        plan = {d[:10]: v for d, v in (S.get('AB10L12_boost') or {}).get('pre', [])}
    rows, events = market_fit.records(closes, cal, lambda t, d: True, {b[0][:10]: b[4] for b in ib}, plan, minpx=0.0)
    years = list(range(2008, int(cal[-1][:4]) + 1))
    s = market_fit.summary(rows, events, years, live_mode='pick')
    return dict(asOf=cal[-1], stocks=len(closes), reviews=[_round(r) for r in s['reviews']], mode=s['mode'])


def main(args):
    *raws, pattern, out = args
    us = json.load(open(os.path.join(ROOT, 'data', 'market_fitness.json')))
    res = [dict(k='US', country='US', index='S&P 500', lists='real member lists', asOf=us.get('asOf'),
                reviews=[_round(r) for r in us['reviews']], mode=us.get('mode'))]
    for path in raws:
        R = pickle.load(open(path, 'rb'))
        for mk, raw in R.items():
            if mk not in NAMES:
                continue
            m = market(raw, pattern.replace('{mk}', mk))
            res.append(dict(k=mk, country=NAMES[mk][0], index=NAMES[mk][1], lists="today's members", **m))
            last = m['reviews'][-1] if m['reviews'] else {}
            print(mk, m['stocks'], 'stocks', {k: last.get(k) for k in ('year', 'giveBack', 'good', 'spike', 'choice', 'mode')})
    order = ['US'] + list(NAMES)
    res.sort(key=lambda r: order.index(r['k']))
    doc = dict(win=market_fit.WIN, gate=market_fit.GATE, good=market_fit.GOOD, markets=res,
               note='information only; foreign markets on their current index members, in local currency')
    with open(out, 'w') as fh:
        json.dump(doc, fh, indent=1)
        fh.write('\n')


if __name__ == '__main__':
    main(sys.argv[1:])

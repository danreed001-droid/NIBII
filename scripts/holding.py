#!/usr/bin/env python3
"""How long are stocks held? Weekly (current) and monthly 5-stock Auto / Boost,
same footing as scripts/improve.py (point-in-time S&P 500 incl. removed
companies, 2010 onward). A holding spell runs from the trade that buys a stock
to the trade that sells it out completely (the 60/40 sleeve trims do not end a
spell). Writes data/holding.json."""
import json
import os
import sys
from datetime import date, datetime, timezone
from multiprocessing import get_context

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import improve as I  # noqa: E402
import robustness as R  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'holding.json')


def spells(run, prices, last_day):
    open_, out = {}, []
    for T, w in run['weights']:
        held = {t for t, x in w.items() if x > 1e-9}
        for t in list(open_):
            if t not in held:
                out.append((t, open_.pop(t), T, False))
        for t in held:
            open_.setdefault(t, T)
    for t, s in open_.items():
        out.append((t, s, last_day, True))
    rows = []
    for t, s, e, still in out:
        px = prices[t]
        a, b = px.get(s), px.get(e)
        if b is None:   # delisted: last known price before the exit
            ks = [d for d in px if d <= e]
            b = px[max(ks)] if ks else None
        days = (date.fromisoformat(e) - date.fromisoformat(s)).days
        rows.append(dict(t=t, buy=s, sell=None if still else e, days=days, open=still,
                         ret=R.r4(b / a - 1) if a and b else None))
    return rows


def summarize(rows):
    n = len(rows)
    tot = sum(r['days'] for r in rows)
    long_ = [r for r in rows if r['days'] > 365]
    near = [r for r in rows if 300 <= r['days'] <= 365]
    ds = sorted(r['days'] for r in rows)
    bands = {}
    for lab, lo, hi in (('<1 month', 0, 30), ('1-3 months', 31, 91), ('3-6 months', 92, 182),
                        ('6-12 months', 183, 365), ('>1 year', 366, 10 ** 6)):
        bands[lab] = sum(lo <= r['days'] <= hi for r in rows)
    return dict(n=n, medianDays=ds[n // 2], avgDays=round(tot / n, 1), maxDays=ds[-1],
                over1y=len(long_), over1yShare=R.r4(len(long_) / n),
                over1yDayShare=R.r4(sum(r['days'] for r in long_) / tot),
                near1y=len(near), bands=bands,
                longest=sorted(rows, key=lambda r: -r['days'])[:15],
                openNow=[r for r in rows if r['open']])


def main():
    t0 = datetime.now()
    D = R.load_data()
    P = R.prepare(D)
    I.G['P'] = P
    R.G['P'] = P
    cal = P['calendar']
    I.G['months'] = I.month_ends(cal)
    jobs = []
    for name in ('cur', 'n5m'):
        kw = I.VARIANTS[name][0]
        jobs += [(f'{name}_auto', kw, False, ()), (f'{name}_boost', kw, True, ())]
    res = {}
    with get_context('fork').Pool(4) as pool:
        for key, run in pool.imap_unordered(I.run_one, jobs):
            s = summarize(spells(run, P['prices'], cal[-1]))
            res[key] = s
            R.log(f"  {key}: n {s['n']} median {s['medianDays']}d max {s['maxDays']}d "
                  f">1y {s['over1y']} ({s['over1yShare']}) near {s['near1y']}")
            for r in s['longest'][:8]:
                R.log(f"     {r['t']:6s} {r['buy']} -> {r['sell'] or 'still held'} {r['days']}d {r['ret']}")
    payload = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   start=R.START, end=cal[-1], results=res,
                   runtimeMin=round((datetime.now() - t0).total_seconds() / 60, 1))
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    R.log(f"wrote {OUT}")


if __name__ == '__main__':
    main()

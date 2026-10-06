#!/usr/bin/env python3
"""Do volume patterns tell the future winners among the top-ranked stocks?

Every weekly decision since 2010: the top 20 stocks by the live weekly rank sum
(point-in-time S&P list, must beat SPY). For each, volume features at the decision
close and the next 20-session return (from the next close, as traded). Per week the
features are rank-correlated with the forward returns (information coefficient), and
the top-5 vs bottom-5 by each feature are compared. Writes data/volume_study.json.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import robustness as R  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, score_table  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'volume_study.json')
WIN = [(5 * i + 26, 5 * i + 21) for i in range(21)]


def fetch_volume(tickers, start):
    import yfinance as yf
    out = {}
    for k in range(0, len(tickers), 100):
        part = tickers[k:k + 100]
        df = yf.download(part, start=start, interval='1d', group_by='ticker', auto_adjust=False,
                         progress=False, threads=True)
        for t in part:
            try:
                d = df[t].dropna(subset=['Close'])
            except KeyError:
                continue
            out[t] = {ts.date().isoformat(): (float(c), float(v)) for ts, c, v in zip(d.index, d['Close'], d['Volume'])}
        R.log(f"  volume {min(k + 100, len(tickers))}/{len(tickers)}")
    return out


def spearman(a, b):
    n = len(a)
    if n < 5:
        return None
    ra = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: a[i]))}
    rb = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: b[i]))}
    d2 = sum((ra[i] - rb[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def main():
    D = R.load_data()
    P = R.prepare(D)
    cal, px = P['calendar'], P['prices']
    tickers = sorted(t for t in px if t != 'SPY')
    vol = fetch_volume(tickers, R.FROM)
    idx = {d: i for i, d in enumerate(cal)}
    fridays = [d for d in last_sessions_of_weeks(cal) if d >= R.START]
    feats = ('rising', 'accum', 'spike', 'dollar')
    obs = {f: [] for f in feats}
    per_week = []
    for d in fridays:
        k = idx[d]
        if k + 21 >= len(cal):
            break
        rows = [r for r in score_table(px, cal, k, R.LOOK, R.SKIP, WIN, 'rank', P['elig_pit']) if r[2]][:20]
        recs = []
        for t, _, _ in rows:
            v = vol.get(t)
            a, b = px[t].get(cal[k + 1]), px[t].get(cal[k + 21])
            if not v or not a or not b:
                continue
            days = [cal[j] for j in range(k - 125, k + 1) if cal[j] in v]
            if len(days) < 100:
                continue
            vv = [v[x][1] for x in days]
            cc = [v[x][0] for x in days]
            base = sum(vv[:-20]) / len(vv[:-20]) or 1
            last20 = sum(vv[-20:]) / 20
            last5 = sum(vv[-5:]) / 5
            up = sum(vv[i] for i in range(1, len(vv)) if cc[i] > cc[i - 1])
            dn = sum(vv[i] for i in range(1, len(vv)) if cc[i] < cc[i - 1]) or 1
            recs.append(dict(t=t, fwd=b / a - 1, rising=last20 / base, accum=up / dn, spike=last5 / base,
                             dollar=math.log(max(1.0, sum(vv[-63:]) / 63 * cc[-1]))))
        if len(recs) < 10:
            continue
        wk = dict(d=d)
        for f in feats:
            ic = spearman([r[f] for r in recs], [r['fwd'] for r in recs])
            srt = sorted(recs, key=lambda r: r[f])
            lo = sum(r['fwd'] for r in srt[:5]) / 5
            hi = sum(r['fwd'] for r in srt[-5:]) / 5
            wk[f] = (ic, hi - lo)
            obs[f].append((d, ic, hi - lo, hi, lo))
        per_week.append(wk)
    res = {}
    for f in feats:
        o = [x for x in obs[f] if x[1] is not None]
        ics = [x[1] for x in o]
        m = sum(ics) / len(ics)
        sd = math.sqrt(sum((x - m) ** 2 for x in ics) / (len(ics) - 1))
        # weekly observations overlap 4-week returns: t-stat deflated by sqrt(4)
        t = m / (sd / math.sqrt(len(ics))) / 2
        half = {}
        for lab, a_, b_ in (('2010-19', '2010', '2019-12-31'), ('2020-26', '2020', '2099')):
            sub = [x for x in o if a_ <= x[0] <= b_]
            half[lab] = dict(ic=round(sum(x[1] for x in sub) / len(sub), 4),
                             spread4w=round(sum(x[2] for x in sub) / len(sub), 4))
        res[f] = dict(weeks=len(o), ic=round(m, 4), t=round(t, 2), hitIc=round(sum(1 for x in ics if x > 0) / len(ics), 3),
                      spread4w=round(sum(x[2] for x in o) / len(o), 4),
                      hiAvg=round(sum(x[3] for x in o) / len(o), 4), loAvg=round(sum(x[4] for x in o) / len(o), 4),
                      halves=half)
        R.log(f"{f}: {res[f]}")
    with open(OUT, 'w') as fh:
        json.dump(dict(results=res, start=R.START, end=cal[-1]), fh, separators=(',', ':'))


if __name__ == '__main__':
    main()

"""Point-in-time S&P 500 membership from the full daily member lists, written into the engine's dataset.

The engine's own loader rebuilds past member lists by walking Wikipedia's change table back from today's list.
That table is close to complete only from 2007; before then most changes are missing, so the rebuilt lists held
companies years before they joined the index (look-ahead) and left out ones that had already left. This step
replaces those lists with the real ones:

data/sp500_history.csv      every member list from 1996 (date, comma-separated tickers; fja05680/sp500 on GitHub,
                            the "Updated" file); Wikipedia's changes after its last date are applied on top
data/sp500_renames.json     {old ticker: current ticker} for companies that only changed ticker (BLL -> BALL)
data/sp500_delisted.json.gz {key: {"bars": [[date, open, high, low, close], ...], "vol": {date: volume}}}: daily
                            dividend-adjusted prices (Tiingo) for members Yahoo no longer carries, over the time
                            they were in the index plus the lookback before; a key ending in _T marks an older
                            company whose ticker was later reused

Each stretch in the index is matched to a price series that was trading at its start and lasted to its end;
stretches with no such series (mostly bankruptcies: Enron, WorldCom, Lehman...) stay out, and the coverage is
printed.

usage: python research/backtest/membership.py <engine/data/.robust_1998-06-01.pkl>"""
import csv
import gzip
import json
import os
import pickle
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(REPO, 'data')
FROM = '1998-06-01'


def norm(t):
    return t.strip().replace('.', '-')


def member_lists(path=os.path.join(DATA, 'sp500_history.csv')):
    csv.field_size_limit(10 ** 8)
    return [(r['date'], {norm(x) for x in r['tickers'].split(',') if x.strip()}) for r in csv.DictReader(open(path))]


def intervals(lists, changes=()):
    """{ticker: [[start, end|None], ...]} from the daily lists, then the later changes (date, added, removed)."""
    iv, prev = {}, set()
    for d, s in lists:
        for t in s - prev:
            iv.setdefault(t, []).append([d, None])
        for t in prev - s:
            iv[t][-1][1] = d
        prev = s
    last = lists[-1][0]
    for d, a, x in sorted((c for c in changes if c[0] and c[0] > last), key=lambda c: c[0]):
        a, x = a and norm(a), x and norm(x)
        if x and x in prev:
            iv[x][-1][1] = d
            prev.discard(x)
        if a and a not in prev:
            iv.setdefault(a, []).append([d, None])
            prev.add(a)
    return iv


def apply(D, lists, renames, delisted, start=FROM):
    """Replace D's member intervals with the real ones; returns (D, priced spans, missing spans)."""
    bars = dict(D['bars'])
    for k, v in delisted.items():
        bars[k] = [tuple(b) for b in v['bars']]
    first = {t: bs[0][0] for t, bs in bars.items() if bs}
    last = {t: bs[-1][0] for t, bs in bars.items() if bs}
    end = max(b[0] for b in D['bench']['SPY'])
    iv, priced, missing = {}, 0, []
    for t, spans in intervals(lists, D.get('changes', ())).items():
        for s, e in spans:
            if e and e < start:
                continue
            s2, e2 = max(s, start), min(e or end, end)
            cands = [renames.get(t, t), t, t + '_T', renames.get(t, t) + '_T']
            k = next((c for c in cands if c in first and first[c] <= s2[:8] + '31' and last[c] >= e2[:7]), None)
            if k is None:   # listed after the span began (an IPO or spin-off added within its first months)
                k = next((c for c in cands if c in first and first[c] <= s2[:4] + '-12-31' and last[c] >= e2[:7]), None)
            if k is None and t in renames:   # a renamed company whose series begins later in the span (CBS's prices start
                c = renames[t]                # at its 2005 split): the rest of it; never another company's series
                k = c if c in first and s2 < first[c] < e2 and last[c] >= e2[:7] else None
                if k is not None:
                    s = first[k]
            if k is None:
                missing.append((t, s, e))
                continue
            priced += 1
            iv.setdefault(k, []).append([s if s > lists[0][0] else None, e])
    D = dict(D)
    D.update(bars=bars, iv=iv, added={}, names=sorted(set(D['names']) | set(iv)),
             extra_vol={k: v.get('vol', {}) for k, v in delisted.items()})
    return D, priced, missing


def main(path):
    D = pickle.load(open(path, 'rb'))
    lists = member_lists()
    renames = json.load(open(os.path.join(DATA, 'sp500_renames.json')))
    delisted = json.load(gzip.open(os.path.join(DATA, 'sp500_delisted.json.gz'), 'rt'))
    D, priced, missing = apply(D, lists, renames, delisted)
    pickle.dump(D, open(path, 'wb'))

    def member(ivs, d):
        return any((a is None or a <= d) and (b is None or d < b) for a, b in ivs)
    cover = []
    for y in range(2000, int(lists[-1][0][:4]) + 1, 5):
        d = f'{y}-06-01'
        real = next(s for dd, s in reversed(lists) if dd <= d)
        have = sum(1 for k, v in D['iv'].items() if member(v, d) and D['bars'][k] and D['bars'][k][0][0] <= d)
        cover.append(f'{y} {have}/{len(real)}')
    print(f'membership: {priced} index stretches priced, {len(missing)} without prices; priced members by year: ' + ', '.join(cover))


if __name__ == '__main__':
    main(sys.argv[1])

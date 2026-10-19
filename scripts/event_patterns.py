"""Weekly: what usually followed each type of market event since 2000, for the events page (data/event_patterns.json).
Information only: the plan doesn't use it.

For every type: how often the S&P 500, long Treasuries, gold, oil and the dollar were higher on the day, a month and
three months later, and the average move; which sectors usually beat the S&P 500 over the next three months; and for
the four broad groups, how it split by the S&P's trend (above or below its 200-day average) at the time. A figure is
marked as having held when it sat on the same side of the all-days figure in both 2000-2012 and 2013 on.

The hand-picked list supplies the news types. The rule types (big up/down days, VIX spikes, market-phase changes) use
every day the nightly rules would have fired since 2000, so they carry no hindsight.

    python scripts/event_patterns.py      # fetch prices, rebuild data/event_patterns.json"""
import json
import os
import sys
from bisect import bisect_left
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import events as ev  # noqa: E402
from mtl import event_types as et  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'event_patterns.json')
START, SPLIT = '2000-01-03', '2013-01-01'
H = {'day': 0, 'month': 21, 'quarter': 63}
ASSETS = {'S&P 500': 'SPY', 'Bonds': 'VUSTX', 'Gold': 'GLD', 'Oil': 'CL=F', 'Dollar': 'DX-Y.NYB'}
SECTORS = {'Tech': 'XLK', 'Financials': 'XLF', 'Energy': 'XLE', 'Utilities': 'XLU', 'Health care': 'XLV',
           'Staples': 'XLP', 'Discretionary': 'XLY', 'Industrials': 'XLI', 'Materials': 'XLB',
           'Small caps': 'IWM', 'Nasdaq 100': 'QQQ'}
EXTRA = ('GC=F', '^VIX')      # gold futures before the gold ETF (Nov 2004); the VIX for the spike rule
GOLD_ETF_FROM = '2004-11-19'
OIL_BROKEN = ('2020-04-14', '2020-05-08')   # US crude futures went negative: returns meaningless
MIN_N = 3


def fetch(start='1999-06-01'):
    import yfinance as yf
    out = {}
    for t in sorted(set(ASSETS.values()) | set(SECTORS.values()) | set(EXTRA)):
        df = yf.download(t, start=start, auto_adjust=True, progress=False)
        c = df['Close']
        c = c[t] if hasattr(c, 'columns') else c
        out[t] = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
    if len(out.get('SPY', {})) < 5000:
        raise SystemExit(f"SPY history came back short ({len(out.get('SPY', {}))} closes)")
    return out


def align(series, cal, stale=3):
    """closes on cal: the last close on or before each session, at most `stale` sessions old."""
    out = np.full(len(cal), np.nan)
    ks = sorted(series)
    j = -1
    for i, d in enumerate(cal):
        while j + 1 < len(ks) and ks[j + 1] <= d:
            j += 1
        if j >= 0 and bisect_left(cal, ks[j]) >= i - stale:
            out[i] = series[ks[j]]
    return out


class Moves:
    def __init__(self, px):
        self.cal = sorted(px['SPY'])
        cal = self.cal
        self.K = len(cal)
        self.a = {}
        for name, t in {**ASSETS, **SECTORS}.items():
            self.a[name] = align(px.get(t, {}), cal)
        if 'GC=F' in px:   # gold: the ETF where it exists, futures before
            fut = align(px['GC=F'], cal)
            self.a['Gold'] = np.where(np.array(cal) >= GOLD_ETF_FROM, self.a['Gold'], fut)
        self.switch = np.array(cal) >= GOLD_ETF_FROM
        self.oil_bad = (np.array(cal) >= OIL_BROKEN[0]) & (np.array(cal) <= OIL_BROKEN[1])
        spy = self.a['S&P 500']
        self.above = np.full(self.K, np.nan)
        cs = np.nancumsum(spy)
        for i in range(200, self.K):
            self.above[i] = spy[i] > (cs[i] - cs[i - 200]) / 200

    def ret(self, name, k, h):
        """h=0: the event day (close before -> close); else the h sessions after the event day's close."""
        i0, i1 = (k - 1, k) if h == 0 else (k, k + h)
        if i0 < 0 or i1 >= self.K:
            return np.nan
        if name == 'Oil' and (self.oil_bad[i0] or self.oil_bad[i1]):
            return np.nan
        if name == 'Gold' and self.switch[i0] != self.switch[i1]:
            return np.nan
        a = self.a[name]
        x, y = a[i0], a[i1]
        if np.isnan(x) or np.isnan(y) or x <= 0 or y <= 0:
            return np.nan
        return y / x - 1


def declump(ks, gap=21):
    out = []
    for k in sorted(ks):
        if not out or k - out[-1] >= gap:
            out.append(k)
    return out


def summary(m, ks, name, h, base):
    """{n, up, avg, held} for events at sessions ks; held: on the same side of all days in both halves."""
    def part(kk):
        v = np.array([m.ret(name, k, h) for k in kk])
        return v[~np.isnan(v)]
    v = part(ks)
    if len(v) < MIN_N:
        return None
    up = float(np.mean(v > 0))
    out = dict(n=int(len(v)), up=round(up, 3), avg=round(float(np.mean(v)), 4))
    halves = [part([k for k in ks if m.cal[k] < SPLIT]), part([k for k in ks if m.cal[k] >= SPLIT])]
    b = base[name][str(h)]['up']
    out['held'] = all(len(x) >= MIN_N for x in halves) and \
        all((np.mean(x > 0) - b) * (up - b) > 0 for x in halves) and abs(up - b) >= 0.05
    return out


def compute(doc, px, now=None):
    m = Moves(px)
    cal, K = m.cal, m.K
    first = bisect_left(cal, START)
    base = {}
    for name in ASSETS:
        base[name] = {}
        for h in H.values():
            v = np.array([m.ret(name, k, h) for k in range(max(first, 1), K)])
            v = v[~np.isnan(v)]
            base[name][str(h)] = dict(up=round(float(np.mean(v > 0)), 3), avg=round(float(np.mean(v)), 4), n=int(len(v)))

    # news types from the list; rule types from every day the nightly rules would have fired since 2000
    by_type = {}
    for e in doc['events']:
        t = e.get('type') or et.classify(e)
        if t in et.RULE_TYPES or et.group(t) in ('Hindsight', 'Other'):
            continue
        k = bisect_left(cal, e['d'])
        if 1 <= k < K:
            by_type.setdefault(t, []).append(k)
    hist = []
    spy = [px['SPY'][d] for d in cal]
    ev.auto(hist, cal, spy, px.get('^VIX', {}), [], since=START)
    for e in hist:
        t = et.classify(dict(e, what=e['what'].split(':')[0]))
        k = bisect_left(cal, e['d'])
        if t in et.RULE_TYPES and 1 <= k < K:
            by_type.setdefault(t, []).append(k)

    def block(ks):
        out = dict(n=len(ks), clusters=len(declump(ks)), first=cal[min(ks)], last=cal[max(ks)], assets={})
        for name in ASSETS:
            out['assets'][name] = {lab: summary(m, ks, name, h, base) for lab, h in H.items()}
        return out

    types = {}
    for t in et.TYPES:
        ks = sorted(set(by_type.get(t, [])))
        if len(ks) < MIN_N:
            continue
        b = block(ks)
        sect = []
        for s in SECTORS:
            pairs = [(m.ret(s, k, 63), m.ret('S&P 500', k, 63), k) for k in ks]
            pairs = [(x - y, k) for x, y, k in pairs if not (np.isnan(x) or np.isnan(y))]
            if len(pairs) >= 5:
                ex = np.array([p[0] for p in pairs])
                halves = [np.array([x for x, k in pairs if (cal[k] < SPLIT) == lo]) for lo in (True, False)]
                beat = float(np.mean(ex > 0))
                held = all(len(x) >= MIN_N for x in halves) and all((np.mean(x > 0) - 0.5) * (beat - 0.5) > 0 for x in halves)
                sect.append(dict(name=s, avg=round(float(ex.mean()), 4), beat=round(beat, 3), n=len(ex), held=bool(held)))
        sect.sort(key=lambda x: -x['avg'])
        b['sectors'] = sect
        b['group'] = et.group(t)
        types[t] = b

    groups = {}
    for g in et.GROUP_NAME:
        ks = sorted({k for t, kk in by_type.items() if et.group(t) == g for k in kk})
        if len(ks) < MIN_N:
            continue
        b = block(ks)
        for lab, want in (('above200', 1.0), ('below200', 0.0)):
            sub = [k for k in ks if m.above[k - 1] == want]
            b[lab] = {lab2: summary(m, sub, 'S&P 500', h, base) for lab2, h in (('month', 21), ('quarter', 63))}
        groups[g] = b
    return dict(about='What usually followed each type of market event since 2000 (scripts/event_patterns.py). Information only.',
                updated=(now or datetime.now(timezone.utc)).isoformat(timespec='seconds'), start=START, split=SPLIT,
                baseline=base, types=types, groups=groups)


def load(path=OUT):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return None


def stale(path=OUT, days=7):
    doc = load(path)
    if not doc:
        return True
    t = datetime.fromisoformat(doc['updated'])
    return (datetime.now(timezone.utc) - t).days >= days


def save(doc, path=OUT):
    with open(path, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')


def main():
    doc = ev.load()
    out = compute(doc, fetch())
    save(out)
    print(f"wrote {OUT}: {len(out['types'])} types, {len(out['groups'])} groups")


if __name__ == '__main__':
    main()

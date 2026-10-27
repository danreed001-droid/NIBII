"""Dominoes (mtl/dominoes.py): what had fallen before past S&P falls, how deep they went, and past times like now."""
from datetime import date, timedelta

import numpy as np

from mtl import dominoes as dm


def sessions(n, start='1990-01-01'):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_falls_run_from_the_top_to_a_new_one_year_high():
    up = list(np.linspace(100, 120, 300))
    path = up + list(np.linspace(120, 110.4, 20)) + list(np.linspace(110.4, 125, 40)) + list(np.linspace(125, 93.75, 60))
    spx = np.array(path)
    F = dm.falls(spx, dm.off_high(spx), start=260)
    assert [round(f['depth'], 3) for f in F] == [-0.08, -0.25]
    assert F[0]['top'] == 299 and not F[0]['open'] and F[1]['open']        # the second has no new high yet


def test_readings_mark_each_domino_against_its_line():
    cal = sessions(600)
    flat = lambda v=100.0: {d: v for d in cal}
    ser = dict(tech=flat(), small=flat(), banks=flat(), junk=flat(),
               transport={d: (100.0 if i < 500 else 88.0) for i, d in enumerate(cal)},       # 12% under its high
               fed={d: (1.0 if i < 400 else 2.5) for i, d in enumerate(cal)},                # up 1.5 points in a year
               curve={d: (0.5 if i != 450 else -0.1) for i, d in enumerate(cal)},            # one inverted day
               oil={d: (50.0 if i < 400 else 80.0) for i, d in enumerate(cal)})               # up 60% in a year
    r, on = dm.readings(cal, ser)
    keys = [k for k, *_ in dm.DOMINOES]
    assert [k for k, x in zip(keys, on[-1]) if x] == ['transport', 'fed', 'curve', 'oil']
    assert round(r['transport'][-1], 2) == -0.12 and r['fed'][-1] == 1.5 and r['curve'][-1] == -0.1
    assert not on[100].any()                                               # unknown before a year of history


def test_matches_take_the_closest_days_once_per_six_months_and_only_finished_ones():
    n = 2000
    feats = np.zeros((n, 9), int)
    feats[300:320, 0] = 1; feats[900:905, 0] = 1; feats[1950:, 0] = 1                 # tech down then, and now
    off = np.full(n, -0.02)
    ok = np.ones(n, bool)
    m = dm.matches(n - 1, feats, off, ok, start=0, k=3)
    assert m[:2] == [300, 900] and all(j <= n - 1 - dm.H6 for j in m)               # not the last six months
    assert all(abs(a - b) >= dm.H6 for a in m for b in m if a != b)


def test_build_reads_now_counts_past_falls_and_lists_what_followed():
    cal = sessions(3300)
    t = np.arange(3300)
    spx = 100 * np.exp(0.0003 * t)
    spx[1500:1600] *= np.linspace(1, 0.7, 100)                       # a 30% fall with banks and junk bonds cracking first
    spx[1600:] *= 0.7
    banks = 100 * np.exp(0.0003 * t)
    banks[1450:] *= 0.8
    junk = np.full(3300, 100.0)
    junk[1450:] = 95.0
    oil = np.full(3300, 50.0)
    oil[3200:] = 80.0                                                 # an oil shock now
    cpi = {f'{y}-{m:02d}-01': 100 * 1.02 ** (y - 1989 + m / 12) for y in range(1989, 2004) for m in range(1, 13)}
    ser = dict(spx=dict(zip(cal, spx)), tech=dict(zip(cal, spx)), small=dict(zip(cal, spx)), banks=dict(zip(cal, banks)),
               transport=dict(zip(cal, banks)), junk=dict(zip(cal, junk)), fed={d: 3.0 for d in cal},   # 3 down first
               curve={d: 1.0 for d in cal}, oil=dict(zip(cal, oil)), cpi=cpi, bonds={d: 100.0 for d in cal})
    ctx = [(cal[1440], 'Credit cracking'), (cal[100], 'Too old to show')]
    D = dm.build(cal, ser, ctx, k=3)
    assert D['asOf'] == cal[-1] and D['count'] == 1 and [x['key'] for x in D['dominoes'] if x['on']] == ['oil']
    assert sum(r['falls'] for r in D['table']) == D['falls'] and D['split']['high']['deep'] >= 1
    assert D['matches'] and all(m['d'] <= cal[-1 - dm.H6] for m in D['matches'])
    assert D['matches'][0]['next']['gold6'] is None and D['matches'][0]['next']['bonds6'] == 0.0
    assert dm.build(cal[:500], {k: {d: v for d, v in s.items() if d <= cal[499]} if isinstance(s, dict) else s
                                for k, s in ser.items()}) is None

"""News forward test (information only): fixed guesses about what follows each day's news, written down each night
before the next session opens and scored only on the sessions that come after (data/news_forward.json).

Why forward: a look back at the news log (Aug 5 - Oct 30, 2026: 102 tests on 62 sessions, 8 passing p<0.05 where ~5
pass by luck) and at the events list since 2000 found nothing that held up. The look back can't be trusted with
hand-picked news written after the fact; a guess logged before the outcome can. The guesses below were fixed on
Oct 31, 2026 from that look back and stay unchanged, so every case counted is out of sample.

Each night (scripts/news_forward.py, after the evening news sync): the entries in data/news_log.json that the market
could first react to at today's close (after-hours and weekend items go to the next session), today's moves, and
each guess that fires writes one call: an asset, a horizon in sessions and a direction (or "a bigger move than
usual"). A call is never rewritten; entries added for that day later don't change it. A missed night is not filled
in afterwards. Scoring compares the close `h` sessions later with the day's close.

A guess holds up only if its hit rate beats a coin flip with p < 0.05 / (number of guesses) after at least MIN_N
calls: with this many guesses, one passing p < 0.05 by luck is likely. Nothing here changes the plan.

Pure and network-free: entries, prices and the clock in, the log dict out."""
from bisect import bisect_left
from datetime import datetime, timezone
from math import comb

VERSION = 1
STARTED = '2026-10-31'
MIN_N = 20
ASSETS = ('SPY', 'QQQ', 'GLD', 'TLT')
NAMES = {'SPY': 'S&P 500', 'QQQ': 'Nasdaq-100', 'GLD': 'Gold', 'TLT': 'Long Treasuries'}
AFTER = {'After-hours', 'After close', 'Weekend', 'Weekend / holiday'}
DIR = {'Bullish': 1, 'Bearish': -1}
IMP = {'High': 2, 'Medium': 1, 'Low': 0.5}
BUSY = 6            # entries in a day
BIG_DROP = -0.015   # S&P close-to-close


def _fed(x):
    c = (x.get('category') or '').lower()
    return any(k in c for k in ('fed', 'rate', 'central'))


def features(entries, moves):
    """The day's read: impact-weighted tone (bullish +, bearish -), entry count, high-impact bearish count, any
    bearish Fed/rates item, and the day's close-to-close moves {ticker: return}."""
    return dict(tone=sum(DIR.get(x.get('direction'), 0) * IMP.get(x.get('impact'), 1) for x in entries),
                n=len(entries),
                bear_hi=sum(1 for x in entries if x.get('direction') == 'Bearish' and x.get('impact') == 'High'),
                fed_bear=any(_fed(x) and x.get('direction') == 'Bearish' for x in entries),
                **{f'r_{t}': moves.get(t) for t in ASSETS})


def _sgn(v):
    return (v > 0) - (v < 0)


# id, plain wording, asset, horizon (sessions), call(features) -> +1 up / -1 down / 'big' / None (no call)
GUESSES = (
    ('tone_tlt', 'Upbeat news day → long Treasuries lower the next day (downbeat → higher)', 'TLT', 1,
     lambda f: -_sgn(f['tone']) or None),
    ('tone_gld', 'Upbeat news day → gold lower the next day (downbeat → higher)', 'GLD', 1,
     lambda f: -_sgn(f['tone']) or None),
    ('tone_spy', 'The news tone carries into the S&P 500 the next day', 'SPY', 1,
     lambda f: _sgn(f['tone']) or None),
    ('tone_qqq', 'The news tone carries into the Nasdaq-100 over the next 2 days', 'QQQ', 2,
     lambda f: _sgn(f['tone']) or None),
    ('shrug', 'Downbeat news but the S&P 500 rose anyway → S&P higher over the next week', 'SPY', 5,
     lambda f: 1 if f['tone'] < 0 and (f['r_SPY'] or 0) > 0 else None),
    ('pile_tlt', '2+ high-impact bearish items → long Treasuries higher over the next week', 'TLT', 5,
     lambda f: 1 if f['bear_hi'] >= 2 else None),
    ('pile_qqq', '2+ high-impact bearish items → Nasdaq-100 lower the next day', 'QQQ', 1,
     lambda f: -1 if f['bear_hi'] >= 2 else None),
    ('fed_bear', 'Bearish Fed or rates news → S&P 500 lower the next day', 'SPY', 1,
     lambda f: -1 if f['fed_bear'] else None),
    ('bounce', 'S&P 500 down 1.5%+ on a day with high-impact bearish news → S&P higher the next day', 'SPY', 1,
     lambda f: 1 if (f['r_SPY'] or 0) <= BIG_DROP and f['bear_hi'] >= 1 else None),
    ('busy', f'Busy news day ({BUSY}+ items) → a bigger S&P 500 move the next day than its typical day', 'SPY', 1,
     lambda f: 'big' if f['n'] >= BUSY else None),
)


def react_index(cal, d, tm):
    """Index in `cal` of the first session whose close can carry an item dated `d` at time `tm`, or None."""
    k = bisect_left(cal, d)
    if tm in AFTER and k < len(cal) and cal[k] == d:
        k += 1
    return k if k < len(cal) else None


def entries_for(news, cal, day):
    """The news-log entries (their 'data' dicts) the market first reacts to at `day`'s close. `cal` must run past
    `day` (the next session included) so after-hours items land on the next session, not this one."""
    i = cal.index(day)
    return [x for x in news if react_index(cal, x.get('date', ''), x.get('time', '')) == i]


def new_doc():
    return dict(version=VERSION, started=STARTED, minN=MIN_N,
                guesses=[dict(id=g, text=t, asset=a, h=h) for g, t, a, h, _ in GUESSES], calls=[], days=[])


def write(doc, day, entries, moves, typical, at=None):
    """Log `day`'s calls once. `moves`: {ticker: that day's return}; `typical`: the S&P's median absolute daily move
    over the 20 sessions before (for 'busy'). Returns the calls added ([] when the day was already logged)."""
    if any(d['d'] == day for d in doc['days']):
        return []
    f = features(entries, moves)
    at = at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    out = []
    for g, _, a, h, rule in GUESSES:
        c = rule(f)
        if c is None:
            continue
        call = dict(d=day, id=g, asset=a, h=h, call=c, at=at)
        if c == 'big':
            call['typical'] = round(typical, 5)
        out.append(call)
    doc['calls'].extend(out)
    doc['days'].append(dict(d=day, at=at, n=f['n'], tone=f['tone'], bearHi=f['bear_hi'], fedBear=f['fed_bear'],
                            calls=len(out)))
    return out


def score(doc, closes):
    """Fill in each open call whose result is now known. closes: {ticker: {date: close}} (one consistent series per
    ticker). Returns how many were scored."""
    k = 0
    for c in doc['calls']:
        if 'hit' in c:
            continue
        ser = closes.get(c['asset']) or {}
        cal = sorted(ser)
        if c['d'] not in ser:
            continue
        i = cal.index(c['d'])
        if i + c['h'] >= len(cal):
            continue
        r = ser[cal[i + c['h']]] / ser[c['d']] - 1
        c['res'] = round(r, 5)
        c['hit'] = abs(r) > c['typical'] if c['call'] == 'big' else (r > 0) == (c['call'] > 0) and r != 0
        k += 1
    return k


def sign_p(k, n):
    """Two-sided: the chance of a record this far from half by coin flips."""
    if not n:
        return 1.0
    lo = min(k, n - k)
    return min(1.0, 2 * sum(comb(n, i) for i in range(lo + 1)) / 2 ** n)


def summary(doc):
    """Per guess: calls, scored, hits, hit rate, p, the average move in the called direction, and a verdict."""
    bar = 0.05 / len(doc['guesses'])
    out = []
    for g in doc['guesses']:
        cs = [c for c in doc['calls'] if c['id'] == g['id']]
        done = [c for c in cs if 'hit' in c]
        hits = sum(1 for c in done if c['hit'])
        n = len(done)
        p = sign_p(hits, n)
        dirn = [c['res'] * c['call'] for c in done if c['call'] != 'big']
        verdict = ('too few' if n < doc.get('minN', MIN_N) else
                   'holding up' if p < bar and hits > n / 2 else
                   'the reverse is holding up' if p < bar else 'no edge so far')
        out.append(dict(id=g['id'], text=g['text'], asset=g['asset'], h=g['h'], calls=len(cs), n=n, hits=hits,
                        rate=round(hits / n, 3) if n else None, p=round(p, 4),
                        avg=round(sum(dirn) / len(dirn), 5) if dirn else None, verdict=verdict))
    return dict(bar=bar, rows=out)

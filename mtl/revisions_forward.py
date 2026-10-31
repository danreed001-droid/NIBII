"""Analyst-revisions forward test (information only): do the strongest stocks with the biggest rises in analysts'
earnings estimates go on to beat the others? (data/revisions_forward.json, shown on docs/forward.html)

The scanner logs, each signal Friday, the estimate revisions of the top 25 ranked stocks (mtl/revisions.py,
data/revisions_log.json), written at the time, so every logged Friday is a guess made before the outcome. Three
guesses, fixed on Oct 31, 2026, each scored once per Friday over the next 20 sessions (about 4 weeks) from that
Friday's close:
  top25     the half of the 25 with the bigger 90-day rise in this year's estimate beats the other half (equal weight)
  top10     the same within the top 10 ranked (where the plan picks from): the 5 with bigger rises beat the other 5
  cut       stocks whose estimates were cut (90-day change below zero, or more analysts cutting than raising in the
            last 30 days) trail the S&P 500 (fires only on Fridays with any)
A guess holds up only after MIN_N scored Fridays with p < 0.05 / 3. Revisions and price strength are fairly separate
reasons, which is why this is worth checking; nothing here changes the plan.

Pure and network-free: the log and closes in, a dict out."""
from mtl.news_forward import sign_p

STARTED = '2026-10-31'
MIN_N = 20
H = 20
GUESSES = (
    ('top25', 'Of the top 25 ranked stocks, the half with the bigger rise in analysts\' estimates beats the other half over the next 4 weeks'),
    ('top10', 'Of the top 10 ranked, the 5 with the bigger rise in estimates beat the other 5 over the next 4 weeks'),
    ('cut', 'Ranked stocks whose estimates were cut trail the S&P 500 over the next 4 weeks'),
)


def _cut(r):
    return (r.get('eps90') is not None and r['eps90'] < 0) or (r.get('down30') or 0) > (r.get('up30') or 0)


def _fwd(ser, d):
    """Return from `d`'s close to the close H sessions later, or None (not yet, or no price)."""
    if not ser or d not in ser:
        return None
    cal = sorted(ser)
    i = cal.index(d)
    return ser[cal[i + H]] / ser[d] - 1 if i + H < len(cal) else None


def _halves(rows):
    """(bigger-rise half, smaller-rise half) of [(ticker, reading)], by the 90-day estimate change."""
    xs = sorted((r for r in rows if r[1].get('eps90') is not None), key=lambda r: -r[1]['eps90'])
    k = len(xs) // 2
    return xs[:k], xs[k:]


def week(d, readings, closes):
    """One Friday's three calls: {id: {n_a, n_b, a, b, edge, hit} or None (didn't fire or not scored yet)}."""
    rows = sorted(readings.items(), key=lambda kv: kv[1].get('rank') or 99)
    out = {}

    def avg(grp):
        rs = [r for r in (_fwd(closes.get(t), d) for t, _ in grp) if r is not None]
        return (sum(rs) / len(rs), len(rs)) if rs else (None, 0)

    for gid, grp in (('top25', rows), ('top10', [r for r in rows if (r[1].get('rank') or 99) <= 10])):
        a, b = _halves(grp)
        if not a or not b:
            out[gid] = None
            continue
        (ra, na), (rb, nb) = avg(a), avg(b)
        out[gid] = dict(waiting=True, n_a=len(a), n_b=len(b)) if ra is None or rb is None else \
            dict(n_a=na, n_b=nb, a=round(ra, 5), b=round(rb, 5), edge=round(ra - rb, 5), hit=ra > rb)
    cuts = [r for r in rows if _cut(r[1])]
    spy = _fwd(closes.get('SPY'), d)
    if not cuts:
        out['cut'] = None
    else:
        rc, nc = avg(cuts)
        out['cut'] = dict(waiting=True, n_a=len(cuts)) if rc is None or spy is None else \
            dict(n_a=nc, a=round(rc, 5), b=round(spy, 5), edge=round(spy - rc, 5), hit=rc < spy,
                 names=[t for t, _ in cuts])
    return out


def build(log, closes, asof=None):
    """{started, minN, h, guesses, weeks: [{d, calls}], summary: {bar, rows}} from the revisions log and closes
    ({ticker: {date: close}}, SPY included)."""
    weeks = [dict(d=d, calls=week(d, log[d], closes)) for d in sorted(log) if d >= '2026-10-01']
    bar = 0.05 / len(GUESSES)
    rows = []
    for gid, text in GUESSES:
        cs = [w['calls'][gid] for w in weeks if w['calls'].get(gid)]
        done = [c for c in cs if 'hit' in c]
        hits = sum(1 for c in done if c['hit'])
        n = len(done)
        p = sign_p(hits, n)
        rows.append(dict(id=gid, text=text, calls=len(cs), n=n, hits=hits, rate=round(hits / n, 3) if n else None,
                         p=round(p, 4), avg=round(sum(c['edge'] for c in done) / n, 5) if n else None,
                         verdict='too few' if n < MIN_N else 'holding up' if p < bar and hits > n / 2 else
                         'the reverse is holding up' if p < bar else 'no edge so far'))
    return dict(asOf=asof, started=STARTED, minN=MIN_N, h=H, guesses=[dict(id=g, text=t) for g, t in GUESSES],
                weeks=weeks, summary=dict(bar=bar, rows=rows))

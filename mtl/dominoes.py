"""Dominoes (information only): what had already fallen before past S&P 500 falls, and past times like now.

Eight dominoes, each down or not (lines fixed from the 2000, 2008, 2020 and 2022 domino charts, not fitted):
  tech, small caps, banks, transports   10%+ under their 1-year highs (Nasdaq composite, Russell 2000, Fidelity Select
                                        Banking and Transportation funds: long histories, back to 1986-87)
  junk bonds                            3%+ under its 1-year high (Vanguard high-yield fund)
  Fed raising rates                     the Fed funds rate 1 point+ above a year earlier
  yield curve                           the 10-year yield under the 3-month rate at any time in the last year
  oil                                   oil (WTI) 50%+ above a year earlier

A fall: the S&P 500 closing 5%+ under its highest close of the last year; it lasts until a new 1-year high, and its
depth is the lowest close in that time against the top. Research (Oct 2026), 52 falls since 1988: on the day the S&P
first closed 5% under its top, falls with 0-2 dominoes down never went to -20% (0 of 38); with 3 or more, 6 of 14 did.

What to expect: what followed past days with the same number of dominoes down and the S&P about as far from its
high (expect()), as a typical move and a range at 1, 3 and 6 months. History, not a promise.

Past times like now: the closest past days on the eight dominoes, inflation above or below 3% and the S&P's distance
from its high (one per stretch of six months, only days whose next six months are known), and what followed. As a
forecast these matches did no better than the normal rate; evaluate() redoes that check on every run.

Pure and network-free: series in, a dict for data/dominoes.json out."""
from bisect import bisect_left
from datetime import date

import numpy as np

from mtl.macro_events import FRED_STALE, published, yoy_monthly

LOOK, H6, H12 = 252, 126, 252
DOMINOES = [  # key, label, how it is read, line
    ('tech', 'Tech', 'off', 0.10), ('small', 'Small caps', 'off', 0.10), ('banks', 'Banks', 'off', 0.10),
    ('transport', 'Transports', 'off', 0.10), ('junk', 'Junk bonds', 'off', 0.03),
    ('fed', 'Fed raising rates', 'fed', 1.0), ('curve', 'Inverted yield curve', 'curve', 0.0),
    ('oil', 'Oil shock', 'oil', 0.5)]
INFL_HIGH = 0.03
DEEP = 0.195        # a bear market: 1990 and 2018 stopped at -19.9% / -19.8%


def line(cal, series, stale=5):
    """{date: value} on cal as an array: the last value on or before each session, NaN when older than `stale`."""
    ks = sorted(series)
    out, j = np.full(len(cal), np.nan), -1
    for i, d in enumerate(cal):
        while j + 1 < len(ks) and ks[j + 1] <= d:
            j += 1
        if j >= 0 and bisect_left(cal, ks[j]) >= i - stale:
            out[i] = series[ks[j]]
    return out


def off_high(a, look=LOOK):
    out = np.full(len(a), np.nan)
    for i in range(look - 1, len(a)):
        w = a[i - look + 1:i + 1]
        if np.isfinite(a[i]) and np.isfinite(w).sum() >= look // 2:
            out[i] = a[i] / np.nanmax(w) - 1
    return out


def ago(a, n=LOOK):
    out = np.full(len(a), np.nan)
    out[n:] = a[:-n]
    return out


def readings(cal, ser):
    """{key: array} of each domino's reading, and the (N x 8) on/off table (False where unknown)."""
    r = {k: off_high(line(cal, ser.get(k) or {})) for k, _, how, _ in DOMINOES if how == 'off'}
    fed = line(cal, ser.get('fed') or {}, stale=FRED_STALE)          # the Fed's daily series run days behind
    r['fed'] = fed - ago(fed)
    curve = line(cal, ser.get('curve') or {}, stale=FRED_STALE)
    r['curve'] = np.array([np.nanmin(curve[max(0, i - LOOK + 1):i + 1]) if np.isfinite(curve[max(0, i - LOOK + 1):i + 1]).any()
                           else np.nan for i in range(len(cal))])
    oil = line(cal, ser.get('oil') or {}, stale=FRED_STALE)          # oil: often a week or more
    r['oil'] = oil / ago(oil) - 1
    on = np.column_stack([(r[k] <= -ln) if how == 'off' else (r[k] >= ln) if how in ('fed', 'oil') else (r[k] < ln)
                          for k, _, how, ln in DOMINOES])
    return r, on & np.isfinite(np.column_stack([r[k] for k, *_ in DOMINOES]))


def falls(spx, spx_off, start, thr=0.05):
    """Every fall: {top, trig, trough, end, depth, open} as session indexes."""
    out, i, n = [], start, len(spx)
    while i < n:
        if spx_off[i] <= -thr:
            w0 = max(0, i - LOOK + 1)
            top = w0 + int(np.argmax(spx[w0:i + 1]))
            j = i + 1
            while j < n and spx[j] < spx[j - LOOK + 1:j].max():
                j += 1
            end = min(j, n - 1)
            tr = i + int(np.argmin(spx[i:end + 1]))
            out.append(dict(top=top, trig=i, trough=tr, end=end, depth=float(spx[tr] / spx[top] - 1), open=j >= n))
            i = j + 1
        else:
            i += 1
    return [f for f in out if f['top'] >= start]


def _ret(a, i, n):
    j = i + n
    return float(a[j] / a[i] - 1) if j < len(a) and np.isfinite(a[i]) and np.isfinite(a[j]) and a[i] > 0 else None


def matches(t, feats, off, ok, start, k=5, w_off=0.05):
    """The k closest past days to session t: same dominoes and inflation side count 1 each per difference, the S&P's
    distance from its high 1 per 5 points; one per six months; only days whose next six months are known by t."""
    js = np.arange(start, t - H6)
    js = js[ok[js]]
    if not len(js):
        return []
    dist = np.abs(feats[js] - feats[t]).sum(1) + np.abs(off[js] - off[t]) / w_off
    pick = []
    for j in js[np.argsort(dist, kind='stable')]:
        if all(abs(j - p) >= H6 for p in pick):
            pick.append(int(j))
        if len(pick) == k:
            break
    return pick


def evaluate(spx, feats, off, ok, start, cal, since='2000-01-01', k=5):
    """The check behind the page's note: each month-end from `since`, the chance of a 10%+ S&P fall within six months
    from the k matches against the normal rate so far; Brier scores (lower is better) and how well each ranks the
    months that did fall (AUC, 0.5 = coin flip), with the domino count alone for comparison."""
    n = len(spx)
    fall6 = np.full(n, np.nan)
    for i in range(n - H6):
        fall6[i] = spx[i + 1:i + H6 + 1].min() / spx[i] - 1
    rows = []
    for t in range(bisect_left(cal, since), n - H6, 21):
        if not ok[t]:
            continue
        m = matches(t, feats, off, ok, start, k)
        past = fall6[start:t - H6]
        past = past[np.isfinite(past)]
        if len(m) < k or not len(past):
            continue
        rows.append((np.mean(fall6[m] <= -0.10), np.mean(past <= -0.10), float(fall6[t] <= -0.10), feats[t, :len(DOMINOES)].sum()))
    if len(rows) < 24:
        return None
    r = np.array(rows)
    y = r[:, 2]

    def auc(s):
        pos, neg = s[y == 1], s[y == 0]
        return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg]))
    if y.min() == y.max():           # every month the same way: nothing to rank
        return None
    return dict(n=len(r), since=since, rate=round(float(y.mean()), 3), brier=round(float(np.mean((r[:, 0] - y) ** 2)), 3),
                brierNormal=round(float(np.mean((r[:, 1] - y) ** 2)), 3), auc=round(auc(r[:, 0]), 3),
                aucCount=round(auc(r[:, 3]), 3))


def expect(spx, score, spx_off, known, start, bonds=None, gold=None, band=0.05):
    """What followed days like the last one: the same number of dominoes down (4+ together) and the S&P within `band`
    of the same distance from its 1-year high. For 1, 3 and 6 months: the S&P's typical (median) move, the range 8 in
    10 of those days fell in, how often it was higher, and how often it fell 5% / 10% at some point on the way; bonds'
    and gold's typical moves. Also the same for every day at that distance from the high, and for the other side of
    the 3-domino line, to compare. Overlapping days are counted, so `stretches` gives how many separate runs they make."""
    n, t = len(spx), len(spx) - 1
    lo, hi = spx_off[t] - band, min(0.0, spx_off[t] + band)
    near = known & (spx_off >= lo) & (spx_off <= hi)
    near[:start] = False
    bucket = lambda c: np.minimum(c, 4)
    same = near & (bucket(score) == bucket(score[t]))
    other = near & ((score >= 3) if score[t] < 3 else (score <= 2))

    def stats(mask):
        ix = np.flatnonzero(mask[:t])
        if len(ix) < 20:
            return None
        out = dict(days=int(len(ix)), stretches=int(1 + np.sum(np.diff(ix) > 21)))
        for lab, h in (('1', 21), ('3', 63), ('6', 126)):
            jx = ix[ix + h < n]
            if len(jx) < 20:
                out[lab] = None
                continue
            r = spx[jx + h] / spx[jx] - 1
            w = np.array([np.min(spx[i + 1:i + h + 1]) for i in jx]) / spx[jx] - 1
            row = dict(med=float(np.median(r)), p10=float(np.percentile(r, 10)), p90=float(np.percentile(r, 90)),
                       up=float(np.mean(r > 0)), fall5=float(np.mean(w <= -0.05)), fall10=float(np.mean(w <= -0.10)))
            for k_, a in (('bonds', bonds), ('gold', gold)):
                if a is not None:
                    x = a[jx + h] / a[jx] - 1
                    x = x[np.isfinite(x)]
                    row[k_] = float(np.median(x)) if len(x) >= 20 else None
            out[lab] = {k_: (None if v is None else round(v, 4)) for k_, v in row.items()}
        return out
    return dict(count=int(bucket(score[t])), lo=round(float(lo), 4), hi=round(float(hi), 4), same=stats(same),
                all=stats(near), other=stats(other), otherLabel='3+' if score[t] < 3 else '0-2')


def _month(d):
    return date.fromisoformat(d).strftime('%b %Y')


def build(cal, ser, context=(), k=5):
    """The dominoes block for data/dominoes.json. cal: S&P 500 sessions; ser: {key: {date: value}} for 'spx', the
    eight dominoes' inputs ('tech', 'small', 'banks', 'transport', 'junk', 'fed', 'curve', 'oil'), 'cpi' (monthly
    index) and, for what followed, 'bonds' and 'gold'; context: [(date, text)] of signals and events to show under each
    past match. Returns None without enough history."""
    n = len(cal)
    spx = line(cal, ser.get('spx') or {})
    if n < 3 * LOOK or not np.isfinite(spx[-1]):
        return None
    spx_off = off_high(spx)
    r, on = readings(cal, ser)
    score = on.sum(1)
    infl = line(cal, published(yoy_monthly(ser.get('cpi') or {}), 14), stale=40)
    known = np.isfinite(np.column_stack([r[k_] for k_, *_ in DOMINOES])).all(1) & np.isfinite(spx_off)
    start = int(np.argmax(known)) if known.any() else n
    ok = known & np.isfinite(infl)
    feats = np.column_stack([on.astype(int), (infl >= INFL_HIGH).astype(int)])
    t = n - 1

    F = falls(spx, spx_off, start)
    table = []
    for lab, lo, hi in (('0', 0, 0), ('1', 1, 1), ('2', 2, 2), ('3', 3, 3), ('4+', 4, 8)):
        g = [-f['depth'] for f in F if lo <= score[f['trig']] <= hi]
        table.append(dict(dominoes=lab, falls=len(g), to10=sum(x >= 0.10 for x in g), to20=sum(x >= DEEP for x in g),
                          to30=sum(x >= 0.30 for x in g)))
    split = {lab: dict(falls=sum(1 for f in F if lo <= score[f['trig']] <= hi),
                       deep=sum(1 for f in F if lo <= score[f['trig']] <= hi and -f['depth'] >= DEEP))
             for lab, lo, hi in (('low', 0, 2), ('high', 3, 8))}

    assets = {'spx': spx, 'bonds': line(cal, ser.get('bonds') or {}), 'gold': line(cal, ser.get('gold') or {})}
    ctx = sorted(context)
    past = []
    for j in (matches(t, feats, spx_off, ok, start, k) if ok[t] else []):
        lo = bisect_left([c[0] for c in ctx], date.fromordinal(date.fromisoformat(cal[j]).toordinal() - 365).isoformat())
        then = [f"{w} ({_month(d)})" for d, w in ctx[lo:] if d <= cal[j]][-4:][::-1]
        nxt = dict(fall6=round(float(np.nanmin(spx[j + 1:j + H6 + 1]) / spx[j] - 1), 4))
        for a, arr in assets.items():
            for lab, h in (('6', H6), ('12', H12)):
                x = _ret(arr, j, h)
                nxt[f'{a}{lab}'] = None if x is None else round(x, 4)
        past.append(dict(d=cal[j], on=[DOMINOES[i][0] for i in range(len(DOMINOES)) if on[j, i]],
                         infl=None if not np.isfinite(infl[j]) else round(float(infl[j]), 4),
                         spxOff=round(float(spx_off[j]), 4), then=then, next=nxt))
    fall6_all = [np.nanmin(spx[i + 1:i + H6 + 1]) / spx[i] - 1 for i in range(start, n - H6)]
    now = [dict(key=k_, label=lab, on=bool(on[t, i]), value=None if not np.isfinite(r[k_][t]) else round(float(r[k_][t]), 4),
                line=ln, how=how) for i, (k_, lab, how, ln) in enumerate(DOMINOES)]
    return dict(asOf=cal[t], spxOff=round(float(spx_off[t]), 4), count=int(score[t]), dominoes=now,
                infl=None if not np.isfinite(infl[t]) else round(float(infl[t]), 4), inflHigh=INFL_HIGH,
                since=cal[start] if start < n else None, falls=len(F), table=table, split=split,
                normal10=round(float(np.mean(np.array(fall6_all) <= -0.10)), 3) if fall6_all else None,
                matches=past, test=evaluate(spx, feats, spx_off, ok, start, cal, k=k),
                expect=expect(spx, score, spx_off, known, start, assets['bonds'], assets['gold']) if known[t] else None)

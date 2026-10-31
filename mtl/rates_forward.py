"""Rates model forward test (information only): each month-end, a model of the 10-year Treasury yield picks where to be
for the next month - SPY, gold (GLD), long Treasuries (TLT) or cash - and the pick is scored a month later against a
plan-style rule and SPY held throughout (data/rates_forward.json, docs/forward.html).

Why forward: in a walk-forward search of 3,303 combinations of 27 market series (Oct 31, 2026), combinations with the
10-year yield beat the plan-style rule in both 2008-2017 and 2017-2026 far more often than any other series (39% vs
1-12%), but that was spotted by looking at both halves, and in the untouched 2005-2008 it was no better than the rest.
So it is fixed here and scored only on months to come.

The model, fixed on Oct 31, 2026: three inputs at each month-end (the 10-year yield, its change over 63 sessions, and
the curve: 10-year minus 3-month yield); for each of SPY, GLD and TLT a ridge regression (inputs standardised on the
training months, penalty ALPHA x the number of months) of the next month's return on those inputs, fitted on every
earlier month-end whose next month is complete; the pick is the asset with the best predicted return, or cash when
none beats a month of the 3-month T-bill rate. The plan-style rule: SPY while it closes above its 150-session
average, else the stronger of GLD and TLT over 63 sessions.

Pure and network-free: closes in, the log dict out."""
from bisect import bisect_right
from functools import reduce

STARTED = '2026-10-31'
ASSETS = ('SPY', 'GLD', 'TLT')
ALPHA = 1.0
MIN_MONTHS = 48
MIN_N = 24                 # scored months before a verdict


class Px:
    """Closes by name with as-of lookups: px.at('SPY', d) = the close on or before d."""

    def __init__(self, series):
        self.s = series
        self.k = {n: sorted(v) for n, v in series.items()}

    def at(self, name, d):
        ks = self.k.get(name) or []
        i = bisect_right(ks, d) - 1
        return self.s[name][ks[i]] if i >= 0 else None


def month_ends(calendar):
    """The last session of each complete month in `calendar` (the calendar's own last day only counts once a later
    session exists, so it is never mistaken for a month-end)."""
    return [d for i, d in enumerate(calendar[:-1]) if calendar[i + 1][:7] != d[:7]]


def features(px, cal, d):
    """[10-year yield, its 63-session change, 10y - 3m yield] at close d, or None."""
    i = bisect_right(cal, d) - 1
    if i < 63:
        return None
    t0, t63, b0 = px.at('TNX', cal[i]), px.at('TNX', cal[i - 63]), px.at('IRX', cal[i])
    return None if None in (t0, t63, b0) else [t0, t0 - t63, t0 - b0]


def _ret(px, a, d0, d1):
    p0, p1 = px.at(a, d0), px.at(a, d1)
    return p1 / p0 - 1 if p0 and p1 else None


def _solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c and M[c][c]:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] if M[i][i] else 0.0 for i in range(n)]


def pick(px, cal, d):
    """(pick, {asset: predicted next-month return}, a month of T-bill interest) for month-end d, fitted on earlier
    month-ends whose next month ended by d. (None, {}, cash) while there are fewer than MIN_MONTHS."""
    me = [m for m in month_ends(cal) if m < d] + [d]
    rows = []
    for m, nxt in zip(me, me[1:]):
        x = features(px, cal, m)
        ys = [_ret(px, a, m, nxt) for a in ASSETS]
        if x and None not in ys:
            rows.append((x, ys))
    x0 = features(px, cal, d)
    cash = (px.at('IRX', d) or 0) / 100 / 12
    if len(rows) < MIN_MONTHS or not x0:
        return None, {}, cash
    k, n = len(x0), len(rows)
    mu = [sum(r[0][j] for r in rows) / n for j in range(k)]
    sd = [max(1e-12, (sum((r[0][j] - mu[j]) ** 2 for r in rows) / n) ** 0.5) for j in range(k)]
    Z = [[(r[0][j] - mu[j]) / sd[j] for j in range(k)] for r in rows]
    z0 = [(x0[j] - mu[j]) / sd[j] for j in range(k)]
    ZtZ = [[sum(z[a] * z[b] for z in Z) + (ALPHA * n if a == b else 0) for b in range(k)] for a in range(k)]
    pred = {}
    for ai, a in enumerate(ASSETS):
        y = [r[1][ai] for r in rows]
        ym = sum(y) / n
        beta = _solve(ZtZ, [sum(z[j] * (yy - ym) for z, yy in zip(Z, y)) for j in range(k)])
        pred[a] = ym + sum(b * z for b, z in zip(beta, z0))
    best = max(pred, key=pred.get)
    return (best if pred[best] > cash else 'CASH'), {a: round(v, 5) for a, v in pred.items()}, cash


def rule_pick(px, cal, d):
    """SPY above its 150-session average, else the stronger of GLD / TLT over 63 sessions."""
    i = bisect_right(cal, d) - 1
    if i < 150:
        return None
    closes = [px.at('SPY', c) for c in cal[i - 149:i + 1]]
    if None not in closes and closes[-1] > sum(closes) / 150:
        return 'SPY'
    g, t = _ret(px, 'GLD', cal[i - 63], cal[i]), _ret(px, 'TLT', cal[i - 63], cal[i])
    return 'GLD' if (g or 0) >= (t or 0) else 'TLT'


def new_doc():
    return dict(started=STARTED, minN=MIN_N, months=[])


def write(doc, d, px, cal, at):
    """Log month-end d's picks once. Returns the row, or None when already logged or the model can't run yet."""
    if any(m['d'] == d for m in doc['months']):
        return None
    p, pred, cash = pick(px, cal, d)
    if p is None:
        return None
    row = dict(d=d, at=at, pick=p, pred=pred, cash=round(cash, 5), rule=rule_pick(px, cal, d))
    doc['months'].append(row)
    return row


def score(doc, px, cal):
    """Fill in each logged month once its next month-end has passed: the model's, the rule's and SPY's returns."""
    me = month_ends(cal)
    n = 0
    for m in doc['months']:
        later = [x for x in me if x > m['d']]
        if 'model' in m or not later:
            continue
        nxt = later[0]
        val = lambda a: m['cash'] if a == 'CASH' else _ret(px, a, m['d'], nxt)
        m.update(to=nxt, model=round(val(m['pick']), 5), ruleRet=round(val(m['rule']), 5) if m.get('rule') else None,
                 spy=round(_ret(px, 'SPY', m['d'], nxt), 5))
        n += 1
    return n


def summary(doc):
    """Compounded returns of the model, the rule and SPY over the scored months, the months the model beat the rule,
    and a verdict once MIN_N months are in."""
    done = [m for m in doc['months'] if 'model' in m]
    comp = lambda k: round(reduce(lambda v, m: v * (1 + (m.get(k) or 0)), done, 1.0) - 1, 4) if done else None
    out = dict(n=len(done), model=comp('model'), rule=comp('ruleRet'), spy=comp('spy'),
               differ=sum(1 for m in done if m['pick'] != m.get('rule')),
               beat=sum(1 for m in done if m['pick'] != m.get('rule') and m['model'] > (m.get('ruleRet') or 0)))
    out['verdict'] = ('too few' if len(done) < MIN_N else 'ahead of the rule' if out['model'] > out['rule'] else 'behind the rule')
    return out

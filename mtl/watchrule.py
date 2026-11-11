"""Watch rule and pullback guidance for the scanner page, from the owner's review picks (research/human_review/ANALYSIS.md).
Information only: nothing here changes the plan.

The watch rule is the best of the 425,355 rules searched from the review picks (idea 249; 63.2% a year from 2000 in the
strict test against the plan's 60.4%, t 1.38, worst drop -26%; the best of so many, so most of that margin is
selection). It lays a haven over the plan:
- out (into a haven) when SPY's 50-day average is under its 200-day, gold is up over the last 21 sessions and SPY
  closes under the channel drawn from its recent 5% swings;
- back to the plan, after at least 3 sessions, when SPY is in the upper half of the channel drawn from its 3% swings or
  closes above its last 3% swing high;
- haven: TLT while it is above its 50-day average, else the haven up most over 21 sessions, else cash; once a week a
  haven whose own money flow turns out is picked again.
Decided at each close; the research traded at the next close.

The guidance reads three lessons from the review picks:
- leave for TLT, not cash (cash calls cost about 2 points a year; TLT calls carried the edge);
- act early in a pullback near the highs (calls within 10% of SPY's 1-year high carried the edge; deep in a bear
  market they added nothing);
- a call a week late is worse than no call (the picks moved 5 sessions later made 57.1% against 64.1%).

compute(doc, entries) takes data/flow_box.json (its daily closes dd / ds / db / dg / df) and the paper record's entries
(data/paper_ledger.json) for what the plan holds now."""
import math

HAVEN_NAME = {'b': 'TLT', 'g': 'gold', 'f': 'DBMF', 'c': 'cash'}
PLAN_CODE = {'boost': 's', 'GLD': 'g', 'GLDX': 'g', 'TLT': 'b', 'TLTX': 'b', 'CASH': 'c', 'BIL': 'c', 'DBMF': 'f'}


def _sma(x, n):
    out, s, q = [None] * len(x), 0.0, 0
    for i, v in enumerate(x):
        if v is None:
            s, q = 0.0, 0
            continue
        s += v
        q += 1
        if q > n:
            s -= x[i - n]
            q = n
        if q == n:
            out[i] = s / n
    return out


def _ret(x, i, n):
    if i < n or x[i] is None or x[i - n] is None or x[i - n] <= 0:
        return None
    return x[i] / x[i - n] - 1


def _rsi(x, n=14):
    out, ag, al, k = [None] * len(x), 0.0, 0.0, 0
    for j in range(1, len(x)):
        if x[j] is None or x[j - 1] is None:
            continue
        ch = x[j] - x[j - 1]
        g, lo = max(ch, 0.0), max(-ch, 0.0)
        k += 1
        if k <= n:
            ag += g / n
            al += lo / n
            if k < n:
                continue
        else:
            ag = (ag * (n - 1) + g) / n
            al = (al * (n - 1) + lo) / n
        out[j] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def zigzag(x, th):
    """Swing highs and lows of the closes x: (index, 'H' | 'L', index of the close that confirmed it by a turn of th)."""
    out, mode, hi, lo, ext = [], 0, None, None, None
    for i, v in enumerate(x):
        if v is None:
            continue
        if hi is None:
            hi = lo = i
            continue
        if mode == 0:
            if v > x[hi]:
                hi = i
            if v < x[lo]:
                lo = i
            if v >= x[lo] * (1 + th):
                out.append((lo, 'L', i)); mode, ext = 1, i
            elif v <= x[hi] * (1 - th):
                out.append((hi, 'H', i)); mode, ext = -1, i
        elif mode == 1:
            if v > x[ext]:
                ext = i
            elif v <= x[ext] * (1 - th):
                out.append((ext, 'H', i)); mode, ext = -1, i
        else:
            if v < x[ext]:
                ext = i
            elif v >= x[ext] * (1 + th):
                out.append((ext, 'L', i)); mode, ext = 1, i
    return out


def strip(x, k0, k1):
    """The tightest channel holding every close in [k0, k1] (log prices): (slope, lower intercept, upper intercept)."""
    P = [(i, math.log(x[i])) for i in range(k0, k1 + 1) if x[i]]
    if len(P) < 5:
        return None

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for q in P:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(P):
        while len(up) >= 2 and cr(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    best = None
    for h in (lo, up):
        for a, b in zip(h, h[1:]):
            s = (b[1] - a[1]) / (b[0] - a[0])
            c = a[1] - s * a[0]
            r = [y - (c + s * xx) for xx, y in P]
            w = max(r) - min(r)
            if best is None or w < best[0]:
                best = (w, s, c + min(r), c + max(r))
    return best[1:]


def swing(x, th):
    """Per close: (position in the swing channel, 0 = its lower line and 1 = its upper; above the last swing high;
    the last swing high). The channel runs from the swing before the last (at least 20 sessions back) to the day
    before, using only swings confirmed by that close."""
    piv = zigzag(x, th)
    pos, above, lasth = [None] * len(x), [None] * len(x), [None] * len(x)
    conf, j = [], 0
    for k in range(len(x)):
        while j < len(piv) and piv[j][2] <= k:
            conf.append(piv[j]); j += 1
        if x[k] is None or len(conf) < 4:
            continue
        hs = [p for p in conf if p[1] == 'H']
        if len(hs) < 2 or len([p for p in conf if p[1] == 'L']) < 2:
            continue
        above[k] = x[k] > x[hs[-1][0]]
        lasth[k] = x[hs[-1][0]]
        ps = [p[0] for p in conf]
        q = len(ps) - 2
        while q > 0 and (k - 1) - ps[q] < 20:
            q -= 1
        ch = strip(x, ps[q], k - 1)
        if ch:
            s, lo, up = ch
            y = math.log(x[k])
            pos[k] = (y - (lo + s * k)) / ((up - lo) or 1e-9)
    return pos, above, lasth


def _haven(i, X, m50):
    if X['b'][i] and m50['b'][i] and X['b'][i] > m50['b'][i]:
        return 'b'
    c = {t: _ret(X[t], i, 21) for t in 'bgf'}
    c = {t: v for t, v in c.items() if v is not None and v > 0}
    return max(c, key=c.get) if c else 'c'


def _share(x, i):
    a, b = _ret(x, i, 21), _ret(x, i, 63)
    return None if a is None or b is None else min(0.5 * a + 0.5 * b, a)


def compute(doc, entries, history=False):
    d = doc['dd']
    X = {'s': doc['ds'], 'b': doc['db'], 'g': doc['dg'], 'f': doc['df']}
    n = len(d)
    m50 = {k: _sma(v, 50) for k, v in X.items()}
    m200 = _sma(X['s'], 200)
    pos5, _, _ = swing(X['s'], 0.05)
    pos3, above3, lasth3 = swing(X['s'], 0.03)
    rsi = _rsi(X['s'])
    hi252 = [max([v for v in X['s'][max(0, i - 251):i + 1] if v is not None] or [None]) for i in range(n)]

    def conds(i):
        return dict(cross=m50['s'][i] is not None and m200[i] is not None and m50['s'][i] < m200[i],
                    gold=(_ret(X['g'], i, 21) or 0) > 0,
                    chan=pos5[i] is not None and pos5[i] < 0)

    def back(i):
        return dict(chan=pos3[i] is not None and pos3[i] > 0.5, high=bool(above3[i]))

    # the rule, run from the start of the data (only past closes at each step)
    st, cur, since, switches = [None] * n, None, 0, []
    for i in range(n):
        prev = cur
        if cur is None:
            if all(conds(i).values()):
                cur, since = _haven(i, X, m50), 0
        else:
            since += 1
            if since >= 3 and any(back(i).values()):
                cur = None
            elif since % 5 == 0 and cur != 'c' and (_share(X[cur], i) or 0) < 0:
                cur = _haven(i, X, m50)
        st[i] = cur
        if cur != prev:
            switches.append((d[i], prev, cur))
    k = n - 1
    held = 's'
    led = sorted((e['d'], e.get('mode')) for e in entries or [] if e.get('d'))
    if led:
        held = PLAN_CODE.get(led[-1][1], 's')
    rule = st[k]
    if rule is None:
        verdict = 'agree'
    elif held == 's':
        verdict = 'differ'
    elif held != rule:
        verdict = 'haven'
    else:
        verdict = 'agree'
    since_d = next((sw[0] for sw in reversed(switches)), None)

    # guidance: the pullback signature the review picks acted on, and how old it is
    dd252 = X['s'][k] / hi252[k] - 1 if hi252[k] else None
    def sig(i):
        return (rsi[i] is not None and rsi[i] < 50 and (_ret(X['s'], i, 5) or 0) < 0 and pos3[i] is not None
                and pos3[i] < 0.4 and hi252[i] and X['s'][i] >= 0.9 * hi252[i])
    age = 0
    while k - age >= 0 and sig(k - age):
        age += 1
    if dd252 is not None and dd252 < -0.10:
        pull = 'deep'
    elif age == 0:
        pull = 'quiet'
    elif age <= 5:
        pull = 'early'
    else:
        pull = 'late'
    tlt1m = _ret(X['b'], k, 21)
    tlt_up = bool(X['b'][k] and m50['b'][k] and X['b'][k] > m50['b'][k])
    return dict(asOf=d[k], rule=rule, plan=held, verdict=verdict, since=since_d,
                conds=conds(k), back=back(k), havenNow=_haven(k, X, m50),
                gold1m=_ret(X['g'], k, 21), spy50=m50['s'][k], spy200=m200[k], spy=X['s'][k],
                chan5=pos5[k], chan3=pos3[k], lastHigh3=lasth3[k],
                switches=[(a, b, c) for a, b, c in switches[-6:]],
                pull=pull, pullAge=age, dd252=dd252, rsi=rsi[k], spy5=_ret(X['s'], k, 5),
                tltUp=tlt_up, tlt1m=tlt1m, **({'states': st} if history else {}))

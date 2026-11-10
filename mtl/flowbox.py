"""The money flow box on the scanner page: stocks (SPY), long bonds (TLT), gold (GLD), managed futures (DBMF) and cash,
week by week since 2000, for an animation of where money is leaning. Information only: nothing here changes the plan.

build() takes the plan history's daily prices and holdings (data/plan_history.json: SPY, gold and bonds with their
pre-fund stand-ins, and what the plan held after each close), fresh daily closes (dividend-adjusted) of SPY / TLT / GLD / DBMF for the days
after it (each joined on at the plan history's last close, so the series runs on without a jump), and the paper record's
entries (data/paper_ledger.json) for what the plan held after the plan history ends. It returns one row per week (the
week's last session):
- d: the date; s / b / g / f: the closes of stocks, bonds, gold and managed futures (f is None before DBMF began);
- h: what the plan held after that close, one letter per week ('s' stocks, 'g' gold, 'b' bonds, 'c' cash, 'f' futures);
- rs / rb / rg / rf: each one's 14-day RSI (Wilder) at that close.
The page works out the rest (the 1 + 3 month scores, the 1-week moves, a 14-week RSI) from these."""
from bisect import bisect_right
from datetime import date

HELD_COLS = ('stocks', 'gold', 'bonds', 'cash', 'futures')
HELD_CODE = {'stocks': 's', 'gold': 'g', 'bonds': 'b', 'cash': 'c', 'futures': 'f'}
MODE_CODE = {'boost': 's', 'GLD': 'g', 'TLT': 'b', 'CASH': 'c', 'DBMF': 'f'}


def rsi(closes, n=14):
    """{date: RSI} for a [(date, close)] series, Wilder's smoothing, from the n-th change on."""
    out, ag, al = {}, 0.0, 0.0
    for j in range(1, len(closes)):
        ch = closes[j][1] - closes[j - 1][1]
        g, lo = max(ch, 0.0), max(-ch, 0.0)
        if j <= n:
            ag += g / n
            al += lo / n
            if j < n:
                continue
        else:
            ag = (ag * (n - 1) + g) / n
            al = (al * (n - 1) + lo) / n
        out[closes[j][0]] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def join(old, new):
    """The [(date, close)] series `old`, then `new` after old's last date, scaled to meet old's last close."""
    if not old:
        return list(new)
    end, last = old[-1]
    base = [c for d, c in new if d <= end]
    if not base:
        return list(old)
    k = last / base[-1]
    return list(old) + [(d, c * k) for d, c in new if d > end]


def held_codes(rows, entries, days, end=None):
    """What the plan held after each day's close: the plan history's rows through its last day (`end`), then the paper
    record's entries."""
    hr = sorted((r[0], r[1:]) for r in rows)
    hd = [r[0] for r in hr]
    end = end or (hd[-1] if hd else '')
    led = sorted((e['d'], e.get('mode')) for e in entries if e.get('d'))
    ld = [e[0] for e in led]
    out = {}
    for d in days:
        if d <= end or not ld:
            j = bisect_right(hd, d) - 1
            if j < 0:
                out[d] = 's'
                continue
            w = hr[j][1]
            out[d] = HELD_CODE[HELD_COLS[max(range(len(HELD_COLS)), key=lambda i: w[i] or 0)]]
        else:
            j = bisect_right(ld, d) - 1
            out[d] = MODE_CODE.get(led[j][1], 's') if j >= 0 else out.get(end, 's')
    return out


def build(plan_history, fresh, entries):
    """The weekly rows (see the module note). plan_history: the parsed data/plan_history.json; fresh: {'SPY'|'TLT'|'GLD'|
    'DBMF': [(date, close)]}; entries: the paper record's entries."""
    P = plan_history['prices']
    series = {}
    for key, col, tk in (('s', 'SPY', 'SPY'), ('b', 'bonds', 'TLT'), ('g', 'gold', 'GLD')):
        old = [(d, c) for d, c in zip(P['dates'], P[col]) if c is not None]
        series[key] = join(old, fresh.get(tk) or [])
    series['f'] = list(fresh.get('DBMF') or [])
    days = sorted({d for k in ('s', 'b', 'g') for d, _ in series[k]})
    first = max(series[k][0][0] for k in ('s', 'b', 'g'))
    days = [d for d in days if d >= first]
    look = {k: dict(v) for k, v in series.items()}
    ff = {}
    for k in ('s', 'b', 'g', 'f'):
        last, col = None, {}
        for d in days:
            last = look[k].get(d, last)
            col[d] = last
        ff[k] = col
    weeks = [d for i, d in enumerate(days) if i + 1 == len(days) or
             date.fromisoformat(days[i + 1]).isocalendar()[:2] != date.fromisoformat(d).isocalendar()[:2]]
    held = held_codes(plan_history.get('held') or [], entries, weeks, plan_history.get('end'))
    rs = {k: rsi(series[k]) for k in ('s', 'b', 'g', 'f')}
    rk = {k: sorted(v) for k, v in rs.items()}
    out = {'d': weeks, 's': [], 'b': [], 'g': [], 'f': [], 'h': ''.join(held[d] for d in weeks),
           'rs': [], 'rb': [], 'rg': [], 'rf': []}
    f0 = series['f'][0][0] if series['f'] else '9999'
    for d in weeks:
        for k in ('s', 'b', 'g', 'f'):
            v = ff[k][d] if (k != 'f' or d >= f0) else None
            out[k].append(round(v, 3) if v is not None else None)
            j = bisect_right(rk[k], d) - 1
            r = rs[k][rk[k][j]] if j >= 0 else None
            out['r' + k].append(round(r, 1) if r is not None else None)
    return out

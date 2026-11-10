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
- vs / vb / vg / vf / vc: with `sizes` (data/market_sizes.json), each basket's market size in $ billions (market_sizes()).
It also keeps the daily closes (dd: dates; ds / db / dg / df; the last DAILY sessions, or all of them) for the 6-month trend
chart, which follows the animation's week.
The page works out the rest (the 1 + 3 month scores, the 1-week moves, a 14-week RSI) from these."""
import math
from bisect import bisect_right
from datetime import date

HELD_COLS = ('stocks', 'gold', 'bonds', 'cash', 'futures')
HELD_CODE = {'stocks': 's', 'gold': 'g', 'bonds': 'b', 'cash': 'c', 'futures': 'f'}
MODE_CODE = {'boost': 's', 'GLD': 'g', 'TLT': 'b', 'CASH': 'c', 'DBMF': 'f'}
DAILY = None   # sessions of daily closes kept for the page's 6-month trend chart (None: all of them)


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


def build(plan_history, fresh, entries, sizes=None):
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
    if sizes:
        # each basket's market size at each week, for the page's 'market size' option; the quarter-end anchors are
        # looked up on the trading calendar (the last session on or before them)
        cal = {}
        for k in ('s', 'g'):
            col_, last_ = {}, None
            qd = sorted({x[0] for x in sizes['stocks']} | set(weeks))
            ks = sorted(ff[k])
            for d in qd:
                j = bisect_right(ks, d) - 1
                col_[d] = ff[k][ks[j]] if j >= 0 else None
            cal[k] = col_
        out.update(market_sizes(weeks, cal, sizes))
    # the last DAILY sessions (dd and ds / db / dg / df, forward-filled closes) for the 6-month trend chart
    tail = days[-DAILY:] if DAILY else days
    out['dd'] = tail
    for k in ('s', 'b', 'g', 'f'):
        out['d' + k] = [round(ff[k][d], 3) if ff[k][d] is not None and (k != 'f' or d >= f0) else None for d in tail]
    return out


OZ_PER_TONNE = 32150.7466


def _interp(pts, d):
    """Linear interpolation of [(date, value)] at date d; flat beyond either end."""
    if not pts:
        return None
    if d <= pts[0][0]:
        return pts[0][1]
    if d >= pts[-1][0]:
        return pts[-1][1]
    j = bisect_right([p[0] for p in pts], d)
    (a, va), (b, vb) = pts[j - 1], pts[j]
    da, db, dd = (date.fromisoformat(x).toordinal() for x in (a, b, d))
    return va + (vb - va) * (dd - da) / (db - da)


def gold_spot(gld, d):
    """The gold price an ounce from a GLD close: a share held 0.1 oz at launch (Nov 18, 2004), less its 0.4% a year fee."""
    yrs = (date.fromisoformat(d) - date(2004, 11, 18)).days / 365.25
    return gld / (0.1 * math.exp(-0.004 * yrs))


def market_sizes(weeks, closes, M):
    """Each basket's market size in $ billions at each week (vs / vb / vg / vf / vc), from M (data/market_sizes.json):
    stocks = the last quarter-end value carried by SPY's move since; bonds and cash = linear between quarter ends (flat
    after the last); gold = above-ground tonnes x the gold price from GLD; futures = the industry's year-end assets."""
    st = [tuple(x) for x in M['stocks']]
    sd = [x[0] for x in st]
    out = {'vs': [], 'vb': [], 'vg': [], 'vf': [], 'vc': []}
    for d in weeks:
        s, g = closes['s'][d], closes['g'][d]
        j = bisect_right(sd, d) - 1
        if j >= 0 and s and closes['s'].get(sd[j]):
            v = st[j][1] * s / closes['s'][sd[j]]
        else:
            v = _interp(st, d)
        out['vs'].append(round(v, 1) if v is not None else None)
        out['vb'].append(round(_interp([tuple(x) for x in M['bonds']], d), 1))
        out['vc'].append(round(_interp([tuple(x) for x in M['cash']], d), 1))
        t = _interp([tuple(x) for x in M['gold_tonnes']], d)
        out['vg'].append(round(t * OZ_PER_TONNE * gold_spot(g, d) / 1e9, 1) if g else None)
        out['vf'].append(round(_interp([tuple(x) for x in M['futures']], d), 1))
    return out

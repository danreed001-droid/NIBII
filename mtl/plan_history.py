"""Where the default plan was: its shares of stocks, gold, bonds, cash and managed futures after each close, for the market
events page.

Before the paper record starts, data/plan_history.json: the point-in-time backtest of today's rules, rebuilt with the
track record (research/backtest/build_plan_history.py), so a rule change redraws those years. From the paper record's
first fill on, its live decisions (data/paper_ledger.json, append-only), each filling at the next session's close: what
the plan actually did, which a later backtest rerun never rewrites. Information only; pure apart from load."""
import json
import os

from mtl.calendar_nyse import add_trading_days, next_trading_day

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data', 'plan_history.json')
LEDGER = os.path.join(ROOT, 'data', 'paper_ledger.json')
TRACK = os.path.join(ROOT, 'data', 'track_record.json')     # its 'rotation' line: the backtest of today's rules
SCAN = os.path.join(ROOT, 'data', 'momentum_scan.json')     # tonight's scan (not kept in git): the live paper account
ORDER = ('stocks', 'gold', 'bonds', 'cash', 'futures')     # futures: DBMF, held instead of cash from Oct 20, 2026
NAME = {'futures': 'managed futures'}                        # how the events page writes a kind (the kind itself otherwise)
LIVE_KIND = {'GLD': 'gold', 'TLT': 'bonds', 'CASH': 'cash', 'DBMF': 'futures'}   # anything else in a live decision is stocks (the list or SPY)
MONTH = 21


def _load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def shares(w):
    out = dict.fromkeys(ORDER, 0.0)
    for t, x in w.items():
        out[LIVE_KIND.get(t, 'stocks')] += x
    tot = sum(out.values()) or 1.0
    return tuple(round(out[k] / tot, 2) for k in ORDER)


def timeline(hist, ledger):
    """[(from close of, (stocks, gold, bonds, cash))] in date order: the backtest until the paper record's first fill,
    then each live decision from the session it fills at."""
    rows = [(r[0], tuple((list(r[1:]) + [0.0] * len(ORDER))[:len(ORDER)])) for r in (hist or {}).get('held', [])]   # older files: no futures column
    live = [(next_trading_day(e['d']).isoformat(), shares(e['w'])) for e in (ledger or {}).get('entries', []) if e.get('w')]
    if live:
        first = min(f for f, _ in live)
        rows = [r for r in rows if r[0] < first] + live
    out = []
    for d, sh in sorted(rows, key=lambda r: r[0]):
        if not out or out[-1][1] != sh:
            out.append((d, sh))
    return out


def load(path=PATH, ledger=LEDGER):
    return timeline(_load(path), _load(ledger))


def main(sh):
    """The biggest part: 'stocks', 'gold', 'bonds', 'cash' or 'futures'."""
    return ORDER[max(range(len(ORDER)), key=lambda i: sh[i])]


def during(tl, d):
    """What the plan held through session d (bought at an earlier close), or None before the history starts."""
    got = None
    for f, sh in tl:
        if f >= d:
            break
        got = sh
    return got


def switch(tl, d, n=MONTH):
    """The first close in the n sessions from d (d's own close included) at which the plan moved its biggest part
    somewhere else: (date, kind), or None."""
    now = during(tl, d)
    if now is None:
        return None
    last, kind = add_trading_days(d, n - 1), main(now)
    for f, sh in tl:
        if d <= f <= last and main(sh) != kind:
            return f, main(sh)
        if f > last:
            break
    return None


def now(tl, asof):
    """Where the plan is after the close of asof: (shares, the close its biggest part moved there, the next decided
    move as (close, kind) or None), or None before the history starts."""
    past = [(f, sh) for f, sh in tl if f <= asof]
    if not past:
        return None
    sh = past[-1][1]
    kind, start = main(sh), past[-1][0]
    for f, s in reversed(past):
        if main(s) != kind:
            break
        start = f
    nxt = next(((f, main(s)) for f, s in tl if f > asof and main(s) != kind), None)
    return sh, start, nxt


def values(track, ledger, live):
    """{date: the plan's value after that close}: the backtest of today's rules (the track record's default line) up to
    the paper record's first fill, then the live paper account chained on from there (what the plan actually made).
    Without tonight's paper account (live empty) the days after the first fill are left out, so they are never filled
    from the backtest."""
    bt = dict((d, v) for d, v in ((track or {}).get('series') or {}).get('rotation') or [])
    ents = (ledger or {}).get('entries') or []
    if not ents:
        return bt
    first = next_trading_day(min(e['d'] for e in ents)).isoformat()
    out = {d: v for d, v in bt.items() if d <= first}
    if live and live[0][0] == first and out.get(first) and live[0][1]:
        k = out[first] / live[0][1]
        out.update((d, v * k) for d, v in live if d > first)
    return out


def load_values(track=TRACK, ledger=LEDGER, scan=SCAN):
    live = ((((_load(scan) or {}).get('plan') or {}).get('paper') or {}).get('curve')) or []
    return values(_load(track), _load(ledger), live)

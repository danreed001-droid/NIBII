"""Where the default plan was: its shares of stocks, gold, bonds and cash after each close, for the market events page.

Up to its end, data/plan_history.json: the point-in-time backtest of today's rules, rebuilt with the track record
(research/backtest/build_plan_history.py), so a rule change redraws the past too. After that, the paper record's live
decisions (data/paper_ledger.json), each filling at the next session's close. Information only; pure apart from load."""
import json
import os

from mtl.calendar_nyse import add_trading_days, next_trading_day

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data', 'plan_history.json')
LEDGER = os.path.join(ROOT, 'data', 'paper_ledger.json')
ORDER = ('stocks', 'gold', 'bonds', 'cash')
LIVE_KIND = {'GLD': 'gold', 'TLT': 'bonds', 'CASH': 'cash'}   # anything else in a live decision is stocks (the list or SPY)
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
    """[(from close of, (stocks, gold, bonds, cash))] in date order: the backtest through its end, then each live
    decision from the session it fills at."""
    rows = [(r[0], tuple(r[1:5])) for r in (hist or {}).get('held', [])]
    end = (hist or {}).get('end') or ''
    for e in sorted((ledger or {}).get('entries', []), key=lambda e: e['d']):
        fill = next_trading_day(e['d']).isoformat()
        if fill > end and e.get('w'):
            rows.append((fill, shares(e['w'])))
    out = []
    for d, sh in sorted(rows, key=lambda r: r[0]):
        if not out or out[-1][1] != sh:
            out.append((d, sh))
    return out


def load(path=PATH, ledger=LEDGER):
    return timeline(_load(path), _load(ledger))


def main(sh):
    """The biggest part: 'stocks', 'gold', 'bonds' or 'cash'."""
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

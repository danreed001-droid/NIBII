"""Analyst earnings-estimate revisions (Yahoo via yfinance), shown next to the picks.

Information only: the rule does not use it. Each signal Friday the readings are
appended to data/revisions_log.json so they can be tested once enough weeks exist
(no free point-in-time history goes back far enough to backtest them today).
"""
import json
import os
import sys
import time


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def revision(trend, revs):
    """{eps, eps90, up30, down30} from yfinance's eps_trend / eps_revisions frames.

    eps: this fiscal year's consensus EPS; eps90: its change over the last 90 days
    (relative to the absolute estimate, so a loss narrowing reads as up); up30 / down30:
    analysts who raised / cut this year's or next year's estimate in the last 30 days."""
    out = {}
    try:
        cur, old = _num(trend.loc['0y', 'current']), _num(trend.loc['0y', '90daysAgo'])
    except (KeyError, AttributeError, TypeError):
        cur = old = None
    if cur is not None:
        out['eps'] = round(cur, 4)
        if old:
            out['eps90'] = round((cur - old) / abs(old), 4)
    up = down = None
    for p in ('0y', '+1y'):
        try:
            u, d = _num(revs.loc[p, 'upLast30days']), _num(revs.loc[p, 'downLast30days'])
        except (KeyError, AttributeError, TypeError):
            continue
        if u is not None:
            up = (up or 0) + int(u)
        if d is not None:
            down = (down or 0) + int(d)
    if up is not None or down is not None:
        out['up30'], out['down30'] = up or 0, down or 0
    return out or None


def fetch_revisions(tickers, pause=0.4, retry_wait=20, give_up=4):
    """{ticker: revision dict} - best effort, a ticker with no data is left out.

    Yahoo sometimes refuses these calls for a while (rate limit / stale session
    cookie): an empty answer is retried once after `retry_wait` seconds, and after
    `give_up` empty answers in a row the rest are skipped so the scan is not held up."""
    import yfinance as yf

    def one(t):
        try:
            tk = yf.Ticker(t)
            return revision(tk.eps_trend, tk.eps_revisions)
        except Exception as e:   # noqa: BLE001 - network / parse trouble never stops the scan
            print(f"  revisions {t}: {e}", file=sys.stderr)
            return None

    out, misses = {}, 0
    for i, t in enumerate(tickers):
        r = one(t)
        if r is None:
            time.sleep(retry_wait)
            r = one(t)
        if r:
            out[t], misses = r, 0
        else:
            misses += 1
            if misses >= give_up:
                print(f"  revisions: no answers, skipping the remaining {len(tickers) - i - 1}", file=sys.stderr)
                break
        time.sleep(pause)
    return out


def log_revisions(path, as_of, revs, ranks):
    """Append this signal day's readings (with each stock's rank) to the log, once per date."""
    try:
        with open(path) as fh:
            log = json.load(fh)
    except (OSError, ValueError):
        log = {}
    log[as_of] = {t: dict(r, rank=ranks.get(t)) for t, r in sorted(revs.items())}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        json.dump(log, fh, indent=0, sort_keys=True)
    return log

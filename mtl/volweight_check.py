"""The buying-volume weighting's probation check (information only; the rule itself is mtl/volweight.py). Each trade of
the Boost list is scored until the next one: the stocks at the weights the rule gave them against the same stocks in
equal parts (both held untouched between the trades). Live trades count from PROBATION_START. After YEAR_DAYS calendar
days the live record is compared with the backtest's own one-year records (the scanner's replay of the same rule before
the start): if the weighting trails equal weight by more than the backtest's 1-in-10 worst year, it should be reviewed
for removal (the scanner logs an issue)."""
from datetime import date

from mtl.volweight import START as PROBATION_START

YEAR_DAYS = 365


def _ret(prices, t, a, b):
    p0, p1 = (prices.get(t) or {}).get(a), (prices.get(t) or {}).get(b)
    return p1 / p0 - 1 if p0 and p1 else 0.0


def periods(weights_log, prices, calendar):
    """[(trade date, next trade date or the calendar's last day, weighted, equal, open)] for each trade."""
    out = []
    for i, (d, w) in enumerate(weights_log):
        stocks = {t: x for t, x in w.items() if x > 0}
        if not stocks:
            continue
        end = weights_log[i + 1][0] if i + 1 < len(weights_log) else calendar[-1]
        if end <= d:
            continue
        r = {t: _ret(prices, t, d, end) for t in stocks}
        tot = sum(stocks.values())
        out.append((d, end, sum(stocks[t] * r[t] for t in stocks) / tot, sum(r.values()) / len(r), i + 1 >= len(weights_log)))
    return out


def _chain(rows):
    a = b = 1.0
    for _, _, w, e, _ in rows:
        a *= 1 + w
        b *= 1 + e
    return a / b - 1


def _years(rows):
    """The weighting's edge over each run of trades spanning a year (one per trade start)."""
    out = []
    for i, r in enumerate(rows):
        start = date.fromisoformat(r[0])
        span = [x for x in rows[i:] if (date.fromisoformat(x[1]) - start).days <= YEAR_DAYS]
        if span and (date.fromisoformat(span[-1][1]) - start).days >= YEAR_DAYS - 10:
            out.append(_chain(span))
    return out


def scorecard(weights_log, prices, calendar, since=PROBATION_START):
    """The live record from `since` (trades, how many the weighting won, its edge so far, compounded), the backtest's
    record before it, and the verdict once a year is in."""
    rows = periods(weights_log, prices, calendar)
    live = [r for r in rows if r[0] >= since]
    past = [r for r in rows if r[0] < since]
    yrs = sorted(_years(past))
    p10 = yrs[len(yrs) // 10] if len(yrs) >= 10 else None
    days = (date.fromisoformat(calendar[-1]) - date.fromisoformat(since)).days if calendar and calendar[-1] >= since else 0
    edge = _chain(live) if live else 0.0
    verdict = ('too early' if days < YEAR_DAYS else
               'review: remove' if p10 is not None and edge < p10 else 'keep')
    return dict(since=since, days=days, trades=len(live), won=sum(1 for r in live if r[2] > r[3] + 1e-12),
                lost=sum(1 for r in live if r[2] < r[3] - 1e-12), edge=round(edge, 5), verdict=verdict,
                rows=[dict(d=r[0], to=r[1], w=round(r[2], 5), eq=round(r[3], 5), open=r[4]) for r in live[-12:]][::-1],
                past=dict(trades=len(past), won=sum(1 for r in past if r[2] > r[3] + 1e-12), edge=round(_chain(past), 4) if past else None,
                          years=len(yrs), aheadYears=sum(1 for x in yrs if x > 0), p10=round(p10, 4) if p10 is not None else None,
                          median=round(yrs[len(yrs) // 2], 4) if yrs else None))

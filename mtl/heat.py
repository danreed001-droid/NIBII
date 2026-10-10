"""Rank heatmaps: how a set of stocks did against each other, period by period.

Each period (a week: last close of one week to the last close of the next,
normally Friday to Friday; or a single trading day) every stock's % change is
ranked among the set: 1 = best gain. Stocks are ordered by the average of
their ranks over the window, lowest (most consistently strong) first. A stock
with no price for a period gets no rank that period.
"""
from datetime import date

from .momentum import last_sessions_of_weeks


def _heat(prices, all_ends, periods, tickers, norm_n, min_norm, breadth=None):
    ends = all_ends[-(periods + 1):]
    if len(ends) < 2:
        return dict(weeks=[], partial=False, tickers=list(tickers), cells={}, sums={}, total={})
    first = len(all_ends) - len(ends)

    def normal(t, j):
        """Std dev of the stock's changes over the norm_n periods ending at all_ends[j]."""
        px, r = prices.get(t, {}), []
        lo = max(0, j - norm_n)
        for a, b in zip(all_ends[lo:j], all_ends[lo + 1:j + 1]):
            if px.get(a) and px.get(b):
                r.append(px[b] / px[a] - 1)
        if len(r) < min_norm:
            return None
        m = sum(r) / len(r)
        return (sum((x - m) ** 2 for x in r) / (len(r) - 1)) ** 0.5
    cells = {t: [] for t in tickers}
    for w, (a, b) in enumerate(zip(ends, ends[1:])):
        ch = {}
        for t in tickers:
            pa, pb = prices.get(t, {}).get(a), prices.get(t, {}).get(b)
            if pa and pb:
                ch[t] = pb / pa - 1
        order = sorted(ch, key=lambda t: -ch[t])
        rank = {t: i + 1 for i, t in enumerate(order)}
        for t in tickers:
            if t not in ch:
                cells[t].append(None)
                continue
            sd = normal(t, first + w)
            cells[t].append([round(ch[t], 4), rank[t], round(ch[t] / sd, 2) if sd else None,
                             float(f"{prices[t][b]:.6g}")])
    # breadth: the share of a wider list (e.g. every stock the dashboard tracks) up each period
    wide = None
    if breadth:
        wide = []
        for a, b in zip(ends, ends[1:]):
            up = tot = 0
            for t in breadth:
                pa, pb = prices.get(t, {}).get(a), prices.get(t, {}).get(b)
                if pa and pb:
                    tot += 1
                    up += pb > pa
            wide.append(round(up / tot, 4) if tot else None)
    sums = {t: sum(c[1] for c in cells[t] if c) for t in tickers}
    n = {t: sum(1 for c in cells[t] if c) for t in tickers}
    # average rank keeps a stock with missing periods comparable; ties keep the input order
    order = sorted(tickers, key=lambda t: sums[t] / n[t] if n[t] else 10 ** 9)
    total = {}
    for t in tickers:
        pa, pb = prices.get(t, {}).get(ends[0]), prices.get(t, {}).get(ends[-1])
        total[t] = round(pb / pa - 1, 4) if pa and pb else None
    return dict(weeks=ends[1:], partial=False, tickers=order, cells=cells, sums=sums, total=total,
                breadth=wide, breadthN=len(breadth) if breadth else 0)


def weekly_heat(prices, calendar, tickers, weeks=26, norm_weeks=52, breadth=None):
    """prices: {ticker: {date: close}}; calendar: sorted session dates.

    Returns dict(weeks=[week-end dates, oldest first], partial=bool (the last
    week is still in progress), tickers=[...sorted by rank sum],
    cells={ticker: [[change, rank, z, close] or None per week]}, sums={ticker: rank sum},
    total={ticker: change over the whole period}, unit='week').

    z = the week's change divided by the stock's normal weekly move: the
    standard deviation of its weekly changes over the `norm_weeks` weeks before
    that week (None with fewer than 8 earlier weeks of prices).
    """
    all_ends = last_sessions_of_weeks(calendar)
    out = _heat(prices, all_ends, weeks, tickers, norm_weeks, 8, breadth)
    if out['weeks']:
        last = out['weeks'][-1]
        out['partial'] = date.fromisoformat(last).weekday() < 4 and last == calendar[-1]
    out['unit'] = 'week'
    return out


def daily_heat(prices, calendar, tickers, days=30, norm_days=63, extra=(), breadth=None):
    """The same, one trading day at a time over the last `days` sessions; z uses
    the standard deviation of the stock's daily changes over the `norm_days`
    sessions before that day (None with fewer than 20). `extra` names tickers
    added by hand (flagged for the page). `breadth`: a wider list of tickers whose
    share up each period is returned as `breadth` (for both functions)."""
    out = _heat(prices, list(calendar), days, tickers, norm_days, 20, breadth)
    out['unit'] = 'day'
    out['extra'] = [t for t in extra if t in tickers]
    return out


def daily_closes(prices, calendar, tickers, days=126):
    """The last `days` sessions (plus the base session before them) of each ticker's daily
    closes, for the scanner's overlay chart over the weekly grid:
    {"days": [dates], "closes": {ticker: [close or None]}}."""
    cal = calendar[-(days + 1):]
    return dict(days=list(cal), closes={t: [round(prices[t][d], 4) if prices.get(t, {}).get(d) is not None else None for d in cal]
                                         for t in tickers})

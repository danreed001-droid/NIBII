"""Weekly rank heatmap: how a set of stocks did against each other, week by week.

Each week (last close of one week to the last close of the next, normally
Friday to Friday) every stock's % change is ranked among the set: 1 = best
gain that week. Stocks are ordered by the sum of their weekly ranks over the
period, lowest (most consistently strong) first. A stock with no price for a
week gets no rank that week and is ranked over the weeks it has.
"""
from .momentum import last_sessions_of_weeks


def weekly_heat(prices, calendar, tickers, weeks=26):
    """prices: {ticker: {date: close}}; calendar: sorted session dates.

    Returns dict(weeks=[week-end dates, oldest first], partial=bool (the last
    week is still in progress), tickers=[...sorted by rank sum],
    cells={ticker: [[change, rank] or None per week]}, sums={ticker: rank sum},
    total={ticker: change over the whole period}).
    """
    ends = last_sessions_of_weeks(calendar)
    ends = ends[-(weeks + 1):]
    if len(ends) < 2:
        return dict(weeks=[], partial=False, tickers=list(tickers), cells={}, sums={}, total={})
    from datetime import date
    partial = date.fromisoformat(ends[-1]).weekday() < 4 and ends[-1] == calendar[-1]
    cells = {t: [] for t in tickers}
    for a, b in zip(ends, ends[1:]):
        ch = {}
        for t in tickers:
            pa, pb = prices.get(t, {}).get(a), prices.get(t, {}).get(b)
            if pa and pb:
                ch[t] = pb / pa - 1
        order = sorted(ch, key=lambda t: -ch[t])
        rank = {t: i + 1 for i, t in enumerate(order)}
        for t in tickers:
            cells[t].append([round(ch[t], 4), rank[t]] if t in ch else None)
    sums = {t: sum(c[1] for c in cells[t] if c) for t in tickers}
    n = {t: sum(1 for c in cells[t] if c) for t in tickers}
    # average rank keeps a stock with missing weeks comparable; ties keep the input order
    order = sorted(tickers, key=lambda t: sums[t] / n[t] if n[t] else 10 ** 9)
    total = {}
    for t in tickers:
        pa, pb = prices.get(t, {}).get(ends[0]), prices.get(t, {}).get(ends[-1])
        total[t] = round(pb / pa - 1, 4) if pa and pb else None
    return dict(weeks=ends[1:], partial=partial, tickers=order, cells=cells, sums=sums, total=total)

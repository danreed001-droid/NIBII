"""Growth ranking grid: which of six cross-asset markets gained the most each
week (last 26) or each day (last 30 trading days).

Each period the assets are ranked by % change from the previous period's
close (1 = best gain), and each asset's ranks are summed over the window
(lowest sum = best). Two shading measures ride along per cell, chosen with a
toggle on the page: the move vs. that asset's own biggest move in the window
("own range", computed at render time), and the move vs. the asset's normal
move for that period length ("sigma": |% change| / std dev of its prior 52
weekly or 60 daily changes).

The same grid runs on the moneyflow-update page. A display overlay only: it
never touches a published documents/<date>.json or influences a call.
Pure functions here; scripts/fetch_growth_rank.py does the network fetch.
"""
from datetime import date, timedelta

# Column order, left -> right: (Yahoo ticker, display name).
GRID_ASSETS = [
    ("NQ=F", "Nasdaq 100 futures"),
    ("ES=F", "S&P 500 futures"),
    ("DX-Y.NYB", "US Dollar Index"),
    ("CL=F", "Crude Oil futures"),
    ("GC=F", "Gold futures"),
    ("ZN=F", "10-Year T-Note futures"),
]
WEEKS = 26            # weeks shown in the weekly grid
DAYS = 30             # trading days shown in the daily grid
BASELINE_WEEKS = 52   # prior weekly changes that define an asset's normal weekly move
BASELINE_DAYS = 60    # prior daily changes that define an asset's normal daily move
MIN_BASELINE = 20     # need at least this many prior changes for a sigma
SIGMA_CAP = 2.5       # moves this many normal moves or more get the darkest sigma shade
OVERLAY_DAYS = 126    # sessions in the six-line overlay chart (about 6 months)


def weekdays_only(rows):
    """[(isodate, close)] -> {date: close}, weekends dropped so every asset is
    measured over the same sessions."""
    out = {}
    for iso, close in rows:
        d = date.fromisoformat(iso)
        if d.weekday() < 5 and close:
            out[d] = float(close)
    return out


def weekly_from_daily(daily):
    """{week_ending_friday: last close of that week} from {date: close}."""
    by_week = {}
    for d in sorted(daily):
        by_week[d + timedelta(days=4 - d.weekday())] = daily[d]
    return by_week


def rank_grid(closes_by_ticker, periods, partial_after, baseline):
    """Ranks the assets each period by % change from the previous period.
    `periods` is the list of period keys to show, preceded by the start
    period (periods[0] is only the base the first change is measured from).
    Returns a JSON-ready dict (dates as ISO strings), rows newest first."""
    if len(periods) < 2:
        return None
    start, shown = periods[0], periods[1:]
    tickers = [t for t, _ in GRID_ASSETS if t in closes_by_ticker]

    def pct(t, prev, cur):
        c = closes_by_ticker[t]
        if prev in c and cur in c and c[prev]:
            return (c[cur] - c[prev]) / c[prev] * 100
        return None

    rows = []
    for prev, cur in zip(periods, shown):
        cells = {t: {"pct": p, "close": closes_by_ticker[t][cur]} for t in tickers if (p := pct(t, prev, cur)) is not None}
        for rank, t in enumerate(sorted(cells, key=lambda t: -cells[t]["pct"]), start=1):
            cells[t]["rank"] = rank
        rows.append({"period": cur, "partial": cur > partial_after, "n": len(cells), "cells": cells})

    for t in tickers:
        keys = sorted(closes_by_ticker[t])
        history = [(k, c) for k, c in ((k, pct(t, pk, k)) for pk, k in zip(keys, keys[1:])) if c is not None]
        for row in rows:
            cell = row["cells"].get(t)
            if not cell:
                continue
            prior = [c for k, c in history if k < row["period"]][-baseline:]
            if len(prior) < MIN_BASELINE:
                continue
            mean = sum(prior) / len(prior)
            sigma = (sum((c - mean) ** 2 for c in prior) / (len(prior) - 1)) ** 0.5
            if sigma > 0:
                cell["sigma"] = sigma
                cell["z"] = cell["pct"] / sigma

    # Sum of ranks, lowest = best; a period an asset has no data for counts
    # as last place so a gap can't make it look better.
    rank_sum = {t: sum(r["cells"][t]["rank"] if t in r["cells"] else len(tickers) for r in rows)
                for t in tickers}
    growth = {t: pct(t, start, shown[-1]) for t in tickers}
    for row in rows:
        row["period"] = row["period"].isoformat()
    rows.reverse()  # newest first
    return {
        "assets": [[t, name] for t, name in GRID_ASSETS if t in tickers],
        "start": start.isoformat(),
        "rows": rows,
        "rankSum": rank_sum,
        "growth": growth,
    }


def build(daily_rows_by_ticker, today):
    """{"weekly": grid, "daily": grid} from {ticker: [(isodate, close)]}.
    Weekly = Friday close to Friday close; daily = session to session, only
    on days every asset traded so a holiday can't leave one ranked alone."""
    daily = {t: weekdays_only(rows) for t, rows in daily_rows_by_ticker.items()}
    daily = {t: c for t, c in daily.items() if c}
    if not daily:
        return None
    weekly = {t: weekly_from_daily(c) for t, c in daily.items()}
    all_weeks = sorted({w for c in weekly.values() for w in c})
    common_days = sorted(set.intersection(*(set(c) for c in daily.values())))
    return {
        "weekly": rank_grid(weekly, all_weeks[-(WEEKS + 1):], today, BASELINE_WEEKS),
        "daily": rank_grid(daily, common_days[-(DAYS + 1):], today - timedelta(days=1), BASELINE_DAYS),
    }


HISTORY_FROM = "2000-01-01"   # the date picker's history file starts here


def history(daily_rows_by_ticker):
    """Compact daily history for the page's date picker (docs/growth_history.json):
    {"days": [weekday ISO dates], "assets": [[ticker, name]], "closes": {ticker: [close or None]}}
    aligned to "days"; the page rebuilds the weekly / daily grids ending on any date with the
    same rules as rank_grid()."""
    daily = {t: weekdays_only(rows) for t, rows in daily_rows_by_ticker.items()}
    daily = {t: c for t, c in daily.items() if c}
    if not daily:
        return None
    days = sorted({d for c in daily.values() for d in c})
    tickers = [t for t, _ in GRID_ASSETS if t in daily]
    return {
        "days": [d.isoformat() for d in days],
        "assets": [[t, name] for t, name in GRID_ASSETS if t in daily],
        "closes": {t: [float(f"{daily[t][d]:.6g}") if d in daily[t] else None for d in days] for t in tickers},
    }


def overlay(hist, end=None, days=OVERLAY_DAYS):
    """The last `days` sessions (plus the base session before them) of history() for the
    page's six-line overlay chart, ending on `end` (ISO date, default the last day):
    {"days": [ISO dates], "assets": [[ticker, name]], "closes": {ticker: [close or None]}}."""
    if not hist or not hist.get("days"):
        return None
    n = len(hist["days"]) if end is None else sum(1 for d in hist["days"] if d <= end)
    lo = max(0, n - days - 1)
    if n - lo < 2:
        return None
    closes = {t: c[lo:n] for t, c in hist["closes"].items() if any(x is not None for x in c[lo:n])}
    return {"days": hist["days"][lo:n], "assets": [a for a in hist["assets"] if a[0] in closes], "closes": closes}

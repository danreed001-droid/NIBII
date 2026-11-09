"""World index trends for the scanner page: the S&P 500 next to the DAX, the FTSE 100 and seven other markets.
Information only: nothing here changes the plan.

trend(closes) reads one index's daily closes (local currency) into its recent changes, its gap to its 200-day
average and to its 1-year high, and a trend label:
- 'up': above a rising 200-day average (higher than 21 sessions earlier);
- 'down': below a falling 200-day average;
- 'mixed': anything else.
weekly(closes) keeps the last close of each week, for the chart. fetch_all() downloads them (yfinance)."""

MARKETS = [('^GSPC', 'S&P 500', 'US'), ('^GDAXI', 'DAX', 'Germany'), ('^FTSE', 'FTSE 100', 'UK'),
           ('^FCHI', 'CAC 40', 'France'), ('^GSPTSE', 'TSX', 'Canada'), ('^AXJO', 'ASX 200', 'Australia'),
           ('^HSI', 'Hang Seng', 'Hong Kong'), ('^IBEX', 'IBEX 35', 'Spain'), ('FTSEMIB.MI', 'FTSE MIB', 'Italy'),
           ('^OMX', 'OMX 30', 'Sweden')]
SHOWN = ('^GSPC', '^GDAXI', '^FTSE')     # on the chart by default
START = '2005-01-01'
MA = 200
SLOPE = 21


def _chg(c, n):
    return c[-1] / c[-1 - n] - 1 if len(c) > n and c[-1 - n] else None


def trend(closes):
    """closes: [(isodate, close)] oldest first -> dict, or None with under a year of closes."""
    c = [v for _, v in closes if v]
    if len(c) < 260:
        return None
    ma = sum(c[-MA:]) / MA
    ma0 = sum(c[-MA - SLOPE:-SLOPE]) / MA
    gap = c[-1] / ma - 1
    if gap > 0 and ma > ma0:
        lab = 'up'
    elif gap < 0 and ma < ma0:
        lab = 'down'
    else:
        lab = 'mixed'
    return dict(asOf=closes[-1][0], last=round(c[-1], 2), m1=_chg(c, 21), m6=_chg(c, 126), m12=_chg(c, 252),
                vsMa=gap, maUp=ma > ma0, offHigh=c[-1] / max(c[-252:]) - 1, trend=lab)


def weekly(closes):
    """The last close of each ISO week: [(isodate, close)]."""
    from datetime import date
    out = []
    for d, v in closes:
        if not v:
            continue
        wk = date.fromisoformat(d).isocalendar()[:2]
        if out and out[-1][0] == wk:
            out[-1] = (wk, d, v)
        else:
            out.append((wk, d, v))
    return [(d, v) for _, d, v in out]


def build(series):
    """series: {ticker: [(isodate, close)]} -> the page's data: one shared weekly calendar and each market's weekly
    closes on it (4 significant figures, None before its start) with its trend."""
    wk = {t: dict(weekly(s)) for t, s in series.items() if s}
    days = sorted({d for w in wk.values() for d in w})
    # one date per week across markets (markets close on different days): the latest in each ISO week
    from datetime import date
    byw = {}
    for d in days:
        byw[date.fromisoformat(d).isocalendar()[:2]] = d
    cal = sorted(byw.values())
    keys = sorted(byw, key=lambda k: byw[k])
    out = []
    for t, name, country in MARKETS:
        w = wk.get(t)
        if not w:
            continue
        wv = {date.fromisoformat(d).isocalendar()[:2]: v for d, v in w.items()}
        vals, last = [], None
        for k in keys:
            if k in wv:
                last = wv[k]
            vals.append(None if last is None else float(f'{last:.4g}'))
        tr = trend(series[t])
        out.append(dict(t=t, name=name, country=country, on=t in SHOWN, v=vals,
                        trend=None if tr is None else {k: (round(x, 4) if isinstance(x, float) else x) for k, x in tr.items()}))
    return dict(d=cal, markets=out)


def fetch_all(start=START):
    """Download every market's daily closes since `start` (yfinance); a market that fails is left out."""
    from mtl import fetch
    series = {}
    for t, _, _ in MARKETS:
        try:
            series[t] = fetch.fetch_closes(t, start=start, period='max')
        except Exception as e:   # one market down must not lose the rest
            print(f'  {t}: {e}')
    return series

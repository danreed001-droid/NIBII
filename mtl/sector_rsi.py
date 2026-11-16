"""Sector and theme RSI for the scanner page (information only, not a rule): the 14-day RSI of each S&P 500 sector
(the SPDR sector funds) and of each industry ("theme": an equal-weight index of the S&P 500 members in it,
data/industries*.csv), tonight and 5 sessions ago, with the 1-month change.

RSI under 30 reads oversold, over 70 overbought. Pure: closes {ticker: {date: close}}, a session calendar."""
from mtl.backtest import rsi_series

FUNDS = {'XLK': 'Technology', 'XLC': 'Communication services', 'XLY': 'Consumer discretionary', 'XLP': 'Consumer staples',
         'XLE': 'Energy', 'XLF': 'Financials', 'XLV': 'Health care', 'XLI': 'Industrials', 'XLB': 'Materials',
         'XLRE': 'Real estate', 'XLU': 'Utilities'}
PERIOD = 14
BACK = 5            # sessions back for the "was" marker
SPAN = 300          # sessions of closes used (enough for the RSI to settle, plus a year of daily history)
MIN_STOCKS = 4      # an industry needs at least this many priced members
DAYS = 252          # sessions of daily RSI kept for the page's date picker


def _carried(px, cal):
    out, last = [], None
    for d in cal:
        v = px.get(d)
        last = v if v else last
        out.append(last)
    return out


def _row(closes):
    """dict(rsi, was, m1) from a close series (None-led allowed), or None when too short."""
    c = [x for x in closes if x]
    if len(c) < PERIOD + BACK + 2:
        return None
    r = rsi_series(c, PERIOD)
    m1 = c[-1] / c[-22] - 1 if len(c) > 22 else None
    return dict(rsi=round(r[-1], 1), was=round(r[-1 - BACK], 1), m1=None if m1 is None else round(m1, 4))


def industry_index(prices, members, cal):
    """Equal-weight index of members' daily returns on cal (moves over 50% left out; flat on days with under 3)."""
    s, m = [0.0] * len(cal), [0] * len(cal)
    for t in members:
        c = _carried(prices.get(t) or {}, cal)
        for i in range(1, len(cal)):
            if c[i] and c[i - 1]:
                r = c[i] / c[i - 1] - 1
                if abs(r) <= 0.5:
                    s[i] += r
                    m[i] += 1
    out, v = [], 1.0
    for i in range(len(cal)):
        v *= 1 + (s[i] / m[i] if m[i] >= 3 else 0.0)
        out.append(v)
    return out


def build(fund_px, prices, industries, calendar, universe=None):
    """dict(asOf, period, back, sectors=[...], themes=[...]), each row dict(name, rsi, was, m1[, t | n]),
    sectors sorted by RSI high to low and themes low to high."""
    cal = calendar[-SPAN:]
    sectors = []
    for t, nm in FUNDS.items():
        r = _row(_carried(fund_px.get(t) or {}, cal)) if fund_px.get(t) else None
        if r:
            sectors.append(dict(t=t, name=nm, **r))
    groups = {}
    for t in (universe if universe is not None else prices):
        g = industries.get(t)
        if g and t in prices:
            groups.setdefault(g, []).append(t)
    themes = []
    for g, ts in groups.items():
        if len(ts) < MIN_STOCKS:
            continue
        r = _row(industry_index(prices, ts, cal))
        if r:
            themes.append(dict(name=g, n=len(ts), **r))
    # daily RSI for the page's date picker: the last DAYS sessions, for every sector and theme with full history
    hd = cal[-DAYS:]
    hist = dict(dates=hd, sectors={}, themes={}, n={})
    def _daily(closes):
        idx = [i for i, x in enumerate(closes) if x]
        if len(idx) < PERIOD + 2:
            return None
        r = rsi_series([closes[i] for i in idx], PERIOD)
        by = {cal[i]: v for i, v in zip(idx, r)}
        out = [by.get(d) for d in hd]
        return None if any(v is None for v in out[-30:]) else [None if v is None else round(v, 1) for v in out]
    for t in FUNDS:
        if fund_px.get(t):
            v = _daily(_carried(fund_px[t], cal))
            if v:
                hist['sectors'][t] = v
    for g, ts in groups.items():
        if len(ts) >= MIN_STOCKS:
            v = _daily(industry_index(prices, ts, cal))
            if v:
                hist['themes'][g] = v
                hist['n'][g] = len(ts)
    sectors.sort(key=lambda x: -x['rsi'])
    themes.sort(key=lambda x: x['rsi'])
    return dict(asOf=calendar[-1] if calendar else None, period=PERIOD, back=BACK, sectors=sectors, themes=themes, hist=hist)

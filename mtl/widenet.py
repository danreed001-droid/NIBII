"""Wide-net watch (information only): the strongest of about 40 assets the plan never holds.

Metals, energy, farm goods, sector and theme funds, country funds, currencies, real estate and bitcoin (the IBIT
spot fund), all US-listed funds an ordinary account can buy. Each is scored the way the plan scores stocks: the
gain from 6 months ago to 1 month ago, and whether it beats SPY's. Two flags help spot a new big move early: near
its 52-week high (within 3%), and a breakout after a base - its first new 52-week closing high after at least 3
months without one, in the last week.

It changes nothing the plan does. Tested Oct 20, 2026 as a "wild card" fifth slot on top of the plan (Strategy-lab
path, 2000-2026, about 40 assets as each fund began): giving 20% of the stock part to the strongest of these each
week made 42.3% a year against 44.4% (worst drop -27% against -32%); only when it is within 3% of its 52-week high,
43.7% (Sortino 2.19 against 2.10) but 41.3% with bitcoin left out. The gain from the best version came from bitcoin
in 2017, so it stays a watch list.

Pure and network-free."""

WIDE_NET = {
    'GLD': 'gold', 'SLV': 'silver', 'GDX': 'gold miners', 'SIL': 'silver miners', 'CPER': 'copper', 'PPLT': 'platinum',
    'URA': 'uranium', 'USO': 'crude oil', 'UNG': 'natural gas', 'XLE': 'energy stocks', 'DBA': 'farm goods',
    'DBC': 'commodities', 'SMH': 'chip stocks', 'IBB': 'biotech', 'XBI': 'small biotech', 'TAN': 'solar',
    'ICLN': 'clean energy', 'KWEB': 'China internet', 'ARKK': 'innovation', 'ITA': 'defense', 'XHB': 'homebuilders',
    'KRE': 'regional banks', 'EEM': 'emerging markets', 'EWJ': 'Japan', 'EWZ': 'Brazil', 'EWT': 'Taiwan',
    'EWY': 'Korea', 'FXI': 'China', 'INDA': 'India', 'EWW': 'Mexico', 'EWG': 'Germany', 'EWU': 'UK', 'EWC': 'Canada',
    'TUR': 'Turkey', 'ARGT': 'Argentina', 'VNM': 'Vietnam', 'FXE': 'euro', 'FXY': 'yen', 'VNQ': 'real estate',
    'IBIT': 'bitcoin'}
LOOK, SKIP = 126, 21   # the plan's score: gain from LOOK sessions ago to SKIP sessions ago
YEAR = 252             # sessions in the 52-week high
NEAR_HIGH = 0.03       # "near its high": within 3% of its 52-week closing high
BASE = 63              # breakout after a base: no new 52-week high in the BASE sessions before
FRESH = 5              # ... made within the last FRESH sessions
SHOW = 10


def _series(closes, calendar):
    """Closes on SPY's sessions, carried over missing days; None before the first close."""
    out, last = [], None
    for d in calendar:
        last = closes.get(d) or last
        out.append(last)
    return out


def _new_high(c, j):
    """Close j is a 52-week closing high (above every close of the year before it)."""
    prev = [x for x in c[max(0, j - YEAR + 1):j] if x]
    return bool(c[j]) and len(prev) >= YEAR - 1 and c[j] > max(prev)


def _breakout(c, j):
    """Close j is the first 52-week high after BASE sessions without one."""
    if not _new_high(c, j) or j < YEAR + BASE:
        return False
    return not any(_new_high(c, i) for i in range(j - BASE, j))


def scan(closes, spy, calendar, k, names=WIDE_NET, show=SHOW):
    """The watch at the close of calendar[k]. closes: {ticker: {date: close}} (dividend-adjusted); spy: SPY's
    {date: close}. Returns asOf, spyScore, n (assets scored), rows (the `show` strongest by score) and breakouts
    (every asset with a fresh breakout after a base, strongest first)."""
    s = _series(spy, calendar)
    spy_score = s[k - SKIP] / s[k - LOOK] - 1 if k >= LOOK and s[k - LOOK] and s[k - SKIP] else None
    rows = []
    for t, name in names.items():
        c = _series(closes.get(t) or {}, calendar)
        if k < LOOK or not (c[k - LOOK] and c[k - SKIP] and c[k]):
            continue
        hi = max(x for x in c[max(0, k - YEAR + 1):k + 1] if x)
        score = c[k - SKIP] / c[k - LOOK] - 1
        brk = next((calendar[j] for j in range(k, max(k - FRESH, -1), -1) if _breakout(c, j)), None)
        rows.append(dict(t=t, name=name, score=round(score, 4),
                         beats=spy_score is not None and score > spy_score and score > 0,
                         r1m=round(c[k] / c[k - SKIP] - 1, 4), offHigh=round(c[k] / hi - 1, 4),
                         nearHigh=c[k] >= (1 - NEAR_HIGH) * hi, breakout=brk))
    rows.sort(key=lambda r: -r['score'])
    return dict(asOf=calendar[k], spyScore=None if spy_score is None else round(spy_score, 4), n=len(rows),
                rows=rows[:show], breakouts=[r for r in rows if r['breakout']])

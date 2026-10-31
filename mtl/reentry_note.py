"""Re-entry note (information only; the plan does not trade on it): when the default plan goes back into stocks after
10+ sessions out, how concentrated is the stock list it buys?

Each stock's sector is the SPDR sector fund its daily returns tracked most closely over the past year (as in the
research: it labels stocks that left the index too and needs no sector table). Since 2000, on the real S&P 500 member
lists (Oct 31, 2026): of 67 re-entries, the 23 whose list had 3 or more of its 5 stocks in one sector beat the haven
they left over the next 21 sessions 22 times (+9.5% on average); the 44 with at most 2 per sector were a coin flip
(23 times, +0.9%). As rules (waiting in the haven, SPY instead, or the best sector's top 3 for 5-63 sessions) none
beat the plan from 2000, so it is a note for the owner's own call."""
from bisect import bisect_right

FUNDS = {'XLK': 'tech', 'XLF': 'financials', 'XLE': 'energy', 'XLV': 'health care', 'XLY': 'consumer discretionary',
         'XLP': 'consumer staples', 'XLI': 'industrials', 'XLB': 'materials', 'XLU': 'utilities'}
LOOK, MIN_OBS = 252, 126      # sessions of daily returns to compare, and the fewest needed
OUT_DAYS = 10                 # a re-entry: in stocks tonight after this many sessions out
SHOW = 10                     # the note stays up this many sessions after the re-entry
CONC = 3                      # 3+ of the list in one sector = concentrated
STATS = dict(conc=dict(n=23, won=22, avg=0.095), spread=dict(n=44, won=23, avg=0.009))


def _rets(px, days):
    out = []
    for a, b in zip(days, days[1:]):
        pa, pb = px.get(a), px.get(b)
        out.append(pb / pa - 1 if pa and pb else None)
    return out


def _corr(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < MIN_OBS:
        return None
    n = len(pairs)
    mx, my = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    sx = sum((a - mx) ** 2 for a, _ in pairs) ** 0.5
    sy = sum((b - my) ** 2 for _, b in pairs) ** 0.5
    return sxy / (sx * sy) if sx and sy else None


def sectors(prices, funds, calendar, k, tickers):
    """{ticker: fund} - the fund each stock's daily returns tracked most closely over the LOOK sessions to close k
    (None when there's too little history)."""
    days = calendar[max(0, k - LOOK):k + 1]
    fr = {f: _rets(funds[f], days) for f in FUNDS if funds.get(f)}
    out = {}
    for t in tickers:
        sr = _rets(prices.get(t) or {}, days)
        cs = [(c, f) for f, r in fr.items() if (c := _corr(sr, r)) is not None]
        out[t] = max(cs)[1] if cs else None
    return out


def reentry_day(modes, calendar, k, out_days=OUT_DAYS):
    """The latest close within SHOW sessions of k at which the plan went back into stocks ('boost') after out_days+
    sessions out, or None."""
    for j in range(k, max(out_days, k - SHOW + 1) - 1, -1):
        if modes.get(calendar[j], 'boost') == 'boost' and all(modes.get(calendar[i], 'boost') != 'boost'
                                                              for i in range(j - out_days, j)):
            return j
    return None


def note(modes, calendar, k, picks, prices, funds):
    """For the scanner: the re-entry (if one is within SHOW sessions), its stock list's sectors, the most in one
    sector, which kind it is, and the research figures; {'show': False} otherwise."""
    j = reentry_day(modes, calendar, k)
    if j is None:
        return dict(show=False)
    pd = [p[0] for p in picks]
    i = bisect_right(pd, calendar[j]) - 1
    lst = list(picks[i][1]) if i >= 0 else []
    sec = sectors(prices, funds, calendar, j, lst)
    count = {}
    for t, f in sec.items():
        if f:
            count[f] = count.get(f, 0) + 1
    top = max(count.items(), key=lambda kv: kv[1]) if count else (None, 0)
    kind = 'unknown' if not count else 'concentrated' if top[1] >= CONC else 'spread'
    return dict(show=True, d=calendar[j], ago=k - j, list=lst, sectors={t: FUNDS.get(f) for t, f in sec.items()},
                most=top[1], mostIn=FUNDS.get(top[0]), kind=kind, stats=STATS)

"""Heavy-volume break warning for the scanner's holding cards (information only, not a rule; the plan does not act on it).

A held pick that is down over 20 sessions, whose sector is falling while at most 3 of the 11 sectors are (its sector
falling alone), on a day with 1.5x or more its 50-day average volume. In the 2000-2026 study of plan picks, those
fell over the next 4 weeks (-3.4% on average at 1.2-1.6x, -5% at 2x+, -17% at 2.5x+), while the same dips on light
volume bounced (+5.3%). The opposite case is flagged too: a pick down over 20 sessions on heavy volume while 7+
sectors are falling (a market-wide dip) bounced hardest (+9.2% at 1.6x+), so it reads as panic selling, not a break.

Sectors are the 11 SPDR sector funds. Pure: closes {ticker: {date: close}}, volumes {ticker: {date: shares}}."""
from mtl.sector_rsi import FUNDS

LOOK = 20          # sessions for "down over 20 days" (the pick and each sector)
VOL_DAYS = 50      # sessions of average volume before the day
HEAVY = 1.5        # day's volume / that average
ALONE_MAX = 3      # at most this many of the 11 sectors down over LOOK sessions: its sector is falling alone
WIDE_MIN = 7       # this many or more: a market-wide dip
SECTOR_FUND = {'Information Technology': 'XLK', 'Technology': 'XLK', 'Communication Services': 'XLC',
               'Consumer Discretionary': 'XLY', 'Consumer Cyclical': 'XLY', 'Consumer Staples': 'XLP',
               'Consumer Defensive': 'XLP', 'Energy': 'XLE', 'Financials': 'XLF', 'Financial Services': 'XLF',
               'Health Care': 'XLV', 'Healthcare': 'XLV', 'Industrials': 'XLI', 'Materials': 'XLB',
               'Basic Materials': 'XLB', 'Real Estate': 'XLRE', 'Utilities': 'XLU'}


def _chg(px, cal):
    """Close on cal[-1] over the close LOOK sessions before, minus 1; None when either is missing."""
    if not px or len(cal) <= LOOK:
        return None
    a, b = px.get(cal[-1]), px.get(cal[-1 - LOOK])
    return a / b - 1 if a and b else None


def vol_ratio(vol, cal):
    """The last session's volume over the average of the VOL_DAYS sessions before it (None when too little data)."""
    if not vol or len(cal) <= VOL_DAYS:
        return None
    today = vol.get(cal[-1])
    base = [vol[d] for d in cal[-1 - VOL_DAYS:-1] if vol.get(d)]
    if not today or len(base) < VOL_DAYS * 0.8:
        return None
    return today / (sum(base) / len(base))


def check(holdings, prices, volumes, fund_px, cal):
    """{ticker: dict(kind='break'|'panic', vr, chg, fund, sector, secChg, down)} for the holdings ([(ticker, sector name)])
    that trip either reading on the last session of cal; down = how many of the 11 sectors are down over LOOK sessions."""
    secs = {f: _chg(fund_px.get(f), cal) for f in FUNDS}
    known = [c for c in secs.values() if c is not None]
    if len(known) < 8:            # too few sector funds priced to tell "alone" from "market-wide"
        return {}
    down = sum(1 for c in known if c < 0)
    out = {}
    for t, sec in holdings:
        chg = _chg(prices.get(t), cal)
        vr = vol_ratio(volumes.get(t), cal)
        if chg is None or chg >= 0 or vr is None or vr < HEAVY:
            continue
        f = SECTOR_FUND.get(sec or '')
        sc = secs.get(f) if f else None
        if sc is not None and sc < 0 and down <= ALONE_MAX:
            kind = 'break'
        elif down >= WIDE_MIN:
            kind = 'panic'
        else:
            continue
        out[t] = dict(kind=kind, vr=round(vr, 2), chg=round(chg, 4), fund=f, sector=sec,
                      secChg=None if sc is None else round(sc, 4), down=down)
    return out

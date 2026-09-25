"""yfinance data layer.

Replaces the bulk of the manual research: closes, vol gauges, yields and the
driver-regression series, each returned WITH the date of the value so the
blindness rule stays checkable. Anything yfinance cannot supply comes back as
None with a reason, so the overlay scores that component zero rather than
guessing. Judgment fields (volRegime, crowd, vote reasons) are never fetched.
"""
from datetime import date

TICKERS = {
    'equities': '^GSPC', 'bonds': 'TLT', 'gold': 'GC=F',
    'dollar': 'DX-Y.NYB', 'iwm': 'IWM', 'qqq': 'QQQ',
}
SIGMA_TICKER = {
    'equities': '^VIX', 'bonds': None, 'gold': '^GVZ',
    'dollar': None, 'iwm': '^RVX', 'qqq': '^VXN',
}
YIELDS = {'ust2': '^IRX_2Y_PLACEHOLDER', 'ust5': '^FVX', 'ust10': '^TNX', 'ust30': '^TYX'}
EXTRA = {'vix3m': '^VIX3M', 'vix9d': '^VIX9D', 'skew': '^SKEW', 'wti': 'CL=F',
         'silver': 'SI=F', 'brent': 'BZ=F', 'rut': '^RUT', 'dji': '^DJI',
         'ndx': '^NDX', 'comp': '^IXIC'}

NOTE_GOLD = ("GC=F is COMEX futures, which run roughly $50 above spot XAU/USD. "
             "The ledger scores SPOT. Either keep one vendor for basis and maturity "
             "consistently, or source spot separately and record which.")
NOTE_YIELDS = ("^TNX/^FVX/^TYX are yield*10 on some feeds; normalise and cross-check. "
               "yfinance has no clean 2-year series - source it explicitly.")


def rsi14(closes, period=14):
    """Wilder RSI on a close series. Needs period+1 points minimum."""
    if closes is None or len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


def sma(closes, n):
    if closes is None or len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 4)


def stretch_inputs_from_history(closes, as_of):
    """Every stretch input except the two judgment components, computed locally.

    Computing RSI and the moving averages here rather than scraping them removes
    the whole class of failure the ledger's dataNotes keeps recording: technical
    pages with inverted 200-days, MA50 and MA200 collapsed together, and values
    silently dated to a later session.
    """
    if not closes:
        return dict(rsi14=None, ma50=None, ma200=None, high52w=None, low52w=None,
                    asOf=as_of, note="no history returned")
    w = closes[-252:] if len(closes) >= 252 else closes
    return dict(rsi14=rsi14(closes), ma50=sma(closes, 50), ma200=sma(closes, 200),
                high52w=round(max(w), 4), low52w=round(min(w), 4), asOf=as_of,
                note=("52-week range is on a CLOSING basis over the trailing 252 sessions; "
                      "vendor pages usually quote an intraday range, which is wider."))


def fetch_closes(ticker, start=None, end=None, period="2y"):
    """Daily closes as [(isodate, close)], oldest first. Requires yfinance."""
    import yfinance as yf
    df = yf.Ticker(ticker).history(period=period, start=start, end=end, auto_adjust=False)
    if df is None or df.empty:
        return []
    return [(i.date().isoformat(), float(c)) for i, c in zip(df.index, df['Close'])
            if c == c]


def closes_through(ticker, s: str, period="2y"):
    """Closes up to and including S. Nothing after S is returned - the blindness
    rule is enforced here in code rather than left to discipline."""
    rows = [r for r in fetch_closes(ticker, period=period) if r[0] <= s]
    return [c for _, c in rows], (rows[-1][0] if rows else None)

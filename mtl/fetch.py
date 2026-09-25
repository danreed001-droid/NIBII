"""yfinance data layer.

Replaces the bulk of the manual research: closes, vol gauges, yields and the
driver-regression series, each returned WITH the date of the value so the
blindness rule stays checkable. Anything yfinance cannot supply comes back as
None with a reason, so the overlay scores that component zero rather than
guessing. Judgment fields (volRegime, crowd, vote reasons) are never fetched.

GOLD AND YIELDS - READ BEFORE TRUSTING LIVE
--------------------------------------------
'gold' below is 'XAUUSD=X', Yahoo's FX-style spot gold quote, not 'GC=F'
(COMEX futures, which run ~$50 above spot on cost-of-carry - kept in
FUTURES_GOLD_TICKER for reference/comparison only, never scored).

^TNX/^FVX/^TYX are CBOE-legacy indices quoted at yield*10 (a 4.33% 10-year
prints as 43.30); YIELD_TICKERS_X10 lists them and scaled_yield() divides by
10. ^IRX is already a direct percentage and is NOT in that set. There is no
2-year Treasury ticker on yfinance; fetch_ust2y_fred() sources DGS2 from FRED
instead.

These conventions are well documented but were NOT re-verified empirically in
the session that wrote this: this environment's outbound network policy
blocks Yahoo Finance (guce.yahoo.com / query2.finance.yahoo.com return 403 at
the proxy), so live scaling could not be spot-checked against a known price.
_assert_plausible_yield/_assert_plausible_gold below catch an obviously wrong
scale rather than let one propagate silently - but the FIRST live run should
still manually cross-check one gold print and one yield against a second
source before the ledger trusts them.
"""
from datetime import date

FUTURES_GOLD_TICKER = 'GC=F'
SPOT_GOLD_TICKER = 'XAUUSD=X'

TICKERS = {
    'equities': '^GSPC', 'bonds': 'TLT', 'gold': SPOT_GOLD_TICKER,
    'dollar': 'DX-Y.NYB', 'iwm': 'IWM', 'qqq': 'QQQ',
}
SIGMA_TICKER = {
    'equities': '^VIX', 'bonds': None, 'gold': '^GVZ',
    'dollar': None, 'iwm': '^RVX', 'qqq': '^VXN',
}
YIELDS = {'ust2': None, 'ust5': '^FVX', 'ust10': '^TNX', 'ust30': '^TYX'}
YIELD_TICKERS_X10 = {'^FVX', '^TNX', '^TYX'}
FRED_UST2Y_SERIES = 'DGS2'
EXTRA = {'vix3m': '^VIX3M', 'vix9d': '^VIX9D', 'skew': '^SKEW', 'wti': 'CL=F',
         'silver': 'SI=F', 'brent': 'BZ=F', 'rut': '^RUT', 'dji': '^DJI',
         'ndx': '^NDX', 'comp': '^IXIC'}

NOTE_GOLD = (f"{TICKERS['gold']} is Yahoo's spot XAU/USD quote. {FUTURES_GOLD_TICKER} is COMEX "
             "futures, which run roughly $50 above spot on cost-of-carry - kept only for "
             "comparison, never scored. Unverified live in this environment; see module docstring.")
NOTE_YIELDS = ("^TNX/^FVX/^TYX are yield*10 on Yahoo (a legacy CBOE index convention) and are "
               "divided by 10 in scaled_yield() before use; ^IRX is not. yfinance has no clean "
               "2-year series - fetch_ust2y_fred() sources FRED's DGS2 instead. "
               "Unverified live in this environment; see module docstring.")


def scaled_yield(raw: float, ticker: str) -> float:
    """Raw Yahoo close -> actual percent yield."""
    pct = raw / 10.0 if ticker in YIELD_TICKERS_X10 else raw
    _assert_plausible_yield(pct, ticker)
    return pct


def _assert_plausible_yield(pct, ticker):
    if pct is not None and not (0.0 <= pct <= 25.0):
        raise ValueError(f"{ticker}: scaled yield {pct} outside plausible 0-25% range - "
                          "check the yield*10 assumption before trusting this print")


def _assert_plausible_gold(px, ticker):
    if px is not None and not (200.0 <= px <= 20000.0):
        raise ValueError(f"{ticker}: gold print {px} outside plausible spot range - "
                          "check whether this is spot or a futures/mis-scaled quote")


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


def gold_close_through(s: str, period="2y"):
    """Spot XAU/USD closes through S, sanity-checked against a plausible range."""
    closes, as_of = closes_through(SPOT_GOLD_TICKER, s, period=period)
    if closes:
        _assert_plausible_gold(closes[-1], SPOT_GOLD_TICKER)
    return closes, as_of


def yield_through(key: str, s: str, period="2y"):
    """Percent yield (already divided by 10 where Yahoo needs it) through S.

    key is one of 'ust2', 'ust5', 'ust10', 'ust30'. 'ust2' has no yfinance
    ticker and is sourced from FRED instead.
    """
    if key == 'ust2':
        return fetch_ust2y_fred(s)
    ticker = YIELDS[key]
    raw, as_of = closes_through(ticker, s, period=period)
    pct = [scaled_yield(v, ticker) for v in raw]
    return pct, as_of


def fetch_ust2y_fred(s: str):
    """2-year Treasury constant-maturity yield (DGS2) through S, from FRED.

    FRED marks non-trading days '.'; those rows are dropped rather than
    interpolated, matching closes_through's oldest-first (date, value) shape
    with the None-value blindness convention used elsewhere in this module.
    """
    import csv
    import io
    import urllib.request

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={FRED_UST2Y_SERIES}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        text = resp.read().decode('utf-8')
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        d, v = row.get('observation_date') or row.get('DATE'), row[FRED_UST2Y_SERIES]
        if v in (None, '.', ''):
            continue
        if d <= s:
            pct = float(v)
            _assert_plausible_yield(pct, 'DGS2')
            rows.append((d, pct))
    return [v for _, v in rows], (rows[-1][0] if rows else None)

"""yfinance data layer.

Replaces the bulk of the manual research: closes, vol gauges, yields and the
driver-regression series, each returned WITH the date of the value so the
blindness rule stays checkable. Anything yfinance cannot supply comes back as
None with a reason, so the overlay scores that component zero rather than
guessing. Judgment fields (volRegime, crowd, vote reasons) are never fetched.

GOLD AND YIELDS - LIVE-VERIFIED 2026-09-25 via GitHub Actions
----------------------------------------------------------------
This environment's own network policy blocks Yahoo Finance, so these were
originally coded from documented convention and flagged unverified. They
have SINCE been spot-checked for real from GitHub Actions (which has normal
outbound internet) - see the "Daily Market Data Fetch" workflow's run from
2026-09-25. Two corrections came out of that check:

- **Gold has no working spot ticker on Yahoo right now.** Both 'XAUUSD=X'
  and 'XAU=X' returned 404 ("Quote not found") live. Only 'GC=F' (COMEX
  futures) returned real data. TICKERS['gold'] is 'GC=F' until a working
  spot source is found - meaning the ledger is currently scoring futures,
  which run ~$50 above spot on cost-of-carry. That basis gap is a real,
  currently-unresolved limitation, not a rounding error.
- **^TNX/^FVX/^TYX are NOT yield*10 - that assumption was wrong.** A live
  check returned ^TNX=5.1620 directly as the percent yield (matching a
  10-year at ~5.16%, not 51.6%). The previous divide-by-10 step
  (scaled_yield(), now removed) would have silently corrupted every yield
  by a factor of 10 the first time this ran for real. YIELDS values are
  used as-is now; _assert_plausible_yield still guards against a future
  format change going uncaught.

There is still no 2-year Treasury ticker on Yahoo; fetch_ust2y_fred() sources
FRED's DGS2 instead - confirmed working live (13,127 rows). Hourly intraday
data (fetch_ohlc's interval='60m', used by mtl.structure) is also confirmed
working for both an index ticker (^GSPC) and an ETF (TLT) - 35 bars each,
current as of the live check.

EQUITIES/QQQ/BONDS/IWM SWITCHED TO FUTURES - LIVE-VERIFIED 2026-09-25 (2nd check)
----------------------------------------------------------------------------------
Switched TICKERS to front-month futures wherever one exists on Yahoo, so the
1D horizon's "1H structure" read (mtl.structure) sees real overnight/pre-open
price action instead of a series that goes quiet outside cash-market hours -
live-verified same-day, all four returning 5 daily rows and 102-103 hourly
bars each: ES=F (S&P 500 e-mini, 7789.0), NQ=F (Nasdaq-100 e-mini, 30902.0),
ZN=F (10-Year T-Note, 104.875), RTY=F (Russell 2000 e-mini, 2864.5).

Two things worth knowing about this switch:
- **NQ=F and RTY=F are INDEX-LEVEL futures, not QQQ/IWM ETF prices** - a
  completely different scale (NQ=F trades around 30,000+, QQQ around
  $700; RTY=F around 2,800+, IWM around $230), not a small basis like
  gold's. scripts/render_html.py's TICKER display map was updated to show
  the real ticker (NQ=F, RTY=F) rather than the old ETF label, so the
  report never shows an index-point price under an ETF's name.
- **ZN=F is a materially different instrument than TLT, not just a
  rescaled version of it.** TLT tracks 20+ Year Treasuries; ZN=F is
  10-Year T-Note futures - shorter duration, different rate sensitivity,
  different price convention (points and fractions, ~104-115, vs TLT's
  ETF share price). "Bonds" now means 10-year rate exposure via futures,
  not TLT's own duration profile - a real, ongoing framing change future
  sessions' judgment votes need to write around, not a rounding error.

**DX=F does NOT exist on Yahoo - live-verified 404, same failure mode as
the gold-ticker check.** TICKERS['dollar'] stays 'DX-Y.NYB' (the ICE cash
index). It is FX-derived and updates near-continuously across the trading
day since the underlying currency crosses trade ~24h on weekdays, but it
is not a discrete futures contract like the other four - dollar is the one
asset that did NOT get a true futures swap in this pass.
"""
from datetime import date

FUTURES_GOLD_TICKER = 'GC=F'
# No working spot gold ticker found on Yahoo as of the 2026-09-25 live check
# (both 'XAUUSD=X' and 'XAU=X' 404). Using futures until a real spot source
# turns up - see the module docstring for the ~$50 basis this introduces.
SPOT_GOLD_TICKER = FUTURES_GOLD_TICKER

TICKERS = {
    'equities': 'ES=F', 'bonds': 'ZN=F', 'gold': SPOT_GOLD_TICKER,
    'dollar': 'DX-Y.NYB', 'iwm': 'RTY=F', 'qqq': 'NQ=F',
}
SIGMA_TICKER = {
    'equities': '^VIX', 'bonds': None, 'gold': '^GVZ',
    'dollar': None, 'iwm': '^RVX', 'qqq': '^VXN',
}
YIELDS = {'ust2': None, 'ust5': '^FVX', 'ust10': '^TNX', 'ust30': '^TYX'}
FRED_UST2Y_SERIES = 'DGS2'
EXTRA = {'vix3m': '^VIX3M', 'vix9d': '^VIX9D', 'skew': '^SKEW', 'wti': 'CL=F',
         'silver': 'SI=F', 'brent': 'BZ=F', 'rut': '^RUT', 'dji': '^DJI',
         'ndx': '^NDX', 'comp': '^IXIC'}

NOTE_GOLD = (f"No working spot gold ticker on Yahoo as of the 2026-09-25 live check "
             f"('XAUUSD=X' and 'XAU=X' both 404). Using {FUTURES_GOLD_TICKER} (COMEX futures, "
             "~$50 above spot on cost-of-carry) as a documented, unresolved limitation until a "
             "real spot source is found.")
NOTE_YIELDS = ("^TNX/^FVX/^TYX/^IRX are all direct percent yields on Yahoo - live-verified "
               "2026-09-25 (^TNX printed 5.1620 for a ~5.16% 10-year). The earlier yield*10 "
               "assumption was wrong and has been removed. yfinance has no clean 2-year series - "
               "fetch_ust2y_fred() sources FRED's DGS2 instead, also live-verified.")
NOTE_FUTURES = ("Equities/qqq/bonds/iwm switched to futures for 24h coverage - "
                 "live-verified 2026-09-25: ES=F, NQ=F, ZN=F, RTY=F all returned real daily and "
                 "hourly data. DX=F does not exist on Yahoo (404, live-verified) so dollar stays "
                 "on DX-Y.NYB, the ICE cash index - the one asset without a true futures source. "
                 "ZN=F is 10-Year T-Note futures, a different instrument and duration than TLT, "
                 "not a rescaled version of it.")


def scaled_yield(raw: float, ticker: str) -> float:
    """Raw Yahoo close -> percent yield. Kept as a named pass-through (not
    inlined at call sites) so the plausibility guard applies uniformly and
    so a future Yahoo format change has one place to fix - see the module
    docstring for why this no longer scales anything."""
    _assert_plausible_yield(raw, ticker)
    return raw


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


def fetch_ohlc(ticker, interval="1d", period="2y", start=None, end=None):
    """OHLC bars as [(iso_timestamp, open, high, low, close)], oldest first.

    interval='60m' (hourly) is subject to Yahoo's own intraday history limit
    (roughly the trailing 730 days, tighter for finer intervals) - a 60d
    period is comfortably inside that limit and far more bars than a swing
    read over a few sessions needs.
    """
    import yfinance as yf
    df = yf.Ticker(ticker).history(interval=interval, period=period, start=start,
                                    end=end, auto_adjust=False)
    if df is None or df.empty:
        return []
    out = []
    for ts, row in zip(df.index, df.itertuples()):
        o, h, l, c = row.Open, row.High, row.Low, row.Close
        if c != c:  # NaN
            continue
        out.append((ts.isoformat(), float(o), float(h), float(l), float(c)))
    return out


def ohlc_through(ticker, s: str, interval="1d", period="2y"):
    """OHLC bars dated on or before S. For an intraday interval this keeps
    every bar within S's own session (S has already closed by the time this
    runs) without ever reaching into S+1 - the blindness rule applies to the
    calendar date, same as closes_through."""
    return [r for r in fetch_ohlc(ticker, interval=interval, period=period) if r[0][:10] <= s]


def close_on(key: str, date: str, period="2y"):
    """The exact close for asset `key` (a TICKERS key) on `date`, or None if
    there's no print for that date yet - a weekend/holiday, or a date whose
    close hasn't happened relative to available data."""
    closes, as_of = (gold_close_through(date, period=period) if key == 'gold'
                     else closes_through(TICKERS[key], date, period=period))
    return closes[-1] if (closes and as_of == date) else None


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

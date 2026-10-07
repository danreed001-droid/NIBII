#!/usr/bin/env python3
"""Draft contracts/inputs.<S>.json and contracts/votes.<S>.json for a session date.

This is the "wire the daily cycle to the engine" half of the split described
in the README: everything fetch.py can compute from a close series (close,
sigma-gauge close, RSI, MA50/MA200, 52-week range) is filled in here, plus
the market-structure read (mtl/structure.py) from hourly/weekly bars. Every
judgment field - direction, driverNote, the first 12 categories, volRegime,
crowd, stretchDrivers, nullInputs, and 216 of the 234 vote (side, reason)
pairs - is left as an explicit TODO placeholder for the model to fill in
before scripts/publish.py is run. This script never invents a judgment
call - but the 13th category (Market structure, weighted 3x in the tally -
see mtl/resolve.py) and its 18 votes (6 assets x 3 horizons) ARE filled in
here, mechanically, because that category reports a computed fact rather
than asking for one; see mtl/structure.py.

Requires network access to Yahoo Finance and (for the 2-year yield) FRED;
neither is reachable from every environment. Run it somewhere that can reach
both, then hand the drafted contracts/ files to the model for the judgment
pass.

Usage:
    python scripts/prepare_daily.py 2026-09-25
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.build import ASSET_ORDER
from mtl.drivers import driver_regime, pct_changes, bp_changes
from mtl.fetch import (TICKERS, SIGMA_TICKER, YIELDS, closes_through, fetch_closes,
                        gold_close_through, yield_through,
                        stretch_inputs_from_history, ohlc_through)
from mtl import mechvotes
from mtl.structure import CATEGORY_NAME as STRUCTURE_CATEGORY_NAME
from mtl.structure import (HOURLY_SWING_N, STRUCTURE_LOOKBACK, WEEKLY_SWING_N,
                           structure_signal, vote_from_signal, weekly_from_daily)

TODO = "TODO: fill in before publish"
JUDGMENT_CATEGORY_COUNT = 12  # categories 1-12: named and voted by the model
TOTAL_CATEGORY_COUNT = 13     # + category 13, Market structure - named and voted mechanically
DRIVER_WINDOW = 21  # trading sessions


def fetch_asset(key: str, s: str) -> dict:
    ticker = TICKERS[key]
    closes, as_of = gold_close_through(s) if key == 'gold' else closes_through(ticker, s)
    if not closes:
        raise RuntimeError(f"{key} ({ticker}): no closes returned through {s}")

    sigma_ticker = SIGMA_TICKER[key]
    if sigma_ticker:
        sigma_closes, sigma_as_of = closes_through(sigma_ticker, s)
        sigma = sigma_closes[-1] if sigma_closes else None
        sigma_source = (f"{sigma_ticker} close {sigma}" + (f" on {sigma_as_of}" if sigma else "")
                         if sigma is not None else TODO)
    else:
        sigma, sigma_source = None, TODO  # no direct vol-gauge ticker for this asset

    return dict(
        name=TODO, instrument=f"{ticker} close", direction=TODO,
        close=closes[-1], sigma=sigma, sigmaSource=sigma_source,
        driverNote=TODO,
        # 12 judgment-named categories (the model fills these in) + the
        # fixed, non-judgment 13th: it reports a computed fact, not
        # something that needs naming.
        categories=[TODO] * JUDGMENT_CATEGORY_COUNT + [STRUCTURE_CATEGORY_NAME],
        stretchInputs=stretch_inputs_from_history(closes, as_of),
        structure=fetch_structure(ticker, s),
        # The raw fetch ticker, recorded verbatim - TICKERS has changed
        # once already (ETFs -> futures) and will again, so the report's
        # display label needs to read this rather than assume a fixed
        # symbol forever. Documents drafted before this field existed
        # (e.g. 2026-09-24) fall back to render_html.py's static map.
        ticker=ticker,
        volRegime=0, crowd=0, stretchDrivers=[], nullInputs=[TODO],
    )


def fetch_structure(ticker: str, s: str) -> dict:
    """Market-structure read for both horizon groups: hourly bars for the
    1D call (a day-ahead read has no business caring about a swing from
    three weeks ago), weekly bars - resampled locally from the same
    blindness-safe daily closes, not a second live request - for 5D/10D.
    """
    hourly = ohlc_through(ticker, s, interval="60m", period="60d")
    daily = ohlc_through(ticker, s, interval="1d", period="2y")
    weekly = weekly_from_daily(daily)
    return dict(
        hourly=structure_signal(hourly, n=HOURLY_SWING_N, lookback=STRUCTURE_LOOKBACK),
        weekly=structure_signal(weekly, n=WEEKLY_SWING_N, lookback=STRUCTURE_LOOKBACK),
    )


def fetch_driver_regime(s: str) -> dict:
    """Correlate each asset's recent % moves against 2Y/10Y (bp) and WTI (%)."""
    price_closes = {}
    for key in ASSET_ORDER:
        closes, _ = gold_close_through(s) if key == 'gold' else closes_through(TICKERS[key], s)
        price_closes[key] = closes[-(DRIVER_WINDOW + 1):]

    ust2, _ = yield_through('ust2', s)
    ust10, _ = yield_through('ust10', s)
    wti, _ = closes_through('CL=F', s)

    n = min(len(ust2), len(ust10), len(wti), DRIVER_WINDOW + 1,
            min(len(c) for c in price_closes.values()))
    if n < 3:
        return {"note": TODO + " (insufficient overlapping history for driver regime)"}

    d2y = bp_changes(ust2[-n:])
    d10y = bp_changes(ust10[-n:])
    doil = pct_changes(wti[-n:])
    asset_returns = {k: pct_changes(c[-n:]) for k, c in price_closes.items()}
    return driver_regime(asset_returns, d2y, d10y, doil, window_label=f"{n - 1}-session")


def draft_inputs(s: str) -> dict:
    assets = {key: fetch_asset(key, s) for key in ASSET_ORDER}
    return dict(
        date=s, assetOrder=list(ASSET_ORDER), assets=assets,
        context=dict(driverRegime=fetch_driver_regime(s), dataNotes=[TODO]),
    )


def fetch_mech(s: str) -> dict:
    """Mechanical votes for categories 2 (Breadth), 3 (Volatility regime) and
    4 (Credit), per asset: {asset_key: {2: vote, 3: vote, 4: vote}}.

    Never raises: a ticker that fails to load degrades that one vote to a
    neutral "data unavailable" vote (see mtl/mechvotes.py), so a dead feed
    cannot stop the daily draft. Everything is cut off at S (blindness rule).
    """
    def rows(ticker):
        try:
            return fetch_closes(ticker, period="2y"), None
        except Exception as e:  # network / delisted / rate-limited
            return [], f"{type(e).__name__}"

    rsp, e1 = rows('RSP'); spy, e2 = rows('SPY')
    hyg, e3 = rows('HYG'); ief, e4 = rows('IEF')
    breadth = [c for _, c in mechvotes.ratio_series(rsp, spy, s)]
    credit = [c for _, c in mechvotes.ratio_series(hyg, ief, s)]
    breadth_err = e1 or e2 or (None if breadth else "no overlapping history")
    credit_err = e3 or e4 or (None if credit else "no overlapping history")

    out = {}
    for key in ASSET_ORDER:
        gauge = SIGMA_TICKER.get(key)
        vol_rows, vol_err = rows(gauge) if gauge else ([], None)
        vol = [c for d, c in vol_rows if d <= s]
        if key in mechvotes.VOL_ASSETS and gauge and not vol:
            v3 = mechvotes.unavailable(f"{gauge} volatility regime", vol_err or "no history")
        else:
            v3 = mechvotes.vol_vote(key, vol, gauge)
        if key in mechvotes.BREADTH_ASSETS and breadth_err:
            v2 = mechvotes.unavailable("RSP/SPY breadth", breadth_err)
        else:
            v2 = mechvotes.breadth_vote(key, breadth)
        if key in mechvotes.CREDIT_ASSETS and credit_err:
            v4 = mechvotes.unavailable("HYG/IEF credit", credit_err)
        else:
            v4 = mechvotes.credit_vote(key, credit)
        out[key] = {2: v2, 3: v3, 4: v4}
    return out


def draft_votes(assets: dict, mech: dict = None) -> dict:
    """12 judgment votes stubbed TODO per horizon, plus the 13th (Market
    structure) filled in mechanically right here - never left as a TODO,
    since there's no judgment call to make: hourly structure for the 1D
    horizon, weekly structure for 5D/10D, exactly as computed.

    If `mech` is given (see fetch_mech), categories 2, 3 and 4 (Breadth,
    Volatility regime, Credit) are filled in mechanically too, and their
    names are set. The judgment pass should keep these votes as drafted
    unless it has a dated, sourced reason to override one."""
    votes = {}
    for key in ASSET_ORDER:
        structure = assets[key]['structure']
        by_h = {}
        for h in (1, 5, 10):
            sig, timeframe = ((structure['hourly'], '1H') if h == 1
                              else (structure['weekly'], 'Weekly'))
            judgment = [["neu", TODO] for _ in range(JUDGMENT_CATEGORY_COUNT)]
            if mech:
                for cat, vote in mech[key].items():
                    judgment[cat - 1] = list(vote)
            by_h[str(h)] = judgment + [vote_from_signal(sig, timeframe)]
        votes[key] = by_h
    return votes


def main(s: str):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inputs_path = os.path.join(root, "contracts", f"inputs.{s}.json")
    votes_path = os.path.join(root, "contracts", f"votes.{s}.json")

    for path in (inputs_path, votes_path):
        if os.path.exists(path):
            raise SystemExit(f"{path} already exists - remove it first if you mean to redraft")

    inputs = draft_inputs(s)
    for a in inputs['assets'].values():
        for idx, name in mechvotes.CATEGORY_NAMES.items():
            a['categories'][idx - 1] = name
    with open(inputs_path, "w") as f:
        json.dump(inputs, f, indent=1)
        f.write("\n")
    with open(votes_path, "w") as f:
        json.dump(draft_votes(inputs['assets'], fetch_mech(s)), f, indent=1)
        f.write("\n")

    print(f"drafted {inputs_path}")
    print(f"drafted {votes_path}")
    print(f"{TODO!r} markers need judgment before scripts/publish.py {s}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    main(sys.argv[1])

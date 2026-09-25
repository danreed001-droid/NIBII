#!/usr/bin/env python3
"""Draft contracts/inputs.<S>.json and contracts/votes.<S>.json for a session date.

This is the "wire the daily cycle to the engine" half of the split described
in the README: everything fetch.py can compute from a close series (close,
sigma-gauge close, RSI, MA50/MA200, 52-week range) is filled in here. Every
judgment field - direction, driverNote, categories, volRegime, crowd,
stretchDrivers, nullInputs, and all 72 vote (side, reason) pairs - is left as
an explicit TODO placeholder for the model to fill in before scripts/publish.py
is run. This script never invents a vote or a judgment call.

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
from mtl.fetch import (TICKERS, SIGMA_TICKER, YIELDS, closes_through,
                        gold_close_through, yield_through,
                        stretch_inputs_from_history, ohlc_through)
from mtl.structure import structure_signal, weekly_from_daily

HOURLY_SWING_N = 3    # bars each side, for the 1D horizon's intraday read
WEEKLY_SWING_N = 2    # bars each side, for the 5D/10D horizons' weekly read
STRUCTURE_LOOKBACK = 4  # most recent labeled swings considered for the trend call

TODO = "TODO: fill in before publish"
CATEGORY_COUNT = 12
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
        driverNote=TODO, categories=[TODO] * CATEGORY_COUNT,
        stretchInputs=stretch_inputs_from_history(closes, as_of),
        structure=fetch_structure(ticker, s),
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


def draft_votes() -> dict:
    return {key: {str(h): [["neu", TODO] for _ in range(CATEGORY_COUNT)]
                  for h in (1, 5, 10)}
            for key in ASSET_ORDER}


def main(s: str):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inputs_path = os.path.join(root, "contracts", f"inputs.{s}.json")
    votes_path = os.path.join(root, "contracts", f"votes.{s}.json")

    for path in (inputs_path, votes_path):
        if os.path.exists(path):
            raise SystemExit(f"{path} already exists - remove it first if you mean to redraft")

    with open(inputs_path, "w") as f:
        json.dump(draft_inputs(s), f, indent=1)
        f.write("\n")
    with open(votes_path, "w") as f:
        json.dump(draft_votes(), f, indent=1)
        f.write("\n")

    print(f"drafted {inputs_path}")
    print(f"drafted {votes_path}")
    print(f"{TODO!r} markers need judgment before scripts/publish.py {s}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    main(sys.argv[1])

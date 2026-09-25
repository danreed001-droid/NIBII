#!/usr/bin/env python3
"""Fetch a live price snapshot for every asset's TICKERS entry and write it
to documents/live.json.

Purely a display overlay for the report's ticker strip - it never touches a
published documents/<date>.json, never influences a call, and is not part
of the blindness-rule-governed data path (fetch.py's closes_through/
ohlc_through). This is "what is this instrument trading at right now",
refreshed by the same twice-daily GitHub Actions run that settles/drafts,
now that TICKERS is mostly futures and actually has something fresh to
show outside cash-market hours.

Usage:
    python scripts/fetch_live.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.fetch import TICKERS, fetch_closes


def main():
    prices = {}
    for key, ticker in TICKERS.items():
        rows = fetch_closes(ticker, period="5d")
        if rows:
            as_of, price = rows[-1]
            prices[key] = dict(ticker=ticker, price=price, asOf=as_of)
        else:
            prices[key] = dict(ticker=ticker, price=None, asOf=None)

    out = dict(fetchedAt=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), prices=prices)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "documents", "live.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

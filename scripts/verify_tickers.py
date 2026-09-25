#!/usr/bin/env python3
"""One-off: confirm a set of candidate Yahoo tickers actually resolve and
report their latest daily close + hourly-bar availability. This sandbox
blocks Yahoo Finance, so this runs via a temporary GitHub Actions
diagnostic step instead - see .github/workflows/daily-fetch.yml history.
Removed once its job is done.

Usage:
    python scripts/verify_tickers.py ES=F NQ=F ZN=F DX=F RTY=F
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.fetch import fetch_closes, fetch_ohlc


def main(tickers):
    for t in tickers:
        try:
            closes = fetch_closes(t, period="5d")
            hourly = fetch_ohlc(t, interval="60m", period="5d")
            last = closes[-1] if closes else None
            print(f"{t}: daily_rows={len(closes)} last={last} hourly_rows={len(hourly)}")
        except Exception as e:
            print(f"{t}: ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])

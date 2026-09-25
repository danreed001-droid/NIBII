#!/usr/bin/env python3
"""One-off: recompute market-structure signals for an already-published
session date using the CURRENT mtl.fetch.TICKERS (now mostly futures, for
24h coverage) and print them as JSON, so they can be patched in as a
replacement for structure data computed under the old ETF/index tickers.

Only needed because 2026-09-24 was structure-backfilled once already under
the pre-futures-swap tickers; this reruns that same read against the new
24h tickers. Not a blindness violation: 2026-09-24 has fully closed and
this only reads bars dated on or before it, exactly like prepare_daily.py's
fetch_structure() does at real draft time.

Usage:
    python scripts/dump_structure.py 2026-09-24
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.build import ASSET_ORDER
from mtl.fetch import TICKERS
from scripts.prepare_daily import fetch_structure


def main(s: str):
    out = {key: dict(ticker=TICKERS[key], **fetch_structure(TICKERS[key], s)) for key in ASSET_ORDER}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "structure_dump.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    main(sys.argv[1])

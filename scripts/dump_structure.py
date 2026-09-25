#!/usr/bin/env python3
"""One-off: compute market-structure signals for an already-published session
date and print them as JSON, so they can be patched into that date's
contracts/inputs and documents files after the fact.

Only needed because contracts/inputs.2026-09-24.json and documents/2026-09-24.json
were drafted/published before mtl/structure.py existed, so they have no
`structure` field at all - not even a TODO. Recomputing it now is not a
blindness violation: 2026-09-24 has fully closed and this only reads bars
dated on or before it, exactly like prepare_daily.py's fetch_structure()
would have at draft time.

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


def main(s: str, out_path: str):
    out = {key: fetch_structure(TICKERS[key], s) for key in ASSET_ORDER}
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD OUT_PATH")
    main(sys.argv[1], sys.argv[2])

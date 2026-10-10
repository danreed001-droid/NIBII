#!/usr/bin/env python3
"""Fetch daily closes since 2000 for the growth ranking grid's six markets
(see mtl/growth_rank.py), write the weekly + daily grids to
documents/growth_rank.json (with the last ~6 months of closes for the overlay
chart), which scripts/render_html.py draws, and the full
history to docs/growth_history.json for the page's "ending on" date picker.

A display overlay only, like fetch_live.py: it never touches a published
documents/<date>.json or influences a call. A failed fetch keeps the
previous file rather than blanking the section.

Usage:
    python scripts/fetch_growth_rank.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl import growth_rank
from mtl.fetch import fetch_closes


def main():
    rows = {}
    for ticker, _name in growth_rank.GRID_ASSETS:
        try:
            rows[ticker] = fetch_closes(ticker, start=growth_rank.HISTORY_FROM, period=None)
        except Exception as e:  # noqa: BLE001 - display overlay, never fatal
            print(f"{ticker}: fetch failed: {e}")
    now = datetime.now(timezone.utc)
    grids = growth_rank.build({t: r for t, r in rows.items() if r}, now.date())
    if not grids:
        print("no data came back - keeping the previous growth_rank.json")
        return
    out = dict(fetchedAt=now.strftime('%Y-%m-%dT%H:%M:%SZ'), **grids)
    hist = growth_rank.history({t: r for t, r in rows.items() if r})
    ov = growth_rank.overlay(hist)
    if ov:
        out["overlay"] = ov   # the six-line chart above the grids (last ~6 months, daily)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "documents", "growth_rank.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"wrote {out_path}")
    # the full daily history, loaded by the page only when the viewer picks an end date
    if hist:
        hist_path = os.path.join(root, "docs", "growth_history.json")
        with open(hist_path, "w") as f:
            json.dump(dict(fetchedAt=out["fetchedAt"], **hist), f, separators=(",", ":"))
        print(f"wrote {hist_path} ({len(hist['days'])} days)")


if __name__ == "__main__":
    main()

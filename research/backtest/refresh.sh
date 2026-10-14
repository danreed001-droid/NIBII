#!/usr/bin/env bash
# Rebuild data/track_record.json (the dashboard's track record) from a fresh point-in-time backtest.
# Run from anywhere inside the repo; needs network (Yahoo Finance, Wikipedia's S&P 500 changes) and about 20-40 minutes.
#   bash research/backtest/refresh.sh
# The engine is the "robustness" branch at BASE with the files in research/backtest/overlay copied over it.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
BASE=2482d03db8ec6659ffd4a6f6a9bc1056aa01c819
WORK=${WORK:-$(mktemp -d)}
echo "work folder: $WORK"
git -C "$REPO" fetch -q origin robustness || true
git -C "$REPO" cat-file -e "$BASE^{commit}"
rm -rf "$WORK/engine"
git -C "$REPO" worktree add -q --detach "$WORK/engine" "$BASE"
cleanup() { git -C "$REPO" worktree remove --force "$WORK/engine" 2>/dev/null || true; }
trap cleanup EXIT
cp -r "$REPO/research/backtest/overlay/." "$WORK/engine/"
cp "$REPO"/data/sp500.csv "$REPO"/data/sp500.asof "$REPO"/data/ndx100.csv "$REPO"/data/ndx100.asof "$WORK/engine/data/" 2>/dev/null || true
export HARNESS_SIDE="$WORK/side" NIBII_REPO="$REPO"
echo "1/3 side series (gold, bonds, dollar, VIX, rates)"
python "$REPO/research/backtest/side_data.py" "$HARNESS_SIDE"
echo "2/3 backtest from 2000 (fetches the point-in-time S&P 500 universe the first time)"
(cd "$WORK/engine" && env DUMP_CURVES=NBup_boost,B1S_boost,N1_auto DUMP_DAILY=1 TAG=_track START=2000-01-03 FROM=1998-06-01 \
    EXCLUDE=EP,CPWR ONLY=NBup,B1S,N1 python scripts/improve.py > "$WORK/backtest.log" 2>&1) || { tail -30 "$WORK/backtest.log"; exit 1; }
grep -E "_(boost|auto): pre" "$WORK/backtest.log" || true
echo "3/3 data/track_record.json"
python "$REPO/research/backtest/build_track.py" "$WORK/engine/data/curves_dump_track.json" "$REPO/data/track_record.json"

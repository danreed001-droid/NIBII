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
python -c "import yfinance, lxml, numpy" 2>/dev/null || pip install -q -r "$REPO/requirements.txt"
git -C "$REPO" cat-file -e "$BASE^{commit}" 2>/dev/null || git -C "$REPO" fetch -q origin robustness
git -C "$REPO" cat-file -e "$BASE^{commit}"
git -C "$REPO" worktree prune
rm -rf "$WORK/engine"
git -C "$REPO" worktree add -q --detach "$WORK/engine" "$BASE"
cleanup() { git -C "$REPO" worktree remove --force "$WORK/engine" 2>/dev/null || true; }
trap cleanup EXIT
cp -r "$REPO/research/backtest/overlay/." "$WORK/engine/"
cp "$REPO"/data/sp500.csv "$REPO"/data/sp500.asof "$REPO"/data/ndx100.csv "$REPO"/data/ndx100.asof "$WORK/engine/data/" 2>/dev/null || true
export HARNESS_SIDE="$WORK/side" NIBII_REPO="$REPO" FROM=1998-06-01
echo "1/5 side series (gold, bonds, dollar, VIX, rates)"
python "$REPO/research/backtest/side_data.py" "$HARNESS_SIDE"
echo "2/5 point-in-time S&P 500 universe and prices"
(cd "$WORK/engine" && python -c "import sys; sys.path[:0] = ['scripts', '.']; import robustness; robustness.load_data()" \
    > "$WORK/universe.log" 2>&1) || { tail -30 "$WORK/universe.log"; exit 1; }
grep -E "universe:" "$WORK/universe.log" || true
echo "3/5 daily volumes"
python "$REPO/research/backtest/volume_data.py" "$WORK/engine/data/.robust_$FROM.pkl" "$HARNESS_SIDE" > "$WORK/volume.log" 2>&1 \
    || { tail -30 "$WORK/volume.log"; exit 1; }
tail -1 "$WORK/volume.log"
echo "4/5 backtest from 2000"
(cd "$WORK/engine" && env DUMP_CURVES=NBup_boost,B1S_boost,N1_auto DUMP_DAILY=1 TAG=_track START=2000-01-03 \
    EXCLUDE=EP,CPWR ONLY=NBup,B1S,N1 python scripts/improve.py > "$WORK/backtest.log" 2>&1) || { tail -30 "$WORK/backtest.log"; exit 1; }
grep -E "_(boost|auto): pre" "$WORK/backtest.log" || true
echo "5/5 data/track_record.json"
python "$REPO/research/backtest/build_track.py" "$WORK/engine/data/curves_dump_track.json" "$REPO/data/track_record.json"

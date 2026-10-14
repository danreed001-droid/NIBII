# Backtest engine (track record refresh)

The dashboard's growth chart and year table (`data/track_record.json`) come from this point-in-time backtest,
not from the scanner's replay. The replay uses today's S&P 500 and Nasdaq-100 members, so it never holds a
stock that later dropped out and looks better than it should. This backtest uses:

- the stocks in the S&P 500 at each date, delisted ones included (EP and CPWR are left out because their
  tickers were reused);
- news gaps, and 0.15% slippage on every trade;
- TLT and GLD extended back with a long Treasury fund and gold futures for the years before they existed.

It starts on Jan 3, 2000. After the backtest's last day, `scripts/render_scanner.py` carries each line forward
with the scanner's daily moves.

## Refresh

```
bash research/backtest/refresh.sh
```

The script needs network access (Yahoo Finance, and Wikipedia's list of S&P 500 changes) and takes about
20–40 minutes. It:

1. Checks out the engine (the `robustness` branch at a fixed commit, `BASE` in the script) as a temporary git
   worktree, then copies `overlay/` over it.
2. Rebuilds the side series with `side_data.py`: gold, bonds, the dollar, VIX and rates.
3. Runs the backtest for the default plan (`NBup`), Boost 100% (`B1S`) and the plain top 5 (`N1`), from 2000
   to the last close. On the first run it downloads the point-in-time S&P 500 universe.
4. Writes `data/track_record.json` with `build_track.py`, and prints each line's return a year and worst drop.

Then re-render the page and run the tests:

```
python scripts/render_scanner.py
python -m pytest -q
```

Run the refresh every 3 months. As of Oct 2026 the default made about 37% a year from 2000, with a −31%
worst drop. A big jump in either number means something changed in the data or the engine: check before you
publish it.

## Files

| File | What it is |
|---|---|
| `refresh.sh` | the whole refresh, end to end |
| `side_data.py` | side series from Yahoo Finance into a folder (`xasset.json`, `vix_irx.json`, `rates/tnx.json`, `spliced.json`) |
| `build_track.py` | the engine's curve dump → `data/track_record.json` |
| `overlay/scripts/improve.py` | the engine's rule variants (`NBup` is the default plan) |
| `overlay/scripts/chan_lines.py` | trendline and channel finders the trendline variants use |
| `overlay/mtl/momentum.py` | the engine's momentum module, as tested |

The engine reads the side series from `$HARNESS_SIDE` and this repo from `$NIBII_REPO`, and `refresh.sh` sets
both. When a rule changes the default plan, update its variant in `overlay/scripts/improve.py` to match, and
the `KEYS` in `build_track.py` if the variant gets a new name.

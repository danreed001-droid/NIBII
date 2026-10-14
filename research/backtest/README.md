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

## When it runs

The **Track record refresh** workflow (`.github/workflows/track-refresh.yml`) runs every 3 months, on Jan 5,
Apr 5, Jul 5 and Oct 5. It also runs from the **Refresh now** button at the bottom of the dashboard, which opens
the workflow on GitHub (tap **Run workflow**). A run takes about 15 minutes:

1. Rerun the backtest (`refresh.sh`).
2. Compare the new numbers with the published ones (`compare_track.py`). If the default plan's return a year
   moved more than 3 points, or its worst drop more than 5, it stops without publishing, because that means
   something changed in the data or the engine. Run it with **Publish even if the numbers moved a lot** ticked
   to publish anyway.
3. Rank today's stocks, render `docs/scanner.html`, and push it with `data/track_record.json` to main.

Since Oct 14, 2026 the narrow-market warning is read from the equal-weight index's full history (2003 on),
so the backtest includes the three cash weeks of 2006–07 that the original audit missed. That took about half
a point a year off: the default made about 36% a year from 2000. Its worst drop became −33% (May to
Oct 2006, when two of those cash weeks held gold as it fell), from −31% in 2001–02. Two runs on Oct 14, 2026
differed by 0.4 points. Yahoo's dividend-adjusted prices differ slightly from one download to the next, and that
flipped one close call between stocks, gold and bonds in Oct 2001; the difference then compounds over 25 years. So
read the figure as accurate to about half a point. Boost 100% and the plain top 5 came out the same both times.

Since Oct 14, 2026 the default (`NBup`) includes the rebound rule (`mtl/rebound.py`): while SPY is 12%+ under its
63-session high, gold or bonds is up 2%+ since that high and SPY's daily chart has made a higher low, it holds the
Boost list over every other rule. The refresh that day put the default at 37.2% a year from 2000 (worst drop −33%),
up from 36.0%; the audit data gives 37.8% vs 36.5% without it. `NBpre` is the default before the rule.

## Run it by hand

```
bash research/backtest/refresh.sh
python scripts/render_scanner.py     # needs data/momentum_scan.json from python scripts/momentum_scan.py
python -m pytest -q
```

`refresh.sh` needs network access (Yahoo Finance, and Wikipedia's list of S&P 500 changes). It:

1. Checks out the engine as a temporary git worktree: the `robustness` branch at a fixed commit (`BASE` in the
   script). Keep that branch. The script then copies `overlay/` over the worktree.
2. Rebuilds the side series with `side_data.py`: gold, bonds, the dollar, VIX and rates.
3. Downloads the point-in-time S&P 500 universe and its prices.
4. Downloads daily volumes for those stocks, plus SPY and QQQ, with `volume_data.py`. The blow-off exit needs them.
5. Runs the backtest for the default plan (`NBup`), Boost 100% (`B1S`) and the plain top 5 (`N1`), from 2000 to
   the last close. Then it writes `data/track_record.json` with `build_track.py` and prints each line's return a
   year and worst drop.

## Files

| File | What it is |
|---|---|
| `refresh.sh` | the whole rebuild, end to end |
| `side_data.py` | side series from Yahoo Finance (`xasset.json`, `vix_irx.json`, `rates/tnx.json`, `spliced.json`) |
| `volume_data.py` | daily volumes (`stock_volume.npz`, `spy_volume.json`) |
| `build_track.py` | the engine's curve dump → `data/track_record.json` |
| `compare_track.py` | the published vs the rebuilt track record; exits 1 when the default moved too much |
| `overlay/scripts/improve.py` | the engine's rule variants (`NBup` is the default plan) |
| `overlay/scripts/chan_lines.py` | trendline and channel finders the trendline variants use |
| `overlay/mtl/momentum.py` | the engine's momentum module, as tested |

The engine reads the side series and volumes from `$HARNESS_SIDE` and this repo from `$NIBII_REPO`;
`refresh.sh` sets both. Some research variants also read a breadth series (`breadth_series.json`) that isn't
built here. The three variants in the track record don't use it.

When a rule changes the default plan, update its variant in `overlay/scripts/improve.py` to match. If the
variant gets a new name, update the `KEYS` in `build_track.py` and `ONLY` / `DUMP_CURVES` in `refresh.sh` too.

# Market structure detection: spec

A starting spec for extending `mtl/structure.py` beyond HH/HL swing labeling.
It defines each concept precisely enough to implement deterministically,
records what the code already does, and lists what is still missing.

Ground rules carried over from the rest of the package:

- **Deterministic.** The same bars always produce the same output. No
  discretionary reads.
- **Blindness-safe.** Only bars at or before the snapshot time `S` are used.
  Anything that needs future bars to confirm (a fractal swing, for example)
  is only reported once those bars exist.
- **Degrade, don't guess.** Too little data returns `None` plus a `note`,
  never a fabricated read.
- **Bars** are `[(ts, o, h, l, c), ...]`, oldest first, as everywhere else.

---

## 1. Swing highs and lows (implemented)

`find_swings(bars, n)` uses an N-bar fractal:

- Bar `i` is a **swing high** if `high[i] == max(high[i-n .. i+n])`.
- Bar `i` is a **swing low** if `low[i] == min(low[i-n .. i+n])`.
- A single wide-range bar can be both.

**Confirmation lag:** a swing at bar `i` can only be known at bar `i+n`.
The last `n` bars of any series can never be swings yet. Any new detector
built on swings inherits this lag and must not act on a swing before
`i+n`.

Current parameters: `HOURLY_SWING_N = 3` (1D horizon) and
`WEEKLY_SWING_N = 2` (5D/10D horizons).

Open question: `>=`/`==` ties mean two equal adjacent highs both qualify.
Decide whether to keep both, keep only the first, or keep only the last,
and add a test that pins the choice.

## 2. HH / HL / LH / LL labeling and trend state (implemented)

`label_structure` compares each swing to the previous swing of the **same
type**:

| Swing | vs previous high | vs previous low |
|-------|------------------|-----------------|
| high  | `HH` if higher, `LH` if lower | — |
| low   | — | `HL` if higher, `LL` if lower |

The first swing of each type and exact ties get `label=None`.

`trend_state` reads the last `STRUCTURE_LOOKBACK = 4` labeled swings:

- `uptrend`: all are `HH`/`HL`
- `downtrend`: all are `LH`/`LL`
- `choppy`: a mix
- `None`: fewer than 2 labeled swings

This feeds category 13 (weight 3) through `vote_from_signal`.

## 3. Break of structure (BOS) and change of character (CHoCH) (implemented: `structure_breaks`)

The current `last_break` flags the latest swing whose *label* contradicts
the prior trend, for example a fresh `LL` after a run of `HH`/`HL`. That is
a label-based reversal signal. It is not the price-level break that
traders mean by BOS/CHoCH, and it only fires once the contradicting swing
is confirmed `n` bars later. Proposed definitions:

**Reference levels.** At each bar `t`, using only swings confirmed by `t`:

- `ref_high` = price of the most recent confirmed swing high
- `ref_low`  = price of the most recent confirmed swing low

**Break test.** Use the **close** by default. A wick through the level is
not a break. Make this a parameter (`break_on='close'|'wick'`).

- Bullish break at bar `t`: `close[t] > ref_high`
- Bearish break at bar `t`: `close[t] < ref_low`

Each reference level can be broken only once. After a break, wait for a new
swing of that type before another break in that direction can fire.

**Classification.** This uses the trend in force *before* the break, from
`trend_state` or from the direction of the previous break:

| Prior trend | Bullish break | Bearish break |
|-------------|---------------|---------------|
| uptrend     | **BOS** (continuation) | **CHoCH** (reversal) |
| downtrend   | **CHoCH** (reversal) | **BOS** (continuation) |
| choppy / None | `break` (unclassified) | `break` (unclassified) |

Output per event:

```python
{'i': t, 'ts': ts, 'kind': 'BOS'|'CHoCH'|'break',
 'direction': 'bull'|'bear', 'level': ref_price,
 'ref_swing_i': index_of_broken_swing, 'close': close[t]}
```

Notes:

- Reacting to the close at bar `t` removes the `n`-bar lag on the event
  itself. The reference swing still had to be confirmed first.
- Keep `last_break` as it is so the golden test is unaffected. Add a new
  `structure_breaks(bars, n, break_on='close')` beside it. Category 13
  should not use BOS/CHoCH until a separate, deliberate weighting decision
  is made.

## 4. Fair value gaps (FVG) (to build)

This is a three-candle imbalance. For candles `i-1`, `i`, `i+1`:

- **Bullish FVG:** `low[i+1] > high[i-1]`. The gap is
  `[high[i-1], low[i+1]]`.
- **Bearish FVG:** `high[i+1] < low[i-1]`. The gap is
  `[high[i+1], low[i-1]]`.

The FVG is attributed to the middle candle `i` and is known at bar `i+1`.

Parameters:

- `min_gap`: ignore gaps smaller than this. Express it as a fraction of
  price, or as a multiple of ATR so one setting works across assets with
  very different price levels (SPX vs ZN vs DXY). Default to an ATR
  multiple, for example `0.1 * ATR(14)`.

**Mitigation** (tracked forward from `i+2`):

- A bullish FVG is **partially filled** when a later `low` enters the gap,
  and **fully filled** when a later `low <= gap_low`.
- A bearish FVG is the mirror image, using `high`.
- Report `filled_pct` (0–1) and `filled_at` (bar index, or `None`).

Output:

```python
{'i': i, 'ts': ts, 'direction': 'bull'|'bear',
 'top': float, 'bottom': float, 'size': float,
 'filled_pct': float, 'filled_at': int|None}
```

Useful summary for a vote or badge: the nearest **unfilled** FVG above and
below the last close, plus its distance in ATR.

Edge case: weekly bars resampled with `weekly_from_daily` have a partial
final week, so its high and low can still change. Do not report an FVG
whose `i+1` candle is the partial week.

## 5. Multi-timeframe alignment (partly built: `mtl/mtf.py` / `scripts/mtf_scan.py` buy scanner)

Today each horizon reads one timeframe: 1D reads hourly, and 5D/10D read
weekly. Nothing checks whether the timeframes agree. Proposal:

**Timeframes:** hourly (`60m`), daily, and weekly (resampled locally from
daily, as now). All are cut at `S`.

**Per-timeframe read:** `trend_state` plus the most recent BOS/CHoCH from
section 3.

**Alignment score** for a horizon, using a higher timeframe (HTF) and a
lower timeframe (LTF):

| HTF       | LTF       | Alignment |
|-----------|-----------|-----------|
| uptrend   | uptrend   | `aligned_bull` |
| downtrend | downtrend | `aligned_bear` |
| uptrend   | downtrend, or recent bearish CHoCH | `conflict` (LTF pullback in HTF uptrend) |
| downtrend | uptrend, or recent bullish CHoCH | `conflict` (LTF rally in HTF downtrend) |
| any       | choppy / None | `htf_only` |
| choppy / None | any   | `unclear` |

Suggested pairs:

- 1D horizon: HTF = daily, LTF = hourly
- 5D/10D horizons: HTF = weekly, LTF = daily

Output this as **informational first**, stored beside `structure.hourly` /
`structure.weekly` and shown as a badge. Only after it has a settled track
record (see `scripts/patterns.py` and its `MIN_SAMPLES` discipline) should
anyone consider letting it move a vote.

---

## Implementation checklist

1. `structure_breaks()` (section 3), with tests on hand-built bar series:
   a continuation BOS, a CHoCH, a wick-only non-break, and no event before
   the reference swing is confirmed.
2. `find_fvgs()` with mitigation tracking (section 4), with tests for a
   bullish gap, a bearish gap, partial fill, full fill, the `min_gap`
   filter, and the partial-week guard.
3. `mtf_alignment()` (section 5), as a pure function over two
   `structure_signal`-style dicts, with one test per row of the table.
4. Wire 1–3 into `prepare_daily.py` / `build.py` as **informational fields
   only**. `tests/test_golden.py` must still pass unchanged.
5. Render badges in `scripts/render_html.py`.
6. Any change to category 13 or a new mechanical category is a separate,
   explicit decision. It changes the golden board, so the README's
   "Market structure" section and `mtl.resolve.WEIGHT` would need updating
   together.

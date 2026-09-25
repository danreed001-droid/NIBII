# Market Tape Ledger — deterministic engine

The arithmetic half of the daily cross-asset "Market Tape Ledger" cycle, lifted
out of the Claude prompt and into version control.

A twelve-category vote model with a mean-reversion overlay calls **six markets**
(SPX, TLT, spot gold, DXY, IWM, QQQ) bullish / bearish / flat over **1, 5 and 10
NYSE sessions** — 18 cells a day.

## Why this exists

Everything here has exactly one correct output for a given input, so a model
should not be re-deriving it by hand every morning. Re-deriving it by hand is
how a tier table silently drifts. Extracting it buys two things:

1. **Correctness.** `tests/test_golden.py` asserts the engine reproduces the
   published 2026-09-24 board — all 18 cells, all six stretch scores, both
   experiments — *exactly*. Any drift in a threshold or tier table fails CI.
2. **Cost.** The model's daily job shrinks to research plus 72 vote reasons.

## The split — this is the important part

| Stays with the model (judgment) | Lives here (deterministic) |
|---|---|
| 72 `(side, reason)` pairs — 6 assets x 3 horizons x 12 categories | bands, flat zones |
| Whether a fact is genuinely two-sided -> `neu` | tally -> margin -> call -> confidence tier |
| Turning news / calendar / auctions into signed votes | cluster downgrade (family map + notch table) |
| Adjudicating vendor conflicts | shadow recompute at threshold 3 |
| Whether a source's own language names a **documented extreme** (`volRegime`, `crowd`) | the four measurable stretch components |
| The `dataNotes` narrative | overlay: rides / opposes / veto / dampen |
| | maturity dates, settlement, correctness flags, vote marks |
| | driver regime (corr, beta, big-day subset) |
| | the record, and the verifier |

The model emits two files; the engine derives everything else:

```
contracts/inputs.<S>.json   every NUMBER, each with its provenance and date
contracts/votes.<S>.json    the 72 (side, reason) pairs
```

```python
from mtl.build import build_document
from mtl.verify import verify_document

doc = build_document(inputs, votes)
assert verify_document(doc) == []
```

## Modules

| Module | Owns |
|---|---|
| `bands.py` | `band(h) = 0.5 * (sigma/100) * sqrt(h/252)`, daily sigma, flat zones |
| `resolve.py` | live gate (<7 -> no-call), margin, tier table, family map, cluster downgrade, shadow threshold |
| `stretch.py` | stretch-v1: six components and their thresholds, label, `rides`/`opposes`/`none`, the margin-4 veto, the one-notch dampen. **Asserts the overlay can never flip a direction.** |
| `score.py` | realized return, outcome vs band, `correct` / `shadowCorrect` / `preReversionCorrect`, vote marking, the `scored` flag |
| `calendar_nyse.py` | NYSE sessions, +1/+5/+10 maturities, holiday rolls |
| `drivers.py` | correlations, betas, big-2Y-day subset, dominance at \|corr\| >= 0.40, plus `check_vote_signs` |
| `record.py` | hit rate, edge units, by asset / horizon / tier, +4-vs-+3, overlay comparison **restricted to changed cells with retroactive documents segregated** |
| `verify.py` | recomputes every derived field from scratch; `assert_no_reason_drift` catches a reason string changing during scoring |
| `fetch.py` | yfinance (+ FRED for the 2-year) layer. Computes RSI and moving averages **locally** from the close series |
| `structure.py` | swing highs/lows and HH/HL/LH/LL trend labeling - see "Market structure" below |
| `build.py` | inputs + votes -> document |

## The daily cycle

```bash
python scripts/prepare_daily.py 2026-09-25   # fetches data, drafts contracts/*.2026-09-25.json
#  -> fill in every "TODO" field by hand: direction, driverNote, categories,
#     volRegime, crowd, stretchDrivers, nullInputs, and all 72 votes
python scripts/publish.py 2026-09-25         # builds, verifies, writes documents/2026-09-25.json
python scripts/render_html.py 2026-09-25     # writes documents/latest.html - overwritten each run.
#  documents/<S>.json stays one file per day (the actual scored ledger);
#  only this rendered display copy is disposable and collapsed to one file.
```

`prepare_daily.py` fetches everything `fetch.py` can compute from a close
series (close, sigma-gauge close, RSI, MA50/MA200, 52-week range, and the
driver-regime correlations) and leaves every judgment field as a `"TODO"`
stub — it never invents a vote or a driver note. `publish.py` refuses to run
if any `"TODO"` marker survives, refuses to overwrite an already-published
document, and only writes `documents/<S>.json` if `verify_document` returns
no errors — it never publishes a document that fails its own audit.

Documents live in `documents/` in this repository, not in the Artifact
database: `ArtifactData` is internal to Claude, and there is no public
endpoint a GitHub Action (or `publish.py` run standalone) can reach. The
Claude task, when it drives this cycle, is a caller of these two scripts, not
a separate runtime — `documents/2026-09-24.json` is the first entry, seeded
from `golden/2026-09-24.published.json`.

## What `fetch.py` fixes

The ledger's own `dataNotes` kept recording the same failures: technical pages
with the 200-day above spot, MA50 and MA200 collapsed onto the same value, RSI
silently dated to a later session, four vendors quoting four different gold
closes, Cboe's CDN two sessions stale, FRED lagging.

Computing RSI and the moving averages from a close series removes that entire
class of bug. `closes_through(ticker, S)` **enforces the blindness rule in code**
— nothing dated after S is ever returned.

Two traps `fetch.py` now resolves rather than just documents:

- **Gold.** `TICKERS['gold']` is `XAUUSD=X` (Yahoo's spot quote), not `GC=F`
  (COMEX futures, ~$50 above spot on cost-of-carry — kept only as
  `FUTURES_GOLD_TICKER` for comparison, never scored).
- **Yields.** `^TNX`/`^FVX`/`^TYX` are yield×10 on Yahoo (a legacy CBOE index
  convention); `scaled_yield()` divides by 10 before the value is used, and
  `^IRX` is excluded from that scaling since it's already a direct
  percentage. yfinance has no 2-year Treasury series, so `fetch_ust2y_fred()`
  sources FRED's `DGS2` instead.

Both fixes are guarded by plausibility asserts (`_assert_plausible_yield`,
`_assert_plausible_gold`) that raise rather than silently accept an
obviously mis-scaled print. **They were not empirically re-verified against
Yahoo Finance in the environment that wrote them** — Yahoo Finance is blocked
by that environment's outbound network policy, so the scaling above rests on
well-documented convention, not a live spot-check. Cross-check one gold print
and one yield against a second source on the first real run before trusting
them unattended.

Also note the 52-week range here is on a **closing** basis over 252 sessions;
vendor pages usually quote the wider intraday range.

## Market structure

`mtl/structure.py` turns the "higher highs and higher lows" / "lower highs
and lower lows" read a trader does by eye on a candlestick chart into a
deterministic computation: an N-bar fractal finds swing highs and lows
(a bar is a swing high if its high is the max within N bars either side),
then each new swing is labeled `HH`/`LH` (relative to the previous swing
high) or `HL`/`LL` (relative to the previous swing low). The most recent
labeled swings classify the state as `uptrend` (HH/HL only), `downtrend`
(LH/LL only), or `choppy` (mixed) - `None` if too few swings exist yet,
never a guess.

The two horizon groups deliberately read different bar sizes:

- **1D** reads **hourly** bars (`ohlc_through(ticker, S, interval="60m")`) -
  a day-ahead call has no business caring about a swing from three weeks
  ago.
- **5D/10D** read **weekly** bars, resampled *locally* from the same
  blindness-safe daily closes (`weekly_from_daily()`) rather than a second
  live Yahoo request - one less thing that could disagree with the rest of
  the document, and it can never leak data past S since it only ever sees
  bars already filtered through S.

`prepare_daily.py` computes both and stores them under each asset's
`structure.hourly` / `structure.weekly`; `build.py` passes them through
untouched (informational, like `stretchInputs` - not itself a vote), and
the report shows a small `1H: ▲ uptrend` / `Weekly: ▼ downtrend` badge on
each horizon. It's there for the model to *cite* when writing the "Trend
structure" category vote, not a silent replacement for that judgment call.

Same caveat as the yield/gold fixes: this reads yfinance's `interval="60m"`
endpoint, which was also unreachable to verify in the environment that
wrote it - whether every ticker in `TICKERS` actually has clean hourly
history on Yahoo (index tickers like `^GSPC` sometimes have gappier
intraday coverage than their ETF equivalents) is unconfirmed. A gap
degrades to `state=None` with a note rather than a wrong answer, but this
wants a first-live-run spot check too.

## News catalysts and pattern analysis

A separate Routine ("Daily market news log") logs dated, ticker-tagged,
sourced market-moving events (macro data, Fed, geopolitics, earnings, deals)
into an Artifact database, independent of this repo. `data/news_log.json` is
a local, durable cache of it (synced by the daily-cycle Routine, since a
plain script can't call the Artifact database itself).

Two things read that cache:

- `scripts/render_html.py` matches each day's catalysts to the relevant
  asset by ticker/keyword and shows them in a "what's been moving this"
  panel per asset - display only, no numbers are parsed out of the log's
  free text.
- `scripts/patterns.py` cross-references catalyst categories against the
  Ledger's own *settled* realized returns (exact numbers from
  `scripts/settle.py`, never anything parsed from the news log's prose) to
  see which catalyst categories have actually preceded which outcomes.
  Every cell is gated behind `MIN_SAMPLES` (15) and reported as unreliable
  below that - with one day of Ledger history this returns nothing yet, and
  that's the honest answer, not a bug.

The daily-cycle Routine also uses the news log as one input (alongside live
web search and the fetched market numbers) when writing votes - it's dated,
sourced, and already covers ~7 weeks of catalysts, so it doesn't need to be
independently rediscovered each morning.

## Honest limits

- **The engine cannot verify `volRegime` or `crowd`.** Both may only be non-zero
  when a source *itself* names a percentile, a record, or a multi-year extreme.
  They arrive as inputs and are recorded verbatim. `crowd` is capped at +/-2.
- **`HOLIDAYS` in `calendar_nyse.py` is hand-maintained.** Extend it per year or
  maturity dates will be wrong.
- **The category record is noise below ~20 marked votes per category.**
  `record.py` returns `byCategoryWarning` saying so; report it, don't rank it.
- **`prepare_daily.py` needs live network access** to Yahoo Finance and FRED,
  which not every environment grants (this one doesn't) — run it somewhere
  that can reach both.

## Test

```bash
pip install -r requirements.txt
python -m pytest tests/ -q          # golden board reproduced exactly, fetch scaling covered
python scripts/run_verify.py documents
```

## Provenance

`golden/2026-09-24.published.json` is the real document written on 2026-09-24
(S = the 2026-09-24 close): TLT at a record-low 79.42 with a stretch score of
-4 `extreme-down`, DXY and QQQ both +3 `extreme-up`, and the overlay changing
5 of 18 cells — including a genuine veto of the bonds 10-day call. The
contracts are the exact inputs and votes behind it.

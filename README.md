# Market Tape Ledger — deterministic engine

The arithmetic half of the daily cross-asset "Market Tape Ledger" cycle, lifted
out of the Claude prompt and into version control.

A thirteen-category vote model with a mean-reversion overlay calls **six
markets** (SPX, 10-year Treasury futures, spot gold, DXY, Russell 2000 futures,
Nasdaq-100 futures) bullish / bearish / flat over **1, 5 and 10 NYSE sessions**
— 18 cells a day. Priced via futures (`ES=F`/`ZN=F`/`GC=F`/`RTY=F`/`NQ=F`)
rather than the cash index/ETF wherever one exists on Yahoo, for 24h coverage
— see "What `fetch.py` fixes" below for what changed and why dollar is the
exception.

## Why this exists

Everything here has exactly one correct output for a given input, so a model
should not be re-deriving it by hand every morning. Re-deriving it by hand is
how a tier table silently drifts. Extracting it buys two things:

1. **Correctness.** `tests/test_golden.py` asserts the engine reproduces the
   published 2026-09-24 board — all 18 cells, all six stretch scores, both
   experiments — *exactly*. Any drift in a threshold or tier table fails CI.
2. **Cost.** The model's daily job shrinks to research plus 216 vote reasons
   (the 13th category's votes are filled in mechanically - see "Market
   structure" below - so the model's workload is unchanged even though the
   category count went up).

## The split — this is the important part

| Stays with the model (judgment) | Lives here (deterministic) |
|---|---|
| 216 `(side, reason)` pairs — 6 assets x 3 horizons x 12 judgment categories | bands, flat zones |
| Whether a fact is genuinely two-sided -> `neu` | tally (**weighted** - category 13 counts 3x) -> margin -> call -> confidence tier |
| Turning news / calendar / auctions into signed votes | cluster downgrade (family map + notch table) |
| Adjudicating vendor conflicts | shadow recompute at threshold 3 |
| Whether a source's own language names a **documented extreme** (`volRegime`, `crowd`) | the four measurable stretch components |
| The `dataNotes` narrative | overlay: rides / opposes / veto / dampen |
| | market structure: HH/HL/LH/LL swing labeling, category 13's 18 votes (6 assets x 3 horizons), filled in mechanically |
| | maturity dates, settlement, correctness flags, vote marks |
| | driver regime (corr, beta, big-day subset) |
| | the record, and the verifier |

The model emits two files; the engine derives everything else:

```
contracts/inputs.<S>.json   every NUMBER, each with its provenance and date
contracts/votes.<S>.json    216 judgment (side, reason) pairs + 18 mechanical
                             ones (category 13) = 234 total
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
| `score.py` | realized return, outcome vs band, `correct` / `shadowCorrect` / `preReversionCorrect`, `real_result` (3-way: correct/incorrect/no-call, a directional call landing flat is a push not a miss), vote marking, the `scored` flag |
| `calendar_nyse.py` | NYSE sessions, +1/+5/+10 maturities, holiday rolls |
| `drivers.py` | correlations, betas, big-2Y-day subset, dominance at \|corr\| >= 0.40, plus `check_vote_signs` |
| `record.py` | hit rate, edge units, by asset / horizon / tier, **each paired with a Real Result rate that excludes no-call pushes**, +4-vs-+3, overlay comparison **restricted to changed cells with retroactive documents segregated** |
| `verify.py` | recomputes every derived field from scratch; `assert_no_reason_drift` catches a reason string changing during scoring |
| `fetch.py` | yfinance (+ FRED for the 2-year) layer. Computes RSI and moving averages **locally** from the close series |
| `structure.py` | swing highs/lows and HH/HL/LH/LL trend labeling - see "Market structure" below |
| `build.py` | inputs + votes -> document |

## The daily cycle

Split across two runtimes, on purpose - each does only what it's actually
suited for:

**GitHub Actions** (`.github/workflows/daily-fetch.yml`, twice on weekdays -
pre-open and mid-afternoon, see "What `fetch.py` fixes" for the exact times -
also runnable manually via `workflow_dispatch`) owns everything that needs
live market data, because it runs on GitHub's own infrastructure with
normal outbound internet - unlike a Claude Code Remote sandbox, which
blocks Yahoo Finance at its network proxy:

```bash
python scripts/settle.py            # marks matured prior calls correct/incorrect
python scripts/prepare_daily.py 2026-09-25   # fetches data, drafts contracts/*.2026-09-25.json,
                                              # if not already drafted/published
# commits and pushes whatever changed
```

**The daily-cycle Routine** (a scheduled Claude session, firing ~20 minutes
after the Actions job) owns everything that needs judgment, and makes no
raw network calls of its own - it doesn't need to, since the numbers it
needs are already sitting in the files the Actions job just pushed:

```bash
# fill in every "TODO" field by hand: direction, driverNote, categories,
# volRegime, crowd, stretchDrivers, nullInputs, and all 216 judgment votes
# (category 13's 18 votes are already filled in - mechanical, not judgment)
python scripts/publish.py 2026-09-25         # builds, verifies, writes documents/2026-09-25.json
python scripts/render_html.py 2026-09-25     # writes documents/latest.html + docs/index.html
```

If you're running this by hand instead, both halves work the same way from
any machine with normal internet access - `prepare_daily.py` doesn't care
who calls it.

`prepare_daily.py` fetches everything `fetch.py` can compute from a close
series (close, sigma-gauge close, RSI, MA50/MA200, 52-week range, and the
driver-regime correlations) and leaves every judgment field as a `"TODO"`
stub — it never invents a vote or a driver note. `publish.py` refuses to run
if any `"TODO"` marker survives, refuses to overwrite an already-published
document, and only writes `documents/<S>.json` if `verify_document` returns
no errors — it never publishes a document that fails its own audit.

Documents live in `documents/` in this repository, not in the Artifact
database: `ArtifactData` is internal to Claude, and the daily-cycle Routine
still can't write documents there from a GitHub Action. `documents/latest.html`
and `docs/index.html` (served by GitHub Pages) are both overwritten each run,
not accumulated per day - `documents/<S>.json` is the one that stays
one-file-per-day, since it's the actual scored ledger.
`documents/2026-09-24.json` is the first entry, seeded from
`golden/2026-09-24.published.json`.

## What `fetch.py` fixes

The ledger's own `dataNotes` kept recording the same failures: technical pages
with the 200-day above spot, MA50 and MA200 collapsed onto the same value, RSI
silently dated to a later session, four vendors quoting four different gold
closes, Cboe's CDN two sessions stale, FRED lagging.

Computing RSI and the moving averages from a close series removes that entire
class of bug. `closes_through(ticker, S)` **enforces the blindness rule in code**
— nothing dated after S is ever returned.

Two traps here, **live-verified 2026-09-25** via the GitHub Actions fetch
workflow (this environment's own network policy blocks Yahoo Finance, so the
first version of this section was written from documented convention and
flagged unverified — a real live check then caught a real bug in it):

- **Gold has no working spot ticker on Yahoo right now.** Both `XAUUSD=X`
  and `XAU=X` — the two spot-quote candidates — returned 404 ("Quote not
  found") live. Only `GC=F` (COMEX futures) returned real data.
  `TICKERS['gold']` is `GC=F` until a working spot source turns up, which
  means the ledger is currently scoring futures, running ~$50 above spot on
  cost-of-carry — a real, open limitation, not a rounding error.
- **`^TNX`/`^FVX`/`^TYX` are NOT yield×10 — that assumption was wrong.** A
  live check returned `^TNX=5.1620` directly as the percent yield (a
  ~5.16% 10-year, not 51.6%). The original divide-by-10 step would have
  silently corrupted every yield by 10x the first time it ran for real.
  `scaled_yield()` now passes values through unscaled; `^IRX` was already
  correct. yfinance still has no 2-year Treasury series, so
  `fetch_ust2y_fred()` sources FRED's `DGS2` instead — also confirmed
  working live (13,127 rows).

`_assert_plausible_yield`/`_assert_plausible_gold` still guard both paths,
so a future Yahoo format change fails loudly instead of publishing a
silently wrong number again.

**Equities/qqq/bonds/iwm switched to futures for 24h coverage — live-verified
2026-09-25 (a second check).** `TICKERS` now reads `ES=F` (S&P 500 e-mini),
`NQ=F` (Nasdaq-100 e-mini), `ZN=F` (10-Year T-Note) and `RTY=F` (Russell 2000
e-mini) instead of `^GSPC`/`QQQ`/`TLT`/`IWM` — all four confirmed live with
real daily and hourly (`interval="60m"`) data, motivated by the 1D horizon's
"1H structure" read needing real pre-open/overnight price action rather than
a series that goes flat outside cash-market hours. Two things worth knowing:

- `NQ=F`/`RTY=F` trade at **index level**, not the old ETF's share price
  (NQ=F ~30,000+ vs QQQ ~$700; RTY=F ~2,800+ vs IWM ~$230) — a real scale
  change, not a small basis like gold's. `scripts/render_html.py`'s display
  label was updated to show the real futures ticker rather than the old ETF
  name, so the report never shows an index-point price under a $-per-share
  label.
- `ZN=F` is **10-Year T-Note futures, a different instrument than TLT** (20+
  Year Treasuries) — shorter duration, different rate sensitivity, a
  different price convention entirely (points and fractions, ~104–115).
  "Bonds" now means 10-year rate exposure via futures, not TLT's own
  duration profile — an ongoing framing change for future sessions'
  judgment votes to write around, not a rounding error.
- `DX=F` **does not exist on Yahoo — live-verified 404**, the same failure
  mode as the gold-ticker check. `TICKERS['dollar']` stays `DX-Y.NYB` (the
  ICE cash index): it updates near-continuously since the underlying FX
  crosses trade ~24h on weekdays, but it is not a discrete futures contract
  like the other four — dollar is the one asset without a true futures swap.

`.github/workflows/daily-fetch.yml` now runs **twice a day** rather than
once — 13:15 UTC (9:15am EDT / 8:15am EST, before the 9:30am ET open) and
19:30 UTC (3:30pm EDT / 2:30pm EST, mid-afternoon) — since the futures
tickers above actually have something fresh to report at both times.
`scripts/settle.py` and `scripts/prepare_daily.py` were already idempotent
(skip an already-settled horizon / an already-drafted date), so the second
run needed no script changes, just the added cron entry.

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
`structure.hourly` / `structure.weekly`; `build.py` passes the raw signal
through untouched too (informational, like `stretchInputs`), and the report
shows a small `1H: ▲ uptrend` / `Weekly: ▼ downtrend` badge on each horizon.

It feeds the vote model two ways, deliberately different:

- **Category 13, "Market structure (HH/HL)," is fully mechanical and
  weighted 3x** (`mtl.resolve.WEIGHT`): `uptrend` -> `bull`, `downtrend` ->
  `bear`, `choppy`/unreadable -> `neu`, filled in by
  `mtl.structure.vote_from_signal()` - never left for a model to judge,
  since it's reporting a computed fact. At weight 3 this one category can
  swing a call on its own (see the docstring in `mtl/resolve.py` and
  `tests/test_weighted_voting.py`'s `test_13th_vote_alone_can_tip...`) -
  that's the tradeoff of weighting it above 1, made deliberately, not a
  side effect.
- **Category 1, "Trend structure," stays judgment** - the model is
  expected to *cite* the same structure read there too (its own MA/RSI
  read plus the swing read, in one sourced sentence), but that vote is
  still authored, not auto-filled.

So the honest answer to "does HH/HL get marked bullish automatically": for
category 13, yes, always, by design, worth 3 points. It doesn't decide the
call by itself outright, but at weight 3 it's the single most powerful
category in the tally - materially different from every other category's
weight of 1.

**Live-verified 2026-09-25** alongside the yield/gold check: `interval="60m"`
returned clean hourly bars for both an index ticker (`^GSPC`, 35 rows) and
an ETF (`TLT`, 35 rows), so intraday coverage isn't the gap it might have
been. `structure_signal` still degrades to `state=None` with a note rather
than guessing if a given ticker's series ever comes up short - that
fallback stays even though the common case now checks out.

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

#!/usr/bin/env python3
"""Render a published ledger document as a self-contained HTML report.

Pure server-side rendering - no client JS required for the page to work; the
vote breakdown uses native <details> disclosure so it degrades to plain HTML.

Usage:
    python scripts/render_html.py 2026-09-24
    # -> documents/2026-09-24.html
"""
import html
import json
import os
import sys

CALL_STATUS = {
    'bullish': ('good', '#0ca30c', '↑'),
    'bearish': ('critical', '#d03b3b', '↓'),
    'flat': ('flat', '#898781', '→'),
    'no-call': ('warning', '#fab219', '?'),
}
VOTE_MARK = {'bull': ('good', '#0ca30c'), 'bear': ('critical', '#d03b3b'), 'neu': ('flat', '#898781')}
STRETCH_TONE = {
    'extreme-down': '#d03b3b', 'stretched-down': '#ec835a', 'neutral': '#898781',
    'stretched-up': '#ec835a', 'extreme-up': '#d03b3b',
}
E = html.escape


def fmt_price(v):
    return f"{v:,.2f}"


def fmt_pct(v):
    return f"{v * 100:+.2f}%"


def call_chip(call, confidence):
    role, hexval, arrow = CALL_STATUS.get(call, ('flat', '#898781', '→'))
    return (f'<span class="chip" style="--dot:{hexval}">'
            f'<span class="dot" aria-hidden="true"></span>'
            f'<span class="chip-label">{arrow} {E(call)}</span>'
            f'<span class="chip-conf">{E(confidence)}</span></span>')


def vote_row(v):
    side = v[0]
    reason = v[1]
    mark = v[2] if len(v) > 2 else None
    role, hexval = VOTE_MARK.get(side, ('flat', '#898787'))
    mark_html = ''
    if mark is not None:
        mark_html = (f'<span class="vote-mark {"hit" if mark else "miss"}">'
                     f'{"correct" if mark else "wrong"}</span>')
    return (f'<li class="vote" style="--dot:{hexval}">'
            f'<span class="dot" aria-hidden="true"></span>'
            f'<span class="vote-text">{E(reason)}</span>{mark_html}</li>')


def horizon_block(a, h):
    votes_html = "".join(vote_row(v) for v in h['votes'])
    reversion = ""
    if h.get('reversionFlag'):
        reversion = f'<p class="reversion">⚠ overlay applied — {E(h["reversionNote"])}</p>'
    elif h.get('reversionNote'):
        reversion = f'<p class="reversion muted">{E(h["reversionNote"])}</p>'

    return f'''
    <div class="horizon">
      <div class="horizon-head">
        <span class="horizon-h">{h['h']}D</span>
        <span class="horizon-maturity">matures {E(h['maturity'])}</span>
      </div>
      {call_chip(h['call'], h['confidence'])}
      <div class="horizon-stats">
        <span>{h['bull']} bull / {h['bear']} bear / {h['neutral']} neu · margin {h['margin']}</span>
        <span>flat zone {fmt_price(h['flatLo'])}–{fmt_price(h['flatHi'])}</span>
      </div>
      {reversion}
      <details class="votes">
        <summary>12 votes</summary>
        <ul>{votes_html}</ul>
      </details>
    </div>'''


def asset_card(a):
    st = a['stretch']
    tone = STRETCH_TONE.get(st['label'], '#898781')
    horizons_html = "".join(horizon_block(a, h) for h in a['horizons'])
    drivers_html = "".join(f'<li>{E(d)}</li>' for d in st.get('drivers', []))
    drivers_block = f'<ul class="drivers">{drivers_html}</ul>' if drivers_html else ''

    return f'''
    <section class="asset">
      <header class="asset-head">
        <div>
          <h2>{E(a['name'])}</h2>
          <p class="instrument">{E(a['instrument'])} · close {fmt_price(a['close'])}</p>
        </div>
        <div class="stretch" style="--tone:{tone}">
          <span class="stretch-score">{st['score']:+d}</span>
          <span class="stretch-label">{E(st['label'])}</span>
        </div>
      </header>
      <p class="driver-note">{E(a['driverNote'])}</p>
      {f'<details class="stretch-drivers"><summary>why this stretch score</summary>{drivers_block}</details>' if drivers_block else ''}
      <div class="horizons">{horizons_html}</div>
    </section>'''


def summary_chips(doc):
    calls = [h['call'] for a in doc['assets'] for h in a['horizons']]
    counts = {k: calls.count(k) for k in ('bullish', 'bearish', 'flat', 'no-call')}
    parts = []
    for call, n in counts.items():
        if n:
            role, hexval, arrow = CALL_STATUS[call]
            parts.append(f'<span class="summary-chip" style="--dot:{hexval}">'
                        f'<span class="dot" aria-hidden="true"></span>{n} {E(call)}</span>')
    return "".join(parts)


PAGE = '''<title>Market Tape Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
    --muted: #898781; --hairline: #2c2c2a; --accent: #3987e5;
    color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #898781; --hairline: #2c2c2a; --accent: #3987e5;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--ink);
  font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding-inline: 16px; padding-block: 32px 64px; max-width: 880px; margin-inline: auto;
}}
h1, h2 {{ font-family: "Fraunces", Georgia, serif; text-wrap: balance; margin: 0; }}
h1 {{ font-size: 2rem; font-weight: 600; }}
h2 {{ font-size: 1.15rem; font-weight: 600; }}
.header {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 8px; }}
.header-top {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; justify-content: space-between; }}
.date {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; color: var(--ink-2); font-size: 0.95rem; }}
.subtitle {{ color: var(--ink-2); margin: 0; }}
.summary-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-block: 16px 28px; }}
.summary-chip {{
  display: inline-flex; align-items: center; gap: 6px; font-size: 0.85rem;
  padding: 4px 10px 4px 8px; border: 1px solid var(--hairline); border-radius: 999px;
  color: var(--ink-2); background: var(--surface);
}}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--dot); flex-shrink: 0; }}
.asset {{
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px;
  padding: 20px; margin-bottom: 18px;
}}
.asset-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }}
.instrument {{ margin: 3px 0 0; color: var(--ink-2); font-size: 0.88rem; font-variant-numeric: tabular-nums; }}
.stretch {{
  display: flex; align-items: baseline; gap: 6px; border-left: 3px solid var(--tone);
  padding-left: 10px; white-space: nowrap;
}}
.stretch-score {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 1.1rem; font-weight: 600; }}
.stretch-label {{ color: var(--ink-2); font-size: 0.85rem; }}
.driver-note {{ color: var(--ink-2); font-size: 0.92rem; margin: 12px 0 0; }}
.stretch-drivers {{ margin-top: 8px; }}
.stretch-drivers summary {{ cursor: pointer; color: var(--accent); font-size: 0.85rem; }}
.stretch-drivers ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--ink-2); font-size: 0.85rem; }}
.horizons {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }}
@media (max-width: 620px) {{ .horizons {{ grid-template-columns: 1fr; }} }}
.horizon {{ border: 1px solid var(--hairline); border-radius: 10px; padding: 12px; }}
.horizon-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }}
.horizon-h {{ font-weight: 600; font-family: ui-monospace, monospace; }}
.horizon-maturity {{ font-size: 0.75rem; color: var(--muted); }}
.chip {{
  display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--hairline);
  border-radius: 999px; padding: 4px 10px 4px 8px; font-size: 0.85rem;
}}
.chip-label {{ text-transform: capitalize; font-weight: 500; }}
.chip-conf {{ color: var(--muted); font-size: 0.78rem; }}
.horizon-stats {{
  display: flex; flex-direction: column; gap: 2px; margin-top: 8px;
  font-size: 0.78rem; color: var(--ink-2); font-variant-numeric: tabular-nums;
}}
.reversion {{ font-size: 0.78rem; margin: 8px 0 0; color: var(--ink); }}
.reversion.muted {{ color: var(--muted); }}
.votes {{ margin-top: 10px; }}
.votes summary {{ cursor: pointer; color: var(--accent); font-size: 0.82rem; }}
.votes ul {{ list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 7px; }}
.vote {{ display: flex; align-items: flex-start; gap: 7px; font-size: 0.82rem; color: var(--ink-2); }}
.vote .dot {{ margin-top: 6px; }}
.vote-text {{ flex: 1; }}
.vote-mark {{ font-size: 0.7rem; white-space: nowrap; padding: 1px 6px; border-radius: 999px; }}
.vote-mark.hit {{ color: #0ca30c; border: 1px solid #0ca30c; }}
.vote-mark.miss {{ color: #d03b3b; border: 1px solid #d03b3b; }}
footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }}
footer a {{ color: var(--accent); }}
</style>

<div class="header">
  <div class="header-top">
    <h1>Market Tape Ledger</h1>
    <span class="date">{date}</span>
  </div>
  <p class="subtitle">6 markets × 3 horizons (1D / 5D / 10D) — 18 calls from a twelve-category vote model, with a stretch/mean-reversion overlay.</p>
</div>
<div class="summary-row">{summary}
  <span class="summary-chip">overlay changed {changed} of 18 cells</span>
  <span class="summary-chip">{scored_label}</span>
</div>

{assets}

<footer>
  Generated by <code>scripts/render_html.py</code> from <code>documents/{date}.json</code> in
  <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a>.
  Every call here is reproducible: <code>mtl.build.build_document</code> derives it from
  <code>contracts/inputs.{date}.json</code> and <code>contracts/votes.{date}.json</code>, and
  <code>mtl.verify.verify_document</code> recomputes it independently. Unsettled cells show no
  correctness mark until their maturity date passes.
</footer>
'''


def render(doc: dict) -> str:
    assets_html = "".join(asset_card(a) for a in doc['assets'])
    return PAGE.format(
        date=doc['date'], summary=summary_chips(doc),
        changed=doc['overlay']['cellsChanged'],
        scored_label="scored" if doc['scored'] else "awaiting settlement",
        assets=assets_html,
    )


def main(s: str):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doc = json.load(open(os.path.join(root, "documents", f"{s}.json")))
    out_path = os.path.join(root, "documents", f"{s}.html")
    with open(out_path, "w") as f:
        f.write(render(doc))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    main(sys.argv[1])

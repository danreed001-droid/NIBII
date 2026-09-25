#!/usr/bin/env python3
"""Render a published ledger document as a self-contained HTML report.

Pure server-side rendering - no client JS required for the page to work; the
vote breakdown uses native <details> disclosure so it degrades to plain HTML.

Usage:
    python scripts/render_html.py 2026-09-24
    # -> documents/latest.html (overwritten each run - see main()'s docstring)
"""
import glob
import html
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.record import aggregate
from mtl.score import outcome, real_result

CALL_STATUS = {
    'bullish': ('good', '#0ca30c', '▲'),
    'bearish': ('critical', '#d03b3b', '▼'),
    'flat': ('flat', '#898781', '▬'),
    'no-call': ('warning', '#fab219', '?'),
}
VOTE_MARK = {'bull': ('good', '#0ca30c'), 'bear': ('critical', '#d03b3b'), 'neu': ('flat', '#898781')}
STRETCH_TONE = {
    'extreme-down': '#d03b3b', 'stretched-down': '#ec835a', 'neutral': '#898781',
    'stretched-up': '#ec835a', 'extreme-up': '#d03b3b',
}
TICKER = {
    # equities/gold keep a small-basis conceptual label (ES=F/GC=F trade
    # close to ^GSPC/spot gold's own scale, same as the gold precedent).
    # bonds/iwm/qqq show the real futures ticker instead of the old ETF
    # label - NQ=F/RTY=F/ZN=F trade at a completely different scale than
    # QQQ/IWM/TLT, so keeping the ETF label would show a wildly
    # wrong-looking number under a familiar name (e.g. "QQQ: 30,902.00").
    'equities': 'SPX', 'bonds': 'ZN=F', 'gold': 'XAU',
    'dollar': 'DXY', 'iwm': 'RTY=F', 'qqq': 'NQ=F',
}
STRETCH_MIN, STRETCH_MAX = -6, 6
E = html.escape


def fmt_price(v):
    return f"{v:,.2f}"


def fmt_pct(v):
    return f"{v * 100:+.2f}%"


def call_chip(call, confidence):
    role, hexval, arrow = CALL_STATUS.get(call, ('flat', '#898781', '▬'))
    return (f'<span class="chip" style="--dot:{hexval}">'
            f'<span class="chip-arrow">{arrow}</span>'
            f'<span class="chip-label">{E(call)}</span>'
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


STRUCTURE_TONE = {
    'uptrend': '#0ca30c', 'downtrend': '#d03b3b', 'choppy': '#898781',
}
STRUCTURE_ARROW = {'uptrend': '▲', 'downtrend': '▼', 'choppy': '↔'}


def structure_badge(sig, timeframe_label):
    """sig is a mtl.structure.structure_signal() dict, or None if this
    document predates the structure field (older published documents)."""
    if not sig or sig.get('state') is None:
        note = (sig or {}).get('note') or 'not enough bars yet'
        return (f'<span class="struct-badge muted" title="{E(note)}">'
                f'{E(timeframe_label)} structure: n/a</span>')
    hexval = STRUCTURE_TONE.get(sig['state'], '#898781')
    arrow = STRUCTURE_ARROW.get(sig['state'], '↔')
    brk = ' · break' if sig.get('lastBreak') else ''
    return (f'<span class="struct-badge" style="--dot:{hexval}">'
            f'<span class="dot" aria-hidden="true"></span>'
            f'{E(timeframe_label)}: {arrow} {E(sig["state"])}{brk}</span>')


def horizon_block(a, h):
    votes_html = "".join(vote_row(v) for v in h['votes'])
    reversion = ""
    if h.get('reversionFlag'):
        reversion = f'<p class="reversion">⚠ overlay applied — {E(h["reversionNote"])}</p>'
    elif h.get('reversionNote'):
        reversion = f'<p class="reversion muted">{E(h["reversionNote"])}</p>'

    structure = a.get('structure') or {}
    if h['h'] == 1:
        struct_html = structure_badge(structure.get('hourly'), '1H')
    else:
        struct_html = structure_badge(structure.get('weekly'), 'Weekly')

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
      <div class="struct-row">{struct_html}</div>
      {reversion}
      <details class="votes">
        <summary>{len(h['votes'])} votes</summary>
        <ul>{votes_html}</ul>
      </details>
    </div>'''


CATALYST_DOT = {'Bullish': '#0ca30c', 'Bearish': '#d03b3b', 'Mixed': '#eda100', 'Neutral': '#898781'}


def catalyst_item(c):
    hexval = CATALYST_DOT.get(c.get('direction'), '#898781')
    impact = c.get('impact', '')
    return (f'<li class="catalyst" style="--dot:{hexval}">'
            f'<span class="dot" aria-hidden="true"></span>'
            f'<span class="catalyst-body">'
            f'<span class="catalyst-meta">{E(c.get("category", ""))} · {E(impact)} impact</span>'
            f'<span class="catalyst-event">{E(c.get("event", ""))}</span>'
            f'</span></li>')


def stretch_gauge(score, label):
    tone = STRETCH_TONE.get(label, '#898781')
    clamped = max(STRETCH_MIN, min(STRETCH_MAX, score))
    pct = (clamped - STRETCH_MIN) / (STRETCH_MAX - STRETCH_MIN) * 100
    return f'''
        <div class="gauge" style="--tone:{tone}" role="img"
             aria-label="stretch score {score}, {E(label)}">
          <div class="gauge-track">
            <span class="gauge-mid"></span>
            <span class="gauge-marker" style="left:{pct:.1f}%"></span>
          </div>
          <div class="gauge-foot">
            <span class="gauge-score">{score:+d}</span>
            <span class="gauge-label">{E(label)}</span>
          </div>
        </div>'''


def asset_card(a, catalysts):
    st = a['stretch']
    horizons_html = "".join(horizon_block(a, h) for h in a['horizons'])
    drivers_html = "".join(f'<li>{E(d)}</li>' for d in st.get('drivers', []))
    drivers_block = f'<ul class="drivers">{drivers_html}</ul>' if drivers_html else ''

    catalysts_block = ''
    if catalysts:
        items = "".join(catalyst_item(c) for c in catalysts)
        catalysts_block = f'''
      <details class="catalysts" open>
        <summary>what's been moving this ({len(catalysts)})</summary>
        <ul>{items}</ul>
      </details>'''

    return f'''
    <section class="asset">
      <header class="asset-head">
        <div>
          <span class="asset-ticker">{E(TICKER.get(a['key'], a['key'].upper()))}</span>
          <h2>{E(a['name'])}</h2>
          <p class="instrument">{E(a['instrument'])} · close {fmt_price(a['close'])}</p>
        </div>
        {stretch_gauge(st['score'], st['label'])}
      </header>
      <p class="driver-note">{E(a['driverNote'])}</p>
      {f'<details class="stretch-drivers"><summary>why this stretch score</summary>{drivers_block}</details>' if drivers_block else ''}
      {catalysts_block}
      <div class="horizons">{horizons_html}</div>
    </section>'''


def ticker_strip(doc):
    items = []
    for a in doc['assets']:
        by_h = {h['h']: h for h in a['horizons']}
        h1 = by_h[1]
        role, hexval, arrow = CALL_STATUS.get(h1['call'], ('flat', '#898781', '▬'))
        horizons_html = "".join(tape_horizon_badge(by_h[h]) for h in (1, 5, 10))
        items.append(f'''
      <div class="tape-item" style="--dot:{hexval}">
        <div class="tape-head">
          <span class="tape-ticker">{E(TICKER.get(a['key'], a['key'].upper()))}</span>
          <span class="tape-price">{fmt_price(a['close'])}</span>
        </div>
        <div class="tape-horizons">{horizons_html}</div>
      </div>''')
    return "".join(items)


def tape_horizon_badge(h):
    role, hexval, arrow = CALL_STATUS.get(h['call'], ('flat', '#898781', '▬'))
    return (f'<span class="tape-badge" style="--dot:{hexval}">'
            f'<span class="tape-badge-h">{h["h"]}D</span>'
            f'<span class="tape-badge-arrow">{arrow}</span></span>')


def stat_tiles(doc):
    calls = [h['call'] for a in doc['assets'] for h in a['horizons']]
    n_bull, n_bear = calls.count('bullish'), calls.count('bearish')
    n_flat, n_nocall = calls.count('flat'), calls.count('no-call')

    extreme = max(doc['assets'], key=lambda a: abs(a['stretch']['score']))
    ex_tone = STRETCH_TONE.get(extreme['stretch']['label'], '#898781')

    def tile(label, value, sub='', tone=None):
        style = f' style="--tone:{tone}"' if tone else ''
        cls = 'stat-tile toned' if tone else 'stat-tile'
        return (f'<div class="{cls}"{style}><span class="stat-label">{E(label)}</span>'
                f'<span class="stat-value">{value}</span>'
                f'{f"<span class=stat-sub>{E(sub)}</span>" if sub else ""}</div>')

    return (
        tile('Bullish calls', n_bull, f'of 18') +
        tile('Bearish calls', n_bear, f'of 18') +
        tile('Flat / no-call', n_flat + n_nocall, f'of 18') +
        tile('Overlay reweighted', doc['overlay']['cellsChanged'], 'of 18 cells') +
        tile('Most stretched', f"{TICKER.get(extreme['key'], extreme['key'].upper())} {extreme['stretch']['score']:+d}",
             extreme['stretch']['label'], tone=ex_tone)
    )


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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
/* Dark is the default look, unconditionally - not keyed off OS preference
   or the viewer's own Claude account theme, since [data-mtl-theme] below
   is this page's own attribute, never the host's shared [data-theme]. Only
   this page's own toggle button can switch it to light. */
:root {{
  --bg: #0d0d0d; --surface: #17181a; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #8b8a85; --hairline: #2c2c2a; --accent: #3987e5; --gold: #d9b46a;
  --masthead-bg: #17181a; --masthead-ink: #ffffff; --masthead-ink-2: #a9adba;
  color-scheme: dark;
}}
/* A page-private attribute, not the host's shared [data-theme] - so this
   page's default can't be overridden by the viewer's own Claude account
   theme setting. Only this page's own toggle ever sets it. */
:root[data-mtl-theme="light"] {{
  --bg: #f4f3ef; --surface: #fdfdfc; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  color-scheme: light;
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--ink); margin: 0;
  font: 15px/1.55 "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.wrap {{ max-width: 920px; margin-inline: auto; padding-inline: 16px; padding-block: 0 64px; }}
h1, h2 {{ font-family: "Fraunces", Georgia, serif; text-wrap: balance; margin: 0; }}
code {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}

/* masthead */
.masthead {{ background: var(--masthead-bg); color: var(--masthead-ink); }}
.masthead-inner {{
  max-width: 920px; margin-inline: auto; padding: 28px 16px 22px;
  border-bottom: 2px solid var(--gold);
}}
.eyebrow {{
  font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--gold); font-weight: 600; margin: 0 0 6px;
}}
.masthead-top {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; justify-content: space-between; }}
.masthead-right {{ display: flex; align-items: center; gap: 10px; }}
h1 {{ font-size: 2.1rem; font-weight: 600; color: var(--masthead-ink); }}
.date {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; color: var(--masthead-ink-2); font-size: 0.95rem; }}
.subtitle {{ color: var(--masthead-ink-2); margin: 8px 0 0; font-size: 0.92rem; }}
.updated {{
  color: var(--masthead-ink-2); margin: 6px 0 0; font-size: 0.75rem;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; opacity: 0.85;
}}

/* ticker strip */
.tape {{
  display: flex; flex-wrap: wrap; gap: 0; margin-top: 20px;
  border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; overflow: hidden;
}}
.tape-item {{
  flex: 1 1 150px; display: flex; flex-direction: column; gap: 8px;
  padding: 10px 14px; border-right: 1px solid rgba(255,255,255,0.12);
  border-top: 3px solid var(--dot);
}}
.tape-item:last-child {{ border-right: none; }}
.tape-head {{ display: flex; align-items: baseline; gap: 8px; }}
.tape-ticker {{ font-family: ui-monospace, monospace; font-weight: 600; font-size: 0.8rem; letter-spacing: 0.04em; color: var(--masthead-ink-2); }}
.tape-price {{ font-family: ui-monospace, monospace; font-size: 1.05rem; font-variant-numeric: tabular-nums; color: var(--masthead-ink); }}
.tape-horizons {{ display: flex; gap: 6px; }}
.tape-badge {{
  display: inline-flex; align-items: center; gap: 4px; font-size: 0.72rem;
  padding: 2px 7px; border-radius: 6px; background: color-mix(in srgb, var(--dot) 16%, transparent);
  color: var(--dot); font-weight: 600;
}}
.tape-badge-h {{ font-family: ui-monospace, monospace; letter-spacing: 0.02em; }}

/* stat tiles */
.stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--hairline);
  border: 1px solid var(--hairline); border-radius: 12px; overflow: hidden; margin-top: -1px; }}
@media (max-width: 720px) {{ .stats {{ grid-template-columns: repeat(2, 1fr); }} }}
.stat-tile {{ background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }}
.stat-tile.toned {{ border-top: 3px solid var(--tone); }}
.stat-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
.stat-value {{ font-family: ui-monospace, monospace; font-size: 1.4rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
.stat-sub {{ font-size: 0.72rem; color: var(--ink-2); text-transform: capitalize; }}

.section-label {{
  font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted);
  font-weight: 600; margin: 36px 0 12px;
}}

/* asset cards */
.asset {{
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px;
  padding: 22px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(11,12,14,0.04), 0 8px 20px -12px rgba(11,12,14,0.12);
}}
.asset-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap; }}
.asset-ticker {{
  display: inline-block; font-family: ui-monospace, monospace; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.06em; color: var(--gold); background: color-mix(in srgb, var(--gold) 14%, transparent);
  padding: 2px 7px; border-radius: 5px; margin-bottom: 6px;
}}
.instrument {{ margin: 3px 0 0; color: var(--ink-2); font-size: 0.88rem; font-variant-numeric: tabular-nums; }}

/* stretch gauge */
.gauge {{ min-width: 190px; }}
.gauge-track {{ position: relative; height: 6px; border-radius: 999px; background: var(--hairline); margin-bottom: 8px; }}
.gauge-mid {{ position: absolute; left: 50%; top: -3px; width: 1px; height: 12px; background: var(--muted); }}
.gauge-marker {{
  position: absolute; top: 50%; width: 14px; height: 14px; border-radius: 50%;
  background: var(--tone); border: 2px solid var(--surface); box-shadow: 0 0 0 1px var(--tone);
  transform: translate(-50%, -50%);
}}
.gauge-foot {{ display: flex; align-items: baseline; gap: 8px; justify-content: flex-end; }}
.gauge-score {{ font-family: ui-monospace, monospace; font-size: 1.15rem; font-weight: 600; color: var(--tone); }}
.gauge-label {{ color: var(--ink-2); font-size: 0.85rem; }}

.driver-note {{ color: var(--ink-2); font-size: 0.92rem; margin: 14px 0 0; }}
.stretch-drivers {{ margin-top: 8px; }}
.stretch-drivers summary {{ cursor: pointer; color: var(--accent); font-size: 0.85rem; }}
.stretch-drivers ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--ink-2); font-size: 0.85rem; }}
.horizons {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }}
@media (max-width: 620px) {{ .horizons {{ grid-template-columns: 1fr; }} }}
.horizon {{ border: 1px solid var(--hairline); border-radius: 10px; padding: 12px; }}
.horizon-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }}
.horizon-h {{ font-weight: 700; font-family: ui-monospace, monospace; letter-spacing: 0.02em; }}
.horizon-maturity {{ font-size: 0.72rem; color: var(--muted); }}
.chip {{
  display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--hairline);
  border-radius: 999px; padding: 4px 10px 4px 8px; font-size: 0.85rem;
}}
.chip-arrow {{ color: var(--dot); font-size: 0.7rem; }}
.chip-label {{ text-transform: capitalize; font-weight: 600; }}
.chip-conf {{ color: var(--muted); font-size: 0.78rem; }}
.struct-row {{ margin-top: 8px; }}
.struct-badge {{
  display: inline-flex; align-items: center; gap: 5px; font-size: 0.74rem;
  color: var(--dot); font-weight: 600; text-transform: capitalize;
}}
.struct-badge.muted {{ color: var(--muted); font-weight: 400; text-transform: none; }}
.struct-badge .dot {{ width: 6px; height: 6px; }}
.horizon-stats {{
  display: flex; flex-direction: column; gap: 2px; margin-top: 10px;
  font-size: 0.78rem; color: var(--ink-2); font-variant-numeric: tabular-nums;
}}
.reversion {{ font-size: 0.78rem; margin: 8px 0 0; color: var(--ink); }}
.reversion.muted {{ color: var(--muted); }}
.votes {{ margin-top: 10px; }}
.votes summary {{ cursor: pointer; color: var(--accent); font-size: 0.82rem; }}
.votes ul {{ list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 7px; }}
.vote {{ display: flex; align-items: flex-start; gap: 7px; font-size: 0.82rem; color: var(--ink-2); }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--dot); flex-shrink: 0; }}
.vote .dot {{ margin-top: 6px; }}
.vote-text {{ flex: 1; }}
.vote-mark {{ font-size: 0.7rem; white-space: nowrap; padding: 1px 6px; border-radius: 999px; }}
.vote-mark.hit {{ color: #0ca30c; border: 1px solid #0ca30c; }}
.vote-mark.miss {{ color: #d03b3b; border: 1px solid #d03b3b; }}
.catalysts {{ margin-top: 16px; border-top: 1px solid var(--hairline); padding-top: 12px; }}
.catalysts summary {{ cursor: pointer; color: var(--accent); font-size: 0.85rem; }}
.catalysts ul {{ list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }}
.catalyst {{ display: flex; align-items: flex-start; gap: 8px; }}
.catalyst .dot {{ margin-top: 6px; }}
.catalyst-body {{ display: flex; flex-direction: column; gap: 2px; }}
.catalyst-meta {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
.catalyst-event {{ font-size: 0.85rem; color: var(--ink-2); }}
footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }}
footer a {{ color: var(--accent); }}

/* track record */
.record {{
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px;
  padding: 22px; margin-top: 8px;
}}
.record-empty {{ color: var(--ink-2); font-size: 0.9rem; }}
.record-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 20px; margin-bottom: 18px; }}
.record-pct {{ font-family: ui-monospace, monospace; font-size: 2rem; font-weight: 600; }}
.record-pct.good {{ color: #0ca30c; }}
.record-pct.critical {{ color: #d03b3b; }}
.record-pct.flat {{ color: var(--ink-2); }}
.record-n {{ color: var(--muted); font-size: 0.85rem; }}
.record-edge {{ font-size: 0.85rem; color: var(--ink-2); }}
.record-head-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; margin: 0 0 6px; }}
.record-row-real {{ color: var(--muted); font-size: 0.72rem; font-weight: 400; margin-left: 8px; }}
.record-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 18px; }}
@media (max-width: 620px) {{ .record-grid {{ grid-template-columns: 1fr 1fr; }} }}
.record-block h3 {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 0 0 8px; font-family: inherit; font-weight: 600; }}
.record-row {{
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 5px 0; border-bottom: 1px solid var(--hairline); font-size: 0.85rem;
}}
.record-row:last-child {{ border-bottom: none; }}
.record-row-label {{ color: var(--ink-2); }}
.record-row-val {{ font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; font-weight: 600; }}
.record-row-n {{ color: var(--muted); font-size: 0.75rem; font-weight: 400; }}
.record-caveat {{ font-size: 0.78rem; color: var(--muted); border-top: 1px solid var(--hairline); padding-top: 12px; margin-top: 4px; }}

/* call log */
.log-wrap {{ overflow-x: auto; border: 1px solid var(--hairline); border-radius: 14px; }}
table.log {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; background: var(--surface); }}
table.log th {{
  text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--muted); font-weight: 600; padding: 10px 14px; border-bottom: 1px solid var(--hairline);
  white-space: nowrap; position: sticky; top: 0; background: var(--surface);
}}
table.log td {{ padding: 9px 14px; border-bottom: 1px solid var(--hairline); white-space: nowrap; vertical-align: middle; }}
table.log tbody tr:last-child td {{ border-bottom: none; }}
table.log tbody tr:hover {{ background: color-mix(in srgb, var(--accent) 6%, transparent); }}
.log-date, .log-matures {{ font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; color: var(--ink-2); font-size: 0.8rem; }}
.log-price {{ font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; color: var(--ink-2); font-size: 0.8rem; text-align: right; }}
.log-ticker {{ font-family: ui-monospace, monospace; font-weight: 600; }}
.log-call {{ display: inline-flex; align-items: center; gap: 5px; text-transform: capitalize; font-weight: 500; }}
.log-call .dot {{ width: 7px; height: 7px; }}
.log-conf {{ color: var(--muted); font-size: 0.78rem; }}
.log-pending {{ color: var(--muted); font-size: 0.78rem; }}
.log-noscore {{ color: var(--muted); font-size: 0.78rem; }}
.log-correct {{ color: #0ca30c; font-weight: 600; }}
.log-wrong {{ color: #d03b3b; font-weight: 600; }}
.log-nocall {{ color: var(--gold); font-weight: 600; }}
.log-caption {{ font-size: 0.78rem; color: var(--muted); margin: 10px 2px 0; }}

.theme-toggle {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.18);
  background: transparent; color: var(--masthead-ink-2); cursor: pointer; flex-shrink: 0;
}}
.theme-toggle:hover {{ color: var(--gold); border-color: var(--gold); }}
.theme-toggle svg {{ width: 15px; height: 15px; }}
</style>

<div class="masthead">
  <div class="masthead-inner">
    <p class="eyebrow">Daily Briefing</p>
    <div class="masthead-top">
      <h1>Market Tape Ledger</h1>
      <span class="masthead-right">
        <span class="date">{date}</span>
        <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dark/light theme">
          <svg id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4"></circle>
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>
          </svg>
          <svg id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden>
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"></path>
          </svg>
        </button>
      </span>
    </div>
    <p class="subtitle">6 markets × 3 horizons (1D / 5D / 10D) — 18 calls from a thirteen-category vote model, with a stretch/mean-reversion overlay.</p>
    <p class="updated">Last updated {generated_at}</p>
    <div class="tape">{tape}</div>
  </div>
</div>

<div class="wrap">
<div class="stats">{stats}</div>

<p class="section-label">The board</p>
{assets}

<p class="section-label">Track record</p>
{record}

<p class="section-label">Call log</p>
{log}

<footer>
  Generated by <code>scripts/render_html.py</code> from <code>documents/{date}.json</code> in
  <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a>.
  Every call here is reproducible: <code>mtl.build.build_document</code> derives it from
  <code>contracts/inputs.{date}.json</code> and <code>contracts/votes.{date}.json</code>, and
  <code>mtl.verify.verify_document</code> recomputes it independently. Unsettled cells show no
  correctness mark until their maturity date passes.
</footer>
</div>

<script>
(function () {{
  var root = document.documentElement;
  var sun = document.getElementById('icon-sun');
  var moon = document.getElementById('icon-moon');
  var btn = document.getElementById('theme-toggle');
  var STORAGE_KEY = 'mtl-theme';

  function isDark(theme) {{
    return theme !== 'light'; // dark is the unconditional default; only an explicit "light" opts out
  }}
  function apply(theme) {{
    if (theme) {{ root.setAttribute('data-mtl-theme', theme); }} else {{ root.removeAttribute('data-mtl-theme'); }}
    var dark = isDark(theme);
    if (sun) sun.hidden = dark;
    if (moon) moon.hidden = !dark;
  }}

  var saved = null;
  try {{ saved = localStorage.getItem(STORAGE_KEY); }} catch (e) {{}}
  apply(saved);

  if (btn) {{
    btn.addEventListener('click', function () {{
      var next = isDark(root.getAttribute('data-mtl-theme')) ? 'light' : 'dark';
      apply(next);
      try {{ localStorage.setItem(STORAGE_KEY, next); }} catch (e) {{}}
    }});
  }}
}})();
</script>
'''


ASSET_MATCH = {
    'equities': ['spy', 'dia', '^gspc', 's&p 500', 's&p'],
    'bonds': ['tlt', 'shy', 'us30y', '10y', '30y', '2y', 'yield', 'treasury'],
    'gold': ['gld', 'gold', 'xau'],
    'dollar': ['dxy', 'dx-y', 'usd', 'dollar'],
    'iwm': ['iwm', 'russell'],
    'qqq': ['qqq', 'nasdaq', 'smh'],
}


def matching_catalysts(asset_key, news_log, date):
    keywords = ASSET_MATCH.get(asset_key, [])
    out = []
    for c in news_log:
        if c.get('date') != date:
            continue
        haystack = ' '.join((c.get('tickers', ''), c.get('event', ''), c.get('numbers', ''))).lower()
        if any(k in haystack for k in keywords):
            out.append(c)
    return out


HORIZON_LABEL = {1: '1D', 5: '5D', 10: '10D'}


def pct_tone(pct):
    if pct is None:
        return 'flat'
    return 'good' if pct >= 55 else ('critical' if pct < 45 else 'flat')


def fmt_pct_or_dash(rate):
    return f"{rate['pct']:.1f}%" if rate['pct'] is not None else '—'


def record_row(label, rate, edge=None, real=None):
    n_txt = f"{rate['hits']}/{rate['n']}" if rate['n'] else '0/0'
    edge_txt = f" · edge {edge:+d}" if edge is not None and rate['n'] else ''
    real_txt = ''
    if real is not None and real['n']:
        real_edge_txt = f" · edge {real['edge']:+d}" if real.get('edge') is not None else ''
        real_txt = (f'<span class="record-row-real">real {fmt_pct_or_dash(real)} '
                    f'({real["hits"]}/{real["n"]}{real_edge_txt})</span>')
    return (f'<div class="record-row"><span class="record-row-label">{E(label)}</span>'
            f'<span class="record-row-val">{fmt_pct_or_dash(rate)} '
            f'<span class="record-row-n">({n_txt}{edge_txt})</span>{real_txt}</span></div>')


def track_record_section(all_docs: dict) -> str:
    agg = aggregate(all_docs)
    if agg['settledCells'] == 0:
        return ('<div class="record"><p class="record-empty">No calls have matured and settled '
                'yet - the earliest published document is too recent for any 1-day horizon to '
                'have closed. Come back after the next session close.</p></div>')

    overall = agg['overall']
    overall_real = agg['overallReal']
    tone = pct_tone(overall['pct'])
    tone_real = pct_tone(overall_real['pct'])
    by_horizon = "".join(record_row(HORIZON_LABEL[h], agg['byHorizon'][h], agg['byHorizon'][h]['edge'],
                                     agg['byHorizon'][h]['real'])
                         for h in (1, 5, 10))
    by_asset = "".join(record_row(TICKER.get(k, k.upper()), agg['byAsset'][k], agg['byAsset'][k]['edge'],
                                   agg['byAsset'][k]['real'])
                       for k in ('equities', 'bonds', 'gold', 'dollar', 'iwm', 'qqq'))
    by_call = "".join(record_row(t.capitalize(), agg['byCallType'][t], agg['byCallType'][t]['edge'],
                                  agg['byCallType'][t]['real'])
                      for t in ('bullish', 'bearish', 'flat', 'no-call') if agg['byCallType'][t]['n'])

    overlay = agg['overlay']
    overlay_html = ''
    if overlay['native']:
        overlay_html = f'''
      <div class="record-block">
        <h3>Overlay effect (cells it actually changed)</h3>
        {record_row('Post-overlay', overlay['post'], overlay['postEdge'])}
        {record_row('Pre-overlay (shadow)', overlay['pre'], overlay['preEdge'])}
      </div>'''

    return f'''
    <div class="record">
      <p class="record-head-label">Result</p>
      <div class="record-head">
        <span class="record-pct {tone}">{fmt_pct_or_dash(overall)}</span>
        <span class="record-n">{overall['hits']}/{overall['n']} settled calls correct</span>
        <span class="record-edge">edge {agg['overallEdge']:+d} units</span>
      </div>
      <p class="record-head-label">Real Result <span class="record-row-real">({agg['noCallCells']} directional
        call{'s' if agg['noCallCells'] != 1 else ''} that landed flat excluded as no-call push{'es' if agg['noCallCells'] != 1 else ''}, not misses)</span></p>
      <div class="record-head">
        <span class="record-pct {tone_real}">{fmt_pct_or_dash(overall_real)}</span>
        <span class="record-n">{overall_real['hits']}/{overall_real['n']} real-result calls correct</span>
        <span class="record-edge">edge {agg['overallRealEdge']:+d} units</span>
      </div>
      <div class="record-grid">
        <div class="record-block"><h3>By horizon</h3>{by_horizon}</div>
        <div class="record-block"><h3>By asset</h3>{by_asset}</div>
        <div class="record-block"><h3>By call type</h3>{by_call}</div>
      </div>
      {overlay_html}
      <p class="record-caveat">{E(agg['byCategoryWarning'])}</p>
    </div>'''


LOG_MAX_SESSIONS = 14  # cap the rendered log so the page doesn't grow unbounded over months


def result_badge(settled, correct):
    if not settled:
        return '<span class="log-pending">pending</span>'
    if correct is None:
        return '<span class="log-noscore">not scored</span>'
    return ('<span class="log-correct">✓ correct</span>' if correct
            else '<span class="log-wrong">✗ incorrect</span>')


def actual_badge(oc, ret, settled):
    """What really happened, independent of what was called - the same
    outcome() classification settle_horizon graded the call against, so
    this is never a second opinion, just the raw fact being shown."""
    if not settled:
        return '<span class="log-pending">pending</span>'
    role, hexval, arrow = CALL_STATUS.get(oc, ('flat', '#898781', '▬'))
    return (f'<span class="log-call"><span class="dot" style="--dot:{hexval}"></span>{arrow} {E(oc)}</span>'
            f'<span class="log-conf">{fmt_pct(ret)}</span>')


def real_result_badge(settled, call, oc):
    if not settled:
        return '<span class="log-pending">pending</span>'
    rr = real_result(call, oc)
    if rr is None:
        return '<span class="log-noscore">not scored</span>'
    if rr == 'correct':
        return '<span class="log-correct">✓ correct</span>'
    if rr == 'no-call':
        return '<span class="log-nocall">– no call</span>'
    return '<span class="log-wrong">✗ incorrect</span>'


def log_row(date, a, h):
    role, hexval, arrow = CALL_STATUS.get(h['call'], ('flat', '#898781', '▬'))
    settled = h.get('maturityClose') is not None
    end_price = fmt_price(h['maturityClose']) if settled else '—'
    oc = outcome(h['ret'], h['band']) if settled else None
    return f'''<tr>
      <td class="log-date">{E(date)}</td>
      <td class="log-ticker">{E(TICKER.get(a['key'], a['key'].upper()))}</td>
      <td>{h['h']}D</td>
      <td><span class="log-call"><span class="dot" style="--dot:{hexval}"></span>{arrow} {E(h['call'])}</span>
          <span class="log-conf">{E(h['confidence'])}</span></td>
      <td class="log-matures">{E(h['maturity'])}</td>
      <td class="log-price">{fmt_price(a['close'])}</td>
      <td class="log-price">{end_price}</td>
      <td>{actual_badge(oc, h.get('ret'), settled)}</td>
      <td>{result_badge(settled, h.get('correct'))}</td>
      <td>{real_result_badge(settled, h['call'], oc)}</td>
    </tr>'''


def call_log_section(all_docs: dict) -> str:
    dates = sorted(all_docs, reverse=True)
    shown_dates = dates[:LOG_MAX_SESSIONS]
    rows = []
    for date in shown_dates:
        doc = all_docs[date]
        for a in doc['assets']:
            for h in sorted(a['horizons'], key=lambda h: h['h']):
                rows.append(log_row(date, a, h))

    caption = f"showing the {len(shown_dates)} most recent session(s) ({len(rows)} calls)"
    if len(dates) > len(shown_dates):
        caption += f" of {len(dates)} published total - see documents/ in the repo for the full history"

    return f'''
    <div class="log-wrap">
      <table class="log">
        <thead><tr><th>Date</th><th>Asset</th><th>Horizon</th><th>Predicted</th><th>Matures</th><th>Start</th><th>End</th><th>Actual</th><th>Result</th><th>Real Result</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    <p class="log-caption">{E(caption)}</p>'''


def render(doc: dict, all_docs: dict = None, generated_at: str = None) -> str:
    news_log = doc.get('context', {}).get('newsLog', [])
    assets_html = "".join(
        asset_card(a, matching_catalysts(a['key'], news_log, doc['date']))
        for a in doc['assets']
    )
    docs = all_docs or {doc['date']: doc}
    stamp = generated_at or datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    return PAGE.format(
        date=doc['date'], tape=ticker_strip(doc), stats=stat_tiles(doc),
        assets=assets_html, record=track_record_section(docs), log=call_log_section(docs),
        generated_at=E(stamp),
    )


def load_all_documents(documents_dir):
    docs = {}
    for path in sorted(glob.glob(os.path.join(documents_dir, "*.json"))):
        doc = json.load(open(path))
        docs[doc['date']] = doc
    return docs


def main(s: str):
    """Renders the board for session date `s`, always to the same files
    (documents/latest.html and docs/index.html) - overwritten each run
    rather than accumulating one HTML file per day. The underlying
    documents/<date>.json ledger is NOT touched by this script and stays
    one file per day; that's the real scored history the Track record /
    Call log sections are computed from, and it has to persist. Only these
    rendered display copies are disposable.

    docs/index.html exists because this repo's GitHub Pages is configured
    to serve from the /docs folder on main - that's the file Pages
    actually publishes at https://danreed001-droid.github.io/NIBII/.
    documents/latest.html stays too, for the artifact-publish workflow and
    anyone browsing the repo directly.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    documents_dir = os.path.join(root, "documents")
    doc = json.load(open(os.path.join(documents_dir, f"{s}.json")))
    all_docs = load_all_documents(documents_dir)
    page = render(doc, all_docs)

    out_path = os.path.join(documents_dir, "latest.html")
    with open(out_path, "w") as f:
        f.write(page)
    print(f"wrote {out_path}")

    docs_dir = os.path.join(root, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    pages_path = os.path.join(docs_dir, "index.html")
    with open(pages_path, "w") as f:
        f.write(page)
    print(f"wrote {pages_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    main(sys.argv[1])

#!/usr/bin/env python3
"""Renders docs/scanner.html - the "Top 5 Strongest" momentum dashboard -
from data/momentum_scan.json (written by scripts/momentum_scan.py).

Static like the Ledger page it sits next to: the data is embedded as JSON
and drawn by an inline script (holdings cards with sparklines, growth of
$100 vs SPY/QQQ, year by year, on-deck list, trade log, sortable top-100
table). Shares the Ledger's tokens, fonts and dark/light toggle.

Usage:
    python scripts/render_scanner.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, 'data', 'momentum_scan.json')
OUT_PATH = os.path.join(ROOT, 'docs', 'scanner.html')

PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Top 5 Strongest</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0d0d0d; --surface: #17181a; --surface-2: #1f2023; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #8b8a85; --hairline: #2c2c2a; --accent: #3987e5; --gold: #d9b46a;
  --masthead-bg: #17181a; --masthead-ink: #ffffff; --masthead-ink-2: #a9adba;
  --pos: #3fbf5f; --neg: #e5605a; --grid: #2c2c2a;
  --s-strat: #3987e5; --s-spy: #c98500; --s-qqq: #d55181; --s-plan: #3fb8a0; --s-boost: #a989f5; --s-mon: #f08c4a; --s-monb: #8fbf3a;
  color-scheme: dark;
}
:root[data-mtl-theme="light"] {
  --bg: #f4f3ef; --surface: #fdfdfc; --surface-2: #f0efea; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  --pos: #0a8f0a; --neg: #c43232; --grid: #e1e0d9;
  --s-strat: #2a78d6; --s-spy: #eda100; --s-qqq: #e87ba4; --s-plan: #13866f; --s-boost: #6d44d4; --s-mon: #c4561a; --s-monb: #5f8a12;
  color-scheme: light;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { background: var(--bg); color: var(--ink); margin: 0; font: 15px/1.55 "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 1120px; margin-inline: auto; padding: 0 16px 64px; }
h1, h2 { font-family: "Fraunces", Georgia, serif; margin: 0; text-wrap: balance; }
.mono, td.num, .num { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
a { color: var(--accent); }
.pos { color: var(--pos); } .neg { color: var(--neg); } .muted { color: var(--muted); }

/* masthead */
.masthead { background: var(--masthead-bg); color: var(--masthead-ink);
  background-image: radial-gradient(1200px 300px at 85% -40%, rgba(217,180,106,0.16), transparent 60%); }
.masthead-inner { max-width: 1120px; margin-inline: auto; padding: 20px 16px 24px; border-bottom: 2px solid var(--gold); }
.nav { display: flex; justify-content: space-between; gap: 12px; font-size: 0.8rem; }
.nav a { color: var(--masthead-ink-2); text-decoration: none; }
.nav a:hover { color: var(--gold); }
.nav .bt { color: var(--gold); font-weight: 600; }
.eyebrow { font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--gold); font-weight: 600; margin: 16px 0 6px; }
.top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
h1 { font-size: 2.4rem; font-weight: 600; }
.subtitle { color: var(--masthead-ink-2); margin: 8px 0 0; font-size: 0.92rem; max-width: 760px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.meta span { border: 1px solid rgba(255,255,255,0.14); border-radius: 999px; padding: 4px 11px; font-size: 0.76rem; color: var(--masthead-ink-2); }
.meta b { color: var(--masthead-ink); font-weight: 600; }
.meta .dot { display: inline-block; width: 7px; height: 7px; border-radius: 99px; background: #5fb87a; margin-right: 6px; vertical-align: 1px; }
.meta .dot.aging { background: #d9b46a; } .meta .dot.stale { background: #e5705f; }
.theme-toggle { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.18); background: transparent; color: var(--masthead-ink-2); cursor: pointer; }
.theme-toggle:hover { color: var(--gold); border-color: var(--gold); }
.theme-toggle svg { width: 15px; height: 15px; }

.section-label { font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); font-weight: 600;
  margin: 34px 0 12px; display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.section-label .hint { text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 0.8rem; }

/* rebalance banner */
.banner { margin-top: 18px; display: flex; gap: 10px 16px; align-items: center; flex-wrap: wrap; background: var(--surface);
  border: 1px solid var(--hairline); border-left: 4px solid var(--gold); border-radius: 12px; padding: 12px 16px; font-size: 0.88rem; }
.banner b { font-weight: 600; }
.tag { display: inline-flex; align-items: center; gap: 4px; border-radius: 999px; padding: 2px 9px; font-size: 0.74rem; font-weight: 600;
  border: 1px solid var(--hairline); }
.tag.buy { color: var(--pos); border-color: color-mix(in srgb, var(--pos) 50%, transparent); }
.tag.sell { color: var(--neg); border-color: color-mix(in srgb, var(--neg) 50%, transparent); }
.tag.ndx { font-size: 0.64rem; padding: 1px 6px; color: var(--muted); letter-spacing: 0.04em; }

/* holdings */
.holdings { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 16px; }
@media (max-width: 1000px) { .holdings { grid-template-columns: repeat(auto-fill, minmax(min(200px, 100%), 1fr)); } }
.hold { position: relative; background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px; padding: 14px 14px 12px;
  display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
.hold[data-t] { cursor: pointer; transition: border-color .15s; }
.hold[data-t]:hover { border-color: var(--muted); }
.hold[data-t]:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.hold[aria-expanded="true"] { border-color: var(--gold); }
.chart-hint { font-size: 0.7rem; color: var(--muted); text-align: right; }
.swpanel { margin-top: 12px; }
.swhead { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
.swhead h3 { margin: 0; font: 600 1.05rem "Space Grotesk", system-ui, sans-serif; }
.swhead .x { font: inherit; font-size: 0.8rem; border: 1px solid var(--hairline); background: var(--surface-2); color: var(--ink-2); border-radius: 999px; padding: 4px 12px; cursor: pointer; }
.swread { display: inline-block; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; margin-left: 6px; vertical-align: 2px; }
.swread.up { background: color-mix(in srgb, var(--pos) 18%, transparent); color: var(--pos); }
.swread.down { background: color-mix(in srgb, var(--neg) 18%, transparent); color: var(--neg); }
.swread.chop { background: var(--surface-2); color: var(--muted); }
.swchart { position: relative; margin-top: 8px; }
.swchart svg { display: block; width: 100%; height: auto; overflow: visible; }
.swchart .wick { stroke-width: 1; }
.swchart .lbl { font: 700 10px ui-monospace, monospace; fill: var(--ink); }
.swchart .strip text { font: 700 9px "Space Grotesk", system-ui, sans-serif; }
.swnote { font-size: 0.78rem; color: var(--muted); margin: 8px 0 0; }
.hold::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 3px; background: linear-gradient(90deg, var(--gold), transparent); }
.hold-top { display: flex; justify-content: space-between; align-items: center; }
.rank { font-family: ui-monospace, monospace; font-size: 0.74rem; color: var(--gold); font-weight: 600; }
.tk { font-family: "Fraunces", Georgia, serif; font-size: 1.6rem; font-weight: 600; line-height: 1.05; }
.nm { color: var(--ink-2); font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.big { font-family: ui-monospace, monospace; font-size: 1.35rem; font-weight: 600; line-height: 1.1; }
.small { font-size: 0.72rem; color: var(--muted); }
.spark { width: 100%; height: 44px; display: block; }
.spark path { fill: none; stroke-width: 1.8; stroke-linejoin: round; }
.kv { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; font-size: 0.74rem; }
.kv span { color: var(--muted); } .kv b { font-family: ui-monospace, monospace; font-weight: 600; text-align: right; }
.tr { display: inline-flex; gap: 6px; font-size: 0.74rem; color: var(--muted); }
.tr i { font-style: normal; font-weight: 600; }
.up { color: var(--pos); } .down { color: var(--neg); } .chop { color: var(--muted); }

/* stat tiles */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--hairline); border: 1px solid var(--hairline);
  border-radius: 12px; overflow: hidden; }
@media (max-width: 720px) { .stats { grid-template-columns: repeat(2, 1fr); } }
.stat { background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 3px; }
.stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.stat-value { font-family: ui-monospace, monospace; font-size: 1.5rem; font-weight: 600; line-height: 1.2; }
.stat-sub { font-size: 0.75rem; color: var(--ink-2); }

/* charts */
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 14px 16px; }
.two { display: grid; grid-template-columns: 1.7fr 1fr; gap: 12px; }
@media (max-width: 900px) { .two { grid-template-columns: 1fr; } }
.two > * { min-width: 0; }
.chart-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.chart-title { font-size: 0.95rem; font-weight: 600; margin: 0; }
.chart-sub { font-size: 0.78rem; color: var(--muted); margin: 2px 0 0; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 0.78rem; color: var(--ink-2); margin: 4px 0 6px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend .lg { display: inline-flex; align-items: center; gap: 6px; font: inherit; color: inherit; background: none; border: 1px solid var(--hairline); border-radius: 999px; padding: 3px 9px; cursor: pointer; }
.legend .lg[aria-pressed="false"] { opacity: 0.45; text-decoration: line-through; }
.legend .lg-hint { font-size: 0.72rem; }
.key { width: 16px; height: 3px; border-radius: 2px; background: var(--c); }
.seg { display: inline-flex; border: 1px solid var(--hairline); border-radius: 999px; padding: 2px; background: var(--surface-2); }
.seg button { font: inherit; font-size: 0.76rem; border: 0; background: transparent; color: var(--ink-2); padding: 3px 10px; border-radius: 999px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg); font-weight: 600; }
.chart { position: relative; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.grid line { stroke: var(--grid); stroke-width: 1; }
.axis text { fill: var(--muted); font-size: 11px; font-family: ui-monospace, monospace; }
.base { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
.line { fill: none; stroke-linejoin: round; stroke-linecap: round; stroke-width: 1.8; }
.line.main { stroke-width: 2.6; }
.endlabel { font-size: 11px; font-family: ui-monospace, monospace; fill: var(--ink-2); }
.cross { stroke: var(--muted); stroke-width: 1; }
.dotm { stroke: var(--surface); stroke-width: 2; }
.tip { position: absolute; pointer-events: none; background: var(--ink); color: var(--bg); font-size: 0.76rem; padding: 7px 10px; border-radius: 6px; min-width: 150px; z-index: 3; }
.tip .row { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.tip .row i { width: 12px; height: 3px; background: var(--c); display: inline-block; }
.tip b { font-family: ui-monospace, monospace; }

/* years */
.years td, .years th { padding: 6px 6px; }
.years.tight td, .years.tight th { padding: 6px 4px; } .years.tight .ybar i { display: none; } .years.tight .ybar { gap: 0; }
.ybar { display: flex; align-items: center; gap: 6px; }
.ybar i { display: block; height: 8px; border-radius: 3px; background: var(--c); min-width: 2px; }
.ybar.neg i { background: var(--neg); opacity: 0.8; }

/* on deck + trades */
.deck { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(250px, 100%), 1fr)); gap: 8px; }
.dk { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 9px 12px; display: grid;
  grid-template-columns: 34px 1fr auto; gap: 2px 10px; align-items: center; }
.dk .rank { font-size: 0.8rem; }
.dk[data-t] { cursor: pointer; transition: border-color .15s; }
.dk[data-t]:hover { border-color: var(--muted); }
.dk[data-t]:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.dk[aria-expanded="true"] { border-color: var(--gold); }
.deck > .swpanel, .holdings > .swpanel { grid-column: 1 / -1; margin-top: 0; }
.dk .tk2 { font-weight: 600; } .dk .nm2 { font-size: 0.72rem; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; grid-column: 2; }
.dk .val { text-align: right; font-family: ui-monospace, monospace; font-size: 0.85rem; font-weight: 600; }
.dk .chg { text-align: right; font-size: 0.72rem; grid-column: 3; }
.timeline { list-style: none; margin: 0; padding: 0; }
.timeline li { display: grid; grid-template-columns: 92px 52px 1fr auto; gap: 8px; align-items: center; padding: 7px 0; border-bottom: 1px solid var(--hairline); font-size: 0.84rem; }
.timeline li:last-child { border-bottom: 0; }
.timeline .when { color: var(--muted); font-size: 0.76rem; font-family: ui-monospace, monospace; }

/* table */
.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.filters input, .filters select { font: inherit; font-size: 0.85rem; background: var(--surface); color: var(--ink); border: 1px solid var(--hairline); border-radius: 8px; padding: 7px 10px; min-width: 0; }
.filters input { flex: 1 1 200px; }
.count { font-size: 0.78rem; color: var(--muted); margin-left: auto; }
.tablebox { position: relative; overflow-x: auto; border: 1px solid var(--hairline); border-radius: 12px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 0.84rem; }
th, td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--hairline); white-space: nowrap; }
th:first-child, td:first-child, th.l, td.l { text-align: left; }
th { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; background: var(--surface); }
th button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; text-transform: inherit; letter-spacing: inherit; }
th button[data-dir]::after { content: attr(data-dir); margin-left: 4px; }
tr.held td { background: color-mix(in srgb, var(--gold) 9%, transparent); }
td .sub { display: block; color: var(--muted); font-size: 0.72rem; max-width: 210px; overflow: hidden; text-overflow: ellipsis; }
tbody tr:last-child td { border-bottom: 0; }
@media (max-width: 640px) { .hide-sm { display: none; } }
.more { display: block; margin: 12px auto 0; font: inherit; font-size: 0.82rem; color: var(--accent); background: none; border: 1px solid var(--hairline); border-radius: 999px; padding: 7px 16px; cursor: pointer; }
/* plan */
.plan { display: grid; grid-template-columns: 1.25fr 1fr; gap: 12px; }
.plan > * { min-width: 0; }
@media (max-width: 520px) { .alloc .nm2 { display: none; } .alloc td { padding: 7px 2px; } }
@media (max-width: 900px) { .plan { grid-template-columns: 1fr; } }
.plan-controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin-bottom: 10px; }
.plan-controls .seg { flex-wrap: wrap; border-radius: 14px; }
.plan-controls .seg button { white-space: nowrap; }
.plan-controls label { font-size: 0.8rem; color: var(--ink-2); display: inline-flex; align-items: center; gap: 8px; }
.money-in { display: inline-flex; align-items: center; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); padding: 0 8px; }
.money-in span { color: var(--muted); }
.money-in input { font: 600 0.95rem ui-monospace, monospace; width: 110px; border: 0; background: transparent; color: var(--ink); padding: 6px 4px; outline: none; }
.money-in:focus-within { border-color: var(--accent); }
.mlist { margin: 6px 0 0; font-size: 0.8rem; color: var(--ink-2); }
.mlist b { font-family: ui-monospace, monospace; }
.alloc { width: 100%; border-collapse: collapse; font-size: 0.86rem; table-layout: fixed; }
.alloc td:nth-child(2) { width: 86px; } .alloc td:nth-child(3) { width: 72px; }
.alloc td:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alloc tr.borrow td:first-child { white-space: normal; }
.alloc td { padding: 7px 4px; border-bottom: 1px solid var(--hairline); }
.alloc td.r { text-align: right; font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.alloc tr.sum td { font-weight: 600; border-bottom: 0; }
.alloc tr.borrow td { color: var(--muted); }
.alloc .sw { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 8px; background: var(--c); }
.plan-stats { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 10px; font-size: 0.8rem; color: var(--ink-2); }
.plan-stats b { font-family: ui-monospace, monospace; }
.assets { list-style: none; margin: 6px 0 0; padding: 0; }
.assets li { display: grid; grid-template-columns: 52px 1fr 70px; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--hairline); font-size: 0.84rem; }
.assets li:last-child { border-bottom: 0; }
.assets li.pick { font-weight: 600; }
.assets li.pick .atk::after { content: ' ★'; color: var(--gold); }
.abar { height: 6px; border-radius: 3px; background: var(--surface-2); position: relative; overflow: hidden; }
.abar i { position: absolute; top: 0; bottom: 0; left: 50%; background: var(--c); border-radius: 3px; }
.assets .num { text-align: right; }
.note { font-size: 0.78rem; color: var(--muted); margin: 8px 0 0; }
.optcheck { margin-top: 12px; }
/* date range */
.range { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin: 0 0 10px; font-size: 0.8rem; color: var(--ink-2); }
.range label { display: inline-flex; align-items: center; gap: 6px; }
.range select { font: inherit; font-size: 0.82rem; color: var(--ink); background: var(--surface-2); border: 1px solid var(--hairline); border-radius: 8px; padding: 4px 8px; }
.range input[type="date"] { font: inherit; font-size: 0.82rem; color: var(--ink); background: var(--surface-2); border: 1px solid var(--hairline); border-radius: 8px; padding: 4px 8px; color-scheme: inherit; }
/* your calls (human model) */
.choices { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0; }
.choice { text-align: left; font: inherit; border: 1px solid var(--hairline); background: var(--surface-2); color: var(--ink); border-radius: 10px; padding: 9px 11px; cursor: pointer; }
.choice b { display: block; font-size: 0.88rem; }
.choice span { font-size: 0.74rem; color: var(--muted); }
.choice[aria-checked="true"] { border-color: var(--gold); box-shadow: inset 0 0 0 1px var(--gold); }
.choice:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.custom { display: flex; gap: 8px 14px; flex-wrap: wrap; align-items: center; font-size: 0.82rem; color: var(--ink-2); margin-bottom: 10px; }
.custom input { width: 58px; font: 600 0.9rem ui-monospace, monospace; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); color: var(--ink); padding: 5px 6px; text-align: right; }
.custom b { font-family: ui-monospace, monospace; }
.picks { margin: 2px 0 10px; }
.picks .ph { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 0 0 4px; }
.pk { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--hairline); font-size: 0.84rem; }
.pk:last-child { border-bottom: 0; }
.pk select { font: inherit; font-size: 0.8rem; color: var(--ink); background: var(--surface-2); border: 1px solid var(--hairline); border-radius: 8px; padding: 4px 6px; max-width: 190px; }
.pk.changed select { border-color: var(--gold); }
#call-note { width: 100%; min-height: 52px; font: inherit; font-size: 0.84rem; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); color: var(--ink); padding: 8px 10px; resize: vertical; }
.call-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
.btn { font: inherit; font-size: 0.85rem; font-weight: 600; background: var(--ink); color: var(--bg); border: 0; border-radius: 999px; padding: 7px 16px; cursor: pointer; }
.submitbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding: 10px 12px; border: 1px solid var(--gold); border-radius: 10px; background: color-mix(in srgb, var(--gold) 10%, transparent); font-size: 0.84rem; }
.submitbar .btn { text-decoration: none; }
.submitbar[hidden] { display: none; }
.btn.ghost { background: transparent; color: var(--ink); border: 1px solid var(--hairline); }
.linkbtn { background: none; border: 0; padding: 0; color: var(--accent); cursor: pointer; font: inherit; font-size: 0.8rem; }
.linkbtn input { display: none; }
#call-status { font-size: 0.8rem; color: var(--ink-2); }
#sync-token { flex: 1 1 180px; min-width: 0; font: 0.84rem ui-monospace, monospace; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); color: var(--ink); padding: 6px 8px; }
.sync code { font-size: 0.74rem; }
.rec-tiles { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 8px 0 10px; }
.rec-tile { background: var(--surface-2); border-radius: 10px; padding: 8px 10px; }
.rec-tile .k { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); display: flex; align-items: center; gap: 6px; }
.rec-tile .k i { width: 12px; height: 3px; border-radius: 2px; background: var(--c); display: inline-block; }
.rec-tile .v { font: 600 1.15rem ui-monospace, monospace; }
.rec-tile .d { font-size: 0.72rem; color: var(--muted); }
.wk { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 8px; table-layout: fixed; }
.wk th:first-child { width: 62px; } .wk th.r { width: 64px; }
.wk td { overflow-wrap: anywhere; }
.wk th { text-align: left; font-weight: 600; color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 4px; border-bottom: 1px solid var(--hairline); }
.wk td { padding: 6px 4px; border-bottom: 1px solid var(--hairline); text-align: left; }
.wk td.r, .wk th.r { text-align: right; font-family: ui-monospace, monospace; }
.wk .note-i { color: var(--muted); font-size: 0.74rem; display: block; }
@media (max-width: 520px) { .years .y-strategy { display: none; } .wk .hide-xs { display: none; } .rec-tiles { gap: 6px; grid-template-columns: repeat(2, 1fr); } .rec-tile .v { font-size: 1rem; } }
footer { margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }
footer li { margin-bottom: 6px; }
</style>

<div class="masthead"><div class="masthead-inner">
  <div class="nav"><a href="index.html">← Market Tape Ledger</a><a class="bt" href="backtest.html">Backtests →</a></div>
  <p class="eyebrow">NIBII · Momentum</p>
  <div class="top"><h1>Top 5 Strongest</h1>
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dark/light theme">
      <svg id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>
      <svg id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"></path></svg>
    </button></div>
  <p class="subtitle">Every Friday close, rank the S&amp;P 500 + Nasdaq-100 by how consistently strong each stock was week by week over
    the last 6 months (skipping the latest month), hold the 5 strongest that beat SPY, and keep each while it stays in the top 10. Trade on Monday, 3:30–4:00 pm ET.</p>
  <div class="meta" id="meta"></div>
</div></div>

<div class="wrap">
  <div class="banner" id="banner"></div>

  <p class="section-label">Current holdings <span class="hint" id="hold-hint"></span></p>
  <div class="holdings" id="holdings"></div>
  <div class="card optcheck" id="optcheck" hidden></div>
  <div class="card swpanel" id="swpanel" hidden></div>

  <p class="section-label">Your plan <span class="hint" id="plan-hint"></span></p>
  <div class="plan">
    <div class="card">
      <div class="plan-controls">
        <label>Account <span class="money-in"><span>$</span><input id="acct" type="text" inputmode="numeric" value="10,000" aria-label="Account size in dollars"></span></label>
        <label>Mix <span class="seg" id="mix-seg"></span></label>
      </div>
      <table class="alloc" id="alloc"></table>
      <div class="plan-stats" id="plan-stats"></div>
      <p class="note" id="auto-note"></p>
    </div>
    <div class="card">
      <p class="chart-title">The sleeve this week</p>
      <p class="chart-sub" id="sleeve-sub"></p>
      <ul class="assets" id="assets"></ul>
      <p class="note" id="sleeve-note"></p>
    </div>
  </div>

  <div id="monthly-wrap" hidden>
  <p class="section-label">Monthly plan <span class="hint">tracked alongside the weekly plans · decided at the last close of each month, traded the next session</span></p>
  <div class="plan" id="monthly"></div>
  </div>

  <p class="section-label">Your calls <span class="hint">the human model · you decide each week · saved in this browser</span></p>
  <div class="plan">
    <div class="card">
      <p class="chart-title" id="call-title">Your call</p>
      <p class="chart-sub" id="call-sub"></p>
      <div class="choices" id="choices" role="radiogroup" aria-label="Your call for the week"></div>
      <div class="custom" id="custom" hidden>
        <label>Stocks <input id="cu-s" type="number" min="0" max="100" step="5" value="70">%</label>
        <label>Sleeve <input id="cu-v" type="number" min="0" max="100" step="5" value="20">%</label>
        <span>Cash <b id="cu-c">10</b>%</span>
      </div>
      <div class="picks" id="picks"></div>
      <textarea id="call-note" placeholder="Why? (optional — e.g. earnings week, Fed meeting, charts look heavy)"></textarea>
      <div class="call-actions"><button type="button" class="btn" id="call-save">Save my call</button>
        <button type="button" class="linkbtn" id="call-clear" hidden>Remove this week’s call</button><span id="call-status" role="status"></span></div>
      <div class="submitbar" id="submitbar" hidden><span id="submit-msg"></span>
        <a class="btn" id="call-submit" target="_blank" rel="noopener">Submit to repo ↗</a></div>
      <p class="note">Saved calls stay in this browser until you <b>Submit to repo</b>: it opens a filled-in GitHub issue — tap <b>Create</b> and the repo records your calls within a minute and closes it. No token needed; only issues from your GitHub account are accepted.</p>
      <p class="note">A call carries forward until you change it.
        <button type="button" class="linkbtn" id="call-export">Back up</button> ·
        <label class="linkbtn">restore<input type="file" id="call-import" accept="application/json"></label></p>
      <div class="sync" hidden>
        <p class="note" style="margin-top:6px"><span id="sync-status"></span> <button type="button" class="linkbtn" id="sync-toggle"></button></p>
        <div id="sync-panel" hidden>
          <p class="note">Your calls are saved to <code>docs/my_calls.json</code> in the NIBII repo, so every device sees them. To save from this device, paste a GitHub
            <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">fine-grained token</a> limited to <b>danreed001-droid/NIBII</b> with
            <b>Contents: Read and write</b>. It is kept only in this browser. Devices without a token still read your calls (view only).
            Notes you write are visible to anyone who can see the repo.</p>
          <div class="call-actions"><input type="password" id="sync-token" placeholder="github_pat_…" autocomplete="off" aria-label="GitHub token">
            <button type="button" class="btn" id="sync-save">Connect</button><button type="button" class="linkbtn" id="sync-off">Disconnect this device</button></div>
        </div>
      </div>
    </div>
    <div class="card">
      <p class="chart-title">Your record</p>
      <p class="chart-sub">Your calls vs following Auto or Steps over the same weeks</p>
      <div class="range" id="rec-range" hidden><label>From <input type="date" id="rr-from"></label><label>To <input type="date" id="rr-to"></label>
        <button type="button" class="linkbtn" id="rr-all">All</button></div>
      <div id="rec"></div>
    </div>
  </div>

  <p class="section-label">Track record <span class="hint" id="range-hint">$100 in the rule vs buying and holding</span></p>
  <div class="range" id="range">
    <label>Years <select id="ry-from" aria-label="From year"></select></label><label>to <select id="ry-to" aria-label="To year"></select></label>
    <span class="seg" id="r-pre"><button type="button" data-r="ytd">YTD</button><button type="button" data-r="1y">1Y</button><button type="button" data-r="3y">3Y</button><button type="button" data-r="5y">5Y</button><button type="button" data-r="10y">10Y</button><button type="button" data-r="all">All</button></span>
    <span class="seg" id="r-tax"><button type="button" data-t="0" aria-pressed="true">Before tax</button><button type="button" data-t="1" aria-pressed="false">After 37% tax</button></span>
    <label>From <input type="date" id="r-from"></label><label>To <input type="date" id="r-to"></label>
  </div>
  <div class="stats" id="stats"></div>
  <div class="two" style="margin-top:12px">
    <div class="card">
      <div class="chart-head"><div><p class="chart-title">Growth of $100</p><p class="chart-sub">Signal at Friday's close, traded at Monday's close, 0.05% cost · plan = top 5 + sleeve</p></div>
        <span class="seg" id="scale-seg"><button type="button" data-v="log">Log</button><button type="button" data-v="linear">Linear</button></span></div>
      <div class="legend" id="legend"></div>
      <div class="chart" id="growth"></div>
    </div>
    <div class="card">
      <p class="chart-title">Year by year</p><p class="chart-sub" id="ytd-note"></p>
      <div class="tablebox" style="border:0;background:none"><table class="years" id="years"></table></div>
    </div>
  </div>

  <div class="two" style="margin-top:0">
    <div>
      <p class="section-label">On deck <span class="hint">ranks 6–20 · climbing ▲ / slipping ▼ vs last week · tap one to open its swing chart below it</span></p>
      <div class="deck" id="deck"></div>
      <div class="card swpanel" id="swpanel2" hidden></div>
    </div>
    <div>
      <p class="section-label">Recent trades</p>
      <div class="card" style="padding:4px 14px"><ul class="timeline" id="trades"></ul></div>
    </div>
  </div>

  <p class="section-label">Top 100 ranking <span class="hint">trend = weekly / daily swing structure</span></p>
  <div class="filters">
    <input id="q" type="search" placeholder="Search ticker or company" aria-label="Search ticker or company">
    <select id="sector" aria-label="Sector"><option value="">All sectors</option></select>
    <span class="count" id="count"></span>
  </div>
  <div class="tablebox"><table>
    <thead><tr>
      <th><button type="button" data-sort="rank">#</button></th>
      <th class="l"><button type="button" data-sort="t">Stock</button></th>
      <th class="l hide-sm"><button type="button" data-sort="sec">Sector</button></th>
      <th><button type="button" data-sort="score">6-1m</button></th>
      <th><button type="button" data-sort="vsSpy">vs SPY</button></th>
      <th class="hide-sm"><button type="button" data-sort="r1m">1m</button></th>
      <th class="hide-sm"><button type="button" data-sort="r12m">12m</button></th>
      <th><button type="button" data-sort="d1w">Δ 1w</button></th>
      <th class="hide-sm"><button type="button" data-sort="d4w">Δ 4w</button></th>
      <th class="hide-sm"><button type="button" data-sort="offHigh">Off high</button></th>
      <th>Trend</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
  <button type="button" class="more" id="more" hidden>Show all 100</button>

  <footer><ul>
    <li><b>The rule.</b> Each of the 21 weeks from 6 months ago to 1 month ago, every stock is ranked by that week's return; the ranks are added up and the best total ranks #1 (changed Oct 2026 from the plain 6-1 month return, which tested worse; the track record uses the new rule throughout, and the monthly plans keep the plain 6-1 month return). The 6-1m column still shows the plain return. Each Friday close: a stock must beat SPY over those weeks to qualify; buy the top 5, the best-ranked at twice the weight of each of the others (changed Oct 2026 from equal weight, with Auto's tiers); a holding stays while it ranks in the top 10, otherwise it is replaced by the best-ranked stock not held. Trades are placed the following Monday in the last 30 minutes before the close (the track record uses Monday's closing prices; trading at Monday's open did about 3% a year worse in testing). Mon–Thu the banner previews what Friday's signal would be if it were today.</li>
    <li><b>Fair test.</b> S&amp;P 500 stocks count only from the day they joined the index. The 15 Nasdaq-only members have no published join dates, so the track record carries some hindsight from them; the S&amp;P-only version made about +1,219% from 2020 on (see Backtests). Stocks that left either index during the test period are missing, which also flatters the record. Small caps are deliberately excluded: adding the Russell 2000 cut the result to about +509% with a −73% drawdown.</li>
    <li><b>Risk.</b> Five stocks is concentrated: drawdowns near −38% happened, it trailed QQQ in <span id="trail-yrs">some years</span>, and 2026's gains came mostly from one theme (memory/storage). Prices from Yahoo Finance, split-adjusted closes (benchmarks include dividends). A mechanical rule's output, not investment advice.</li>
    <li>Generated by <code>scripts/momentum_scan.py</code> + <code>scripts/render_scanner.py</code> in <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a> · <span id="gen"></span></li>
  </ul></footer>
</div>

<script type="application/json" id="scan-data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('scan-data').textContent);
  var SINCE = (D.rule && D.rule.start ? D.rule.start : '2020').slice(0, 4);
  var NS = 'http://www.w3.org/2000/svg';
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function pct(x, dp) { if (x == null) return '–'; var v = x * 100, d = dp == null ? (Math.abs(v) >= 100 ? 0 : 1) : dp; return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d) + '%'; }
  function tone(x) { return x > 0 ? 'pos' : x < 0 ? 'neg' : ''; }
  function fmtDate(s, opts) { return new Date(s + 'T12:00:00Z').toLocaleDateString(undefined, opts || { month: 'short', day: 'numeric', year: 'numeric' }); }
  function el(tag, a) { var e = document.createElementNS(NS, tag); for (var k in a) e.setAttribute(k, a[k]); return e; }
  var ARW = { up: '▲', down: '▼', chop: '◆' };
  function trend(tr) { if (!tr) return '<span class="muted">–</span>'; return '<span class="tr" title="weekly / daily structure"><span>W <i class="' + (tr[0] || 'chop') + '">' + (ARW[tr[0]] || '·') + '</i></span><span>D <i class="' + (tr[1] || 'chop') + '">' + (ARW[tr[1]] || '·') + '</i></span></span>'; }
  function delta(n) { if (n == null) return '<span class="muted">new</span>'; if (n === 0) return '<span class="muted">–</span>'; return '<span class="' + (n > 0 ? 'pos' : 'neg') + '">' + (n > 0 ? '▲' : '▼') + Math.abs(n) + '</span>'; }
  var held = {}; D.holdings.forEach(function (h) { held[h.t] = 1; });

  // masthead meta + freshness
  var gen = new Date(D.generatedAt);
  function ago() { var m = Math.floor((Date.now() - gen) / 60000), h = m / 60; return m < 60 ? m + ' min ago' : h < 48 ? Math.floor(h) + 'h ago' : Math.floor(h / 24) + ' days ago'; }
  function meta() {
    var h = (Date.now() - gen) / 3600000;
    $('meta').innerHTML = '<span><i class="dot ' + (h < 30 ? '' : h < 80 ? 'aging' : 'stale') + '"></i>Updated <b>' + ago() + '</b></span>' +
      '<span>Prices as of <b>' + fmtDate(D.asOf) + '</b></span>' +
      '<span>Last trade day <b>' + fmtDate(D.lastRebalance, { month: 'short', day: 'numeric' }) + '</b></span>' +
      (D.signalDay ? '<span>Trade <b>Mon ' + fmtDate(D.tradeDate, { month: 'short', day: 'numeric' }) + '</b>, 3:30–4:00 pm ET</span>'
        : '<span>Next signal <b>Fri ' + fmtDate(D.signalDate, { month: 'short', day: 'numeric' }) + '</b> → trade <b>Mon ' + fmtDate(D.tradeDate, { month: 'short', day: 'numeric' }) + '</b></span>') +
      '<span>Universe <b>' + D.universe.total + '</b> stocks</span>';
  }
  meta(); setInterval(meta, 60000);
  $('gen').textContent = 'built ' + gen.toLocaleString();

  // rebalance banner
  var ch = D.changes;
  var SLb = D.sleeve, md = { month: 'short', day: 'numeric' }, wd = { weekday: 'short', month: 'short', day: 'numeric' };
  var tags = ch.sell.map(function (t) { return '<span class="tag sell">sell ' + esc(t) + '</span>'; }).join('') +
    ch.buy.map(function (t) { return '<span class="tag buy">buy ' + esc(t) + '</span>'; }).join('');
  if (D.signalDay) {
    var PA = D.plan && D.plan.auto, pm = (D.plan && D.plan['default']) || 'auto';
    try { pm = localStorage.getItem('nibii-plan-mix3') || pm; } catch (e) {}
    var BO = PA && PA.boost;
    var PM = PA && (pm === 'steps' ? PA.steps : pm === 'boost' ? BO : pm === 'auto' || pm === 'guard' ? PA : null);
    var mixTag = PM && PM.split !== PM.prevSplit ? '<span class="tag ' + (PM.split === '100/0' ? 'buy' : 'sell') + '">' + (pm === 'steps' ? 'steps' : 'auto') + ' mix → ' + PM.split + '</span>' : '';
    if (pm === 'boost' && BO) {   // the boosted rule trades its own list
      tags = BO.sell.map(function (t) { return '<span class="tag sell">sell ' + esc(t) + '</span>'; }).join('') +
        BO.buy.map(function (t) { return '<span class="tag buy">buy ' + esc(t) + (BO.boosted.indexOf(t) >= 0 ? ' (news boost)' : '') + '</span>'; }).join('');
    }
    var GD = PA && PA.guard;
    if (pm === 'guard' && GD && GD.bear !== GD.prevBear) mixTag += '<span class="tag ' + (GD.bear ? 'sell' : 'buy') + '">bear guard ' + (GD.bear ? 'ON → ' + Math.round(GD.share * 100) + '% of stocks into SPY' : 'OFF → back to the top 5') + '</span>';
    var sw = SLb && SLb.held !== SLb.prevHeld ? '<span class="tag sell">sell ' + esc(SLb.prevHeld) + '</span><span class="tag buy">buy ' + esc(SLb.held) + ' (sleeve)</span>' : '';
    $('banner').innerHTML = '<b>Trade Mon ' + fmtDate(D.tradeDate, md) + ', 3:30–4:00 pm ET</b><span class="muted">signal from ' + fmtDate(D.asOf, wd) + '’s close:</span>' +
      (tags || sw || mixTag ? tags + sw + mixTag : '<span>No stock, sleeve or mix changes — just reset to your mix.</span>');
  } else {
    $('banner').innerHTML = (tags ? '<b>Preview — if Friday’s signal were ' + fmtDate(D.asOf, wd) + '’s close:</b>' + tags
        : '<b>No changes so far</b><span class="muted">At ' + fmtDate(D.asOf, wd) + '’s close all five holdings still rank in the top ' + D.rule.keepRank + '.</span>') +
      '<span class="muted">Signal Fri ' + fmtDate(D.signalDate, md) + ' → trade Mon ' + fmtDate(D.tradeDate, md) + ' before the close.</span>';
  }

  function spark(vals, w, h) {
    if (!vals || vals.length < 2) return '';
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), n = vals.length;
    var d = vals.map(function (v, i) { return (i ? 'L' : 'M') + (i / (n - 1) * w).toFixed(1) + ' ' + (h - 3 - (v - lo) / (hi - lo || 1) * (h - 6)).toFixed(1); }).join('');
    var c = vals[n - 1] >= vals[0] ? 'var(--pos)' : 'var(--neg)';
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + '" style="stroke:' + c + '" vector-effect="non-scaling-stroke"></path></svg>';
  }

  // holdings
  $('hold-hint').textContent = (D.signalDay ? 'after Monday’s trades · ' : '') + '#1-ranked holding at 2× (about 33% of the stock part), the others about 17% each · 6-1m = return from 6 months to 1 month ago';
  (function () {
    var O = D.option;
    if (!O) return;
    var md = { month: 'short', day: 'numeric' };
    var usd = function (x) { return '$' + (x >= 100 ? x.toFixed(0) : x.toFixed(2)); };
    $('optcheck').innerHTML =
      '<p class="chart-title">Option check · #1 ' + esc(O.t) + '</p>' +
      '<p class="chart-sub">Optional add-on: a 4-week at-the-money call on the #1 stock (strike ≈ ' + usd(O.price) + ', expiring ' + fmtDate(O.expiry, md) + '), sized at about 2% of the account. ' +
      'It only paid in testing when the call was cheap.</p>' +
      '<div class="stats" style="margin-top:8px">' +
      '<div class="stat"><span class="stat-label">Cheap: buy at or under</span><span class="stat-value pos">' + usd(O.cheap) + '</span><span class="stat-sub">' + pct(O.cheap / O.price, 1) + ' of the price</span></div>' +
      '<div class="stat"><span class="stat-label">Skip if over</span><span class="stat-value neg">' + usd(O.skip) + '</span><span class="stat-sub">' + pct(O.skip / O.price, 1) + ' of the price</span></div>' +
      '<div class="stat"><span class="stat-label">Usual 4-week move</span><span class="stat-value">' + pct(O.usual, 1) + '</span><span class="stat-sub">≈ ' + usd(O.usualUsd) + ' (last year)</span></div>' +
      '<div class="stat"><span class="stat-label">Swing (HV, 3 months)</span><span class="stat-value">' + pct(O.hv, 0) + '</span><span class="stat-sub">fair call ≈ ' + usd(O.fair) + '</span></div></div>' +
      '<p class="note" style="margin-top:8px">' + (O.earningsInside ? '<b class="neg">Earnings ' + fmtDate(O.earnings, md) + ' fall inside the 4 weeks — options are usually overpriced; skip this one.</b> ' :
        (O.earnings ? 'Next earnings ' + fmtDate(O.earnings, md) + ' (after expiry). ' : 'Check the earnings date before buying. ')) +
      'Compare your broker’s ask price for the call with the numbers above. Between them is borderline. A rough guide from a backtest with modelled option prices, not a recommendation.</p>';
    $('optcheck').hidden = false;
  })();
  $('holdings').innerHTML = D.holdings.slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); }).map(function (h) {
    var tap = h.chart ? ' data-t="' + esc(h.t) + '" tabindex="0" role="button" aria-expanded="false" aria-controls="swpanel" aria-label="' + esc(h.t) + ': show swing chart"' : '';
    return '<article class="hold"' + tap + '><div class="hold-top"><span class="rank">#' + (h.rank || '–') + '</span><span>' + (h.new ? '<span class="tag buy">buy Mon</span> ' : '') + (h.ndx ? '<span class="tag ndx" title="Nasdaq-100 only">NDX</span>' : '') + '</span></div>' +
      '<div><div class="tk">' + esc(h.t) + (h.w ? ' <span class="small muted">' + Math.round(h.w * 100) + '%</span>' : '') + '</div><div class="nm" title="' + esc(h.n) + '">' + esc(h.n) + '</div></div>' +
      '<div><div class="big ' + tone(h.score) + '">' + pct(h.score, 0) + '</div><div class="small">6-1m · ' + pct(h.vsSpy, 0) + ' vs SPY</div></div>' +
      spark(h.spark, 200, 44) +
      '<div class="kv"><span>Held</span><b>' + (h.new ? 'new' : (h.weeks || 0) + ' wk') + '</b><span>Since buy</span><b class="' + tone(h.sinceRet) + '">' + pct(h.sinceRet) + '</b>' +
      '<span>1 month</span><b class="' + tone(h.r1m) + '">' + pct(h.r1m) + '</b><span>Off high</span><b>' + pct(h.offHigh) + '</b></div>' +
      '<div style="display:flex;justify-content:space-between;align-items:center"><span class="small">' + esc(h.sec) + '</span>' + trend(h.trend) + '</div>' +
      (h.chart ? '<div class="chart-hint">Swing chart ›</div>' : '') + '</article>';
  }).join('');

  // swing chart panel: tap a card to open it
  var HB = {}; D.table.forEach(function (r) { if (r.chart) HB[r.t] = r; }); D.holdings.forEach(function (h) { if (h.chart) HB[h.t] = h; });
  var openT = {};   // panel id -> ticker shown
  function svgEl(tag, a, txt) { var e = el(tag, a); if (txt != null) e.textContent = txt; return e; }
  function drawSwing(t, pid) {
    var h = HB[t], C = h.chart, panel = $(pid || 'swpanel');
    var READ = { up: ['up', 'Uptrend'], down: ['down', 'Downtrend'], chop: ['chop', 'Mixed'] };
    var rd = READ[C.now] || ['chop', 'No read'];
    var A = D.plan && D.plan.auto, counts = A && A.down.indexOf(t) >= 0;
    panel.innerHTML = '<div class="swhead"><div><h3>' + esc(t) + ' · daily swings <span class="swread ' + rd[0] + '">' + rd[1] + ' now</span></h3>' +
      '<p class="chart-sub">' + esc(h.n) + ' · last ' + C.c.length + ' sessions · ▼ swing high, ▲ swing low</p></div>' +
      '<button type="button" class="x">Close</button></div><div class="swchart"></div>' +
      '<p class="swnote">A swing high is the highest high of 7 days (3 before, 3 after), so it is only known 3 days later; lows likewise. ' +
      '<b>HH/LH</b> = higher/lower than the previous swing high, <b>HL/LL</b> = vs the previous swing low. Down = the last two swings are both LH/LL; up = both HH/HL; otherwise mixed. ' +
      (counts ? '<b>This holding is in a downtrend at the signal close and counts toward the auto mix (each one down moves 20% to the sleeve: 1 → 80/20, 2 → 60/40, 3+ → 40/60).</b>' : 'The auto mix moves 20% to the sleeve for each holding that reads down at Friday’s close (1 → 80/20, 2 → 60/40, 3+ → 40/60).') + '</p>';
    panel.querySelector('.x').onclick = function () { closeSwing(panel.id); };
    var box = panel.querySelector('.swchart'), W = Math.max(300, box.clientWidth), PH = Math.round(Math.min(340, Math.max(220, W * 0.42))), SH = 26, H = PH + SH + 26;
    var m = { l: 52, r: 10, t: 22, b: 8 }, n = C.c.length, step = (W - m.l - m.r) / n;
    var lo = Infinity, hi = -Infinity; C.c.forEach(function (b) { lo = Math.min(lo, b[3]); hi = Math.max(hi, b[2]); });
    var pad = (hi - lo) * 0.09; lo -= pad; hi += pad;
    function X(i) { return m.l + (i + 0.5) * step; }
    function Y(v) { return m.t + (1 - (v - lo) / (hi - lo)) * (PH - m.t - m.b); }
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': t + ' daily candles with swing labels' });
    var g = el('g', { class: 'grid axis' }); svg.appendChild(g);
    var span = hi - lo, raw = span / 4, mag = Math.pow(10, Math.floor(Math.log10(raw))), stp = [1, 2, 2.5, 5, 10].map(function (k) { return k * mag; }).find(function (v) { return v >= raw; });
    for (var v = Math.ceil(lo / stp) * stp; v <= hi; v += stp) {
      g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }));
      g.appendChild(svgEl('text', { x: m.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, '$' + (v >= 100 ? Math.round(v) : v.toFixed(v >= 10 ? 0 : 1))));
    }
    var idx = {}; C.c.forEach(function (b, i) { idx[b[0]] = i; });
    var bw = Math.max(1.4, step * 0.62);
    C.c.forEach(function (b, i) {
      var col = b[4] >= b[1] ? 'var(--pos)' : 'var(--neg)', x = X(i);
      svg.appendChild(el('line', { class: 'wick', x1: x, x2: x, y1: Y(b[2]), y2: Y(b[3]), style: 'stroke:' + col }));
      var y0 = Y(Math.max(b[1], b[4])), y1 = Y(Math.min(b[1], b[4]));
      svg.appendChild(el('rect', { x: x - bw / 2, y: y0, width: bw, height: Math.max(1, y1 - y0), rx: Math.min(1.5, bw / 3), style: 'fill:' + col }));
    });
    var labelAll = step >= 7, sws = C.sw.filter(function (s) { return s.d in idx; });
    sws.forEach(function (s, j) {
      var x = X(idx[s.d]), isH = s.k === 'h', down = s.l === 'LH' || s.l === 'LL', col = down ? 'var(--neg)' : 'var(--pos)';
      var y = Y(s.p) + (isH ? -6 : 6), tri = isH ? 'M' + (x - 4) + ' ' + (y - 5) + 'L' + (x + 4) + ' ' + (y - 5) + 'L' + x + ' ' + y + 'Z' : 'M' + (x - 4) + ' ' + (y + 5) + 'L' + (x + 4) + ' ' + (y + 5) + 'L' + x + ' ' + y + 'Z';
      svg.appendChild(el('path', { d: tri, style: 'fill:' + col }));
      if (labelAll || j >= sws.length - 4) svg.appendChild(svgEl('text', { class: 'lbl', x: x, y: isH ? y - 8 : y + 16, 'text-anchor': 'middle' }, s.l));
    });
    // Friday reads
    var strip = el('g', { class: 'strip' }); svg.appendChild(strip);
    var SC = { up: 'var(--pos)', down: 'var(--neg)', chop: 'var(--muted)' }, ST = { up: 'up', down: 'DOWN', chop: 'mixed' };
    C.fri.forEach(function (f, j) {
      if (!(f[0] in idx)) return;
      var a = idx[f[0]], b = j + 1 < C.fri.length && C.fri[j + 1][0] in idx ? idx[C.fri[j + 1][0]] : n, x0 = m.l + (a + 0.5) * step, x1 = m.l + (b + 0.5) * step;
      x1 = Math.min(x1, W - m.r);
      strip.appendChild(el('rect', { x: x0 + 1, y: PH + 6, width: Math.max(1, x1 - x0 - 2), height: SH - 6, rx: 3, style: 'fill:' + (SC[f[1]] || 'var(--hairline)') + ';opacity:' + (f[1] === 'chop' || !f[1] ? 0.45 : 0.85) }));
      if (x1 - x0 > 34) strip.appendChild(svgEl('text', { x: (x0 + x1) / 2, y: PH + 6 + (SH - 6) / 2 + 3.5, 'text-anchor': 'middle', style: 'fill:' + (f[1] === 'chop' || !f[1] ? 'var(--ink)' : '#fff') }, ST[f[1]] || '–'));
    });
    svg.appendChild(svgEl('text', { x: m.l - 6, y: PH + 6 + (SH - 6) / 2 + 3.5, 'text-anchor': 'end', style: 'fill:var(--muted);font-size:10px' }, 'Fri read'));
    var ax = el('g', { class: 'axis' }); svg.appendChild(ax);
    C.c.forEach(function (b, i) { if (i && b[0].slice(5, 7) !== C.c[i - 1][0].slice(5, 7)) ax.appendChild(svgEl('text', { x: X(i), y: H - 4, 'text-anchor': 'middle' }, fmtDate(b[0], { month: 'short' }))); });
    var cross = el('line', { class: 'cross', y1: m.t, y2: PH, visibility: 'hidden' }); svg.appendChild(cross);
    var tip = document.createElement('div'); tip.className = 'tip'; tip.hidden = true;
    box.innerHTML = ''; box.appendChild(svg); box.appendChild(tip);
    svg.addEventListener('pointermove', function (e) {
      var r = svg.getBoundingClientRect(), sx = (e.clientX - r.left) / r.width * W, i = Math.max(0, Math.min(n - 1, Math.floor((sx - m.l) / step))), b = C.c[i];
      cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.setAttribute('visibility', 'visible');
      var sw = C.sw.filter(function (s) { return s.d === b[0]; }).map(function (s) { return s.l; }).join(' ');
      tip.innerHTML = '<div style="margin-bottom:3px">' + fmtDate(b[0], { weekday: 'short', month: 'short', day: 'numeric' }) + (sw ? ' · <b>' + sw + '</b>' : '') + '</div>' +
        '<div class="row">O <b>' + b[1].toFixed(2) + '</b> H <b>' + b[2].toFixed(2) + '</b></div><div class="row">L <b>' + b[3].toFixed(2) + '</b> C <b>' + b[4].toFixed(2) + '</b></div>';
      tip.hidden = false; var bx = X(i) / W * r.width, left = bx + 12; if (left + tip.offsetWidth > r.width) left = bx - tip.offsetWidth - 12;
      tip.style.left = Math.max(0, left) + 'px'; tip.style.top = '8px';
    });
    svg.addEventListener('pointerleave', function () { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); });
  }
  var SWSEL = { swpanel: '.hold[data-t]', swpanel2: '.dk[data-t]' };
  function closeSwing(pid) {
    openT[pid] = null; $(pid).hidden = true;
    document.querySelectorAll(SWSEL[pid]).forEach(function (c) { c.setAttribute('aria-expanded', 'false'); });
  }
  function openSwing(t, pid) {
    pid = pid || 'swpanel';
    if (openT[pid] === t) { closeSwing(pid); return; }
    openT[pid] = t; $(pid).hidden = false;
    // drop the chart down right under the tapped card (full row in the grid)
    var card = document.querySelector(SWSEL[pid] + '[data-t="' + t + '"]');
    if (card) {   // after the last card on the tapped card's row, so the row stays intact
      var panel = $(pid), grid = card.parentNode;
      panel.hidden = true;            // measure the rows without the panel in the way
      var row = card.offsetTop, last = card;
      Array.prototype.forEach.call(grid.children, function (c) { if (c !== panel && c.offsetTop === row) last = c; });
      if (last.nextSibling !== panel) grid.insertBefore(panel, last.nextSibling);
      panel.hidden = false;
    }
    document.querySelectorAll(SWSEL[pid]).forEach(function (c) { c.setAttribute('aria-expanded', String(c.getAttribute('data-t') === t)); });
    drawSwing(t, pid);
    $(pid).scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  $('holdings').addEventListener('click', function (e) { var c = e.target.closest('.hold[data-t]'); if (c) openSwing(c.getAttribute('data-t')); });
  $('holdings').addEventListener('keydown', function (e) { var c = e.target.closest('.hold[data-t]'); if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openSwing(c.getAttribute('data-t')); } });
  var swr; window.addEventListener('resize', function () { clearTimeout(swr); swr = setTimeout(function () { Object.keys(openT).forEach(function (pid) { if (openT[pid]) drawSwing(openT[pid], pid); }); }, 150); });

  // plan + your own weekly calls ("Mine", the human model)
  (function () {
    var P = D.plan, SL = D.sleeve, HU = D.human, A_ = null;
    if (!P || !SL) { $('plan-hint').textContent = ''; return; }
    var A = P.auto, md = { month: 'short', day: 'numeric' };
    // ---- calls: {friday: {m: auto|steps|cash|custom, s, v, c, note, at}} in localStorage
    // calls live in docs/my_calls.json in the repo (synced through GitHub's API with the viewer's
    // token) and are cached in localStorage; a removed call is kept as {m:'del'} so removals sync too
    var CK = 'nibii-calls-v1', TK = 'nibii-gh-token', calls = {}, act = {};
    var GH = { owner: 'danreed001-droid', repo: 'NIBII', path: 'docs/my_calls.json', branch: 'main' };
    var MODES = ['auto', 'boost', 'steps', 'cash', 'custom', 'del'];
    function clean(c) {
      if (!c || MODES.indexOf(c.m) < 0) return null;
      var cc = { m: c.m, note: String(c.note || '').slice(0, 300), at: String(c.at || '') };
      if (c.m === 'custom') { cc.s = Math.max(0, Math.min(100, Math.round(+c.s || 0))); cc.v = Math.max(0, Math.min(100 - cc.s, Math.round(+c.v || 0))); cc.c = 100 - cc.s - cc.v; }
      var TKR = /^[A-Z][A-Z0-9.\-]{0,9}$/;
      var sw = (Array.isArray(c.swaps) ? c.swaps : []).filter(function (x) { return Array.isArray(x) && TKR.test(x[0]) && TKR.test(x[1]); }).slice(0, 5).map(function (x) { return [x[0], x[1]]; });
      var dr = (Array.isArray(c.drops) ? c.drops : []).filter(function (x) { return TKR.test(x); }).slice(0, 5);
      if (sw.length) cc.swaps = sw;
      if (dr.length) cc.drops = dr;
      return cc;
    }
    // swap / drop helpers: candidates are ranks 6-10 that the model doesn't hold
    var MODEL = D.holdings.map(function (h) { return h.t; }), TBL = {};
    D.table.forEach(function (r) { TBL[r.t] = r; });
    D.holdings.forEach(function (h) { if (!TBL[h.t]) TBL[h.t] = h; });
    var BOOSTL = (A_ = D.plan && D.plan.auto && D.plan.auto.boost) ? A_.holdings : MODEL;
    if (A_) A_.rows.forEach(function (r) { if (!TBL[r.t]) TBL[r.t] = r; });
    function modelFor(m) { return m === 'boost' ? BOOSTL : MODEL; }
    function candsFor(m) { var ml = modelFor(m); return D.table.filter(function (r) { return r.rank && r.rank <= 10 && ml.indexOf(r.t) < 0; }); }
    var CANDS = candsFor('auto');
    function slotsFor(model, c) {   // mirrors mtl/human.slots_for for this week's ranks
      var drops = (c && c.drops) || [], swaps = {}, used = {};
      ((c && c.swaps) || []).forEach(function (x) { swaps[x[0]] = x[1]; });
      model.forEach(function (t) { used[t] = 1; });
      return model.map(function (t) {
        if (drops.indexOf(t) >= 0) return null;
        var r = swaps[t];
        if (r && TBL[r] && TBL[r].rank && TBL[r].rank <= 10 && !used[r]) { used[r] = 1; return r; }
        return t;
      });
    }
    function relive() { act = {}; Object.keys(calls).forEach(function (k) { if (calls[k].m !== 'del') act[k] = calls[k]; }); }
    function merge(src) {   // newest 'at' wins per week; returns how many changed
      var n = 0;
      Object.keys(src || {}).forEach(function (k) {
        var c = clean(src[k]);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(k) || !c) return;
        if (!calls[k] || (c.at || '') > (calls[k].at || '')) { calls[k] = c; n++; }
      });
      relive(); return n;
    }
    try { merge(JSON.parse(localStorage.getItem(CK) || '{}')); } catch (e) {}
    function saveCalls() { relive(); try { localStorage.setItem(CK, JSON.stringify(calls)); return true; } catch (e) { return false; } }
    var token = ''; try { token = localStorage.getItem(TK) || ''; } catch (e) {}
    function b64e(t) { return btoa(unescape(encodeURIComponent(t))); }
    function b64d(t) { return decodeURIComponent(escape(atob(String(t).replace(/\s/g, '')))); }
    var API = 'https://api.github.com/repos/' + GH.owner + '/' + GH.repo + '/contents/' + GH.path;
    function ghGet() {
      return fetch(API + '?ref=' + GH.branch + '&t=' + Date.now(), { headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' }, cache: 'no-store' })
        .then(function (r) {
          if (r.status === 404) return { sha: null, calls: {} };
          if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? 'token' : 'http ' + r.status);
          return r.json().then(function (j) { var d = {}; try { d = JSON.parse(b64d(j.content)); } catch (x) {} return { sha: j.sha, calls: (d && d.calls) || {} }; });
        });
    }
    var syncNote = '', remote = null;   // remote: the repo copy, once loaded
    function same(a, b) {
      var f = function (c) { return c ? JSON.stringify([c.m, c.s, c.v, c.swaps || [], c.drops || [], c.note || '']) : ''; };
      return f(a) === f(b);
    }
    function pendingCalls() {   // saved here but not (yet) in the repo copy
      var out = {};
      Object.keys(calls).forEach(function (k) {
        var r = remote && remote[k];
        if (calls[k].m === 'del' ? r && r.m !== 'del' : !same(calls[k], r)) out[k] = calls[k];
      });
      return out;
    }
    function submitBar() {
      if (!$('submitbar')) return;
      var pc = pendingCalls(), n = Object.keys(pc).length;
      $('submitbar').hidden = !n;
      if (!n) return;
      $('submit-msg').innerHTML = '<b>' + n + '</b> call' + (n > 1 ? 's' : '') + ' saved in this browser, not in the repo yet.';
      var body = 'Calls submitted from the Top 5 dashboard. Leave the block below as-is — the Calls intake workflow reads it, records the calls in docs/my_calls.json and closes this issue.\n\n```json\n' +
        JSON.stringify({ calls: pc }) + '\n```\n';
      $('call-submit').href = 'https://github.com/' + GH.owner + '/' + GH.repo + '/issues/new?title=' + encodeURIComponent('calls ' + Object.keys(pc).sort().pop()) + '&body=' + encodeURIComponent(body);
    }
    function syncUI(msg) {
      if (msg != null) syncNote = msg;
      $('sync-status').textContent = (token ? 'Saving straight to the repo from this device' : 'Calls recorded in the repo are shown on every device') + (syncNote ? ' · ' + syncNote : '');
      $('sync-toggle').textContent = token ? 'Sync settings' : 'Optional: save directly with a GitHub token';
    }
    function pull() {   // read the repo copy: through the API with a token (fresh), else the Pages copy
      var get = token ? ghGet().then(function (g) { return g.calls; })
        : fetch('my_calls.json?t=' + Date.now(), { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : {}; }).then(function (j) { return (j && j.calls) || {}; });
      return get.then(function (rc) {
        remote = {}; Object.keys(rc || {}).forEach(function (k) { var c = clean(rc[k]); if (c) remote[k] = c; });
        var n = merge(rc); saveCalls(); submitBar(); return n;
      });
    }
    function push(what, tries) {
      if (!token) { submitBar(); return Promise.resolve(false); }
      syncUI('saving to repo…');
      return ghGet().then(function (g) {
        merge(g.calls); saveCalls();
        var body = { message: 'My calls: ' + what, branch: GH.branch,
                     content: b64e(JSON.stringify({ app: 'nibii-calls', v: 1, calls: calls }, null, 1) + '\n') };
        if (g.sha) body.sha = g.sha;
        return fetch(API, { method: 'PUT', headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      }).then(function (r) {
        if ((r.status === 409 || r.status === 422) && (tries || 0) < 2) return push(what, (tries || 0) + 1);
        if (!r.ok) throw new Error(r.status === 401 || r.status === 403 || r.status === 404 ? 'token' : 'http ' + r.status);
        syncUI('saved to repo ' + new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })); return true;
      }).catch(function (e) {
        syncUI(e.message === 'token' ? 'repo refused the token — check it can write Contents on NIBII' : 'could not reach GitHub, saved in this browser'); return false;
      });
    }
    var WK = {}; (HU ? HU.weeks : []).forEach(function (w) { WK[w[0]] = w; });
    function callFor(fri) { var ks = Object.keys(act).filter(function (k) { return k <= fri; }).sort(); return ks.length ? act[ks[ks.length - 1]] : null; }
    function sigOf(cs) {   // mirrors mtl/human.signature
      return Object.keys(cs).sort().map(function (k) {
        var c = cs[k];
        return [k, c.m, c.s == null ? null : c.s, c.v == null ? null : c.v,
                (c.swaps || []).map(function (x) { return [x[0], x[1]]; }).sort(), (c.drops || []).slice().sort()];
      });
    }
    function share(txt) { return +String(txt).split('/')[0] / 100; }
    function mixOf(c, fri) {   // -> [stocks, sleeve, cash] or null
      if (!c) return null;
      var w = WK[fri];
      if (c.m === 'auto') { var s1 = w ? w[2] : A ? share(A.split) : 1; return [s1, 1 - s1, 0]; }
      if (c.m === 'boost') { var s3 = w && w[4] != null ? w[4] : A && A.boost ? share(A.boost.split) : 1; return [0, 1 - s3, 0, s3]; }
      if (c.m === 'steps') { var s2 = w ? w[3] : A && A.steps ? share(A.steps.split) : 1; return [s2, 1 - s2, 0]; }
      if (c.m === 'cash') return [0, 0, 1];
      return [c.s / 100, c.v / 100, c.c / 100];
    }
    function callLabel(c) {
      if (!c) return '—';
      var b = c.m === 'auto' ? 'Follow Auto' : c.m === 'boost' ? 'Follow Boost' : c.m === 'steps' ? 'Follow Steps' : c.m === 'cash' ? 'No trade (cash)' : 'Custom';
      var x = [];
      (c.swaps || []).forEach(function (s2) { x.push(s2[0] + '→' + s2[1]); });
      (c.drops || []).forEach(function (d2) { x.push('drop ' + d2); });
      return b + (c.m !== 'cash' && x.length ? ' · ' + x.join(', ') : '');
    }
    function mixTxt(m) { return Math.round((m[0] + (m[3] || 0)) * 100) + '/' + Math.round(m[1] * 100) + (m[2] ? '/' + Math.round(m[2] * 100) : ''); }
    var inForce = A ? A.decided : D.asOf;   // the signal Friday whose trades are (or will be) held now

    var mix = P['default'], acct = 10000;
    try { mix = localStorage.getItem('nibii-plan-mix3') || mix; acct = +(localStorage.getItem('nibii-plan-acct') || acct) || 10000; } catch (e) {}
    if (P.splits.indexOf(mix) < 0) mix = P['default'];
    $('mix-seg').innerHTML = P.splits.map(function (m) { return '<button type="button" data-v="' + m + '">' + (m === 'auto' ? 'Auto' : m === 'boost' ? 'Boost' : m === 'guard' ? 'Guard' : m === 'steps' ? 'Steps' : m === 'mine' ? 'Mine' : m) + '</button>'; }).join('');
    function usd(v) { return '$' + (v < 100 ? v.toFixed(2) : Math.round(v).toLocaleString()); }
    var name = {}; SL.assets.forEach(function (a) { name[a.t] = a; });
    function draw() {
      document.querySelectorAll('#mix-seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === mix)); });
      var m, mine = null;
      if (mix === 'mine') { mine = callFor(inForce); m = mixOf(mine, inForce) || [A ? share(A.split) : 1, A ? 1 - share(A.split) : 0, 0]; }
      else if (mix === 'auto' && A) m = [share(A.split), 1 - share(A.split), 0];
      else if (mix === 'guard' && A && A.guard) m = [A.guard.weights[0], A.guard.weights[1], 0, A.guard.weights[2]];
      else if (mix === 'boost' && A && A.boost) m = [share(A.boost.split), 1 - share(A.boost.split), 0];
      else if (mix === 'steps' && A) m = [share(A.steps.split), 1 - share(A.steps.split), 0];
      else m = [share(mix), 1 - share(mix), 0];
      var mineBoost = mix === 'mine' && mine && mine.m === 'boost';
      if (mineBoost) m = [m[3], m[1], m[2]];
      var spyAmt = acct * (m[3] || 0);
      var stocks = acct * m[0], sleeve = acct * m[1], cash = acct * m[2], per = stocks / D.rule.topN;
      $('plan-hint').textContent = (mix === 'auto' ? 'auto mix this week: ' : mix === 'boost' ? 'auto + news boost this week: ' : mix === 'guard' ? 'auto + guard this week: ' : mix === 'steps' ? 'steps mix this week: ' : mix === 'mine' ? 'your call: ' : '') +
        Math.round(m[0] * 100) + '% top 5 · ' + Math.round(m[1] * 100) + '% sleeve' + (m[3] ? ' · ' + Math.round(m[3] * 100) + '% SPY' : '') + (m[2] ? ' · ' + Math.round(m[2] * 100) + '% cash' : '') + ' · no leverage · trade & reset Mondays';
      var hs = D.holdings.slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); });
      var sp = name[SL.held] || {};
      function sh(v, px) { if (!px) return ''; var n = v / px; return '≈' + n.toFixed(n < 10 ? 2 : 0) + ' sh'; }
      var BS = (mix === 'boost' || mineBoost) && A && A.boost ? A.boost : null;
      if (BS) {   // the boosted list: model holdings it keeps first, boosted names in the slots they took
        BS.rows.forEach(function (r) { if (!TBL[r.t]) TBL[r.t] = r; });
        var keepB = hs.filter(function (h) { return BS.holdings.indexOf(h.t) >= 0; }), inB = BS.holdings.filter(function (t) { return !hs.some(function (h) { return h.t === t; }); });
        hs = keepB.concat(hs.filter(function (h) { return BS.holdings.indexOf(h.t) < 0; }));
      }
      var shown = BS ? hs.map(function (h, i) { return i < keepB.length ? h.t : inB[i - keepB.length] || h.t; })
        : mix === 'mine' && mine ? slotsFor(hs.map(function (h) { return h.t; }), mine) : hs.map(function (h) { return h.t; });
      if (mineBoost) { var sb = slotsFor(shown, mine); hs = shown.map(function (t) { return TBL[t] || { t: t }; }); shown = sb; }
      var gapOf = {}; if (BS) BS.gaps.forEach(function (g) { gapOf[g.t] = g.d; });
      var rows = stocks > 0 ? shown.map(function (t, i) {
        if (!t) return '<tr><td><span class="sw" style="--c:var(--muted)"></span><b>Cash</b> <span class="muted">dropped ' + esc(hs[i].t) + '</span></td><td class="r">' + usd(per) + '</td><td></td></tr>';
        var h = TBL[t] || {}, swapped = t !== hs[i].t;
        return '<tr><td><span class="sw" style="--c:var(--s-strat)"></span><b>' + esc(t) + '</b> <span class="muted nm2">' + (swapped ? (BS && !mineBoost ? (gapOf[t] ? 'news boost (gap ' + fmtDate(gapOf[t], md) + ') instead of ' : 'boost list holds it instead of ') : 'swapped in for ') + esc(hs[i].t) : esc(h.n || '')) + '</span></td>' +
          '<td class="r">' + usd(per) + '</td><td class="r muted">' + sh(per, h.close) + '</td></tr>';
      }).join('') : '<tr class="borrow"><td>Top 5 stocks — not held this week</td><td class="r">$0</td><td></td></tr>';
      rows += sleeve > 0 ? '<tr><td><span class="sw" style="--c:var(--s-plan)"></span><b>' + esc(SL.held) + '</b> <span class="muted">sleeve<span class="nm2"> · ' + esc(sp.n || '') + '</span></span></td>' +
        '<td class="r">' + usd(sleeve) + '</td><td class="r muted">' + sh(sleeve, sp.close) + '</td></tr>'
        : '<tr class="borrow"><td>Sleeve (' + esc(SL.held) + ') — not held this week</td><td class="r">$0</td><td></td></tr>';
      if (spyAmt > 0) rows += '<tr><td><span class="sw" style="--c:var(--s-spy)"></span><b>SPY</b> <span class="muted nm2">bear guard</span></td><td class="r">' + usd(spyAmt) + '</td><td class="r muted">' + sh(spyAmt, A.guard.spyClose) + '</td></tr>';
      if (cash > 0) rows += '<tr><td><span class="sw" style="--c:var(--muted)"></span><b>Cash</b> <span class="muted nm2">T-bills or money market</span></td><td class="r">' + usd(cash) + '</td><td></td></tr>';
      rows += '<tr class="sum"><td>Total</td><td class="r">' + usd(acct) + '</td><td></td></tr>';
      $('alloc').innerHTML = '<tbody>' + rows + '</tbody>';
      var st = P.stats[mix], S0 = D.stats.strategy;
      $('plan-stats').innerHTML = (st ? '<span>Since ' + SINCE + ' ' + (mix === 'auto' ? 'with auto' : mix === 'boost' ? 'with auto + news boost' : mix === 'guard' ? 'with auto + guard' : mix === 'steps' ? 'with steps' : 'at ' + mix) + ': <b class="pos">' + pct(st.annual, 0) + '</b> a year, worst drop <b class="neg">' + pct(st.maxDD, 0) + '</b></span>'
          : '<span>Your record is scored below, from your first call.</span>') +
        '<span class="muted">Top 5 alone: ' + pct(S0.annual, 0) + ' a year, worst drop ' + pct(S0.maxDD, 0) + '</span>';
      if (mix === 'mine') {
        $('auto-note').innerHTML = mine ? '<b>Mine:</b> your call in force — ' + callLabel(mine) + ' → <b>' + mixTxt(m) + '</b>' + (mine.note ? ' · “' + esc(mine.note) + '”' : '') + '. Change it under Your calls.'
          : '<b>Mine:</b> no call yet, so this shows Auto. Make one under Your calls.';
      } else if (A && mix === 'boost' && A.boost) {
        var B = A.boost, gl = B.gaps.length ? B.gaps.map(function (g) { return '<b>' + esc(g.t) + '</b> ' + fmtDate(g.d, md) + (g.held ? ' (held)' : ''); }).join(', ') : 'none';
        $('auto-note').innerHTML = '<b>Auto + News boost:</b> the same top 5, but any stock that gapped up ' + Math.round(B.gap * 100) + '%+ on news (opened and closed ' + Math.round(B.gap * 100) +
          '%+ up, near the day’s high — usually earnings) in the last 4 weeks replaces the weakest holding, even if it isn’t in the top 5 yet; then the Auto mix on top. ' +
          'News gaps in the last 4 weeks: ' + gl + '. ' +
          (B.boosted.length ? 'This week it holds <b>' + B.boosted.map(esc).join(', ') + '</b> instead of ' + B.replaced.map(esc).join(', ') + '. ' : 'This week it holds the same stocks as the plain top 5. ') +
          (D.signalDay ? 'Auto mix ' + B.split + (B.split !== B.prevSplit ? ' (was ' + B.prevSplit + ')' : '') + '. ' : '') +
          'Since ' + SINCE + ': ' + pct(P.stats.boost.annual, 0) + ' a year vs ' + pct(P.stats.auto.annual, 0) + ' for Auto; tested 2000–2026 about +32% a year vs +25%, worst drop −62% vs −73%, and it caught the 2009 rebound (+35% vs −27%). ' +
          'Its list differed from the plain top 5 in ' + B.weeksDiff + ' of ' + A.weeks + ' weeks. Expect fewer real gains than the test: it only knows today’s index members.';
      } else if (A && mix === 'guard' && A.guard) {
        var G = A.guard;
        $('auto-note').innerHTML = '<b>Auto + Guard:</b> the Auto mix, plus a bear-market guard: while SPY closes below its level a year earlier, ' + Math.round(G.share * 100) +
          '% of the stock part sits in SPY instead of the top 5. ' + (D.signalDay ? 'This Friday: ' : 'Last Friday: ') + 'SPY ' + (G.spyNow != null ? G.spyNow.toFixed(2) : '–') + ' vs ' +
          (G.spyYearAgo != null ? G.spyYearAgo.toFixed(2) : '–') + ' a year ago → guard <b>' + (G.bear ? 'ON' : 'off') + '</b>' +
          (D.signalDay && G.bear !== G.prevBear ? ' (changed — trade it Monday)' : '') + '.' + (!D.signalDay && G.previewBear != null && G.previewBear !== G.bear ? ' If Friday were today the guard would turn ' + (G.previewBear ? 'ON' : 'off') + '.' : '') +
          ' It costs a little in good years (since ' + SINCE + ': ' + pct(P.stats.guard.annual, 0) + ' a year vs ' + pct(P.stats.auto.annual, 0) + ' for Auto) and pays off in long bear markets: tested 2000–2026, about the same +25% a year with a worst drop near −63% instead of −73%, and 2009 about −5% instead of −27%. On ' + G.weeksBear + ' weeks since ' + SINCE + '.';
      } else if (A && mix === 'steps' && A.steps) {
        var dn2 = A.down.length, lst2 = dn2 ? ' (' + A.down.map(esc).join(', ') + ')' : '', S2 = A.steps;
        $('auto-note').innerHTML = '<b>Steps:</b> 100% top 5 when no holding is in a daily lower-low downtrend at Friday’s close; 1 down → 80/20, 2 down → 60/40, 3 or more → 40/60 (since Oct 2026 Auto uses these same tiers). ' +
          (D.signalDay ? 'This Friday: ' : 'Last Friday: ') + dn2 + ' of ' + A.checked.length + ' in a downtrend' + lst2 + ' → <b>' + S2.split + '</b>' +
          (D.signalDay && S2.split !== S2.prevSplit ? ' (was ' + S2.prevSplit + ' — change it Monday)' : '') + '.' +
          (!D.signalDay && S2.preview ? ' If Friday were today: ' + A.previewDown.length + ' in a downtrend → ' + S2.preview + '.' : '') +
          ' Since ' + SINCE + ' it was below 100% in ' + S2.weeksLow + ' of ' + A.weeks + ' weeks.';
      } else if (A && mix !== 'auto') {
        $('auto-note').innerHTML = 'Fixed mix: reset to ' + mix + ' every Monday whatever the charts say. Auto and Steps adjust it to how many holdings are in a downtrend.';
      } else if (A) {
        var dn = A.down.length, lst = dn ? ' (' + A.down.map(esc).join(', ') + ')' : '';
        $('auto-note').innerHTML = '<b>Auto:</b> 100% top 5; for each holding in a daily lower-low downtrend at Friday’s close, 20% moves to the sleeve for the week (1 → 80/20, 2 → 60/40, 3+ → 40/60). ' +
          (D.signalDay ? 'This Friday: ' : 'Last Friday: ') + dn + ' of ' + A.checked.length + ' in a downtrend' + lst + ' → <b>' + A.split + '</b>' +
          (D.signalDay && A.split !== A.prevSplit ? ' (was ' + A.prevSplit + ' — change it Monday)' : '') + '.' +
          (!D.signalDay && A.preview ? ' If Friday were today: ' + A.previewDown.length + ' in a downtrend → ' + A.preview + '.' : '') +
          ' Since ' + SINCE + ' it was below 100% in ' + A.weeksLow + ' of ' + A.weeks + ' weeks.';
      }
    }
    $('mix-seg').onclick = function (e) { var b = e.target.closest('button'); if (!b) return; mix = b.getAttribute('data-v'); try { localStorage.setItem('nibii-plan-mix3', mix); } catch (x) {} draw(); };
    var inp = $('acct');
    inp.value = Math.round(acct).toLocaleString();
    inp.oninput = function () { var v = +inp.value.replace(/[^0-9.]/g, ''); if (v > 0) { acct = v; try { localStorage.setItem('nibii-plan-acct', String(v)); } catch (x) {} draw(); } };
    inp.onblur = function () { inp.value = Math.round(acct).toLocaleString(); };
    draw();

    // ---- your call for the coming trade (keyed by its signal Friday)
    var FRI = D.signalDate, wkNow = WK[FRI], pick = null;
    $('call-title').textContent = 'Your call for the week of Mon ' + fmtDate(D.tradeDate, md);
    $('call-sub').textContent = (D.signalDay ? 'Uses today’s' : 'Will use Friday ' + fmtDate(FRI, md) + '’s') + ' signal · trade Mon ' + fmtDate(D.tradeDate, md) + ', 3:30–4:00 pm ET · held until the next Monday trade';
    function autoNow(kind) {
      var col = kind === 'auto' ? 2 : kind === 'boost' ? 4 : 3;
      if (wkNow && wkNow[col] != null) return mixTxt([wkNow[col], 1 - wkNow[col], 0]) + ' this week';
      var pv = A && (kind === 'auto' ? A.preview : kind === 'boost' ? A.boost && A.boost.split : A.steps && A.steps.preview);
      return 'set Friday' + (pv ? ' (now ' + pv + ')' : '');
    }
    var OPTS = [['boost', 'Follow Boost', autoNow('boost')], ['auto', 'Follow Auto', autoNow('auto')], ['steps', 'Follow Steps', autoNow('steps')],
                ['cash', 'No trade', 'sit in cash this week'], ['custom', 'Custom', 'your own stocks / sleeve / cash']];
    $('choices').innerHTML = OPTS.map(function (o) { return '<button type="button" class="choice" role="radio" aria-checked="false" data-m="' + o[0] + '"><b>' + o[1] + '</b><span>' + o[2] + '</span></button>'; }).join('');
    function cuSync() {
      var sv = Math.max(0, Math.min(100, Math.round(+$('cu-s').value || 0))), vv = Math.max(0, Math.min(100 - sv, Math.round(+$('cu-v').value || 0)));
      $('cu-c').textContent = 100 - sv - vv; return [sv, vv, 100 - sv - vv];
    }
    $('cu-s').oninput = cuSync; $('cu-v').oninput = cuSync;
    function choose(mm) {
      pick = mm;
      document.querySelectorAll('#choices .choice').forEach(function (b) { b.setAttribute('aria-checked', String(b.getAttribute('data-m') === mm)); });
      $('custom').hidden = mm !== 'custom';
      if ($('picks')) { $('picks').hidden = mm === 'cash'; if (pickList !== modelFor(mm)) drawPicks(curCall && curCall.m === mm ? curCall : null); }
    }
    var pickList = null, curCall = null;
    $('choices').onclick = function (e) { var b = e.target.closest('.choice'); if (b) choose(b.getAttribute('data-m')); };
    function drawPicks(c) {
      var box = $('picks'), ml = modelFor(pick), CANDS = candsFor(pick);
      pickList = ml;
      if (!ml.length) { box.innerHTML = ''; return; }
      var swaps = {}, drops = (c && c.drops) || [];
      ((c && c.swaps) || []).forEach(function (x) { swaps[x[0]] = x[1]; });
      var opts = function (t) {
        var cur = drops.indexOf(t) >= 0 ? 'drop' : swaps[t] && CANDS.some(function (r) { return r.t === swaps[t]; }) ? 'swap:' + swaps[t] : 'keep';
        return '<option value="keep"' + (cur === 'keep' ? ' selected' : '') + '>Keep</option><option value="drop"' + (cur === 'drop' ? ' selected' : '') + '>Drop → cash</option>' +
          CANDS.map(function (r) { var v = 'swap:' + r.t; return '<option value="' + v + '"' + (cur === v ? ' selected' : '') + '>Swap → #' + r.rank + ' ' + esc(r.t) + ' (' + pct(r.score, 0) + ')</option>'; }).join('');
      };
      box.innerHTML = '<p class="ph">' + (pick === 'boost' ? 'Boost list' : 'Stocks') + ' · keep, drop (slot goes to cash), or swap in a top-10 stock not held</p>' + ml.map(function (t) { return TBL[t] || { t: t }; }).sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); }).map(function (h) {
        return '<div class="pk" data-t="' + esc(h.t) + '"><span><b>' + esc(h.t) + '</b> <span class="muted">#' + (h.rank || '–') + ' · ' + pct(h.score, 0) + '</span></span>' +
          '<select aria-label="' + esc(h.t) + ': keep, drop or swap">' + opts(h.t) + '</select></div>';
      }).join('') + (CANDS.length ? '' : '<p class="swnote">No stocks ranked 6–10 outside the five this week.</p>');
      box.querySelectorAll('.pk').forEach(function (row) { var sel = row.querySelector('select'); row.classList.toggle('changed', sel.value !== 'keep'); sel.onchange = function () { row.classList.toggle('changed', sel.value !== 'keep'); }; });
    }
    function readPicks() {
      var swaps = [], drops = [], seen = {};
      $('picks').querySelectorAll('.pk').forEach(function (row) {
        var t = row.getAttribute('data-t'), v = row.querySelector('select').value;
        if (v === 'drop') drops.push(t);
        else if (v.indexOf('swap:') === 0 && !seen[v]) { seen[v] = 1; swaps.push([t, v.slice(5)]); }
      });
      return { swaps: swaps, drops: drops };
    }
    function showCall() {
      var own = act[FRI], carried = callFor(FRI);
      var c = own || carried;
      curCall = c;
      choose(c ? c.m : 'boost');
      drawPicks(c);
      if (c && c.m === 'custom') { $('cu-s').value = c.s; $('cu-v').value = c.v; }
      cuSync();
      $('call-note').value = own && own.note ? own.note : '';
      $('call-clear').hidden = !own;
      $('call-status').textContent = own ? 'Saved: ' + callLabel(own) + (own.m === 'custom' ? ' ' + own.s + '/' + own.v + '/' + own.c : '')
        : carried ? 'Carrying forward: ' + callLabel(carried) : 'No call yet for this week.';
    }
    $('call-save').onclick = function () {
      if (!pick) return;
      var c = { m: pick, note: $('call-note').value.trim().slice(0, 300), at: new Date().toISOString() };
      if (pick === 'custom') { var cu = cuSync(); c.s = cu[0]; c.v = cu[1]; c.c = cu[2]; }
      if (pick !== 'cash') { var pk = readPicks(); if (pk.swaps.length) c.swaps = pk.swaps; if (pk.drops.length) c.drops = pk.drops; }
      calls[FRI] = c;
      var ok = saveCalls(); showCall(); draw(); drawRecord();
      if (!ok && !token) $('call-status').textContent = 'Could not save — this browser is blocking storage.';
      push('week of ' + D.tradeDate + ' — ' + callLabel(c));
    };
    $('call-clear').onclick = function () { calls[FRI] = { m: 'del', note: '', at: new Date().toISOString() }; saveCalls(); showCall(); draw(); drawRecord(); push('removed week of ' + D.tradeDate); };
    $('call-export').onclick = function () {
      var blob = new Blob([JSON.stringify({ app: 'nibii-calls', v: 1, calls: calls }, null, 1)], { type: 'application/json' });
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'nibii-my-calls.json'; document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    };
    $('call-import').onchange = function (e) {
      var f = e.target.files && e.target.files[0]; if (!f) return;
      var r = new FileReader();
      r.onload = function () {
        var n = 0, src = {};
        try { var j = JSON.parse(r.result); src = j && j.calls ? j.calls : j; } catch (x) {}
        var now = new Date().toISOString();
        Object.keys(src || {}).forEach(function (k) { if (src[k] && typeof src[k] === 'object') src[k] = Object.assign({}, src[k], { at: now }); });
        n = merge(src); saveCalls(); showCall(); draw(); drawRecord();
        $('call-status').textContent = n ? 'Restored ' + n + ' call' + (n > 1 ? 's' : '') + '.' : 'That file had no calls in it.';
        if (n) push('restored ' + n + ' calls');
        e.target.value = '';
      };
      r.readAsText(f);
    };
    // sync settings
    $('sync-toggle').onclick = function () { $('sync-panel').hidden = !$('sync-panel').hidden; };
    $('sync-save').onclick = function () {
      var t = $('sync-token').value.trim(); if (!t) return;
      token = t; try { localStorage.setItem(TK, t); } catch (x) {}
      $('sync-token').value = ''; syncUI('checking…');
      pull().then(function () { showCall(); draw(); drawRecord(); return push('connected a device'); })
        .then(function (ok) { if (ok) $('sync-panel').hidden = true; })
        .catch(function (e) {
          token = ''; try { localStorage.removeItem(TK); } catch (x) {}
          syncUI(e && e.message === 'token' ? 'GitHub refused that token — it needs Contents: Read and write on NIBII' : 'could not reach GitHub — try again');
        });
    };
    $('sync-off').onclick = function () { token = ''; try { localStorage.removeItem(TK); } catch (x) {} syncUI('this device disconnected'); };


    // ---- your record: your calls vs following Auto / Steps from your first call
    function simulate(mixAt, startTrade) {
      var tradeFri = {}; HU.weeks.forEach(function (w) { tradeFri[w[1]] = w[0]; });
      var out = [], a = 0, b = 0, c = 0, bb = 0, prev = null;
      HU.days.forEach(function (x) {
        if (x[0] < startTrade) return;
        if (prev) { a *= x[1] / prev[1]; b *= x[2] / prev[2]; c *= x[3] / prev[3]; bb *= (x[4] || x[1]) / (prev[4] || prev[1]); }
        var nav = prev ? a + b + c + bb : 1;
        if (x[0] in tradeFri) { var mm = mixAt(tradeFri[x[0]]) || [1, 0, 0]; a = nav * mm[0]; b = nav * mm[1]; c = nav * mm[2]; bb = nav * (mm[3] || 0); }
        out.push([x[0], nav]); prev = x;
      });
      return out;
    }
    var RR = { a: '', b: '' };
    $('rr-from').onchange = function () { RR.a = $('rr-from').value; drawRecord(); };
    $('rr-to').onchange = function () { RR.b = $('rr-to').value; drawRecord(); };
    $('rr-all').onclick = function () { RR.a = RR.b = ''; drawRecord(); };
    function drawRecord() {
      var box = $('rec'), keys = Object.keys(act).sort();
      $('rec-range').hidden = true;
      if (!HU || !HU.days.length) { box.innerHTML = '<p class="muted">Record data is not available in this build.</p>'; return; }
      if (!keys.length) { box.innerHTML = '<p class="swnote">No calls yet. Make your first call on the left — your record starts at that week’s Monday trade and is compared with simply following Auto or Steps over the same weeks.</p>'; return; }
      var w0 = HU.weeks.filter(function (w) { return w[0] >= keys[0]; })[0];
      var f0 = keys[0], start = w0 ? w0[1] : D.tradeDate, lastDay = HU.days[HU.days.length - 1][0];
      if (start > lastDay) { box.innerHTML = '<p class="swnote">Your record starts at the close of <b>Mon ' + fmtDate(start, md) + '</b>, when your first call (' + esc(callLabel(act[f0])) + ') is traded. Check back after that close.</p>'; return; }
      var me = simulate(function (f) { return mixOf(callFor(f), f); }, start);
      // the daily update scores swaps / drops on real prices from the repo copy of the calls;
      // use it when it scored exactly these calls, else this page's estimate (model stocks)
      var SM = HU.mine, scored = !!(SM && SM.curve && SM.curve.length && JSON.stringify(SM.sig) === JSON.stringify(sigOf(act)));
      var hasPicks = keys.some(function (k) { return (act[k].swaps || []).length || (act[k].drops || []).length; });
      var baseC = null, slotsBy = {};
      if (scored) { me = SM.curve; baseC = SM.base; SM.weeks.forEach(function (w) { slotsBy[w[0]] = w[2]; }); }
      var au = simulate(function (f) { var w = WK[f]; return w ? [w[2], 1 - w[2], 0] : null; }, start);
      var stp = simulate(function (f) { var w = WK[f]; return w ? [w[3], 1 - w[3], 0] : null; }, start);
      var bst = simulate(function (f) { var w = WK[f]; return w && w[4] != null ? [0, 1 - w[4], 0, w[4]] : null; }, start);
      // optional From/To filter inside the record
      $('rec-range').hidden = false;
      var ra = RR.a && RR.a > start ? RR.a : start, rb = RR.b && RR.b < lastDay ? RR.b : lastDay;
      if (ra > rb) { var tt = ra; ra = rb; rb = tt; }
      $('rr-from').min = $('rr-to').min = start; $('rr-from').max = $('rr-to').max = lastDay;
      $('rr-from').value = ra; $('rr-to').value = rb;
      function cut(c) { return c.filter(function (p) { return p[0] >= ra && p[0] <= rb; }); }
      me = cut(me); au = cut(au); stp = cut(stp); bst = cut(bst); if (baseC) baseC = cut(baseC);
      if (me.length < 2) { box.innerHTML = '<p class="swnote">Pick a range with at least two trading days between ' + fmtDate(start, md) + ' and ' + fmtDate(lastDay, md) + '.</p>'; return; }
      function tot(c) { return c[c.length - 1][1] / c[0][1] - 1; }
      function dd(c) { var pk = c[0][1], m = 0; c.forEach(function (p) { pk = Math.max(pk, p[1]); m = Math.min(m, p[1] / pk - 1); }); return m; }
      var SER2 = [['You', me, 'var(--gold)'], ['Boost', bst, 'var(--s-boost)'], ['Auto', au, 'var(--s-plan)'], ['Steps', stp, 'var(--ink-2)']];
      var pickNote = scored && hasPicks && baseC && baseC.length > 1
        ? '<p class="swnote" style="margin:4px 0 0">Your swaps & drops: <b class="' + tone(tot(me) - tot(baseC)) + '">' + pct(tot(me) - tot(baseC)) + '</b> vs the same mixes with the model’s own five stocks.</p>'
        : hasPicks && !scored ? '<p class="swnote" style="margin:4px 0 0">Swaps and drops are scored on real prices by the next daily update (after 5:20pm ET) once your calls are synced to the repo — until then “You” uses the model’s stocks.</p>' : '';
      var html = '<div class="rec-tiles">' + SER2.map(function (s) {
        return '<div class="rec-tile"><div class="k"><i style="--c:' + s[2] + '"></i>' + s[0] + '</div><div class="v ' + tone(tot(s[1])) + '">' + pct(tot(s[1])) + '</div><div class="d">worst ' + pct(dd(s[1])) + '</div></div>';
      }).join('') + '</div>' + pickNote + '<p class="chart-sub" style="margin:0">' + (ra === start && rb === lastDay ? 'Since Mon ' + fmtDate(start, md) : fmtDate(ra, md) + ' – ' + fmtDate(rb, md)) + ' · ' + (me.length - 1) + ' trading days</p><div class="chart" id="rec-chart"></div>';
      // weekly table, newest first
      var wks = HU.weeks.filter(function (w) { return w[1] >= start && w[1] <= lastDay; });
      var allW = wks; wks = wks.filter(function (w, i) { var e2 = i + 1 < allW.length ? allW[i + 1][1] : lastDay; return e2 > ra && w[1] < rb; });
      function val(c, d) { var v = null; for (var i = 0; i < c.length && c[i][0] <= d; i++) v = c[i][1]; return v; }
      var rowsW = wks.map(function (w, i) {
        var j = allW.indexOf(w), full = j + 1 < allW.length ? allW[j + 1][1] : lastDay, c = callFor(w[0]), m = mixOf(c, w[0]) || [1, 0, 0];
        var b0 = w[1] < ra ? ra : w[1], end = full > rb ? rb : full;
        var rm = val(me, end) / val(me, b0) - 1, rau = val(au, end) / val(au, b0) - 1;
        return '<tr><td>' + fmtDate(w[1], md) + (full === lastDay && full !== w[1] ? '*' : '') + (b0 !== w[1] || end !== full ? '<span class="note-i">part</span>' : '') + '</td><td>' + esc(callLabel(c)) + ' <span class="muted">' + mixTxt(m) + '</span>' +
          (slotsBy[w[0]] ? '<span class="note-i">' + slotsBy[w[0]].map(function (t) { return t ? esc(t) : 'cash'; }).join(' · ') + '</span>' : '') +
          (act[w[0]] && act[w[0]].note ? '<span class="note-i">“' + esc(act[w[0]].note) + '”</span>' : '') + '</td>' +
          '<td class="r hide-xs">' + mixTxt([w[2], 1 - w[2], 0]) + '</td><td class="r ' + tone(rm) + '">' + (b0 === end ? '–' : pct(rm)) + '</td><td class="r ' + tone(rau) + '">' + (b0 === end ? '–' : pct(rau)) + '</td></tr>';
      }).reverse().slice(0, 52).join('');
      html += '<table class="wk"><thead><tr><th>Week of</th><th>Your call</th><th class="r hide-xs">Auto mix</th><th class="r">You</th><th class="r">Auto</th></tr></thead><tbody>' + rowsW + '</tbody></table>' +
        '<p class="swnote">* week still running. Weeks run Monday close to Monday close; cash earns the T-bill rate. A call you skip carries the last one forward.</p>';
      box.innerHTML = html;
      if (me.length >= 2) {
        var cb = $('rec-chart'), W = Math.max(280, cb.clientWidth), H = 150, mg = { l: 40, r: 52, t: 8, b: 18 };
        var lo = Infinity, hi = -Infinity; SER2.forEach(function (s) { s[1].forEach(function (p) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }); });
        var pad = (hi - lo) * 0.1 || 0.01; lo -= pad; hi += pad;
        var n = me.length;
        function X(i) { return mg.l + i / (n - 1) * (W - mg.l - mg.r); }
        function Y(v) { return mg.t + (1 - (v - lo) / (hi - lo)) * (H - mg.t - mg.b); }
        var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Your record vs Auto and Steps' });
        var g = el('g', { class: 'grid axis' }); svg.appendChild(g);
        [lo + pad, 1, hi - pad].forEach(function (v, j) { if (j === 1 && (v < lo || v > hi)) return; g.appendChild(el('line', { x1: mg.l, x2: W - mg.r, y1: Y(v), y2: Y(v) })); var t = el('text', { x: mg.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }); t.textContent = pct(v - 1, 0); g.appendChild(t); });
        SER2.slice().reverse().forEach(function (s) {
          svg.appendChild(el('path', { d: s[1].map(function (p, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join(''), style: 'fill:none;stroke-width:2;stroke:' + s[2] + (s[0] === 'Steps' ? ';stroke-dasharray:4 3' : '') }));
          var t = el('text', { x: W - mg.r + 6, y: Y(s[1][n - 1][1]) + 4, style: 'fill:var(--ink-2);font-size:11px' }); t.textContent = s[0]; svg.appendChild(t);
        });
        var ax = el('g', { class: 'axis' }); svg.appendChild(ax);
        [0, n - 1].forEach(function (i) { var t = el('text', { x: X(i), y: H - 4, 'text-anchor': i ? 'end' : 'start' }); t.textContent = fmtDate(me[i][0], md); ax.appendChild(t); });
        cb.appendChild(svg);
      }
    }
    showCall(); drawRecord(); syncUI('');
    pull().then(function (n) { if (n) { showCall(); draw(); drawRecord(); } syncUI(n ? 'loaded ' + n + ' from the repo' : ''); })
      .catch(function (e) { syncUI(e && e.message === 'token' ? 'repo refused the token' : 'could not reach the repo'); });
    var rr; window.addEventListener('resize', function () { clearTimeout(rr); rr = setTimeout(drawRecord, 150); });

    // sleeve card
    var maxR = 0.01; SL.assets.forEach(function (a) { maxR = Math.max(maxR, Math.abs(a.r6 || 0)); });
    var since = SL.history.length ? SL.history[0].d : null;
    $('sleeve-sub').textContent = 'Holds the best 6-month return of the six · ' + SL.held + (since ? ' since ' + fmtDate(since) : '');
    $('assets').innerHTML = SL.assets.slice().sort(function (a, b) { return (b.r6 || -9) - (a.r6 || -9); }).map(function (a) {
      var w = Math.abs(a.r6 || 0) / maxR * 50, neg = (a.r6 || 0) < 0;
      return '<li class="' + (a.t === SL.held ? 'pick' : '') + '"><span class="atk">' + esc(a.t) + '</span>' +
        '<span title="' + esc(a.n) + '"><span class="small">' + esc(a.n) + '</span><span class="abar"><i style="--c:' + (neg ? 'var(--neg)' : 'var(--pos)') + ';' + (neg ? 'right:50%;left:auto;' : '') + 'width:' + w + '%"></i></span></span>' +
        '<span class="num ' + tone(a.r6) + '">' + pct(a.r6) + '</span></li>';
    }).join('');
    var ss = SL.stats;
    $('sleeve-note').innerHTML = (D.signalDay && SL.held !== SL.prevHeld ? '<b>New pick: switch ' + esc(SL.prevHeld) + ' → ' + esc(SL.held) + ' on Monday.</b> '
        : !D.signalDay && SL.preview !== SL.held ? '<b>Preview: if Friday’s signal were today, switch ' + esc(SL.held) + ' → ' + esc(SL.preview) + '.</b> ' : '') +
      'Sleeve alone since ' + SINCE + ': ' + pct(ss.annual, 0) + ' a year, worst drop ' + pct(ss.maxDD, 0) + '. 6-month returns, dividends included.';
  })();

  // date range for the track record (defaults to everything since the start)
  var ALL0 = D.curves.strategy[0][0], ALL1 = D.curves.strategy[D.curves.strategy.length - 1][0];
  var R = { a: ALL0, b: ALL1 };
  function inR(c) { return c.filter(function (p) { return p[0] >= R.a && p[0] <= R.b; }); }
  // after-tax view, measured from the start of the selected range: what you would keep if you cashed out
  // that day. Strategies: 37% on each calendar year's net gain (losses carried forward), paid the next
  // April 15, and 37% on this year's unpaid gain. SPY / QQQ: bought at the range start and held;
  // 20% on dividends as paid, 20% on the gain if held over a year (37% if not).
  var TAX = false, YIELD = { SPY: 0.016, QQQ: 0.007 };
  function taxed(c, key) {
    if (c.length < 2) return c;
    var out = [[c[0][0], c[0][1]]];
    if (YIELD[key] != null) {
      var basis = c[0][1], t0 = Date.parse(c[0][0]);
      for (var i = 1; i < c.length; i++) {
        var yrs = (Date.parse(c[i][0]) - t0) / 31557600000;
        var v = c[i][1] * Math.pow(1 - 0.20 * YIELD[key], yrs), rate = yrs > 1 ? 0.20 : 0.37;
        out.push([c[i][0], v - rate * Math.max(0, v - basis)]);
      }
      return out;
    }
    var A = c[0][1], G = 0, carry = 0, owed = 0, pay = null, yr = c[0][0].slice(0, 4);
    for (var j = 1; j < c.length; j++) {
      var d = c[j][0], y = d.slice(0, 4);
      if (y !== yr) {
        var net = G - carry;
        if (net > 0) { owed += 0.37 * net; carry = 0; } else carry = -net;
        G = 0; yr = y; pay = y + '-04-15';
      }
      if (owed > 0 && pay && d >= pay) { A -= owed; owed = 0; pay = null; }
      var g = A * (c[j][1] / c[j - 1][1] - 1);
      A += g; G += g;
      out.push([d, A - owed - 0.37 * Math.max(0, G - carry)]);
    }
    return out;
  }
  function view(key) { var c = inR(D.curves[key] || []); return TAX ? taxed(c, key) : c; }
  function rstat(key) {
    var c = view(key);
    if (c.length < 2) return null;
    var pk = c[0][1], dd = 0; c.forEach(function (p) { pk = Math.max(pk, p[1]); dd = Math.min(dd, p[1] / pk - 1); });
    var tot = c[c.length - 1][1] / c[0][1] - 1, yrs = (Date.parse(c[c.length - 1][0]) - Date.parse(c[0][0])) / 31557600000;
    return { tot: tot, ann: yrs >= 0.95 ? Math.pow(1 + tot, 1 / yrs) - 1 : null, dd: dd };
  }
  function tile(label, value, sub, cls) { return '<div class="stat"><span class="stat-label">' + label + '</span><span class="stat-value ' + (cls || '') + '">' + value + '</span><span class="stat-sub">' + sub + '</span></div>'; }
  function drawStats() {
    var t5 = rstat('strategy'), au = rstat('plan'), st = rstat('steps'), sp = rstat('SPY'), qq = rstat('QQQ'), bo = rstat('boost');
    if (!t5) { $('stats').innerHTML = tile('Range', '–', 'pick at least two trading days', ''); return; }
    function yr(x) { return x && x.ann != null ? pct(x.ann, 0) + ' a year' : 'under a year'; }
    $('stats').innerHTML =
      tile('Top 5', pct(t5.tot, 0), yr(t5), tone(t5.tot)) +
      tile('Boost / Auto', (bo ? pct(bo.tot, 0) : '–') + ' / ' + (au ? pct(au.tot, 0) : '–'), (bo ? yr(bo) : '') + ' · worst ' + (bo ? pct(bo.dd, 0) : '–') + ' / ' + (au ? pct(au.dd, 0) : '–'), tone(bo && bo.tot)) +
      tile('SPY / QQQ', pct(sp.tot, 0) + ' / ' + pct(qq.tot, 0), 'worst ' + pct(sp.dd, 0) + ' / ' + pct(qq.dd, 0)) +
      tile('Top 5 worst drop', pct(t5.dd, 0), R.a === ALL0 && R.b === ALL1 ? 'since ' + SINCE : 'in this range', 'neg');
    $('range-hint').textContent = '$100 in the rule vs buying and holding · ' + fmtDate(inR(D.curves.strategy)[0][0]) + ' – ' + fmtDate(R.b) +
      (TAX ? ' · after tax: rule 37% on each year’s gains (paid each April), SPY/QQQ held, 20% long-term · value if cashed out that day' : ' · before tax');
  }
  var rf = $('r-from'), rto = $('r-to'), ryf = $('ry-from'), ryt = $('ry-to');
  (function () {
    var o = '';
    for (var y = +ALL0.slice(0, 4); y <= +ALL1.slice(0, 4); y++) o += '<option value="' + y + '">' + y + '</option>';
    ryf.innerHTML = ryt.innerHTML = o;
    ryf.value = ALL0.slice(0, 4); ryt.value = ALL1.slice(0, 4);
  })();
  // a whole-year range: Jan 1 of the first year (the prior year's last close is the base) to Dec 31 of the last
  // a range based on the last close of December belongs to the next year
  function shownYear(d) { var y = +d.slice(0, 4); return String(d.slice(5) >= '12-24' && y < +ALL1.slice(0, 4) ? y + 1 : y); }
  function yearStart(y) { var prev = D.curves.strategy.filter(function (p) { return p[0] < y + '-01-01'; }); return prev.length ? prev[prev.length - 1][0] : ALL0; }
  ryf.onchange = function () { var a = +ryf.value, b = Math.max(a, +ryt.value); setRange(yearStart(a), b + '-12-31'); };
  ryt.onchange = function () { var b = +ryt.value, a = Math.min(+ryf.value, b); setRange(yearStart(a), b + '-12-31'); };
  rf.min = rto.min = ALL0; rf.max = rto.max = ALL1; rf.value = ALL0; rto.value = ALL1;
  function setRange(a, b) {
    R.a = a < ALL0 ? ALL0 : a; R.b = b > ALL1 ? ALL1 : b;
    if (R.a > R.b) { var t = R.a; R.a = R.b; R.b = t; }
    rf.value = R.a; rto.value = R.b;
    ryf.value = shownYear(R.a); ryt.value = R.b.slice(0, 4);
    document.querySelectorAll('#r-pre button').forEach(function (x) { x.setAttribute('aria-pressed', 'false'); });
    drawStats(); drawGrowth();
  }
  rf.onchange = function () { if (rf.value) setRange(rf.value, R.b); };
  rto.onchange = function () { if (rto.value) setRange(R.a, rto.value); };
  $('r-tax').onclick = function (e) {
    var bt = e.target.closest('button'); if (!bt) return;
    TAX = bt.getAttribute('data-t') === '1';
    document.querySelectorAll('#r-tax button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === bt)); });
    drawStats(); drawGrowth();
  };
  $('r-pre').onclick = function (e) {
    var bt = e.target.closest('button'); if (!bt) return;
    var k = bt.getAttribute('data-r'), end = new Date(ALL1 + 'T12:00:00Z'), a = ALL0;
    if (k === 'ytd') a = yearStart(+ALL1.slice(0, 4));
    else if (k !== 'all') { var d0 = new Date(end); d0.setUTCFullYear(d0.getUTCFullYear() - parseInt(k, 10)); a = d0.toISOString().slice(0, 10); }
    setRange(a, ALL1);
    bt.setAttribute('aria-pressed', 'true');
  };

  // monthly plans
  (function () {
    var M = D.monthly;
    if (!M) return;
    var md = { month: 'short', day: 'numeric' };
    function card(b, title, color, note) {
      var sp = (b.split || '100/0').split('/');
      var rows = b.holdings.map(function (h) {
        return '<tr><td><span class="sw" style="--c:' + color + '"></span><b>' + esc(h.t) + '</b> <span class="muted"><span class="nm2">' + esc(h.n) + '</span></span></td>' +
          '<td class="r muted">' + (h.since ? fmtDate(h.since, md) : '') + '</td><td class="r ' + tone(h.sinceRet || 0) + '">' + (h.sinceRet == null ? '–' : pct(h.sinceRet, 1)) + '</td></tr>';
      }).join('');
      var tr = (b.trades || []).slice(0, 6).map(function (x) {
        return (x.side === 'buy' ? 'bought ' : 'sold ') + '<b>' + esc(x.t) + '</b> ' + fmtDate(x.d, md);
      }).join(' · ');
      return '<div class="card"><p class="chart-title">' + title + '</p>' +
        '<p class="chart-sub">Since ' + SINCE + ': <b class="pos">' + pct(b.stats.annual, 0) + '</b> a year, worst drop <b class="neg">' + pct(b.stats.maxDD, 0) + '</b> · this month ' + sp[0] + '% stocks' +
        (b.sleeve ? ', ' + sp[1] + '% in ' + esc(b.sleeve) : '') + '</p>' +
        '<table class="alloc"><tbody>' + (rows || '<tr><td class="muted">No holdings yet</td></tr>') + '</tbody></table>' +
        '<p class="mlist">Held since · gain since bought' + (tr ? '<br>Recent: ' + tr : '') + '</p>' +
        (note ? '<p class="note">' + note + '</p>' : '') + '</div>';
    }
    var next = 'Next decision at the ' + fmtDate(M.nextDecision, md) + ' close, traded ' + fmtDate(M.nextTrade, md) + '.';
    var pv = (M.preview || []).length ? ' If the month ended today it would hold ' + M.preview.map(esc).join(', ') + '.' : '';
    $('monthly').innerHTML = card(M.boost, 'Monthly boost', 'var(--s-monb)', next) + card(M.auto, 'Monthly auto', 'var(--s-mon)', next + pv);
    $('monthly-wrap').hidden = false;
  })();

  // growth chart
  var SER = [['strategy', 'Top 5 strongest', 'var(--s-strat)', 'main'], ['QQQ', 'QQQ', 'var(--s-qqq)', ''], ['SPY', 'SPY', 'var(--s-spy)', '']];
  if (D.curves.plan && D.plan) SER.splice(1, 0, ['plan', 'Plan (auto mix)', 'var(--s-plan)', 'main']);
  if (D.curves.boost && D.plan) SER.splice(1, 0, ['boost', 'Plan (boost)', 'var(--s-boost)', 'main']);
  if (D.curves.monthlyBoost) SER.splice(SER.length - 2, 0, ['monthlyBoost', 'Monthly boost', 'var(--s-monb)', 'main']);
  if (D.curves.monthly) SER.splice(SER.length - 2, 0, ['monthly', 'Monthly auto', 'var(--s-mon)', 'main']);
  var HIDE = {}; try { HIDE = JSON.parse(localStorage.getItem('nibii-hide-lines') || '{}') || {}; } catch (e) {}
  function drawLegend() {
    $('legend').innerHTML = SER.map(function (s) { return '<button type="button" class="lg" data-k="' + s[0] + '" aria-pressed="' + String(!HIDE[s[0]]) + '"><i class="key" style="--c:' + s[2] + '"></i>' + s[1] + '</button>'; }).join('') +
      '<span class="muted lg-hint">tap a line to hide / show it</span>';
  }
  var scale = 'log';
  try { scale = localStorage.getItem('nibii-mom-scale') || 'log'; } catch (e) {}
  drawLegend();
  $('legend').onclick = function (e) {
    var b = e.target.closest('.lg'); if (!b) return;
    var k = b.getAttribute('data-k'), shownN = SER.filter(function (s) { return !HIDE[s[0]]; }).length;
    if (!HIDE[k] && shownN <= 1) return;   // keep at least one line
    if (HIDE[k]) delete HIDE[k]; else HIDE[k] = 1;
    try { localStorage.setItem('nibii-hide-lines', JSON.stringify(HIDE)); } catch (x) {}
    drawLegend(); drawGrowth();
  };
  function day(s) { return Date.parse(s + 'T12:00:00Z'); }
  function money(v) { return '$' + (v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(0)); }
  function drawGrowth() {
    document.querySelectorAll('#scale-seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === scale)); });
    var box = $('growth'); box.innerHTML = '';
    var series = SER.filter(function (s) { return !HIDE[s[0]]; }).map(function (s) { var c = view(s[0]), b0 = c.length ? c[0][1] : 1; return { name: s[1], c: s[2], cls: s[3], pts: c.map(function (p) { return [day(p[0]), p[1] / b0 * 100]; }) }; });
    if (!series[0].pts.length) return;
    var W = Math.max(320, box.clientWidth), H = Math.round(Math.min(380, Math.max(240, W * 0.5))), m = { l: 56, r: 64, t: 10, b: 26 };
    var xs = [], ys = [];
    series.forEach(function (s) { s.pts.forEach(function (p) { xs.push(p[0]); ys.push(p[1]); }); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    var log = scale === 'log', f = log ? Math.log : function (v) { return v; };
    var ticks = [];
    if (log) { [50, 100, 200, 500, 1000, 2000, 5000, 10000].forEach(function (v) { if (v >= lo * 0.9 && v <= hi * 1.1) ticks.push(v); }); }
    if (!log || ticks.length < 3) { ticks = []; var st = Math.pow(10, Math.floor(Math.log10((hi - lo) / 4))); st = (hi - lo) / st > 20 ? st * 5 : (hi - lo) / st > 8 ? st * 2 : st; for (var v = Math.ceil(lo / st) * st; v <= hi; v += st) ticks.push(v); }
    var y0 = f(Math.min(lo, ticks[0] || lo)), y1 = f(Math.max(hi, ticks[ticks.length - 1] || hi));
    function X(t) { return m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r); }
    function Y(v) { return m.t + (1 - (f(v) - y0) / (y1 - y0 || 1)) * (H - m.t - m.b); }
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Growth of $100' }), g = el('g', { class: 'grid axis' });
    ticks.forEach(function (v) { g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) })); var t = el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }); t.textContent = money(v); g.appendChild(t); });
    if (x1 - x0 > 400 * 864e5) { for (var yr = new Date(x0).getUTCFullYear() + 1; Date.UTC(yr, 0, 1) <= x1; yr++) { var tx = el('text', { x: X(Date.UTC(yr, 0, 1)), y: H - 6, 'text-anchor': 'middle' }); tx.textContent = yr; g.appendChild(tx); } }
    else { [x0, (x0 + x1) / 2, x1].forEach(function (t, j) { var tx = el('text', { x: X(t), y: H - 6, 'text-anchor': j === 0 ? 'start' : j === 2 ? 'end' : 'middle' }); tx.textContent = new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' }); g.appendChild(tx); }); }
    svg.appendChild(g);
    svg.appendChild(el('line', { class: 'base', x1: m.l, x2: W - m.r, y1: Y(100), y2: Y(100) }));
    var ends = [];
    series.slice().reverse().forEach(function (s) {
      svg.appendChild(el('path', { class: 'line ' + s.cls, d: s.pts.map(function (p, i) { return (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join(''), style: 'stroke:' + s.c }));
      var last = s.pts[s.pts.length - 1]; ends.push({ y: Y(last[1]), v: last[1], c: s.c });
    });
    ends.sort(function (a, b) { return a.y - b.y; });
    for (var i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
    ends.forEach(function (e) { svg.appendChild(el('rect', { x: W - m.r + 4, y: e.y - 1.5, width: 8, height: 3, rx: 1, style: 'fill:' + e.c })); var t = el('text', { class: 'endlabel', x: W - m.r + 16, y: e.y + 4 }); t.textContent = money(e.v); svg.appendChild(t); });
    var cross = el('line', { class: 'cross', y1: m.t, y2: H - m.b, visibility: 'hidden' }); svg.appendChild(cross);
    var dots = series.map(function (s) { var c = el('circle', { class: 'dotm', r: 4, style: 'fill:' + s.c, visibility: 'hidden' }); svg.appendChild(c); return c; });
    var tip = document.createElement('div'); tip.className = 'tip'; tip.hidden = true;
    box.appendChild(svg); box.appendChild(tip);
    var allX = series[0].pts.map(function (p) { return p[0]; });
    function at(s, t) { var lo2 = 0, hi2 = s.pts.length - 1; if (t < s.pts[0][0]) return null; while (lo2 < hi2) { var mid = (lo2 + hi2 + 1) >> 1; if (s.pts[mid][0] <= t) lo2 = mid; else hi2 = mid - 1; } return s.pts[lo2]; }
    svg.addEventListener('pointermove', function (e) {
      var rect = svg.getBoundingClientRect(), px = (e.clientX - rect.left) / rect.width * W, t = x0 + (px - m.l) / (W - m.l - m.r) * (x1 - x0);
      var k = 0; while (k < allX.length - 1 && allX[k + 1] <= t) k++; var tx = allX[k], sx = X(tx);
      cross.setAttribute('x1', sx); cross.setAttribute('x2', sx); cross.setAttribute('visibility', 'visible');
      tip.textContent = ''; var hd = document.createElement('div'); hd.textContent = new Date(tx).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); hd.style.marginBottom = '4px'; tip.appendChild(hd);
      series.forEach(function (s, j) {
        var p = at(s, tx), row = document.createElement('div'); row.className = 'row';
        var key = document.createElement('i'); key.style.setProperty('--c', s.c); row.appendChild(key);
        var b = document.createElement('b'); b.textContent = p ? money(p[1]) : '–'; row.appendChild(b);
        row.appendChild(document.createTextNode(' ' + s.name)); tip.appendChild(row);
        if (p) { dots[j].setAttribute('cx', X(p[0])); dots[j].setAttribute('cy', Y(p[1])); dots[j].setAttribute('visibility', 'visible'); }
      });
      tip.hidden = false; var bx = sx / W * rect.width, left = bx + 12; if (left + tip.offsetWidth > rect.width) left = bx - tip.offsetWidth - 12;
      tip.style.left = Math.max(0, left) + 'px'; tip.style.top = '8px';
    });
    svg.addEventListener('pointerleave', function () { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); dots.forEach(function (d) { d.setAttribute('visibility', 'hidden'); }); });
  }
  $('scale-seg').onclick = function (e) { var b = e.target.closest('button'); if (!b) return; scale = b.getAttribute('data-v'); try { localStorage.setItem('nibii-mom-scale', scale); } catch (x) {} drawGrowth(); };
  drawStats(); drawGrowth();
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(drawGrowth, 150); });

  (function () {
    var yS = D.years && D.years.strategy, yQ = D.years && D.years.QQQ;
    if (!yS || !yQ) return;
    var lag = Object.keys(yS).sort().filter(function (y) { return yQ[y] != null && yS[y] < yQ[y]; });
    var cur = new Date().getFullYear().toString();
    lag = lag.filter(function (y) { return y !== cur; });
    var txt = lag.length ? (lag.length > 1 ? lag.slice(0, -1).join(', ') + ' and ' + lag[lag.length - 1] : lag[0]) : 'no full year';
    var t = document.getElementById('trail-yrs'); if (t) t.textContent = txt;
  })();
  // years
  var ys = Object.keys(D.years.strategy).sort(), maxAbs = 0;
  var YK = (D.years.monthly ? ['boost', 'plan', 'monthlyBoost', 'monthly', 'SPY', 'QQQ'] : ['strategy', 'boost', 'plan', 'SPY', 'QQQ'])
    .filter(function (k) { return D.years[k]; });
  var YC = { strategy: 'var(--s-strat)', boost: 'var(--s-boost)', plan: 'var(--s-plan)', monthlyBoost: 'var(--s-monb)', monthly: 'var(--s-mon)', SPY: 'var(--s-spy)', QQQ: 'var(--s-qqq)' };
  var YH = { strategy: 'Top 5', boost: 'Boost', plan: 'Auto', monthlyBoost: 'M boost', monthly: 'M auto', SPY: 'SPY', QQQ: 'QQQ' };
  ys.forEach(function (y) { YK.forEach(function (k) { maxAbs = Math.max(maxAbs, Math.abs(D.years[k][y] || 0)); }); });
  var barMax = YK.length > 5 ? 3 : YK.length > 4 ? 18 : YK.length > 3 ? 26 : 70;
  function ybar(v, c) { var w = Math.max(2, Math.abs(v) / maxAbs * barMax); return '<span class="ybar' + (v < 0 ? ' neg' : '') + '"><i style="--c:' + c + ';width:' + w + 'px"></i><span class="num ' + tone(v) + '">' + pct(v, 0) + '</span></span>'; }
  $('years').className = 'years' + (YK.length > 5 ? ' tight' : '');
  $('years').innerHTML = '<thead><tr><th class="l">Year</th>' + YK.map(function (k) { return '<th class="l y-' + k + '">' + YH[k] + '</th>'; }).join('') + '</tr></thead><tbody>' +
    ys.map(function (y) { return '<tr><td class="l">' + y + '</td>' + YK.map(function (k) { return '<td class="l y-' + k + '">' + ybar(D.years[k][y] || 0, YC[k]) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody>';
  $('ytd-note').textContent = ys[ys.length - 1] + ' is year to date (' + fmtDate(D.asOf, { month: 'short', day: 'numeric' }) + ')' + (D.years.monthly ? ' · M = monthly' : window.innerWidth <= 520 ? ' · Top 5 column on wider screens' : '');

  // on deck
  $('deck').innerHTML = D.table.filter(function (r) { return r.rank > 5 && r.rank <= 20; }).map(function (r) {
    var tap = r.chart ? ' data-t="' + esc(r.t) + '" tabindex="0" role="button" aria-expanded="false" aria-controls="swpanel2" aria-label="' + esc(r.t) + ': show swing chart"' : '';
    return '<div class="dk' + (held[r.t] ? ' held' : '') + '"' + tap + '><span class="rank">#' + r.rank + '</span><span class="tk2">' + esc(r.t) + (held[r.t] ? ' <span class="tag ndx" title="currently held">HELD</span>' : '') + (r.ndx ? ' <span class="tag ndx">NDX</span>' : '') +
      '</span><span class="val ' + tone(r.score) + '">' + pct(r.score, 0) + '</span><span class="nm2">' + esc(r.n) + '</span><span class="chg">' + delta(r.d1w) + '</span></div>';
  }).join('');
  $('deck').addEventListener('click', function (e) { var c = e.target.closest('.dk[data-t]'); if (c) openSwing(c.getAttribute('data-t'), 'swpanel2'); });
  $('deck').addEventListener('keydown', function (e) { var c = e.target.closest('.dk[data-t]'); if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openSwing(c.getAttribute('data-t'), 'swpanel2'); } });

  // trades
  $('trades').innerHTML = D.trades.slice(0, 12).map(function (x) {
    return '<li><span class="when">' + fmtDate(x.d, { month: 'short', day: 'numeric', year: '2-digit' }) + '</span><span class="tag ' + x.side + '">' + x.side + '</span><span><b>' + esc(x.t) + '</b> <span class="muted" style="font-size:0.76rem">' + esc(x.n) + '</span></span><span class="num muted">$' + (x.px != null ? x.px.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '–') + '</span></li>';
  }).join('');

  // table
  var T = { q: '', sec: '', sort: 'rank', dir: 1, all: false };
  var secs = {}; D.table.forEach(function (r) { if (r.sec) secs[r.sec] = 1; });
  Object.keys(secs).sort().forEach(function (s) { var o = document.createElement('option'); o.value = s; o.textContent = s; $('sector').appendChild(o); });
  function renderTable() {
    var q = T.q.trim().toLowerCase();
    var list = D.table.filter(function (r) { return (!T.sec || r.sec === T.sec) && (!q || r.t.toLowerCase().indexOf(q) >= 0 || r.n.toLowerCase().indexOf(q) >= 0); });
    list.sort(function (a, b) { var x = a[T.sort], y = b[T.sort]; if (x == null) return 1; if (y == null) return -1; return (x > y ? 1 : x < y ? -1 : 0) * T.dir; });
    var shown = T.all || q || T.sec ? list : list.slice(0, 30);
    $('count').textContent = list.length + ' of ' + D.table.length;
    $('more').hidden = shown.length === list.length;
    $('rows').innerHTML = shown.map(function (r) {
      return '<tr' + (held[r.t] ? ' class="held"' : '') + '><td class="num">' + r.rank + '</td><td class="l"><b>' + esc(r.t) + '</b>' + (r.ndx ? ' <span class="tag ndx">NDX</span>' : '') + '<span class="sub">' + esc(r.n) + '</span></td>' +
        '<td class="l hide-sm">' + esc(r.sec) + '</td><td class="num ' + tone(r.score) + '">' + pct(r.score, 0) + '</td><td class="num">' + pct(r.vsSpy, 0) + '</td>' +
        '<td class="num hide-sm ' + tone(r.r1m) + '">' + pct(r.r1m) + '</td><td class="num hide-sm ' + tone(r.r12m) + '">' + pct(r.r12m, 0) + '</td>' +
        '<td class="num">' + delta(r.d1w) + '</td><td class="num hide-sm">' + delta(r.d4w) + '</td><td class="num hide-sm">' + pct(r.offHigh) + '</td><td>' + trend(r.trend) + '</td></tr>';
    }).join('') || '<tr><td colspan="11" class="l muted">No stocks match.</td></tr>';
    document.querySelectorAll('th button[data-sort]').forEach(function (b) { if (b.getAttribute('data-sort') === T.sort) b.setAttribute('data-dir', T.dir > 0 ? '↑' : '↓'); else b.removeAttribute('data-dir'); });
  }
  $('q').oninput = function (e) { T.q = e.target.value; renderTable(); };
  $('sector').onchange = function (e) { T.sec = e.target.value; renderTable(); };
  $('more').onclick = function () { T.all = true; renderTable(); };
  document.querySelector('thead').onclick = function (e) {
    var b = e.target.closest('button[data-sort]'); if (!b) return; var k = b.getAttribute('data-sort');
    T.dir = T.sort === k ? -T.dir : (k === 'rank' || k === 't' || k === 'sec' ? 1 : -1); T.sort = k; renderTable();
  };
  renderTable();
})();
(function () {
  var root = document.documentElement, sun = document.getElementById('icon-sun'), moon = document.getElementById('icon-moon');
  function apply(t) { if (t) root.setAttribute('data-mtl-theme', t); else root.removeAttribute('data-mtl-theme'); var dark = t !== 'light'; sun.hidden = dark; moon.hidden = !dark; }
  var saved = null; try { saved = localStorage.getItem('mtl-theme'); } catch (e) {}
  apply(saved);
  document.getElementById('theme-toggle').addEventListener('click', function () {
    var next = root.getAttribute('data-mtl-theme') === 'light' ? 'dark' : 'light'; apply(next); try { localStorage.setItem('mtl-theme', next); } catch (e) {}
  });
})();
</script>
'''


def render(scan):
    # Escape "</" so a company name can never close the <script> block early.
    return PAGE.replace('__DATA__', json.dumps(scan, separators=(',', ':')).replace('</', '<\\/'))


def main():
    if not os.path.exists(DATA_PATH):
        sys.exit(f"{DATA_PATH} not found - run: python scripts/momentum_scan.py")
    with open(DATA_PATH) as f:
        page = render(json.load(f))
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        f.write(page)
    print(f"wrote {OUT_PATH}")


if __name__ == '__main__':
    main()

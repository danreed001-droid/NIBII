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
import html
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
<meta name="robots" content="noindex">
<title>Top 5 Strongest</title>
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#17181a">
<link rel="icon" type="image/png" href="img/app-192.png">
<link rel="apple-touch-icon" href="img/apple-touch-180.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Top 5">
<script>
  // installable app: the service worker (docs/sw.js) opens the last page seen when there is no connection
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('sw.js').catch(function () {}); });
  }
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0d0d0d; --surface: #17181a; --surface-2: #1f2023; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #8b8a85; --hairline: #2c2c2a; --accent: #3987e5; --gold: #d9b46a;
  --masthead-bg: #17181a; --masthead-ink: #ffffff; --masthead-ink-2: #a9adba;
  --pos: #3fbf5f; --neg: #e5605a; --grid: #2c2c2a;
  --s-strat: #3987e5; --s-spy: #c98500; --s-qqq: #d55181; --s-spmo: #9aa86a; --s-calls: #e0a43a; --s-ccalls: #d98ad0; --s-plan: #3fb8a0; --s-boost: #a989f5; --s-b100: #4fd1e8; --s-rot: #f2d03b; --s-cush: #e6a14a; --s-mon: #f08c4a; --s-monb: #8fbf3a;
  color-scheme: dark;
}
:root[data-mtl-theme="light"] {
  --bg: #f4f3ef; --surface: #fdfdfc; --surface-2: #f0efea; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  --pos: #0a8f0a; --neg: #c43232; --grid: #e1e0d9;
  --s-strat: #2a78d6; --s-spy: #eda100; --s-qqq: #e87ba4; --s-spmo: #6b7a33; --s-calls: #b7791f; --s-ccalls: #a1459a; --s-plan: #13866f; --s-boost: #6d44d4; --s-b100: #0a8aa3; --s-rot: #8a6d00; --s-cush: #b4600b; --s-mon: #c4561a; --s-monb: #5f8a12;
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
.nav { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px 12px; font-size: 0.8rem; }
.nav a { color: var(--masthead-ink-2); text-decoration: none; }
.nav a:hover { color: var(--gold); }
.nav .bt { color: var(--gold); font-weight: 600; }
.nav-r { display: flex; align-items: center; gap: 14px; }
.nav .add { border: 1px solid var(--gold); border-radius: 999px; padding: 1px 9px; }
.eyebrow { font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--gold); font-weight: 600; margin: 16px 0 6px; }
.top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
h1 { font-size: 2.4rem; font-weight: 600; }
.subtitle { color: var(--masthead-ink-2); margin: 8px 0 0; font-size: 0.92rem; max-width: 760px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.meta span { border: 1px solid rgba(255,255,255,0.14); border-radius: 999px; padding: 4px 11px; font-size: 0.76rem; color: var(--masthead-ink-2); }
.meta b { color: var(--masthead-ink); font-weight: 600; }
.evf .evf-q { width: 100%; }
.evf input, .evf select { font: inherit; font-size: 16px; color: var(--ink); background: var(--surface-2); border: 1px solid var(--hairline);
  border-radius: 8px; padding: 7px 10px; min-width: 0; }
.evf select { padding: 7px 4px; }
.evf .evf-mv { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 8px; color: var(--muted); font-size: 0.86rem; }
.evf .evf-mv input { width: 3em; padding: 7px 5px; }
.evf .evf-n { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
@media (max-width: 520px) { .evf { padding: 12px; } .evf .evf-mv { gap: 5px; } }
.evf button { font: inherit; font-size: 0.86rem; color: var(--muted); background: none; border: 0; padding: 7px 4px; cursor: pointer;
  text-decoration: underline; text-underline-offset: 2px; }
.evf .evf-count { color: var(--muted); font-size: 0.82rem; margin: 8px 0 0; }
.evf table { width: 100%; border-collapse: collapse; font-size: 0.84rem; margin-top: 6px; }
.evf th { text-align: left; color: var(--muted); font-weight: 600; font-size: 0.72rem; border-bottom: 1px solid var(--hairline); padding: 4px;
  text-transform: none; letter-spacing: 0; background: none; white-space: nowrap; }
.evf td { border-bottom: 1px solid var(--hairline); padding: 6px 4px; vertical-align: top; text-align: left; white-space: normal; }
.evf td.d { white-space: nowrap; color: var(--muted); width: 3.6em; } .evf td.d small { display: block; font-size: 0.72rem; }
.evf .n { text-align: right; white-space: nowrap; }
.evf .tag { font-size: 0.68rem; background: var(--surface-2); color: var(--muted); border-radius: 6px; padding: 1px 6px; white-space: nowrap; }
.evf .clamp { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.evf td a { color: inherit; text-decoration-color: var(--muted); text-underline-offset: 2px; }
.evf .evf-more { font-size: 0.82rem; margin: 8px 0 0; }
.issues-card ul { margin: 6px 0 0; padding-left: 0; list-style: none; }
.issues-card li { padding: 7px 0; border-top: 1px solid var(--hairline); font-size: 0.84rem; line-height: 1.45; }
.issues-card li:first-child { border-top: 0; }
.issues-card .when { color: var(--muted); font-size: 0.74rem; margin-right: 6px; white-space: nowrap; }
.issues-card .ok { color: var(--pos); font-weight: 600; }
.issues-card .clamp { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.issues-card .more { font-size: 0.82rem; margin: 6px 0 0; }
.meta b.pos { color: var(--pos); } .meta b.neg { color: var(--neg); } .meta b.warn { color: var(--gold); }
.meta .market-signs { flex-basis: 100%; font-size: 0.8rem; line-height: 1.4; color: var(--muted); }
.meta .data-issues { flex-basis: 100%; border: 1px solid var(--neg); border-radius: 8px; padding: 8px 11px; font-size: 0.82rem; line-height: 1.4; color: var(--masthead-ink); background: rgba(220, 60, 60, 0.14); }
.meta .dot { display: inline-block; width: 7px; height: 7px; border-radius: 99px; background: #5fb87a; margin-right: 6px; vertical-align: 1px; }
.meta .dot.aging { background: #d9b46a; } .meta .dot.stale { background: #e5705f; }
.theme-toggle { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.18); background: transparent; color: var(--masthead-ink-2); cursor: pointer; }
.theme-toggle:hover { color: var(--gold); border-color: var(--gold); }
.theme-toggle svg { width: 15px; height: 15px; } .theme-toggle svg[hidden] { display: none; }

.section-label { font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); font-weight: 600;
  margin: 34px 0 12px; display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.section-label .hint { text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 0.8rem; }
.section-label .hint a { color: var(--accent); text-decoration: none; }

/* rebalance banner */
.banner { margin-top: 18px; display: flex; gap: 10px 16px; align-items: center; flex-wrap: wrap; background: var(--surface);
  border: 1px solid var(--hairline); border-left: 4px solid var(--gold); border-radius: 12px; padding: 12px 16px; font-size: 0.88rem; }
.banner b { font-weight: 600; }
.banner .why { flex-basis: 100%; margin: 2px 0 0; padding-left: 18px; font-size: 0.85rem; color: var(--ink-2); }
.banner .why li { margin-top: 3px; }
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
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1px; background: var(--hairline); border: 1px solid var(--hairline);
  border-radius: 12px; overflow: hidden; }
@media (max-width: 720px) { .stats { grid-template-columns: repeat(2, 1fr); } }
.stat { background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 3px; }
.stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.stat-value { font-family: ui-monospace, monospace; font-size: 1.5rem; font-weight: 600; line-height: 1.2; }
.stat-sub { font-size: 0.75rem; color: var(--ink-2); }
.stat.default { box-shadow: inset 4px 0 0 var(--s-rot); }
.stat.default .stat-label { color: var(--ink); font-weight: 600; }
.badge-def { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 999px; background: var(--s-rot); color: var(--surface); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; vertical-align: 1px; }

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
.legend .lg.default { font-weight: 600; border-color: var(--s-rot); }
.legend .seg { margin-right: 4px; }
.years th.def, .years td.def { background: color-mix(in srgb, var(--s-rot) 12%, transparent); }
.years th.def { color: var(--ink); }
.years th .sub { display: block; font-weight: 400; font-size: 0.66rem; color: var(--muted); }
.key { width: 16px; height: 3px; border-radius: 2px; background: var(--c); }
.seg { display: inline-flex; border: 1px solid var(--hairline); border-radius: 999px; padding: 2px; background: var(--surface-2); }
.seg button { font: inherit; font-size: 0.76rem; border: 0; background: transparent; color: var(--ink-2); padding: 3px 10px; border-radius: 999px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg); font-weight: 600; }
.wc-btn { font: inherit; font-size: 13px; padding: 4px 10px; margin: 2px 2px; border-radius: 6px; border: 1px solid var(--hairline); background: var(--surface); color: inherit; cursor: pointer; }
.wc-btn[aria-pressed="true"] { background: var(--ink); color: var(--bg); border-color: var(--ink); font-weight: 600; }
.chart { position: relative; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.grid line { stroke: var(--grid); stroke-width: 1; }
.axis text { fill: var(--muted); font-size: 11px; font-family: ui-monospace, monospace; }
.base { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
.line { fill: none; stroke-linejoin: round; stroke-linecap: round; stroke-width: 1.8; }
.line.main { stroke-width: 2.6; }
.line.default { stroke-width: 3.6; }
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
/* 3D price-volume chart */
.pv { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 14px 14px 12px; margin-bottom: 18px; }
.pv-bar { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; margin-bottom: 8px; }
.pv-group { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.pv-group > span { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-right: 2px; }
.pv button { font: inherit; font-size: 0.78rem; border: 1px solid var(--hairline); background: transparent; color: var(--ink-2);
  border-radius: 999px; padding: 4px 10px; cursor: pointer; }
.pv button:hover { border-color: var(--muted); color: var(--ink); }
.pv button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--surface); }
.pv button.tk { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 0.74rem; }
.pv button.tk.held { border-color: color-mix(in srgb, var(--gold) 70%, var(--hairline)); }
.pv button.tk sup { color: var(--muted); font-size: 0.6rem; margin-left: 2px; }
.pv button.tk[aria-pressed="true"] sup { color: inherit; opacity: 0.7; }
.pv-stage { position: relative; border-radius: 10px; overflow: hidden; background: var(--surface-2); }
.pv-plot { width: 100%; height: min(68vh, 560px); min-height: 360px; }
.pv-wait { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: 0.85rem; pointer-events: none; }
.pv-hint { position: absolute; left: 12px; bottom: 8px; font-size: 0.72rem; color: var(--muted); pointer-events: none; }
.pv-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px 12px; margin-top: 10px; }
.pv-stat { border-top: 1px solid var(--hairline); padding-top: 6px; min-width: 0; }
.pv-stat .k { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
.pv-stat .v { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; font-size: 0.98rem; margin-top: 2px; }
.pv-stat .s { font-size: 0.74rem; color: var(--ink-2); }
.pv .pos { color: var(--pos); } .pv .neg { color: var(--neg); }
.pv-note { font-size: 0.8rem; color: var(--muted); margin: 10px 2px 0; line-height: 1.5; }
.pv-note i { display: inline-block; width: 12px; height: 3px; border-radius: 2px; vertical-align: middle; margin: 0 3px 0 1px; }

/* weekly rank heatmap */
.heatbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin-bottom: 8px; font-size: 0.8rem; color: var(--muted); }
.heatbar .hkey { display: inline-flex; align-items: center; gap: 6px; }
.heatbar .hkey i { display: inline-block; width: 64px; height: 10px; border-radius: 3px; background: linear-gradient(90deg, var(--neg), var(--surface-2) 50%, var(--accent)); }
.heatbox { overflow-x: auto; border: 1px solid var(--hairline); border-radius: 12px; background: var(--surface); }
table.heat { border-collapse: separate; border-spacing: 2px; width: 100%; min-width: 340px; padding: 6px; }
table.heat th { font-size: 0.74rem; font-weight: 600; color: var(--ink-2); padding: 4px 2px; text-align: center; white-space: nowrap; }
table.heat th.wk, table.heat td.wk { text-align: left; color: var(--muted); font-weight: 500; font-size: 0.72rem; padding-right: 6px; position: sticky; left: 0; background: var(--surface); width: 52px; }
table.heat th.held { color: var(--gold); }
table.heat th.extra { color: var(--muted); font-style: italic; }
table.heat td.c { text-align: center; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; font-size: 0.74rem; padding: 4px 2px; border-radius: 4px; cursor: default; min-width: 26px; }
@media (max-width: 520px) { table.heat { border-spacing: 1px; padding: 4px; min-width: 680px; } table.heat th { font-size: 0.66rem; } table.heat td.c { font-size: 0.68rem; padding: 4px 0; } table.heat th.wk, table.heat td.wk { width: 48px; font-size: 0.66rem; padding-right: 3px; } table.heat tr.sum td { font-size: 0.64rem; } table.heat tr.sum td.wk { white-space: normal; line-height: 1.2; } table.heat th.ud, table.heat td.ud { width: 70px; padding-left: 4px; } }
table.heat td.c.px { font-size: 0.62rem; letter-spacing: -0.02em; }
table.heat td.c:focus-visible { outline: 2px solid var(--gold); outline-offset: 1px; }
table.heat tr.sum td { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; font-size: 0.74rem; text-align: center; color: var(--ink-2); padding-top: 6px; border-top: 1px solid var(--hairline); }
table.heat tr.sum td.wk { font-family: inherit; }
table.heat th.ud, table.heat td.ud { width: 104px; padding-left: 8px; }
.udrow { display: flex; align-items: center; gap: 6px; }
.udbar { flex: 1; display: flex; height: 12px; border-radius: 3px; overflow: hidden; background: var(--surface-2); }
.udbar span { display: block; height: 100%; }
.udbar .u { background: var(--accent); } .udbar .d { background: var(--neg); }
.udnum { font-size: 0.68rem; color: var(--ink-2); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; white-space: nowrap; width: 2.6em; text-align: right; }
.udtrend { margin-top: 8px; border: 1px solid var(--hairline); border-radius: 12px; background: var(--surface); padding: 8px 10px 4px; }
.udtrend svg { display: block; width: 100%; height: auto; }
.udtrend .t { font-size: 11px; fill: var(--muted); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.udtrend .cap { font-size: 0.74rem; color: var(--muted); display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: center; }
.udtrend .cap i { display: inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 5px; }
.heatnote { font-size: 0.8rem; color: var(--muted); margin: 8px 2px 0; min-height: 1.3em; }
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
#trk-card { margin-top: 28px; }
#trk-card .btn { text-decoration: none; display: inline-block; }
#y2-in { width: 100%; font: 0.9rem ui-monospace, monospace; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); color: var(--ink); padding: 8px 10px; margin: 4px 0 8px; box-sizing: border-box; }
#y2-chart svg, #pp-chart svg { width: 100%; height: auto; display: block; }
#y2-log { font-size: 0.82rem; color: var(--ink-2); margin-top: 6px; }
#sync-token { flex: 1 1 180px; min-width: 0; font: 0.84rem ui-monospace, monospace; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); color: var(--ink); padding: 6px 8px; }
.sync code { font-size: 0.74rem; }
.rec-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: 8px; margin: 8px 0 10px; }
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
@media (max-width: 520px) { .years .y-strategy { display: none; } .wk .hide-xs { display: none; } .rec-tiles { gap: 6px; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); } .rec-tile .v { font-size: 1rem; } }
footer { margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }
footer li { margin-bottom: 6px; }
</style>

<div class="masthead"><div class="masthead-inner">
  <div class="nav"><a href="index.html">← Market Tape Ledger</a><span class="nav-r"><a class="bt add" href="__ADD_URL__" target="_blank" rel="noopener" title="Add your own news to the market events page">＋ Add news</a><a class="bt" href="events.html">Events →</a><a class="bt" href="backtest.html">Backtests →</a></span></div>
  <p class="eyebrow">NIBII · Momentum</p>
  <div class="top"><h1>Top 5 Strongest</h1>
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dark/light theme">
      <svg id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>
      <svg id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"></path></svg>
    </button></div>
  <p class="subtitle">At each week’s last close (usually Friday), rank the S&amp;P 500 by 6-month performance (skipping the latest month), hold the
    5 strongest that beat SPY, and keep each while it stays in the top 10. Trade at the next session (usually Monday), 3:30–4:00 pm ET.</p>
  <div class="meta" id="meta"></div>
</div></div>

<div class="wrap">
  <div class="banner" id="banner"></div>

  <p class="section-label">Current holdings <span class="hint" id="hold-hint"></span></p>
  <div class="holdings" id="holdings"></div>
  <div class="card optcheck" id="optcheck" hidden></div>
  <div class="card swpanel" id="swpanel" hidden></div>

__EVENTS__
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

  <p class="section-label">You-2 <span class="hint">your stocks, the default plan’s timing · since Oct 14, 2026</span></p>
  <div class="plan">
    <div class="card" id="you2">
      <p class="chart-title">You-2: your stocks</p>
      <p class="chart-sub" id="y2-sub">Starts Oct 14, 2026 with the default plan’s five</p>
      <div id="y2-now"></div>
      <label class="note" for="y2-in">Your stocks (up to 10 tickers, commas or spaces)</label>
      <input id="y2-in" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="DELL, MRNA, MU, AMD, HPE">
      <div class="call-actions"><a class="btn" id="y2-submit" target="_blank" rel="noopener">Save to repo ↗</a><span id="y2-status" role="status"></span></div>
      <p class="note">Saving opens a filled-in GitHub issue: tap <b>Create</b> and the repo records the list within a minute. The list is bought in equal weights at the next close after the day you save it. From then on You-2 follows the default plan: in your stocks while the plan holds the Boost list, in gold, bonds or cash (or half in one) whenever the plan is, and back in your stocks when the plan is (the rebound rule included). Switches happen at the same closes as the plan’s.</p>
    </div>
    <div class="card">
      <p class="chart-title">You-2 record</p>
      <p class="chart-sub">$100 from Oct 14, 2026: You-2 vs the default plan and SPY</p>
      <div id="y2-chart"></div>
      <div id="y2-log"></div>
    </div>
  </div>

  <p class="section-label">Paper record <span class="hint">the default plan, frozen and logged every evening · since Oct 14, 2026</span></p>
  <div class="plan">
    <div class="card" id="paper">
      <p class="chart-title">Paper record: the default plan</p>
      <p class="chart-sub" id="pp-sub">Starts Oct 14, 2026</p>
      <div id="pp-now"></div>
      <div id="pp-chart"></div>
      <p class="note">Each evening after the close, the decision for the next close is logged with the time and a fingerprint of the rule code, and never edited. It fills at the next close with 0.15% per side, like the backtest. Every run also replays each logged day on fresh data and code, and lists any difference.</p>
    </div>
    <div class="card">
      <p class="chart-title">What the backtest says to expect</p>
      <p class="chart-sub">Every 3-, 6- and 12-month window of the default plan on this page’s universe, 2000–2026: return, share of windows ahead of SPY, and the typical worst drop inside a window</p>
      <div class="tablebox" style="border:0;background:none;overflow-x:auto"><table class="years" id="pp-bands"></table></div>
      <div id="pp-log"></div>
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
      <div class="chart-head"><div><p class="chart-title">Growth of $100</p><p class="chart-sub" id="growth-sub">The thick line is the default plan, <b>Boost + rotation</b>. The other lines are alternative mixes to compare it with.</p></div>
        <span class="seg" id="scale-seg"><button type="button" data-v="log">Log</button><button type="button" data-v="linear">Linear</button></span></div>
      <div class="legend" id="legend"></div>
      <div class="chart" id="growth"></div>
    </div>
    <div class="card">
      <p class="chart-title">Year by year</p><p class="chart-sub" id="ytd-note"></p>
      <div class="tablebox" style="border:0;background:none"><table class="years" id="years"></table></div>
    </div>
  </div>

__WALLST__
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

__OVLIB__
  <p class="section-label"><span id="heat-title">Top 15</span>, week by week <span class="hint" id="heat-hint"></span></p>
  <div class="heatbar" id="heat-bar">
    <span class="seg" role="group" aria-label="Show in each cell">
      <button type="button" id="heat-rank" data-v="rank" aria-pressed="true">Week rank</button>
      <button type="button" id="heat-pct" data-v="pct" aria-pressed="false">% change</button>
      <button type="button" id="heat-price" data-v="price" aria-pressed="false">Price</button>
    </span>
    <span class="seg" role="group" aria-label="Color cells by">
      <button type="button" id="heat-size" data-c="size" aria-pressed="true">Color: size of move</button>
      <button type="button" id="heat-norm" data-c="norm" aria-pressed="false">vs its normal week</button>
      <button type="button" id="heat-pricec" data-c="price" aria-pressed="false">Price level</button>
    </span>
    <span class="hkey"><span>down</span><i></i><span>up</span><span id="heat-scale"></span></span>
  </div>
  <div id="heat-ov"></div>
  <div class="heatbox"><table class="heat" id="heat"></table></div>
  <div class="udtrend" id="heat-trend" aria-label="Share of stocks up over time"></div>
  <p class="heatnote" id="heat-note">Hover or tap a cell for details. On a phone, swipe the table sideways.</p>

  <p class="section-label"><span id="dheat-title">Top 30 + large caps</span>, day by day <span class="hint" id="dheat-hint"></span></p>
  <div class="heatbar" id="dheat-bar">
    <span class="seg" role="group" aria-label="Show in each cell">
      <button type="button" id="dheat-rank" data-v="rank" aria-pressed="true">Day rank</button>
      <button type="button" id="dheat-pct" data-v="pct" aria-pressed="false">% change</button>
      <button type="button" id="dheat-price" data-v="price" aria-pressed="false">Price</button>
    </span>
    <span class="seg" role="group" aria-label="Color cells by">
      <button type="button" id="dheat-size" data-c="size" aria-pressed="true">Color: size of move</button>
      <button type="button" id="dheat-norm" data-c="norm" aria-pressed="false">vs its normal day</button>
      <button type="button" id="dheat-pricec" data-c="price" aria-pressed="false">Price level</button>
    </span>
    <span class="hkey"><span>down</span><i></i><span>up</span><span id="dheat-scale"></span></span>
  </div>
  <div class="heatbox"><table class="heat" id="dheat"></table></div>
  <div class="udtrend" id="dheat-trend" aria-label="Share of stocks up over time"></div>
  <p class="heatnote" id="dheat-note">Hover or tap a cell for details. On a phone, swipe the table sideways.</p>

  <p class="section-label">Price, volume and time in 3D <span class="hint" id="pv-hint">last 6 months, daily · drag to rotate</span></p>
  <div class="pv" id="pv">
    <div class="pv-bar">
      <div class="pv-group" role="group" aria-label="Top 10 picks" id="pv-top"><span>Top 10</span></div>
      <div class="pv-group" role="group" aria-label="Other tickers" id="pv-oth"><span>Others</span></div>
    </div>
    <div class="pv-bar">
      <div class="pv-group" role="group" aria-label="Volume shape" id="pv-shape"><span>Volume as</span>
        <button type="button" data-shape="poles" aria-pressed="true">Poles</button>
        <button type="button" data-shape="wall" aria-pressed="false">Wall</button></div>
      <div class="pv-group" role="group" aria-label="View" id="pv-views"><span>View</span>
        <button type="button" data-view="3d" aria-pressed="true">3D</button>
        <button type="button" data-view="top" aria-pressed="false">From above: price</button>
        <button type="button" data-view="front" aria-pressed="false">Front: volume over time</button>
        <button type="button" data-view="side" aria-pressed="false">Side: volume by price</button>
        <button type="button" id="pv-spin" aria-pressed="false">Spin</button></div>
    </div>
    <div class="pv-stage">
      <div class="pv-plot" id="pv-plot" role="img" aria-label="3D chart of daily price and volume"></div>
      <div class="pv-wait" id="pv-wait">Loading the 3D chart…</div>
      <div class="pv-hint">Drag to rotate · scroll or pinch to zoom · hover a point for the day</div>
    </div>
    <div class="pv-stats" id="pv-stats"></div>
    <p class="pv-note">x = time, y = price, z = volume (millions of shares). The grey line on the floor is the price chart; each day stands on it as a pole as tall as that day's volume:
      <i style="background:var(--pos)"></i>green = closed up, <i style="background:var(--neg)"></i>red = closed down. <b>Wall</b> joins the poles into one surface.
      <b>From above</b> = a price chart, <b>Front</b> = volume over time, <b>Side</b> = volume by price level. Gold-edged = held now; the small number is the current rank.</p>
  </div>

__GROWTH__
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
      <th><button type="button" data-sort="revEps" title="Change in analysts' estimate of this year's earnings over the last 90 days, and how many raised / cut estimates in the last 30 days (information only - the rule does not use it)">Estimates</button></th>
      <th>Trend</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
  <button type="button" class="more" id="more" hidden>Show all 100</button>

__RESEARCH__
  <div class="card" id="trk-card">
    <p class="chart-title">Refresh the track record</p>
    <p class="note">The growth chart and year table come from the point-in-time backtest, run through <b id="trk-end">its last refresh</b>; after that each line carries on with the daily scan.
      It reruns by itself every 3 months (Jan 5, Apr 5, Jul 5, Oct 5).</p>
    <div class="call-actions"><a class="btn" id="trk-refresh" href="https://github.com/danreed001-droid/NIBII/actions/workflows/track-refresh.yml" target="_blank" rel="noopener">Refresh now ↗</a></div>
    <p class="note">Opens GitHub: tap <b>Run workflow</b>, then the green <b>Run workflow</b> button. It takes about 15 minutes, and the page updates when it finishes.
      If the default plan’s return a year moves more than 3 points, or its worst drop more than 5, it stops without publishing. To publish anyway, run it again with <b>Publish even if the numbers moved a lot</b> ticked.</p>
  </div>

__ISSUES__
  <footer><ul>
    <li><b>The rule.</b> Score = return from 6 months ago to 1 month ago. Each Friday close: a stock must beat SPY's score to qualify; buy the top 5 in equal weight; a holding stays while it ranks in the top 10, otherwise it is replaced by the best-ranked stock not held. Trades are placed the following Monday in the last 30 minutes before the close (the track record uses Monday's closing prices; trading at Monday's open did about 3% a year worse in testing). Mon–Thu the banner previews what Friday's signal would be if it were today.</li>
    <li><b>Fair test.</b> Picks come from S&amp;P 500 members only, each counted from the day it joined the index. Many companies that later left the index have no free price history (about 4 in 10 members in 2000, 1 in 10 in 2020), which flatters the early years. Small caps are deliberately excluded: adding the Russell 2000 cut the result to about +509% with a −73% drawdown.</li>
    <li><b>Risk.</b> Five stocks is concentrated: drawdowns near −38% happened, it trailed QQQ in <span id="trail-yrs">some years</span>, and a single year's gains can come mostly from one theme. Prices from Yahoo Finance, split-adjusted closes (benchmarks include dividends). A mechanical rule's output, not investment advice.</li>
    <li>Generated by <code>scripts/momentum_scan.py</code> + <code>scripts/render_scanner.py</code> in <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a> · <span id="gen"></span></li>
  </ul></footer>
</div>

<script type="application/json" id="scan-data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('scan-data').textContent);
  var SINCE = (D.rule && D.rule.start ? D.rule.start : '2020').slice(0, 4);
  // the track record and its figures come from the point-in-time backtest (data/track_record.json) when there is one
  var TRK = D.track || null, TSINCE = TRK && TRK.start ? TRK.start.slice(0, 4) : SINCE;
  function bt(k) { return TRK && TRK.stats && TRK.stats[k] ? TRK.stats[k] : null; }
  var NS = 'http://www.w3.org/2000/svg';
  function $(id) { return document.getElementById(id); }
  function cushionLog(CU) {   // the cushion's recent on/off weeks
    if (!CU.log || !CU.log.length) return '';
    return '<br><b>Cushion log</b> (newest first): ' + CU.log.map(function (r) {
      return fmtDate(r[0], { month: 'short', day: 'numeric', year: 'numeric' }) + ' → <b>' + (r[1] === '100/0' ? 'off' : 'on (' + r[1] + ')') + '</b> <span class="muted">(SPY ' + (r[2] == null ? '–' : pct(r[2])) + ', credit ' + (r[3] == null ? '–' : pct(r[3])) + ')</span>';
    }).join(' · ') + '. ';
  }
  var ROTN = { TLT: 'Long Treasuries (20y+)', GLD: 'Gold', SPY: 'S&amp;P 500 ETF', BIL: 'T-bills (cash)', CASH: 'Cash (no T-bills)', DBMF: 'Managed futures (DBMF)', boost: 'the Boost 100% stock list' };
  function rotName(m) { return m === 'boost' ? 'the Boost list' : m === 'CASH' ? 'cash' : m === 'DBMF' ? 'DBMF (managed futures)' : m; }
  function rotTag(RT) {   // the switch decided at the last close
    if (!RT.trade) return whipTag(RT);
    var X = D.plan && D.plan.auto && D.plan.auto.boostx, buy = esc(rotName(RT.mode)) + ' (rotation)';
    if (RT.mode === 'boost' && X && X.holdings && X.holdings.length) {   // back into stocks: name them, and any cash slot
      var sk = (X.fade && X.fade.skipped) || [], open = Math.max(0, 5 - X.holdings.length);
      buy = X.holdings.map(esc).join(', ') + ' (20% each' + (open ? '; keep ' + open * 20 + '% in cash' + (sk.length ? ', ' + sk.map(function (s) { return esc(s.t); }).join(', ') + ' fading' : '') : '') + ')';
    }
    return '<span class="tag sell">sell ' + esc(rotName(RT.held)) + '</span><span class="tag buy">buy ' + buy + '</span>';
  }
  function whipTag(RT) {   // the whipsaw switch decided at the last close
    var W = RT && RT.whip;
    if (!W || !W.trade) return '';
    var full = (W.part == null ? 0.5 : W.part) >= 1;
    if (!W.held) return full ? '<span class="tag sell">sell the Boost list</span><span class="tag buy">buy ' + esc(W.half) + ' with the whole account (whipsaw)</span>'
      : '<span class="tag sell">sell half the Boost list</span><span class="tag buy">buy ' + esc(W.half) + ' with that half (whipsaw)</span>';
    if (!W.half) return '<span class="tag sell">sell ' + esc(W.held) + '</span><span class="tag buy">back to 100% the Boost list (whipsaw off)</span>';
    return '<span class="tag sell">sell ' + esc(W.held) + '</span><span class="tag buy">buy ' + esc(W.half) + ' (whipsaw)</span>';
  }
  function callWhy(pm) {   // bullets under the rebalance banner: why this is the call
    var A = D.plan && D.plan.auto, RT = A && A.rotation, X = A && A.boostx;
    var L = (pm === 'boost100' || pm === 'cushion' || pm === 'rotation') && X ? X : null;
    var f = function (d) { return fmtDate(d, { weekday: 'short', month: 'short', day: 'numeric' }); };
    var nm = { TLT: 'TLT (Treasuries)', GLD: 'GLD (gold)', CASH: 'cash', DBMF: 'DBMF (managed futures)', BIL: 'T-bills' };
    var row = {}, keep = D.rule.keepRank, out = [];
    (D.table || []).forEach(function (r) { row[r.t] = r; });
    var rank = function (t) { return row[t] && row[t].rank ? '#' + row[t].rank : 'below #' + (D.table || []).length; };
    var beat = function (t) { return row[t] && row[t].vsSpy != null ? ' (its 6-to-1-month return beats SPY’s by ' + pct(row[t].vsSpy) + ')' : ''; };
    var held = L ? L.holdings : (D.holdings || []).map(function (h) { return h.t; });
    var FD = L && L.fade, fadeWhy = FD && FD.skipped && FD.skipped.length ? FD.skipped.map(function (s) {
      return '<b>' + esc(s.t) + '</b> (#' + s.rank + ': volume ' + Math.round(s.vol * 100) + '% of normal, daily swings ' + Math.round(s.swing * 100) + '%)';
    }).join(', ') : '';
    var out_ = pm === 'rotation' && RT && RT.mode !== 'boost';
    if (out_) {
      var N = RT.narrow, LH = RT.lowerhigh, B = RT.noBills, holds = nm[RT.mode] || RT.mode, last = (RT.log || [])[0];
      if (N && N.inCash) {
        var R = N.reading;
        out.push('<b>Your plan holds ' + esc(holds) + ', not stocks,</b> until after the close on ' + f(N.until || N.cash[1]) + ': the narrow-market cash week, since the close after ' + f(N.cash[0]) + '.');
        if (R) out.push('Why: SPY is ' + (R.high < 0 ? pct(-R.high).slice(1) + ' below' : 'at') + ' its 52-week high, the equal-weight S&amp;P 500 has trailed it by ' + pct(Math.abs(R.lag)).slice(1) + ' over 3 months (a few big stocks are carrying the index) and the VIX is ' + R.vix.toFixed(1) +
          ', near its 3-month low of ' + R.vixLow.toFixed(1) + '. A calm, narrow high like this has come before drops' + (N.on ? '. The warning fired again at the last close, and each warning moves the end back a week' : '') + '.');
      } else if (LH && LH.inCash) {
        out.push('<b>Your plan holds ' + esc(holds) + ', not stocks,</b> until after the close on ' + f(LH.until || LH.run[1]) + ': the lower-high exit. SPY made a lower high on its weekly chart and closed below it, which came before the bigger drops in testing.');
      } else {
        var rs = { rotate: 'SPY is in a daily downtrend and ' + esc(RT.mode) + ' has been leading', exit: 'SPY is below its 150-day average in a weekly downtrend (the downtrend exit)', 'switch': 'SPY is below its 150-day average in a weekly downtrend (the downtrend exit)', pricebreak: 'SPY broke below its 100-day average while that average and its 7-day average were both falling (the price-break rule), for 10 sessions' };
        out.push('<b>Your plan holds ' + esc(holds) + ', not stocks:</b> ' + (last && rs[last[3]] || 'the rotation rules are out of stocks') + '. It goes back to stocks when that ends.');
      }
      if ((RT.mode === 'CASH' || RT.mode === 'DBMF') && B) out.push((RT.mode === 'DBMF' ? 'Managed futures (DBMF)' : 'Cash') + ', not gold or bonds, because over 3 months ' + B.assets.map(function (t) { return esc(t) + ' is ' + pct(B.pct[t]); }).join(' and ') + ': the plan holds one of them only if it is up, and otherwise DBMF, a fund that follows trends in stock, bond, currency and commodity futures, instead of cash.');
      var RB2 = RT.rebound;
      if (RB2 && RB2.drop != null && RB2.drop >= RB2.drop_th && !RB2.on) {
        var miss = [];
        if (!(RB2.best != null && RB2.best >= RB2.haven_th)) miss.push('gold or bonds up ' + Math.round(RB2.haven_th * 100) + '%+ since the high (now ' + pct(RB2.best) + ')');
        if (!RB2.hl) miss.push('a higher low on SPY’s daily chart');
        out.push('Rebound rule: SPY is ' + pct(-RB2.drop) + ' from its 3-month high; the plan goes back into stocks once it also has ' + miss.join(' and ') + '.');
      }
    } else if (pm === 'rotation' && RT && RT.rebound && RT.rebound.active) {
      var RB = RT.rebound;
      out.push('<b>In stocks because of the rebound rule:</b> SPY is ' + pct(-RB.drop) + ' from its 3-month high (' + fmtDate(RB.high[0], { month: 'short', day: 'numeric' }) + '), gold or bonds is up ' + pct(RB.best) + ' since then, and SPY’s daily chart has made a higher low, so the plan holds the Boost list over the rules that would take it out. Drops like this, with money running to safety and the selling drying up, have rebounded hard.');
    } else if (pm === 'rotation' && RT && RT.spy) {
      var S = RT.spy, NN = RT.narrow;
      var tr = function (x) { return { up: 'uptrend', down: 'downtrend', chop: 'choppy' }[x && x[0]] || 'no clear trend'; };
      out.push('<b>In stocks</b> because SPY is ' + pct(S.gap) + ' vs its 150-day average (daily chart ' + tr(S.daily) + ', weekly ' + tr(S.weekly) + '), with no lower-high exit or narrow-market cash week in force' +
        (NN && NN.cash && !NN.inCash ? '. <b>A narrow-market cash week is scheduled</b> from the close after ' + f(NN.cash[0]) : '') + '.');
    }
    var lead = out_ ? ' in the list it goes back to' : '';
    var sells = D.signalDay && L ? L.sell : D.changes.sell, buys = D.signalDay && L ? L.buy : D.changes.buy;
    var when = D.signalDay ? '' : ' if Friday’s signal were today';
    sells.forEach(function (t) {
      var why = L && (L.blown || []).indexOf(t) >= 0 ? 'blow-off exit: its last month’s gain is more than ' + L.mult + '× its gain over the 5 months before, and SPY is below its ' + L.ma + '-day average (blow-offs tend to fade in a weak market)'
        : L && (L.surged || []).indexOf(t) >= 0 ? 'surge exit: it closed ' + Math.round(L.surge.up * 100) + '%+ up on ' + L.surge.vol + '×+ its usual volume a week ago, which tends to fade'
        : !row[t] || row[t].rank > keep ? 'it has dropped to ' + rank(t) + ', outside the top ' + keep
        : row[t].vsSpy != null && row[t].vsSpy <= 0 ? 'its 6-to-1-month return no longer beats SPY’s (' + pct(row[t].vsSpy) + ')'
        : 'it no longer makes the list (ranks ' + rank(t) + ')';
      out.push('<b>Sell ' + esc(t) + '</b>' + lead + when + ': ' + why + '.');
    });
    var nb = 0;
    buys.forEach(function (t) {
      var why = L && (L.boosted || []).indexOf(t) >= 0 ? 'news boost: it gapped up ' + Math.round((A.boost ? A.boost.gap : 0.12) * 100) + '%+ on news in the last 4 weeks, so it takes the weakest holding’s slot'
        : 'it ranks ' + rank(t) + ', the ' + (nb++ ? 'next ' : '') + 'best-ranked stock not held' + beat(t);
      out.push('<b>Buy ' + esc(t) + '</b>' + lead + when + ': ' + why + '.');
    });
    if (!sells.length && !buys.length && held.length) {
      var hs = held.slice().sort(function (a, b) { return ((row[a] || {}).rank || 999) - ((row[b] || {}).rank || 999); });
      var edge = hs[hs.length - 1], er = (row[edge] || {}).rank;
      var nxt = (D.table || []).filter(function (r) { return held.indexOf(r.t) < 0 && r.vsSpy > 0; })[0];
      out.push('<b>No stock swaps</b>' + lead + ': all ' + held.length + ' holdings still rank in the top ' + keep + ' (' + hs.map(function (t) { return esc(t) + ' ' + rank(t); }).join(', ') +
        '). A holding stays until it drops out of the top ' + keep + ', so small rank moves don’t cause trades.' +
        (er && er >= keep - 1 && nxt ? ' Closest to the edge: ' + esc(edge) + ' at #' + er + '; if it is below #' + keep + ' at Friday’s close, ' + esc(nxt.t) + ' (#' + nxt.rank + ' now) takes its place.' : ''));
    }
    if (fadeWhy && !out_) out.push('<b>Cash slot (' + Math.round((FD.cash || FD.skipped.length) * 100 / 5) + '% of the stocks part)</b>: ' + fadeWhy + (FD.skipped.length === 1 ? ' is' : ' are') +
      ' in the top 5 but not bought: trading volume and daily swings have both faded (under ' + Math.round(FD.vol * 100) + '% and ' + Math.round(FD.swing * 100) + '% of normal), which in testing marked runs running out of steam. The slot stays in cash, not the next stock, until it drops out of the top 5 or picks up again.');
    if (L && !out_) out.push('Blow-off exit ' + (L.armed ? '<b>on</b>: SPY is below its ' + L.ma + '-day average, so a holding whose last month’s gain is more than ' + L.mult + '× its prior 5 months’ is sold'
      : 'off: SPY is above its ' + L.ma + '-day average, and in a steady market selling strong runners early cost money') + '.');
    out.push(D.signalDay ? 'Stock swaps happen only at the week’s last close, traded ' + fmtDate(D.tradeDate, { weekday: 'short', month: 'short', day: 'numeric' }) + ' in the last 30 minutes; moves into or out of stocks, and a sale by the blow-off or surge exit, can happen at any close.'
      : 'Stock swaps happen only at the week’s last close (' + fmtDate(D.signalDate, { weekday: 'short', month: 'short', day: 'numeric' }) + ', traded ' + fmtDate(D.tradeDate, { weekday: 'short', month: 'short', day: 'numeric' }) + '), so earlier in the week this is a preview; moves into or out of stocks, and a sale by the blow-off or surge exit, can happen at any close.');
    return '<ul class="why">' + out.map(function (s) { return '<li>' + s + '</li>'; }).join('') + '</ul>';
  }
  function narrowNote(RT) {   // the narrow-market cash week: rule, reading now, schedule
    var N = RT && RT.narrow;
    if (!N) return '';
    var f = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); }, R = N.reading;
    var end = N.until || (N.cash && N.cash[1]);
    var hn = { TLT: 'TLT (Treasuries)', GLD: 'GLD (gold)', CASH: 'cash', DBMF: 'DBMF (managed futures)', BIL: 'T-bills' };
    var st = !N.ok ? 'no reading (RSP or VIX data missing)' : N.inCash ? '<b>ON: the account holds ' + esc(hn[N.asset] || N.asset || 'cash') + '</b>' + (N.cash ? ' since the close after ' + f(N.cash[0]) : '') + (end ? ', back to the plan after the close on ' + f(end) + ' unless the warning fires again (each warning adds a week)' : '')
      : N.cash ? '<b>cash week scheduled</b>: out of stocks from the close after ' + f(N.cash[0]) + (end ? ' through ' + f(end) : '')
      : N.on ? '<b>warning fired today</b>: out of stocks at the close ' + (N.delay + 2) + ' sessions from now' : 'off';
    var rd = R ? ' Now: SPY ' + pct(R.high) + ' from its 52-week high (needs within ' + Math.round((1 - N.high) * 100) + '%), equal-weight S&amp;P vs SPY over 3 months ' + pct(R.lag) +
      ' (needs below −' + (N.lag * 100).toFixed(1) + '%), VIX ' + R.vix.toFixed(1) + ' vs its 3-month low ' + R.vixLow.toFixed(1) + ' (needs within ' + N.vix + ').' : '';
    var lg = (N.log || []).slice(0, 6).map(f).join(' · ');
    return '<br><span class="' + (N.inCash || N.cash ? 'neg' : 'muted') + '"><b>4. Narrow-market cash week</b> (default since Oct 13, 2026, on probation): ' + st + '.</span>' +
      '<span class="muted"> When SPY closes within 2% of its 52-week high, the equal-weight S&amp;P 500 has lagged it by more than 1.5% over 3 months (a few large stocks carrying the index) and the VIX sits within 2 points of its 3-month low (a calm market), the whole account moves out of stocks at the close ' + (N.delay + 2) + ' sessions later (decided the session before) for ' + N.days + ' sessions (into gold or bonds if one is up over 3 months, else DBMF managed futures: see 6. No T-bills), then back to whatever the plan holds.' + rd +
      ' In the audit the plan made 42.9% a year from 2000 vs 38.8% without it (Sharpe 1.31 vs 1.18; worst drop −34% either way), 45.6% vs 38.9% from 2010 (−24% vs −29%), 54.6% vs 47.2% from 2016 (−23% vs −29%) and 80.5% vs 71.7% from 2020 (−23% vs −29%); since 2012 the plan lost about 39% over its cash days, which random cash weeks matched in only 0.14% of draws, and it held with the thresholds moved. It was found on 2012–2026. On 2006–07, which it was not built on, it fired three times: twice in 2006 it cost money (stocks kept rising and gold, held instead, fell: that year −13.1% instead of +3.0%, the plan’s worst drop), and in October 2007 it caught the top (+38.1% instead of +28.1%). Rebuilt abroad with stand-ins for the equal-weight index and the VIX, it lost in four of five markets (it fired less often there, and in Germany and Japan at the wrong times), so it looks specific to the US: treat it as on probation.' +
      (lg ? ' Last warnings: ' + lg + ' (' + N.n + ' warning days since 2012).' : '') + '</span>';
  }
  function lowerhighNote(RT) {   // the lower-high exit: rule, reading now, current two weeks, log
    var L = RT && RT.lowerhigh;
    if (!L) return '';
    var f = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); }, R = L.reading;
    var px = function (p) { return p[1].toFixed(2) + ' (' + f(p[0]) + ')'; };
    var end = L.until || (L.run && L.run[1]);
    var nm = { TLT: 'TLT (Treasuries)', GLD: 'GLD (gold)', BIL: 'T-bills', CASH: 'cash', DBMF: 'DBMF (managed futures)' };
    var st = L.inCash ? '<b>ON: the account holds ' + esc(nm[L.asset] || L.asset || 'cash') + '</b>' + (L.run ? ' since the close after ' + f(L.run[0]) : '') + (end ? ', back to the plan after the close on ' + f(end) : '')
      : R && R.on ? (RT.mode !== 'boost' ? 'off: the signal is on, but the plan is already out of stocks' : 'off: the signal is on, but this lower high has already had its two weeks (only a new one fires again)')
      : 'off';
    var rd = '';
    if (R) {
      var lower = R.highs[1][1] < R.highs[0][1];
      rd = ' Now: SPY ' + R.close.toFixed(2) + '; last two weekly swing highs ' + px(R.highs[0]) + ' → ' + px(R.highs[1]) + ' (' + (lower ? '<b>lower</b>' : 'higher') + ')' +
        (R.peak ? '; latest weekly peak since, not yet confirmed, ' + px(R.peak) + (R.peak[1] < R.highs[1][1] ? ' (lower)' : '') : '') +
        (R.daily && R.daily.length === 2 ? '; last two daily swing highs ' + px(R.daily[0]) + ' → ' + px(R.daily[1]) + ' (' + (R.daily[1][1] < R.daily[0][1] ? 'lower' : 'higher') + ')' : '') +
        (R.on ? ' → <b>' + (R.kind === 'early' ? 'early' : 'confirmed') + ' lower high</b>' : '') + '.';
    }
    var lg = (L.log || []).slice(0, 6).map(function (r) { return f(r[0]) + ' <span class="muted">(' + esc(r[1]) + ')</span>'; }).join(' · ');
    return '<br><span class="' + (L.inCash ? 'neg' : 'muted') + '"><b>5. Lower-high exit</b> (default since Oct 13, 2026, on probation): ' + st + '.</span>' +
      '<span class="muted"> When SPY’s weekly chart (swings ' + L.swing + ' weeks either side) makes a lower high and SPY closes below it — or, without waiting for that high to be confirmed, the latest weekly peak sits below the last swing high while the daily chart has already made a lower high and SPY closes below both — the whole account moves into the stronger of TLT / GLD (the one in a daily uptrend with the steepest gradient, picked again each day; when neither is rising, the one up more over 3 months if it is up, else DBMF managed futures) for ' + L.days + ' sessions (two weeks), then back to whatever the plan holds. An early signal and the later confirmation of the same high each get their two weeks; the signal that just fired can’t fire again right away. It acts only while the plan holds the Boost list, so a lower high still in place when the plan comes back into stocks fires then.' + rd +
      ' In the audit the plan made 42.9% a year from 2000 vs 40.2% without it, worst drop −34% vs −35% (after tax 27.0% vs 25.4%); 45.6% vs 41.1% from 2010 (−24% vs −35%); 54.6% vs 52.0% from 2016 and 80.5% vs 76.5% from 2020 (same worst drops). In the T-bills version of the plan (38.8% from 2000), one stretch per lower high (no second two weeks on confirmation) made 37.9% and T-bills instead of gold or bonds in the exit 37.5% (gold and bonds helped most in 2008 and 2011). The extra return depends on the exact timing (with T-bills, 12 sessions or acting a day late beat the plan from only one of four starts), but the smaller drops held in every variant. Staying out until SPY’s downtrend ended instead of two weeks cut the drops but cost 2–8 points a year, because the momentum stocks rebound before SPY confirms. It fired about once a year and was designed after looking at the 2007–2011 and 2022 drops, so treat it as on probation.' +
      (lg ? ' Last signals: ' + lg + ' (' + L.n + ' since ' + SINCE + ').' : '') + '</span>';
  }
  function noBillsNote(RT) {   // no T-bills: what the plan holds wherever it would have held T-bills
    var B = RT && RT.noBills;
    if (!B) return '';
    var nm = { TLT: 'TLT (Treasuries)', GLD: 'GLD (gold)', CASH: 'cash', DBMF: 'DBMF (managed futures)' };
    var chg = B.assets.map(function (t) { return esc(t) + ' ' + (B.pct[t] == null ? '–' : pct(B.pct[t])); }).join(' · ');
    return '<br><span class="muted"><b>6. No T-bills</b> (default since Oct 13, 2026): wherever the rules above would hold T-bills — the narrow-market cash week, the downtrend or lower-high exit with neither TLT nor GLD rising, the whipsaw switch with nothing up — the plan holds instead whichever of TLT / GLD is up more over the last ' + B.look + ' sessions (3 months; 6 months until Oct 19, 2026) if it is up at all, else DBMF, a managed-futures fund that follows trends in stock, bond, currency and commodity futures (plain cash earning nothing until Oct 20, 2026), picked again at each close. ' +
      'Now: 3-month change ' + chg + ' → it would hold <b>' + esc(nm[B.pick] || B.pick) + '</b>. ' +
      'DBMF instead of plain cash (Oct 20, 2026) made 42.9% a year from 2000 vs 42.4% with cash (after tax 27.0% vs 26.7%; worst drop −34% either way), 45.6% vs 44.7% from 2010, 54.6% vs 53.2% from 2016 and 80.5% vs 77.9% from 2020; all of the gain is from May 2019, when the fund began (cash before). A trend-following stand-in rebuilt back to 2000 was ahead of cash by about 2 points a year from 2000 and in seven of nine markets abroad; month by month the gain is not proven (t 1.2). ' +
      'With plain cash, the 3-month look (Oct 19, 2026) made 42.4% a year from 2000 vs 41.0% with the 6-month one (after tax 26.7% vs 25.9%; worst drop −34% either way), 44.7% vs 43.3% from 2010, 53.2% vs 50.8% from 2016 and 77.9% vs 75.0% from 2020; ahead from all seven start years tested (2000 to 2020, by 1.3 to 2.8 points), in 232 of 285 rolling 3-year windows (45 behind) and in Japan, the UK and Germany; 2013–2025 about level, so 2026 carries much of the recent gain; month by month the gain is not proven (t 1.2). ' +
      'In the audit the plan made 42.9% a year from 2000 vs 38.8% with T-bills and 38.3% with plain cash in every T-bill slot (after tax 27.0% vs 24.5%; worst drop −34% vs −32%), 45.6% vs 41.2% from 2010, 54.6% vs 47.9% from 2016 and 80.5% vs 72.6% from 2020 (same worst drops). Since 2000 it replaced 945 T-bill days: 371 in gold, 354 in bonds, 173 in DBMF, 47 in cash (before DBMF began). ' +
      'Holding the stronger of the two even when both are falling did about the same or worse (42.4%, 44.6%, 51.6%, 74.6%). The gain over T-bills is lumpy: most of it is bonds in late 2008 and gold during the 2024–2025 cash weeks, so count on it about matching T-bills, not on the extra return.</span>';
  }
  function reboundNote(RT) {   // the rebound rule: stay in stocks after a deep drop that has started to turn
    var B = RT && RT.rebound;
    if (!B) return '';
    var f = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); };
    var hv = Object.keys(B.haven || {}).map(function (t) { return esc(t) + ' ' + pct(B.haven[t]); }).join(', ');
    var lows = B.lows && B.lows.length === 2 ? 'last two daily swing lows ' + B.lows[0][1].toFixed(2) + ' (' + f(B.lows[0][0]) + ') → ' + B.lows[1][1].toFixed(2) + ' (' + f(B.lows[1][0]) + ')' : 'not two daily swing lows yet';
    var st = B.active ? '<b>ON: the plan holds the Boost list</b> over the other rules' : B.on ? 'conditions met, but the plan holds stocks anyway' : 'off';
    var rd = B.high ? ' Now: SPY ' + pct(-B.drop) + ' from its highest close of the last ' + B.look + ' sessions (' + B.high[1].toFixed(2) + ' on ' + f(B.high[0]) + '; needs −' + Math.round(B.drop_th * 100) + '% or worse); since then ' + (hv || 'no gold / bond prices') + ' (the better needs +' + Math.round(B.haven_th * 100) + '% or more); ' + lows + ' (' + (B.hl ? 'a higher low since the high' : 'no higher low since the high') + ').' : '';
    var lg = (B.log || []).map(function (r) { return f(r[0]) + (r[1] !== r[0] ? '–' + f(r[1]) : ''); }).join(' · ');
    return '<br><span class="' + (B.active ? 'pos' : 'muted') + '"><b>7. Rebound rule</b> (default since Oct 14, 2026, on probation): ' + st + '.</span>' +
      '<span class="muted"> When SPY closes 12% or more under its highest close of the last 3 months, gold or bonds (the better of GLD / TLT) is up 2% or more since that high, and SPY’s daily chart has made a higher low since then (its last swing low, ' + B.swing + ' days either side, above the one before), the plan holds the Boost list whatever rules 1–6 say. Money running to safety during a deep drop marks the kind of fall that has rebounded hard, and the higher low says the selling has started to dry up; without that last check the rule stayed in stocks through the October 2008 collapse (worst drop −40% instead of −33%).' + rd +
      ' In the audit the plan made 42.9% a year from 2000 vs 41.1% without it, 45.6% vs 43.9% from 2010, 54.6% vs 54.4% from 2016 and 80.5% vs 76.2% from 2020, worst drops −34% vs −32% from 2000 and −23% vs −23% from 2020. It overrode the other rules on only 70 sessions since 2000, most of them in late 2008 and early 2009 (2008 +32.0% instead of +24.1%, 2009 +161.3% instead of +134.2%), the rest in 2001, 2002, 2011 (+24.2% instead of +16.0%), 2016 and 2020. At 15% it made about the same as without it and at 20% a little more, so it rests on a handful of bear-market bottoms and was picked after about 80 timing tests in one day. Checked on the index alone where the audit never looked: in the US in 1962–1999 it fired 6 times and the S&amp;P 500 was higher 3 months later every time (median +17%); abroad, with US bonds and gold as the havens, the index did better after it fired than after other deep drops in the UK, Germany and Japan but not Canada, and as a re-entry on a simple 150-day timing rule it added a little return in most markets while deepening the worst drop in Japan, Germany and Hong Kong; and in 1928–1961, with no gold or bond prices to check, the deep drop and higher low alone kept buying the 1930s collapse (worst drop −66% vs −41%). Treat it as on probation.' +
      (lg ? ' Last held: ' + lg + ' (' + B.n + ' stretches since ' + SINCE + ').' : ' It has not had to override the other rules since ' + SINCE + '.') + '</span>';
  }
  function pricebreakNote(RT) {   // the price-break haven rule
    var P = RT && RT.pricebreak;
    if (!P) return '';
    var f = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); };
    var st = P.active ? '<b>ON: the plan holds the haven pick, not stocks</b>' : P.brk ? 'break today' : 'off';
    var rd = P.close != null ? ' Now: SPY closed ' + P.close.toFixed(2) + ', ' + (P.below ? 'under' : 'above') + ' its ' + P.slow_n + '-day average (' + P.slow.toFixed(2) + '); its ' + P.fast_n + '-day average is ' + P.fast.toFixed(2) + '; both averages are ' + (P.down ? '' : 'not ') + 'lower than ' + P.slope + ' sessions ago.' : '';
    var lg = (P.log || []).map(function (r) { return f(r[0]) + (r[1] !== r[0] ? '–' + f(r[1]) : ''); }).join(' · ');
    return '<br><span class="' + (P.active ? 'pos' : 'muted') + '"><b>8. Price-break rule</b> (default since Oct 24, 2026, on probation): ' + st + '.</span>' +
      '<span class="muted"> On the day SPY closes under its ' + P.slow_n + '-day average for the first time (it closed on or above it the day before) while that average and its ' + P.fast_n + '-day average are both lower than ' + P.slope + ' sessions earlier, the plan holds the haven pick (the better of TLT / GLD over 3 months if it is up, else DBMF) for the next ' + P.hold + ' sessions, wherever it would otherwise hold stocks. In the audit (0.05% per side) the plan made 45.8% a year from 2000 vs 44.3% without it, 52.5% vs 51.8% from 2010, 66.4% vs 65.7% from 2016 and 90.5% vs 89.3% from 2020; worst drop −28% vs −32%. It changed the holding in only 9 of 27 years (99 haven days): ahead in 2002, 2003, 2007, 2011 and 2022, behind in 2001, 2008, 2012 and 2015. The same signals moved 2–24 years in time never matched the gain, but the result rests on a handful of breaks and one rule family tried many ways; abroad it was ahead in 4 of 10 markets and behind in 5, so it is on probation.' + rd +
      (lg ? ' Last held: ' + lg + ' (' + P.n + ' stretches since ' + SINCE + ').' : ' It has not had to move the plan since ' + SINCE + '.') + '</span>';
  }
  function whipNote(RT) {   // the whipsaw switch: rule, reading now, recent sales, log
    var W = RT && RT.whip;
    if (!W) return '';
    var full = (W.part == null ? 0.5 : W.part) >= 1;
    var nm = { TLT: 'Treasuries', GLD: 'gold', SPY: 'SPY', BIL: 'T-bills', CASH: 'cash', DBMF: 'DBMF (managed futures)' };
    var chg = W.assets.map(function (t) { return esc(t) + ' ' + (W.chg[t] == null ? '–' : pct(W.chg[t])) + (W.weekly[t] === 'down' ? ' <span class="muted">(weekly downtrend, skipped)</span>' : ''); }).join(' · ');
    var lg = (W.log || []).map(function (r) { return fmtDate(r[0], { month: 'short', day: 'numeric', year: 'numeric' }) + (r[1] !== r[0] ? '–' + fmtDate(r[1], { month: 'short', day: 'numeric', year: 'numeric' }) : '') + (r[2] ? ' (' + esc(r[2]) + ')' : ''); }).join(' · ');
    var sl = (W.sales || []).slice(0, 8).map(function (r) { return esc(r[1]) + ' <span class="' + (r[4] < 0 ? 'neg' : 'pos') + '">' + (r[4] == null ? '–' : pct(r[4])) + '</span>' + (r[5] ? ' <span class="muted">(skipped by the filter, counted)</span>' : ''); }).join(' · ');
    var G = W.regime || {};
    var now = W.on ? (RT.mode !== 'boost' ? 'on, but the plan is out of stocks, so it has nothing to split'
      : W.half ? (full ? '100% <b>' + esc(W.half) + '</b> (' + esc(nm[W.half] || W.half) + ')' : 'half the Boost list, half <b>' + esc(W.half) + '</b> (' + esc(nm[W.half] || W.half) + ')')
      : G.on ? '100% the Boost list: the check is on, but rates and gold are both rising, so the switch stands aside' : '100% the Boost list') : '100% the Boost list';
    var reg = G.rate != null ? ' <b>Rate/gold regime:</b> 10-year yield ' + G.rate.toFixed(2) + '% (' + (G.rate0 != null ? G.rate0.toFixed(2) + '% ' + G.look + ' sessions ago' : 'no earlier reading') + '), gold ' + (G.goldChg == null ? '–' : pct(G.goldChg)) + ' over the same 3 months → ' +
      (G.on ? '<span class="pos">both rising</span>: the switch stands aside and the plan stays fully in the Boost list (bonds tend to lose while rates climb)' : 'not both rising: the switch works as usual') +
      '. <span class="muted">Added Oct 10, 2026: 29.7% → 29.9% a year before tax from 2000 (19.1% → 19.2% after), 29.4% → 29.8% from 2010, 37.5% → 38.1% from 2016, 55.8% → 57.2% from 2020, same worst drops (corrected data); a small gain, on probation until live results back it. Both rising on ' + G.daysOn + ' of ' + G.days + ' sessions since ' + SINCE + '.</span>' : '';
    return '<br><b>3. Whipsaw switch ' + (W.on ? '<span class="neg">ON</span>' : 'off') + ':</b> at each week’s last close, of the stocks the Boost list sold in the last ' + W.look + ' sessions (6 months; at least ' + W.need + ' sales), if ' + Math.round(W.loss * 100) + '% or more were sold below their buy price, momentum is whipsawing: until a later week’s check finds otherwise, ' + (full ? 'the whole account' : 'half of it (the rest stays in the Boost list)') + ' goes into whichever of ' + W.assets.join(', ') + ' is up most over the last ' + W.pctLook + ' sessions (3 months), skipping any in a weekly downtrend (if none is up, the stronger of TLT / GLD over 3 months if it is up, else cash). ' +
      (full ? '<span class="muted">Until Oct 16, 2026 only half the account moved. Moving all of it made 42.9% a year from 2000 vs 42.0% (worst drop −34% either way), 45.6% vs 44.1% from 2010, 54.6% vs 53.8% from 2016 and 80.5% vs 78.1% from 2020 (−23% vs −27%); most of the gain came in 2011 and 2016 (and it gave back 6 points in 2015), month by month it is not proven (t 0.9), and in Japan, the UK, Germany, India and Hong Kong it was up in two and down in three (within about a point), so it is on probation.</span> ' : '') +
      'Since Oct 16, 2026 the check counts the Boost list with the fading-energy filter off: a stock the filter skipped counts as if it had been bought and later sold, and an empty slot is not a sale, so the filter changes which stocks are bought, never when the switch steps out. ' +
      '<b>Now:</b> ' + now + (W.trade ? ' — <b>trade at the close on ' + fmtDate(W.trade, { weekday: 'short', month: 'short', day: 'numeric' }) + '</b>' : '') + '. ' +
      'Boost-list sales in the last ' + W.look + ' sessions: ' + W.n + ', ' + W.lost + ' at a loss' + (W.share != null ? ' (' + Math.round(W.share * 100) + '%; ' + Math.round(W.loss * 100) + '% switches it on)' : '') + (W.previewOn !== W.on ? ' — if the week ended today it would turn <b>' + (W.previewOn ? 'on' : 'off') + '</b>' : '') + '. ' +
      '3-month change: ' + chg + (W.pick ? ' → it would go into <b>' + esc(W.pick) + '</b>' : '') + '. ' +
      (sl ? 'Recent sales: ' + sl + '. ' : '') +
      'On ' + W.daysOn + ' of ' + W.days + ' sessions since ' + SINCE + (lg ? '. Recent stretches: ' + lg : '') + '. ' +
      reg + ' ' +
      '<span class="muted">In the 2000–2026 audit it was on about 5% of the time (late 2008, late 2011, late 2015, late 2018, 2022) and took the plan from 29.0% to 29.7% a year before tax (18.7% to 19.1% after), worst drop −51% to −49%; from 2010 29.1% to 29.4%; from 2020 55.9% to 55.8%, worst drop −39% to −31% (corrected data). About 100 chop filters were tried before this one, so treat the small gain as luck and the smaller drops as the point.</span>';
  }
  function warnNote(RT) {   // information only: SPY falling below its average while bonds or gold rise
    if (!RT) return '';
    var lg = (RT.warnLog || []).map(function (r) { return fmtDate(r[0], { month: 'short', day: 'numeric', year: 'numeric' }) + (r[1] !== r[0] ? '–' + fmtDate(r[1], { month: 'short', day: 'numeric' }) : '') + ' (' + esc(r[2]) + ')'; }).join(' · ');
    return '<br><span class="' + (RT.warn ? 'neg' : 'muted') + '"><b>Downtrend warning ' + (RT.warn ? 'ON' : 'off') + '</b></span><span class="muted"> (information only, not traded): SPY’s daily chart in a downtrend (lower highs, lower lows), SPY below its ' + RT.ma + '-day average, and TLT or GLD rising' +
      (RT.warn ? ' — now: <b>' + esc(RT.warn) + '</b> is rising (up most over 6 months). The rule itself waits for its 15-session confirmation before switching; stepping aside earlier is your call.' : '.') +
      ' Tested as an automatic switch (straight into the rising asset) it fixed late 2018 (−3% instead of −15%) but cost about 2 points a year over 2000–2026, because most of these warnings were short dips. On ' + RT.warnDays + ' sessions since ' + SINCE + (lg ? '. Recent: ' + lg : '') + '.</span>' + breadthNote(RT) + warnCallNote(RT) + rsiNote(RT.rsiWarn) + trendNote(RT.trendWatch) + chopNote(RT.chop);
  }
  var WC_KEY = 'nibii-warncalls';
  function wcLoad() { try { return JSON.parse(localStorage.getItem(WC_KEY) || '{}') || {}; } catch (e) { return {}; } }
  function wcSave(o) { try { localStorage.setItem(WC_KEY, JSON.stringify(o)); } catch (e) {} }
  function warnCallNote(RT) {   // your own out / stay call on a warning day, scored 3 months later
    var WC = RT && RT.warnCalls, rec = (WC && WC.calls) || [], local = wcLoad(), day = D.asOf, mine = local[day] || null;
    var inRepo = {}; rec.forEach(function (r) { inRepo[r.d] = r.c; });
    var h = '<br><span id="warn-call"><b>Your call on the warning</b> <span class="muted">(recorded, not traded; scored 3 months later: “stay” earns what the plan made, “out” what half bonds, half gold made):</span> ';
    if (RT.warn) {
      var cur = (mine && mine.c) || inRepo[day];
      h += '<button type="button" class="wc-btn" data-wcall="out" aria-pressed="' + (cur === 'out') + '">Out: half bonds, half gold</button> ' +
           '<button type="button" class="wc-btn" data-wcall="stay" aria-pressed="' + (cur === 'stay') + '">Stay in stocks</button> ';
      var todo = {}; Object.keys(local).forEach(function (k) { if (inRepo[k] !== local[k].c) todo[k] = local[k]; });
      if (Object.keys(todo).length) {
        var body = 'Downtrend-warning call from the Top 5 dashboard. Leave the block below as-is: the Calls intake workflow records it in docs/my_calls.json and closes this issue.\n\n```json\n' + JSON.stringify({ warn: todo }) + '\n```\n';
        h += '<a class="wc-sub" target="_blank" rel="noopener" href="https://github.com/danreed001-droid/NIBII/issues/new?title=' + encodeURIComponent('calls warn ' + day) + '&body=' + encodeURIComponent(body) + '">Save it to the repo</a> <span class="muted">(opens a GitHub issue; press Submit)</span>';
      } else if (inRepo[day]) h += '<span class="muted">Recorded: <b>' + esc(inRepo[day]) + '</b>.</span>';
    } else h += '<span class="muted">The buttons appear on days the warning is on.</span>';
    if (WC && WC.n) h += ' <span class="muted">Your record: ' + WC.right + ' of ' + WC.n + ' scored calls right; $1 → ' + pct(WC.me, 0) + ' on your calls vs ' + pct(WC.stay, 0) + ' always staying in the plan and ' + pct(WC.out, 0) + ' always out.</span>';
    if (rec.length) h += ' <span class="muted">Calls: ' + rec.slice(0, 8).map(function (r) {
      return fmtDate(r.d, { month: 'short', day: 'numeric', year: 'numeric' }) + ' <b>' + esc(r.c) + '</b> ' + (r.done ? '(' + (r.right ? '✓' : '✗') + ' plan ' + pct(r.plan != null ? r.plan : r.spy) + ', bonds + gold ' + pct(r.duo) + ', SPY ' + pct(r.spy) + ')'
        : '(scored ' + fmtDate(r.due, { month: 'short', day: 'numeric' }) + '; so far plan ' + pct(r.plan != null ? r.plan : r.spy) + ', bonds + gold ' + pct(r.duo) + ')');
    }).join(' · ') + '.</span>';
    return h + '</span>';
  }
  function breadthNote(RT) {   // how broad the selloff is: a clue for your call, not a rule
    var B = RT && RT.breadth;
    if (!B || B.down == null) return '';
    var broad = B.down >= B.broad, cut = Math.round(-B.cut * 100), sh = Math.round(B.broad * 100);
    return '<br><span class="' + (RT.warn && broad ? 'neg' : 'muted') + '"><b>Breadth: ' + Math.round(B.down * 100) + '% of stocks</b> (of ' + B.n + ') are down ' + cut + '% or more over the last month' +
      (B.prev != null ? ' (' + Math.round(B.prev * 100) + '% yesterday)' : '') + ' — ' + (broad ? '<b>a broad selloff</b>' : 'a narrow one') + ' by the ' + sh + '% line.</span>' +
      '<span class="muted"> A clue for your call, not a rule: at the 32 warnings since 2001, broad selloffs favoured going out (bonds + gold beat the plan in 10 of 15) and narrow ones favoured staying (the plan won 13 of 17); March 2020 was the broadest and still rebounded hard. As an automatic rule it cost 1–7 points a year, so it stays information only.</span>';
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-wcall]');
    if (!b) return;
    var o = wcLoad(); o[D.asOf] = { c: b.getAttribute('data-wcall'), note: '', at: new Date().toISOString() }; wcSave(o);
    var el = document.getElementById('warn-call'), RT = D.plan && D.plan.auto && D.plan.auto.rotation;
    if (el && RT) el.outerHTML = warnCallNote(RT);
  });
  function rsiNote(W) {   // RSI(14) support-line break (information only)
    if (!W) return '';
    var lg = (W.log || []).map(function (r) { return fmtDate(r[0], { month: 'short', day: 'numeric', year: 'numeric' }) + ' <span class="muted">(SPY ' + (r[2] == null ? '–' : pct(r[2])) + ' vs 150-day)</span>'; }).join(' · ');
    return '<br><span class="' + (W.on ? 'neg' : 'muted') + '"><b>RSI support-line warning ' + (W.on ? 'ON' : 'off') + '</b></span><span class="muted"> (information only): SPY’s 14-day RSI closed below a support line drawn through its swing lows (at least 4 touching it, none clearly below) in the last 20 sessions, with SPY below or within 2% of its 150-day average' +
      (W.on ? ' — broke on ' + fmtDate(W.date, { month: 'short', day: 'numeric' }) + ' (line ' + W.line + ', RSI now ' + W.rsi + ', SPY ' + pct(W.gap) + ' vs its 150-day)' : (W.date ? '; last break ' + fmtDate(W.date, { month: 'short', day: 'numeric', year: 'numeric' }) : '')) +
      '. It fired before the August 2015 and October 2018 drops; as an automatic exit it made about 2 points a year less from 2000 (2018 −7% instead of −15%, but 2015 −15% instead of −6%), so it is a heads-up, not a trade.' + (lg ? ' Recent breaks: ' + lg + '.' : '') + '</span>';
  }
  function chopNote(C) {   // choppy-market watch: the plan moved the whole account 3+ times in the last 40 sessions (information only)
    if (!C) return '';
    var f = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); };
    var nm = function (h) { return h === 'boost' ? 'stocks' : h; };
    var mv = (C.moves || []).map(function (m) { return f(m[0]) + ' ' + esc(nm(m[1])) + '→' + esc(nm(m[2])); }).join(' · ');
    var sp = (C.spells || []).filter(function (s) { return s[1]; }).slice(-3).map(function (s) { return f(s[0]) + '–' + f(s[1]); }).join(' · ');
    return '<br><span class="' + (C.on ? 'neg' : 'muted') + '"><b>Choppy-market watch ' + (C.on ? 'ON' : 'off') + '</b></span><span class="muted"> (information only' + (C.on && C.since ? ', since ' + f(C.since) : '') + '): the default plan moved the whole account ' + C.n + ' time' + (C.n === 1 ? '' : 's') + ' in the last ' + C.look + ' sessions (on at ' + C.need + ')' + (mv ? ': ' + mv : '') + '.' +
      ' Flipping like this is how the plan loses in a sideways market: in late 2015 it made 17 moves in four months and lost 12% while SPY rose 7%. Tested as rules (Oct 20, 2026): holding at least 5 to 15 sessions after a move, holding the strongest of SPY, gold or bonds, holding the stocks, or sitting in cash or DBMF while all three move little; none beat simply following the plan, because the same flipping also starts real crashes (2008, 2020, 2022). So the plan keeps following its rules; this tells you when a run of small losses is likely. In the 2000–2026 backtest it was on about 30% of sessions; here, ' + C.daysOn + ' of ' + C.days + ' sessions since ' + SINCE + '.' + (sp ? ' Recent spells: ' + sp + '.' : '') + '</span>';
  }
  function trendNote(T) {   // SPY trendline watch: a rising weekly line touched 3 or 4 times about evenly (information only)
    if (!T) return '';
    var f = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); };
    var tp = function (L) { return L.touches.map(function (t) { return f(t[0]); }).join(', '); };
    var L = T.line, B = T.last;
    var st = T.on ? 'ON' : 'off';
    var brk = B ? (T.on ? ' — SPY closed under its line on ' + f(B.date) + ' (line ' + B.level.toFixed(2) + ', close ' + B.close.toFixed(2) + '; the line ran through the ' + f(B.a[0]) + ' and ' + f(B.b[0]) + ' weekly lows, touched ' + tp(B) + ')' : '; last break ' + f(B.date)) : '';
    var now = L ? ' Line watched now: through the ' + f(L.a[0]) + ' and ' + f(L.b[0]) + ' weekly lows, touched ' + tp(L) + '; at ' + L.level.toFixed(2) + ' this week, SPY ' + T.close.toFixed(2) + ' (' + pct(L.gap) + ' vs the line).' : ' No line qualifies right now.';
    var lg = (T.log || []).map(function (r) { return f(r[0]); }).join(' · ');
    return '<br><span class="' + (T.on ? 'neg' : 'muted') + '"><b>SPY trendline warning ' + st + '</b></span><span class="muted"> (information only)' + brk + '. A rising line on SPY’s weekly chart through two swing lows at least ' + T.span + ' weeks (6 months) apart, touched 3 or 4 times about evenly: weeks whose low sits within 1% of the line, starting at its first point and reaching its second, the shortest gap at least half the longest. It fires on the first close under the line and stays on for ' + T.days + ' sessions; each line breaks once.' + now +
      ' As a two-week step out of stocks on top of Boost + rotation it fired 5 times since 2000 and made 37.4% a year from 2000 vs 37.8% for the plan (39.3% vs 39.2% from 2010, 46.1% vs 47.3% from 2016): it caught October 2014 (that year +11.5% instead of −3.6%) but cost 2000 and 2018, and stepping out again on a second break of the same line did worse, so it is a heads-up, not a trade.' + (lg ? ' Recent breaks: ' + lg + '.' : '') + '</span>';
  }
  function rotNote(RT, P) {   // the Boost + rotation explainer with today's readings
    var arw = function (l) { return l && l[0] ? (l[0] === 'up' ? 'up ▲' : l[0] === 'down' ? 'down ▼' : 'choppy') : '–'; };
    var gr = function (l) { return l && l[1] != null ? ' (gradient ' + l[1].toFixed(2) + ')' : ''; };
    var S = RT.spy, LH = S.lastHigh, why = { rotate: 'rotation', 'rotate-end': 'its uptrend broke', exit: 'downtrend exit', 'switch': 'best asset changed', above: 'SPY back above its average', steeper: 'SPY’s higher lows steeper', narrow: 'narrow-market cash week', 'narrow-end': 'cash week over', lowerhigh: 'lower-high exit', 'lowerhigh-end': 'two weeks out over', nobills: 'no T-bills: stronger of TLT / GLD, or cash', rebound: 'rebound rule: back in stocks', 'rebound-end': 'rebound rule over', pricebreak: 'price-break rule: SPY broke its 100-day average', 'pricebreak-end': 'price-break stay over' };
    var now = RT.mode === 'boost' ? 'in the <b>Boost 100% stock list</b>' : 'out of stocks, in <b>' + esc(RT.mode) + '</b> (' + esc(ROTN[RT.mode] || '') + ')';
    return '<b>Boost + rotation (the default):</b> the Boost 100% stock list (with its blow-off and surge exits), moved out of stocks when the charts say so; decided at any close and traded at the next close. ' +
      '<b>1. Rotation:</b> while SPY’s daily chart makes lower highs and lower lows, if TLT or GLD makes higher highs and higher lows with a steeper gradient than SPY (the line through its last two higher lows, scaled by its volatility), switch into whichever of them is up more over the last 6 months once it has led on more than ' + RT.confirm + ' of SPY’s downtrend sessions (counted only while SPY is in its downtrend; the count starts over once SPY has been out of its downtrend for more than ' + (RT.confirmGap || 10) + ' sessions); back to stocks the day its uptrend breaks. ' +
      '<b>2. Downtrend exit:</b> out of stocks when SPY’s weekly chart is in a downtrend whose last lower high sat below the ' + RT.ma + '-day average, SPY is below the average too, and the line through its last two weekly lower lows falls slowly (a grinding bear market, not a crash); then hold whichever of TLT / GLD is in an uptrend and up more over the last 6 months (if neither, the one up more over 3 months if it is up at all, else T-bills, which rule 6 swaps for gold, bonds or DBMF). The exit ends when SPY closes above its ' + RT.ma + '-day average, or SPY’s daily higher lows are steeper than TLT’s and GLD’s; then back to what rotation holds (usually stocks). ' +
      '<br><b>Now:</b> ' + now + (RT.trade ? ' — <b>switch at the close on ' + fmtDate(RT.trade, { weekday: 'short', month: 'short', day: 'numeric' }) + '</b> (from ' + esc(rotName(RT.held)) + ')' : '') + '. ' +
      'SPY daily ' + arw(S.daily) + gr(S.daily) + ', weekly ' + arw(S.weekly) + ', ' + pct(S.gap) + ' vs its ' + RT.ma + '-day average' +
      (LH ? '; last weekly swing high ' + LH.px.toFixed(2) + ' (' + esc(LH.label || '') + ', ' + fmtDate(LH.d) + (LH.ma ? ', average then ' + LH.ma.toFixed(2) : '') + ')' : '') + '. ' +
      RT.assets.map(function (t) { var c6 = RT.pickPct && RT.pickPct[t]; return t + ' daily ' + arw(RT.legs[t]) + gr(RT.legs[t]) + (c6 != null ? ', 6-month ' + pct(c6) : ''); }).join(' · ') + '.' +
      (RT.cand && RT.mode === 'boost' && RT.streak ? ' ' + esc(RT.cand) + ' has led for ' + RT.streak + ' sessions (more than ' + RT.confirm + ' needed).' : '') +
      ' Out of stocks on ' + RT.daysOut + ' of ' + RT.days + ' sessions since ' + SINCE + ', ' + RT.switches + ' switches. ' + (bt('rotation') && bt('boost100') ? 'Backtest since ' + TSINCE + ' (stocks in the S&amp;P 500 at the time): ' + pct(bt('rotation').annual, 1) + ' a year, worst drop ' + pct(bt('rotation').maxDD, 0) + ' vs ' + pct(bt('boost100').annual, 1) + ' and ' + pct(bt('boost100').maxDD, 0) + ' for Boost 100%. ' : '') +
      'In the 2000–2026 audit (stocks in the S&amp;P 500 at the time, 0.15% slippage, 37%/20% tax; TLT / GLD spliced onto a Treasury fund / gold futures before they existed) $100,000 grew to about $58.9M after tax vs $5.17M for Boost 100%: 42.9% a year before tax (27.0% after) vs 24.5% (15.9%), worst drop −34% vs −63%; from 2010 45.6% vs 26.2%, from 2016 54.6%, from 2020 80.5% vs 53.3% (all with the surge exit below, the whipsaw switch with its rate/gold regime, TLT / GLD picked by their 6-month gain, the narrow-market cash week, the lower-high exit into gold or bonds on both its triggers, no T-bills (gold or bonds by their 3-month gain, else DBMF managed futures), the rebound rule and the fading-energy filter, whose skipped stocks the whipsaw check counts as if bought, and the whole account in the whipsaw switch’s asset; with plain cash instead of DBMF (the default until Oct 20, 2026) 42.4% and $54.9M; with half of it there 42.0% and $53.0M; without the filter 40.6% and $43.4M; without the rebound rule 41.1% and $47.0M; with T-bills 38.8% and $34.4M, worst drop −32%; with plain cash instead of T-bills 38.3% and $32.2M; with one stretch per lower high 37.9% and $30.4M; with T-bills in the lower-high exit 37.5% and $28.9M; without the lower-high exit 36.7% and $26.4M, worst drop −35%. Earlier steps, measured before the rebound rule: without the cash week as well 30.6% and $11.9M; with the old dip add 30.4% and $11.7M, so it was dropped; picking the steepest gradient instead 29.9% and $10.8M, without the regime 29.7% and $10.5M, without the half-switch 29.0% and $9.7M, before the surge exit 27.4% and $7.8M). Corrected Oct 13, 2026: two tickers (EP, CPWR) had been priced with the histories of other companies that reuse the symbols and are now left out, which took about 5 points a year off the 2000 figures. Since Oct 14, 2026 the cash week reads the equal-weight index from 2003, so the audit includes three 2006–07 cash weeks the first run missed (37.0% before). The thresholds were picked on that same history, so expect less: an overfitting test across 599 tested versions (run before the lower-high exit was added) puts a realistic plan at about 18–25% a year before tax. The 6-month pick also did better than the gradient pick when replayed in Japan, the UK, Germany, India and Hong Kong (UK 13.1% vs 11.2% a year).' +
      (RT.log && RT.log.length ? '<br><b>Switch log</b> (newest first): ' + RT.log.map(function (r) { return fmtDate(r[0], { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' + esc(rotName(r[1])) + ' → <b>' + esc(rotName(r[2])) + '</b> <span class="muted">(' + esc(why[r[3]] || r[3] || '') + ')</span>'; }).join(' · ') + '. ' : '') + whipNote(RT) + narrowNote(RT) + lowerhighNote(RT) + noBillsNote(RT) + reboundNote(RT) + pricebreakNote(RT);
  }
  function fadeNote(A) {   // the fading-energy filter on new buys (rule 8)
    var X = A && A.boostx, F = X && X.fade;
    if (!F) return '';
    var sk = F.skipped || [];
    var now = sk.length ? '<b>now: ' + sk.map(function (s) { return esc(s.t) + ' (#' + s.rank + ', volume ' + Math.round(s.vol * 100) + '%, swings ' + Math.round(s.swing * 100) + '%)'; }).join(', ') + ' not bought, ' + (sk.length === 1 ? 'its slot' : 'their slots') + ' in cash</b>'
      : 'none of the top 5 is fading now';
    return '<br><span class="' + (sk.length ? 'pos' : 'muted') + '"><b>8. Fading-energy filter</b> (default since Oct 16, 2026, on probation): ' + now + '.</span>' +
      '<span class="muted"> A top-5 stock isn’t bought while its trading volume over the last month is under ' + Math.round(F.vol * 100) + '% of the 5 months before and its daily swings are under ' + Math.round(F.swing * 100) + '% of its normal: a run that has gone quiet. Its slot stays in cash, not the next-ranked stock, until it drops out of the top 5 or picks up again; a stock already held is kept. ' +
      'In a study of the plan’s 1,384 buys since 2000, quiet picks trailed SPY by 10%+ about twice as often as the rest; skipping them for the next-ranked stock did not help (37.6% vs 37.8% a year), leaving the slot in cash did. ' +
      'The whipsaw switch reads the same list with the filter off: a skipped stock counts as if it had been bought and later sold, and an empty slot is never a sale, so the filter changes which stocks are bought, never when the switch steps out (counting the empty slot as a sale that did not lose had kept the switch off through most of the 2020 crash in a backtest started that January: −40% instead of −27%). ' +
      'In the audit the plan made 42.9% a year from 2000 vs 40.6% without it (after tax 27.0% vs 25.6%; worst drop −34% either way), 45.6% vs 43.4% from 2010, 54.6% vs 51.9% from 2016 and 80.5% vs 77.5% from 2020 (−23% either way). ' +
      'It did better in 7 of 10 separate test periods (worse in 2010–2013) and with every volume threshold from 60% to 100%, but did nothing in Japan, the UK, Germany, India and Hong Kong, and month by month the gain is not proven once the ~55 versions tried that day are counted, so treat it as on probation. You-2 applies it to your stocks too.</span>';
  }
  function bxNote(A) {   // the blow-off exit line under Boost 100% / Boost + cushion
    var X = A && A.boostx, m = X ? X.mult : 2;
    if (!X) return '';
    var on = (X.armed ? 'It is <b>on</b> now: SPY ' : 'It is <b>off</b> now: SPY ') + X.spy.toFixed(2) + ' vs its ' + X.ma + '-day average ' + X.spyMa.toFixed(2) + (X.since ? ' (' + (X.armed ? 'below' : 'above') + ' since ' + esc(X.since) + ')' : '') + (X.armed ? '.' : ', so holdings are kept through blow-offs.');
    return '<br><span class="muted">Blow-off exit: a holding is sold when its last month’s gain is more than ' + m + '× its gain over the 5 months before (it tends to give that back), and the slot goes to the next-ranked stock; it can come back after 4 weeks. ' +
      'It is switched on only in a weak market: while SPY closes below its ' + X.ma + '-day average (on in ' + X.armedWeeks + (A.cushion ? ' of ' + A.cushion.weeks : '') + ' weeks since ' + SINCE + '). In weak markets and rebounds, blow-offs fade; in steady uptrends selling them cost money. ' + on +
      ' Each holding now (last month ÷ prior 5 months, sells at ' + m + (X.armed ? '' : ' when on') + '): ' + X.holdings.map(function (t) { var r = X.ratio[t]; return esc(t) + ' ' + (r == null ? '–' : r.toFixed(2)); }).join(' · ') +
      (X.blown.length ? ' · this week it sells <b>' + X.blown.map(esc).join(', ') + '</b> on the exit' : '') + '.</span>' + surgeNote(X) + callNote(X);
  }
  function surgeNote(X) {   // the surge exit: a 5%+ up day on 4x+ volume -> sold a week later
    var G = X && X.surge;
    if (!G) return '';
    var md = { month: 'short', day: 'numeric' }, wd = { weekday: 'short', month: 'short', day: 'numeric' };
    function ev(e) { return esc(e.t) + ' ' + fmtDate(e.d, md) + ' (' + pct(e.up, 0) + ' on ' + e.x.toFixed(1) + '× volume)'; }
    var pend = (G.pending || []).map(function (e) { return '<b>' + ev(e) + ' → sells at the close on ' + fmtDate(e.sell, wd) + '</b>'; });
    return '<br><span class="muted">Surge exit (always on): a holding that closes ' + Math.round(G.up * 100) + '%+ up on at least ' + G.vol + '× its 50-day average volume is sold at the close ' + (G.delay + 1) +
      ' trading days later (decided ' + G.delay + ' sessions after the surge day), and the slot goes to the next-ranked stock. In the 2000–2026 audit it added about 1.6 points a year before tax (29.0% vs 27.4%; 2000–2024 alone 24.1% vs 23.2%; corrected data); ' +
      'selling the same day sold too early (2020), waiting 2–3 weeks gave the gain back. ' +
      (pend.length ? 'Scheduled: ' + pend.join(' · ') + '. ' : 'Nothing scheduled now. ') +
      (X.surged && X.surged.length ? 'Sold on it at this close: <b>' + X.surged.map(esc).join(', ') + '</b>. ' : '') +
      (G.log && G.log.length ? 'Recent surges while held: ' + G.log.slice(0, 6).map(ev).join(' · ') + '.' : '') + '</span>';
  }
  function callNote(X) {   // optional call sleeve: best-case pricing only, ~10% of the account split across the calls held
    var C = X.calls || {}, ts = X.holdings.filter(function (t) { return C[t]; });
    if (!ts.length) return '';
    var mo = function (d) { return fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' }); };
    var bud = Math.round((X.callBudget || 0.1) * 100), sl = Math.round((X.callSleeve || 0.2) * 100);
    function q(c) {
      var Q = c.quote;
      if (!Q) return ' · live quote: none';
      if (Q.ok == null) return ' · live quote: no bid/ask right now (check at the open)';
      return ' · live: bid ' + Q.bid.toFixed(2) + ' / ask ' + Q.ask.toFixed(2) + ', IV ' + Math.round(Q.iv * 100) + '%, spread ' + Math.round(Q.spread * 100) + '% → ' + (Q.ok ? '<b>best case: yes</b>' : '<b>not best case: skip</b>');
    }
    return '<br><span class="muted"><b>Call sleeve</b> (' + sl + '% of the account; the cash part in T-bills): when a stock enters, buy a ~6-month call 20% above its price, sell it when the plan sells the stock. ' +
      '<b>Only at best-case pricing</b>: implied volatility at or below the max IV shown and bid/ask no wider than ' + Math.round((X.callSpread || 0.04) * 100) + '% of the mid; limit order at the mid, otherwise skip. ' +
      'Size: about ' + bud + '% of the account split across the calls you hold (1 call ' + bud + '%, 2 calls ' + bud / 2 + '% each, 5 calls ' + bud / 5 + '% each). ' +
      ts.map(function (t) { var c = C[t]; return '<b>' + esc(t) + '</b> $' + c.strike + ' call, ' + mo(c.expiry) + ': max $' + c.maxPrice.toFixed(2) + ' ($' + Math.round(c.maxPrice * 100).toLocaleString() + ' a contract), max IV ' + Math.round(c.maxIv * 100) + '%' + q(c); }).join(' · ') +
      '. The max price is modeled from the stock’s own volatility; the live check uses the option chain at the last update.</span>';
  }
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
      (D.signalDay ? '<span>Trade <b>' + fmtDate(D.tradeDate, { weekday: 'short', month: 'short', day: 'numeric' }) + '</b>, 3:30–4:00 pm ET</span>'
        : '<span>Next signal <b>' + fmtDate(D.signalDate, { weekday: 'short', month: 'short', day: 'numeric' }) + '</b> → trade <b>' + fmtDate(D.tradeDate, { weekday: 'short', month: 'short', day: 'numeric' }) + '</b></span>') +
      '<span>Picks from the <b>' + (D.universe.sp || D.universe.total) + '</b> S&amp;P 500 stocks</span>' +
      marketPill() +
      (D.nextUpdateBy && Date.now() > Date.parse(D.nextUpdateBy) ? '<div class="data-issues neg" role="alert"><b>Not updated:</b> this page is from ' + fmtDate(D.asOf) +
        '’s close and the next nightly run is overdue (it failed, or GitHub skipped or paused it). Don’t trade on it until it updates; see Issues at the bottom.</div>' : '') +
      ((D.dataIssues || []).length ? '<div class="data-issues neg" role="alert"><b>Data problem:</b> ' + D.dataIssues.map(esc).join(' ') + '</div>' : '');
  }
  // market phase: bull run / correction / bear market (information only; no rule reads it)
  function marketPill() {
    var M = D.market; if (!M || !M.phase) return '';
    var tone = { 'bull run': 'pos', 'new bull run': 'pos', 'correction': 'warn', 'recovering': 'warn', 'bear market': 'neg' }[M.phase] || '';
    var name = M.phase.charAt(0).toUpperCase() + M.phase.slice(1);
    var bull = M.phase === 'bull run' || M.phase === 'new bull run';
    var tip = bull ? 'SPY ' + (M.dd < -0.0005 ? Math.abs(M.dd * 100).toFixed(1) + '% below its high, ' : 'at its high, ') + 'up ' + Math.round(M.up * 100) + '% from that bear-market low'
      : M.phase === 'correction' ? 'SPY ' + Math.abs(M.dd * 100).toFixed(1) + '% below its ' + fmtDate(M.high) + ' high'
      : 'SPY ' + Math.abs(M.dd * 100).toFixed(1) + '% below its ' + fmtDate(M.high) + ' high, up ' + Math.round(M.up * 100) + '% from its ' + fmtDate(M.low) + ' low';
    var since = M.since ? ' since <b>' + fmtDate(M.since, { month: 'short', day: 'numeric', year: 'numeric' }) + '</b>' : '';
    var signs = (M.signs || []).length ? '<div class="market-signs"><b>Early signs of a bottom</b> (information only; in backtests they also fired in bear-market rallies): ' +
      M.signs.map(function (x) { return esc(x.what) + ' (' + fmtDate(x.d, { month: 'short', day: 'numeric' }) + ')'; }).join('; ') + '</div>' : '';
    return '<span title="' + esc('Bear market: SPY 20%+ below its high. New bull run: up 20% from a bear-market low, until a new high. Correction: 10-20% below the high. Information only; the plan does not use it.') + '">Market <b class="' + tone + '">' + name + '</b>' + since + ' · ' + tip + '</span>' + signs;
  }
  meta(); setInterval(meta, 60000);
  $('gen').textContent = 'built ' + gen.toLocaleString();
  if (TRK && TRK.end) $('trk-end').textContent = fmtDate(TRK.end);

  // rebalance banner
  var ch = D.changes;
  var SLb = D.sleeve, md = { month: 'short', day: 'numeric' }, wd = { weekday: 'short', month: 'short', day: 'numeric' };
  var tags = ch.sell.map(function (t) { return '<span class="tag sell">sell ' + esc(t) + '</span>'; }).join('') +
    ch.buy.map(function (t) { return '<span class="tag buy">buy ' + esc(t) + '</span>'; }).join('');
  if (D.signalDay) {
    var PA = D.plan && D.plan.auto, pm = (D.plan && D.plan['default']) || 'auto';
    try { pm = localStorage.getItem('nibii-plan-mix5') || pm; } catch (e) {}
    var BO = PA && PA.boost, BXb = PA && (PA.boostx || PA.boost);
    var PM = PA && (pm === 'steps' ? PA.steps : pm === 'boost' ? BO : pm === 'auto' || pm === 'guard' ? PA : null);
    var mixTag = PM && PM.split !== PM.prevSplit ? '<span class="tag ' + (PM.split === '100/0' ? 'buy' : 'sell') + '">' + (pm === 'steps' ? 'steps' : 'auto') + ' mix → ' + PM.split + '</span>' : '';
    if (pm === 'boost100' || pm === 'rotation') mixTag = '';
    var CUb = PA && PA.cushion;
    if (pm === 'cushion') mixTag = CUb && CUb.split !== CUb.prevSplit ? '<span class="tag ' + (CUb.split === '100/0' ? 'buy' : 'sell') + '">cushion → ' + CUb.split + '</span>' : '';
    if ((pm === 'boost' || pm === 'boost100' || pm === 'cushion' || pm === 'rotation') && BO) {   // the boosted rules trade their own lists
      var BL = pm === 'boost' ? BO : BXb;
      tags = BL.sell.map(function (t) { return '<span class="tag sell">sell ' + esc(t) + ((BL.blown || []).indexOf(t) >= 0 ? ' (blow-off exit)' : (BL.surged || []).indexOf(t) >= 0 ? ' (surge exit)' : '') + '</span>'; }).join('') +
        BL.buy.map(function (t) { return '<span class="tag buy">buy ' + esc(t) + (BL.boosted.indexOf(t) >= 0 ? ' (news boost)' : '') + '</span>'; }).join('');
    }
    var RTb = PA && PA.rotation;
    if (pm === 'rotation' && RTb && RTb.mode !== 'boost') tags = '<span class="muted">Boost + rotation is out of stocks (' + esc(RTb.mode) + '): the stock list changes don’t apply.</span>';
    if (pm === 'rotation' && RTb && (RTb.trade || (RTb.whip && RTb.whip.trade))) mixTag = rotTag(RTb);
    if (RTb && RTb.rsiWarn && RTb.rsiWarn.on) mixTag += '<span class="tag sell">RSI support-line break (info only)</span>';
    if (RTb && RTb.trendWatch && RTb.trendWatch.on) mixTag += '<span class="tag sell">SPY broke its trendline (info only)</span>';
    if (RTb && RTb.chop && RTb.chop.on) mixTag += '<span class="tag sell">choppy market: the plan is whipsawing (info only)</span>';
    if ((pm === 'boost100' || pm === 'cushion' || pm === 'rotation') && BXb && BXb.surge && !(pm === 'rotation' && RTb && RTb.mode !== 'boost'))
      (BXb.surge.pending || []).forEach(function (e) { mixTag += '<span class="tag sell">' + esc(e.t) + ' sells ' + fmtDate(e.sell, { weekday: 'short', month: 'short', day: 'numeric' }) + ' (surge exit)</span>'; });
    if (RTb && RTb.warn) mixTag += '<span class="tag sell">downtrend warning: SPY below its 150-day, ' + esc(RTb.warn) + ' rising (info only)</span>';
    var GD = PA && PA.guard;
    if (pm === 'guard' && GD && GD.bear !== GD.prevBear) mixTag += '<span class="tag ' + (GD.bear ? 'sell' : 'buy') + '">bear guard ' + (GD.bear ? 'ON → ' + Math.round(GD.share * 100) + '% of stocks into SPY' : 'OFF → back to the top 5') + '</span>';
    var sw = SLb && SLb.held !== SLb.prevHeld ? '<span class="tag sell">sell ' + esc(SLb.prevHeld) + '</span><span class="tag buy">buy ' + esc(SLb.held) + ' (sleeve)</span>' : '';
    $('banner').innerHTML = '<b>Trade Mon ' + fmtDate(D.tradeDate, md) + ', 3:30–4:00 pm ET</b><span class="muted">signal from ' + fmtDate(D.asOf, wd) + '’s close:</span>' +
      (tags || sw || mixTag ? tags + sw + mixTag : '<span>No stock, sleeve or mix changes — just reset to your mix.</span>') + callWhy(pm);
  } else {
    var RTm = D.plan && D.plan.auto && D.plan.auto.rotation, pm2 = (D.plan && D.plan['default']) || 'auto';
    try { pm2 = localStorage.getItem('nibii-plan-mix5') || pm2; } catch (e) {}
    $('banner').innerHTML = (RTm && RTm.rsiWarn && RTm.rsiWarn.on ? '<span class="tag sell">RSI support-line break, SPY near or below its 150-day (info only)</span>' : '') + (RTm && RTm.trendWatch && RTm.trendWatch.on ? '<span class="tag sell">SPY closed under its rising trendline (info only)</span>' : '') + (RTm && RTm.chop && RTm.chop.on ? '<span class="tag sell">choppy-market watch ON: the plan moved ' + RTm.chop.n + ' times in ' + RTm.chop.look + ' sessions (info only)</span>' : '') + (RTm && RTm.warn ? '<span class="tag sell">downtrend warning: SPY below its 150-day in a daily downtrend, ' + esc(RTm.warn) + ' rising (info only)</span>' : '') + (pm2 === 'rotation' && RTm && (RTm.trade || (RTm.whip && RTm.whip.trade)) ? '<b>Boost + rotation — trade at the close ' + fmtDate(RTm.trade || RTm.whip.trade, wd) + ':</b>' + rotTag(RTm) + '<br>' : '') + (tags ? '<b>Preview — if Friday’s signal were ' + fmtDate(D.asOf, wd) + '’s close:</b>' + tags
        : '<b>No changes so far</b><span class="muted">At ' + fmtDate(D.asOf, wd) + '’s close all five holdings still rank in the top ' + D.rule.keepRank + '.</span>') +
      '<span class="muted">Signal Fri ' + fmtDate(D.signalDate, md) + ' → trade Mon ' + fmtDate(D.tradeDate, md) + ' before the close.</span>' + callWhy(pm2);
  }

  // a small line chart for the You-2 and paper records: every line ends in a label (a colour swatch, its name and its value in $)
  // and the labels are pushed apart so none overprint, with room on the right for the longest; a dashed line marks the $100 start
  function miniLines(ser, label) {
    var all = []; ser.forEach(function (x) { x[1].forEach(function (p) { all.push(p[1]); }); });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), W = 600, H = 200, R = 210, FS = 13;
    if (hi - lo < 0.004) { lo -= 0.002; hi += 0.002; }
    var xs = function (i, len) { return (i / Math.max(1, len - 1)) * (W - R - 8) + 4; }, ys = function (v) { return H - 20 - (v - lo) / ((hi - lo) || 1) * (H - 40); };
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(label) + '">', labs = [];
    if (lo <= 1 && hi >= 1) svg += '<line x1="4" x2="' + (W - R - 4) + '" y1="' + ys(1).toFixed(1) + '" y2="' + ys(1).toFixed(1) + '" style="stroke:var(--muted);stroke-width:1;stroke-dasharray:3 4;opacity:.6"/>' +
      '<text x="4" y="' + (ys(1) - 4).toFixed(1) + '" font-size="11" style="fill:var(--muted)">$100</text>';
    // drawn back to front: the first line (yours) sits on top as a thin line, the others are wider and fainter underneath so a line that
    // matches yours exactly (You-2 and the default plan hold the same stocks) still shows
    ser.slice().reverse().forEach(function (x, ri) {
      if (!x[1].length) return;
      var top = ri === ser.length - 1;
      svg += '<polyline style="fill:none;stroke:' + x[2] + ';stroke-width:' + (top ? 2 : 4.5) + ';opacity:' + (top ? 1 : 0.55) + '" points="' + x[1].map(function (p, i) { return xs(i, x[1].length).toFixed(1) + ',' + ys(p[1]).toFixed(1); }).join(' ') + '"/>';
      var lp = x[1][x[1].length - 1], ex = xs(x[1].length - 1, x[1].length);
      svg += '<circle cx="' + ex.toFixed(1) + '" cy="' + ys(lp[1]).toFixed(1) + '" r="3.5" style="fill:' + x[2] + '"/>';
      labs.push({ y: ys(lp[1]), x: ex, name: x[0], v: '$' + (lp[1] * 100).toFixed(1), c: x[2] });
    });
    labs.sort(function (a, b) { return a.y - b.y; });
    for (var i = 0; i < labs.length; i++) { labs[i].y = Math.max(labs[i].y, FS); if (i && labs[i].y - labs[i - 1].y < FS + 3) labs[i].y = labs[i - 1].y + FS + 3; }
    for (var j = labs.length - 1; j >= 0; j--) { labs[j].y = Math.min(labs[j].y, H - 4 - (labs.length - 1 - j) * (FS + 3)); }
    labs.forEach(function (l) {
      svg += '<rect x="' + (l.x + 9).toFixed(1) + '" y="' + (l.y - 8).toFixed(1) + '" width="10" height="4" rx="2" style="fill:' + l.c + '"/>' +
        '<text x="' + (l.x + 24).toFixed(1) + '" y="' + (l.y + 1).toFixed(1) + '" font-size="' + FS + '" style="fill:var(--ink)"><tspan>' + esc(l.name) + '</tspan><tspan dx="6" font-weight="600">' + l.v + '</tspan></text>';
    });
    return svg + '</svg>';
  }

  // You-2: your stocks, the default plan's timing (mtl/you2.py; docs/my_calls.json "you2")
  (function () {
    if (!$('you2')) return;
    var Y = D.plan && D.plan.you2, inp = $('y2-in'), sub = $('y2-submit');
    var hn = { stocks: 'your stocks', cash: 'cash', CASH: 'cash', DBMF: 'DBMF (managed futures)', TLT: 'TLT (Treasuries)', GLD: 'GLD (gold)', BIL: 'T-bills' };
    function hname(h) { if (!h) return '–'; if (h.indexOf('stocks+') === 0) return 'half your stocks, half ' + (hn[h.slice(7)] || h.slice(7)); return hn[h] || h; }
    function today() { try { return new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' }); } catch (e) { return new Date().toISOString().slice(0, 10); } }
    function tickers() { return (inp.value || '').toUpperCase().split(/[\s,;]+/).filter(function (t) { return /^[A-Z][A-Z0-9.\-]{0,9}$/.test(t); }).filter(function (t, i, a) { return a.indexOf(t) === i; }).slice(0, 10); }
    function update() {
      var t = tickers(), day = today();
      var block = {}; block[day] = { stocks: t, note: '', at: new Date().toISOString() };
      var body = 'You-2 list from the Top 5 dashboard. Leave the block below as-is: the Calls intake workflow records it in docs/my_calls.json and closes this issue.\n\n```json\n' + JSON.stringify({ you2: block }) + '\n```\n';
      sub.href = 'https://github.com/danreed001-droid/NIBII/issues/new?title=' + encodeURIComponent('calls you2 ' + day) + '&body=' + encodeURIComponent(body);
      var same = Y && (Y.stocks || []).join(',') === t.join(',');
      $('y2-status').textContent = !t.length ? 'Enter at least one ticker' : same ? 'Same as your current list' : t.length + ' stock' + (t.length === 1 ? '' : 's') + ': ' + t.join(', ');
      sub.style.pointerEvents = t.length && !same ? '' : 'none';
      sub.style.opacity = t.length && !same ? '' : '0.5';
    }
    if (Y) {
      inp.value = (Y.stocks || []).join(', ');
      var n = (Y.entries || []).length, last = function (c) { return c && c.length ? c[c.length - 1][1] : null; };
      $('y2-sub').textContent = 'Started ' + fmtDate(Y.start, { month: 'short', day: 'numeric', year: 'numeric' }) + ' · ' + n + ' list' + (n === 1 ? '' : 's') + ' so far';
      var yv = last(Y.curve), pv = last(Y.plan), sv = last(Y.spy);
      $('y2-now').innerHTML = '<p>Now holds <b>' + esc(hname(Y.holds)) + '</b>' + (Y.next && Y.next !== Y.holds ? '; after the next close: <b>' + esc(hname(Y.next)) + '</b>' : '') + '. Your list: <b>' + esc((Y.stocks || []).join(', ') || '–') + '</b>.' +
        (Y.missing && Y.missing.length ? ' <span class="neg">No price for ' + esc(Y.missing.join(', ')) + ': check the ticker.</span>' : '') +
        (yv != null ? ' Since the start: You-2 ' + pct(yv - 1) + ', the default plan ' + pct(pv != null ? pv - 1 : null) + ', SPY ' + pct(sv != null ? sv - 1 : null) + '.' : '') + '</p>';
      var C = Y.curve || [];
      if (C.length < 2) $('y2-chart').innerHTML = '<p class="note">The chart starts after the first closes.</p>';
      else {
        $('y2-chart').innerHTML = miniLines([['You-2', C, 'var(--s-ccalls)'], ['Default plan', Y.plan || [], 'var(--s-rot)'], ['SPY', Y.spy || [], 'var(--s-spy)']], 'You-2 vs the default plan and SPY since the start');
      }
      $('y2-log').innerHTML = 'Your lists: ' + (Y.entries || []).map(function (e) { return fmtDate(e[0], { month: 'short', day: 'numeric', year: 'numeric' }) + ': ' + esc(e[1].join(', ')); }).join(' · ');
    }
    inp.addEventListener('input', update);
    update();
  })();

  // Paper record: the default plan's frozen, time-stamped forward test (mtl/paper.py; data/paper_ledger.json)
  (function () {
    var P = D.plan && D.plan.paper;
    if (!P || !$('paper')) return;
    var md = { month: 'short', day: 'numeric', year: 'numeric' };
    var hn = { CASH: 'cash', DBMF: 'DBMF (managed futures)', TLT: 'TLT (Treasuries)', GLD: 'GLD (gold)', SPY: 'SPY', BIL: 'T-bills' };
    function what(e) {
      if (!e) return '–';
      if (e.mode !== 'boost') return hn[e.mode] || e.mode;
      var cash = e.w && e.w.CASH ? ' + ' + Math.round(e.w.CASH * 100) + '% cash' : '';
      return (e.half ? 'half in ' + (hn[e.half] || e.half) + ', half in ' : '') + (e.list || []).join(', ') + cash;
    }
    var fr = P.frozen || {}, ch = (P.rulesChanged || [])[0], up = (P.updates || [])[(P.updates || []).length - 1];
    $('pp-sub').textContent = 'Started ' + fmtDate(P.start, md) + ' · ' + P.entries + ' decision' + (P.entries === 1 ? '' : 's') + ' logged · ' +
      (ch ? 'rule code changed on ' + fmtDate(ch, md) + ' without an update note'
        : up ? 'rules updated on ' + fmtDate(up.since, md) + ': ' + up.what
        : 'rules unchanged since ' + fmtDate(fr.since || P.start, md)) + ' (fingerprint ' + ((up || fr).fingerprint || '').slice(0, 8) + ')';
    var S = P.status || {}, html = '<p>';
    html += 'Latest decision, for the next close: <b>' + esc(what(P.tonight)) + '</b>. ';
    if (S.sessions > 0) html += 'Over ' + S.sessions + ' session' + (S.sessions === 1 ? '' : 's') + ': paper record <b>' + pct(S.ret) + '</b>, SPY ' + pct(S.spy) + ', worst drop ' + pct(S.dd) + '. ';
    else html += 'The record starts with the first fill. ';
    html += (S.band ? 'Judged on the ' + P.bands[String(S.band)].label + ' range. ' : 'Too early to judge against the ranges (3 months at the earliest). ');
    html += (S.flags && S.flags.length) ? '<span class="neg">Warning: ' + esc(S.flags.join('; ')) + '.</span> ' : '<span class="pos">No warnings.</span> ';
    html += P.checked ? (P.diffs && P.diffs.length
      ? '<span class="neg">Replay check: ' + P.diffs.length + ' of ' + P.checked + ' logged days differ: ' + esc(P.diffs.map(function (x) { return x.d + ' (' + x.what + ')'; }).join('; ')) + '.</span>'
      : (P.checked === 1 ? 'Replay check: the logged day matches.' : 'Replay check: all ' + P.checked + ' logged days match.'))
      : 'Replay check: starts once a logged day has passed.';
    $('pp-now').innerHTML = html + '</p>';
    var C = P.curve || [], Sp = P.spy || [];
    if (C.length < 2) $('pp-chart').innerHTML = '<p class="note">The chart starts after the first closes.</p>';
    else {
      $('pp-chart').innerHTML = miniLines([['Paper record', C, 'var(--s-rot)'], ['SPY', Sp, 'var(--s-spy)']], 'Paper record vs SPY since the start');
    }
    var B = P.bands || {}, rows = '<thead><tr><th class="l">After</th><th>1 in 20 bad</th><th>Typical</th><th>Beat SPY</th><th>Typical drop</th></tr></thead><tbody>';
    Object.keys(B).sort(function (a, b) { return a - b; }).forEach(function (h) {
      var b = B[h], on = String(S.band) === h;
      rows += '<tr' + (on ? ' style="font-weight:600"' : '') + '><td class="l">' + esc(b.label) + (on ? ' (now)' : '') + '</td><td>' + pct(b.p5) + '</td><td>' + pct(b.p50) + '</td><td>' + Math.round(b.ahead * 100) + '%</td><td>' + pct(b.dd50, 0) + '</td></tr>';
    });
    $('pp-bands').innerHTML = rows + '</tbody>';
    $('pp-log').innerHTML = '<p class="note">Warning signs: the latest 3, 6 or 12 months (the longest reached) below the 1-in-20 floor for that length, trailing SPY by more than the 1-in-10 margin, or a drop deeper than the backtest’s worst (' + pct(P.worstDD, 0) + '). Trailing SPY in a single year is not one: the backtest did that 1 year in 5.</p>' +
      '<p class="note">Latest decisions: ' + (P.last || []).map(function (e) {
        var t = e.at ? new Date(e.at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET' : '';
        return fmtDate(e.d, { month: 'short', day: 'numeric' }) + ': ' + esc(what(e)) + (t ? ' <span class="muted">(logged ' + esc(t) + ')</span>' : '');
      }).join(' · ') + '</p>';
  })();

  function spark(vals, w, h) {
    if (!vals || vals.length < 2) return '';
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), n = vals.length;
    var d = vals.map(function (v, i) { return (i ? 'L' : 'M') + (i / (n - 1) * w).toFixed(1) + ' ' + (h - 3 - (v - lo) / (hi - lo || 1) * (h - 6)).toFixed(1); }).join('');
    var c = vals[n - 1] >= vals[0] ? 'var(--pos)' : 'var(--neg)';
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + '" style="stroke:' + c + '" vector-effect="non-scaling-stroke"></path></svg>';
  }

  // holdings
  $('hold-hint').textContent = (D.signalDay ? 'after Monday’s trades · ' : '') + 'equal weight · 6-1m = return from 6 months to 1 month ago';
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
  function revCell(v) {   // analyst estimate revisions: 90-day change in this year's EPS estimate, raised / cut in 30 days
    if (!v) return '<span class="muted">–</span>';
    var a = v.eps90 != null ? '<span class="' + tone(v.eps90) + '">' + pct(v.eps90, Math.abs(v.eps90) < 0.1 ? 1 : 0) + '</span>' : '–';
    var b = v.up30 != null ? '<span class="small muted"> ↑' + v.up30 + ' ↓' + v.down30 + '</span>' : '';
    return '<span style="white-space:nowrap">' + a + b + '</span>';
  }
  $('holdings').innerHTML = D.holdings.slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); }).map(function (h) {
    var tap = h.chart ? ' data-t="' + esc(h.t) + '" tabindex="0" role="button" aria-expanded="false" aria-controls="swpanel" aria-label="' + esc(h.t) + ': show swing chart"' : '';
    return '<article class="hold"' + tap + '><div class="hold-top"><span class="rank">#' + (h.rank || '–') + '</span><span>' + (h.new ? '<span class="tag buy">buy Mon</span> ' : '') + (h.ndx ? '<span class="tag ndx" title="Nasdaq-100 only">NDX</span>' : '') + '</span></div>' +
      '<div><div class="tk">' + esc(h.t) + (h.w ? ' <span class="small muted">' + Math.round(h.w * 100) + '%</span>' : '') + '</div><div class="nm" title="' + esc(h.n) + '">' + esc(h.n) + '</div></div>' +
      '<div><div class="big ' + tone(h.score) + '">' + pct(h.score, 0) + '</div><div class="small">6-1m · ' + pct(h.vsSpy, 0) + ' vs SPY</div></div>' +
      spark(h.spark, 200, 44) +
      '<div class="kv"><span>Held</span><b>' + (h.new ? 'new' : (h.weeks || 0) + ' wk') + '</b><span>Since buy</span><b class="' + tone(h.sinceRet) + '">' + pct(h.sinceRet) + '</b>' +
      '<span>1 month</span><b class="' + tone(h.r1m) + '">' + pct(h.r1m) + '</b><span>Off high</span><b>' + pct(h.offHigh) + '</b>' +
      '<span title="Analysts’ estimate of this year’s earnings: change over 90 days · raised / cut in the last 30 days">Estimates</span><b>' + revCell(h.rev) + '</b></div>' +
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
    var MODES = ['rotation', 'gold', 'bonds', 'mf', 'auto', 'boost', 'boost100', 'cushion', 'steps', 'cash', 'custom', 'del'];
    var WHOLE = { rotation: 5, gold: 6, bonds: 7, mf: 8 };   // whole-account calls: the default plan, 100% GLD, 100% TLT, 100% DBMF (their slot in a mix)
    function clean(c) {
      if (!c || MODES.indexOf(c.m) < 0) return null;
      var cc = { m: c.m, note: String(c.note || '').slice(0, 300), at: String(c.at || '') };
      if (c.m === 'custom') { cc.s = Math.max(0, Math.min(100, Math.round(+c.s || 0))); cc.v = Math.max(0, Math.min(100 - cc.s, Math.round(+c.v || 0))); cc.c = 100 - cc.s - cc.v; }
      var TKR = /^[A-Z][A-Z0-9.\-]{0,9}$/;
      var sw = (Array.isArray(c.swaps) ? c.swaps : []).filter(function (x) { return Array.isArray(x) && TKR.test(x[0]) && TKR.test(x[1]); }).slice(0, 5).map(function (x) { return [x[0], x[1]]; });
      var dr = (Array.isArray(c.drops) ? c.drops : []).filter(function (x) { return TKR.test(x); }).slice(0, 5);
      if (sw.length && !(c.m in WHOLE)) cc.swaps = sw;
      if (dr.length && !(c.m in WHOLE)) cc.drops = dr;
      return cc;
    }
    // swap / drop helpers: candidates are ranks 6-10 that the model doesn't hold
    var MODEL = D.holdings.map(function (h) { return h.t; }), TBL = {};
    D.table.forEach(function (r) { TBL[r.t] = r; });
    D.holdings.forEach(function (h) { if (!TBL[h.t]) TBL[h.t] = h; });
    var BOOSTL = (A_ = D.plan && D.plan.auto && D.plan.auto.boost) ? A_.holdings : MODEL;
    var BOOSTXL = (A_ = D.plan && D.plan.auto && (D.plan.auto.boostx || D.plan.auto.boost)) ? A_.holdings : MODEL;
    if (A_) A_.rows.forEach(function (r) { if (!TBL[r.t]) TBL[r.t] = r; });
    function modelFor(m) { return m === 'boost' ? BOOSTL : m === 'boost100' || m === 'cushion' ? BOOSTXL : MODEL; }
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
          return r.json().then(function (j) { var d = {}; try { d = JSON.parse(b64d(j.content)); } catch (x) {} return { sha: j.sha, calls: (d && d.calls) || {}, warn: (d && d.warn) || null, you2: (d && d.you2) || null }; });
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
                     content: b64e(JSON.stringify(Object.assign({ app: 'nibii-calls', v: 1, calls: calls }, g.warn ? { warn: g.warn } : {}, g.you2 ? { you2: g.you2 } : {}), null, 1) + '\n') };   // keeps the warning calls and You-2
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
    function mixOf(c, fri) {   // -> [stocks, sleeve, cash, boost list, boost 100% list, default plan, GLD, TLT, DBMF] or null
      if (!c) return null;
      var w = WK[fri];
      if (c.m in WHOLE) { var mw = [0, 0, 0, 0, 0, 0, 0, 0, 0]; mw[WHOLE[c.m]] = 1; return mw; }
      if (c.m === 'auto') { var s1 = w ? w[2] : A ? share(A.split) : 1; return [s1, 1 - s1, 0]; }
      if (c.m === 'boost100') return [0, 0, 0, 0, 1];
      if (c.m === 'cushion') { var s5 = w && w[5] != null ? w[5] : A && A.cushion ? share(A.cushion.split) : 1; return [0, 1 - s5, 0, 0, s5]; }
      if (c.m === 'boost') { var s3 = w && w[4] != null ? w[4] : A && A.boost ? share(A.boost.split) : 1; return [0, 1 - s3, 0, s3]; }
      if (c.m === 'steps') { var s2 = w ? w[3] : A && A.steps ? share(A.steps.split) : 1; return [s2, 1 - s2, 0]; }
      if (c.m === 'cash') return [0, 0, 1];
      return [c.s / 100, c.v / 100, c.c / 100];
    }
    function callLabel(c) {
      if (!c) return '—';
      var b = c.m === 'rotation' ? 'Follow the default plan' : c.m === 'gold' ? 'Gold (GLD)' : c.m === 'bonds' ? 'Bonds (TLT)' : c.m === 'mf' ? 'Managed futures (DBMF)' : c.m === 'auto' ? 'Follow Auto' : c.m === 'boost' ? 'Follow Boost' : c.m === 'boost100' ? 'Follow Boost 100%' : c.m === 'cushion' ? 'Follow Boost + cushion' : c.m === 'steps' ? 'Follow Steps' : c.m === 'cash' ? 'No trade (cash)' : 'Custom';
      var x = [];
      (c.swaps || []).forEach(function (s2) { x.push(s2[0] + '→' + s2[1]); });
      (c.drops || []).forEach(function (d2) { x.push('drop ' + d2); });
      return b + (c.m !== 'cash' && !(c.m in WHOLE) && x.length ? ' · ' + x.join(', ') : '');
    }
    function mixTxt(m) { if (m[5]) return 'default plan'; if (m[6]) return '100% gold'; if (m[7]) return '100% bonds'; if (m[8]) return '100% managed futures'; return Math.round((m[0] + (m[3] || 0) + (m[4] || 0)) * 100) + '/' + Math.round(m[1] * 100) + (m[2] ? '/' + Math.round(m[2] * 100) : ''); }
    var inForce = A ? A.decided : D.asOf;   // the signal Friday whose trades are (or will be) held now

    var mix = P['default'], acct = 10000;
    try { mix = localStorage.getItem('nibii-plan-mix5') || mix; acct = +(localStorage.getItem('nibii-plan-acct') || acct) || 10000; } catch (e) {}
    if (P.splits.indexOf(mix) < 0) mix = P['default'];
    $('mix-seg').innerHTML = P.splits.map(function (m) { return '<button type="button" data-v="' + m + '">' + (m === 'rotation' ? 'Boost + rotation' : m === 'auto' ? 'Auto' : m === 'boost' ? 'Boost' : m === 'boost100' ? 'Boost 100%' : m === 'cushion' ? 'Boost + cushion' : m === 'guard' ? 'Guard' : m === 'steps' ? 'Steps' : m === 'mine' ? 'Mine' : m) + '</button>'; }).join('');
    function usd(v) { return '$' + (v < 100 ? v.toFixed(2) : Math.round(v).toLocaleString()); }
    var name = {}; SL.assets.forEach(function (a) { name[a.t] = a; });
    function draw() {
      document.querySelectorAll('#mix-seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === mix)); });
      // your call in force ('Mine'): following the default plan shows the plan itself; gold / bonds show that fund
      var mine = mix === 'mine' ? callFor(inForce) : null, MX = mine && mine.m === 'rotation' ? 'rotation' : mix;
      var HV = mine && (mine.m === 'gold' || mine.m === 'bonds' || mine.m === 'mf') ? { gold: 'GLD', bonds: 'TLT', mf: 'DBMF' }[mine.m] : null;
      var m, RT = A && A.rotation, RA = MX === 'rotation' && RT && RT.mode !== 'boost' ? RT.mode : null;
      var WH = MX === 'rotation' && !RA && RT && RT.whip && RT.whip.half ? RT.whip.half : null;   // whipsaw switch asset
      var WP = RT && RT.whip && RT.whip.part != null ? RT.whip.part : 0.5;                          // its share of the account
      if (HV) m = [0, 0, 0];
      else if (MX === 'mine') { m = mixOf(mine, inForce) || [A ? share(A.split) : 1, A ? 1 - share(A.split) : 0, 0]; }
      else if (MX === 'auto' && A) m = [share(A.split), 1 - share(A.split), 0];
      else if (MX === 'guard' && A && A.guard) m = [A.guard.weights[0], A.guard.weights[1], 0, A.guard.weights[2]];
      else if (MX === 'boost' && A && A.boost) m = [share(A.boost.split), 1 - share(A.boost.split), 0];
      else if (MX === 'boost100') m = [1, 0, 0];
      else if (MX === 'rotation') m = RA ? [0, 0, 0] : WH ? [1 - WP, 0, 0] : [1, 0, 0];
      else if (MX === 'cushion' && A && A.cushion) m = [share(A.cushion.split), 1 - share(A.cushion.split), 0];
      else if (MX === 'steps' && A) m = [share(A.steps.split), 1 - share(A.steps.split), 0];
      else m = [share(MX), 1 - share(MX), 0];
      var mineBoost = MX === 'mine' && mine && (mine.m === 'boost' || mine.m === 'boost100' || mine.m === 'cushion');
      if (mineBoost) m = [(m[3] || 0) + (m[4] || 0), m[1], m[2]];
      var spyAmt = acct * (m[3] || 0);
      var stocks = acct * m[0], sleeve = acct * m[1], cash = acct * m[2], per = stocks / D.rule.topN;
      $('plan-hint').textContent = HV ? 'your call: 100% ' + HV + ' (' + (HV === 'GLD' ? 'gold' : HV === 'TLT' ? 'long Treasuries' : 'managed futures') + ') · held until you change your call' : MX === 'rotation' ? (RA ? 'boost + rotation: out of stocks, 100% ' + RA + ' · decided at any close, traded at the next close' : WH ? (WP >= 1 ? 'boost + rotation: whipsaw switch on, 100% ' + WH : 'boost + rotation: whipsaw switch on, ' + Math.round((1 - WP) * 100) + '% the Boost list, ' + Math.round(WP * 100) + '% ' + WH) + ' · decided at any close, traded at the next close' : 'boost + rotation: the Boost 100% list, 100% stocks · decided at any close, traded at the next close') : (MX === 'auto' ? 'auto mix this week: ' : MX === 'boost' ? 'auto + news boost this week: ' : MX === 'boost100' ? 'news boost, always fully in stocks: ' : MX === 'cushion' ? 'boost + cushion this week: ' : MX === 'guard' ? 'auto + guard this week: ' : MX === 'steps' ? 'steps mix this week: ' : MX === 'mine' ? 'your call: ' : '') +
        Math.round(m[0] * 100) + '% top 5 · ' + Math.round(m[1] * 100) + '% sleeve' + (m[3] ? ' · ' + Math.round(m[3] * 100) + '% SPY' : '') + (m[2] ? ' · ' + Math.round(m[2] * 100) + '% cash' : '') + ' · no leverage · trade & reset Mondays';
      var hs = D.holdings.slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); });
      var sp = name[SL.held] || {};
      function sh(v, px) { if (!px) return ''; var n = v / px; return '≈' + n.toFixed(n < 10 ? 2 : 0) + ' sh'; }
      var useX = MX === 'boost100' || MX === 'cushion' || MX === 'rotation' || (mineBoost && (mine.m === 'boost100' || mine.m === 'cushion'));
      var BS = (MX === 'boost' || MX === 'boost100' || MX === 'cushion' || MX === 'rotation' || mineBoost) && A && A.boost ? (useX && A.boostx ? A.boostx : A.boost) : null;
      if (BS) {   // the boosted list: model holdings it keeps first, boosted names in the slots they took
        BS.rows.forEach(function (r) { if (!TBL[r.t]) TBL[r.t] = r; });
        var keepB = hs.filter(function (h) { return BS.holdings.indexOf(h.t) >= 0; }), inB = BS.holdings.filter(function (t) { return !hs.some(function (h) { return h.t === t; }); });
        hs = keepB.concat(hs.filter(function (h) { return BS.holdings.indexOf(h.t) < 0; }));
      }
      var shown = BS ? hs.map(function (h, i) { return i < keepB.length ? h.t : inB[i - keepB.length] || h.t; })
        : MX === 'mine' && mine ? slotsFor(hs.map(function (h) { return h.t; }), mine) : hs.map(function (h) { return h.t; });
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
      if (WH) rows += '<tr><td><span class="sw" style="--c:var(--s-rot)"></span><b>' + esc(WH) + '</b> <span class="muted nm2">' + esc(ROTN[WH] || WH) + ' · whipsaw switch</span></td><td class="r">' + usd(acct * WP) + '</td><td class="r muted">' + sh(acct * WP, WH === 'SPY' ? (A.guard && A.guard.spyClose) : RT.px[WH]) + '</td></tr>';
      if (RA) rows = '<tr><td><span class="sw" style="--c:var(--s-rot)"></span><b>' + esc(RA) + '</b> <span class="muted nm2">' + esc(ROTN[RA] || '') + ' · Boost + rotation is out of stocks</span></td><td class="r">' + usd(acct) + '</td><td class="r muted">' + sh(acct, RT.px[RA]) + '</td></tr>';
      if (HV) rows = '<tr><td><span class="sw" style="--c:var(--s-rot)"></span><b>' + HV + '</b> <span class="muted nm2">' + esc(ROTN[HV] || '') + ' · your call</span></td><td class="r">' + usd(acct) + '</td><td class="r muted">' + sh(acct, RT && RT.px ? RT.px[HV] : null) + '</td></tr>';
      rows += '<tr class="sum"><td>Total</td><td class="r">' + usd(acct) + '</td><td></td></tr>';
      $('alloc').innerHTML = '<tbody>' + rows + '</tbody>';
      var bk = { rotation: 'rotation', boost100: 'boost100' }[MX], bs = bk ? bt(bk) : null, t5b = bt('strategy');
      $('plan-stats').innerHTML = (bs ? '<span>Backtest since ' + TSINCE + ' (stocks in the S&amp;P 500 at the time): <b class="pos">' + pct(bs.annual, 1) + '</b> a year, worst drop <b class="neg">' + pct(bs.maxDD, 0) + '</b></span>'
          : MX === 'mine' ? '<span>Your record is scored below, from your first call.</span>'
          : '<span>No point-in-time backtest of this mix, so no track record is shown for it (a replay with today’s index members would flatter it).</span>') +
        (t5b ? '<span class="muted">Top 5 basic rule, same backtest: ' + pct(t5b.annual, 1) + ' a year, worst drop ' + pct(t5b.maxDD, 0) + '</span>' : '');
      if (MX === 'mine') {
        $('auto-note').innerHTML = mine ? '<b>Mine:</b> your call in force — ' + callLabel(mine) + ' → <b>' + mixTxt(m) + '</b>' + (mine.note ? ' · “' + esc(mine.note) + '”' : '') + '. Change it under Your calls.'
          : '<b>Mine:</b> no call yet, so this shows Auto. Make one under Your calls.';
      } else if (A && MX === 'rotation' && RT) {
        $('auto-note').innerHTML = (mix === 'mine' ? '<b>Mine:</b> your call in force — Follow the default plan' + (mine.note ? ' · “' + esc(mine.note) + '”' : '') + '. Change it under Your calls.<br>' : '') + rotNote(RT, P) + warnNote(RT) + bxNote(A) + fadeNote(A);
      } else if (A && MX === 'cushion' && A.cushion) {
        var CU = A.cushion;
        var crOk = CU.credit == null || CU.credit < 0, crTxt = function (v) { return v == null ? 'no data' : pct(v); };
        $('auto-note').innerHTML = '<b>Boost + cushion:</b> the Boost stock list, fully in stocks unless two things agree at the Friday close: SPY is below its ' + CU.ma + '-day average <i>and</i> junk bonds (HYG) have lagged quality bonds (LQD) over the last ' + CU.creditLook + ' sessions. Then ' + Math.round((1 - CU.share) * 100) + '% sits in the sleeve (' + esc(SL.held) + ') and ' + Math.round(CU.share * 100) + '% in the stocks. ' +
          (D.signalDay ? 'This Friday: SPY ' : 'Last Friday: SPY ') + pct(CU.spyGap) + ' vs its ' + CU.ma + '-day average, junk vs quality bonds ' + crTxt(CU.credit) + ' → <b>' + CU.split + '</b>' + (D.signalDay && CU.split !== CU.prevSplit ? ' (was ' + CU.prevSplit + ' — trade it Monday)' : '') + '.' +
          (CU.spyGap != null && CU.spyGap < 0 && !crOk ? ' SPY is below its average but credit is calm, so the cushion stays off (a likely false alarm).' : '') +
          (!D.signalDay && CU.previewSplit !== CU.split ? ' If Friday were today it would be ' + CU.previewSplit + ' (SPY ' + pct(CU.previewSpyGap) + ' vs its average, junk vs quality ' + crTxt(CU.previewCredit) + ').' : '') +
          ' The cushion was on in ' + CU.weeksLow + ' of ' + CU.weeks + ' weeks since ' + SINCE + (CU.weeksSpyLow != null ? ' (SPY alone was below its average in ' + CU.weeksSpyLow + ')' : '') + '. ' +
          'In the 2000–2026 audit (stocks in the S&amp;P 500 at the time, 0.15% slippage, 37%/20% tax) $100,000 grew to about $4.49M after tax (worst drop −59% before tax), vs $5.17M and −63% for Boost 100% (both with the surge exit; $3.80M and $4.36M before it) and $3.62M for the old SPY-only cushion (corrected data); from 2020 it made 54.2% a year vs 53.3% for Boost 100%, worst drop −34% vs −39%. There is no HYG data before 2007, so before then it is the SPY-only rule.' +
          cushionLog(CU) + bxNote(A);
      } else if (A && MX === 'boost100' && A.boost) {
        $('auto-note').innerHTML = '<b>Boost 100%:</b> the Boost stock list (top 5 + news gaps) with the blow-off and surge exits, always fully in the stocks: no Auto steps into the sleeve when holdings turn down. ' +
          (bt('boost100') ? 'Backtest since ' + TSINCE + ' (stocks in the S&amp;P 500 at the time): ' + pct(bt('boost100').annual, 1) + ' a year, worst drop ' + pct(bt('boost100').maxDD, 0) + '. ' : '') +
          'In the 2000–2026 audit (stocks in the S&amp;P 500 at the time, 0.15% slippage, 37%/20% tax) $100,000 grew to about $5.17M after tax with the blow-off and surge exits ($4.36M before the surge exit, $3.87M with neither; corrected data); ' +
          'the cost is deeper drops: about −66% at the worst after tax. Only follow it if you would hold through a drop like that.' + bxNote(A);
      } else if (A && MX === 'boost' && A.boost) {
        var B = A.boost, gl = B.gaps.length ? B.gaps.map(function (g) { return '<b>' + esc(g.t) + '</b> ' + fmtDate(g.d, md) + (g.held ? ' (held)' : ''); }).join(', ') : 'none';
        $('auto-note').innerHTML = '<b>Auto + News boost:</b> the same top 5, but any stock that gapped up ' + Math.round(B.gap * 100) + '%+ on news (opened and closed ' + Math.round(B.gap * 100) +
          '%+ up, near the day’s high — usually earnings) in the last 4 weeks replaces the weakest holding, even if it isn’t in the top 5 yet; then the Auto mix on top. ' +
          'News gaps in the last 4 weeks: ' + gl + '. ' +
          (B.boosted.length ? 'This week it holds <b>' + B.boosted.map(esc).join(', ') + '</b> instead of ' + B.replaced.map(esc).join(', ') + '. ' : 'This week it holds the same stocks as the plain top 5. ') +
          (D.signalDay ? 'Auto mix ' + B.split + (B.split !== B.prevSplit ? ' (was ' + B.prevSplit + ')' : '') + '. ' : '') +
          'Tested 2000–2026 about +32% a year vs +25%, worst drop −62% vs −73%, and it caught the 2009 rebound (+35% vs −27%). ' +
          'Its list differed from the plain top 5 in ' + B.weeksDiff + ' of ' + A.weeks + ' weeks. Expect fewer real gains than the test: it only knows today’s index members.';
      } else if (A && MX === 'guard' && A.guard) {
        var G = A.guard;
        $('auto-note').innerHTML = '<b>Auto + Guard:</b> the Auto mix, plus a bear-market guard: while SPY closes below its level a year earlier, ' + Math.round(G.share * 100) +
          '% of the stock part sits in SPY instead of the top 5. ' + (D.signalDay ? 'This Friday: ' : 'Last Friday: ') + 'SPY ' + (G.spyNow != null ? G.spyNow.toFixed(2) : '–') + ' vs ' +
          (G.spyYearAgo != null ? G.spyYearAgo.toFixed(2) : '–') + ' a year ago → guard <b>' + (G.bear ? 'ON' : 'off') + '</b>' +
          (D.signalDay && G.bear !== G.prevBear ? ' (changed — trade it Monday)' : '') + '.' + (!D.signalDay && G.previewBear != null && G.previewBear !== G.bear ? ' If Friday were today the guard would turn ' + (G.previewBear ? 'ON' : 'off') + '.' : '') +
          ' It costs a little in good years and pays off in long bear markets: tested 2000–2026, about the same +25% a year with a worst drop near −63% instead of −73%, and 2009 about −5% instead of −27%. On ' + G.weeksBear + ' weeks since ' + SINCE + '.';
      } else if (A && MX === 'steps' && A.steps) {
        var dn2 = A.down.length, lst2 = dn2 ? ' (' + A.down.map(esc).join(', ') + ')' : '', S2 = A.steps;
        $('auto-note').innerHTML = '<b>Steps:</b> 100% top 5 when no holding is in a daily lower-low downtrend at Friday’s close; 1 down → 80/20, 2 down → 60/40, 3 or more → 40/60 (Auto and Boost use these same tiers). ' +
          (D.signalDay ? 'This Friday: ' : 'Last Friday: ') + dn2 + ' of ' + A.checked.length + ' in a downtrend' + lst2 + ' → <b>' + S2.split + '</b>' +
          (D.signalDay && S2.split !== S2.prevSplit ? ' (was ' + S2.prevSplit + ' — change it Monday)' : '') + '.' +
          (!D.signalDay && S2.preview ? ' If Friday were today: ' + A.previewDown.length + ' in a downtrend → ' + S2.preview + '.' : '') +
          ' Since ' + SINCE + ' it was below 100% in ' + S2.weeksLow + ' of ' + A.weeks + ' weeks.';
      } else if (A && MX !== 'auto') {
        $('auto-note').innerHTML = 'Fixed mix: reset to ' + MX + ' every Monday whatever the charts say. Auto and Steps adjust it to how many holdings are in a downtrend.';
      } else if (A) {
        var dn = A.down.length, lst = dn ? ' (' + A.down.map(esc).join(', ') + ')' : '';
        $('auto-note').innerHTML = '<b>Auto:</b> 100% top 5; for each holding in a daily lower-low downtrend at Friday’s close, 20% moves to the sleeve for the week (1 → 80/20, 2 → 60/40, 3+ → 40/60). ' +
          (D.signalDay ? 'This Friday: ' : 'Last Friday: ') + dn + ' of ' + A.checked.length + ' in a downtrend' + lst + ' → <b>' + A.split + '</b>' +
          (D.signalDay && A.split !== A.prevSplit ? ' (was ' + A.prevSplit + ' — change it Monday)' : '') + '.' +
          (!D.signalDay && A.preview ? ' If Friday were today: ' + A.previewDown.length + ' in a downtrend → ' + A.preview + '.' : '') +
          ' Since ' + SINCE + ' it was below 100% in ' + A.weeksLow + ' of ' + A.weeks + ' weeks.';
      }
    }
    $('mix-seg').onclick = function (e) { var b = e.target.closest('button'); if (!b) return; mix = b.getAttribute('data-v'); try { localStorage.setItem('nibii-plan-mix5', mix); } catch (x) {} draw(); };
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
      var col = kind === 'auto' ? 2 : kind === 'boost' ? 4 : kind === 'cushion' ? 5 : 3;
      if (wkNow && wkNow[col] != null) return mixTxt([wkNow[col], 1 - wkNow[col], 0]) + ' this week';
      var pv = A && (kind === 'auto' ? A.preview : kind === 'boost' ? A.boost && A.boost.split : kind === 'cushion' ? A.cushion && A.cushion.previewSplit : A.steps && A.steps.preview);
      return 'set Friday' + (pv ? ' (now ' + pv + ')' : '');
    }
    function planNow() {   // what the default plan holds now (it trades at any close, not just Mondays)
      var R = A && A.rotation;
      if (!R) return 'whatever the default plan holds, trading when it trades';
      var h = R.mode !== 'boost' ? '100% ' + R.mode : R.whip && R.whip.half ? (R.whip.part >= 1 ? '100% ' : Math.round(R.whip.part * 100) + '% ') + R.whip.half : 'the Boost list, 100% stocks';
      return 'now ' + h + ' · trades when the plan does (watch the alerts)';
    }
    var OPTS = [['rotation', 'Follow the default plan', planNow()], ['gold', 'Gold (GLD)', '100% gold this week, whatever the plan holds'], ['bonds', 'Bonds (TLT)', '100% long Treasuries this week, whatever the plan holds'], ['mf', 'Managed futures (DBMF)', '100% DBMF this week (a fund that follows trends in stock, bond, currency and commodity futures), whatever the plan holds'],
                ['boost100', 'Follow Boost 100%', 'Boost list + blow-off exit in weak markets + surge exit, always 100% stocks'], ['cushion', 'Follow Boost + cushion', autoNow('cushion')], ['boost', 'Follow Boost', autoNow('boost')], ['auto', 'Follow Auto', autoNow('auto')], ['steps', 'Follow Steps', autoNow('steps')],
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
      if ($('picks')) { $('picks').hidden = mm === 'cash' || mm in WHOLE; if (pickList !== modelFor(mm)) drawPicks(curCall && curCall.m === mm ? curCall : null); }
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
      box.innerHTML = '<p class="ph">' + (pick === 'boost' || pick === 'boost100' || pick === 'cushion' ? 'Boost list' : 'Stocks') + ' · keep, drop (slot goes to cash), or swap in a top-10 stock not held</p>' + ml.map(function (t) { return TBL[t] || { t: t }; }).sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); }).map(function (h) {
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
      choose(c ? c.m : 'rotation');
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
    // HU.days rows: [date, top 5, sleeve, cash, boost list, boost 100% list, default plan, GLD, TLT, DBMF]; a mix puts the
    // money in those nine series (a missing value falls back as below, so an older build still adds up)
    var FB = [[1], [2], [3], [4, 1], [5, 4, 1], [6, 3], [7, 3], [8, 3], [9, 3]];
    function hv(x, j) { var ch = FB[j]; for (var i = 0; i < ch.length; i++) if (x[ch[i]]) return x[ch[i]]; return 1; }
    function simulate(mixAt, startTrade) {
      var tradeFri = {}; HU.weeks.forEach(function (w) { tradeFri[w[1]] = w[0]; });
      var out = [], u = [0, 0, 0, 0, 0, 0, 0, 0, 0], prev = null;
      HU.days.forEach(function (x) {
        if (x[0] < startTrade) return;
        if (prev) for (var j = 0; j < 9; j++) u[j] *= hv(x, j) / hv(prev, j);
        var nav = prev ? u.reduce(function (s, v) { return s + v; }, 0) : 1;
        if (x[0] in tradeFri) { var mm = mixAt(tradeFri[x[0]]) || [1, 0, 0]; for (var k = 0; k < 9; k++) u[k] = nav * (mm[k] || 0); }
        out.push([x[0], nav]); prev = x;
      });
      return out;
    }
    var RR = { a: '', b: '', all: false };   // all: every week in the table, not just the last REC_WEEKS
    var REC_WEEKS = 8;
    $('rr-from').onchange = function () { RR.a = $('rr-from').value; drawRecord(); };
    $('rr-to').onchange = function () { RR.b = $('rr-to').value; drawRecord(); };
    $('rr-all').onclick = function () { RR.a = RR.b = ''; drawRecord(); };
    function drawRecord() {
      var box = $('rec'), keys = Object.keys(act).sort();
      $('rec-range').hidden = true;
      if (!HU || !HU.days.length) { box.innerHTML = '<p class="muted">Record data is not available in this build.</p>'; return; }
      if (!keys.length) { box.innerHTML = '<p class="swnote">No calls yet. Make your first call on the left — your record starts at that week’s Monday trade and is compared with simply following the default plan, Auto or Steps over the same weeks.</p>'; return; }
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
      var b100 = simulate(function (f) { var w = WK[f]; return w && w[4] != null ? [0, 0, 0, 0, 1] : null; }, start);
      var cu = simulate(function (f) { var w = WK[f]; return w && w[5] != null ? [0, 1 - w[5], 0, 0, w[5]] : null; }, start);
      var dfl = HU.days.length && HU.days[HU.days.length - 1].length > 6 ? simulate(function () { return [0, 0, 0, 0, 0, 1, 0, 0]; }, start) : null;
      // optional From/To filter inside the record
      $('rec-range').hidden = false;
      var ra = RR.a && RR.a > start ? RR.a : start, rb = RR.b && RR.b < lastDay ? RR.b : lastDay;
      if (ra > rb) { var tt = ra; ra = rb; rb = tt; }
      $('rr-from').min = $('rr-to').min = start; $('rr-from').max = $('rr-to').max = lastDay;
      $('rr-from').value = ra; $('rr-to').value = rb;
      function cut(c) { return c.filter(function (p) { return p[0] >= ra && p[0] <= rb; }); }
      me = cut(me); au = cut(au); stp = cut(stp); bst = cut(bst); b100 = cut(b100); cu = cut(cu); if (baseC) baseC = cut(baseC); if (dfl) dfl = cut(dfl);
      if (me.length < 2) { box.innerHTML = '<p class="swnote">Pick a range with at least two trading days between ' + fmtDate(start, md) + ' and ' + fmtDate(lastDay, md) + '.</p>'; return; }
      function tot(c) { return c[c.length - 1][1] / c[0][1] - 1; }
      function dd(c) { var pk = c[0][1], m = 0; c.forEach(function (p) { pk = Math.max(pk, p[1]); m = Math.min(m, p[1] / pk - 1); }); return m; }
      var SER2 = [['You', me, 'var(--gold)']].concat(dfl && dfl.length === me.length ? [['Default plan', dfl, 'var(--s-rot)']] : []).concat([['Boost', bst, 'var(--s-boost)'], ['Boost 100%', b100, 'var(--s-b100)'], ['Cushion', cu, 'var(--s-cush)'], ['Auto', au, 'var(--s-plan)'], ['Steps', stp, 'var(--ink-2)']]);
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
      }).reverse().slice(0, 52);
      var moreW = rowsW.length > REC_WEEKS ? '<p class="swnote" style="margin:6px 0 0"><button type="button" class="linkbtn" id="rr-more">' +
        (RR.all ? 'Show the last ' + REC_WEEKS + ' weeks' : 'Show all ' + rowsW.length + ' weeks') + '</button></p>' : '';
      html += '<table class="wk"><thead><tr><th>Week of</th><th>Your call</th><th class="r hide-xs">Auto mix</th><th class="r">You</th><th class="r">Auto</th></tr></thead><tbody>' +
        (RR.all ? rowsW : rowsW.slice(0, REC_WEEKS)).join('') + '</tbody></table>' + moreW +
        '<p class="swnote">* week still running. Weeks run Monday close to Monday close; cash earns nothing (no T-bills). A call you skip carries the last one forward. The table keeps the last 52 weeks; the totals and chart cover the whole range.</p>';
      box.innerHTML = html;
      if ($('rr-more')) $('rr-more').onclick = function () { RR.all = !RR.all; drawRecord(); };
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
  var TAX = false, YIELD = { SPY: 0.016, QQQ: 0.007, SPMO: 0.01 };
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
  // the default plan's curve (Boost + rotation unless the scan says otherwise)
  var DEFK = ({ auto: 'plan', rotation: 'rotation', boost: 'boost', boost100: 'boost100', cushion: 'cushion', calls: 'calls', cushionCalls: 'cushionCalls' })[(D.plan && D.plan['default']) || 'rotation'] || 'rotation';
  function tile(label, value, sub, cls, wcls) { return '<div class="stat' + (wcls ? ' ' + wcls : '') + '"><span class="stat-label">' + label + '</span><span class="stat-value ' + (cls || '') + '">' + value + '</span><span class="stat-sub">' + sub + '</span></div>'; }
  function drawStats() {
    var t5 = rstat('strategy'), au = rstat('plan'), st = rstat('steps'), sp = rstat('SPY'), qq = rstat('QQQ'), sm = rstat('SPMO'), bo = rstat('boost'), b1 = rstat('boost100'), cs = rstat('cushion'), ro = rstat('rotation'), ca = rstat('calls'), cc = rstat('cushionCalls');
    if (!t5) { $('stats').innerHTML = tile('Range', '–', 'pick at least two trading days', ''); return; }
    function yr(x) { return x && x.ann != null ? pct(x.ann, 0) + ' a year' : 'under a year'; }
    var DEFL = { rotation: 'Boost + rotation', boost100: 'Boost 100%', cushion: 'Boost + cushion', calls: 'Boost 100% + calls', cushionCalls: 'Boost + cushion + calls', plan: 'Auto mix', boost: 'Boost' };
    var one = function (k, x, label) { return x ? tile(label, pct(x.tot, 0), yr(x) + ' · worst ' + pct(x.dd, 0), tone(x.tot)) : ''; };
    var dx = rstat(DEFK);
    $('stats').innerHTML =
      (dx ? tile((DEFL[DEFK] || DEFK) + '<span class="badge-def">default</span>', pct(dx.tot, 0), yr(dx) + ' · worst ' + pct(dx.dd, 0), tone(dx.tot), 'default') : '') +
      tile('Top 5 basic rule', pct(t5.tot, 0), yr(t5), tone(t5.tot)) +
      (bo || au ? tile('Boost / Auto', (bo ? pct(bo.tot, 0) : '–') + ' / ' + (au ? pct(au.tot, 0) : '–'), (bo ? yr(bo) : '') + ' · worst ' + (bo ? pct(bo.dd, 0) : '–') + ' / ' + (au ? pct(au.dd, 0) : '–'), tone(bo && bo.tot)) : '') +
      (DEFK !== 'rotation' ? one('rotation', ro, 'Boost + rotation') : '') +
      (DEFK !== 'boost100' ? one('boost100', b1, 'Boost 100%') : '') +
      (DEFK !== 'cushion' ? one('cushion', cs, 'Boost + cushion') : '') +
      (DEFK !== 'calls' ? one('calls', ca, 'Boost 100% + calls') : '') +
      (DEFK !== 'cushionCalls' ? one('cushionCalls', cc, 'Boost + cushion + calls') : '') +
      tile('SPY / QQQ', pct(sp.tot, 0) + ' / ' + pct(qq.tot, 0), 'worst ' + pct(sp.dd, 0) + ' / ' + pct(qq.dd, 0)) +
      (sm ? tile('SPMO (momentum ETF)', pct(sm.tot, 0), yr(sm) + ' · worst ' + pct(sm.dd, 0) + (view('SPMO')[0][0] > inR(D.curves.strategy)[0][0] ? ' · since ' + fmtDate(view('SPMO')[0][0], { month: 'short', year: 'numeric' }) : ''), tone(sm.tot)) : '') +
      tile('Top 5 basic: worst drop', pct(t5.dd, 0), R.a === ALL0 && R.b === ALL1 ? 'since ' + TSINCE : 'in this range', 'neg');
    $('range-hint').textContent = (TRK ? 'Backtest with the stocks in the S&P 500 at the time' : '$100 in the rule vs buying and holding') + ' · ' + fmtDate(inR(D.curves.strategy)[0][0]) + ' – ' + fmtDate(R.b) +
      (TAX ? ' · after tax: rule 37% on each year’s gains (paid each April), SPY/QQQ/SPMO held, 20% long-term · value if cashed out that day' : ' · before tax');
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
        '<p class="chart-sub">This month ' + sp[0] + '% stocks' +
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
  var SER = [['strategy', 'Top 5 basic rule', 'var(--s-strat)', 'main'], ['QQQ', 'QQQ', 'var(--s-qqq)', ''], ['SPY', 'SPY', 'var(--s-spy)', '']];
  if (D.curves.SPMO) SER.splice(SER.length - 2, 0, ['SPMO', 'SPMO (from Oct 2015)', 'var(--s-spmo)', '']);
  if (D.curves.plan && D.plan) SER.splice(1, 0, ['plan', 'Plan (auto mix)', 'var(--s-plan)', 'main']);
  if (D.curves.boost && D.plan) SER.splice(1, 0, ['boost', 'Plan (boost)', 'var(--s-boost)', 'main']);
  if (D.curves.boost100 && D.plan) SER.splice(2, 0, ['boost100', 'Boost 100%', 'var(--s-b100)', 'main']);
  if (D.curves.cushion && D.plan) SER.splice(3, 0, ['cushion', 'Boost + cushion', 'var(--s-cush)', 'main']);
  if (D.curves.calls && D.plan) SER.splice(3, 0, ['calls', 'Boost 100% + calls', 'var(--s-calls)', 'main']);
  if (D.curves.rotation && D.plan) SER.splice(1, 0, ['rotation', 'Boost + rotation', 'var(--s-rot)', 'main']);
  if (D.curves.cushionCalls && D.plan) SER.splice(6, 0, ['cushionCalls', 'Boost + cushion + calls', 'var(--s-ccalls)', 'main']);
  if (D.curves.monthlyBoost) SER.splice(SER.length - 2, 0, ['monthlyBoost', 'Monthly boost', 'var(--s-monb)', 'main']);
  if (D.curves.monthly) SER.splice(SER.length - 2, 0, ['monthly', 'Monthly auto', 'var(--s-mon)', 'main']);
  // the default plan leads the legend, drawn thickest and labelled as the default
  (function () {
    var i = SER.findIndex(function (x) { return x[0] === DEFK; });
    if (i >= 0) { var d0 = SER.splice(i, 1)[0]; SER.unshift([d0[0], d0[1] + ' (default)', d0[2], 'main default']); }
  })();
  var SIMPLE = [DEFK, 'SPY', 'QQQ'];
  function simpleHide() { var h = {}; SER.forEach(function (x) { if (SIMPLE.indexOf(x[0]) < 0) h[x[0]] = 1; }); return h; }
  var HIDE = null; try { HIDE = JSON.parse(localStorage.getItem('nibii-hide-lines2') || 'null'); } catch (e) {}
  if (!HIDE) HIDE = simpleHide();
  function drawLegend() {
    var simple = SER.every(function (x) { return !HIDE[x[0]] === (SIMPLE.indexOf(x[0]) >= 0); });
    var all = SER.every(function (x) { return !HIDE[x[0]]; });
    $('legend').innerHTML = '<span class="seg" id="lg-preset"><button type="button" data-p="def" aria-pressed="' + String(simple) + '">Default vs SPY &amp; QQQ</button><button type="button" data-p="all" aria-pressed="' + String(all) + '">All mixes</button></span>' +
      SER.map(function (s) { return '<button type="button" class="lg' + (s[0] === DEFK ? ' default' : '') + '" data-k="' + s[0] + '" aria-pressed="' + String(!HIDE[s[0]]) + '"><i class="key" style="--c:' + s[2] + '"></i>' + s[1] + '</button>'; }).join('') +
      '<span class="muted lg-hint">tap a line to hide / show it</span>';
  }
  var scale = 'log';
  try { scale = localStorage.getItem('nibii-mom-scale') || 'log'; } catch (e) {}
  drawLegend();
  $('legend').onclick = function (e) {
    var pb = e.target.closest('#lg-preset button');
    if (pb) { HIDE = pb.getAttribute('data-p') === 'all' ? {} : simpleHide(); try { localStorage.setItem('nibii-hide-lines2', JSON.stringify(HIDE)); } catch (x) {} drawLegend(); drawGrowth(); return; }
    var b = e.target.closest('.lg'); if (!b) return;
    var k = b.getAttribute('data-k'), shownN = SER.filter(function (s) { return !HIDE[s[0]]; }).length;
    if (!HIDE[k] && shownN <= 1) return;   // keep at least one line
    if (HIDE[k]) delete HIDE[k]; else HIDE[k] = 1;
    try { localStorage.setItem('nibii-hide-lines2', JSON.stringify(HIDE)); } catch (x) {}
    drawLegend(); drawGrowth();
  };
  function day(s) { return Date.parse(s + 'T12:00:00Z'); }
  function money(v) { return '$' + (v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(0)); }
  function drawGrowth() {
    document.querySelectorAll('#scale-seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === scale)); });
    var box = $('growth'); box.innerHTML = '';
    // a line that starts later than the range (SPMO) starts at SPY's level that day: SPY until then
    var spyV = view('SPY'), s0 = spyV.length ? spyV[0][0] : '';
    function lift(c) { if (!c.length || !s0 || c[0][0] <= s0) return 1; var q = spyV.filter(function (p) { return p[0] <= c[0][0]; }); return q.length ? q[q.length - 1][1] / spyV[0][1] : 1; }
    var series = SER.filter(function (s) { return !HIDE[s[0]] && view(s[0]).length; }).map(function (s) { var c = view(s[0]), b0 = c.length ? c[0][1] / lift(c) : 1; return { name: s[1], c: s[2], cls: s[3], pts: c.map(function (p) { return [day(p[0]), p[1] / b0 * 100]; }) }; });
    if (!series[0].pts.length) return;
    var W = Math.max(320, box.clientWidth), H = Math.round(Math.min(380, Math.max(240, W * 0.5))), m = { l: 56, r: 64, t: 10, b: 26 };
    var xs = [], ys = [];
    series.forEach(function (s) { s.pts.forEach(function (p) { xs.push(p[0]); ys.push(p[1]); }); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    var log = scale === 'log', f = log ? Math.log : function (v) { return v; };
    var ticks = [];
    if (log) { [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000, 2000000].forEach(function (v) { if (v >= lo * 0.9 && v <= hi * 1.1) ticks.push(v); }); }
    if (!log || ticks.length < 3) { ticks = []; var st = Math.pow(10, Math.floor(Math.log10((hi - lo) / 4))); st = (hi - lo) / st > 20 ? st * 5 : (hi - lo) / st > 8 ? st * 2 : st; for (var v = Math.ceil(lo / st) * st; v <= hi; v += st) ticks.push(v); }
    var y0 = f(Math.min(lo, ticks[0] || lo)), y1 = f(Math.max(hi, ticks[ticks.length - 1] || hi));
    function X(t) { return m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r); }
    function Y(v) { return m.t + (1 - (f(v) - y0) / (y1 - y0 || 1)) * (H - m.t - m.b); }
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Growth of $100' }), g = el('g', { class: 'grid axis' });
    ticks.forEach(function (v) { g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) })); var t = el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }); t.textContent = money(v); g.appendChild(t); });
    if (x1 - x0 > 400 * 864e5) { var ystep = Math.max(1, Math.ceil(40 / ((W - m.l - m.r) / ((x1 - x0) / (365.25 * 864e5))))); for (var yr = new Date(x0).getUTCFullYear() + 1; Date.UTC(yr, 0, 1) <= x1; yr++) { if (yr % ystep) continue; var tx = el('text', { x: X(Date.UTC(yr, 0, 1)), y: H - 6, 'text-anchor': 'middle' }); tx.textContent = yr; g.appendChild(tx); } }
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
  var YK = (D.years.monthly ? ['rotation', 'calls', 'boost100', 'cushionCalls', 'cushion', 'boost', 'plan', 'SPY', 'QQQ', 'SPMO'] : ['strategy', 'rotation', 'calls', 'boost100', 'cushionCalls', 'cushion', 'boost', 'plan', 'SPY', 'QQQ', 'SPMO'])
    .filter(function (k) { return D.years[k]; });
  if (YK.indexOf(DEFK) > 0) { YK.splice(YK.indexOf(DEFK), 1); YK.unshift(DEFK); }
  var YC = { strategy: 'var(--s-strat)', boost: 'var(--s-boost)', boost100: 'var(--s-b100)', cushion: 'var(--s-cush)', plan: 'var(--s-plan)', monthlyBoost: 'var(--s-monb)', monthly: 'var(--s-mon)', SPY: 'var(--s-spy)', QQQ: 'var(--s-qqq)', SPMO: 'var(--s-spmo)', calls: 'var(--s-calls)', cushionCalls: 'var(--s-ccalls)', rotation: 'var(--s-rot)' };
  var YH = { strategy: 'Top 5 basic', boost: 'Boost', boost100: 'Boost 100%', cushion: 'Cushion', plan: 'Auto', monthlyBoost: 'M boost', monthly: 'M auto', SPY: 'SPY', QQQ: 'QQQ', SPMO: 'SPMO', calls: 'B100 + calls', cushionCalls: 'Cush + calls', rotation: 'Boost + rotation' };
  var YHD = function (k) { return k === DEFK ? 'Default<span class="sub">' + YH[k] + '</span>' : YH[k]; };
  ys.forEach(function (y) { YK.forEach(function (k) { maxAbs = Math.max(maxAbs, Math.abs(D.years[k][y] || 0)); }); });
  var barMax = YK.length > 5 ? 3 : YK.length > 4 ? 18 : YK.length > 3 ? 26 : 70;
  function ybar(v, c) { var w = Math.max(2, Math.abs(v) / maxAbs * barMax); return '<span class="ybar' + (v < 0 ? ' neg' : '') + '"><i style="--c:' + c + ';width:' + w + 'px"></i><span class="num ' + tone(v) + '">' + pct(v, 0) + '</span></span>'; }
  $('years').className = 'years' + (YK.length > 5 ? ' tight' : '');
  $('years').innerHTML = '<thead><tr><th class="l">Year</th>' + YK.map(function (k) { return '<th class="l y-' + k + (k === DEFK ? ' def' : '') + '">' + YHD(k) + '</th>'; }).join('') + '</tr></thead><tbody>' +
    ys.map(function (y) { return '<tr><td class="l">' + y + '</td>' + YK.map(function (k) { return '<td class="l y-' + k + (k === DEFK ? ' def' : '') + '">' + (D.years[k][y] == null ? '<span class="muted">–</span>' : ybar(D.years[k][y], YC[k])) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody>';
  $('ytd-note').textContent = 'The shaded first column is the default plan (' + YH[DEFK] + '); the rest are alternatives. ' + ys[ys.length - 1] + ' is year to date (' + fmtDate(D.asOf, { month: 'short', day: 'numeric' }) + ').' +
    (TRK ? ' Backtest with the stocks in the S&P 500 at the time that have price history (58% of members in 2000, 67% in 2010, 77% in 2015, over 90% since 2020; most companies bought out or delisted before then are missing, which likely flatters the early years), 0.15% a trade' + (TRK.end ? '; after ' + fmtDate(TRK.end, { month: 'short', day: 'numeric', year: 'numeric' }) + ' the lines follow the live scan' : '') + '.' : '');
  if (TRK) $('growth-sub').innerHTML = 'The thick line is the default plan, <b>Boost + rotation</b>; the others are alternatives. Backtest from ' + TSINCE + ' with the stocks that were in the S&amp;P 500 at each date and have price history (58% of members in 2000, 67% in 2010, 77% in 2015, over 90% since 2020; most companies bought out or delisted before then are missing, which likely flatters the early years), news gaps and 0.15% a trade' + (TRK.end ? '; after ' + fmtDate(TRK.end, { month: 'short', day: 'numeric', year: 'numeric' }) + ' the lines follow the live scan' : '') + '. Lines with no such backtest (cushion, calls, monthly mixes) are not shown.';

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

  // rank heatmaps: the current top 15 week by week, and the top 30 (+ a few large caps) day by day
  function heatmap(H, p) {
    if (!H || !H.weeks || !H.weeks.length) { $(p).closest('.heatbox').hidden = true; return; }
    var unit = H.unit || 'week', daily = unit === 'day', N = H.tickers.length, n = H.weeks.length;
    var mode = 'rank', cmode = 'size', cap = daily ? 0.05 : 0.12, zcap = 2.5;
    try { mode = localStorage.getItem('nibii-' + p + '-mode') || 'rank'; cmode = localStorage.getItem('nibii-' + p + '-color') || 'size'; } catch (e) {}
    var rankNow = {}; D.table.forEach(function (r) { rankNow[r.t] = r.rank; });
    var extra = {}; (H.extra || []).forEach(function (t) { extra[t] = 1; });
    var core = N - (H.extra || []).length;
    $(p + '-title').textContent = daily ? 'Top ' + core + (H.extra && H.extra.length ? ' + ' + H.extra.length + ' large caps' : '') : 'Top ' + N;
    $(p + '-hint').textContent = daily
      ? 'each trading day the ' + N + ' stocks are ranked by % change: 1 = best · columns sorted by the sum of daily ranks over ' + n + ' days, lowest (most consistent) on the left · + = added by hand (' + (H.extra || []).join(', ') + ') · newest day at the top'
      : 'each week (last close to last close, normally Friday to Friday) the current top ' + N + ' are ranked by % change: 1 = best · columns sorted by the sum of weekly ranks over ' + n + ' weeks, lowest (most consistent) on the left · newest week at the top · darker = bigger move, either in % or against the stock\'s own normal week';
    function lab(d) { return fmtDate(d, { month: 'short', day: 'numeric' }); }
    // each stock's lowest / highest close in the window, for the price-level colors
    var pxlo = {}, pxhi = {};
    H.tickers.forEach(function (t) { H.cells[t].forEach(function (c) { if (c && c[3] != null) { pxlo[t] = Math.min(pxlo[t] == null ? Infinity : pxlo[t], c[3]); pxhi[t] = Math.max(pxhi[t] == null ? -Infinity : pxhi[t], c[3]); } }); });
    function pxpos(t, c) { return c && c[3] != null && pxhi[t] > pxlo[t] ? (c[3] - pxlo[t]) / (pxhi[t] - pxlo[t]) : null; }
    function money(x) { return x == null ? '–' : x >= 1000 ? Math.round(x).toLocaleString() : x >= 100 ? x.toFixed(1) : x.toFixed(2); }
    function shade(cell, t) {
      if (cmode === 'price') {
        var q = pxpos(t, cell);
        if (q == null) return 'background:var(--surface-2);color:var(--muted)';
        var mm = Math.round(12 + Math.abs(q - 0.5) * 2 * 73);
        return 'background:color-mix(in srgb, ' + (q >= 0.5 ? 'var(--accent)' : 'var(--neg)') + ' ' + mm + '%, var(--surface-2));color:' + (mm > 52 ? '#fff' : 'var(--ink)');
      }
      var ch = cell[0], v = cmode === 'norm' ? cell[2] : ch;
      if (v == null) return 'background:var(--surface-2);color:var(--muted)';
      var a = Math.min(1, Math.abs(v) / (cmode === 'norm' ? zcap : cap)), m = Math.round(12 + a * 73);
      var c = ch >= 0 ? 'var(--accent)' : 'var(--neg)';
      return 'background:color-mix(in srgb, ' + c + ' ' + m + '%, var(--surface-2));color:' + (m > 52 ? '#fff' : 'var(--ink)');
    }
    function when(i) {
      return (daily ? '' : 'week ending ') + fmtDate(H.weeks[i], { weekday: daily ? 'short' : undefined, month: 'short', day: 'numeric', year: 'numeric' }) + (H.partial && i === n - 1 ? ' (in progress)' : '');
    }
    function detail(t, i) {
      var c = H.cells[t][i];
      if (!c) return t + ' · ' + when(i) + ' · no price';
      return t + ' · ' + when(i) + (c[3] != null ? ' · close $' + money(c[3]) + (pxpos(t, c) != null ? ' (' + Math.round(pxpos(t, c) * 100) + '% of its ' + n + '-' + unit + ' low–high range)' : '') : '') + ' · ' + (c[0] >= 0 ? '+' : '') + (c[0] * 100).toFixed(1) + '% · rank ' + c[1] + ' of ' + N +
        (c[2] != null ? ' · ' + Math.abs(c[2]).toFixed(1) + '× its normal ' + (daily ? 'daily' : 'weekly') + ' move' : '');
    }
    function udbar(up, dn, title) {
      var tot = up + dn; if (!tot) return '<td class="ud"></td>';
      var pu = up / tot * 100;
      return '<td class="ud" title="' + title + '"><div class="udrow"><div class="udbar" role="img" aria-label="' + title + '"><span class="u" style="width:' + pu.toFixed(1) + '%"></span><span class="d" style="width:' + (100 - pu).toFixed(1) + '%"></span></div>' +
        '<span class="udnum">' + Math.round(pu) + '%</span></div></td>';
    }
    function udcell(i) {
      var up = 0, dn = 0;
      H.tickers.forEach(function (t) { var c = H.cells[t][i]; if (c) { if (c[0] > 0) up++; else dn++; } });
      return udbar(up, dn, up + ' of ' + (up + dn) + ' up, ' + dn + ' down · ' + when(i));
    }
    function draw() {
      document.querySelectorAll('#' + p + '-bar .seg button[data-v]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === mode)); });
      document.querySelectorAll('#' + p + '-bar .seg button[data-c]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-c') === cmode)); });
      $(p + '-scale').textContent = cmode === 'price'
        ? '· red = the stock\'s lowest close in the window, full color = its highest'
        : cmode === 'norm'
        ? '· full color = 2.5× the stock\'s normal ' + unit + ' (its usual ' + (daily ? 'daily swing over the past 3 months' : 'weekly swing over the past year') + ')'
        : '· full color = a ' + (cap * 100) + '% ' + unit;
      var head = '<thead><tr><th class="wk">' + (daily ? 'Day' : 'Week') + '</th>' + H.tickers.map(function (t) {
        var cls = held[t] ? 'held' : extra[t] ? 'extra' : '';
        var tip = held[t] ? t + ' is held now' : rankNow[t] ? t + ' is ranked #' + rankNow[t] + ' now' : t + ' (added by hand)';
        return '<th' + (cls ? ' class="' + cls + '"' : '') + ' title="' + esc(tip) + '">' + esc(t) + (extra[t] ? '+' : '') + '</th>';
      }).join('') + '<th class="ud" title="Share of the ' + N + ' stocks that were up (blue) or down (red) that ' + unit + '; the number is the % up">Up / down</th></tr></thead>';
      var body = '';
      for (var i = n - 1; i >= 0; i--) {
        body += '<tr><td class="wk">' + lab(H.weeks[i]) + (H.partial && i === n - 1 ? '*' : '') + '</td>' + H.tickers.map(function (t) {
          var c = H.cells[t][i];
          if (!c) return '<td class="c" tabindex="0" data-t="' + esc(t) + '" data-i="' + i + '" title="' + esc(detail(t, i)) + '">·</td>';
          var txt = mode === 'rank' ? c[1] : mode === 'price' ? money(c[3]) : (c[0] >= 0 ? '+' : '') + (c[0] * 100).toFixed(daily ? 1 : 0);
          return '<td class="c' + (mode === 'price' ? ' px' : '') + '" tabindex="0" style="' + shade(c, t) + '" data-t="' + esc(t) + '" data-i="' + i + '" title="' + esc(detail(t, i)) + '">' + txt + '</td>';
        }).join('') + udcell(i) + '</tr>';
      }
      var foot = '<tr class="sum"><td class="wk">Rank sum</td>' + H.tickers.map(function (t) { return '<td>' + H.sums[t] + '</td>'; }).join('') + (function () {
          var up = 0, dn = 0; H.tickers.forEach(function (t) { H.cells[t].forEach(function (c) { if (c) { if (c[0] > 0) up++; else dn++; } }); });
          return udbar(up, dn, up + ' of ' + (up + dn) + ' stock-' + unit + 's up over ' + n + ' ' + unit + 's');
        })() + '</tr>' +
        '<tr class="sum"><td class="wk">' + n + (daily ? '-day' : '-wk') + ' %</td>' + H.tickers.map(function (t) { var v = H.total[t]; return '<td class="' + tone(v) + '" title="' + esc(t) + ': ' + (v == null ? 'no price' : pct(v, 1)) + ' over ' + n + ' ' + unit + 's">' + (v == null ? '–' : (v >= 0 ? '+' : '−') + Math.abs(Math.round(v * 100))) + '</td>'; }).join('') + '<td class="ud"></td></tr>';
      $(p).innerHTML = head + '<tbody>' + body + foot + '</tbody>';
      trend();
    }
    function share(i) {
      var up = 0, tot = 0;
      H.tickers.forEach(function (t) { var c = H.cells[t][i]; if (c) { tot++; if (c[0] > 0) up++; } });
      return tot ? up / tot : null;
    }
    var tmode = 'run';
    try { tmode = localStorage.getItem('nibii-' + p + '-trend') || 'run'; } catch (e) {}
    function trend() {
      var box = $(p + '-trend'); if (!box) return;
      var W = Math.max(300, Math.round(box.clientWidth - 20)), Hh = W < 520 ? 140 : 170, L = 40, R = 8, T = 10, B = 22;
      var sh = H.weeks.map(function (_, i) { return share(i); });
      var wide = H.breadth || [];
      function run(a) { var c = 0, out = [0]; a.forEach(function (v) { c += v == null ? 0 : (2 * v - 1) * 100; out.push(c); }); return out; }
      var run1 = run(sh), run2 = wide.length ? run(wide) : null;
      // the running lines have one more point (the start, 0) than there are periods
      var m = tmode === 'run' ? n + 1 : n;
      var x = function (i) { return L + (m > 1 ? i / (m - 1) : 0.5) * (W - L - R); };
      var lo, hi;
      if (tmode === 'run') {
        var all = run1.concat(run2 || []);
        lo = Math.min.apply(null, all.concat([0])); hi = Math.max.apply(null, all.concat([0]));
        var pad = Math.max(10, (hi - lo) * 0.08); lo -= pad; hi += pad;
      } else { lo = 0; hi = 1; }
      var y = function (v) { return T + (hi - v) / (hi - lo) * (Hh - T - B); };
      function path(a) { return a.map(function (v, i) { return v == null ? '' : (i && a[i - 1] != null ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); }).join(''); }
      var g = '';
      var ticks = tmode === 'run' ? (function () {
        var span = hi - lo, st = [25, 50, 100, 200, 250, 500, 1000].find(function (q) { return span / q <= 5; }) || 2000, out = [];
        for (var v = Math.ceil(lo / st) * st; v <= hi; v += st) out.push(v); return out;
      })() : [0, 0.5, 1];
      ticks.forEach(function (v) {
        var mid = tmode === 'run' ? v === 0 : v === 0.5;
        g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) + '" stroke="var(--' + (mid ? 'muted' : 'grid') + ')" ' + (mid ? 'stroke-dasharray="4 3"' : '') + '/>' +
          '<text class="t" x="' + (L - 6) + '" y="' + (y(v) + 4).toFixed(1) + '" text-anchor="end">' + (tmode === 'run' ? (v > 0 ? '+' : '') + v : Math.round(v * 100) + '%') + '</text>';
      });
      var dates = tmode === 'run' ? [null].concat(H.weeks) : H.weeks;
      var step = Math.max(1, Math.ceil(m / Math.max(3, Math.floor(W / 90)))), xl = '';
      for (var i = m - 1; i >= 1; i -= step) xl += '<text class="t" x="' + x(i).toFixed(1) + '" y="' + (Hh - 6) + '" text-anchor="' + (i === m - 1 ? 'end' : 'middle') + '">' + lab(dates[i]) + '</text>';
      var areas = '', lines;
      if (tmode === 'run') {
        areas = '<path d="' + path(run1) + 'L' + x(m - 1).toFixed(1) + ' ' + y(0).toFixed(1) + 'L' + x(0).toFixed(1) + ' ' + y(0).toFixed(1) + 'Z" fill="var(--accent)" fill-opacity="0.14"/>';
        lines = (run2 ? '<path d="' + path(run2) + '" fill="none" stroke="var(--gold)" stroke-width="2"/>' : '') + '<path d="' + path(run1) + '" fill="none" stroke="var(--accent)" stroke-width="2.4"/>';
      } else {
        var top = path(sh);
        areas = '<path d="' + top + 'L' + x(n - 1).toFixed(1) + ' ' + y(1) + 'L' + x(0).toFixed(1) + ' ' + y(1) + 'Z" fill="var(--neg)" fill-opacity="0.16"/>' +
          '<path d="' + top + 'L' + x(n - 1).toFixed(1) + ' ' + y(0) + 'L' + x(0).toFixed(1) + ' ' + y(0) + 'Z" fill="var(--accent)" fill-opacity="0.2"/>';
        lines = (wide.length ? '<path d="' + path(wide) + '" fill="none" stroke="var(--gold)" stroke-width="2"/>' : '') + '<path d="' + top + '" fill="none" stroke="var(--accent)" stroke-width="2.4"/>';
      }
      var hit = '', w = (W - L - R) / Math.max(1, m - 1);
      for (var j = 0; j < m; j++) hit += '<rect x="' + (x(j) - w / 2).toFixed(1) + '" y="' + T + '" width="' + w.toFixed(1) + '" height="' + (Hh - T - B) + '" fill="transparent" data-i="' + j + '"/>';
      var gridName = daily ? 'these ' + N : 'the top ' + N;
      box.innerHTML = '<div class="cap"><span class="seg" role="group" aria-label="Chart">' +
        '<button type="button" data-tm="run" aria-pressed="' + (tmode === 'run') + '">Running total</button><button type="button" data-tm="share" aria-pressed="' + (tmode === 'share') + '">Share up each ' + unit + '</button></span>' +
        '<span><i style="background:var(--accent)"></i>' + gridName + '</span>' + (wide.length ? '<span><i style="background:var(--gold)"></i>all ' + H.breadthN + ' stocks tracked</span>' : '') +
        '<span id="' + p + '-tv">' + (tmode === 'run' ? 'adds % up minus % down each ' + unit + ': rising = more stocks going up than down' : '') + '</span></div>' +
        '<svg viewBox="0 0 ' + W + ' ' + Hh + '" role="img" aria-label="' + (tmode === 'run' ? 'Running total of % up minus % down' : 'Share of stocks up') + ' each ' + unit + ', last ' + n + ' ' + unit + 's">' +
        areas + g + lines + xl + hit + '</svg>';
      box.querySelector('.seg').addEventListener('click', function (e) {
        var bt = e.target.closest('button[data-tm]'); if (!bt) return; tmode = bt.getAttribute('data-tm');
        try { localStorage.setItem('nibii-' + p + '-trend', tmode); } catch (x2) {}
        trend();
      });
      function tip(e) {
        var r = e.target.closest('rect[data-i]'); if (!r) return; var i = +r.getAttribute('data-i');
        var txt;
        if (tmode === 'run') {
          if (i === 0) txt = 'start of the window: 0';
          else txt = lab(dates[i]) + ': ' + gridName + ' ' + (run1[i] > 0 ? '+' : '') + Math.round(run1[i]) + ' (' + Math.round(sh[i - 1] * 100) + '% up that ' + unit + ')' +
            (run2 ? ' · all stocks ' + (run2[i] > 0 ? '+' : '') + Math.round(run2[i]) + ' (' + Math.round(wide[i - 1] * 100) + '% up)' : '');
        } else {
          txt = lab(dates[i]) + ': ' + gridName + ' ' + Math.round(sh[i] * 100) + '% up' + (wide.length ? ' · all stocks ' + Math.round(wide[i] * 100) + '% up' : '');
        }
        $(p + '-tv').textContent = txt;
      }
      var svg = box.querySelector('svg');
      svg.addEventListener('mouseover', tip); svg.addEventListener('click', tip);
    }
    var rz; window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(trend, 150); });
    function show(e) { var c = e.target.closest('td.c'); if (c) $(p + '-note').textContent = detail(c.getAttribute('data-t'), +c.getAttribute('data-i')); }
    $(p).addEventListener('mouseover', show);
    $(p).addEventListener('click', show);
    $(p).addEventListener('focusin', show);
    $(p + '-bar').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-v], button[data-c]'); if (!b) return;
      if (b.hasAttribute('data-v')) {
        mode = b.getAttribute('data-v');
        if (mode === 'price') cmode = 'price';                 // price view: color by price level
        else if (cmode === 'price') cmode = 'size';
        try { localStorage.setItem('nibii-' + p + '-mode', mode); localStorage.setItem('nibii-' + p + '-color', cmode); } catch (x) {}
      }
      else { cmode = b.getAttribute('data-c'); try { localStorage.setItem('nibii-' + p + '-color', cmode); } catch (x) {} }
      draw();
    });
    draw();
    if (H.partial) $(p + '-note').textContent = '* this ' + unit + ' is still in progress. Hover or tap a cell for details.';
  }
  heatmap(D.heat, 'heat');
  heatmap(D.dheat, 'dheat');

  // 3D price-volume chart: x = trading day, y = close, z = volume; Plotly is loaded only when the section comes into view
  (function () {
    var PV = D.pv3d, box = $('pv');
    if (!box) return;
    if (!PV || !PV.tickers || !PV.tickers.length) { box.hidden = true; box.previousElementSibling.hidden = true; return; }
    var plot = $('pv-plot'), wait = $('pv-wait'), ticker = PV.tickers[0].t, view = '3d', shape = 'poles', spinning = false, spinT = null, loaded = false;
    try { var s0 = localStorage.getItem('nibii-pv-t'); if (s0 && PV.tickers.some(function (x) { return x.t === s0; })) ticker = s0;
          var s1 = localStorage.getItem('nibii-pv-shape'); if (s1 === 'wall' || s1 === 'poles') shape = s1; } catch (e) {}
    var CAMS = {
      '3d': { eye: { x: -0.95, y: -2.15, z: 0.9 }, up: { x: 0, y: 0, z: 1 }, center: { x: 0, y: 0, z: -0.12 }, projection: { type: 'perspective' } },
      top: { eye: { x: 0, y: 0, z: 2.4 }, up: { x: 0, y: 1, z: 0 }, center: { x: 0, y: 0, z: 0 }, projection: { type: 'orthographic' } },
      front: { eye: { x: 0, y: -2.4, z: 0 }, up: { x: 0, y: 0, z: 1 }, center: { x: 0, y: 0, z: 0 }, projection: { type: 'orthographic' } },
      side: { eye: { x: 2.4, y: 0, z: 0 }, up: { x: 0, y: 0, z: 1 }, center: { x: 0, y: 0, z: 0 }, projection: { type: 'orthographic' } } };
    var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    function narrow() { return plot.clientWidth < 600; }
    function cam(v) { var c = JSON.parse(JSON.stringify(CAMS[v])); if (v === '3d' && narrow()) c.eye = { x: c.eye.x * 1.45, y: c.eye.y * 1.45, z: c.eye.z * 1.3 }; return c; }
    function tok(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
    function fd(s) { return fmtDate(s, { month: 'short', day: 'numeric', year: 'numeric' }); }
    function pc(v) { return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'; }
    function cur() { return PV.tickers.filter(function (x) { return x.t === ticker; })[0]; }
    // ticker buttons: top 10 in rank order (gold edge = held now), then the reference tickers
    PV.tickers.forEach(function (x) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'tk' + (x.held ? ' held' : '');
      b.textContent = x.t; b.setAttribute('data-t', x.t); b.title = x.n + (x.rank ? ' · rank ' + x.rank : '') + (x.held ? ' · held now' : '');
      if (x.rank) { var r = document.createElement('sup'); r.textContent = x.rank; b.appendChild(r); }
      b.addEventListener('click', function () { ticker = x.t; try { localStorage.setItem('nibii-pv-t', ticker); } catch (e) {} mark(); draw(); });
      $(x.rank ? 'pv-top' : 'pv-oth').appendChild(b);
    });
    function mark() {
      box.querySelectorAll('button.tk').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-t') === ticker)); });
      box.querySelectorAll('#pv-shape button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-shape') === shape)); });
      box.querySelectorAll('#pv-views button[data-view]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === view)); });
    }
    function rows() {
      var X = cur(), out = [];
      for (var i = 1; i < PV.days.length; i++) {
        var c = X.close[i], p = X.close[i - 1], v = X.vol[i];
        if (c == null || v == null) continue;
        out.push({ d: PV.days[i], c: c, v: v / 1e6, ch: p ? c / p - 1 : 0 });
      }
      return out;
    }
    function stats(S) {
      var X = cur(), first = null; for (var i = 0; i < X.close.length; i++) if (X.close[i] != null) { first = X.close[i]; break; }
      if (!S.length) { $('pv-stats').innerHTML = ''; return; }
      var last = S[S.length - 1], chg = last.c / first - 1, avg = S.reduce(function (a, r) { return a + r.v; }, 0) / S.length;
      var big = S.reduce(function (a, r) { return r.v > a.v ? r : a; }, S[0]), up = S.filter(function (r) { return r.ch >= 0; }), dn = S.filter(function (r) { return r.ch < 0; });
      function mean(a) { return a.reduce(function (s, r) { return s + r.v; }, 0) / (a.length || 1); }
      var it = [['Last close', '$' + last.c.toFixed(2), fd(last.d)],
        ['6-month change', '<span class="' + (chg >= 0 ? 'pos' : 'neg') + '">' + pc(chg) + '</span>', 'from $' + first.toFixed(2)],
        ['Average volume', avg.toFixed(1) + 'M', 'shares a day'],
        ['Heaviest day', big.v.toFixed(1) + 'M', fd(big.d) + ' · <span class="' + (big.ch >= 0 ? 'pos' : 'neg') + '">' + pc(big.ch) + '</span> · ' + (big.v / avg).toFixed(1) + '× average'],
        ['Up / down days', up.length + ' / ' + dn.length, 'avg volume ' + mean(up).toFixed(1) + 'M vs ' + mean(dn).toFixed(1) + 'M']];
      $('pv-stats').innerHTML = it.map(function (x) { return '<div class="pv-stat"><div class="k">' + x[0] + '</div><div class="v">' + x[1] + '</div><div class="s">' + x[2] + '</div></div>'; }).join('');
    }
    function traces(S) {
      var up = tok('--pos'), dn = tok('--neg'), fl = tok('--muted'), X = S.map(function (r, n) { return n; });   // day number (big timestamps break WebGL precision)
      var Y = S.map(function (r) { return r.c; }), Z = S.map(function (r) { return r.v; });
      var out = [{ type: 'scatter3d', mode: 'lines', x: X, y: Y, z: S.map(function () { return 0; }), line: { color: fl, width: 5 }, hoverinfo: 'skip' }];
      if (shape === 'wall') {
        var vx = [], vy = [], vz = [], fi = [], fj = [], fk = [], fc = [];
        S.forEach(function (r, n) { vx.push(n, n); vy.push(r.c, r.c); vz.push(0, r.v); });
        for (var n = 0; n + 1 < S.length; n++) { var b0 = 2 * n, col = S[n + 1].ch >= 0 ? up : dn; fi.push(b0, b0); fj.push(b0 + 1, b0 + 3); fk.push(b0 + 3, b0 + 2); fc.push(col, col); }
        out.push({ type: 'mesh3d', x: vx, y: vy, z: vz, i: fi, j: fj, k: fk, facecolor: fc, flatshading: true,
          lighting: { ambient: 0.85, diffuse: 0.35, specular: 0.05, roughness: 0.9, fresnel: 0.05 }, hoverinfo: 'skip', showscale: false });
        out.push({ type: 'scatter3d', mode: 'lines', x: X, y: Y, z: Z, line: { color: tok('--ink-2'), width: 2 }, hoverinfo: 'skip' });
      } else {
        [[function (r) { return r.ch >= 0; }, up], [function (r) { return r.ch < 0; }, dn]].forEach(function (g) {
          var x = [], y = [], z = [];
          S.forEach(function (r, n) { if (g[0](r)) { x.push(n, n, null); y.push(r.c, r.c, null); z.push(0, r.v, null); } });
          out.push({ type: 'scatter3d', mode: 'lines', x: x, y: y, z: z, line: { color: g[1], width: 4 }, hoverinfo: 'skip', connectgaps: false });
        });
      }
      out.push({ type: 'scatter3d', mode: 'markers', x: X, y: Y, z: Z, marker: { size: shape === 'wall' ? 2.4 : 3.2, color: S.map(function (r) { return r.ch >= 0 ? up : dn; }), line: { width: 0 } },
        text: S.map(function (r) { return fd(r.d) + '<br>close $' + r.c.toFixed(2) + ' (' + pc(r.ch) + ')<br>volume ' + r.v.toFixed(1) + 'M'; }), hovertemplate: '%{text}<extra></extra>' });
      return out;
    }
    function axis(title, extra) {
      var ink = tok('--ink-2'), grid = tok('--hairline');
      return Object.assign({ title: { text: title, font: { size: 12, color: ink } }, color: ink, gridcolor: grid, zerolinecolor: grid, showbackground: true,
        backgroundcolor: tok('--surface'), tickfont: { size: 10, color: tok('--muted') }, showspikes: false }, extra || {});
    }
    function layout(S) {
      var tv = [], tt = [];
      S.forEach(function (r, n) { if (n > 0 && r.d.slice(5, 7) !== S[n - 1].d.slice(5, 7)) { tv.push(n); tt.push(MON[+r.d.slice(5, 7) - 1]); } });
      return { paper_bgcolor: tok('--surface-2'), plot_bgcolor: tok('--surface-2'), margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false,
        font: { color: tok('--ink-2') },
        hoverlabel: { bgcolor: tok('--surface'), bordercolor: tok('--hairline'), font: { color: tok('--ink'), size: 12 } },
        scene: { xaxis: axis('Time', { tickmode: 'array', tickvals: tv, ticktext: tt, range: [-1, S.length] }), yaxis: axis('Price ($)', { tickprefix: '$' }),
          zaxis: axis('Volume (M)', { rangemode: 'tozero' }),
          aspectmode: 'manual', aspectratio: narrow() ? { x: 1.35, y: 0.9, z: 0.8 } : { x: 2.1, y: 1, z: 0.85 }, camera: cam(view), dragmode: 'turntable' } };
    }
    function draw() {
      var S = rows(); stats(S);
      if (!loaded) return;
      Plotly.react(plot, traces(S), layout(S), { responsive: true, displaylogo: false, modeBarButtonsToRemove: ['toImage', 'resetCameraLastSave3d'] });
    }
    function setView(v) {
      view = v; stopSpin(); mark();
      if (!loaded) return;
      var p0 = plot._fullLayout && plot._fullLayout.scene ? plot._fullLayout.scene.camera.projection.type : 'perspective';
      if (p0 !== CAMS[v].projection.type) { Plotly.purge(plot); draw(); }   // the wall (mesh) needs a fresh scene when the camera type changes
      else Plotly.relayout(plot, { 'scene.camera': cam(v) });
    }
    box.querySelectorAll('#pv-views button[data-view]').forEach(function (b) { b.addEventListener('click', function () { setView(b.getAttribute('data-view')); }); });
    box.querySelectorAll('#pv-shape button').forEach(function (b) { b.addEventListener('click', function () {
      shape = b.getAttribute('data-shape'); try { localStorage.setItem('nibii-pv-shape', shape); } catch (e) {} mark();
      if (loaded) { var c = plot._fullLayout.scene.camera; draw(); Plotly.relayout(plot, { 'scene.camera': c }); } }); });
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function stopSpin() { spinning = false; clearInterval(spinT); $('pv-spin').setAttribute('aria-pressed', 'false'); }
    $('pv-spin').addEventListener('click', function () {
      if (spinning || !loaded) { stopSpin(); return; }
      if (view !== '3d') setView('3d');
      spinning = true; this.setAttribute('aria-pressed', 'true');
      var e = plot._fullLayout.scene.camera.eye, r = Math.sqrt(e.x * e.x + e.y * e.y), a = Math.atan2(e.y, e.x);
      spinT = setInterval(function () { a += reduce ? 0.02 : 0.012; Plotly.relayout(plot, { 'scene.camera.eye': { x: r * Math.cos(a), y: r * Math.sin(a), z: e.z } }); }, reduce ? 120 : 40);
    });
    plot.addEventListener('pointerdown', function () { if (spinning) stopSpin(); });
    new MutationObserver(function () { if (loaded) { Plotly.purge(plot); draw(); } }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-mtl-theme'] });
    mark(); stats(rows());
    function load() {
      if (loaded || load.started) return; load.started = true;
      var sc = document.createElement('script'); sc.src = 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js';
      sc.onload = function () { loaded = true; wait.hidden = true; draw(); };
      sc.onerror = function () { wait.textContent = 'The 3D chart library did not load. Check the connection and reload the page.'; load.started = false; };
      document.head.appendChild(sc);
    }
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (es) { if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); load(); } }, { rootMargin: '400px' });
      io.observe(box);
    } else load();
  })();

  // the weekly grid's top 15 as lines on one chart: daily closes (~6 months), or the grid's weekly closes
  // when the scan predates the daily ones; the stocks held now get a colour, the rest stay grey
  (function () {
    var HT = D.heat, box = $('heat-ov');
    if (!box || !window.mtlOverlay || !HT || !HT.tickers || !HT.tickers.length) { if (box) box.hidden = true; return; }
    var nm = {}; D.table.forEach(function (r) { nm[r.t] = r.n; });
    var assets = HT.tickers.map(function (t) { return [t, nm[t] || t]; }), HD = HT.daily, data;
    if (HD && HD.days && HD.days.length > 1) data = { days: HD.days, assets: assets, closes: HD.closes };
    else {
      var cl = {}; HT.tickers.forEach(function (t) { cl[t] = HT.cells[t].map(function (c) { return c && c[3] != null ? c[3] : null; }); });
      data = { days: HT.weeks, assets: assets, closes: cl };
    }
    var hl = D.holdings.map(function (h) { return h.t; }).filter(function (t) { return HT.tickers.indexOf(t) >= 0; });
    mtlOverlay(box, { title: 'Top ' + HT.tickers.length + ' on one chart', key: 'nibii-heat-ov', step: HD ? 'daily' : 'weekly', highlight: hl,
      note: (hl.length ? 'Coloured = held now (' + hl.join(', ') + '); grey = the rest of the top ' + HT.tickers.length + '. ' : '') +
            'Hover a name in the legend to bring its line forward; click it to hide the line.' }).set(data);
  })();

  // table
  var T = { q: '', sec: '', sort: 'rank', dir: 1, all: false };
  D.table.forEach(function (r) { r.revEps = r.rev && r.rev.eps90 != null ? r.rev.eps90 : null; });
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
        '<td class="num">' + delta(r.d1w) + '</td><td class="num hide-sm">' + delta(r.d4w) + '</td><td class="num hide-sm">' + pct(r.offHigh) + '</td><td class="num">' + revCell(r.rev) + '</td><td>' + trend(r.trend) + '</td></tr>';
    }).join('') || '<tr><td colspan="12" class="l muted">No stocks match.</td></tr>';
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
  function apply(t) { if (t) root.setAttribute('data-mtl-theme', t); else root.removeAttribute('data-mtl-theme'); var dark = t !== 'light'; sun.toggleAttribute('hidden', dark); moon.toggleAttribute('hidden', !dark); }
  var saved = null; try { saved = localStorage.getItem('mtl-theme'); } catch (e) {}
  apply(saved);
  document.getElementById('theme-toggle').addEventListener('click', function () {
    var next = root.getAttribute('data-mtl-theme') === 'light' ? 'dark' : 'light'; apply(next); try { localStorage.setItem('mtl-theme', next); } catch (e) {}
  });
})();
</script>
'''


GROWTH_PATH = os.path.join(ROOT, 'documents', 'growth_rank.json')


def growth_html():
    """The cross-asset growth ranking grid from the main page (documents/growth_rank.json,
    refreshed by the daily data fetch), or '' when the file is missing."""
    try:
        with open(GROWTH_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ''
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render_html import growth_rank_section
    sec = growth_rank_section(data)
    when = (data.get('fetchedAt') or '')[:10]
    fix = ('<style>#growthRank table.gr-table th { text-transform: none; letter-spacing: 0; white-space: normal; overflow-wrap: anywhere; }'
           ' #growthRank table.gr-table th.gr-label { white-space: nowrap; }</style>')
    return fix + sec.replace('<p class="section-label">Growth ranking</p>',
                       '<p class="section-label">Cross-asset growth ranking <span class="hint">Nasdaq, S&amp;P, dollar, oil, gold, 10-year notes'
                       + (f' · fetched {when}' if when else '') + '</span></p>', 1) if sec else ''


RESEARCH_PATH = os.path.join(ROOT, 'documents', 'winners_research.html')


IGNITION_PATH = os.path.join(ROOT, 'data', 'ignition_scan.json')
KIND_LABEL = {'ignition': 'Ignition', 'turnaround': 'Turnaround', 'breakout': 'Breakout', 'pocket': 'Pocket pivot',
              'all': 'Any liquid stock'}
KIND_TONE = {'ignition': 'buy', 'turnaround': 'buy', 'breakout': '', 'pocket': '', 'all': 'ndx'}
POCKET_SHOWN = 15
RECENT_SHOWN = 40

IGNITION_CSS = """<style>
#watch .card { margin-bottom: 12px; }
#watch p, #watch li { color: var(--ink-2); font-size: 0.86rem; }
#watch p { margin: 0 0 8px; }
#watch .tablebox { margin-bottom: 12px; }
#watch td .sub { max-width: 240px; }
#watch td.w, #watch th.w { white-space: normal; text-align: left; }
#watch details { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 0 16px; margin-bottom: 10px; }
#watch summary { cursor: pointer; padding: 12px 0; font-weight: 600; color: var(--ink); }
#watch details[open] summary { border-bottom: 1px solid var(--hairline); margin-bottom: 10px; }
#watch details > :last-child { margin-bottom: 14px; }
#watch .grp { color: var(--gold); font-size: 0.7rem; font-weight: 600; margin-left: 4px; }
#watch ul { margin: 0 0 8px; padding-left: 20px; }
#watch .acts { display: grid; gap: 8px; margin-bottom: 12px; }
#watch .act { background: var(--surface); border: 1px solid var(--hairline); border-left: 4px solid var(--hairline); border-radius: 10px; padding: 10px 14px; }
#watch .act p { margin: 4px 0 0; }
#watch .act.new { border-left-color: var(--accent); } #watch .act.exit { border-left-color: var(--neg); }
#watch .act.trail { border-left-color: var(--gold); } #watch .act.profit { border-left-color: var(--pos); }
#watch .act .who { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
#watch .act .who .muted { font-size: 0.78rem; }
#watch .act .size { font-size: 0.8rem; color: var(--ink); }
#watch .act .why { margin: 6px 0 0; padding-left: 18px; font-size: 0.8rem; color: var(--ink-2); }
#watch .act .why li { margin-top: 2px; }
#watch .mkt { border-left: 4px solid var(--pos); } #watch .mkt.warn { border-left-color: var(--gold); } #watch .mkt.bad { border-left-color: var(--neg); }
#watch .acct { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--ink-2); margin: 0 0 10px; }
#watch tr.wg td { background: var(--surface-2); padding-top: 10px; }
#watch .soon { color: var(--gold); }
#watch table.wl td.do { min-width: 200px; max-width: 300px; font-size: 0.78rem; color: var(--ink-2); }
#watch table.wl td .sub { max-width: 150px; }
#watch table.wl th, #watch table.wl td { padding: 7px 8px; }
#watch .acct input { font: inherit; width: 120px; padding: 5px 8px; border-radius: 8px; border: 1px solid var(--hairline); background: var(--surface-2); color: var(--ink); }
</style>"""


def _e(x):
    return html.escape(str(x or ''))


def _p(x, d=1, sign=True):
    if x is None:
        return '–'
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def _x(v):
    return '–' if v is None else f'{v:.1f}x'


def _tone(x):
    return '' if x is None else ('pos' if x > 0 else 'neg' if x < 0 else '')


def _stock(r):
    sub = ' · '.join(filter(None, [r.get('n'), r.get('ind')]))
    return f'<b>{_e(r["t"])}</b>' + (f'<span class="sub">{_e(sub)}</span>' if sub else '')


def _tag(kind):
    return f'<span class="tag {KIND_TONE.get(kind, "")}">{KIND_LABEL.get(kind, _e(kind))}</span>'


ACT_LABEL = {'new': 'New', 'exit': 'Exit', 'trail': 'Sell the rest', 'profit': 'Take profit', 'hold': 'Hold'}
ACT_TONE = {'new': 'buy', 'exit': 'sell', 'trail': 'sell', 'profit': 'buy', 'hold': ''}

SIZE_JS = """<script>
(function () {
  var box = document.getElementById('acct'); if (!box) return;
  try { var v = localStorage.getItem('mtl-acct'); if (v) box.value = v; } catch (e) {}
  function fill() {
    var a = parseFloat(String(box.value).replace(/[^0-9.]/g, '')) || 0;
    try { localStorage.setItem('mtl-acct', box.value); } catch (e) {}
    document.querySelectorAll('#watch .size[data-close]').forEach(function (el) {
      var c = +el.getAttribute('data-close'), st = +el.getAttribute('data-stop');
      if (!a || !(c > st)) { el.textContent = ''; return; }
      var n = Math.floor(Math.min(a * 0.01 / (c - st), a * 0.25 / c));
      el.textContent = 'Size: ' + n + ' shares (~$' + Math.round(n * c).toLocaleString() + ') risks ~$' + Math.round(n * (c - st)).toLocaleString() + ' to the stop.';
    });
  }
  box.addEventListener('input', fill); fill();
})();
</script>"""


def _act(a):
    size = (f'<p class="size" data-close="{a["close"]}" data-stop="{a["stop"]}"></p>'
            if a['act'] == 'new' and a.get('close') and a.get('stop') else '')
    return (f'<div class="act {a["act"]}"><div class="who"><span class="tag {ACT_TONE[a["act"]]}">{ACT_LABEL[a["act"]]}</span>'
            f'<b>{_e(a["t"])}</b><span class="muted">{_e(a.get("n"))} · {KIND_LABEL.get(a["kind"], "")} {_e(a.get("d"))}</span></div>'
            f'<p>{_e(a["text"])}</p>'
            + (f'<ul class="why">' + ''.join(f'<li>{_e(w)}</li>' for w in a.get('why') or []) + '</ul>' if a.get('why') else '')
            + f'{size}</div>')


def _theme_line(scan):
    th = scan.get('themes') or []
    if not th:
        return ''
    em = [r['ind'] for r in th if r.get('emerging') or r.get('newTop')]
    return (f'<p><b>Hottest fields:</b> {", ".join(_e(r["ind"]) for r in th[:3])}'
            + (f' · <b>heating up:</b> {", ".join(_e(g) for g in em[:4])}' if em else '') + ' (see Hot industries below).</p>')


def plan_html(scan):
    sys.path.insert(0, ROOT)
    from mtl.ignition import market_note, plan
    acts = plan(scan)
    tone, note = market_note(scan.get('market'))
    main = [a for a in acts if a['act'] != 'hold']
    holds = [a for a in acts if a['act'] == 'hold']
    out = ['<p class="section-label">Action plan <span class="hint">rewritten every night from the scan · '
           'the swing playbook from the research below</span></p>',
           f'<div class="card mkt {tone}"><p><b>Market:</b> {_e(note)}</p>' + _theme_line(scan) + '</div>',
           '<label class="acct">Account size $<input id="acct" inputmode="decimal" placeholder="e.g. 25000">'
           '<span class="muted">sizes new ideas to risk 1% to the stop, max 25% of the account per stock</span></label>']
    if main:
        out.append('<div class="acts">' + ''.join(_act(a) for a in main) + '</div>')
    else:
        out.append('<p class="note">No new ignitions or turnarounds and nothing to sell tonight.</p>')
    if holds:
        out.append(f'<details><summary>Hold - {len(holds)} recent flag{"s" if len(holds) != 1 else ""} still above their stops</summary>'
                   '<div class="acts">' + ''.join(_act(a) for a in holds) + '</div></details>')
    return ''.join(out) + SIZE_JS


STATE_LABEL = {'up': ('Uptrend', 'pos'), 'mixed': ('Mixed', 'muted'), 'down': ('Downtrend', 'neg')}


def _earn_days(r, as_of):
    from datetime import date as _d
    if not r.get('earn') or not as_of:
        return None
    return (_d.fromisoformat(r['earn'][:10]) - _d.fromisoformat(as_of)).days


def _earn_cell(r, as_of):
    n = _earn_days(r, as_of)
    if n is None:
        return '<span class="muted">–</span>'
    from datetime import date as _d
    d = _d.fromisoformat(r['earn'][:10])
    txt = d.strftime('%b ') + str(d.day)
    return f'<b class="soon">{txt}</b> <span class="muted">{n}d</span>' if n <= 14 else f'{txt} <span class="muted">{n}d</span>'


def _watch_do(r, plan_by_t, as_of=None):
    n = _earn_days(r, as_of)
    pre = (f'<b>Earnings in {n} day{"s" if n != 1 else ""}</b> - the gap that matters often comes on the report; '
           'avoid buying right before it, act on the reaction. ') if n is not None and 0 <= n <= 14 else ''
    return pre + _watch_do_base(r, plan_by_t)


def _watch_do_base(r, plan_by_t):
    a = plan_by_t.get(r['t'])
    if a:
        return f'<b>{ACT_LABEL[a["act"]]}:</b> {_e(a["text"])}'
    f = r.get('flag')
    if f and f['days'] == 0:
        return f'Flagged {KIND_LABEL.get(f["kind"], f["kind"]).lower()} today: check the news; stop under today\'s low.'
    if r['state'] == 'up':
        return ('Uptrend, recent ' + KIND_LABEL.get(f['kind'], '').lower() + '. Hold; add on the next earnings gap-up.') if f else \
            'Uptrend: wait for a gap-up on earnings or a breakout on volume to buy.'
    if r['state'] == 'mixed':
        return 'Above its 50-day average but not a full uptrend: wait.'
    return 'Downtrend: avoid until it gets back above its 50-day average.'


def watch_html(scan):
    groups = scan.get('watch') or []
    if not groups:
        return ''
    sys.path.insert(0, ROOT)
    from mtl.ignition import plan
    plan_by_t = {a['t']: a for a in plan(scan)}
    body = []
    for g in groups:
        ranks = [r.get('indRank') for r in g['rows'] if r.get('indRank')]
        ind_rank = max(set(ranks), key=ranks.count) if ranks else None
        if ind_rank and ranks.count(ind_rank) * 2 < len(g['rows']):
            ind_rank = None                     # the group spans several industries
        body.append(f'<tr class="wg"><td colspan="10" class="l"><b>{_e(g["group"])}</b> <span class="muted">· {g["up"]} of {g["n"]} in an uptrend'
                    f' · median 3m vs SPY {_p(g.get("r63"), 0)}'
                    + (f' · industry rank #{ind_rank} of {scan.get("themeCount", "?")}' if ind_rank else '') + '</span></td></tr>')
        for r in g['rows']:
            if r.get('missing'):
                body.append(f'<tr><td class="l"><b>{_e(r["t"])}</b></td><td colspan="9" class="l muted">no price data</td></tr>')
                continue
            lab, tone = STATE_LABEL[r['state']]
            f = r.get('flag')
            flag = f'{_tag(f["kind"])} <span class="muted">{_e(f["d"][5:])}</span>' if f else '<span class="muted">–</span>'
            body.append(f'<tr><td class="l">{_stock(dict(t=r["t"], n=r.get("n")))}</td><td class="l {tone}">{lab}</td>'
                        f'<td class="num {_tone(r.get("chg"))}">{_p(r.get("chg"))}</td>'
                        f'<td class="num hide-sm {_tone(r.get("r21"))}">{_p(r.get("r21"), 0)}</td>'
                        f'<td class="num {_tone(r.get("r63"))}">{_p(r.get("r63"), 0)}</td>'
                        f'<td class="num">{"–" if r.get("rs") is None else r["rs"]}</td>'
                        f'<td class="num hide-sm">{_p(r.get("offHigh"), 0)}</td><td class="l hide-sm">{flag}</td>'
                        f'<td class="num">{_earn_cell(r, scan.get("asOf"))}</td><td class="l w do">{_watch_do(r, plan_by_t, scan.get("asOf"))}</td></tr>')
    return ('<p class="section-label">Watchlist: semis &amp; AI <span class="hint">nightly status · edit the list in '
            '<a href="https://github.com/danreed001-droid/NIBII/blob/main/data/watchlist.json">data/watchlist.json</a></span></p>'
            '<div class="tablebox"><table class="wl"><thead><tr><th class="l">Stock</th><th class="l">Trend</th><th>Day</th>'
            '<th class="hide-sm">1m vs SPY</th><th>3m vs SPY</th><th title="Relative strength percentile, 1-99">RS</th>'
            '<th class="hide-sm">Off 52w high</th><th class="l hide-sm">Latest flag</th><th>Earnings</th><th class="l w">Do</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


THEMES_SHOWN = 12


def themes_html(scan):
    th = (scan.get('themes') or [])[:THEMES_SHOWN]
    if not th:
        return ''
    hot = [r for r in th if r.get('emerging') or r.get('newTop')]

    def badges(r):
        return ((' <span class="tag buy">Emerging</span>' if r.get('emerging') else '')
                + (' <span class="tag">New in top 10</span>' if r.get('newTop') else ''))
    rows = ''.join(
        f'<tr><td class="num">{i}</td><td class="l w"><b>{_e(r["ind"])}</b>{badges(r)}</td><td class="num">{r["heat"]}</td>'
        f'<td class="num hide-sm">{r["n"]}</td>'
        f'<td class="l w">{r["flags"]}{(" · " + ", ".join(_e(t) for t in r["flagged"])) if r["flagged"] else ""}</td>'
        f'<td class="num">{round(r["up"] * 100)}% <span class="{_tone(r["dUp"])}">({r["dUp"] * 100:+.0f})</span></td>'
        f'<td class="num hide-sm {_tone(r.get("r63"))}">{_p(r.get("r63"), 0)}</td>'
        f'<td class="l hide-sm">{", ".join(_e(t) for t in r.get("leaders") or [])}</td></tr>'
        for i, r in enumerate(th, 1))
    lead = (f'<p class="note"><b>Heating up:</b> ' + ' · '.join(_e(r['ind']) for r in hot) + '</p>') if hot else ''
    return ('<p class="section-label">Hot industries <span class="hint">which field is blowing up, whatever it is · '
            f'{scan.get("themeCount", len(th))} industries ranked by recent flags, share in an uptrend and 3-month return vs SPY</span></p>'
            + lead +
            '<div class="tablebox"><table><thead><tr><th>#</th><th class="l w">Industry</th>'
            '<th title="0-100: average rank of flag rate, uptrend share and 3-month return vs SPY">Heat</th>'
            '<th class="hide-sm">Stocks</th><th class="l w">Flags 20d</th>'
            '<th title="Share of its stocks in an uptrend now (change in points over 4 weeks)">In uptrend (4w Δ)</th>'
            '<th class="hide-sm">3m vs SPY</th><th class="l hide-sm">Strongest</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
            '<p class="note"><b>Emerging</b> = its share of stocks in an uptrend rose 15+ points in 4 weeks and it ranks in the top '
            'quarter. <b>New in top 10</b> = not in the top 10 a week ago. A field that keeps showing up here, with its stocks gapping '
            'on earnings, is how the AI suppliers looked in 2023 - and how the next theme will look.</p>')


def ignition_html(scan=None):
    """The "Next big thing watch" block from data/ignition_scan.json (written
    nightly by scripts/ignition_scan.py), or '' when there is no scan yet."""
    if scan is None:
        try:
            with open(IGNITION_PATH) as f:
                scan = json.load(f)
        except (OSError, ValueError):
            return ''
    today = scan.get('today') or []
    pockets = [r for r in today if r['kind'] == 'pocket']
    shown = [r for r in today if r['kind'] != 'pocket'] + pockets[:POCKET_SHOWN]
    out = [IGNITION_CSS, '<section id="watch">',
           '<p class="section-label">Next big thing watch <span class="hint">'
           f'ignition scan · {scan.get("liquid", 0):,} liquid US stocks (NYSE + Nasdaq, $5+, $10M+/day) · close of {_e(scan.get("asOf"))}</span></p>',
           '<div class="card"><p>Every weekday after the close this scans every US-listed stock for the signatures that started the '
           'big 2021–2026 winners (research below): a <b>gap up on several times normal volume</b>, ideally in an uptrend near the high, '
           'stronger than the market, and <b>repeating</b> on later earnings. A flag is a reason to look closer, not a buy signal: '
           'check the news behind it (guidance raise, contract, first profit?) and see the hit rates at the bottom before sizing anything.</p>']
    if scan.get('mechanical'):
        out.append('<p class="note">Options-expiry / index-rebalance day: breakout and pocket-pivot flags are skipped (mechanical volume).</p>')
    out.append('</div>')
    out.append(plan_html(scan))
    out.append(watch_html(scan))
    out.append(themes_html(scan))

    rows = ''.join(
        f'<tr><td class="l">{_stock(r)}{"<span class=grp>▲ group</span>" if r.get("group") else ""}</td><td class="l">{_tag(r["kind"])}</td>'
        f'<td class="num">{r["score"]:.1f}</td><td class="num {_tone(r.get("chg"))}">{_p(r.get("chg"))}</td>'
        f'<td class="num hide-sm">{_p(r.get("gap"))}</td><td class="num">{_x(r.get("vr"))}</td>'
        f'<td class="num">{"–" if r.get("rs") is None else r["rs"]}</td><td class="num hide-sm">{_p(r.get("offHigh"))}</td>'
        f'<td class="num">{r.get("repeats") or "–"}</td></tr>' for r in shown)
    if not rows:
        rows = f'<tr><td colspan="9" class="l muted">Nothing flagged at the {_e(scan.get("asOf"))} close.</td></tr>'
    extra = len(pockets) - POCKET_SHOWN
    out.append('<p class="section-label">Flagged at the latest close <span class="hint">sorted by score: setup, relative strength, '
               'repeat gaps, closeness to the 52-week high, group move</span></p>'
               '<div class="tablebox"><table><thead><tr><th class="l">Stock</th><th class="l">Setup</th><th>Score</th><th>Day</th>'
               '<th class="hide-sm">Gap</th><th>Vol vs 50d</th><th title="Relative strength percentile, 1-99">RS</th>'
               '<th class="hide-sm">Off 52w high</th><th title="Qualifying gap-ups (ignition or turnaround) in the last 12 months">Gaps 12m</th>'
               f'</tr></thead><tbody>{rows}</tbody></table></div>'
               + (f'<p class="note">+{extra} more pocket pivots not shown.</p>' if extra > 0 else ''))

    groups = scan.get('groups') or []
    if groups:
        out.append('<p class="note"><b>Group moves</b> (2+ stocks in one industry flagged in the last 5 sessions): '
                   + ' · '.join(f'{_e(g)}: {", ".join(_e(t) for t in ts)}' for g, ts in groups) + '</p>')

    recent = (scan.get('recent') or [])[:RECENT_SHOWN]
    if recent:
        rr = ''.join(
            f'<tr><td class="num l">{_e(r["d"])}</td><td class="l">{_stock(r)}</td><td class="l">{_tag(r["kind"])}</td>'
            f'<td class="num {_tone(r.get("since"))}">{_p(r.get("since"))}</td><td class="num hide-sm {_tone(r.get("ex"))}">{_p(r.get("ex"))}</td>'
            f'<td>{"<span class=pos>holding</span>" if r.get("held") else "<span class=neg>lost it</span>"}</td></tr>' for r in recent)
        out.append(f'<details><summary>Flags from the last {scan.get("rules", {}).get("recent", 20)} sessions and how they have done</summary>'
                   '<div class="tablebox"><table><thead><tr><th class="l">Flagged</th><th class="l">Stock</th><th class="l">Setup</th>'
                   '<th>Since</th><th class="hide-sm">vs SPY</th><th title="Still above the flag day\'s low - the usual stop">Flag-day low</th>'
                   f'</tr></thead><tbody>{rr}</tbody></table></div></details>')

    st = scan.get('stats') or {}
    if st:
        sr = ''.join(
            f'<tr><td class="l">{_tag(k)}</td><td class="num">{v.get("n", 0):,}</td>'
            f'<td class="num {_tone(v.get("ex20"))}">{_p(v.get("ret20"))} <span class="muted">({_p(v.get("ex20"))})</span></td>'
            f'<td class="num {_tone(v.get("ex60"))}">{_p(v.get("ret60"))} <span class="muted">({_p(v.get("ex60"))})</span></td>'
            f'<td class="num hide-sm {_tone(v.get("ex120"))}">{_p(v.get("ret120"))} <span class="muted">({_p(v.get("ex120"))})</span></td>'
            f'<td class="num">{_p(v.get("beat60"), 0, False)}</td><td class="num">{_p(v.get("up50"), 0, False)}</td>'
            f'<td class="num hide-sm neg">{_p(v.get("mae60"))}</td></tr>'
            for k, v in st.items() if v.get('n'))
        out.append(f'<details open><summary>Hit rates: every flag since {_e(scan.get("statsFrom"))}, replayed with the same rules</summary>'
                   '<div class="tablebox"><table><thead><tr><th class="l">Setup</th><th>Flags</th><th>Median 20d (vs SPY)</th>'
                   '<th>60d (vs SPY)</th><th class="hide-sm">120d (vs SPY)</th><th>Beat SPY 60d</th>'
                   '<th title="Share of flags whose close reached +50% at some point within 120 sessions">Hit +50% in 120d</th>'
                   '<th class="hide-sm" title="Median of the lowest close within 60 sessions vs the flag-day close">Typical dip 60d</th>'
                   f'</tr></thead><tbody>{sr}</tbody></table></div>'
                   '<p class="note">How to read it: compare each setup with <b>Any liquid stock</b> (a random pick over the same days). '
                   'The <b>median</b> flag goes nowhere special; the edge, if any, is in the <b>tail</b> '
                   '(the share that reach +50%) and in cutting the losers early. Only stocks listed today are replayed, so companies that '
                   'went bust or were delisted are missing, which flatters these numbers. Not investment advice.</p></details>')
    out.append('</section>')
    return '\n'.join(out)


WALLST_PATH = os.path.join(ROOT, 'data', 'wall_street_tests.json')
WALLST_ROWS = {   # measure, what it means
    'return': ('Return a year (after tax)', 'Average yearly growth from 2000. After tax = a taxable account (37% short-term, 20% long-term).'),
    'sharpe': ('Sharpe ratio', 'Return above cash for each unit of ups and downs. Above 1 is excellent for a stock strategy; the market is about 0.4.'),
    'sortino': ('Sortino ratio', 'Like Sharpe, but only the downside swings count as risk, so big up-days are not punished.'),
    'maxdd': ('Worst drop', 'The biggest fall from a high before it recovered (−33.4% from May 2001 to June 2002, about 2 points deeper than before the rebound rule because of its two days in stocks in October 2001; −33.3% from May to Oct 2006, when two cash weeks held gold as it fell; −44% from late 2007 to spring 2009 before the lower-high exit). Expect to sit through drops like this.'),
    'calmar': ('Calmar ratio', 'Yearly return divided by the worst drop: how much you earn for the worst pain. SPY earns 0.15.'),
    'ulcer': ('Ulcer index', 'How deep and how long the drops last, combined into one number. Lower is calmer.'),
    'omega': ('Omega ratio', 'Gains in up months divided by losses in down months (above cash): $2.94 gained for every $1 lost.'),
    'capture': ('Up / down capture', 'In months SPY rose, the plan rose about 1.4x as much; in months SPY fell, it was about flat on average.'),
    'var': ('Bad month (VaR / CVaR 95%)', 'One month in 20 loses at least the first number; the second is the average of those bad months.'),
    'worst3': ('Worst 3 years', 'The weakest three-year stretch, per year (2000–2002 for SPY).'),
    'under': ('Longest underwater', 'The longest wait below a previous high before getting back to it, on daily closes (the plan: May 2001 to May 2003; SPY: March 2000 to October 2006). Every drop is listed under Back to the peak below.'),
    'alpha': ('Alpha after factors', 'Return left over after taking out what the market, size, value, quality, momentum, bonds and gold explain. A t-stat above 2 means it is unlikely to be luck.'),
    'alphadec': ('Alpha 2000s / 2010s / 2020s', 'The same by decade: strong in the 2000s and 2020s, weakest in the 2010s.'),
}
WALLST_MC = {
    'typical': ('Typical return a year (after tax)', 'The middle outcome of the simulated futures.'),
    'bad': ('Bad case (1 in 20)', 'Only 5% of simulated futures did worse than this per year.'),
    'spy': ('SPY, typical', 'The same simulation for SPY, for comparison.'),
    'beatSpy': ('Chance of beating SPY', 'Share of simulated futures in which the plan ended ahead of SPY.'),
    'beatSpyTax': ('... after tax', 'The plan after tax against SPY untaxed.'),
    'beatSpyHalf': ('... with half the edge', 'If the plan only keeps half of its historical lead over SPY: the realistic check for a backtest tuned on this history.'),
    'beatPrev': ('Chance of beating the previous plan', 'Share of simulated futures in which the plan beat the previous plan (the same plan picking gold or bonds by their 6-month gain wherever it would hold T-bills, the default until Oct 19, 2026).'),
    'dd': ('Typical worst drop', 'The middle worst drop within each simulated future.'),
    'dd50': ('Chance of a −50% drop', 'Share of simulated futures with a drop of half or more at some point.'),
    'dd50Half': ('... with half the edge', 'The same with half of the historical lead.'),
    'under': ('Typical longest wait for a new high', 'The middle of each simulated future’s longest stretch below a previous high.'),
    'underBad': ('... bad case (1 in 20)', 'Only 5% of simulated futures had a longer wait at some point.'),
    'under2y': ('Chance of a wait over 2 years', 'Share of simulated futures with at least one stretch of more than 24 months below a previous high.'),
    'underSpy': ('SPY, typical longest wait', 'The same for SPY, for comparison.'),
}
WALLST_OTHER = {
    'pbo': lambda o: f'<b>Overfitting test (PBO, {o.get("n")} versions):</b> a {_e(o["v"])} chance that the best-looking version is a fluke, judged on years it was not picked on. Under 50% means picking the best version helped.',
    'dsr': lambda o: f'<b>Deflated Sharpe ratio ({o.get("n"):,} versions):</b> a {_e(o["v"])} chance the edge is real after allowing for how many versions were tried. '
                     f'Luck alone would give the best of that many versions a Sharpe ratio of about {_e(o["luck"])}; the plan’s is {_e(o["sharpe"])}. Above 95% is the usual bar.',
    'walk': lambda o: f'<b>Walk-forward:</b> re-picking the best version each year, using only the years before it, earned {_e(o["v"])} a year in 2005–2025 against {_e(o["typical"])} for the typical version.',
    'pickT': lambda o: f'<b>The 6-month pick on its own:</b> adds about {_e(o["v"])}; a t-stat under 2 means the gain is not proven, so it is on probation.',
    'cashT': lambda o: f'<b>The narrow-market cash week on its own:</b> {_e(o["v"])}. Month by month the gain is not proven (most months it does nothing); judged on its cash weeks against random weeks it is unlikely to be luck. It was found on 2012–2026, went 1 for 3 on the 2006–07 years it was not built on, and did not carry over abroad (below), so it is on probation.',
    'billsT': lambda o: f'<b>No T-bills on its own</b> (gold or bonds if up over 6 months, else cash; 3 months since Oct 19, 2026; DBMF managed futures instead of cash since Oct 20, 2026): {_e(o["v"])}. The gain is lumpy (bonds in late 2008, gold in the 2024–2025 cash weeks; gold cost about 40 points of 2026\'s gain), so count on it doing about as well as T-bills.',
    'bills3T': lambda o: f'<b>The 3-month look on its own</b> (gold or bonds by their 3-month gain instead of 6, wherever the plan would hold T-bills; default since Oct 19, 2026): {_e(o["v"])}. Most of the gain is a few stretches (2026, 2009, 2017) and it cost 15 points in 2025, so it is on probation.',
    'mfT': lambda o: f'<b>Managed futures instead of cash on its own</b> (DBMF, a fund that follows trends in stock, bond, currency and commodity futures, wherever the no-T-bills pick finds neither gold nor bonds up; default since Oct 20, 2026): {_e(o["v"])}. The fund began in May 2019, so the gain is from then on; it rests on a few stretches and is on probation.',
    'reboundT': lambda o: f'<b>The rebound rule on its own:</b> {_e(o["v"])}. Month by month the gain is not proven; it rests on a handful of bear-market bottoms (most of it late October 2008) and was picked after many timing tests, so it is on probation.',
    'lowerT': lambda o: f'<b>The lower-high exit on its own:</b> {_e(o["v"])}. Month by month the gain is not proven (most months it does nothing); the point is the smaller drops. It was designed after looking at the 2007–2011 and 2022 drops, so it is on probation.',
    'fadeT': lambda o: f'<b>The fading-energy filter on its own:</b> {_e(o["v"])}. It was found by studying the plan\'s own losing picks, so it is on probation.',
    'abroad': lambda o: f'<b>Other countries</b> (the same rules on each market\'s own stocks, without the cash week): {_e(o["v"])}.',
    'abroadCash': lambda o: f'<b>The cash week abroad</b> (rebuilt with an equal-weight basket of each index\'s current stocks and the US VIX or the index\'s own volatility; on US data these stand-ins kept most of the gain): {_e(o["v"])}. It fired less often abroad and, in Germany and Japan, at the wrong times, so it looks specific to the US since 2012.',
    'y1927': lambda o: f'<b>Before the data it was built on:</b> {_e(o["v"])}.',
    'plan': lambda o: f'<b>What to plan on:</b> {_e(o["v"])}. The rules were picked on the same history they are tested on, so the headline numbers are the best case.',
}


def recovery_html(rc):
    """Back to the peak: how long the plan took to get back to a previous high after each 15%+ drop, or ''."""
    drops = (rc or {}).get('drops') or []
    if not drops:
        return ''
    MN = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    def md(d): return f'{MN[int(d[5:7]) - 1]} {d[:4]}' if d else 'not yet'
    def mo(x): return f'{x:.0f}' if x >= 0.95 else 'under 1'
    def pc(v): return f'{v * 100:.0f}%'.replace('-', '−')
    top, rest = drops[:8], drops[8:]
    rows = ''.join(f'<tr><td class="num">{pc(x["depth"])}</td><td class="l">{md(x["peak"])}</td><td class="l hide-sm">{md(x["low"])}</td>'
                   f'<td class="l">{md(x["back"])}</td><td class="num"><b>{mo(x["total"])}</b></td>'
                   f'<td class="num hide-sm">{mo(x["down"])}</td><td class="num hide-sm">{mo(x["up"])}</td></tr>' for x in top)
    L, now = rc.get('longest') or {}, rc.get('now') or {}
    lo_, hi_ = (min(x['total'] for x in rest), max(x['total'] for x in rest)) if rest else (0, 0)
    tail = f'The other {len(rest)} took {mo(lo_)} to {mo(hi_)} months each. ' if rest else ''
    cmp_ = ''.join(f'{lab} waited <b>{L[k]["months"]} months</b> ({md(L[k]["peak"])} to {md(L[k]["back"])}). ' for k, lab in (('spy', 'SPY'), ('qqq', 'QQQ')) if L.get(k))
    nowtxt = (f'At the end of the audit ({md(rc.get("end"))}) the plan was {abs(now["below"]) * 100:.1f}% below its high of {md(now["since"])}. ' if now.get('below', 0) < -0.001 else '')
    return ('<p class="section-label" style="margin-top:4px">Back to the peak <span class="hint">how long the plan took to get back to a previous high · '
            f'every drop of {rc.get("cut", 0.15) * 100:.0f}% or more · daily closes from Jan 2000</span></p>'
            f'<p class="note" style="margin:0 0 8px">{rc.get("count")} drops of {rc.get("cut", 0.15) * 100:.0f}% or more in {rc.get("years")} years. '
            f'The typical one took about <b>{mo(rc.get("median", 0))} months</b> from the peak back to it: about {mo(rc.get("medianDown", 0))} falling and {mo(rc.get("medianUp", 0))} climbing back. '
            f'The longest was <b>{L.get("plan", {}).get("months")} months</b>. For comparison, {cmp_}'
            f'Between those drops, half of the plan’s {rc.get("newHighs", 0):,} new highs came within {rc.get("gapMedianDays")} days of the one before, and 90% within {round(rc.get("gap90Days", 0) / 7)} weeks.</p>'
            '<div class="tablebox"><table><thead><tr><th>Drop</th><th class="l">Peak</th><th class="l hide-sm">Low</th><th class="l">Back</th>'
            '<th>Months</th><th class="hide-sm">Months falling</th><th class="hide-sm">Months back</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
            f'<p class="note" style="margin:-4px 0 12px">Back = when the plan was back at its peak; months = from the peak to then, split on wider screens into months falling and months back. The {len(top)} longest waits, longest first. {tail}{nowtxt}A backtest, so expect real waits to run a little longer.</p>')


def wallst_html(ws=None):
    """The Wall Street tests (risk scorecard, Monte Carlo, overfitting) from data/wall_street_tests.json, or ''."""
    if ws is None:
        try:
            with open(WALLST_PATH) as f:
                ws = json.load(f)
        except (OSError, ValueError):
            return ''
    rows = [r for r in ws.get('scorecard') or [] if r.get('k') in WALLST_ROWS]
    if not rows:
        return ''
    sc = ''.join(f'<tr><td class="l w"><b>{_e(WALLST_ROWS[r["k"]][0])}</b><span class="msub">{_e(WALLST_ROWS[r["k"]][1])}</span></td>'
                 f'<td class="num"><b>{_e(r.get("plan"))}</b></td><td class="num hide-sm">{_e(r.get("prev"))}</td><td class="num">{_e(r.get("spy"))}</td>'
                 f'<td class="l m hide-sm">{_e(WALLST_ROWS[r["k"]][1])}</td></tr>' for r in rows)
    mc = ws.get('monteCarlo') or {}
    hz = mc.get('horizons') or []
    mrows = ''.join(f'<tr><td class="l w"><b>{_e(WALLST_MC[r["k"]][0])}</b><span class="msub">{_e(WALLST_MC[r["k"]][1])}</span></td>'
                    + ''.join(f'<td class="num{" hide-sm" if i == 0 else ""}">{_e(v)}</td>' for i, v in enumerate(r.get('v') or []))
                    + f'<td class="l m hide-sm">{_e(WALLST_MC[r["k"]][1])}</td></tr>' for r in mc.get('rows') or [] if r.get('k') in WALLST_MC)
    other = ''.join(f'<li>{WALLST_OTHER[o["k"]](o)}</li>' for o in ws.get('other') or [] if o.get('k') in WALLST_OTHER)
    return ('<style>#wallst table td.m { min-width: 260px; max-width: 420px; white-space: normal; font-size: 0.78rem; color: var(--ink-2); }'
            ' #wallst td.w { min-width: 170px; white-space: normal; } #wallst ul { margin: 10px 0 0; padding-left: 20px; font-size: 0.84rem; color: var(--ink-2); }'
            ' #wallst li { margin-bottom: 6px; } #wallst .tablebox { margin-bottom: 12px; } #wallst .msub { display: none; }'
            ' @media (max-width: 640px) { #wallst .msub { display: block; font-weight: 400; font-size: 0.74rem; color: var(--muted); margin-top: 3px; max-width: 230px; } }</style>'
            '<section id="wallst"><p class="section-label">Wall Street tests <span class="hint">the standard checks a fund manager would run on the '
            f'default plan · {_e(ws.get("period"))} backtest, before tax unless noted · run {_e(ws.get("asOf"))}</span></p>'
            '<div class="tablebox"><table><thead><tr><th class="l">Measure</th><th>Plan</th><th class="hide-sm">Previous plan</th><th>SPY</th>'
            '<th class="l hide-sm">What it means</th></tr></thead><tbody>' + sc + '</tbody></table></div>'
            f'<p class="note" style="margin:-4px 0 12px"><b>Plan</b> = {_e(ws.get("plan"))}. <b>Previous plan</b> = {_e(ws.get("previous"))}. '
            f'{_e(ws.get("source"))}.</p>'
            + recovery_html(ws.get('recovery'))
            + (f'<p class="section-label" style="margin-top:4px">Monte Carlo <span class="hint">{mc.get("paths", 0):,} simulated futures, built by '
               'reshuffling the plan\'s own months in blocks of about a year; the same months for every column</span></p>'
               '<div class="tablebox"><table><thead><tr><th class="l">Result</th>' + ''.join(f'<th{" class=hide-sm" if i == 0 else ""}>{_e(h)}</th>' for i, h in enumerate(hz))
               + '<th class="l hide-sm">What it means</th></tr></thead><tbody>' + mrows + '</tbody></table></div>' if mrows else '')
            + (f'<ul>{other}</ul>' if other else '') + '</section>')


LAB_PATH = os.path.join(ROOT, 'data', 'strategy_backtest.json')
LAB_NOTES = {
    'Current system': 'what the dashboard trades: S&P 500 picks, Boost list + exits + fading-energy filter + rotation + whipsaw + cash week + lower-high exit + rebound rule, no T-bills (managed futures instead of cash)',
    '+ Ignition boost': 'an Ignition in the last 4 weeks also jumps the queue',
    'Top 2 sectors': 'only stocks from the 2 strongest sectors',
    'Top 3 industries': 'only stocks from the 3 strongest industries',
    'Ignition stocks only': 'only stocks with an Ignition in the last 3 months',
    'Repeat gappers': 'only stocks with 2+ big gap-ups in 12 months',
    'Trend leaders near highs': 'only uptrends within 5% of the 52-week high',
    'Semis & AI watchlist': 'only the watchlist names (hindsight)',
    'News gappers only': 'only stocks with a 12%+ news gap in the last 4 weeks',
    'News gappers when SPY up': 'news-gap stocks only while SPY is above its 200-day, else the current picks',
    'Boost only when SPY up': 'current system, news boost switched off while SPY is below its 200-day',
    'News gappers, cash when SPY down': 'news-gap stocks above SPY\'s 200-day, cash (0%) below; no rotation',
    'Top 5 alone': 'the plain stock rule: no boost, exits or rotation',
}


def lab_html(lab=None):
    """The Strategy lab table from data/strategy_backtest.json (scripts/backtest_strategies.py), or ''."""
    if lab is None:
        try:
            with open(LAB_PATH) as f:
                lab = json.load(f)
        except (OSError, ValueError):
            return ''
    periods = lab.get('periods') or {}
    if not periods:
        return ''
    base_name = lab.get('base') or 'Current system'
    keys = list(periods)
    names = list(next(iter(periods.values()))['rows'])
    skip = set(lab.get('hindsight') or [])
    best = {}
    for k in keys:
        cand = [(v.get('annual') or -9, n) for n, v in periods[k]['rows'].items()
                if not v.get('bench') and not v.get('ref') and n not in skip]
        best[k] = max(cand)[1] if cand else None
    head = ''.join(f'<th>{_e(k)}+ /yr</th><th class="hide-sm">after tax</th><th class="hide-sm">worst</th>' for k in keys)
    body = []
    for n in names:
        cells = []
        for k in keys:
            v = periods[k]['rows'].get(n) or {}
            cur = (periods[k]['rows'].get(base_name) or {}).get('annual')
            a = v.get('annual')
            diff = '' if a is None or cur is None or n == base_name or v.get('bench') else \
                f' <span class="{_tone(a - cur)}">({(a - cur) * 100:+.0f})</span>'
            b = ' style="font-weight:700"' if best.get(k) == n else ''
            cells.append(f'<td class="num"{b} title="total {_p(v.get("total"), 0)}">{_p(a)}{diff}</td>'
                         f'<td class="num hide-sm">{_p(v.get("afterTax"))}</td>'
                         f'<td class="num hide-sm neg">{_p(v.get("maxDD"), 0)}</td>')
        row0 = next(iter(periods.values()))['rows'].get(n) or {}
        muted = row0.get('bench') or row0.get('ref')
        label = f'<b>{_e(n)}</b>' if n == base_name else _e(n)
        note = LAB_NOTES.get(n, 'buy and hold' if row0.get('bench') else '')
        body.append(f'<tr{" class=bench" if muted else ""}><td class="l w">{label}<span class="sub">{_e(note)}</span></td>{"".join(cells)}</tr>')
    tax = lab.get('taxRate')
    return ('<style>#lab tr.bench td { color: var(--muted); } #lab td.w { min-width: 210px; } #lab td .sub { max-width: 260px; white-space: normal; }</style>'
            '<section id="lab"><p class="section-label">Strategy lab <span class="hint">new ideas inside the current system '
            '(the live plan\'s own rules: S&P 500 members, Boost list, exits, fading-energy filter, rotation, whipsaw, narrow-market cash week, lower-high exit, rebound rule and no-T-bills swap; only which stocks may be bought changes) · weekly, 0.05% cost · '
            f'to {_e(lab.get("asOf"))}</span></p>'
            '<div class="tablebox"><table><thead><tr><th class="l">Strategy</th>' + head + '</tr></thead><tbody>'
            + ''.join(body) + '</tbody></table></div>'
            '<p class="note">Per-year return from each start to today, before tax (difference vs the current system in points); '
            f'<b>after tax</b> = a regular taxable account, each year\'s gain taxed at {round((tax or 0.35) * 100)}% as short-term '
            '(losses carried forward; buy-and-hold rows taxed once at 20%) - in an IRA / Roth use the before-tax column; '
            'worst = biggest peak-to-trough drop. Bold = best per start, ignoring the watchlist and reference rows. '
            '<b>Caveats:</b> stocks that left the indexes or went bust are missing, which flatters every row, more so from 2000. '
            'The Semis &amp; AI watchlist was picked in 2026 knowing AI won, so its row is hindsight. Rebuilt every 3 months by '
            '<code>scripts/backtest_strategies.py</code>. Not investment advice.</p></section>')


def research_html():
    """The five-year winners research section (documents/winners_research.html,
    a static HTML fragment), or '' when the file is missing."""
    try:
        with open(RESEARCH_PATH) as f:
            return f.read()
    except OSError:
        return ''


def overlay_lib():
    """The shared overlay line chart (CSS + mtlOverlay script) from render_html."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render_html import OVERLAY_CSS, OVERLAY_JS
    return OVERLAY_CSS + OVERLAY_JS


TRACK_PATH = os.path.join(ROOT, 'data', 'track_record.json')
TRACK_KEYS = ('rotation', 'boost100', 'strategy', 'SPY', 'QQQ')
REPLAY_ONLY = ('plan', 'boost', 'cushion', 'calls', 'cushionCalls', 'monthly', 'monthlyBoost', 'steps', 'guard')


def calendar_years(curve):
    """{year: return} from [[date, value], ...]: each year's last value over the year before's (the first year
    from the first value)."""
    out, prev, cur_y, last = {}, curve[0][1] if curve else None, None, None
    for d, v in curve:
        y = d[:4]
        if cur_y is not None and y != cur_y:
            out[cur_y] = round(last / prev - 1, 4)
            prev = last
        cur_y, last = y, v
    if cur_y is not None:
        out[cur_y] = round(last / prev - 1, 4)
    return out


def with_track_record(scan, path=TRACK_PATH):
    """The track record from the point-in-time backtest (data/track_record.json: the stocks in the S&P 500 at each
    date that have price history - 58% of members in 2000 rising to over 90% since 2020 -, 0.15% slippage, from 2000) instead of the scan's replay, which only knows today's
    index members and so flatters every year. Each backtest line carries on with the replay's own daily moves after
    the backtest ends. Lines with no backtest behind them leave the track record."""
    try:
        with open(path) as f:
            T = json.load(f)
    except (OSError, ValueError):
        return scan
    curves = scan.get('curves') or {}
    if not curves.get('strategy'):
        return scan
    out, C, Y = dict(scan), dict(curves), dict(scan.get('years') or {})
    for k in TRACK_KEYS:
        line = [list(p) for p in (T.get('series') or {}).get(k) or []]
        if not line:
            continue
        end, base = line[-1][0], line[-1][1]
        rep_ = curves.get(k) or []
        anchor = next((v for d, v in reversed(rep_) if d <= end), None)
        if anchor:
            line += [[d, round(base * v / anchor, 4)] for d, v in rep_ if d > end]
        C[k] = line
        Y[k] = calendar_years(line)
    for k in REPLAY_ONLY:
        C.pop(k, None)
        Y.pop(k, None)
    out['curves'], out['years'] = C, Y
    TS = T.get('stats') or {}
    out['track'] = dict(source=T.get('source'), start=T.get('start'), end=T.get('end'), stats=TS)
    if TS.get('strategy'):
        out['stats'] = dict(scan.get('stats') or {}, strategy=dict((scan.get('stats') or {}).get('strategy') or {}, annual=TS['strategy']['annual'], maxDD=TS['strategy']['maxDD']))
    return out


def render(scan, growth=None):
    scan = with_track_record(scan)
    # Escape "</" so a company name can never close the <script> block early.
    page = PAGE.replace('__GROWTH__', growth_html() if growth is None else growth).replace('__OVLIB__', overlay_lib(), 1)
    page = page.replace('__WALLST__', wallst_html(), 1)
    page = page.replace('__RESEARCH__', widenet_html(scan) + ignition_html() + lab_html() + research_html(), 1)
    page = page.replace('__ISSUES__', issues_html(scan), 1)
    page = page.replace('__EVENTS__', events_html(), 1)
    sys.path.insert(0, ROOT)
    from mtl.events import ADD_URL   # the events page's "Add news" form
    page = page.replace('__ADD_URL__', ADD_URL, 1)
    return page.replace('__DATA__', json.dumps(scan, separators=(',', ':')).replace('</', '<\\/'))


EVENTS_SECTION = r'''<section id="events-find"><p class="section-label">Market events <span class="hint">search __N__ events since 2000
    and how the S&amp;P 500 moved · <a href="events.html">all events →</a></span></p>
  <div class="card evf" role="search">
    <input class="evf-q" id="ev-q" type="search" placeholder="Search events (Fed, COVID, 2008…)" aria-label="Search market events" autocomplete="off">
    <div class="evf-mv"><select id="ev-per" aria-label="Which move"><option value="day">Day</option><option value="month">1 month</option></select>
      <select id="ev-dir" aria-label="Direction"><option value="any">up/down</option><option value="up">up</option><option value="down">down</option></select>
      <span class="evf-n"><span aria-hidden="true">≥</span><input id="ev-min" type="number" inputmode="decimal" min="0" step="0.5" placeholder="0" aria-label="Moved at least this many percent"><span>%</span></span>
      <button id="ev-clear" type="button" hidden>Clear</button></div>
    <p class="evf-count" id="ev-count" aria-live="polite" hidden></p>
    <table id="ev-res" hidden><thead><tr><th>Date</th><th>Event</th><th class="n">Day</th><th class="n">1 month</th></tr></thead><tbody></tbody></table>
    <p class="evf-more" id="ev-more" hidden><a id="ev-all" href="events.html">See them all on the events page →</a></p>
  </div>
<script type="application/json" id="ev-data">__ROWS__</script>
<script>
__MATCH__
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var rows = JSON.parse($('ev-data').textContent), q = $('ev-q'), per = $('ev-per'), dir = $('ev-dir'), min = $('ev-min'),
      clear = $('ev-clear'), count = $('ev-count'), table = $('ev-res'), body = table.tBodies[0], more = $('ev-more'), SHOW = __SHOW__;
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function pct(x) {
    var td = document.createElement('td');
    td.className = 'n';
    if (x === null || x === undefined) { td.textContent = '–'; td.classList.add('muted'); return td; }
    td.textContent = (x > 0 ? '+' : '') + (x * 100).toFixed(1).replace('-', '−') + '%';
    if (x) td.classList.add(x > 0 ? 'pos' : 'neg');
    return td;
  }
  function apply() {
    var f = evFilter(q, per, dir, min), on = evOn(f);
    clear.hidden = !on; count.hidden = !on; body.textContent = '';
    if (!on) { table.hidden = true; more.hidden = true; return; }
    var hits = rows.filter(function (r) { return evMatch(r[5], r[3], r[4], f); });
    count.textContent = hits.length ? 'Found ' + hits.length + ' of ' + rows.length + ' events' +
      (hits.length > SHOW ? ' · newest ' + SHOW + ' shown here' : '') : 'No events match. Try fewer words or a smaller move.';
    hits.slice(0, SHOW).forEach(function (r) {
      // built with text nodes, never innerHTML: "added by you" items are free text from the form
      var tr = document.createElement('tr'), d = document.createElement('td'), td = document.createElement('td'), p = r[0].split('-');
      var w = document.createElement('div');   // the event, cut to two lines (full text on the events page)
      w.className = 'clamp'; td.appendChild(w);
      d.className = 'd';
      var y = document.createElement('small');
      d.textContent = MON[+p[1] - 1] + ' ' + (+p[2]); y.textContent = p[0]; d.appendChild(y);
      if (r[6]) {
        var a = document.createElement('a');
        a.href = r[6]; a.target = '_blank'; a.rel = 'noopener'; a.textContent = r[1];
        w.appendChild(a);
      } else w.textContent = r[1];
      if (r[2]) {
        var t = document.createElement('span');
        t.className = 'tag'; t.textContent = r[2];
        w.appendChild(document.createTextNode(' ')); w.appendChild(t);
      }
      tr.appendChild(d); tr.appendChild(td); tr.appendChild(pct(r[3])); tr.appendChild(pct(r[4]));
      body.appendChild(tr);
    });
    table.hidden = !hits.length;
    more.hidden = hits.length <= SHOW;
    $('ev-all').textContent = 'See all ' + hits.length + ' on the events page →';
    var h = new URLSearchParams();
    if (q.value.trim()) h.set('q', q.value.trim());
    if (per.value !== 'day') h.set('per', per.value);
    if (dir.value !== 'any') h.set('dir', dir.value);
    if (min.value) h.set('min', min.value);
    $('ev-all').href = 'events.html#' + h.toString();
  }
  [q, min].forEach(function (el) { el.addEventListener('input', apply); });
  [per, dir].forEach(function (el) { el.addEventListener('change', apply); });
  clear.addEventListener('click', function () { q.value = ''; min.value = ''; dir.value = 'any'; per.value = 'day'; apply(); q.focus(); });
  apply();
})();
</script></section>
'''


def events_html(path=None, show=5):
    """The market events search: the events page's search box and move filter (same matching, mtl/events.py). It
    searches every event but lists at most `show` hits here, newest first, each cut to two lines, so the card's height
    has a fixed ceiling; the rest are a link away on the events page, with the same search filled in."""
    sys.path.insert(0, ROOT)
    from mtl import events as ev
    try:
        doc = ev.load(path) if path else ev.load()
    except (OSError, ValueError):
        return ''
    evs = sorted(doc['events'], key=lambda e: e['d'], reverse=True)
    rows = [[e['d'], e['what'], ev.tag(e), e.get('day'), e.get('month'), ev.search_text(e),
             e['link'] if (e.get('link') or '').startswith(('http://', 'https://')) else ''] for e in evs]
    # every '<' and '__' escaped, so form text can't end the script block or hit the page's __PLACEHOLDERS__
    data = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('__', '_\\u005f')
    return (EVENTS_SECTION.replace('__N__', str(len(rows)), 1).replace('__SHOW__', str(show), 1)
            .replace('__MATCH__', ev.MATCH_JS, 1).replace('__ROWS__', data, 1))


ISSUES_PATH = os.path.join(ROOT, 'docs', 'issues.html')
ISSUES_SHOW = 5   # the scanner page lists this many; the rest are on docs/issues.html


def issue_rows(scan, entries=None, today=None):
    """[(date, text)]: every data problem and failed run in the issues log (mtl/health.py) from the last 14 days,
    newest first, plus a stale side scan or track record."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    sys.path.insert(0, ROOT)
    from mtl import health
    if entries is None:
        try:
            entries = health.load()
        except ValueError:
            entries = [dict(d=scan.get('asOf') or '', src='run', at='', text='The issues log (data/issues_log.json) is damaged and could not be read.')]
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    rows = [(e['d'], e['text']) for e in health.recent(entries, today)]
    try:
        with open(IGNITION_PATH) as f:
            ig = json.load(f).get('asOf')
    except (OSError, ValueError):
        ig = None
    if scan.get('asOf') and (ig is None or ig < scan['asOf']):
        rows.insert(0, (scan['asOf'], f"The Next big thing scan is from {ig or 'no date'}, not {scan['asOf']}: tonight's scan failed or was skipped (it never affects the plan)."))
    if not scan.get('track'):
        rows.insert(0, (scan.get('asOf') or '', 'The point-in-time track record (data/track_record.json) is missing, so the growth chart shows the replay on today\'s index members, which flatters every year.'))
    return rows


def widenet_html(scan):
    """The "Wide net" watch (information only, mtl/widenet.py): the strongest of about 40 assets the plan never holds,
    scored like the plan scores stocks, with a flag for a fresh breakout after a base. '' when the scan has none."""
    W = ((scan.get('plan') or {}).get('auto') or {}).get('wideNet')
    if not W or not W.get('rows'):
        return ''

    def flags(r):
        return ((' <span class="tag buy">Breakout after a base</span>' if r.get('breakout') else '')
                + (' <span class="tag">Near 52w high</span>' if r.get('nearHigh') and not r.get('breakout') else ''))
    rows = ''.join(
        f'<tr><td class="num">{i}</td><td class="l"><b>{_e(r["t"])}</b> <span class="muted">{_e(r["name"])}</span>{flags(r)}</td>'
        f'<td class="num {_tone(r["score"])}">{_p(r["score"], 0)}</td>'
        f'<td class="num">{"yes" if r.get("beats") else "no"}</td>'
        f'<td class="num hide-sm {_tone(r.get("r1m"))}">{_p(r.get("r1m"), 1)}</td>'
        f'<td class="num">{_p(r.get("offHigh"), 1)}</td></tr>'
        for i, r in enumerate(W['rows'], 1))
    shown = {r['t'] for r in W['rows']}
    extra = [r for r in W.get('breakouts') or [] if r['t'] not in shown]
    brk = ('<p class="note"><b>Also breaking out after a base:</b> '
           + ' · '.join(f'{_e(r["t"])} ({_e(r["name"])}, {_p(r["score"], 0)})' for r in extra) + '</p>') if extra else ''
    return ('<section id="widenet"><p class="section-label">Wide net <span class="hint">information only · the strongest of '
            f'{W.get("n", 0)} assets the plan never holds · close of {_e(W.get("asOf"))}</span></p>'
            '<div class="tablebox"><table><thead><tr><th>#</th><th class="l">Asset</th>'
            '<th title="Gain from 6 months ago to 1 month ago, the score the plan uses for stocks">6m score</th>'
            f'<th title="Score above SPY\'s ({_p(W.get("spyScore"), 0)}) and above zero">Beats SPY</th>'
            '<th class="hide-sm">Last month</th><th>Off 52w high</th>'
            f'</tr></thead><tbody>{rows}</tbody></table></div>' + brk +
            '<p class="note">Metals, energy, farm goods, sector and theme funds, country funds, currencies, real estate and bitcoin '
            '(IBIT), ranked the way the plan ranks stocks. <b>Breakout after a base</b> = its first new 52-week closing high after '
            'at least 3 months without one, in the last week: the kind of start big runs share. The plan never buys these. '
            'As a "wild card" fifth slot (20% in the strongest each week) it made 42.3% a year from 2000 against 44.4% for the plan, '
            'with a smaller worst drop (−27% against −32%); the best version only beat it on risk thanks to bitcoin in 2017. '
            'So this is a list to look at, not a trade.</p></section>\n')


def issues_html(scan, entries=None, today=None, show=ISSUES_SHOW):
    """The "Issues (last 2 weeks)" card at the bottom of the page: the newest `show` issues, each cut to two lines,
    so the card's height has a fixed ceiling; the full list is on docs/issues.html."""
    rows = issue_rows(scan, entries, today)
    src = '<a href="https://github.com/danreed001-droid/NIBII/issues" target="_blank" rel="noopener">GitHub issues</a>'
    if rows:
        items = ''.join(f'<li><div class="clamp"><span class="when">{_e(d_)}</span>{_e(t_)}</div></li>' for d_, t_ in rows[:show])
        more = (f'<p class="more"><a href="issues.html">+ {len(rows) - show} more · see all →</a></p>'
                if len(rows) > show else '')
        body = f'<ul>{items}</ul>{more}'
    else:
        body = '<p class="note"><span class="ok">✓ No issues in the last 2 weeks.</span> Every nightly run finished and its data checked out.</p>'
    return ('<section id="issues"><p class="section-label">Issues <span class="hint">last 2 weeks · '
            '<a href="issues.html">issues page →</a></span></p>'
            '<div class="card issues-card">' + body +
            f'<p class="note">Data problems and failed runs were also sent to you as {src} when they happened. Data problems '
            'are listed by the close they were found on, a failed run by the day it ran; older ones drop off after 14 days.</p>'
            '</div></section>\n')


def issues_page(scan, entries=None, today=None):
    """docs/issues.html: every issue from the last 2 weeks, in full (the scanner page shows the newest few)."""
    rows = issue_rows(scan, entries, today)
    items = ''.join(f'<li><span class="when">{_e(d_)}</span>{_e(t_)}</li>' for d_, t_ in rows) or \
        '<li><span class="ok">✓ No issues in the last 2 weeks.</span></li>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Scanner Issues</title>
<style>
:root {{ --bg: #fbfaf7; --ink: #1d1c1a; --muted: #6f6d67; --line: #e1e0d9; --pos: #0a8f0a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #161615; --ink: #ecebe6; --muted: #98968f; --line: #2c2c2a; --pos: #3fbf5f; }} }}
:root[data-theme="dark"] {{ --bg: #161615; --ink: #ecebe6; --muted: #98968f; --line: #2c2c2a; --pos: #3fbf5f; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 -apple-system, system-ui, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 760px; margin: 0 auto; padding: 18px 16px 48px; }}
.nav a {{ color: var(--muted); text-decoration: none; font-size: 0.85rem; }}
h1 {{ font-size: 1.6rem; margin: 10px 0 6px; }} p.note {{ color: var(--muted); font-size: 0.86rem; }}
ul {{ list-style: none; padding: 0; margin: 12px 0 0; }}
li {{ padding: 9px 0; border-top: 1px solid var(--line); font-size: 0.9rem; }} li:first-child {{ border-top: 0; }}
.when {{ color: var(--muted); font-size: 0.78rem; margin-right: 8px; white-space: nowrap; }} .ok {{ color: var(--pos); font-weight: 600; }}
</style></head><body><div class="wrap">
<div class="nav"><a href="scanner.html">← Top 5 Strongest</a></div>
<h1>Issues, last 2 weeks</h1>
<p class="note">{f"{len(rows)} issue{'' if len(rows) == 1 else 's'}, newest first: d" if rows else 'D'}ata problems are listed by the close they were
found on, a failed run by the day it ran. Older ones drop off after 14 days.</p>
<ul>{items}</ul>
</div></body></html>
'''


def main():
    if not os.path.exists(DATA_PATH):
        sys.exit(f"{DATA_PATH} not found - run: python scripts/momentum_scan.py")
    with open(DATA_PATH) as f:
        scan = json.load(f)
    page = render(scan)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        f.write(page)
    with open(ISSUES_PATH, 'w') as f:
        f.write(issues_page(with_track_record(scan)))   # the same rows the scanner page's card lists
    print(f"wrote {OUT_PATH} and {ISSUES_PATH}")


if __name__ == '__main__':
    main()

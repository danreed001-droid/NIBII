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
  --s-strat: #3987e5; --s-spy: #c98500; --s-qqq: #d55181; --s-plan: #3fb8a0;
  color-scheme: dark;
}
:root[data-mtl-theme="light"] {
  --bg: #f4f3ef; --surface: #fdfdfc; --surface-2: #f0efea; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  --pos: #0a8f0a; --neg: #c43232; --grid: #e1e0d9;
  --s-strat: #2a78d6; --s-spy: #eda100; --s-qqq: #e87ba4; --s-plan: #13866f;
  color-scheme: light;
}
* { box-sizing: border-box; }
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
.ybar { display: flex; align-items: center; gap: 6px; }
.ybar i { display: block; height: 8px; border-radius: 3px; background: var(--c); min-width: 2px; }
.ybar.neg i { background: var(--neg); opacity: 0.8; }

/* on deck + trades */
.deck { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(250px, 100%), 1fr)); gap: 8px; }
.dk { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 9px 12px; display: grid;
  grid-template-columns: 34px 1fr auto; gap: 2px 10px; align-items: center; }
.dk .rank { font-size: 0.8rem; }
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
.plan-controls label { font-size: 0.8rem; color: var(--ink-2); display: inline-flex; align-items: center; gap: 8px; }
.money-in { display: inline-flex; align-items: center; border: 1px solid var(--hairline); border-radius: 8px; background: var(--surface-2); padding: 0 8px; }
.money-in span { color: var(--muted); }
.money-in input { font: 600 0.95rem ui-monospace, monospace; width: 110px; border: 0; background: transparent; color: var(--ink); padding: 6px 4px; outline: none; }
.money-in:focus-within { border-color: var(--accent); }
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
  <p class="subtitle">Every Friday close, rank the S&amp;P 500 + Nasdaq-100 by 6-month performance (skipping the latest month), hold the
    5 strongest that beat SPY, and keep each while it stays in the top 10.</p>
  <div class="meta" id="meta"></div>
</div></div>

<div class="wrap">
  <div class="banner" id="banner"></div>

  <p class="section-label">Current holdings <span class="hint" id="hold-hint"></span></p>
  <div class="holdings" id="holdings"></div>

  <p class="section-label">Your plan <span class="hint" id="plan-hint"></span></p>
  <div class="plan">
    <div class="card">
      <div class="plan-controls">
        <label>Account <span class="money-in"><span>$</span><input id="acct" type="text" inputmode="numeric" value="10,000" aria-label="Account size in dollars"></span></label>
        <label>Mix <span class="seg" id="mix-seg"></span></label>
      </div>
      <table class="alloc" id="alloc"></table>
      <div class="plan-stats" id="plan-stats"></div>
    </div>
    <div class="card">
      <p class="chart-title">The sleeve this week</p>
      <p class="chart-sub" id="sleeve-sub"></p>
      <ul class="assets" id="assets"></ul>
      <p class="note" id="sleeve-note"></p>
    </div>
  </div>

  <p class="section-label">Track record since 2020 <span class="hint">$100 in the rule vs buying and holding</span></p>
  <div class="stats" id="stats"></div>
  <div class="two" style="margin-top:12px">
    <div class="card">
      <div class="chart-head"><div><p class="chart-title">Growth of $100</p><p class="chart-sub">Weekly rebalanced, 0.05% trading cost · plan = top 5 + sleeve, reset weekly</p></div>
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
      <p class="section-label">On deck <span class="hint">ranks 6–20 · climbing ▲ / slipping ▼ vs last week</span></p>
      <div class="deck" id="deck"></div>
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
    <li><b>The rule.</b> Score = return from 6 months ago to 1 month ago. Each Friday close: a stock must beat SPY's score to qualify; buy the top 5 in equal weight; a holding stays while it ranks in the top 10, otherwise it is replaced by the best-ranked stock not held. The banner shows what that would do at today's close; trades only happen on Fridays.</li>
    <li><b>Fair test.</b> S&amp;P 500 stocks count only from the day they joined the index. The 15 Nasdaq-only members have no published join dates, so the track record carries some hindsight from them; the S&amp;P-only version made about +1,219% over the same period (see Backtests). Stocks that left either index since 2020 are missing, which also flatters the record. Small caps are deliberately excluded: adding the Russell 2000 cut the result to about +509% with a −73% drawdown.</li>
    <li><b>Risk.</b> Five stocks is concentrated: drawdowns near −38% happened, it trailed QQQ in 2020, 2023 and 2024, and 2026's gains came mostly from one theme (memory/storage). Prices from Yahoo Finance, split-adjusted closes (benchmarks include dividends). A mechanical rule's output, not investment advice.</li>
    <li>Generated by <code>scripts/momentum_scan.py</code> + <code>scripts/render_scanner.py</code> in <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a> · <span id="gen"></span></li>
  </ul></footer>
</div>

<script type="application/json" id="scan-data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('scan-data').textContent);
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
      '<span>Last rebalance <b>' + fmtDate(D.lastRebalance, { month: 'short', day: 'numeric' }) + '</b></span>' +
      '<span>Next rebalance <b>Fri ' + fmtDate(D.nextRebalance, { month: 'short', day: 'numeric' }) + '</b></span>' +
      '<span>Universe <b>' + D.universe.total + '</b> stocks</span>';
  }
  meta(); setInterval(meta, 60000);
  $('gen').textContent = 'built ' + gen.toLocaleString();

  // rebalance banner
  var ch = D.changes;
  $('banner').innerHTML = (ch.sell.length || ch.buy.length)
    ? '<b>If it rebalanced at ' + fmtDate(D.asOf, { weekday: 'short', month: 'short', day: 'numeric' }) + '’s close:</b>' +
      ch.sell.map(function (t) { return '<span class="tag sell">sell ' + esc(t) + '</span>'; }).join('') +
      ch.buy.map(function (t) { return '<span class="tag buy">buy ' + esc(t) + '</span>'; }).join('') +
      '<span class="muted">Trades only happen at the Friday close.</span>'
    : '<b>No changes</b><span class="muted">At ' + fmtDate(D.asOf, { weekday: 'short', month: 'short', day: 'numeric' }) + '’s close all five holdings still rank in the top ' + D.rule.keepRank + '. Next check: Friday ' + fmtDate(D.nextRebalance, { month: 'short', day: 'numeric' }) + '.</span>';

  function spark(vals, w, h) {
    if (!vals || vals.length < 2) return '';
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), n = vals.length;
    var d = vals.map(function (v, i) { return (i ? 'L' : 'M') + (i / (n - 1) * w).toFixed(1) + ' ' + (h - 3 - (v - lo) / (hi - lo || 1) * (h - 6)).toFixed(1); }).join('');
    var c = vals[n - 1] >= vals[0] ? 'var(--pos)' : 'var(--neg)';
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true"><path d="' + d + '" style="stroke:' + c + '" vector-effect="non-scaling-stroke"></path></svg>';
  }

  // holdings
  $('hold-hint').textContent = 'equal weight · 6-1m = return from 6 months to 1 month ago';
  $('holdings').innerHTML = D.holdings.slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); }).map(function (h) {
    return '<article class="hold"><div class="hold-top"><span class="rank">#' + (h.rank || '–') + '</span>' + (h.ndx ? '<span class="tag ndx" title="Nasdaq-100 only">NDX</span>' : '') + '</div>' +
      '<div><div class="tk">' + esc(h.t) + '</div><div class="nm" title="' + esc(h.n) + '">' + esc(h.n) + '</div></div>' +
      '<div><div class="big ' + tone(h.score) + '">' + pct(h.score, 0) + '</div><div class="small">6-1m · ' + pct(h.vsSpy, 0) + ' vs SPY</div></div>' +
      spark(h.spark, 200, 44) +
      '<div class="kv"><span>Held</span><b>' + (h.weeks || 0) + ' wk</b><span>Since buy</span><b class="' + tone(h.sinceRet) + '">' + pct(h.sinceRet) + '</b>' +
      '<span>1 month</span><b class="' + tone(h.r1m) + '">' + pct(h.r1m) + '</b><span>Off high</span><b>' + pct(h.offHigh) + '</b></div>' +
      '<div style="display:flex;justify-content:space-between;align-items:center"><span class="small">' + esc(h.sec) + '</span>' + trend(h.trend) + '</div></article>';
  }).join('');

  // plan: account size x leverage -> dollars per position
  (function () {
    var P = D.plan, SL = D.sleeve;
    if (!P || !SL) { $('plan-hint').textContent = ''; return; }
    var mix = P['default'], acct = 10000;
    try { mix = localStorage.getItem('nibii-plan-mix') || mix; acct = +(localStorage.getItem('nibii-plan-acct') || acct) || 10000; } catch (e) {}
    if (P.splits.indexOf(mix) < 0) mix = P['default'];
    $('mix-seg').innerHTML = P.splits.map(function (m) { return '<button type="button" data-v="' + m + '">' + m + '</button>'; }).join('');
    function usd(v) { return '$' + (v < 100 ? v.toFixed(2) : Math.round(v).toLocaleString()); }
    var name = {}; SL.assets.forEach(function (a) { name[a.t] = a; });
    function draw() {
      document.querySelectorAll('#mix-seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === mix)); });
      var split = +mix.split('/')[0] / 100, stocks = acct * split, sleeve = acct - stocks, per = stocks / D.rule.topN;
      $('plan-hint').textContent = mix.split('/')[0] + '% top 5 · ' + mix.split('/')[1] + '% sleeve · no leverage · reset every Friday';
      var hs = D.holdings.slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); });
      var sp = name[SL.held] || {};
      function sh(v, px) { if (!px) return ''; var n = v / px; return '≈' + n.toFixed(n < 10 ? 2 : 0) + ' sh'; }
      var rows = hs.map(function (h) {
        return '<tr><td><span class="sw" style="--c:var(--s-strat)"></span><b>' + esc(h.t) + '</b> <span class="muted nm2">' + esc(h.n) + '</span></td>' +
          '<td class="r">' + usd(per) + '</td><td class="r muted">' + sh(per, h.close) + '</td></tr>';
      }).join('');
      rows += '<tr><td><span class="sw" style="--c:var(--s-plan)"></span><b>' + esc(SL.held) + '</b> <span class="muted">sleeve<span class="nm2"> · ' + esc(sp.n || '') + '</span></span></td>' +
        '<td class="r">' + usd(sleeve) + '</td><td class="r muted">' + sh(sleeve, sp.close) + '</td></tr>';
      rows += '<tr class="sum"><td>Total</td><td class="r">' + usd(acct) + '</td><td></td></tr>';
      $('alloc').innerHTML = '<tbody>' + rows + '</tbody>';
      var st = P.stats[mix], S0 = D.stats.strategy;
      $('plan-stats').innerHTML = '<span>Since 2020 at ' + mix + ': <b class="pos">' + pct(st.annual, 0) + '</b> a year, worst drop <b class="neg">' + pct(st.maxDD, 0) + '</b></span>' +
        '<span class="muted">Top 5 alone: ' + pct(S0.annual, 0) + ' a year, worst drop ' + pct(S0.maxDD, 0) + '</span>';
    }
    $('mix-seg').onclick = function (e) { var b = e.target.closest('button'); if (!b) return; mix = b.getAttribute('data-v'); try { localStorage.setItem('nibii-plan-mix', mix); } catch (x) {} draw(); };
    var inp = $('acct');
    inp.value = Math.round(acct).toLocaleString();
    inp.oninput = function () { var v = +inp.value.replace(/[^0-9.]/g, ''); if (v > 0) { acct = v; try { localStorage.setItem('nibii-plan-acct', String(v)); } catch (x) {} draw(); } };
    inp.onblur = function () { inp.value = Math.round(acct).toLocaleString(); };
    draw();

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
    $('sleeve-note').innerHTML = (SL.preview !== SL.held ? '<b>If it rebalanced at ' + fmtDate(D.asOf, { month: 'short', day: 'numeric' }) + '’s close: switch ' + esc(SL.held) + ' → ' + esc(SL.preview) + '.</b> ' : '') +
      'Sleeve alone since 2020: ' + pct(ss.annual, 0) + ' a year, worst drop ' + pct(ss.maxDD, 0) + '. 6-month returns, dividends included.';
  })();

  // stats
  var S = D.stats;
  function tile(label, value, sub, cls) { return '<div class="stat"><span class="stat-label">' + label + '</span><span class="stat-value ' + (cls || '') + '">' + value + '</span><span class="stat-sub">' + sub + '</span></div>'; }
  $('stats').innerHTML =
    tile('Since 2020', pct(S.strategy.total, 0), pct(S.strategy.annual, 0) + ' a year', 'pos') +
    tile('vs SPY / QQQ', pct(S.SPY.total, 0) + ' / ' + pct(S.QQQ.total, 0), pct(S.SPY.annual, 0) + ' / ' + pct(S.QQQ.annual, 0) + ' a year') +
    tile('Last 12 months', pct(S.strategy.oneYear, 0), 'SPY ' + pct(S.SPY.oneYear, 0) + ' · QQQ ' + pct(S.QQQ.oneYear, 0), tone(S.strategy.oneYear)) +
    tile('Worst drop', pct(S.strategy.maxDD, 0), 'SPY ' + pct(S.SPY.maxDD, 0) + ' · QQQ ' + pct(S.QQQ.maxDD, 0), 'neg');

  // growth chart
  var SER = [['strategy', 'Top 5 strongest', 'var(--s-strat)', 'main'], ['QQQ', 'QQQ', 'var(--s-qqq)', ''], ['SPY', 'SPY', 'var(--s-spy)', '']];
  if (D.curves.plan && D.plan) SER.splice(1, 0, ['plan', 'Plan ' + D.plan['default'], 'var(--s-plan)', 'main']);
  var scale = 'log';
  try { scale = localStorage.getItem('nibii-mom-scale') || 'log'; } catch (e) {}
  $('legend').innerHTML = SER.map(function (s) { return '<span><i class="key" style="--c:' + s[2] + '"></i>' + s[1] + '</span>'; }).join('');
  function day(s) { return Date.parse(s + 'T12:00:00Z'); }
  function money(v) { return '$' + (v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(0)); }
  function drawGrowth() {
    document.querySelectorAll('#scale-seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === scale)); });
    var box = $('growth'); box.innerHTML = '';
    var series = SER.map(function (s) { return { name: s[1], c: s[2], cls: s[3], pts: D.curves[s[0]].map(function (p) { return [day(p[0]), p[1]]; }) }; });
    var W = Math.max(320, box.clientWidth), H = Math.round(Math.min(380, Math.max(240, W * 0.5))), m = { l: 56, r: 64, t: 10, b: 26 };
    var xs = [], ys = [];
    series.forEach(function (s) { s.pts.forEach(function (p) { xs.push(p[0]); ys.push(p[1]); }); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    var log = scale === 'log', f = log ? Math.log : function (v) { return v; };
    var ticks = [];
    if (log) { [50, 100, 200, 500, 1000, 2000, 5000, 10000].forEach(function (v) { if (v >= lo * 0.9 && v <= hi * 1.1) ticks.push(v); }); }
    else { var st = Math.pow(10, Math.floor(Math.log10((hi - lo) / 4))); st = (hi - lo) / st > 20 ? st * 5 : (hi - lo) / st > 8 ? st * 2 : st; for (var v = Math.ceil(lo / st) * st; v <= hi; v += st) ticks.push(v); }
    var y0 = f(Math.min(lo, ticks[0] || lo)), y1 = f(Math.max(hi, ticks[ticks.length - 1] || hi));
    function X(t) { return m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r); }
    function Y(v) { return m.t + (1 - (f(v) - y0) / (y1 - y0 || 1)) * (H - m.t - m.b); }
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Growth of $100' }), g = el('g', { class: 'grid axis' });
    ticks.forEach(function (v) { g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) })); var t = el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }); t.textContent = money(v); g.appendChild(t); });
    for (var yr = new Date(x0).getUTCFullYear() + 1; Date.UTC(yr, 0, 1) <= x1; yr++) { var tx = el('text', { x: X(Date.UTC(yr, 0, 1)), y: H - 6, 'text-anchor': 'middle' }); tx.textContent = yr; g.appendChild(tx); }
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
  drawGrowth();
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(drawGrowth, 150); });

  // years
  var ys = Object.keys(D.years.strategy).sort(), maxAbs = 0;
  var YK = D.years.plan ? ['strategy', 'plan', 'SPY', 'QQQ'] : ['strategy', 'SPY', 'QQQ'];
  var YC = { strategy: 'var(--s-strat)', plan: 'var(--s-plan)', SPY: 'var(--s-spy)', QQQ: 'var(--s-qqq)' };
  var YH = { strategy: 'Top 5', plan: 'Plan ' + (D.plan ? D.plan['default'] : ''), SPY: 'SPY', QQQ: 'QQQ' };
  ys.forEach(function (y) { YK.forEach(function (k) { maxAbs = Math.max(maxAbs, Math.abs(D.years[k][y] || 0)); }); });
  var barMax = YK.length > 3 ? 26 : 70;
  function ybar(v, c) { var w = Math.max(2, Math.abs(v) / maxAbs * barMax); return '<span class="ybar' + (v < 0 ? ' neg' : '') + '"><i style="--c:' + c + ';width:' + w + 'px"></i><span class="num ' + tone(v) + '">' + pct(v, 0) + '</span></span>'; }
  $('years').innerHTML = '<thead><tr><th class="l">Year</th>' + YK.map(function (k) { return '<th class="l">' + YH[k] + '</th>'; }).join('') + '</tr></thead><tbody>' +
    ys.map(function (y) { return '<tr><td class="l">' + y + '</td>' + YK.map(function (k) { return '<td class="l">' + ybar(D.years[k][y] || 0, YC[k]) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody>';
  $('ytd-note').textContent = ys[ys.length - 1] + ' is year to date (' + fmtDate(D.asOf, { month: 'short', day: 'numeric' }) + ')';

  // on deck
  $('deck').innerHTML = D.table.filter(function (r) { return r.rank > 5 && r.rank <= 20; }).map(function (r) {
    return '<div class="dk' + (held[r.t] ? ' held' : '') + '"><span class="rank">#' + r.rank + '</span><span class="tk2">' + esc(r.t) + (held[r.t] ? ' <span class="tag ndx" title="currently held">HELD</span>' : '') + (r.ndx ? ' <span class="tag ndx">NDX</span>' : '') +
      '</span><span class="val ' + tone(r.score) + '">' + pct(r.score, 0) + '</span><span class="nm2">' + esc(r.n) + '</span><span class="chg">' + delta(r.d1w) + '</span></div>';
  }).join('');

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

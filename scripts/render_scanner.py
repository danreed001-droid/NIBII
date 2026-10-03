#!/usr/bin/env python3
"""Renders docs/scanner.html - the structure scanner dashboard - from
data/scan.json (written by `scripts/mtf_scan.py --out data/scan.json`).

The page is static: the scan data is embedded as JSON and drawn by a small
inline script, so GitHub Pages can serve it as-is next to docs/index.html
(the Market Tape Ledger page, which links here). It shares that page's
look - same tokens, fonts and dark/light toggle (same localStorage key, so
the theme carries across both pages).

Usage:
    python scripts/render_scanner.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, 'data', 'scan.json')
OUT_PATH = os.path.join(ROOT, 'docs', 'scanner.html')

PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Structure Scanner</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0d0d0d; --surface: #17181a; --surface-2: #1f2023; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #8b8a85; --hairline: #2c2c2a; --accent: #3987e5; --gold: #d9b46a;
  --masthead-bg: #17181a; --masthead-ink: #ffffff; --masthead-ink-2: #a9adba;
  --up: #0ca30c; --down: #d03b3b; --chop: #898781; --watch: #d9b46a;
  color-scheme: dark;
}
:root[data-mtl-theme="light"] {
  --bg: #f4f3ef; --surface: #fdfdfc; --surface-2: #f0efea; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  --up: #0a8f0a; --down: #c43232; --chop: #898781; --watch: #93701f;
  color-scheme: light;
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--ink); margin: 0;
  font: 15px/1.55 "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
}
.wrap { max-width: 1080px; margin-inline: auto; padding: 0 16px 64px; }
h1, h2 { font-family: "Fraunces", Georgia, serif; text-wrap: balance; margin: 0; }
.mono, code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
a { color: var(--accent); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* masthead */
.masthead { background: var(--masthead-bg); color: var(--masthead-ink); }
.masthead-inner { max-width: 1080px; margin-inline: auto; padding: 22px 16px 22px; border-bottom: 2px solid var(--gold); }
.back { display: inline-block; font-size: 0.8rem; color: var(--masthead-ink-2); text-decoration: none; margin-bottom: 14px; }
.back:hover { color: var(--gold); }
.eyebrow { font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--gold); font-weight: 600; margin: 0 0 6px; }
.masthead-top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; justify-content: space-between; }
.masthead-right { display: flex; align-items: center; gap: 10px; }
h1 { font-size: 2.1rem; font-weight: 600; }
.subtitle { color: var(--masthead-ink-2); margin: 8px 0 0; font-size: 0.92rem; max-width: 760px; }
.fresh { margin: 12px 0 0; font-size: 0.78rem; color: var(--masthead-ink-2); display: flex; align-items: center; gap: 8px; }
.fresh-dot { width: 8px; height: 8px; border-radius: 999px; background: #5fb87a; }
.fresh[data-state="aging"] .fresh-dot { background: #d9b46a; }
.fresh[data-state="stale"] .fresh-dot { background: #e5705f; }
.theme-toggle {
  display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px;
  border-radius: 999px; border: 1px solid rgba(255,255,255,0.18); background: transparent;
  color: var(--masthead-ink-2); cursor: pointer;
}
.theme-toggle:hover { color: var(--gold); border-color: var(--gold); }
.theme-toggle svg { width: 15px; height: 15px; }

/* controls */
.controls {
  position: sticky; top: 0; z-index: 5; background: var(--bg);
  display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; padding: 14px 0 12px;
  border-bottom: 1px solid var(--hairline);
}
.ctl { display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
.seg { display: inline-flex; border: 1px solid var(--hairline); border-radius: 999px; padding: 2px; background: var(--surface); }
.seg button {
  font: inherit; font-size: 0.8rem; text-transform: none; letter-spacing: 0; border: 0; background: transparent;
  color: var(--ink-2); padding: 5px 12px; border-radius: 999px; cursor: pointer; white-space: nowrap;
}
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg); font-weight: 600; }
.seg button:focus-visible, .chip:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* stat tiles */
.stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--hairline);
  border: 1px solid var(--hairline); border-radius: 12px; overflow: hidden; margin-top: 18px; }
@media (max-width: 720px) { .stats { grid-template-columns: repeat(2, 1fr); } .stats > :last-child { grid-column: 1 / -1; } }
.stat { background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; border-top: 3px solid var(--tone, transparent); }
.stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.stat-value { font-family: ui-monospace, monospace; font-size: 1.6rem; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.2; }
.stat-sub { font-size: 0.74rem; color: var(--ink-2); }

.section-label { font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: 36px 0 12px; display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.section-label .hint { text-transform: none; letter-spacing: 0; font-weight: 500; font-size: 0.78rem; }

/* state glyphs + pills */
.st { position: relative; display: inline-flex; align-items: center; justify-content: center; min-width: 1.6em; font-size: 0.85rem; font-weight: 600; }
.st-up { color: var(--up); } .st-down { color: var(--down); } .st-chop { color: var(--chop); } .st-na { color: var(--muted); opacity: 0.6; }
.pill { display: inline-flex; align-items: center; gap: 5px; padding: 2px 10px; border-radius: 999px; font-size: 0.74rem; font-weight: 600;
  border: 1px solid var(--hairline); color: var(--ink-2); white-space: nowrap; }
.v-buy { --c: var(--up); border-color: color-mix(in srgb, var(--up) 55%, transparent); color: var(--ink); background: color-mix(in srgb, var(--up) 14%, transparent); }
.v-sell { --c: var(--down); border-color: color-mix(in srgb, var(--down) 55%, transparent); color: var(--ink); background: color-mix(in srgb, var(--down) 14%, transparent); }
.v-watch { color: var(--watch); border-color: color-mix(in srgb, var(--watch) 45%, transparent); }
.v-no { --c: var(--chop); color: var(--muted); }

/* signal cards */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(300px, 100%), 1fr)); gap: 12px; }
.sig { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; border-left: 4px solid var(--c); }
.sig.buy { --c: var(--up); } .sig.sell { --c: var(--down); }
.sig-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.tk { font-family: "Fraunces", Georgia, serif; font-size: 1.45rem; font-weight: 600; line-height: 1.1; }
.nm { color: var(--ink-2); font-size: 0.8rem; }
.meta { font-size: 0.74rem; color: var(--muted); }
.tfstrip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.tf { background: var(--surface-2); border-radius: 8px; padding: 5px 6px; text-align: center; font-size: 0.68rem; color: var(--muted); }
.tf .st { display: flex; margin: 1px auto 0; font-size: 0.82rem; }
.tf.trig { outline: 1px dashed var(--c); outline-offset: -1px; }
.levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; }
.levels div { display: flex; flex-direction: column; }
.levels dt { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
.levels dd { margin: 0; font-family: ui-monospace, monospace; font-weight: 600; font-variant-numeric: tabular-nums; }
.why { margin: 0; font-size: 0.78rem; color: var(--ink-2); }
.empty { background: var(--surface); border: 1px dashed var(--hairline); border-radius: 12px; padding: 22px; color: var(--ink-2); font-size: 0.9rem; }
.empty button { font: inherit; color: var(--accent); background: none; border: 0; padding: 0; cursor: pointer; text-decoration: underline; }

/* ETF rows */
.etfs { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(330px, 100%), 1fr)); gap: 12px; }
.etf { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 12px 14px; display: grid; gap: 8px; }
.etf-top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.etf-top .tk { font-size: 1.15rem; }
.etf-setups { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.72rem; color: var(--muted); align-items: center; }

/* breadth */
.breadth { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 14px 16px; }
.legend { display: flex; gap: 14px; font-size: 0.74rem; color: var(--ink-2); margin-bottom: 10px; flex-wrap: wrap; }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.sw { width: 10px; height: 10px; border-radius: 3px; background: var(--c); }
.brow { display: grid; grid-template-columns: minmax(110px, 190px) 1fr minmax(130px, auto); gap: 10px; align-items: center; padding: 5px 0; font-size: 0.8rem; }
.brow.total { border-bottom: 1px solid var(--hairline); padding-bottom: 9px; margin-bottom: 4px; font-weight: 600; }
.bname { color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bname small { color: var(--muted); font-weight: 400; }
.bar { display: flex; gap: 2px; height: 14px; }
.bar i { display: block; height: 100%; background: var(--c); min-width: 0; }
.bar i:first-child { border-radius: 4px 0 0 4px; } .bar i:last-child { border-radius: 0 4px 4px 0; }
.bar i:only-child { border-radius: 4px; }
.bar i:hover { filter: brightness(1.2); }
.bnums { font-family: ui-monospace, monospace; font-size: 0.74rem; color: var(--ink-2); white-space: nowrap; text-align: right; }
.bnums b { font-weight: 600; color: var(--ink); }
@media (max-width: 560px) { .brow { grid-template-columns: 1fr; gap: 4px; } .bnums { text-align: left; } }
#tip { position: fixed; z-index: 20; pointer-events: none; background: var(--ink); color: var(--bg); font-size: 0.76rem; padding: 6px 9px; border-radius: 6px; max-width: 260px; }

/* table */
.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.filters input, .filters select {
  font: inherit; font-size: 0.85rem; background: var(--surface); color: var(--ink);
  border: 1px solid var(--hairline); border-radius: 8px; padding: 7px 10px; min-width: 0;
}
.filters input { flex: 1 1 180px; }
.chip { font: inherit; font-size: 0.78rem; border: 1px solid var(--hairline); background: var(--surface); color: var(--ink-2); border-radius: 999px; padding: 5px 11px; cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--ink); color: var(--ink); font-weight: 600; }
.count { font-size: 0.78rem; color: var(--muted); margin-left: auto; }
.tablebox { position: relative; overflow-x: auto; border: 1px solid var(--hairline); border-radius: 12px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 0.84rem; }
th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--hairline); white-space: nowrap; }
th { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; position: sticky; top: 0; background: var(--surface); }
th button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; text-transform: inherit; letter-spacing: inherit; }
th button[data-dir]::after { content: attr(data-dir); margin-left: 4px; }
td.c, th.c { text-align: center; }
tbody tr.row { cursor: pointer; }
tbody tr.row:hover { background: var(--surface-2); }
tbody tr.row td:first-child b { font-weight: 600; }
td .sub { display: block; color: var(--muted); font-size: 0.72rem; max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
tr.detail td { background: var(--surface-2); white-space: normal; font-size: 0.8rem; color: var(--ink-2); }
.dgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 6px 16px; margin-bottom: 8px; }
.dgrid b { color: var(--ink); font-weight: 600; }
.dsetup { margin: 4px 0 0; }
.more { display: block; margin: 12px auto 0; font: inherit; font-size: 0.82rem; color: var(--accent); background: none; border: 1px solid var(--hairline); border-radius: 999px; padding: 7px 16px; cursor: pointer; }
@media (max-width: 640px) { .col-sector { display: none; } }

footer { margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }
footer p { margin: 0 0 8px; }
</style>

<div class="masthead">
  <div class="masthead-inner">
    <a class="back" href="index.html">← Market Tape Ledger</a>
    <p class="eyebrow">NIBII · Structure Scanner</p>
    <div class="masthead-top">
      <h1>Trend Scanner</h1>
      <span class="masthead-right">
        <span class="mono" id="scan-date" style="color:var(--masthead-ink-2);font-size:0.9rem"></span>
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
    <p class="subtitle">Weekly, daily, 1-hour and 15-minute market structure (higher highs / higher lows vs lower highs / lower lows) for the S&amp;P 500 and six ETFs.
      <b>BUY</b> when the larger timeframes are all in an uptrend and the trigger timeframe just flipped bullish; <b>SELL</b> is the mirror image.</p>
    <p class="fresh" id="fresh"><span class="fresh-dot"></span><span id="fresh-text"></span></p>
  </div>
</div>

<div class="wrap">
  <div class="controls">
    <div class="ctl">Trend rule
      <span class="seg" id="mode-seg">
        <button type="button" data-mode="strict" title="The last 4 labeled swings must all agree">Strict · 4 swings</button>
        <button type="button" data-mode="loose" title="Only the latest swing high and low must agree">Loose · 2 swings</button>
      </span>
    </div>
    <div class="ctl">Setup
      <span class="seg" id="setup-seg">
        <button type="button" data-setup="all">Both</button>
        <button type="button" data-setup="daily">Daily trade</button>
        <button type="button" data-setup="hourly">Hourly trade</button>
      </span>
    </div>
  </div>

  <div class="stats" id="stats"></div>

  <p class="section-label">Signals <span class="hint" id="sig-hint"></span></p>
  <div id="signals"></div>

  <p class="section-label">Your ETFs <span class="hint">XLF · XLU · XLY · EEM · GLD · SLV</span></p>
  <div class="etfs" id="etfs"></div>

  <p class="section-label">Breadth by sector
    <span class="seg" id="tf-seg">
      <button type="button" data-tf="0">Weekly</button>
      <button type="button" data-tf="1">Daily</button>
      <button type="button" data-tf="2">1H</button>
      <button type="button" data-tf="3">15m</button>
    </span>
  </p>
  <div class="breadth" id="breadth"></div>

  <p class="section-label">All tickers <span class="hint">tap a row for the swing labels and reasons</span></p>
  <div class="filters">
    <input id="q" type="search" placeholder="Search ticker or company" aria-label="Search ticker or company">
    <select id="sector" aria-label="Sector"><option value="">All sectors</option></select>
    <span id="vchips"></span>
    <span class="count" id="count"></span>
  </div>
  <div class="tablebox">
    <table>
      <thead><tr>
        <th><button type="button" data-sort="t">Ticker</button></th>
        <th class="col-sector"><button type="button" data-sort="sec">Sector</button></th>
        <th class="c">W</th><th class="c">D</th><th class="c">1H</th><th class="c">15m</th>
        <th><button type="button" data-sort="daily">Daily trade</button></th>
        <th><button type="button" data-sort="hourly">Hourly trade</button></th>
        <th style="text-align:right"><button type="button" data-sort="px">Last</button></th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
  <button type="button" class="more" id="more" hidden>Show all</button>

  <footer>
    <p><b>How it works.</b> Each chart's swing highs and lows come from an N-bar fractal (2 bars each side on weekly, 3 elsewhere) and are labeled HH/LH and HL/LL.
      A timeframe is <b>▲ up</b> when its recent labeled swings are all HH/HL, <b>▼ down</b> when all LH/LL, <b>◆ choppy</b> otherwise.
      <b>Daily trade:</b> weekly + daily aligned, 1H just printed a change of character (CHoCH) the same way within 7 bars.
      <b>Hourly trade:</b> weekly + daily + 1H aligned, 15m CHoCH within 8 bars. Entry is the last close; the stop is the swing on the other side of the break.
      <b>WATCH</b> = larger timeframes aligned, no trigger yet.</p>
    <p>Unfinished bars are ignored. Prices from Yahoo Finance; this is a mechanical read of chart structure, not investment advice.
      Generated by <code>scripts/render_scanner.py</code> from <code>data/scan.json</code> in
      <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a>.</p>
  </footer>
</div>
<div id="tip" hidden></div>

<script type="application/json" id="scan-data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('scan-data').textContent);
  var TF = ['W', 'D', '1H', '15m'], TFN = ['Weekly', 'Daily', '1H', '15m'];
  var ARW = { up: '▲', down: '▼', chop: '◆' }, TXT = { up: 'up', down: 'down', chop: 'choppy' };
  var VICON = { BUY: '▲', SELL: '▼', WATCH: '◷', NO: '–' };
  var RANK = { BUY: 0, SELL: 0, WATCH: 1, NO: 2 };
  var KEY = 'nibii-scanner';
  var S = { mode: 'strict', setup: 'all', tf: 0, v: 'all', sec: '', q: '', sort: 'signal', dir: 1, all: false, open: {} };
  try { var saved = JSON.parse(localStorage.getItem(KEY) || '{}'); ['mode', 'setup', 'tf'].forEach(function (k) { if (saved[k] != null) S[k] = saved[k]; }); } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify({ mode: S.mode, setup: S.setup, tf: S.tf })); } catch (e) {} }

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function num(x) { if (x == null) return '–'; var a = Math.abs(x); return x.toLocaleString(undefined, { maximumFractionDigits: a >= 1000 ? 1 : a >= 10 ? 2 : 4 }); }
  function st(s, title) { var c = s || 'na'; var t = s ? TXT[s] : 'n/a'; return '<span class="st st-' + c + '" title="' + esc(title || t) + '">' + (ARW[s] || '·') + '<span class="sr">' + t + '</span></span>'; }
  function pill(v) { return '<span class="pill v-' + v.toLowerCase() + '">' + VICON[v] + ' ' + v + '</span>'; }
  function mode(r) { return r.m && r.m[S.mode]; }
  function setups(r) { var m = mode(r); if (!m) return []; return Object.keys(m.set).filter(function (k) { return S.setup === 'all' || S.setup === k; }).map(function (k) { return [k, m.set[k]]; }); }
  function best(r) { var b = null; setups(r).forEach(function (p) { if (!b || RANK[p[1].v] < RANK[b[1].v]) b = p; }); return b; }
  function risk(s) { return s.e && s.s ? Math.abs(s.e - s.s) / s.e * 100 : null; }
  var tickers = D.tickers.filter(function (r) { return !r.err; });
  var sp = tickers.filter(function (r) { return !r.etf; });

  // header
  var gen = new Date(D.generatedAt);
  document.getElementById('scan-date').textContent = gen.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  function fresh() {
    var m = Math.floor((Date.now() - gen) / 60000), h = m / 60;
    var a = m < 1 ? 'just now' : m < 60 ? m + ' min ago' : h < 48 ? Math.floor(h) + 'h ' + (m % 60) + 'm ago' : Math.floor(h / 24) + ' days ago';
    document.getElementById('fresh-text').textContent = 'Scanned ' + a + ' · ' + D.tickers.length + ' tickers';
    document.getElementById('fresh').setAttribute('data-state', h < 2 ? 'fresh' : h < 24 ? 'aging' : 'stale');
  }
  fresh(); setInterval(fresh, 60000);

  function pressed(segId, attr, val) {
    document.querySelectorAll('#' + segId + ' button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute(attr) === String(val))); });
  }

  function renderStats() {
    var c = { BUY: 0, SELL: 0, WATCH: 0 };
    tickers.forEach(function (r) { setups(r).forEach(function (p) { if (c[p[1].v] != null) c[p[1].v]++; }); });
    var up = 0, dn = 0;
    sp.forEach(function (r) { var s = mode(r).st[S.tf]; if (s === 'up') up++; else if (s === 'down') dn++; });
    var pu = sp.length ? Math.round(up / sp.length * 100) : 0, pd = sp.length ? Math.round(dn / sp.length * 100) : 0;
    function tile(label, value, sub, tone) {
      return '<div class="stat"' + (tone ? ' style="--tone:' + tone + '"' : '') + '><span class="stat-label">' + label + '</span><span class="stat-value">' + value + '</span><span class="stat-sub">' + sub + '</span></div>';
    }
    var which = S.setup === 'all' ? 'daily + hourly setups' : S.setup + ' trade';
    document.getElementById('stats').innerHTML =
      tile('▲ Buy signals', c.BUY, which, 'var(--up)') +
      tile('▼ Sell signals', c.SELL, which, 'var(--down)') +
      tile('◷ Watch', c.WATCH, 'aligned, waiting for a flip', 'var(--watch)') +
      tile(TFN[S.tf] + ' breadth', '<span class="st-up">▲</span> ' + pu + '%', 'of the S&amp;P 500 in an uptrend · <span class="st-down">▼</span> ' + pd + '% down', null) +
      tile('Scanned', D.tickers.length, sp.length + ' stocks · ' + (tickers.length - sp.length) + ' ETFs', null);
  }

  function tfStrip(r, trigIdx) {
    var m = mode(r);
    return '<div class="tfstrip">' + TF.map(function (t, i) {
      return '<div class="tf' + (i === trigIdx ? ' trig' : '') + '" title="' + TFN[i] + ': ' + esc(m.lab[i] || 'no labeled swings') + '">' + t + st(m.st[i], TFN[i] + ' ' + (m.st[i] ? TXT[m.st[i]] : 'n/a')) + '</div>';
    }).join('') + '</div>';
  }

  function renderSignals() {
    var hits = [];
    tickers.forEach(function (r) { setups(r).forEach(function (p) { if (p[1].v === 'BUY' || p[1].v === 'SELL') hits.push([r, p[0], p[1]]); }); });
    hits.sort(function (a, b) { return (a[2].v > b[2].v ? 1 : a[2].v < b[2].v ? -1 : 0) || (risk(a[2]) || 99) - (risk(b[2]) || 99); });
    document.getElementById('sig-hint').textContent = hits.length ? hits.length + ' live · sorted by tightest stop' : '';
    var el = document.getElementById('signals');
    if (!hits.length) {
      el.innerHTML = '<div class="empty">No BUY or SELL signals under the ' + S.mode + ' trend rule right now.' +
        (S.mode === 'strict' ? ' <button type="button" id="try-loose">Try the loose rule</button>' : '') + '</div>';
      var t = document.getElementById('try-loose'); if (t) t.onclick = function () { setMode('loose'); };
      return;
    }
    el.innerHTML = '<div class="cards">' + hits.map(function (h) {
      var r = h[0], k = h[1], s = h[2], side = s.v.toLowerCase(), rk = risk(s);
      var trig = D.setups[k].trigger, ti = D.timeframes.indexOf(trig);
      return '<article class="sig ' + side + '"><div class="sig-head"><div><div class="tk">' + esc(r.t) + '</div><div class="nm">' + esc(r.n) + '</div></div>' + pill(s.v) + '</div>' +
        '<div class="meta">' + esc(r.sec) + ' · ' + (k === 'daily' ? 'Daily trade' : 'Hourly trade') + ' · trigger ' + esc(trig) + '</div>' +
        tfStrip(r, ti) +
        '<dl class="levels"><div><dt>Entry ~</dt><dd>' + num(s.e) + '</dd></div><div><dt>Stop ' + (side === 'buy' ? 'below' : 'above') + '</dt><dd>' + num(s.s) + '</dd></div><div><dt>Risk</dt><dd>' + (rk == null ? '–' : rk.toFixed(1) + '%') + '</dd></div></dl>' +
        '<p class="why">' + esc(s.r) + '</p></article>';
    }).join('') + '</div>';
  }

  function renderEtfs() {
    document.getElementById('etfs').innerHTML = D.tickers.filter(function (r) { return r.etf; }).map(function (r) {
      if (r.err) return '<div class="etf"><div class="etf-top"><span class="tk">' + esc(r.t) + '</span></div><span class="meta">' + esc(r.err) + '</span></div>';
      return '<div class="etf"><div class="etf-top"><div><span class="tk">' + esc(r.t) + '</span> <span class="nm">' + esc(r.n) + '</span></div><span class="mono">' + num(r.px) + '</span></div>' +
        tfStrip(r, -1) +
        '<div class="etf-setups">' + setups(r).map(function (p) { return '<span>' + (p[0] === 'daily' ? 'Daily' : 'Hourly') + '</span>' + pill(p[1].v); }).join('') + '</div></div>';
    }).join('');
  }

  function renderBreadth() {
    var groups = {};
    sp.forEach(function (r) { (groups[r.sec] = groups[r.sec] || []).push(r); });
    function count(list) { var c = { up: 0, chop: 0, down: 0, na: 0 }; list.forEach(function (r) { c[mode(r).st[S.tf] || 'na']++; }); return c; }
    var rows = Object.keys(groups).map(function (k) { return [k, count(groups[k]), groups[k].length]; });
    rows.sort(function (a, b) { return (b[1].up - b[1].down) / b[2] - (a[1].up - a[1].down) / a[2]; });
    rows.unshift(['S&P 500', count(sp), sp.length, true]);
    function seg(c, n, key, label, name) {
      if (!c[key]) return '';
      var pct = c[key] / n * 100;
      return '<i style="--c:var(--' + key + ');flex:' + c[key] + ' 1 0" data-tip="' + esc(name + ' · ' + TFN[S.tf] + ': ' + c[key] + ' of ' + n + ' ' + label + ' (' + Math.round(pct) + '%)') + '"></i>';
    }
    document.getElementById('breadth').innerHTML =
      '<div class="legend"><span><i class="sw" style="--c:var(--up)"></i>▲ Uptrend (HH/HL)</span><span><i class="sw" style="--c:var(--chop)"></i>◆ Choppy</span><span><i class="sw" style="--c:var(--down)"></i>▼ Downtrend (LH/LL)</span></div>' +
      rows.map(function (row) {
        var c = row[1], n = row[2];
        return '<div class="brow' + (row[3] ? ' total' : '') + '"><span class="bname">' + esc(row[0]) + ' <small>' + n + '</small></span>' +
          '<span class="bar">' + seg(c, n, 'up', 'in an uptrend', row[0]) + seg(c, n, 'chop', 'choppy', row[0]) + seg(c, n, 'down', 'in a downtrend', row[0]) + '</span>' +
          '<span class="bnums">▲ <b>' + Math.round(c.up / n * 100) + '%</b> · ◆ ' + Math.round(c.chop / n * 100) + '% · ▼ <b>' + Math.round(c.down / n * 100) + '%</b></span></div>';
      }).join('');
  }

  // table
  var sectors = {}; tickers.forEach(function (r) { sectors[r.sec] = 1; });
  var sel = document.getElementById('sector');
  Object.keys(sectors).sort().forEach(function (s) { var o = document.createElement('option'); o.value = s; o.textContent = s; sel.appendChild(o); });
  var VOPTS = ['all', 'BUY', 'SELL', 'WATCH', 'NO'];
  document.getElementById('vchips').innerHTML = VOPTS.map(function (v) { return '<button type="button" class="chip" data-v="' + v + '">' + (v === 'all' ? 'All' : VICON[v] + ' ' + v) + '</button> '; }).join('');

  function setupCell(r, k) {
    var m = mode(r); if (!m || !m.set[k]) return '–';
    return pill(m.set[k].v);
  }
  function sortKey(r) {
    switch (S.sort) {
      case 't': return r.t;
      case 'sec': return r.sec + ' ' + r.t;
      case 'px': return r.px || 0;
      case 'daily': case 'hourly': return RANK[mode(r).set[S.sort].v] + ' ' + r.t;
      default: var b = best(r); return (b ? RANK[b[1].v] : 3) + (r.etf ? ' 0' : ' 1') + r.t;
    }
  }
  function detail(r) {
    var m = mode(r);
    return '<tr class="detail"><td colspan="9"><div class="dgrid">' + TF.map(function (t, i) {
      var b = r.brk && r.brk[i];
      return '<div><b>' + TFN[i] + '</b> ' + st(m.st[i]) + ' ' + esc(m.lab[i] || '–') + '<br><span class="meta">last break: ' + (b ? esc(b.d + ' ' + b.k + ', ' + b.ago + ' bars ago') : 'none') + '</span></div>';
    }).join('') + '</div>' + Object.keys(m.set).map(function (k) {
      var s = m.set[k];
      return '<p class="dsetup">' + pill(s.v) + ' <b>' + (k === 'daily' ? 'Daily' : 'Hourly') + ' trade</b> – ' + esc(s.r) + (s.e ? ' · entry ~' + num(s.e) + ', stop ' + num(s.s) : '') + '</p>';
    }).join('') + '</td></tr>';
  }
  function renderTable() {
    var q = S.q.trim().toLowerCase();
    var list = tickers.filter(function (r) {
      if (S.sec && r.sec !== S.sec) return false;
      if (q && r.t.toLowerCase().indexOf(q) < 0 && r.n.toLowerCase().indexOf(q) < 0) return false;
      if (S.v !== 'all' && !setups(r).some(function (p) { return p[1].v === S.v; })) return false;
      return true;
    });
    list.sort(function (a, b) { var x = sortKey(a), y = sortKey(b); return (x > y ? 1 : x < y ? -1 : 0) * S.dir; });
    var LIMIT = 60, shown = S.all ? list : list.slice(0, LIMIT);
    document.getElementById('count').textContent = list.length + ' of ' + tickers.length;
    var more = document.getElementById('more');
    more.hidden = list.length <= LIMIT || S.all; more.textContent = 'Show all ' + list.length;
    document.getElementById('rows').innerHTML = shown.map(function (r) {
      var m = mode(r);
      return '<tr class="row" data-t="' + esc(r.t) + '" aria-expanded="' + !!S.open[r.t] + '"><td><b>' + esc(r.t) + '</b><span class="sub">' + esc(r.n) + '</span></td>' +
        '<td class="col-sector">' + esc(r.sec) + '</td>' +
        m.st.map(function (s, i) { return '<td class="c">' + st(s, TFN[i] + ' ' + (s ? TXT[s] : 'n/a') + (m.lab[i] ? ' · ' + m.lab[i] : '')) + '</td>'; }).join('') +
        '<td>' + setupCell(r, 'daily') + '</td><td>' + setupCell(r, 'hourly') + '</td>' +
        '<td class="mono" style="text-align:right">' + num(r.px) + '</td></tr>' + (S.open[r.t] ? detail(r) : '');
    }).join('') || '<tr><td colspan="9" style="color:var(--muted)">No tickers match.</td></tr>';
    document.querySelectorAll('th button[data-sort]').forEach(function (b) {
      if (b.getAttribute('data-sort') === S.sort) b.setAttribute('data-dir', S.dir > 0 ? '↑' : '↓'); else b.removeAttribute('data-dir');
    });
    document.querySelectorAll('#vchips .chip').forEach(function (c) { c.setAttribute('aria-pressed', String(c.getAttribute('data-v') === S.v)); });
  }

  function renderAll() {
    pressed('mode-seg', 'data-mode', S.mode); pressed('setup-seg', 'data-setup', S.setup); pressed('tf-seg', 'data-tf', S.tf);
    renderStats(); renderSignals(); renderEtfs(); renderBreadth(); renderTable();
  }
  function setMode(m) { S.mode = m; save(); renderAll(); }

  document.getElementById('mode-seg').onclick = function (e) { var b = e.target.closest('button'); if (b) setMode(b.getAttribute('data-mode')); };
  document.getElementById('setup-seg').onclick = function (e) { var b = e.target.closest('button'); if (b) { S.setup = b.getAttribute('data-setup'); save(); renderAll(); } };
  document.getElementById('tf-seg').onclick = function (e) { var b = e.target.closest('button'); if (b) { S.tf = +b.getAttribute('data-tf'); save(); pressed('tf-seg', 'data-tf', S.tf); renderStats(); renderBreadth(); } };
  document.getElementById('vchips').onclick = function (e) { var b = e.target.closest('.chip'); if (b) { S.v = b.getAttribute('data-v'); renderTable(); } };
  document.getElementById('q').oninput = function (e) { S.q = e.target.value; renderTable(); };
  sel.onchange = function (e) { S.sec = e.target.value; renderTable(); };
  document.getElementById('more').onclick = function () { S.all = true; renderTable(); };
  document.querySelector('thead').onclick = function (e) {
    var b = e.target.closest('button[data-sort]'); if (!b) return;
    var k = b.getAttribute('data-sort'); S.dir = S.sort === k ? -S.dir : 1; S.sort = k; renderTable();
  };
  document.getElementById('rows').onclick = function (e) {
    var tr = e.target.closest('tr.row'); if (!tr) return;
    var t = tr.getAttribute('data-t'); S.open[t] = !S.open[t]; renderTable();
  };

  // breadth hover tooltip
  var tip = document.getElementById('tip');
  var bx = document.getElementById('breadth');
  bx.addEventListener('mousemove', function (e) {
    var i = e.target.closest('[data-tip]'); if (!i) { tip.hidden = true; return; }
    tip.textContent = i.getAttribute('data-tip'); tip.hidden = false;
    var x = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
  });
  bx.addEventListener('mouseleave', function () { tip.hidden = true; });

  renderAll();
})();
(function () {
  var root = document.documentElement, sun = document.getElementById('icon-sun'), moon = document.getElementById('icon-moon');
  var KEY = 'mtl-theme';
  function apply(t) {
    if (t) root.setAttribute('data-mtl-theme', t); else root.removeAttribute('data-mtl-theme');
    var dark = t !== 'light'; sun.hidden = dark; moon.hidden = !dark;
  }
  var saved = null; try { saved = localStorage.getItem(KEY); } catch (e) {}
  apply(saved);
  document.getElementById('theme-toggle').addEventListener('click', function () {
    var next = root.getAttribute('data-mtl-theme') === 'light' ? 'dark' : 'light';
    apply(next); try { localStorage.setItem(KEY, next); } catch (e) {}
  });
})();
</script>
'''


def render(scan):
    # Escape "</" so a company name can never close the <script> block early.
    data = json.dumps(scan, separators=(',', ':')).replace('</', '<\\/')
    return PAGE.replace('__DATA__', data)


def main():
    if not os.path.exists(DATA_PATH):
        sys.exit(f"{DATA_PATH} not found - run: python scripts/mtf_scan.py --out data/scan.json")
    with open(DATA_PATH) as f:
        page = render(json.load(f))
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        f.write(page)
    print(f"wrote {OUT_PATH}")


if __name__ == '__main__':
    main()

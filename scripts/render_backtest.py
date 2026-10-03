#!/usr/bin/env python3
"""Renders docs/backtest.html - the scanner backtest plotted over time -
from data/backtest.json (written by scripts/backtest.py).

Static like docs/scanner.html: results embedded as JSON and drawn by an
inline script (cumulative P&L lines with a crosshair tooltip, monthly net
P&L bars, stats and tables), sharing the Ledger's tokens and theme toggle.

Usage:
    python scripts/render_backtest.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, 'data', 'backtest.json')
OUT_PATH = os.path.join(ROOT, 'docs', 'backtest.html')

PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scanner Backtest</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0d0d0d; --surface: #17181a; --surface-2: #1f2023; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #8b8a85; --hairline: #2c2c2a; --accent: #3987e5; --gold: #d9b46a;
  --masthead-bg: #17181a; --masthead-ink: #ffffff; --masthead-ink-2: #a9adba;
  --s-all: #3987e5; --s-short: #d95926; --s-long: #199e70; --b-spy: #c98500;
  --b-qqq: #d55181; --b-nvda: #008300; --b-arkk: #9085e9; --b-btc: #e66767;
  --pos: #0ca30c; --neg: #d03b3b; --grid: #2c2c2a;
  color-scheme: dark;
}
:root[data-mtl-theme="light"] {
  --bg: #f4f3ef; --surface: #fdfdfc; --surface-2: #f0efea; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  --s-all: #2a78d6; --s-short: #eb6834; --s-long: #1baf7a; --b-spy: #eda100;
  --b-qqq: #e87ba4; --b-nvda: #008300; --b-arkk: #4a3aa7; --b-btc: #e34948;
  --pos: #0a8f0a; --neg: #c43232; --grid: #e1e0d9;
  color-scheme: light;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); margin: 0; font: 15px/1.55 "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 1080px; margin-inline: auto; padding: 0 16px 64px; }
h1 { font-family: "Fraunces", Georgia, serif; margin: 0; font-size: 2.1rem; font-weight: 600; }
.mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
a { color: var(--accent); }
.masthead { background: var(--masthead-bg); color: var(--masthead-ink); }
.masthead-inner { max-width: 1080px; margin-inline: auto; padding: 22px 16px; border-bottom: 2px solid var(--gold); }
.back { font-size: 0.8rem; color: var(--masthead-ink-2); text-decoration: none; margin-right: 14px; }
.back:hover { color: var(--gold); }
.eyebrow { font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--gold); font-weight: 600; margin: 14px 0 6px; }
.top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.subtitle { color: var(--masthead-ink-2); margin: 8px 0 0; font-size: 0.92rem; max-width: 780px; }
.theme-toggle { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.18); background: transparent; color: var(--masthead-ink-2); cursor: pointer; }
.theme-toggle:hover { color: var(--gold); border-color: var(--gold); }
.theme-toggle svg { width: 15px; height: 15px; }

.controls { position: sticky; top: 0; z-index: 5; background: var(--bg); display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center;
  padding: 14px 0 12px; border-bottom: 1px solid var(--hairline); }
.ctl { display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
.seg { display: inline-flex; border: 1px solid var(--hairline); border-radius: 999px; padding: 2px; background: var(--surface); }
.seg button { font: inherit; font-size: 0.8rem; text-transform: none; letter-spacing: 0; border: 0; background: transparent; color: var(--ink-2);
  padding: 5px 12px; border-radius: 999px; cursor: pointer; white-space: nowrap; }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg); font-weight: 600; }
.seg button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 560px) { .trig { display: none; } .ctl { flex-wrap: wrap; } .seg button { padding: 5px 9px; font-size: 0.76rem; } }
.window { font-size: 0.8rem; color: var(--ink-2); margin: 12px 0 0; }

.stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--hairline); border: 1px solid var(--hairline);
  border-radius: 12px; overflow: hidden; margin-top: 16px; }
@media (max-width: 720px) { .stats { grid-template-columns: repeat(2, 1fr); } .stats > :last-child { grid-column: 1 / -1; } }
.stat { background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.stat-value { font-family: ui-monospace, monospace; font-size: 1.5rem; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.2; }
.stat-sub { font-size: 0.74rem; color: var(--ink-2); }

.section-label { font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: 34px 0 12px; }
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 14px 16px; }
.chart-title { font-size: 0.95rem; font-weight: 600; margin: 0 0 2px; }
.chart-sub { font-size: 0.78rem; color: var(--muted); margin: 0 0 10px; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.78rem; color: var(--ink-2); margin-bottom: 6px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.key { width: 16px; height: 2px; border-radius: 2px; background: var(--c); }
.chart { position: relative; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.grid line { stroke: var(--grid); stroke-width: 1; }
.zero { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
.axis text { fill: var(--muted); font-size: 11px; font-family: ui-monospace, monospace; }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.endlabel { font-size: 11px; font-family: ui-monospace, monospace; fill: var(--ink-2); }
.cross { stroke: var(--muted); stroke-width: 1; }
.dot { stroke: var(--surface); stroke-width: 2; }
.bar-pos { fill: var(--pos); } .bar-neg { fill: var(--neg); }
.bars rect:hover { filter: brightness(1.25); }
.tip { position: absolute; pointer-events: none; background: var(--ink); color: var(--bg); font-size: 0.76rem; padding: 7px 10px; border-radius: 6px;
  min-width: 150px; z-index: 3; }
.tip .row { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.tip .row i { width: 12px; height: 2px; background: var(--c); display: inline-block; }
.tip b { font-family: ui-monospace, monospace; }
.empty { color: var(--muted); padding: 30px 0; text-align: center; }

.tablebox { overflow-x: auto; border: 1px solid var(--hairline); border-radius: 12px; background: var(--surface); position: relative; }
table { border-collapse: collapse; width: 100%; font-size: 0.84rem; }
th, td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--hairline); white-space: nowrap; font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
th { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; }
tr:last-child td { border-bottom: 0; }
.pos { color: var(--pos); } .neg { color: var(--neg); }
.swatch { display: inline-block; width: 12px; height: 2px; background: var(--c); vertical-align: middle; margin-right: 6px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 720px) { .two { grid-template-columns: 1fr; } }
.hero { display: grid; grid-template-columns: minmax(260px, 340px) 1fr; gap: 12px; margin-top: 16px; }
@media (max-width: 860px) { .hero { grid-template-columns: 1fr; } }
.board-row { display: grid; grid-template-columns: 116px 1fr 64px; gap: 8px; align-items: center; padding: 5px 0; font-size: 0.8rem; }
.board-row.me .bname { font-weight: 600; color: var(--ink); }
.bname { color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: flex; align-items: center; gap: 6px; }
.bname i { width: 10px; height: 10px; border-radius: 3px; background: var(--c); flex: none; }
.btrack { position: relative; height: 16px; }
.btrack .axis0 { position: absolute; top: -3px; bottom: -3px; width: 1px; background: var(--muted); }
.btrack .fill { position: absolute; top: 0; bottom: 0; background: var(--c); border-radius: 4px; }
.bval { font-family: ui-monospace, monospace; font-size: 0.78rem; text-align: right; font-variant-numeric: tabular-nums; }
.board-foot { font-size: 0.72rem; color: var(--muted); margin: 8px 0 0; }
.verdict { font-family: "Fraunces", Georgia, serif; font-size: 1.15rem; margin: 0 0 10px; line-height: 1.35; }
.toggles { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tog { font: inherit; font-size: 0.76rem; display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--hairline); background: var(--surface-2);
  color: var(--ink-2); border-radius: 999px; padding: 4px 10px; cursor: pointer; }
.tog i { width: 14px; height: 3px; border-radius: 2px; background: var(--c); }
.tog[aria-pressed="false"] { opacity: 0.45; }
.tog[aria-pressed="false"] i { background: var(--muted); }
.tog:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.line.bench { stroke-width: 1.6; }
.line.strat { stroke-width: 2.6; }
.mini { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; }
.mini div { background: var(--surface-2); border-radius: 8px; padding: 8px 10px; }
.mini span { display: block; font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
.mini b { font-family: ui-monospace, monospace; font-size: 1rem; }
.notes { margin-top: 34px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }
.notes li { margin-bottom: 6px; }
</style>

<div class="masthead"><div class="masthead-inner">
  <a class="back" href="scanner.html">← Trend Scanner</a><a class="back" href="index.html">Market Tape Ledger</a>
  <p class="eyebrow">NIBII · Backtest</p>
  <div class="top"><h1>Scanner Backtest</h1>
    <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dark/light theme">
      <svg id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>
      <svg id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"></path></svg>
    </button></div>
  <p class="subtitle" id="subtitle"></p>
</div></div>

<div class="wrap">
  <div class="controls">
    <div class="ctl">Setup <span class="seg" id="setup-seg">
      <button type="button" data-v="daily">Daily trade<span class="trig"> · 1h trigger</span></button>
      <button type="button" data-v="hourly">Hourly trade<span class="trig"> · 15m trigger</span></button></span></div>
    <div class="ctl">Trend rule <span class="seg" id="mode-seg">
      <button type="button" data-v="strict">Strict · 4 swings</button>
      <button type="button" data-v="loose">Loose · 2 swings</button></span></div>
  </div>
  <p class="window" id="window"></p>

  <div class="hero">
    <div class="card">
      <p class="verdict" id="verdict"></p>
      <p class="chart-title">Total return, same window</p>
      <p class="chart-sub">$100 in one account vs $100 bought and held</p>
      <div id="board"></div>
      <p class="board-foot">Strategy lines = one $100 account split equally across every open signal each day (cash when none).</p>
      <div class="mini" id="mini"></div>
    </div>
    <div class="card">
      <p class="chart-title">Growth of $100</p>
      <p class="chart-sub">Strategy vs buy-and-hold · tap a chip to show or hide a line</p>
      <div class="toggles" id="toggles"></div>
      <div class="chart" id="growth"></div>
    </div>
  </div>

  <p class="section-label">Trade stats</p>
  <div class="stats" id="stats"></div>

  <p class="section-label">Results over time</p>
  <div class="card">
    <p class="chart-title">Cumulative P&amp;L, $<span class="stake"></span> on every trade</p>
    <p class="chart-sub">Running sum of every closed trade's dollar result, by exit date (trades overlap, so this is not one account)</p>
    <div class="legend" id="legend"></div>
    <div class="chart" id="equity"></div>
  </div>
  <div class="card" style="margin-top:12px">
    <p class="chart-title">Net P&amp;L by month</p>
    <p class="chart-sub">Buys and sells combined · bars above zero are winning months</p>
    <div class="chart" id="monthly"></div>
  </div>

  <p class="section-label">Buys vs sells</p>
  <div class="tablebox"><table id="sides"></table></div>

  <p class="section-label">By year</p>
  <div class="tablebox"><table id="years"></table></div>

  <p class="section-label">Tickers <span style="text-transform:none;letter-spacing:0;font-weight:500" id="tk-side"></span></p>
  <div class="two"><div class="tablebox"><table id="best"></table></div><div class="tablebox"><table id="worst"></table></div></div>

  <ul class="notes">
    <li><b>Rules.</b> Buy at the close of the bar where the trigger timeframe prints a bullish change of character (closes above its last swing high after a bearish run) while every larger timeframe is in an uptrend; sell when the trigger timeframe next breaks bearish. Sells (shorts) are the exact mirror. Each decision uses only bars that had closed at that moment.</li>
    <li><b>History.</b> Yahoo Finance keeps ~730 trading days of 1-hour bars and ~60 days of 15-minute bars, so the daily trade can only be tested from late 2023 and the hourly trade from mid-2026 - not from 2020.</li>
    <li><b>P&amp;L.</b> Every trade is a fixed $<span class="stake"></span> position in the stock/ETF; P&amp;L is the sum of those results. Trades overlap across tickers, so the capital in use at once is far more than $<span class="stake"></span>. No commissions, spreads or slippage; fills at bar closes; prices split- and dividend-adjusted.</li>
    <li><b>Benchmarks.</b> SPY, QQQ, NVDA, ARKK and Bitcoin bought with $100 at the first close of the window and held to the end, dividends reinvested (Bitcoin trades every day, the rest on market days).</li>
    <li><b>Options.</b> These are moves of the underlying. An option on the same trade magnifies the move and also loses time value - a small underlying win can still lose money on an option.</li>
    <li><b>Data check.</b> <span id="dropped"></span></li>
    <li><b>Universe.</b> Today's S&amp;P 500 members plus six ETFs, so stocks that dropped out of the index are missing (survivorship bias - flatters long results).</li>
    <li>Generated by <code>scripts/backtest.py</code> + <code>scripts/render_backtest.py</code> in <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a> · <span id="gen"></span></li>
  </ul>
</div>

<script type="application/json" id="bt-data">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('bt-data').textContent);
  var S = { setup: 'daily', mode: 'loose' };
  try { var sv = JSON.parse(localStorage.getItem('nibii-backtest') || '{}'); if (sv.setup) S.setup = sv.setup; if (sv.mode) S.mode = sv.mode; } catch (e) {}
  var SIDES = [['all', 'Buys + sells', 'var(--s-all)'], ['long', 'Buys (long)', 'var(--s-long)'], ['short', 'Sells (short)', 'var(--s-short)']];
  var BAR_MIN = { daily: 60, hourly: 15 };
  var NS = 'http://www.w3.org/2000/svg';

  function $(id) { return document.getElementById(id); }
  function money(x, sign) { if (x == null) return '–'; var s = Math.abs(x) >= 1000 ? Math.round(Math.abs(x)).toLocaleString() : Math.abs(x).toFixed(2); return (x < 0 ? '−$' : (sign && x > 0 ? '+$' : '$')) + s; }
  function pct(x, sign) { if (x == null) return '–'; return (sign && x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x * 100).toFixed(2) + '%'; }
  function tone(x) { return x > 0 ? 'pos' : x < 0 ? 'neg' : ''; }
  function hold(bars) { var m = bars * BAR_MIN[S.setup]; if (m < 60 * 6.5) return (m / 60).toFixed(1) + 'h'; return (m / 60 / 6.5).toFixed(1) + ' sessions'; }
  function cur() { return D.results[S.mode + ':' + S.setup]; }
  function el(tag, attrs) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }
  function niceStep(span, target) { var raw = span / target, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p; return (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p; }
  function ticks(lo, hi, n) { var st = niceStep(hi - lo || 1, n), out = []; for (var v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(10)); return out; }
  function day(s) { return Date.parse(s + 'T12:00:00Z'); }
  function fmtDate(t, long) { return new Date(t).toLocaleDateString(undefined, long ? { year: 'numeric', month: 'short', day: 'numeric' } : { year: '2-digit', month: 'short' }); }

  $('subtitle').textContent = 'Every BUY and SELL the Trend Scanner would have taken across ' + D.tickers + ' tickers (S&P 500 + six ETFs), with a $' + D.stake + ' position each, closed when the trigger timeframe flips the other way.';
  document.querySelectorAll('.stake').forEach(function (s) { s.textContent = D.stake; });
  var dr = D.dropped || {}, drn = Object.keys(dr).reduce(function (a, k) { return a + dr[k]; }, 0);
  $('dropped').textContent = drn ? drn + ' trades were left out because their price fell outside that day\u2019s actual daily range, meaning Yahoo\u2019s intraday and daily data disagree about the ticker (' + Object.keys(dr).sort(function (a, b) { return dr[b] - dr[a]; }).map(function (k) { return k + ' ' + dr[k]; }).join(', ') + ').' : 'Every trade\u2019s entry and exit sat inside that day\u2019s daily price range.';
  $('gen').textContent = 'run ' + new Date(D.generatedAt).toLocaleString();

  function pressed(id, v) { document.querySelectorAll('#' + id + ' button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-v') === v)); }); }

  function renderStats() {
    var r = cur(), s = r.all.stats;
    $('window').textContent = r.first ? 'Trades from ' + fmtDate(day(r.first), true) + ' to ' + fmtDate(day(r.last), true) + ' · ' + D.setups[S.setup].label : 'No trades for this setup and rule.';
    function tile(label, value, sub, cls) { return '<div class="stat"><span class="stat-label">' + label + '</span><span class="stat-value ' + (cls || '') + '">' + value + '</span><span class="stat-sub">' + sub + '</span></div>'; }
    if (!s.trades) { $('stats').innerHTML = tile('Trades', 0, 'none closed', ''); return; }
    $('stats').innerHTML =
      tile('Closed trades', s.trades.toLocaleString(), r.long.stats.trades + ' buys · ' + r.short.stats.trades + ' sells' + (s.stillOpen ? ' · ' + s.stillOpen + ' open' : '')) +
      tile('Win rate', Math.round(s.winRate * 100) + '%', 'avg win ' + pct(s.avgWin, true) + ' · avg loss ' + pct(s.avgLoss, true)) +
      tile('Avg per trade', pct(s.avgRet, true), 'median ' + pct(s.medianRet, true), tone(s.avgRet)) +
      tile('Total P&amp;L', money(s.totalPnl, true), '$' + D.stake + ' on every trade', tone(s.totalPnl)) +
      tile('Profit factor', s.profitFactor == null ? '–' : s.profitFactor.toFixed(2), 'gross wins ÷ gross losses · avg hold ' + hold(s.avgBars));
  }

  var ENT = {
    all: ['Strategy · buys + sells', 'var(--s-all)', 'strat'], long: ['Strategy · buys only', 'var(--s-long)', 'strat'],
    short: ['Strategy · sells only', 'var(--s-short)', 'strat'], SPY: ['S&P 500 (SPY)', 'var(--b-spy)', 'bench'],
    QQQ: ['Nasdaq-100 (QQQ)', 'var(--b-qqq)', 'bench'], NVDA: ['Nvidia (NVDA)', 'var(--b-nvda)', 'bench'],
    ARKK: ['ARK Innovation (ARKK)', 'var(--b-arkk)', 'bench'], 'BTC-USD': ['Bitcoin (BTC)', 'var(--b-btc)', 'bench']
  };
  var ORDER = ['all', 'long', 'short', 'SPY', 'QQQ', 'NVDA', 'ARKK', 'BTC-USD'];
  var SHOWN = { all: true, long: false, short: false, SPY: true, QQQ: true, NVDA: true, ARKK: true, 'BTC-USD': true };
  try { var sh = JSON.parse(localStorage.getItem('nibii-backtest-lines') || 'null'); if (sh) SHOWN = sh; } catch (e) {}

  // series: [{name, c, cls, pts: [[t, v], ...]}]; fmt formats a y value; base = reference line
  function lineChart(box, series, fmt, base, label) {
    box.innerHTML = '';
    series = series.filter(function (s) { return s.pts.length; });
    if (!series.length) { box.innerHTML = '<p class="empty">Nothing to plot.</p>'; return; }
    var tip = document.createElement('div'); tip.className = 'tip'; tip.hidden = true;
    var W = Math.max(320, box.clientWidth), H = Math.round(Math.min(380, Math.max(240, W * 0.45))), m = { l: 58, r: 70, t: 10, b: 26 };
    var xs = [], ys = [base];
    series.forEach(function (s) { s.pts.forEach(function (p) { xs.push(p[0]); ys.push(p[1]); }); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs); if (x0 === x1) { x0 -= 864e5; x1 += 864e5; }
    var ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys), yt = ticks(ymin, ymax, 5);
    var y0 = Math.min(yt[0], ymin), y1 = Math.max(yt[yt.length - 1], ymax);
    function X(t) { return m.l + (t - x0) / (x1 - x0) * (W - m.l - m.r); }
    function Y(v) { return m.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b); }
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': label });
    var g = el('g', { class: 'grid axis' });
    yt.forEach(function (v) { g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) })); var t = el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }); t.textContent = fmt(v); g.appendChild(t); });
    var span = x1 - x0;
    if (span < 1.2e10) { for (var t2 = x0; t2 <= x1; t2 += 7 * 864e5) { var tt = el('text', { x: X(t2), y: H - 6, 'text-anchor': 'middle' }); tt.textContent = new Date(t2).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); g.appendChild(tt); } }
    else { var step = span > 7e10 ? 6 : 3, d = new Date(x0); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + 1);
      while (d.getTime() <= x1) { if (d.getUTCMonth() % step === 0) { var tx = el('text', { x: X(d.getTime()), y: H - 6, 'text-anchor': 'middle' }); tx.textContent = fmtDate(d.getTime()); g.appendChild(tx); } d.setUTCMonth(d.getUTCMonth() + 1); } }
    svg.appendChild(g);
    svg.appendChild(el('line', { class: 'zero', x1: m.l, x2: W - m.r, y1: Y(base), y2: Y(base) }));
    var ends = [];
    series.slice().reverse().forEach(function (s) {
      svg.appendChild(el('path', { class: 'line ' + (s.cls || ''), d: s.pts.map(function (p, i) { return (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1); }).join(''), style: 'stroke:' + s.c }));
      var last = s.pts[s.pts.length - 1]; ends.push({ y: Y(last[1]), v: last[1], c: s.c });
    });
    ends.sort(function (a, b) { return a.y - b.y; });
    for (var i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
    ends.forEach(function (e) {
      svg.appendChild(el('rect', { x: W - m.r + 4, y: e.y - 1, width: 8, height: 2, rx: 1, style: 'fill:' + e.c }));
      var t = el('text', { class: 'endlabel', x: W - m.r + 16, y: e.y + 4 }); t.textContent = fmt(e.v); svg.appendChild(t);
    });
    var cross = el('line', { class: 'cross', y1: m.t, y2: H - m.b, visibility: 'hidden' }); svg.appendChild(cross);
    var dots = series.map(function (s) { var c = el('circle', { class: 'dot', r: 4, style: 'fill:' + s.c, visibility: 'hidden' }); svg.appendChild(c); return c; });
    box.appendChild(svg); box.appendChild(tip);
    function valueAt(s, t) { if (t < s.pts[0][0]) return null; var lo = 0, hi = s.pts.length - 1; while (lo < hi) { var mid = (lo + hi + 1) >> 1; if (s.pts[mid][0] <= t) lo = mid; else hi = mid - 1; } return s.pts[lo]; }
    var allX = Array.from(new Set(xs)).sort(function (a, b) { return a - b; });
    svg.addEventListener('pointermove', function (e) {
      var rect = svg.getBoundingClientRect(), px = (e.clientX - rect.left) / rect.width * W;
      var t = x0 + (px - m.l) / (W - m.l - m.r) * (x1 - x0), lo = 0, hi = allX.length - 1;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (allX[mid] < t) lo = mid + 1; else hi = mid; }
      if (lo > 0 && Math.abs(allX[lo - 1] - t) < Math.abs(allX[lo] - t)) lo--;
      var tx = allX[lo], sx = X(tx);
      cross.setAttribute('x1', sx); cross.setAttribute('x2', sx); cross.setAttribute('visibility', 'visible');
      tip.textContent = '';
      var hd = document.createElement('div'); hd.textContent = fmtDate(tx, true); hd.style.marginBottom = '4px'; tip.appendChild(hd);
      var rows = series.map(function (s, k) { return [s, k, valueAt(s, tx)]; });
      rows.sort(function (a, b) { return (b[2] ? b[2][1] : -1e18) - (a[2] ? a[2][1] : -1e18); });
      rows.forEach(function (r) {
        var s = r[0], p = r[2], row = document.createElement('div'); row.className = 'row';
        var key = document.createElement('i'); key.style.setProperty('--c', s.c); row.appendChild(key);
        var b = document.createElement('b'); b.textContent = p ? fmt(p[1]) : '–'; row.appendChild(b);
        row.appendChild(document.createTextNode(' ' + s.name)); tip.appendChild(row);
        var dot = dots[r[1]];
        if (p) { dot.setAttribute('cx', X(p[0])); dot.setAttribute('cy', Y(p[1])); dot.setAttribute('visibility', 'visible'); } else dot.setAttribute('visibility', 'hidden');
      });
      tip.hidden = false;
      var bx = sx / W * rect.width, left = bx + 12; if (left + tip.offsetWidth > rect.width) left = bx - tip.offsetWidth - 12;
      tip.style.left = Math.max(0, left) + 'px'; tip.style.top = '8px';
    });
    svg.addEventListener('pointerleave', function () { tip.hidden = true; cross.setAttribute('visibility', 'hidden'); dots.forEach(function (d) { d.setAttribute('visibility', 'hidden'); }); });
  }

  function retOf(key) { var r = cur(); var o = ENT[key][2] === 'strat' ? (r.growth || {})[key] : (r.bench || {})[key]; return o && o.stats; }

  function renderHero() {
    var r = cur(), rows = ORDER.map(function (k) { var st = retOf(k); return st && st.total != null ? [k, st] : null; }).filter(Boolean);
    if (!rows.length) { $('board').innerHTML = '<p class="empty">No trades for this setup and rule.</p>'; $('verdict').textContent = ''; $('mini').innerHTML = ''; return; }
    rows.sort(function (a, b) { return b[1].total - a[1].total; });
    var lo = Math.min(0, Math.min.apply(null, rows.map(function (x) { return x[1].total; }))), hi = Math.max(0, Math.max.apply(null, rows.map(function (x) { return x[1].total; })));
    var span = hi - lo || 1, z = -lo / span * 100;
    $('board').innerHTML = rows.map(function (x) {
      var k = x[0], v = x[1].total, w = Math.abs(v) / span * 100, left = v >= 0 ? z : z - w;
      return '<div class="board-row' + (ENT[k][2] === 'strat' ? ' me' : '') + '" title="' + ENT[k][0] + ': ' + pct(v, true) + ' total, max drawdown ' + pct(x[1].maxDD) + '">' +
        '<span class="bname"><i style="--c:' + ENT[k][1] + '"></i>' + (ENT[k][2] === 'strat' ? ENT[k][0].replace('Strategy · ', '') : k) + '</span>' +
        '<span class="btrack"><span class="axis0" style="left:' + z + '%"></span><span class="fill" style="--c:' + ENT[k][1] + ';left:' + left + '%;width:' + Math.max(w, 0.6) + '%"></span></span>' +
        '<span class="bval ' + tone(v) + '">' + pct(v, true).replace(/\.\d+%/, '%') + '</span></div>';
    }).join('');
    var me = retOf('all'), spy = retOf('SPY'), rank = rows.findIndex(function (x) { return x[0] === 'all'; }) + 1;
    $('verdict').textContent = me && spy ? 'One $100 strategy account ' + (me.total >= 0 ? 'made ' : 'lost ') + Math.round(Math.abs(me.total) * 100) + '% vs ' + (spy.total >= 0 ? '+' : '−') + Math.round(Math.abs(spy.total) * 100) + '%' + ' for SPY — #' + rank + ' of ' + rows.length + '.' : '';
    var g = r.growth.all.stats;
    $('mini').innerHTML = '<div><span>Max drawdown</span><b class="neg">' + pct(g.maxDD) + '</b></div>' +
      '<div><span>Days in market</span><b>' + Math.round((g.exposure || 0) * 100) + '%</b></div>' +
      '<div><span>Avg open</span><b>' + (g.avgOpen || 0).toFixed(1) + '</b></div>';
  }

  function renderGrowth() {
    var r = cur();
    $('toggles').innerHTML = ORDER.map(function (k) { return '<button type="button" class="tog" data-k="' + k + '" aria-pressed="' + !!SHOWN[k] + '"><i style="--c:' + ENT[k][1] + '"></i>' + ENT[k][0] + '</button>'; }).join('');
    var series = ORDER.filter(function (k) { return SHOWN[k]; }).map(function (k) {
      var o = ENT[k][2] === 'strat' ? (r.growth || {})[k] : (r.bench || {})[k];
      return { name: ENT[k][0], c: ENT[k][1], cls: ENT[k][2], pts: o ? o.curve.map(function (p) { return [day(p[0]), p[1]]; }) : [] };
    });
    lineChart($('growth'), series, function (v) { return '$' + Math.round(v).toLocaleString(); }, 100, 'Growth of $100: strategy vs buy-and-hold');
  }
  $('toggles').onclick = function (e) {
    var b = e.target.closest('.tog'); if (!b) return; var k = b.getAttribute('data-k'); SHOWN[k] = !SHOWN[k];
    try { localStorage.setItem('nibii-backtest-lines', JSON.stringify(SHOWN)); } catch (x) {} renderGrowth();
  };

  function renderEquity() {
    var r = cur();
    $('legend').innerHTML = SIDES.map(function (s) { return '<span><i class="key" style="--c:' + s[2] + '"></i>' + s[1] + '</span>'; }).join('');
    lineChart($('equity'), SIDES.map(function (s) { return { name: s[1], c: s[2], cls: s[0] === 'all' ? 'strat' : '', pts: r[s[0]].curve.map(function (p) { return [day(p[0]), p[1]]; }) }; }),
      function (v) { return money(v, true); }, 0, 'Cumulative P&L over time');
  }

  var tipMo = document.createElement('div'); tipMo.className = 'tip'; tipMo.hidden = true;

  function renderMonthly() {
    var box = $('monthly'), pts = cur().all.curve; box.innerHTML = '';
    if (!pts.length) { box.innerHTML = '<p class="empty">No closed trades.</p>'; return; }
    var months = {}, prev = 0;
    pts.forEach(function (p) { var k = p[0].slice(0, 7); months[k] = months[k] || { pnl: 0, n: 0 }; months[k].pnl += p[1] - prev; months[k].n += p[2]; prev = p[1]; });
    var keys = Object.keys(months).sort(), vals = keys.map(function (k) { return months[k].pnl; });
    var W = Math.max(320, box.clientWidth), H = 200, m = { l: 58, r: 12, t: 8, b: 24 };
    var yt = ticks(Math.min(0, Math.min.apply(null, vals)), Math.max(0, Math.max.apply(null, vals)), 4), y0 = Math.min(yt[0], Math.min.apply(null, vals)), y1 = Math.max(yt[yt.length - 1], Math.max.apply(null, vals));
    function Y(v) { return m.t + (1 - (v - y0) / (y1 - y0 || 1)) * (H - m.t - m.b); }
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Net P&L by month' }), g = el('g', { class: 'grid axis' });
    yt.forEach(function (v) { g.appendChild(el('line', { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) })); var t = el('text', { x: m.l - 8, y: Y(v) + 4, 'text-anchor': 'end' }); t.textContent = money(v); g.appendChild(t); });
    var slot = (W - m.l - m.r) / keys.length, bw = Math.max(2, slot - 2), every = Math.ceil(keys.length / Math.floor((W - m.l - m.r) / 52));
    keys.forEach(function (k, i) { if (i % every === 0) { var t = el('text', { x: m.l + slot * (i + 0.5), y: H - 6, 'text-anchor': 'middle' }); t.textContent = fmtDate(Date.parse(k + '-15T12:00:00Z')); g.appendChild(t); } });
    svg.appendChild(g);
    var bars = el('g', { class: 'bars' });
    keys.forEach(function (k, i) {
      var v = months[k].pnl, y = Math.min(Y(v), Y(0)), h = Math.max(1, Math.abs(Y(v) - Y(0)));
      var r = el('rect', { x: m.l + slot * i + (slot - bw) / 2, y: y, width: bw, height: h, rx: Math.min(3, bw / 2), class: v >= 0 ? 'bar-pos' : 'bar-neg' });
      r.addEventListener('pointermove', function (e) {
        tipMo.textContent = ''; var a = document.createElement('div'); a.textContent = fmtDate(Date.parse(k + '-15T12:00:00Z'), false); tipMo.appendChild(a);
        var b = document.createElement('b'); b.textContent = money(v, true); tipMo.appendChild(b); tipMo.appendChild(document.createTextNode(' net · ' + months[k].n + ' trades'));
        tipMo.hidden = false; var rect = box.getBoundingClientRect(), left = e.clientX - rect.left + 12; if (left + tipMo.offsetWidth > rect.width) left = e.clientX - rect.left - tipMo.offsetWidth - 12;
        tipMo.style.left = Math.max(0, left) + 'px'; tipMo.style.top = (e.clientY - rect.top - 50) + 'px';
      });
      r.addEventListener('pointerleave', function () { tipMo.hidden = true; });
      bars.appendChild(r);
    });
    svg.appendChild(bars);
    svg.appendChild(el('line', { class: 'zero', x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0) }));
    box.appendChild(svg); box.appendChild(tipMo);
  }

  function renderTables() {
    var r = cur();
    $('sides').innerHTML = '<thead><tr><th>Side</th><th>Trades</th><th>Win rate</th><th>Avg / trade</th><th>Avg win</th><th>Avg loss</th><th>Best</th><th>Worst</th><th>Profit factor</th><th>Avg hold</th><th>Total P&amp;L</th></tr></thead><tbody>' +
      SIDES.slice(1).concat([SIDES[0]]).map(function (sd) {
        var s = r[sd[0]].stats; if (!s.trades) return '<tr><td><i class="swatch" style="--c:' + sd[2] + '"></i>' + sd[1] + '</td><td colspan="10" style="text-align:left;color:var(--muted)">no closed trades</td></tr>';
        return '<tr><td><i class="swatch" style="--c:' + sd[2] + '"></i>' + sd[1] + '</td><td>' + s.trades + '</td><td>' + Math.round(s.winRate * 100) + '%</td><td class="' + tone(s.avgRet) + '">' + pct(s.avgRet, true) + '</td><td>' + pct(s.avgWin, true) + '</td><td>' + pct(s.avgLoss, true) +
          '</td><td>' + pct(s.best, true) + '</td><td>' + pct(s.worst, true) + '</td><td>' + (s.profitFactor == null ? '–' : s.profitFactor.toFixed(2)) + '</td><td>' + hold(s.avgBars) + '</td><td class="' + tone(s.totalPnl) + '"><b>' + money(s.totalPnl, true) + '</b></td></tr>';
      }).join('') + '</tbody>';
    var years = {}; ['long', 'short', 'all'].forEach(function (k) { Object.keys(r[k].years).forEach(function (y) { years[y] = 1; }); });
    $('years').innerHTML = '<thead><tr><th>Year</th><th>Trades</th><th>Win rate</th><th>Buys P&amp;L</th><th>Sells P&amp;L</th><th>Total P&amp;L</th></tr></thead><tbody>' +
      Object.keys(years).sort().map(function (y) {
        var a = r.all.years[y], l = r.long.years[y], s = r.short.years[y];
        function m(o) { return o ? '<span class="' + tone(o.pnl) + '">' + money(o.pnl, true) + '</span>' : '–'; }
        return '<tr><td>' + y + '</td><td>' + a.trades + '</td><td>' + Math.round(a.wins / a.trades * 100) + '%</td><td>' + m(l) + '</td><td>' + m(s) + '</td><td><b>' + m(a) + '</b></td></tr>';
      }).join('') + '</tbody>';
    function tk(rows, title) {
      return '<thead><tr><th>' + title + '</th><th>Trades</th><th>Win rate</th><th>P&amp;L</th></tr></thead><tbody>' + rows.map(function (a) {
        return '<tr><td><b>' + a.t + '</b></td><td>' + a.trades + '</td><td>' + Math.round(a.wins / a.trades * 100) + '%</td><td class="' + tone(a.pnl) + '">' + money(a.pnl, true) + '</td></tr>';
      }).join('') + '</tbody>';
    }
    $('tk-side').textContent = '· buys + sells, $' + D.stake + ' per trade';
    $('best').innerHTML = tk(r.all.tickers.best, 'Best 10'); $('worst').innerHTML = tk(r.all.tickers.worst, 'Worst 10');
  }

  function renderAll() { pressed('setup-seg', S.setup); pressed('mode-seg', S.mode); renderStats(); renderHero(); renderGrowth(); renderEquity(); renderMonthly(); renderTables(); }
  function bind(id, key) { $(id).onclick = function (e) { var b = e.target.closest('button'); if (!b) return; S[key] = b.getAttribute('data-v'); try { localStorage.setItem('nibii-backtest', JSON.stringify(S)); } catch (x) {} renderAll(); }; }
  bind('setup-seg', 'setup'); bind('mode-seg', 'mode');
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { renderGrowth(); renderEquity(); renderMonthly(); }, 150); });
  renderAll();
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


def render(data):
    return PAGE.replace('__DATA__', json.dumps(data, separators=(',', ':')).replace('</', '<\\/'))


def main():
    if not os.path.exists(DATA_PATH):
        sys.exit(f"{DATA_PATH} not found - run: python scripts/backtest.py")
    with open(DATA_PATH) as f:
        page = render(json.load(f))
    with open(OUT_PATH, 'w') as f:
        f.write(page)
    print(f"wrote {OUT_PATH}")


if __name__ == '__main__':
    main()

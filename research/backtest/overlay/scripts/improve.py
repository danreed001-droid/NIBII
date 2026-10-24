#!/usr/bin/env python3
"""Tests a broader, slower, risk-aware version of the Auto / Boost plans on the
same robust footing as scripts/robustness.py (point-in-time S&P 500 incl.
removed companies, sleeve traded Monday, 0.15% slippage per side, lot-level
37% short-term / 20% long-term tax ledger with wash sales and IRS-timed
payments), 2010 onward.

New rule ("v2"), changed one piece at a time so each step is visible:
  1. 12 holdings instead of 5 (keep while ranked in the top 24)
  2. swapped monthly (last session of the month, traded next session)
     instead of weekly
  3. new buys ranked by 6-1 month return divided by 6-month volatility
  4. crash protection: at each rebalance positions are scaled down so the
     basket's last-6-month volatility would have been at most 20% a year
     (Barroso & Santa-Clara volatility scaling, long only, no leverage);
     the unused part sits in T-bills (BIL)
Auto: 60/40 with the best-of sleeve when 40%+ of holdings are in a daily
lower-low downtrend at the decision close (2 of 5 in the original rule).
Boost: Auto plus the news-gap boost.

Writes data/improve.json.
"""
import json
import math
import os
import sys
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from multiprocessing import get_context
import numpy as _np


def _rtop_design(n):
    t = _np.arange(n, dtype=float)
    T = _np.vstack([_np.ones(n), t, t * t]).T
    return T, _np.linalg.pinv(T)


_RT_CACHE = {}


def chan_break_at(closes, n, k, lag=5):
    """closes: the last n + lag + 1 closes, oldest first. True when a rising regression channel fitted to the n
    closes ending `lag` sessions ago, projected to today, has today's close below its lower band (midline - k sd)."""
    if len(closes) < n + lag + 1 or any(not c or c <= 0 for c in closes):
        return False
    y = _np.log(_np.asarray(closes[:n], dtype=float)); t = _np.arange(n, dtype=float); tm = t.mean()
    b = float(((t - tm) * (y - y.mean())).sum() / ((t - tm) ** 2).sum()); a = float(y.mean() - b * tm)
    if b <= 0:
        return False
    sd = float((y - (a + b * t)).std())
    return _np.log(closes[-1]) < a + b * (n - 1 + lag) - k * sd


def rtop_at(closes, n, r2min, mode):
    """Rounded top on the last n closes (oldest first): a quadratic fit to log price that is concave with
    R2 >= r2min and either has turned down (mode 'turned': vertex in the last 70% of the window, slope at the
    end negative) or has flattened (mode 'flat': still rising at the start, end slope under a third of it)."""
    if len(closes) < n or any(not c or c <= 0 for c in closes):
        return False
    if n not in _RT_CACHE:
        _RT_CACHE[n] = _rtop_design(n)
    T, Pi = _RT_CACHE[n]
    y = _np.log(_np.asarray(closes, dtype=float))
    a, b, c = Pi @ y
    if c >= 0:
        return False
    fit = T @ _np.array([a, b, c]); sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(((y - fit) ** 2).sum()) / sst if sst else 0.0
    if r2 < r2min:
        return False
    end = b + 2 * c * (n - 1)
    if mode == 'turned':
        vx = -b / (2 * c)
        return 0.3 * n <= vx <= n - 1 and end < 0
    return b > 0 and end < b / 3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if os.environ.get('MTL_PATH'):
    sys.path.insert(0, os.environ['MTL_PATH'])
import robustness as R  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
if os.environ.get('MTL_PATH'):   # test engine: load run_momentum from a patched copy
    import importlib.util as _ilu
    _sp = _ilu.spec_from_file_location('mtl_test_momentum', os.path.join(os.environ['MTL_PATH'], 'mtl', 'momentum.py'))
    _mm = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_mm)
    run_momentum = _mm.run_momentum
from mtl.news import booster  # noqa: E402
from mtl.sleeve import ASSETS, best_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDE_ = os.environ.get('HARNESS_SIDE', os.path.join(ROOT, 'side'))   # side series (research/backtest/side_data.py, volume_data.py)
OUT = os.path.join(ROOT, 'data', 'improve.json')
SLIP = 0.0015
G = {}

VARIANTS = {
    # name: (engine kwargs, boost?)
    'cur': (dict(top_n=5), None),
    'n5m': (dict(top_n=5, monthly=True), None),
    'l12w': (dict(top_n=5, look=252), None),
    'l12m': (dict(top_n=5, monthly=True, look=252), None),
    't3w': (dict(top_n=3), None),
    't4w': (dict(top_n=4), None),
    't10w': (dict(top_n=10), None),
    't3m': (dict(top_n=3, monthly=True), None),
    't4m': (dict(top_n=4, monthly=True), None),
    't10m': (dict(top_n=10, monthly=True), None),
    'acw': (dict(top_n=5, accel='first'), None),
    'acm': (dict(top_n=5, monthly=True, accel='first'), None),
    'abw': (dict(top_n=5, accel='blend'), None),
    'abm': (dict(top_n=5, monthly=True, accel='blend'), None),
    'rkw': (dict(top_n=5, windows=[(21 * (i + 1), 21 * i) for i in range(1, 7)], blend='rank'), None),
    'rkm': (dict(top_n=5, monthly=True, windows=[(21 * (i + 1), 21 * i) for i in range(1, 7)], blend='rank'), None),
    'rk0w': (dict(top_n=5, windows=[(21 * (i + 1), 21 * i) for i in range(0, 6)], blend='rank'), None),
    'rk0m': (dict(top_n=5, monthly=True, windows=[(21 * (i + 1), 21 * i) for i in range(0, 6)], blend='rank'), None),
    'rwkw': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank'), None),
    'rwkm': (dict(top_n=5, monthly=True, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank'), None),
    'rwk0w': (dict(top_n=5, windows=[(5 * i + 5, 5 * i) for i in range(25)], blend='rank'), None),
    'rwk0m': (dict(top_n=5, monthly=True, windows=[(5 * i + 5, 5 * i) for i in range(25)], blend='rank'), None),
    'wb25': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.25, 5, 0.0)), None),
    'wb50': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.5, 5, 0.0)), None),
    'wb100': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 1.0, 5, 0.0)), None),
    'wb50t10': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.5, 10, 0.0)), None),
    'wrec1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 1.0)), None),
    'wrec1b50': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.5, 5, 1.0)), None),
    'sow': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='sortino'), None),
    'som': (dict(top_n=5, monthly=True, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='sortino'), None),
    'so0w': (dict(top_n=5, windows=[(5 * i + 5, 5 * i) for i in range(25)], blend='sortino'), None),
    'shw': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='sharpe'), None),
    'rsow': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank_sortino'), None),
    'bk10': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', boost_rank=10), None),
    'bk20': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', boost_rank=20), None),
    'bk40': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', boost_rank=40), None),
    'bk60': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', boost_rank=60), None),
    'bk100': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', boost_rank=100), None),
    'sx2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(2, False)), None),
    'sx25': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(2.5, False)), None),
    'sx3': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(3, False)), None),
    'sx2u': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(2, True)), None),
    'sx3u': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(3, True)), None),
    'sx4': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(4, False)), None),
    'sx5': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sig_exit=(5, False)), None),
    'dtf50': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(trend=0.5)), None),
    'dtf0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(trend=0.0)), None),
    'dtf60': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(trend=0.6)), None),
    'dsc2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sector_cap=2), None),
    'dsc1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sector_cap=1), None),
    'dbl70': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(cap=0.7)), None),
    'dq30': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(qqq=0.3)), None),
    'dvt25': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', vol_target=0.25, vol_window=63), None),
    'dvt35': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', vol_target=0.35, vol_window=63), None),
    'dld': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'd1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(one=True)), None),
    'dmix': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', sector_cap=2, plan=dict(trend=0.5, ladder=True)), None),
    'dtc0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(trend=0.0, cash=True)), None),
    'dtc50': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(trend=0.5, cash=True)), None),
    'dq30ld': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(qqq=0.3, ladder=True)), None),
    'ld': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'ldlin': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=(1.0, 0.8, 0.6, 0.4, 0.2, 0.0))), None),
    'ldst': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=(1.0, 0.7, 0.5, 0.25))), None),
    'ldspy': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True, spy=True)), None),
    'ldday': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True, daily=True)), None),
    'ldc3': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True, cash3=True)), None),
    'ldk8': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', max_corr=0.8, plan=dict(ladder=True)), None),
    'ldk7': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', max_corr=0.7, plan=dict(ladder=True)), None),
    'ldiv': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='inv_vol', plan=dict(ladder=True)), None),
    'svok': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(slv_ok=True)), None),
    'ldok': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True, slv_ok=True)), None),
    'ldstok': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=(1.0, 0.7, 0.5, 0.25), slv_ok=True)), None),
    'svup': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(slv_up=True)), None),
    'ldup': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True, slv_up=True)), None),
    'ldstup': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=(1.0, 0.7, 0.5, 0.25), slv_up=True)), None),
    't2x': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x'), None),
    'ldt2x': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True)), None),
    'lint2x': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=(1.0, 0.8, 0.6, 0.4, 0.2, 0.0))), None),
    'ld9': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=(1.0, 0.9, 0.8, 0.7, 0.4, 0.1))), None),
    'ld9t2x': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=(1.0, 0.9, 0.8, 0.7, 0.4, 0.1))), None),
    'sl21': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, slook=21)), None),
    'sl63': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, slook=63)), None),
    'sl252': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, slook=252)), None),
    'srk0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, srank=[(5 * i + 5, 5 * i) for i in range(25)])), None),
    'srk1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, srank=[(5 * i + 26, 5 * i + 21) for i in range(21)])), None),
    'srk13': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, srank=[(5 * i + 5, 5 * i) for i in range(13)])), None),
    'tl0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, tl=0.0)), None),
    'tl2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, tl=0.02)), None),
    'tl5': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, tl=0.05)), None),
    'lxA': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', lolo_exit=dict(on=True), plan=dict(ladder=True)), None),
    'lxB': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', lolo_exit=dict(buy_up=True), plan=dict(ladder=True)), None),
    'lxC': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', lolo_exit=dict(daily=True), plan=dict(ladder=True)), None),
    'lxD': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', lolo_exit=dict(on=True), plan=dict(ladder=(1.0,))), None),
    'nosl': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=(1.0,))), None),
    'kr15': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True), keep_rank=15), None),
    'kr20': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True), keep_rank=20), None),
    'rres': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank_resid', weighting='top2x', plan=dict(ladder=True)), None),
    'r52': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank_52', weighting='top2x', plan=dict(ladder=True)), None),
    'w13': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(13)], blend='rank', weighting='top2x', plan=dict(ladder=True)), None),
    'w26': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(26)], blend='rank', weighting='top2x', plan=dict(ladder=True)), None),
    'ws2': (dict(top_n=5, windows=[(5 * i + 15, 5 * i + 10) for i in range(23)], blend='rank', weighting='top2x', plan=dict(ladder=True)), None),
    'btc': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, btc=True)), None),
    'btcsma': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, btc=True, btc_gate='sma')), None),
    'btclolo': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, btc=True, btc_gate='lolo')), None),
    'btcboth': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, btc=True, btc_gate='both')), None),
    'fri': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', exec_next=None, plan=dict(ladder=True, same=True)), None),
    'spk15': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', skip_spike=0.15, plan=dict(ladder=True)), None),
    'spk25': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', skip_spike=0.25, plan=dict(ladder=True)), None),
    'biw': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', biweekly=True, plan=dict(ladder=True)), None),
    'spy0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', plan=dict(ladder=True, spare_spy=True)), None),
    'c3': (dict(top_n=3, weighting='top2x', windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'c4': (dict(top_n=4, weighting='top2x', windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'rkw5': (dict(top_n=5, weighting='rankw', windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    't3x': (dict(top_n=5, weighting='top3x', windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'kr7': (dict(top_n=5, weighting='top2x', keep_rank=7, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'lev': (dict(top_n=5, weighting='top2x', lev_etf=True, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', plan=dict(ladder=True)), None),
    'rg20': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', regime_ma=20, weighting='top2x', plan=dict(ladder=True)), None),
    'rg50': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', regime_ma=50, weighting='top2x', plan=dict(ladder=True)), None),
    'rg200': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', regime_ma=200, weighting='top2x', plan=dict(ladder=True)), None),
    'old2x': (dict(top_n=5, weighting='top2x', plan=dict(ladder=True)), None),
    'cons': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank_ret', weighting='top2x', plan=dict(ladder=True)), None),
    'drift': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='drift', plan=dict(ladder=True)), None),
    'drift35': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='drift:0.35', plan=dict(ladder=True)), None),
    'pi150': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 0.5), weighting='top2x', plan=dict(ladder=True)), None),
    'pi200': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 1.0), weighting='top2x', plan=dict(ladder=True)), None),
    'pi314': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 2.14), weighting='top2x', plan=dict(ladder=True)), None),
    'pcexp': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 2.14, 'exp'), weighting='top2x', plan=dict(ladder=True)), None),
    'pcp2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 2.14, 'pow2'), weighting='top2x', plan=dict(ladder=True)), None),
    'pcp3': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 2.14, 'pow3'), weighting='top2x', plan=dict(ladder=True)), None),
    'pcp5': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend=('rank', 0.0, 0, 2.14, 'pow5'), weighting='top2x', plan=dict(ladder=True)), None),
    'dly': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', daily_rebal=True, plan=dict(ladder=True)), None),
    'dlyd': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', daily_rebal=True, plan=dict(ladder=True, daily=True)), None),
    'ev1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=1, plan=dict(ladder=True)), None),
    'ev2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=2, plan=dict(ladder=True)), None),
    'ev3': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=3, plan=dict(ladder=True)), None),
    'ev4': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=4, plan=dict(ladder=True)), None),
    'ev5': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=5, plan=dict(ladder=True)), None),
    'ev6': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=6, plan=dict(ladder=True)), None),
    'ev7': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=7, plan=dict(ladder=True)), None),
    'ev8': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=8, plan=dict(ladder=True)), None),
    'e4o0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=4, offset=0, plan=dict(ladder=True)), None),
    'e4o1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=4, offset=1, plan=dict(ladder=True)), None),
    'e4o2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=4, offset=2, plan=dict(ladder=True)), None),
    'e4o3': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=4, offset=3, plan=dict(ladder=True)), None),
    'e5o0': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=5, offset=0, plan=dict(ladder=True)), None),
    'e5o1': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=5, offset=1, plan=dict(ladder=True)), None),
    'e5o2': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=5, offset=2, plan=dict(ladder=True)), None),
    'e5o3': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=5, offset=3, plan=dict(ladder=True)), None),
    'e5o4': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', every_n=5, offset=4, plan=dict(ladder=True)), None),
    'liq10': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.1, plan=dict(ladder=True)), None),
    'liq20': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.2, plan=dict(ladder=True)), None),
    'liq30': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.3, plan=dict(ladder=True)), None),
    'liq25': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.25, plan=dict(ladder=True)), None),
    'liq35': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.35, plan=dict(ladder=True)), None),
    'liq40': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.4, plan=dict(ladder=True)), None),
    'liq50': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.5, plan=dict(ladder=True)), None),
    'liq60': (dict(top_n=5, windows=[(5 * i + 26, 5 * i + 21) for i in range(21)], blend='rank', weighting='top2x', liq_w=0.6, plan=dict(ladder=True)), None),
    'oldld': (dict(top_n=5, plan=dict(ladder=True)), None),
    'WS25f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy200', 0.75, 'best'))), None),
    'WS25c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy200', 0.75, 'BIL'))), None),
    'WS50f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy200', 0.5, 'best'))), None),
    'WS50c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy200', 0.5, 'BIL'))), None),
    'WS100f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy200', 0.0, 'best'))), None),
    'WS100c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy200', 0.0, 'BIL'))), None),
    'WD25f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('both', 0.75, 'best'))), None),
    'WD25c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('both', 0.75, 'BIL'))), None),
    'WD50f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('both', 0.5, 'best'))), None),
    'WD50c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('both', 0.5, 'BIL'))), None),
    'WD100f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('both', 0.0, 'best'))), None),
    'WD100c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('both', 0.0, 'BIL'))), None),
    'WM25f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'WM25c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'BIL'))), None),
    'WM50f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy6m', 0.5, 'best'))), None),
    'WM50c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy6m', 0.5, 'BIL'))), None),
    'WM100f': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy6m', 0.0, 'best'))), None),
    'WM100c': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('spy6m', 0.0, 'BIL'))), None),
    'T15': (dict(top_n=5, trail_stop=0.15, plan=dict(ladder=(1.0,))), None),
    'T20': (dict(top_n=5, trail_stop=0.20, plan=dict(ladder=(1.0,))), None),
    'T25': (dict(top_n=5, trail_stop=0.25, plan=dict(ladder=(1.0,))), None),
    'V25': (dict(top_n=5, vol_target=0.25, plan=dict(ladder=(1.0,))), None),
    'V30': (dict(top_n=5, vol_target=0.30, plan=dict(ladder=(1.0,))), None),
    'K7': (dict(top_n=7, plan=dict(ladder=(1.0,))), None),
    'K10': (dict(top_n=10, plan=dict(ladder=(1.0,))), None),
    'IV': (dict(top_n=5, weighting='inv_vol', plan=dict(ladder=(1.0,))), None),
    'SC2': (dict(top_n=5, sector_cap=2, plan=dict(ladder=(1.0,))), None),
    'CE': (dict(top_n=5, plan=dict(ladder=(1.0,), gates=[('spy6m', 0.25), ('eq100', 0.25)])), None),
    'CE2': (dict(top_n=5, plan=dict(ladder=(1.0,), gates=[('spy6m', 0.25), ('spy200', 0.25)])), None),
    'CV35': (dict(top_n=5, vol_target=0.35, plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'CV45': (dict(top_n=5, vol_target=0.45, plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'EQ25': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('eq100', 0.75, 'best'))), None),
    'EQ50': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('eq100', 0.5, 'best'))), None),
    'XE40': (dict(top_n=5, xit='ext40', plan=dict(ladder=(1.0,))), None),
    'XE60': (dict(top_n=5, xit='ext60', plan=dict(ladder=(1.0,))), None),
    'XR85': (dict(top_n=5, xit='rsi85', plan=dict(ladder=(1.0,))), None),
    'XAC': (dict(top_n=5, xit='accel', plan=dict(ladder=(1.0,))), None),
    'XBT1': (dict(top_n=5, xit='bt50_25', plan=dict(ladder=(1.0,))), None),
    'XBT2': (dict(top_n=5, xit='bt100_20', plan=dict(ladder=(1.0,))), None),
    'XCL': (dict(top_n=5, xit='climax', plan=dict(ladder=(1.0,))), None),
    'XTM': (dict(top_n=5, xit='time252', plan=dict(ladder=(1.0,))), None),
    'XLH': (dict(top_n=5, xit='lolo50', plan=dict(ladder=(1.0,))), None),
    'YE50': (dict(top_n=5, plan=dict(ladder=(1.0,), trim='ext50')), None),
    'YPT': (dict(top_n=5, plan=dict(ladder=(1.0,), trim='pt')), None),
    'YBT': (dict(top_n=5, plan=dict(ladder=(1.0,), trim='bt50_25')), None),
    'XA05': (dict(top_n=5, xit='accel_0.5', plan=dict(ladder=(1.0,))), None),
    'XA15': (dict(top_n=5, xit='accel_1.5', plan=dict(ladder=(1.0,))), None),
    'XA20': (dict(top_n=5, xit='accel_2.0', plan=dict(ladder=(1.0,))), None),
    'XA42': (dict(top_n=5, xit='accel_1.0_42', plan=dict(ladder=(1.0,))), None),
    'XA10d': (dict(top_n=5, xit='accel_1.0_10', plan=dict(ladder=(1.0,))), None),
    'XC20': (dict(top_n=5, xit='accel_2.0', plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'XAG63': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 63), plan=dict(ladder=(1.0,))), None),
    'XAG126': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 126), plan=dict(ladder=(1.0,))), None),
    'XAG189': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 189), plan=dict(ladder=(1.0,))), None),
    'XAG252': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 252), plan=dict(ladder=(1.0,))), None),
    'XAD63': (dict(top_n=5, xit='accel_2.0', xgate=('dd20', 63), plan=dict(ladder=(1.0,))), None),
    'XAD126': (dict(top_n=5, xit='accel_2.0', xgate=('dd20', 126), plan=dict(ladder=(1.0,))), None),
    'XAD189': (dict(top_n=5, xit='accel_2.0', xgate=('dd20', 189), plan=dict(ladder=(1.0,))), None),
    'XAD252': (dict(top_n=5, xit='accel_2.0', xgate=('dd20', 252), plan=dict(ladder=(1.0,))), None),
    'XCG63': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 63), plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'XCG126': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 126), plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'XCG189': (dict(top_n=5, xit='accel_2.0', xgate=('spy6m', 189), plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'XN10': (dict(top_n=10, xit='accel_2.0', xgate=('spy6m', 126), plan=dict(ladder=(1.0,))), None),
    'XN25': (dict(top_n=25, xit='accel_2.0', xgate=('spy6m', 126), plan=dict(ladder=(1.0,))), None),
    'XN50': (dict(top_n=50, xit='accel_2.0', xgate=('spy6m', 126), plan=dict(ladder=(1.0,))), None),
    'XN100': (dict(top_n=100, xit='accel_2.0', xgate=('spy6m', 126), plan=dict(ladder=(1.0,))), None),
    'XM120w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma120', 0), plan=dict(ladder=(1.0,))), None),
    'XM120w63': (dict(top_n=5, xit='accel_2.0', xgate=('ma120', 63), plan=dict(ladder=(1.0,))), None),
    'XM120w126': (dict(top_n=5, xit='accel_2.0', xgate=('ma120', 126), plan=dict(ladder=(1.0,))), None),
    'XM120w189': (dict(top_n=5, xit='accel_2.0', xgate=('ma120', 189), plan=dict(ladder=(1.0,))), None),
    'XM200w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma200', 0), plan=dict(ladder=(1.0,))), None),
    'XM200w63': (dict(top_n=5, xit='accel_2.0', xgate=('ma200', 63), plan=dict(ladder=(1.0,))), None),
    'XM200w126': (dict(top_n=5, xit='accel_2.0', xgate=('ma200', 126), plan=dict(ladder=(1.0,))), None),
    'XM200w189': (dict(top_n=5, xit='accel_2.0', xgate=('ma200', 189), plan=dict(ladder=(1.0,))), None),
    'XM50w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma50', 0), plan=dict(ladder=(1.0,))), None),
    'XM100w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma100', 0), plan=dict(ladder=(1.0,))), None),
    'XM150w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,))), None),
    'XM250w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma250', 0), plan=dict(ladder=(1.0,))), None),
    'XM170w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma170', 0), plan=dict(ladder=(1.0,))), None),
    'XM180w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma180', 0), plan=dict(ladder=(1.0,))), None),
    'XM190w0': (dict(top_n=5, xit='accel_2.0', xgate=('ma190', 0), plan=dict(ladder=(1.0,))), None),
    'XCM150': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'XCQ100': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy100', 0.75, 'best'))), None),
    'XCQ120': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy120', 0.75, 'best'))), None),
    'XCQ150': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy150', 0.75, 'best'))), None),
    'XCQ180': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy180', 0.75, 'best'))), None),
    'XCQ200': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy200', 0.75, 'best'))), None),
    'QA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('spy150', 0.25), ('spy6m', 0.25)])), None),
    'QB': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('spy150', 0.25), ('spy200', 0.25)])), None),
    'QC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('s150or6m', 0.75, 'best'))), None),
    'QD': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('s150or6m', 0.5, 'best'))), None),
    'QE': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('s150or6m', 0.0, 'best'))), None),
    'QF': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('spy150', 0.5, 'best'))), None),
    'TW1': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), weak=dict(monthly=True), plan=dict(ladder=(1.0,))), None),
    'TW1k': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), weak=dict(keep=15), plan=dict(ladder=(1.0,))), None),
    'TW2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), weak=dict(risk_adj=True), plan=dict(ladder=(1.0,))), None),
    'TW3': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), weak=dict(above200='cash'), plan=dict(ladder=(1.0,))), None),
    'TW3r': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), weak=dict(above200='next'), plan=dict(ladder=(1.0,))), None),
    'TW4': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), weak=dict(offhigh=0.15), plan=dict(ladder=(1.0,))), None),
    'MAN': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('manual', 0.0, 'BIL'))), None),
    'MAN2': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('manual2', 0.0, 'BIL'))), None),
    'CFCU': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_cu', 0.75, 'best'))), None),
    'CFHY': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'))), None),
    'CFSC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_sc', 0.75, 'best'))), None),
    'CFOIL': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_oil', 0.75, 'best'))), None),
    'CFUSD': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_usd', 0.75, 'best'))), None),
    'CFANY2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_any2', 0.75, 'best'))), None),
    'CFANY2h': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_any2', 0.5, 'best'))), None),
    'CFCUh': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_cu', 0.5, 'best'))), None),
    'VC90': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), volconf=0.9, plan=dict(ladder=(1.0,))), None),
    'VC100': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), volconf=1.0, plan=dict(ladder=(1.0,))), None),
    'VC110': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), volconf=1.1, plan=dict(ladder=(1.0,))), None),
    'INDT': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), indconf='top', plan=dict(ladder=(1.0,))), None),
    'INDS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), indconf='spy', plan=dict(ladder=(1.0,))), None),
    'MV30': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), minvol=0.30, plan=dict(ladder=(1.0,))), None),
    'MV40': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), minvol=0.40, plan=dict(ladder=(1.0,))), None),
    'VX20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('vix20', 0.75, 'best'))), None),
    'VX25': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('vix25', 0.75, 'best'))), None),
    'VX30': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('vix30', 0.75, 'best'))), None),
    'VX25h': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('vix25', 0.5, 'best'))), None),
    'VX30h': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('vix30', 0.5, 'best'))), None),
    'VX25c': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('vix25', 0.75, 'BIL'))), None),
    'VXL': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('vix20', 0.15), ('vix30', 0.20), ('vix35', 0.15)])), None),
    'VXHY': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('c_hy', 0.25), ('vix30', 0.25)])), None),
    'VXHY25': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('c_hy', 0.25), ('vix25', 0.25)])), None),
    'MWX': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('manual3', 0.0, 'BIL'))), None),
    'MWN': (dict(top_n=5, plan=dict(ladder=(1.0,), gate=('manual3', 0.0, 'BIL'))), None),
    'MWHY': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('c_hy', 0.25), ('manual3', 1.0)])), None),
    'LRS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('lowrate', 0.0, 'SPY'))), None),
    'LRQ': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('lowrate', 0.0, 'QQQ'))), None),
    'LRS50': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('lowrate', 0.5, 'SPY'))), None),
    'R12S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel252', 0.0, 'SPY'))), None),
    'R6S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel126', 0.0, 'SPY'))), None),
    'R12Q': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel252', 0.0, 'QQQ'))), None),
    'R12S50': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel252', 0.5, 'SPY'))), None),
    'R12LR': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel252_lr', 0.0, 'SPY'))), None),
    'BIG1': (dict(top_n=1, xit='accel_2.0', xgate=('ma150', 0), big=50, plan=dict(ladder=(1.0,))), None),
    'BIG3': (dict(top_n=3, xit='accel_2.0', xgate=('ma150', 0), big=50, plan=dict(ladder=(1.0,))), None),
    'BIG5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), big=50, plan=dict(ladder=(1.0,))), None),
    'MAN4': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), manualplan=[('2001-01-01', 'boost'), ('2008-01-25', 'bonds'), ('2009-02-23', 'boost'), ('2011-05-04', 'bonds'), ('2011-12-13', 'boost'), ('2012-04-30', 'bonds'), ('2012-06-15', 'boost'), ('2019-04-26', 'bonds'), ('2020-07-17', 'boost'), ('2022-04-08', 'cushion'), ('2022-07-15', 'boost'), ('2025-02-28', 'cash'), ('2025-03-21', 'boost')])), None),
    'ROT63': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0))), None),
    'ROT126': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=126, thr=1.0))), None),
    'ROT63W': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w'))), None),
    'ROT126W': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=126, thr=1.0, tf='w'))), None),
    'ROT63L': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=0.0))), None),
    'ROT63H': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=2.0))), None),
    'ROTWS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w', vs='strat'))), None),
    'ROTWU': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w', spy_weak=True))), None),
    'ROTWSU': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w', vs='strat', spy_weak=True))), None),
    'ROTDSU': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, vs='strat', spy_weak=True))), None),
    'RLLW': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w', spy_ll=True))), None),
    'RLLWS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w', vs='strat', spy_ll=True))), None),
    'RLLD': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, spy_ll=True, spy_tf='d'))), None),
    'RLLDW': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=1.0, tf='w', spy_ll=True, spy_tf='d'))), None),
    'RLLW0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=63, thr=0.0, tf='w', spy_ll=True))), None),
    'LGD': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True))), None),
    'LGDR': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d'))), None),
    'LGW': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True))), None),
    'LGWR': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w'))), None),
    'LGDdn': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, spy_down=True))), None),
    'LGWdn': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, spy_down=True))), None),
    'LGDt': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, thr=0.15))), None),
    'LGWt': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, thr=0.15))), None),
    'M1D': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=21, thr=1.0, spy_weak=True))), None),
    'M1W': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=21, thr=1.0, tf='w', spy_weak=True))), None),
    'M1Dll': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=21, thr=1.0, spy_ll=True, spy_tf='d'))), None),
    'M1Wll': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), rotate=dict(n=21, thr=1.0, tf='w', spy_ll=True))), None),
    'PTD': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts'))), None),
    'PTW': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, slope='pts'))), None),
    'PTDdn': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True))), None),
    'PTWdn': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True))), None),
    'PTDR': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', slope='pts'))), None),
    'PTWR': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', slope='pts'))), None),
    'PTDRdn': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', slope='pts', spy_down=True))), None),
    'SB_c5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=5))), None),
    'SB_c10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=10))), None),
    'SB_l3': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, min_lows=3))), None),
    'SB_xw': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, exit_tf='w'))), None),
    'SB_cool': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, cool=21))), None),
    'SB_dd5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, spy_dd=0.05))), None),
    'SB_dd10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, spy_dd=0.10))), None),
    'SB_mix': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=5, cool=21, spy_dd=0.05))), None),
    'SB_mix2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=5, exit_tf='w', spy_dd=0.05))), None),
    'SB_mix3': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, min_lows=3, cool=21, spy_dd=0.05))), None),
    'SB_c15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=15))), None),
    'SB_c20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=20))), None),
    'SB_c30': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=30))), None),
    'SB_c12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=12))), None),
    'SB_c13': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=13))), None),
    'SB_c14': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=14))), None),
    'SB_c16': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=16))), None),
    'SB_c17': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=17))), None),
    'SB_c18': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=18))), None),
    'CHR13': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=13))), None),
    'CHR14': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=14))), None),
    'CHR15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=15))), None),
    'CHR16': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=16))), None),
    'CHR18': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, confirm=18))), None),
    'XR10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'XCR10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'XR13': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=13))), None),
    'XCR13': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=13))), None),
    'XR15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'XCR15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'XR18': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=18))), None),
    'XCR18': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=18))), None),
    'W0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0))), None),
    'CW0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0))), None),
    'WSD0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0))), None),
    'CWSD0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0))), None),
    'DSW0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0))), None),
    'CDSW0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0))), None),
    'W5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5))), None),
    'CW5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5))), None),
    'WSD5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5))), None),
    'CWSD5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5))), None),
    'DSW5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5))), None),
    'CDSW5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5))), None),
    'W10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'CW10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'WSD10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'CWSD10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'DSW10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'CDSW10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10))), None),
    'W15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'CW15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'WSD15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'CWSD15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', spy_tf2='w', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'DSW15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'CDSW15': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='w', spy_tf2='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15))), None),
    'SOwBILno0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='BIL', back='notdown', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOwBILup0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='BIL', back='up', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOwTLTno0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='TLTX', back='notdown', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOwTLTup0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='TLTX', back='up', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOwbesno0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='best', back='notdown', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOwbesup0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='best', back='up', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdBILno0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', back='notdown', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdBILno10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', back='notdown', confirm=10, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdBILup0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', back='up', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdBILup10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', back='up', confirm=10, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdTLTno0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='TLTX', back='notdown', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdTLTno10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='TLTX', back='notdown', confirm=10, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdTLTup0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='TLTX', back='up', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdTLTup10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='TLTX', back='up', confirm=10, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdbesno0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', back='notdown', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdbesno10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', back='notdown', confirm=10, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdbesup0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', back='up', confirm=0, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'SOdbesup10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', back='up', confirm=10, vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MwBILA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='BIL', ma150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MwBILB': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='BIL', ma150=True, lh150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MwBILC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='BIL', lh150=True, back='notdown', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MwbesA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='best', ma150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MwbesB': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='best', ma150=True, lh150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MwbesC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='w', spyout='best', lh150=True, back='notdown', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MdBILA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', ma150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MdBILB': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', ma150=True, lh150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MdBILC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='BIL', lh150=True, back='notdown', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MdbesA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', ma150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MdbesB': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', ma150=True, lh150=True, back='ma', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'MdbesC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', spyout='best', lh150=True, back='notdown', vol=True, slope='pts', assets=('TLTX', 'GLDX')))), None),
    'OVdBIL': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL')))), None),
    'COVdBIL': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL')))), None),
    'OVdbes': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best')))), None),
    'COVdbes': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best')))), None),
    'OVwBIL': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='BIL')))), None),
    'COVwBIL': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='BIL')))), None),
    'OVwbes': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='best')))), None),
    'COVwbes': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='best')))), None),
    'SLd03': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.03)))), None),
    'CSLd03': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.03)))), None),
    'SLd05': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.05)))), None),
    'CSLd05': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.05)))), None),
    'SLd08': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.08)))), None),
    'CSLd08': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.08)))), None),
    'SLd12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.12)))), None),
    'CSLd12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.12)))), None),
    'SLd20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.2)))), None),
    'CSLd20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.2)))), None),
    'SLd30': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.3)))), None),
    'CSLd30': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', slow=0.3)))), None),
    'BRd': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', bridge='SPY')))), None),
    'CBRd': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', bridge='SPY')))), None),
    'BRw': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='BIL', bridge='SPY')))), None),
    'CBRw': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='BIL', bridge='SPY')))), None),
    'BRd12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', bridge='SPY', slow=0.12)))), None),
    'CBRd12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', bridge='SPY', slow=0.12)))), None),
    'BRw12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='BIL', bridge='SPY', slow=0.12)))), None),
    'CBRw12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='w', dest='BIL', bridge='SPY', slow=0.12)))), None),
    'BRdQ': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', bridge='QQQ')))), None),
    'CBRdQ': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='BIL', bridge='QQQ')))), None),
    'SLb08': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.08)))), None),
    'CSLb08': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.08)))), None),
    'SLb12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XM150w0s': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,))), None),
    'CFHYs': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'))), None),
    'VD5x4d5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=63, lag=0.0, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TOa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='turn', n=63, cnt=8, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TOb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='turn', n=63, cnt=12, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TOc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='turn', n=63, cnt=16, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TOd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='turn', n=126, cnt=24, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TOe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='turn', n=63, cnt=12, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WHa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WHb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.75, min=4, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WHc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='BEST'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBEST', pn=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBEST', pn=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBEST', pn=252), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBEST', pn=252, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WNa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=126, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WNb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBEST', pn=126, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WNc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='all', tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='eq'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.07, how='eq'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AUa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='w', dest='UUPX'), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AUb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='pct', n=63, dest='UUPX'), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AUc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='w', dest='FXYX'), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AUd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='pct', n=63, dest='FXYX'), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AUe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='w', dest=('UUPX', 'FXYX')), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AUf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='pct', n=63, dest=('UUPX', 'FXYX')), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BSa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', bilsub=dict(assets=('UUPX',), n=63), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BSb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', bilsub=dict(assets=('FXYX',), n=63), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BSc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', bilsub=dict(assets=('UUPX', 'FXYX'), n=63), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BSd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', bilsub=dict(assets=('UUPX', 'FXYX'), n=126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('rot', 63), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('ov', 63), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 63), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 21), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRn': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'LDa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='lcap1m'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'LDb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='lcap3m'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'LDc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='lmom3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'LDd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='lmom5'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'LDe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='either'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WXa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnconf=dict(src='spy', ref='warn', drop=0.05, armed=20, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WXb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnconf=dict(src='basket', ref='warn', drop=0.05, armed=20, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WXc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnconf=dict(src='either', ref='warn', drop=0.05, armed=20, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WXd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnconf=dict(src='either', ref='hi20', drop=0.05, armed=20, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WXe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnconf=dict(src='either', ref='warn', drop=0.05, armed=20, days=10), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WXf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnconf=dict(src='basket', ref='hi20', drop=0.05, armed=20, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NT3a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=3, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NT4a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=4, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NT6a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=6, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NT7a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=7, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NU3a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=3), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NU4a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=4), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NU6a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=6), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NU7a': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=7), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWn10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='n10'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'QNn': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='c52n'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'QNv': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='c52v'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'QNy': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='c52y'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'QNa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='c52any'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'QNt': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='cathany'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWsv': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='surv'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWrv': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='rv'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWsr': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='survrv'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWn20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='n20'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWv1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='v1'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWv3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='v3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWh99': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='h99'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NWh97': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='h97'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NCa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3l': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ll=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3m': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ma150=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3p': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, dest='pct'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJd5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='d', n=5), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJd10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='d', n=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3a50': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ma=50), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3a20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ma=20), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3u': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, dnotup=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw2a50': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, ma=50), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw4a50': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, ma=50), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJd5a50': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='d', n=5, ma=50), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3b20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, bma=20), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3b10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, bma=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw4b20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, bma=20), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw4b10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, bma=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3a50h': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ma=50, half=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MJw3b20h': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, bma=20, half=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BKw2b20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, src='boost', bma=20), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BKw3b20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, src='boost', bma=20), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, rsi=(14, 50), round=10, stay=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, rsi=(14, 50), round=10, stay=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, nolh=True, rsi=(14, 50), round=10, stay=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, rsi=(14, 50), stay=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, stay=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, rsi=(14, 50), round=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RWg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, rsi=(14, 50), round=10, stay=True, half=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CHa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, chan=dict(tf='d', n=10, k=2.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CHb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, chan=dict(tf='w', n=2, k=2.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CHc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, chan=dict(tf='d', n=5, k=2.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CHd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, rsi=(14, 50), round=10, stay=True, chan=dict(tf='d', n=10, k=2.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CHe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, chan=dict(tf='d', n=10, k=3.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw3d5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, days=5, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw3d10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw3d15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, days=15, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw2d10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXrwd10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, rsi=(14, 50), round=10, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw3d10b': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, days=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=5, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=15, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw2d10m': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=2, ma150=True, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw3d10m': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ma150=True, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d10m': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, ma150=True, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw3d10mb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, ma150=True, days=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXd10d10m': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='d', n=10, ma150=True, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=8, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=12, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw5d10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=5, days=10, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d10b': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d10L1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, lag=1, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d10L2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, lag=2, to='BIL'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXw4d10h': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, to='BIL', half=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), major=dict(tf='w', n=4, days=10, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4dd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, to='BIL', prov='dd'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw3lh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, days=10, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lh15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=15, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw5lh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=5, days=10, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw3lh15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=3, days=15, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4dd15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=15, to='BIL', prov='dd'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw5lh15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=5, days=15, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lh8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=8, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lh12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=12, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lhL1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, lag=1, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lhb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw4lhh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, to='BIL', prov='dlh', half=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw5lh8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=5, days=8, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TPw5lh12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=5, days=12, to='BIL', prov='dlh'), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TBw4lhb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBgb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gb', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBc0': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='cash', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBmx': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil=dict(narrow='cash', other='gb'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBbl': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='bil', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBrv': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil=dict(narrow='gb', other='cash'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBup': (dict(top_n=5, pf=dict(kinds=['fade_vs'], th_v=0.70, th_s=0.55, cash=True), fzr=dict(near=0.01, days=10, gl_near=0.03, gl_days=10, parts='fg'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', nobil_n=63, nobil_fb='DBMF', pbreak=dict(slow=100, fast=7, slope=5, hold=10), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(share=1.0, metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_gap=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default plan: + the fading-energy filter on new buys and the whole account in the whipsaw switch's asset (Oct 16, 2026); the 15-session count starts over after more than 10 sessions out of SPY's downtrend (Oct 19, 2026); the no-T-bills pick by 3-month change (Oct 19, 2026); DBMF (managed futures) instead of cash where neither is up (Oct 20, 2026); the price-break haven rule (Oct 24, 2026); the two-scale buy rules: buy freeze and green light (Oct 26, 2026; the stock lower-high part, parts 's', was dropped: -1 to -3 points a year here)
    'NBpb': (dict(top_n=5, pf=dict(kinds=['fade_vs'], th_v=0.70, th_s=0.55, cash=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', nobil_n=63, nobil_fb='DBMF', pbreak=dict(slow=100, fast=7, slope=5, hold=10), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(share=1.0, metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_gap=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default plan before the two-scale buy rules (Oct 24, 2026)
    'NBc3': (dict(top_n=5, pf=dict(kinds=['fade_vs'], th_v=0.70, th_s=0.55, cash=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', nobil_n=63, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(share=1.0, metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_gap=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default before managed futures replaced cash (Oct 19-20, 2026)
    'NBb6': (dict(top_n=5, pf=dict(kinds=['fade_vs'], th_v=0.70, th_s=0.55, cash=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(share=1.0, metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_gap=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default plan before the 3-month no-T-bills pick (Oct 19, 2026)
    'NBg0': (dict(top_n=5, pf=dict(kinds=['fade_vs'], th_v=0.70, th_s=0.55, cash=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(share=1.0, metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default plan before the count restart (Oct 19, 2026)
    'NBhalf': (dict(top_n=5, pf=dict(kinds=['fade_vs'], th_v=0.70, th_s=0.55, cash=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the previous default: half the account in the whipsaw switch's asset
    'NBnf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default before the fading-energy filter (Oct 14-16, 2026)
    'NBpre': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the default plan before the rebound rule (Oct 14, 2026)
    'ANY15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold or bonds leading counts toward the 15 sessions
    'ANY10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # ... 10 sessions
    'ANY20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=20, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # ... 20 sessions
    'NBc10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # same leader, 10 sessions
    'NBc20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=20, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # same leader, 20 sessions
    'ANYU15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold, bonds or the dollar leading counts toward the 15 sessions; it buys the leader
    'ANYU10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold, bonds or the dollar leading counts toward the 10 sessions; it buys the leader
    'ANYU20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=20, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold, bonds or the dollar leading counts toward the 20 sessions; it buys the leader
    'CVa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=2), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule + channel veto
    'CVb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=2), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count + channel veto
    'CVc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=2, tol=0.02), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule + veto down to 2% under the line
    'CVd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=2, tol=0.02), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count + veto down to 2% under the line
    'CVe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=4), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule + veto, bigger swings (4 weeks either side)
    'CVf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=4), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count + veto, bigger swings
    'CVg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=2, tol=0.02, near=0.03), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule; no switch while SPY is 2% under to 3% over the channel bottom
    'CVh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(n=2, tol=0.02, near=0.03), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count; same near-bottom veto
    'BBa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='bb', tol=0.02, near=0.02), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule; no switch within 2% of the lower Bollinger band
    'BBb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='bb', tol=0.02, near=0.02), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count; same band veto
    'WBx': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='wbb', tol=0.02, near=0.03), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule; no switch 2% under to 3% over the weekly lower Bollinger band
    'WBy': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='wbb', tol=0.02, near=0.03), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count; same weekly band veto
    'WCa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='wch', span=26, tol=0.02, near=0.03), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule; near the bottom of a 6-month+ weekly channel
    'WCb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='wch', span=26, tol=0.02, near=0.03), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count; same
    'WCc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='wch', span=52, tol=0.02, near=0.03), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # current rule; near the bottom of a 12-month+ weekly channel
    'WCd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', chveto=dict(kind='wch', span=52, tol=0.02, near=0.03), any_lead=True, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # gold-or-bonds count; same
    'WLa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', wkout=dict(n=2, back='hl'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly LH+LL (2-week swings) -> out; back on a daily higher low
    'WLb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', wkout=dict(n=4, back='hl'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly LH+LL (4-week swings) -> out; back on a daily higher low
    'WLc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', wkout=dict(n=2, back='up'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly LH+LL (2-week swings) -> out; back on a daily higher high + higher low
    'WLd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', wkout=dict(n=4, back='up'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly LH+LL (4-week swings) -> out; back on a daily higher high + higher low
    'WLe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', wkout=dict(n=2, back='hl', below=True), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # as WLa, only while SPY is under the last weekly lower high
    'STd2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='d', m=2.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # Supertrend daily (10, 2) on top of the plan
    'STd3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='d', m=3.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # Supertrend daily (10, 3) on top of the plan
    'STd4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='d', m=4.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # Supertrend daily (10, 4) on top of the plan
    'STw2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='w', m=2.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # Supertrend weekly (10, 2) on top of the plan
    'STw3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='w', m=3.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # Supertrend weekly (10, 3) on top of the plan
    'STw4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='w', m=4.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # Supertrend weekly (10, 4) on top of the plan
    'SRd3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='d', m=3.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=100000))), None),   # Supertrend daily (10, 3) instead of the rotation and downtrend exit
    'SRw3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', stx=dict(tf='w', m=3.0), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=100000))), None),   # Supertrend weekly (10, 3) instead of the rotation and downtrend exit
    'TWn': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='w', back='both', haven='nb'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly time-symmetry exit; haven: the usual no-T-bills pick
    'TWt': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='w', back='both', haven='t'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly time-symmetry exit; haven: gold/bonds past the time check
    'TWu': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='w', back='both', haven='tu'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly time-symmetry exit; haven: time check + up over 6 months
    'TWh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='w', back='both', haven='th'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly time-symmetry exit; haven: time check + higher highs and lows
    'TWx': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='w', back='both', haven='h'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # weekly time-symmetry exit; haven: higher highs and lows only
    'TDn': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='d', back='both', haven='nb'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # daily time-symmetry exit; haven: the usual no-T-bills pick
    'TDt': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='d', back='both', haven='t'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # daily time-symmetry exit; haven: gold/bonds past the time check
    'TDu': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='d', back='both', haven='tu'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # daily time-symmetry exit; haven: time check + up over 6 months
    'TDh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='d', back='both', haven='th'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # daily time-symmetry exit; haven: time check + higher highs and lows
    'TDx': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='d', back='both', haven='h'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # daily time-symmetry exit; haven: higher highs and lows only
    'TDnh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='d', haven='nb'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # reference: back only above the high
    'TWnh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', tsym=dict(tf='w', haven='nb'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # reference: back only above the high
    'HVwt': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='ts:w:t', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the plan as is; where it would hold T-bills, gold / bonds that pass the weekly time check, else cash
    'HVwu': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='ts:w:tu', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the plan as is; where it would hold T-bills, gold / bonds that pass the weekly time check + up 6 months, else cash
    'HVdt': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='ts:d:t', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the plan as is; where it would hold T-bills, gold / bonds that pass the daily time check, else cash
    'HVdu': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='ts:d:tu', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # the plan as is; where it would hold T-bills, gold / bonds that pass the daily time check + up 6 months, else cash
    'SKa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.05, 0.10, 'moved')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 5-10% down and gold/bonds moved 2%+ either way -> stocks
    'SKb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.10, None, 'fell')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 10%+ down and gold/bonds fell 2%+ -> stocks
    'SKc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.15, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 15%+ down and gold or bonds rallied 2%+ -> stocks
    'SKd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.05, 0.10, 'moved'), (0.10, None, 'fell'), (0.15, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # all three
    'SKe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.05, None, 'moved')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 5%+ down (any depth) and gold/bonds moved 2%+ either way -> stocks
    'SKc12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.12, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 0.12+ down and gold or bonds rallied 2%+ -> stocks
    'SKc20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.20, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 0.20+ down and gold or bonds rallied 2%+ -> stocks
    'SKc10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(rules=[(0.10, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SPY 0.10+ down and gold or bonds rallied 2%+ -> stocks
    'SHa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.05, 0.10, 'moved')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKa + only after a daily higher low
    'SHb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.10, None, 'fell')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKb + only after a daily higher low
    'SHc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.15, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKc + only after a daily higher low
    'SHc12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKc12 + only after a daily higher low
    'SHc20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.20, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKc20 + only after a daily higher low
    'SHd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.05, 0.10, 'moved'), (0.10, None, 'fell'), (0.15, None, 'rallied')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKd + only after a daily higher low
    'SHe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', fstock=dict(hl=True, rules=[(0.05, None, 'moved')]), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),   # SKe + only after a daily higher low
    'RGmc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', regate=dict(when='ma', hold='cash'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGms': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', regate=dict(when='ma', hold='stay'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGmb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', regate=dict(when='ma', hold='bil'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGdc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', regate=dict(when='dlh', hold='cash'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGds': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', regate=dict(when='dlh', hold='stay'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGec': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', regate=dict(when='either', hold='cash'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MH3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', minhold=3, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MH5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', minhold=5, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MH10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', minhold=10, major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBnw': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CM1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gb:TLTX,GLDX,DBCX', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CM2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gb:TLTX,GLDX,DBCX', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, pool=('TLTX', 'GLDX', 'DBCX')), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CM3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gb:TLTX,GLDX,DBCX', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, pool=('TLTX', 'GLDX', 'DBCX')), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'DBCX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CR1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gb:TLTX,GLDX,USOX', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CR2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gb:TLTX,GLDX,USOX', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, pool=('TLTX', 'GLDX', 'USOX')), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CR3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gb:TLTX,GLDX,USOX', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, pool=('TLTX', 'GLDX', 'USOX')), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'USOX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBnx': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBns': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CN6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(span=26)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TL3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(kind='line', span=26, touches=3, even=0.5)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TL4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(kind='line', span=26, touches=4, even=0.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TCX': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(span=26, ratio=0.8, par=0.8, ovl=0.75)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TCX3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(span=26, ratio=0.75, par=0.75, ovl=0.7, touches=3, even=0.5)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TL34': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(kind='line', span=26, touches=(3, 4), even=0.5)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TL3r': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(again=True, kind='line', span=26, touches=3, even=0.5)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TL4r': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(again=True, kind='line', span=26, touches=4, even=0.0)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TCXr': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(again=True, span=26, ratio=0.8, par=0.8, ovl=0.75)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CN12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(span=52)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CN6p': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(span=26, par=0.66)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CN12p': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, chan2=dict(span=52, par=0.66)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CN6o': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, twice=True, chan2=dict(span=26, only=True)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CN12o': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, twice=True, chan2=dict(span=52, only=True)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TY6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=4, gap=26)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TY12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=4, gap=52)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TY6o': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, twice=True, tline=dict(n=4, gap=26, only=True)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TY12o': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, twice=True, tline=dict(n=4, gap=52, only=True)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=4)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=8)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRn6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=6)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRn7': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=7)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRn9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=9)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRn10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=10)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRn12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=12)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRd5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=8, days=5)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRd15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=8, days=15)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRlag': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=8, lag=1)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, tline=dict(n=8, tol=0.01)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TRo': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbup', major=dict(tf='w', n=4, days=10, twice=True, tline=dict(n=8, only=True)), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'UU1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbuu', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'UU2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbuu', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True, pool=('TLTX', 'GLDX', 'UUPX')), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'UU3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil='gbuu', major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBnl': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(fstock=dict(hl=True, rules=[(0.12, None, 'rallied')]), nobil='gbup', narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NBru': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(nobil=dict(narrow='gbup', other='cash'), major=dict(tf='w', n=4, days=10, prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TBw4lh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(major=dict(tf='w', n=4, days=10, to='BIL', prov='dlh', twice=True), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PBKa': (dict(top_n=5, pullback=dict(kind='sma5'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PBKw': (dict(top_n=5, pullback=dict(kind='sma5', max_wait=5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PBKd': (dict(top_n=5, pullback=dict(kind='down', max_wait=5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DYTa': (dict(top_n=5, dyn_top=dict(pct=0.67, n_hi=3), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DYTb': (dict(top_n=5, dyn_top=dict(pct=0.80, n_hi=3), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DYTc': (dict(top_n=5, dyn_top=dict(pct=0.67, n_hi=3, lo_pct=0.33, n_lo=7), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SECa': (dict(top_n=5, sec_top=2, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SECb': (dict(top_n=5, sec_top=3, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RMs': (dict(top_n=5, resid=dict(est=252, mode='sum'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RMh': (dict(top_n=5, resid=dict(est=252, mode='sharpe'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RMh2': (dict(top_n=5, resid=dict(est=504, mode='sharpe'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSa15': (dict(top_n=5, trailg=dict(x=0.15), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSa20': (dict(top_n=5, trailg=dict(x=0.2), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSa25': (dict(top_n=5, trailg=dict(x=0.25), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSa30': (dict(top_n=5, trailg=dict(x=0.3), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSw15': (dict(top_n=5, trailg=dict(x=0.15, ma=150), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSw20': (dict(top_n=5, trailg=dict(x=0.2, ma=150), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TSw25': (dict(top_n=5, trailg=dict(x=0.25, ma=150), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CXv': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(crash=dict(kind='vixdd', on=30, dd=0.10, off=25), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CXv35': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(crash=dict(kind='vixdd', on=35, dd=0.10, off=25), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CXvm': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(crash=dict(kind='vixdd', on=30, dd=0.10, off_ma=20), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CXt': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(crash=dict(kind='term', on=1.0, off=0.95, days=1), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CXt2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(crash=dict(kind='term', on=1.0, off=0.95, days=2), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CXt05': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(crash=dict(kind='term', on=1.05, off=0.95, days=1), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZp3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(pick_z=True, narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RPp3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZp9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(pick_z=True, narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 189), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RPp9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 189), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZp12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(pick_z=True, narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 252), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RPp12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 252), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZp': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(pick_z=True, narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq05': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(63, 0.5), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(63, 1.0), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(63, 1.5), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(63, 2.0), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq10n': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(63, 1.0), relz_up=False, narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq10w6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(126, 1.0), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RZq10c5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(relz=(63, 1.0), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WZs': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, zsel=True, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGz05': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(rg_z=(63, 0.5), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGz10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(rg_z=(63, 1.0), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGz15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(rg_z=(63, 1.5), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGz20': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(rg_z=(63, 2.0), narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ05m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz5m3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ05m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz5m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ10m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz10m3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ10m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz10m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ15m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz15m3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ15m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz15m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ20m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz20m3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NZ20m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nz20m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HCa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, half=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HC4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl15m4', half=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HC6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl15m6', half=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BX50': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma50', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BXnone': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BX100': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma100', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BX180': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma180', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BXoff': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RQ1': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 21, True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RQ3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 63, True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RQ6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126, True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RQ9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 189, True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RQ12': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 252, True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=63, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=84, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=105, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m7': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=147, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=168, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH50m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=189, loss=0.5, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH65m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=63, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH65m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=84, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH65m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=105, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH65m7': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=147, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH65m8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=168, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH65m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=189, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=63, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=84, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=105, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m7': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=147, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=168, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH70m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=189, loss=0.7, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=63, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=84, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=105, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=126, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m7': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=147, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m8': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=168, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WH80m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5), side=dict(metric='whip', n=189, loss=0.8, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL10m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl10m3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL10m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl10m4'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL10m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl10m5'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL10m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl10m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL10m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl10m9'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL15m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl15m4'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL15m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl15m5'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL15m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl15m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL15m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl15m9'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL20m3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl20m3'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL20m4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl20m4'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL20m5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl20m5'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL20m6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl20m6'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NL20m9': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=5, w='nl20m9'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NCb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=10, days=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NCc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=5, days=10), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NCd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(narrowcash=dict(delay=10, days=10), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NPa': (dict(top_n=5, narrowpause=dict(days=10), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NPb': (dict(top_n=5, narrowpause=dict(days=5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NPc': (dict(top_n=5, narrowpause=dict(days=5, delay=10), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXa': (dict(top_n=5, techx=dict(kind='macd_sig', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXb': (dict(top_n=5, techx=dict(kind='macd_neg', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXc': (dict(top_n=5, techx=dict(kind='ichi_cloud', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXd': (dict(top_n=5, techx=dict(kind='tk', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXe': (dict(top_n=5, techx=dict(kind='ma50', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXf': (dict(top_n=5, techx=dict(kind='macd_neg'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TXg': (dict(top_n=5, techx=dict(kind='ichi_cloud'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CKa': (dict(top_n=5, chanbrk=dict(on='stock', n=126, confirm=2, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CKb': (dict(top_n=5, chanbrk=dict(on='stock', n=63, confirm=2, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CKc': (dict(top_n=5, chanbrk=dict(on='stock', n=126, confirm=2), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CKd': (dict(top_n=5, chanbrk=dict(on='sector', n=126, confirm=2), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CKe': (dict(top_n=5, chanbrk=dict(on='sector', n=63, confirm=2), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CKf': (dict(top_n=5, chanbrk=dict(on='sector', n=126, confirm=2, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MRa': (dict(top_n=5, rsiweak=dict(th=45, macro=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MRb': (dict(top_n=5, rsiweak=dict(th=45, macro=True, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MRc': (dict(top_n=5, rsiweak=dict(th=45), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MRd': (dict(top_n=5, rsiweak=dict(th=45, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='all', to='BIL', hi=55, lo=45), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='all', to='SPY', hi=55, lo=45), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='boost', to='BIL', hi=55, lo=45), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='boost', to='SPY', hi=55, lo=45), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSk': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='all', to='SPY', hi=45, lo=55), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='all', to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='all', to='SPY'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='boost', to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='boost', to='SPY'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='all', to='BIL', strict=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MSf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(massell=dict(on=3, off=2, scope='boost', to='BIL', strict=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KPd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(spytop=dict(tf='w', n=39, r2=0.5, mode='flat'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KPe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(spytop=dict(tf='w', n=39, r2=0.5, mode='turned'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KPf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(spytop=dict(tf='w', n=52, r2=0.7, mode='flat'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KTa': (dict(top_n=5, rtop=dict(on='stock', n=63, r2=0.7, mode='flat'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KTb': (dict(top_n=5, rtop=dict(on='stock', n=63, r2=0.7, mode='turned'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KTc': (dict(top_n=5, rtop=dict(on='stock', n=63, r2=0.7, mode='turned', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KSa': (dict(top_n=5, rtop=dict(on='sector', n=63, r2=0.7, mode='flat'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KSb': (dict(top_n=5, rtop=dict(on='sector', n=63, r2=0.7, mode='turned'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KSc': (dict(top_n=5, rtop=dict(on='sector', n=63, r2=0.7, mode='turned', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KPa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(spytop=dict(n=63, r2=0.7, mode='turned'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KPb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(spytop=dict(n=63, r2=0.7, mode='flat'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'KPc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(spytop=dict(n=126, r2=0.7, mode='turned', full=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SXa': (dict(top_n=5, sectch=dict(tf='d', how='both'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SXb': (dict(top_n=5, sectch=dict(tf='w', how='both'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SXc': (dict(top_n=5, sectch=dict(tf='d', how='lh'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SXd': (dict(top_n=5, sectch=dict(tf='w', how='lh'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SXe': (dict(top_n=5, sectch=dict(tf='d', how='both', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SXf': (dict(top_n=5, sectch=dict(tf='w', how='both', sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNa': (dict(top_n=5, hhnow=dict(tf='d', m=2, r2=0.9), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNb': (dict(top_n=5, hhnow=dict(tf='d', m=2, r2=0.95), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNc': (dict(top_n=5, hhnow=dict(tf='w', m=2, r2=0.9), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNd': (dict(top_n=5, hhnow=dict(tf='w', m=2, r2=0.95), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNe': (dict(top_n=5, hhnow=dict(tf='d', m=2, r2=0.9, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNf': (dict(top_n=5, hhnow=dict(tf='d', m=2, r2=0.95, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNg': (dict(top_n=5, hhnow=dict(tf='w', m=2, r2=0.9, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HNh': (dict(top_n=5, hhnow=dict(tf='w', m=2, r2=0.95, sell=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTa': (dict(top_n=5, hhline=dict(tf='w', m=3, r2=0.9, tol=0.05), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTb': (dict(top_n=5, hhline=dict(tf='w', m=3, r2=0.9, tol=0.02), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTc': (dict(top_n=5, hhline=dict(tf='w', m=4, r2=0.95, tol=0.05), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTd': (dict(top_n=5, hhline=dict(tf='d', m=3, r2=0.9, tol=0.03), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTf': (dict(top_n=5, hhline=dict(tf='d', m=3, r2=0.9, tol=0.02), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTg': (dict(top_n=5, hhline=dict(tf='d', m=3, r2=0.9, tol=0.05), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTh': (dict(top_n=5, hhline=dict(tf='d', m=3, r2=0.95, tol=0.03), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTi': (dict(top_n=5, hhline=dict(tf='d', m=3, r2=0.8, tol=0.03), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTj': (dict(top_n=5, hhline=dict(tf='d', m=4, r2=0.9, tol=0.03), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTk': (dict(top_n=5, hhline=dict(tf='d', m=3, r2=0.9, tol=0.0), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HTe': (dict(top_n=5, hhline=dict(tf='w', m=3, r2=0.8, tol=0.05), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HBa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.15, to='SPY'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HBb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.15, to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HBc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.10, to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HBd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.20, to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HBe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.15, to='BIL', full=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HSa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=None, stretch=1.5, to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HSb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.08, stretch=1.5, to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HSc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(brake=dict(th=0.10, stretch=1.2, to='BIL'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CCa': (dict(top_n=5, max_corr=0.7, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CCb': (dict(top_n=5, max_corr=0.6, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CCc': (dict(top_n=5, max_corr=0.5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SCa': (dict(top_n=5, sector_cap=2, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SCb': (dict(top_n=5, sector_cap=2, cap_level='sector', vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SCc': (dict(top_n=5, sector_cap=3, cap_level='sector', vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DDa': (dict(top_n=5, wdown=dict(how='ddays', n=105, th=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DDb': (dict(top_n=5, wdown=dict(how='ddays', n=105, th=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DDc': (dict(top_n=5, wdown=dict(how='ddays', n=105, th=0.45), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FGa': (dict(top_n=5, fresh='same', vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FGb': (dict(top_n=5, fresh='next', vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WDa': (dict(top_n=5, wdown=dict(how='down', min=1), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WDb': (dict(top_n=5, wdown=dict(how='down', min=4), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WDc': (dict(top_n=5, wdown=dict(how='down', min=8), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WDd': (dict(top_n=5, wdown=dict(how='lh2'), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WSa': (dict(top_n=5, wdown=dict(how='pct', n=63), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WSb': (dict(top_n=5, wdown=dict(how='pct', n=40), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WSc': (dict(top_n=5, wdown=dict(how='pct', n=21), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SPa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, spy_pct=21, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SPb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, spy_pct=42, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SPc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, spy_pct=63, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SPd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, spy_pct=126, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SOa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', spy_pct=63, dest='best', slow=0.12)))), None),
    'SOb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', spy_pct=126, dest='best', slow=0.12)))), None),
    'SBa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, spy_pct=63, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', spy_pct=63, dest='best', slow=0.12)))), None),
    'PUa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 126), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 100), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PUd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 100), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 150), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PUb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 150), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 189), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRk': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 252), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PUc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 252), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 63, True), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PRg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', pick=('both', 21, True), dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'UXa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX', 'UUPX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='ow', m=1.5, hold=20, persist=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='ow', m=1.5, hold=10, persist=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='ow', m=2.0, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.07, how='ow', m=1.5, hold=20), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DPf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', dip=dict(th=0.10, how='ow', m=2.0, hold=10), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AFa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='pct', n=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AFb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='w'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AFc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='pct', n=21), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AFd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='d'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AFe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='pct', n=63, out='pct', out_n=10), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'AFf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', allfall=dict(how='w', out='pct', out_n=10), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', rg_n=42, tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', rg_n=126, tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='side', rg_n=21, tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_conf=0, tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_conf=0, rg_fear='f', tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_boost='all', rg_conf=0, tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RGf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), rg_conf=5, tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WNx': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSa': (dict(top_n=5, rise=dict(r1m=0.0), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSb': (dict(top_n=5, rise=dict(ma50=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSc': (dict(top_n=5, rise=dict(r1m=0.0, ma50=True), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSd': (dict(top_n=5, rise=dict(r1m=0.05), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSe': (dict(top_n=5, skip=0, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSf': (dict(top_n=5, skip=10, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RSg': (dict(top_n=5, fac=dict(f='r1m', w=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GVa': (dict(top_n=5, fac=dict(f='hvol', w=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GVb': (dict(top_n=5, fac=dict(f='hvol', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GMa': (dict(top_n=5, fac=dict(f='ma200', w=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GMb': (dict(top_n=5, fac=dict(f='ma200', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GUa': (dict(top_n=5, fac=dict(f='vsurge', w=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GUb': (dict(top_n=5, fac=dict(f='vsurge', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'GVc': (dict(top_n=5, fac=dict(f='hvol', w=0.2), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FSa': (dict(top_n=5, fac=dict(f='smooth', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FSb': (dict(top_n=5, fac=dict(f='smooth', w=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FHa': (dict(top_n=5, fac=dict(f='hi52', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FHb': (dict(top_n=5, fac=dict(f='hi52', w=0.33), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FRa': (dict(top_n=5, fac=dict(f='radj', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FBa': (dict(top_n=5, fac=dict(f='blend', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FVa': (dict(top_n=5, fac=dict(f='upvol', w=0.5), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'FCa': (dict(top_n=5, sector_cap=2, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TKa': (dict(top_n=5, keep_rank=12, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TKb': (dict(top_n=5, keep_rank=15, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TLa': (dict(top_n=5, ltk=dict({'from': 200, 'rank': 30}), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TLb': (dict(top_n=5, ltk=dict({'from': 180, 'rank': 50}), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TFa': (dict(top_n=5, ltk=dict({'lose': 6}), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TCa': (dict(top_n=5, keep_rank=12, ltk=dict({'from': 200, 'rank': 30, 'lose': 6}), vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'TMa': (dict(top_n=5, monthly=True, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=0.25), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=1.0), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', bth=0.30, out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=0.5, back='ma20'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=0.5, back='calm'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', bth=0.30, out=1.0), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=0.25, back='ma20'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'BRi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='broad', out=1.0, back='calm'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', back='hl'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', back='hl', out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', fr=0.0), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', fr=0.05), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', fr=0.05, out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ZFh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='fresh', back='ma20', out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', back='hl'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', back='ma20'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='w'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='w', back='hl'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='big'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='big', back='hl'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='brk', back='hl'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='big', back='ma20'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='big', off=0.15, back='hl'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'YQj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', trig='w', back='ma20'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=0), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='rising', conf=0), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=10), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=5, noreset=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=0, out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=5, out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=0, back='up'), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='rising', conf=5, noreset=True), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WQj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(warnq=dict(dest='duo', conf=10, noreset=True, out=0.5), side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'PXa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=63, slow=0.12)))), None),
    'PXb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=126, slow=0.12)))), None),
    'PXc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=63, stay=True, slow=0.12)))), None),
    'PXd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=126, stay=True, slow=0.12)))), None),
    'PXe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=63, back_pct=63, slow=0.12)))), None),
    'PXf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=63, nodown=True, slow=0.12)))), None),
    'PXg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=63, stay=True, back_pct=63, slow=0.12)))), None),
    'PXh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PBMIX', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='pct', pn=126, back_pct=126, slow=0.12)))), None),
    'XRa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PROT', pn=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PROT', pn=126, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PROT', pn=126, nodown=True, none='boost'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PROT', pn=63, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PROT', sel='grad'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='PROTMIX', pn=126, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='PROT', pn=126, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='PROT', pn=252, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XRi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='PROT', sel='grad'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='PBEST', pn=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='PBEST', pn=252, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.75, min=4, thr=0.5, mode='PBEST', pn=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.75, min=4, thr=0.5, mode='PBEST', pn=252, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WPj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='PBMIX', pn=252, nodown=True), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='BMIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=126, loss=0.65, min=6, thr=0.5, mode='BNS'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='BEST'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='BMIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.75, min=4, thr=0.5, mode='BEST'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=42, loss=0.75, min=3, thr=0.5, mode='BEST'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WBh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='BNS'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WHd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=63, loss=0.6, min=4, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WHe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='whip', n=42, loss=0.75, min=3, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=63, lag=-0.05, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=63, lag=-0.10, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=42, lag=-0.05, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=63, lag=-0.05, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=126, lag=-0.10, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'MFg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='mom', n=63, lag=-0.15, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=126, flat=0.03, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=126, flat=0.06, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=126, flat=0.05, lows=True, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=126, flat=0.05, daily=True, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=126, flat=0.05, daily=True, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=252, flat=0.03, daily=True, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'HHg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='hh', n=126, flat=0.08, daily=True, lows=True, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDk': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=126, thr=0.07, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDl': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='r2', n=126, thr=0.1, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDm': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='band', n=63, gap=0.03, slope=0.02, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDn': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='band', n=63, gap=0.05, slope=0.03, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDo': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=126, thr=0.1, near=0.05, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDp': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='band', n=63, gap=0.03, slope=0.02, thr=0.5, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDq': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='r2', n=126, thr=0.2, near=0.04, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=63, thr=0.15, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=63, thr=0.2, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=126, thr=0.15, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=126, thr=0.25, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='r2', n=126, thr=0.3, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='r2', n=126, thr=0.5, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=126, thr=0.2, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='r2', n=126, thr=0.4, mode='MIX'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=126, thr=0.2, mode='QQQ'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SDj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(side=dict(metric='er', n=63, thr=0.1, mode='SPY'), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=2, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=2, delay=3, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=2, delay=10, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.0, vol=2, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=3.0, vol=2, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=2, delay=5, hold=21), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=2, delay=5, hold=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CQh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.0, vol=2, delay=10, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPa': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=3, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPb': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=3, delay=3, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPc': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=4, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPd': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=5, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPe': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.0, vol=3, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPf': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=3.0, vol=3, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPg': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=3, delay=5, hold=21), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPh': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=3, delay=5, hold=126), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPi': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=3, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPj': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='QQQ', k=2.5, vol=4, delay=5, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CPk': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(cap=dict(src='SPY', k=2.5, vol=3, delay=10, hold=63), tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x4d10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=10), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x4d15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=15), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD7x4d5': (dict(top_n=5, vx=dict(move='day', th=0.07, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD7x4d10': (dict(top_n=5, vx=dict(move='day', th=0.07, vol_k=4, delay=10), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD7x4d15': (dict(top_n=5, vx=dict(move='day', th=0.07, vol_k=4, delay=15), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x4d5': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x4d10': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=4, delay=10), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x4d15': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=4, delay=15), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x3d5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=3, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x3d10': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=3, delay=10), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x3d15': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=3, delay=15), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x5': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x6': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=6), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD3x4': (dict(top_n=5, vx=dict(move='day', th=0.03, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD7x4': (dict(top_n=5, vx=dict(move='day', th=0.07, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x45': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4.5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x35': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=3.5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x5': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW15x4': (dict(top_n=5, vx=dict(move='week', th=0.15, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW30x4': (dict(top_n=5, vx=dict(move='week', th=0.3, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x2': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=2), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x3': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=3), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD5x4': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD10x2': (dict(top_n=5, vx=dict(move='day', th=0.1, vol_k=2), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD10x3': (dict(top_n=5, vx=dict(move='day', th=0.1, vol_k=3), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VD10x4': (dict(top_n=5, vx=dict(move='day', th=0.1, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x2': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=2), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x3': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=3), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VW20x4': (dict(top_n=5, vx=dict(move='week', th=0.2, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VE50x2': (dict(top_n=5, vx=dict(move='entry', th=0.5, vol_k=2), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VE50x3': (dict(top_n=5, vx=dict(move='entry', th=0.5, vol_k=3), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'VE50x4': (dict(top_n=5, vx=dict(move='entry', th=0.5, vol_k=4), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SL10': (dict(top_n=10, keep_rank=20, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SL10L': (dict(top_n=10, keep_rank=20, look=252, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'M10': (dict(top_n=10, look=252, skip=21, monthly=True), None),
    'M10k': (dict(top_n=10, look=252, skip=21, monthly=True, keep_rank=20), None),
    'M10nq': (dict(top_n=10, look=252, skip=21, monthly=True, only_set='ndx'), None),
    'M10sp': (dict(top_n=10, look=252, skip=21, monthly=True, only_set='sp_now'), None),
    'M5w': (dict(top_n=5, keep_rank=10), None),
    'SLnq': (dict(top_n=5, only_set='ndx', xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'XDa': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.0, x_a=2.0, back_n=10)))), None),
    'XDb': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.5, x_a=2.0, back_n=10)))), None),
    'XDc': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.0, x_a=2.0, x_up=True, back_n=10)))), None),
    'XDd': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.0, x_a=2.0, back_n=20)))), None),
    'XDe': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.0, x_a=2.0, xw=5, back_n=10)))), None),
    'XDf': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.0, x_a=2.0, x150=False, back_n=10)))), None),
    'XDg': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=3.0, x_a=2.5, back_n=10)))), None),
    'XDh': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev|slow', x_k=2.0, x_a=2.0)))), None),
    'XDao': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev', x_k=2.0, x_a=2.0, back_n=10)))), None),
    'XDbo': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev', x_k=2.5, x_a=2.0, back_n=10)))), None),
    'XDco': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev', x_k=2.0, x_a=2.0, x_up=True, back_n=10)))), None),
    'XDgo': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev', x_k=3.0, x_a=2.5, back_n=10)))), None),
    'XDho': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='xdev', x_k=2.0, x_a=2.0)))), None),
    'MAa': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w')))), None),
    'WRa': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', wk_red='last', d_ll=True)))), None),
    'WRb': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', wk_red='last', d_ll=True, confirm_out=15)))), None),
    'WRc': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', wk_red='cur', d_ll=True)))), None),
    'WRd': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', ma_fall=0, ma_below=True, wk_red='last', d_ll=True)))), None),
    'WRe': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ma20w', wk_red='last', d_ll=True)))), None),
    'WRf': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', wk_red='last', d_ll=True, ma_150=True)))), None),
    'WRg': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w|slow', wk_red='last', d_ll=True)))), None),
    'WRh': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', wk_red='last', d_ll=True, ma_below=True)))), None),
    'MAi': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ma20w')))), None),
    'MAj': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ma20w', ma_up_exit=True)))), None),
    'MAk': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ma20w', ma_up_exit=True, confirm_out=15)))), None),
    'MAb': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', confirm_out=15)))), None),
    'MAc': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', ma_below=True)))), None),
    'MAd': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', ma_below=True, confirm_out=15)))), None),
    'MAe': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', ma_fall=2)))), None),
    'MAf': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', ma_up_exit=True)))), None),
    'MAg': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w|slow')))), None),
    'MAh': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, back150=False, trig='ma20w', ma_150=True)))), None),
    'CSLb12': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SLb20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.2)))), None),
    'CSLb20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('c_hy', 0.75, 'best'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.2)))), None),
    'SQ30': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), qqq=0.3, legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SQ50': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), qqq=0.5, legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'ST10': (dict(top_n=10, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SL12': (dict(top_n=5, look=252, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SK20': (dict(top_n=5, keep_rank=20, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SLRQ': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('lowrate', 0.0, 'QQQ'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SR63S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel63', 0.0, 'SPY'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SR63Q': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel63', 0.0, 'QQQ'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SR126S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel126', 0.0, 'SPY'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SR126Q': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel126', 0.0, 'QQQ'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SR252S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel252', 0.0, 'SPY'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'SR252Q': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gate=('rel252', 0.0, 'QQQ'), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'L2d': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ll2', ll_tf='d', back150=False)))), None),
    'L2dA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ll2', ll_tf='d')))), None),
    'L2w': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ll2', ll_tf='w', back150=False)))), None),
    'L2wA': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ll2', ll_tf='w')))), None),
    'L2dS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ll2|slow', ll_tf='d')))), None),
    'L2wS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='ll2|slow', ll_tf='w')))), None),
    'BKdS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='d')))), None),
    'BKwS': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='w')))), None),
    'BKd': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk', brk_tf='d')))), None),
    'DC20S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='don|slow', don_n=20)))), None),
    'DC50S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='don|slow', don_n=50)))), None),
    'BG2S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='big|slow', big_k=2.0)))), None),
    'BG3S': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='big|slow', big_k=3.0)))), None),
    'BG3S10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='big|slow', big_k=3.0, back_n=10)))), None),
    'BG3S20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='big|slow', big_k=3.0, back_n=20)))), None),
    'BG2S10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='big|slow', big_k=2.0, back_n=10)))), None),
    'BG4S10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='big|slow', big_k=4.0, back_n=10)))), None),
    'BKdS10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='d', back_n=10)))), None),
    'BKwS20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='w', back_n=20)))), None),
    'VL175': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=1.75, back_n=10)))), None),
    'VL2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0, back_n=10)))), None),
    'VL25': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.5, back_n=10)))), None),
    'VL3': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=3.0, back_n=10)))), None),
    'VL2n': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0, back_n=10, vol_150=False)))), None),
    'VL2s': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0)))), None),
    'VL2d': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0, vol_dn=0.015, back_n=10)))), None),
    'VL2b20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0, back_n=20)))), None),
    'VN2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0, back_n=10, vol_150=False)))), None),
    'VN25': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.5, back_n=10, vol_150=False)))), None),
    'VN3': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=3.0, back_n=10, vol_150=False)))), None),
    'VB25': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.5, back_n=10)))), None),
    'VB2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.0, back_n=10)))), None),
    'VN25b5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='vol|slow', vol_k=2.5, back_n=5, vol_150=False)))), None),
    'B2d': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='d', brk2=True)))), None),
    'B2d10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='d', brk2=True, back_n=10)))), None),
    'B2d20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='brk|slow', brk_tf='d', brk2=True, back_n=20)))), None),
    'CB0': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_below=0, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CB3': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_below=3, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CB5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_below=5, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CB8': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_below=8, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'CB10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, conf_below=10, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WC': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, wait_cash='cand', overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WC150': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, wait_cash='cand', wait150=True, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WD150': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, wait_cash='down', wait150=True, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WD': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, wait_cash='down', overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NOW': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=0,  overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'NOW5': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=5,  overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'RS20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=20)))), None),
    'RS20b10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=20, back_n=10)))), None),
    'RS20b20': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=20, back_n=20)))), None),
    'RS10': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=10)))), None),
    'RS40': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=40)))), None),
    'RS3t2': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=20, rsi_pts=3, rsi_tol=2.0)))), None),
    'RS4t35': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12, trig='rsi|slow', rsi_w=20, rsi_tol=3.5)))), None),
    'DR10': (dict(top_n=5, daily_rebal=True, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DR15': (dict(top_n=5, daily_rebal=True, keep_rank=15, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DR20': (dict(top_n=5, daily_rebal=True, keep_rank=20, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DR30': (dict(top_n=5, daily_rebal=True, keep_rank=30, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DR5': (dict(top_n=5, daily_rebal=True, keep_rank=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'DR7': (dict(top_n=5, daily_rebal=True, keep_rank=7, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'WK5': (dict(top_n=5, keep_rank=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), legrot=dict(tf='d', vol=True, slope='pts', spy_down=True, assets=('TLTX', 'GLDX'), confirm=15, overlay=dict(back_tf='d', dest='best', slow=0.12)))), None),
    'QG': (dict(top_n=5, xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,), gates=[('spy150', 0.25), ('eq100', 0.25)])), None),
    'XACC': (dict(top_n=5, xit='accel', plan=dict(ladder=(1.0,), gate=('spy6m', 0.75, 'best'))), None),
    'XACCE': (dict(top_n=5, xit='accel', plan=dict(ladder=(1.0,), gates=[('spy6m', 0.25), ('eq100', 0.25)])), None),
    'G2A': (dict(top_n=5, plan=dict(ladder=(1.0,), lev=(2.0, None))), None),
    'G2D': (dict(top_n=5, plan=dict(ladder=(1.0,), lev=(2.0, 'both'))), None),
    'G15S': (dict(top_n=5, plan=dict(ladder=(1.0,), lev=(1.5, 'spy200'))), None),
    'G2S': (dict(top_n=5, plan=dict(ladder=(1.0,), lev=(2.0, 'spy200'))), None),
    'G15D': (dict(top_n=5, plan=dict(ladder=(1.0,), lev=(1.5, 'both'))), None),
    'G3D': (dict(top_n=5, plan=dict(ladder=(1.0,), lev=(3.0, 'both'))), None),
    'RA': (dict(top_n=5, with_sleeve='all', regime='spy200', plan=dict(ladder=(1.0,))), None),
    'RA2': (dict(top_n=5, with_sleeve='all', regime='spy200', weak_funds_only=True, plan=dict(ladder=(1.0,))), None),
    'RB': (dict(top_n=5, with_sleeve='all', regime='spy6m', plan=dict(ladder=(1.0,))), None),
    'RC': (dict(top_n=5, with_sleeve='all', regime='breadth', plan=dict(ladder=(1.0,))), None),
    'RD': (dict(top_n=5, with_sleeve='all', regime='both', plan=dict(ladder=(1.0,))), None),
    'E6': (dict(top_n=5, with_sleeve='eq', plan=dict(ladder=(1.0,))), None),
    'A6': (dict(top_n=5, with_sleeve='all', plan=dict(ladder=(1.0,))), None),
    'L6': (dict(top_n=5, with_sleeve='lev', plan=dict(ladder=(1.0,))), None),
    'L3': (dict(top_n=5, with_sleeve='lev', look=63, skip=0, plan=dict(ladder=(1.0,))), None),
    'L1': (dict(top_n=5, with_sleeve='lev', look=21, skip=0, plan=dict(ladder=(1.0,))), None),
    'X6': (dict(top_n=5, with_sleeve=True, plan=dict(ladder=(1.0,))), None),
    'X3': (dict(top_n=5, with_sleeve=True, look=63, skip=0, plan=dict(ladder=(1.0,))), None),
    'X1': (dict(top_n=5, with_sleeve=True, look=21, skip=0, plan=dict(ladder=(1.0,))), None),
    'Y3': (dict(top_n=5, look=63, skip=0, plan=dict(ladder=(1.0,))), None),
    'Y1': (dict(top_n=5, look=21, skip=0, plan=dict(ladder=(1.0,))), None),
    'N1': (dict(top_n=5, plan=dict(ladder=(1.0,))), None),
    'B1S': (dict(top_n=5, vx=dict(move='day', th=0.05, vol_k=4, delay=5), xit='accel_2.0', xgate=('ma150', 0), plan=dict(ladder=(1.0,))), None),
    'N2': (dict(top_n=5, weighting='drift', plan=dict(ladder=(1.0,))), None),
    'N3': (dict(top_n=5, weighting='drift', rsix=True, keep_all=True, plan=dict(ladder=(1.0,))), None),
    'N4': (dict(top_n=5, weighting='drift', rsix=True, keep_rank=30, plan=dict(ladder=(1.0,))), None),
    'N5': (dict(top_n=5, weighting='drift', plan=dict(ladder=True)), None),
    'S1': (dict(top_n=5, rsix=True, keep_all=True, plan=dict(ladder=True)), None),
    'S2': (dict(top_n=5, rsix=True, keep_rank=30, plan=dict(ladder=True)), None),
    'S3': (dict(top_n=5, keep_rank=30, plan=dict(ladder=True)), None),
    'S4': (dict(top_n=5, keep_rank=20, plan=dict(ladder=True)), None),
    'zA': (dict(top_n=5, zmode='top15', plan=dict(ladder=True)), None),
    'zA5': (dict(top_n=5, zmode='top15', keep_rank=5, plan=dict(ladder=True)), None),
    'zR': (dict(top_n=5, zmode='rankall', plan=dict(ladder=True)), None),
    'zR5': (dict(top_n=5, zmode='rankall', keep_rank=5, plan=dict(ladder=True)), None),
    'zS': (dict(top_n=5, zmode='zsum', plan=dict(ladder=True)), None),
    'zS5': (dict(top_n=5, zmode='zsum', keep_rank=5, plan=dict(ladder=True)), None),
    'rsA': (dict(top_n=5, rsum=26, plan=dict(ladder=True)), None),
    'rsB': (dict(top_n=5, rsum=26, keep_rank=5, plan=dict(ladder=True)), None),
    'rsB13': (dict(top_n=5, rsum=13, keep_rank=5, plan=dict(ladder=True)), None),
    'kr5': (dict(top_n=5, keep_rank=5, plan=dict(ladder=True)), None),
    'dp20': (dict(top_n=5, dipf=0.20, plan=dict(ladder=True)), None),
    'dp15': (dict(top_n=5, dipf=0.15, plan=dict(ladder=True)), None),
    'dp30': (dict(top_n=5, dipf=0.30, plan=dict(ladder=True)), None),
    'dp25': (dict(top_n=5, dipf=0.25, plan=dict(ladder=True)), None),
    'dp35': (dict(top_n=5, dipf=0.35, plan=dict(ladder=True)), None),
    'dp40': (dict(top_n=5, dipf=0.40, plan=dict(ladder=True)), None),
    'dp20x1': (dict(top_n=5, dipf=0.20, dip_max=1, plan=dict(ladder=True)), None),
    'sfA': (dict(top_n=5, sfilt='fill', plan=dict(ladder=True)), None),
    'sfB': (dict(top_n=5, sfilt='cash', plan=dict(ladder=True)), None),
    'sfW': (dict(top_n=5, sfilt='wait', plan=dict(ladder=True)), None),
    'sfC': (dict(top_n=5, sfilt='all', plan=dict(ladder=True)), None),
    'sfH': (dict(top_n=5, sfilt='fill', sf_which='hl', plan=dict(ladder=True)), None),
    'sfR': (dict(top_n=5, sfilt='fill', sf_which='rsi', plan=dict(ladder=True)), None),
    'n12w': (dict(top_n=12), None),
    'n12m': (dict(top_n=12, monthly=True), None),
    'n12m_ra': (dict(top_n=12, monthly=True, risk_adj=True), None),
    'v2': (dict(top_n=12, monthly=True, risk_adj=True, vol_target=0.20, vol_window=126), None),
}


def _fz_weekly(daily):
    """ISO-week bars dated by the week's last session (as mtl/rotation.py weekly in the live repo)."""
    out, key = [], None
    for b in daily:
        k = date.fromisoformat(b[0][:10]).isocalendar()[:2]
        if k != key:
            key = k
            out.append([b[0], b[1], b[2], b[3], b[4]])
        else:
            w = out[-1]
            w[0], w[2], w[3], w[4] = b[0], max(w[2], b[2]), min(w[3], b[3]), b[4]
    return [tuple(w) for w in out]


class _FzReader:
    """The swing reads of the live repo's mtl/rotation.py Reader.labels: 3-bar daily swings on the last 320 daily
    bars, 2-bar weekly swings on the weekly bars of the last 900 daily bars, labeled by mtl.structure."""

    def __init__(self, bars):
        from mtl.structure import find_swings, label_structure
        self._fs, self._ls = find_swings, label_structure
        self.bars = {t: [tuple([b[0][:10]] + list(b[1:5])) for b in bs] for t, bs in bars.items() if bs}
        self.days = {t: [b[0] for b in bs] for t, bs in self.bars.items()}
        self._lab = {}

    def labels(self, t, d, tf='d'):
        if (t, d, tf) not in self._lab:
            from bisect import bisect_right as _b
            j = _b(self.days[t], d)
            daily = self.bars[t][max(0, j - (900 if tf == 'w' else 320)):j]
            bs = _fz_weekly(daily) if tf == 'w' else daily
            self._lab[(t, d, tf)] = self._ls(self._fs(bs, n=2 if tf == 'w' else 3))
        return self._lab[(t, d, tf)]

    def two(self, t, d, tf, kind):
        return [x['price'] for x in self.labels(t, d, tf) if x['type'] == kind][-2:]


def fz_windows(spy_bars, cal, start, near=0.01, days=10, gl_near=0.03, gl_days=10):
    """The live repo's mtl/fractal.py spy_windows: (frozen, green) calendar indices. At a week's last close (the next
    session in a later ISO week; the calendar's last day is skipped), the buy freeze when SPY is within `near` of its
    last weekly swing high, that high is below the one before and the daily swing highs are falling too; the green light
    when the weekly swing lows are rising, SPY is within `gl_near` above the last one and the daily swing lows rise too."""
    Rz = _FzReader({'SPY': spy_bars})
    px = {b[0][:10]: b[4] for b in spy_bars}
    frozen, green = set(), set()
    for k in range(1, len(cal) - 1):
        d = cal[k]
        if d < start or d not in px:
            continue
        if date.fromisoformat(cal[k + 1]).isocalendar()[:2] == date.fromisoformat(d).isocalendar()[:2]:
            continue
        c = px[d]
        wh, dh = Rz.two('SPY', d, 'w', 'high'), Rz.two('SPY', d, 'd', 'high')
        wl, dl = Rz.two('SPY', d, 'w', 'low'), Rz.two('SPY', d, 'd', 'low')
        if len(wh) == 2 and wh[1] < wh[0] and c >= wh[1] * (1 - near) and len(dh) == 2 and dh[1] < dh[0]:
            frozen.update(range(k + 1, k + 1 + days))
        if len(wl) == 2 and wl[1] > wl[0] and c <= wl[1] * (1 + gl_near) and len(dl) == 2 and dl[1] > dl[0]:
            green.update(range(k + 1, k + 1 + gl_days))
    return frozen, green


def month_ends(calendar):
    out = []
    for k, d in enumerate(calendar):
        if k + 1 == len(calendar) or calendar[k + 1][:7] != d[:7]:
            out.append(d)
    return out


def run_one(args):
    key, kw, boost, exclude = args
    P = G['P']
    base = P['elig_pit']
    if kw.get('lev_etf'):
        _b0 = base
        base = (lambda t, d: (t in G['LEV'] and t in P['prices']) or (t not in G['LEV'] and _b0(t, d)))
    else:
        _b1 = base
        base = (lambda t, d: t not in G['LEV'] and _b1(t, d))
    kw = dict(kw)
    kw.pop('lev_etf', None)
    ex = set(exclude)
    elig = (lambda t, d: t not in ex and base(t, d)) if ex else base
    kw = dict(kw)
    oset = kw.pop('only_set', None)
    if oset:
        import csv as _csv
        fn_ = {'ndx': 'ndx100.csv', 'sp_now': 'sp500.csv'}[oset]
        S_ = {r['symbol'] for r in _csv.DictReader(open(os.path.join(ROOT, 'data', fn_)))}
        _px = P['prices']
        elig = (lambda t, d, S_=S_: t in S_ and t not in G.get('LEV', ()) and t in _px)
    wdn = kw.pop('wdown', None)
    if wdn:
        # skip stocks in a weekly downtrend (they leave at the next rebalance and the next-ranked stock takes the slot):
        # how='pct': down over the last n sessions; 'down': weekly lower highs + lower lows (2-bar fractal, last two
        # labeled swings) for at least `min` weeks; 'lh2': the last two weekly swing highs were both lower highs
        cal_w, px_w = P['calendar'], P['prices']
        posw = {d_: i_ for i_, d_ in enumerate(cal_w)}
        _ew = elig
        wcache = {}

        def wk_series(t):
            weeks, cur = [], None
            for b in G['BARS'].get(t) or []:
                key_ = date.fromisoformat(b[0][:10]).isocalendar()[:2]
                if cur is None or key_ != cur:
                    weeks.append([b[0][:10], b[1], b[2], b[3], b[4]]); cur = key_
                else:
                    w = weeks[-1]; w[0] = b[0][:10]; w[2] = max(w[2], b[2]); w[3] = min(w[3], b[3]); w[4] = b[4]
            n = 2
            labeled, his, last = [], [], {'high': None, 'low': None}
            ds, st, run = [], [], 0
            for w in range(len(weeks)):
                i = w - n
                if i >= n:
                    win = weeks[i - n:i + n + 1]
                    h, l = weeks[i][2], weeks[i][3]
                    for typ, price, cond in (('high', h, h == max(x[2] for x in win)), ('low', l, l == min(x[3] for x in win))):
                        if not cond:
                            continue
                        prev = last[typ]
                        if prev is None or price == prev:
                            lab = None
                        elif typ == 'high':
                            lab = 'HH' if price > prev else 'LH'
                        else:
                            lab = 'HL' if price > prev else 'LL'
                        last[typ] = price
                        if lab:
                            labeled.append(lab)
                            if typ == 'high':
                                his.append(lab)
                rec = labeled[-2:]
                down = len(rec) == 2 and set(rec) <= {'LH', 'LL'}
                run = run + 1 if down else 0
                ds.append(weeks[w][0]); st.append((down, run, len(his) >= 2 and his[-1] == 'LH' and his[-2] == 'LH'))
            return ds, st
        G.setdefault('WD_N', [0, 0])

        def elig_wd(t, d_):
            if not _ew(t, d_):
                return False
            if wdn['how'] == 'pct':
                k_ = posw.get(d_)
                if k_ is None or k_ < wdn['n']:
                    return True
                p_ = px_w.get(t) or {}
                a_, b_ = p_.get(cal_w[k_ - wdn['n']]), p_.get(d_)
                return not (a_ and b_ and b_ < a_)
            if wdn['how'] == 'ddays':
                # share of down closes over the last n sessions; skip the stock when it exceeds th
                k_ = posw.get(d_)
                if k_ is None or k_ < wdn['n'] + 1:
                    return True
                p_ = px_w.get(t) or {}
                dn_, tot_ = 0, 0
                for i_ in range(k_ - wdn['n'] + 1, k_ + 1):
                    a_, b_ = p_.get(cal_w[i_ - 1]), p_.get(cal_w[i_])
                    if a_ and b_:
                        tot_ += 1; dn_ += b_ < a_
                return not (tot_ >= 20 and dn_ / tot_ > wdn['th'])
            if t not in wcache:
                wcache[t] = wk_series(t)
            ds, st = wcache[t]
            j = bisect_right(ds, d_) - 1
            if j < 0:
                return True
            down, run, lh2 = st[j]
            if wdn['how'] == 'lh2':
                return not lh2
            return not (down and run >= wdn.get('min', 1))
        elig = elig_wd
    fresh_ = kw.pop('fresh', None)
    monthly = kw.pop('monthly', False)
    accel = kw.pop('accel', None)
    boost_rank = kw.pop('boost_rank', None)
    sig = kw.pop('sig_exit', None)
    plan = kw.pop('plan', None)
    lx = kw.pop('lolo_exit', None)
    biweekly = kw.pop('biweekly', False)
    daily_rb = kw.pop('daily_rebal', False)
    every_n = kw.pop('every_n', None)
    offset = kw.pop('offset', 0)
    liq_w = kw.pop('liq_w', None)
    if liq_w:
        cal_l = P['calendar']
        cum = G['dvcum']
        pct_cache = {}

        def liq_pct(k):
            if k not in pct_cache:
                vals = {}
                for t, c in cum.items():
                    if k - 63 < 0 or k >= len(c):
                        continue
                    a_, b_ = c[k - 63], c[k]
                    if b_ > a_:
                        vals[t] = b_ - a_
                order = sorted(vals, key=vals.get)
                n_ = len(order) or 1
                pct_cache[k] = {t: (i + 1) / n_ for i, t in enumerate(order)}
            return pct_cache[k]

        def liq_key(t, k, sc):
            return -((1 - liq_w) * sc + liq_w * liq_pct(k).get(t, 0.0))
        kw['rank_key'] = liq_key
    bign = kw.pop('big', None)
    if bign:
        cumb = G['dvcum']
        calb = P['calendar']
        posb = {d_: i_ for i_, d_ in enumerate(calb)}
        bcache = {}

        def big_set(k_):
            if k_ not in bcache:
                vals = {}
                for t_, c_ in cumb.items():
                    if k_ < 63 or k_ >= len(c_):
                        continue
                    v_ = c_[k_] - c_[k_ - 63]
                    if v_ > 0:
                        vals[t_] = v_
                bcache[k_] = set(sorted(vals, key=lambda t_: -vals[t_])[:bign])
            return bcache[k_]
        _eb = elig

        def elig_big(t, d_):
            k_ = posb.get(d_)
            return _eb(t, d_) and k_ is not None and t in big_set(k_)
        elig = elig_big
    ind_mode = kw.pop('indconf', None)
    if ind_mode:
        import csv as _csv
        with open(os.path.join(ROOT, 'data', 'industries.csv')) as fh:
            ind_ = {r['symbol']: r['industry'] for r in _csv.DictReader(fh) if r.get('industry')}
        cal_i, px_i = P['calendar'], P['prices']
        members = {}
        for t_, g_ in ind_.items():
            if t_ in px_i:
                members.setdefault(g_, []).append(t_)
        icache = {}

        def ind_scores(k_):
            if k_ not in icache:
                d1, d0 = cal_i[k_ - 21], cal_i[k_ - 147]
                spy_ = px_i['SPY']
                sp_ = spy_[d1] / spy_[d0] - 1 if spy_.get(d1) and spy_.get(d0) else 0.0
                med = {}
                for g_, ts in members.items():
                    r_ = sorted(px_i[t_][d1] / px_i[t_][d0] - 1 for t_ in ts if px_i[t_].get(d1) and px_i[t_].get(d0))
                    if len(r_) >= 3:
                        med[g_] = r_[len(r_) // 2]
                order = sorted(med, key=lambda g_: -med[g_])
                icache[k_] = (med, {g_: i_ / max(1, len(order)) for i_, g_ in enumerate(order)}, sp_)
            return icache[k_]

        def ind_ok(t, k_):
            g_ = ind_.get(t)
            if g_ is None or k_ < 147:
                return True
            med, rk, sp_ = ind_scores(k_)
            if g_ not in med:
                return True
            return rk[g_] < 0.5 if ind_mode == 'top' else med[g_] > sp_
        kw['buy_when'] = ind_ok
    minvol = kw.pop('minvol', None)
    if minvol:
        cal_m, px_m = P['calendar'], P['prices']

        def vol_hi(t, k_):
            pts = [px_m[t].get(cal_m[j]) for j in range(max(0, k_ - 63), k_ + 1)]
            pts = [x for x in pts if x]
            if len(pts) < 40:
                return True
            r_ = [math.log(b / a) for a, b in zip(pts, pts[1:])]
            m_ = sum(r_) / len(r_)
            return (sum((x - m_) ** 2 for x in r_) / (len(r_) - 1)) ** 0.5 * math.sqrt(252) >= minvol
        kw['buy_when'] = vol_hi
    vc = kw.pop('volconf', None)
    if vc:
        cum_v = G['dvcum']

        def vol_ok(t, k_):
            c_ = cum_v.get(t)
            if c_ is None or k_ < 100 or k_ >= len(c_):
                return True                      # no volume data: allowed
            a20, a100 = (c_[k_] - c_[k_ - 20]) / 20, (c_[k_] - c_[k_ - 100]) / 100
            return a100 <= 0 or a20 / a100 >= vc
        kw['buy_when'] = vol_ok
    wk = kw.pop('weak', None)
    if wk:
        cal_w, spw = P['calendar'], P['prices']['SPY']
        arr_w, last_w = [], None
        for d_ in cal_w:
            last_w = spw.get(d_) or last_w
            arr_w.append(last_w)
        weak_ = [k_ >= 150 and all(arr_w[k_ - 149:k_ + 1]) and arr_w[k_] < sum(arr_w[k_ - 149:k_ + 1]) / 150
                 for k_ in range(len(arr_w))]
        pos_w = {d_: i_ for i_, d_ in enumerate(cal_w)}
        if wk.get('monthly'):
            from mtl.momentum import last_sessions_of_weeks as _lsw3
            me_ = set(month_ends(cal_w))
            kw['rebal_dates'] = {d_ for d_ in _lsw3(cal_w) if not weak_[pos_w[d_]]} | {d_ for d_ in me_ if weak_[pos_w[d_]]}
        if wk.get('keep'):
            kw['keep_rank'] = lambda k_, n_=wk['keep']: n_ if weak_[k_] else 10
        if wk.get('risk_adj'):
            kw['risk_adj'] = lambda k_: weak_[k_]
        px_w = P['prices']

        def _c(t, k_):
            return px_w[t].get(cal_w[k_])
        if wk.get('above200'):
            def ok200(t, k_):
                if not weak_[k_]:
                    return True
                p_ = _c(t, k_)
                w_ = [x for x in (_c(t, j) for j in range(max(0, k_ - 199), k_ + 1)) if x]
                return bool(p_ and len(w_) >= 150 and p_ > sum(w_) / len(w_))
            kw['buy_when'] = ok200
            if wk['above200'] == 'cash':
                kw['buy_max_rank'] = lambda k_: 5 if weak_[k_] else None
        if wk.get('offhigh'):
            th_ = wk['offhigh']

            def okhi(t, k_):
                if not weak_[k_]:
                    return True
                p_ = _c(t, k_)
                w_ = [x for x in (_c(t, j) for j in range(max(0, k_ - 251), k_ + 1)) if x]
                return bool(p_ and w_ and p_ >= max(w_) * (1 - th_))
            kw['buy_when'] = okhi
    regime = kw.pop('regime_ma', None)
    if regime:
        cal_r, spy_r = P['calendar'], P['prices']['SPY']
        up_r = {}
        for k_ in range(regime, len(cal_r)):
            w_ = [spy_r.get(cal_r[j]) for j in range(k_ - regime + 1, k_ + 1)]
            if all(w_):
                up_r[k_] = spy_r[cal_r[k_]] > sum(w_) / regime
        kw['blend'] = ('regime', lambda k: up_r.get(k, False))
    spike = kw.pop('skip_spike', None)
    if spike:
        cal_s, px_s = P['calendar'], P['prices']

        def no_spike(t, k):
            a_, b_ = px_s[t].get(cal_s[k - 5]) if k >= 5 else None, px_s[t].get(cal_s[k])
            return not (a_ and b_ and b_ / a_ - 1 >= spike)
        kw['buy_when'] = no_spike
    if lx:
        cal_ = P['calendar']
        kw['exit_when'] = lambda t, k: G['down'](t, cal_[k])
        kw['exit_daily'] = lx.get('daily', False)
        kw['cooldown'] = lx.get('cooldown', 5)
        if lx.get('buy_up'):
            kw['buy_when'] = lambda t, k: G['up'](t, cal_[k])
    xit = kw.pop('xit', None)
    if xit:
        X = G['XF']

        def hold_exit_x(t, k, e):
            a = X(t)
            if a is None:
                return False
            c, ma50, ma200, rsi, = a['c'], a['ma50'], a['ma200'], a['rsi']
            p_ = c[k]
            if p_ != p_:
                return False
            if xit.startswith('ext'):
                th = int(xit[3:]) / 100
                return ma50[k] == ma50[k] and p_ > ma50[k] * (1 + th)
            if xit == 'rsi85':
                return rsi[k] == rsi[k] and rsi[k] > 85
            if xit.startswith('accel'):
                parts = xit.split('_')
                m_ = float(parts[1]) if len(parts) > 1 else 1.0
                sh_ = int(parts[2]) if len(parts) > 2 else 21
                if k < 126:
                    return False
                r1 = p_ / c[k - sh_] - 1
                r5 = c[k - sh_] / c[k - 126] - 1
                return r1 > 0 and r5 > 0 and r1 > m_ * r5
            if xit.startswith('bt'):
                g_, tr_ = xit[2:].split('_')
                g_, tr_ = int(g_) / 100, int(tr_) / 100
                seg = c[e:k + 1]
                pk = _np.nanmax(seg) if len(seg) else _np.nan
                return pk == pk and pk >= c[e] * (1 + g_) and p_ <= pk * (1 - tr_)
            if xit == 'climax':
                if k < 252 or ma200[k] != ma200[k] or p_ < ma200[k] * 1.8:
                    return False
                r = c[k - 251:k + 1] / c[k - 252:k] - 1
                return _np.nanargmax(r) == len(r) - 1
            if xit == 'time252':
                return k - e >= 252
            if xit == 'lolo50':
                seg = c[e:k + 1]
                return _np.nanmax(seg) >= c[e] * 1.5 and G['down'](t, P['calendar'][k])
            return False
        kw['hold_exit'] = hold_exit_x
        xg = kw.pop('xgate', None)
        if xg:
            # the exit only counts within W sessions after a bad market: SPY 6-month return < 0, or SPY 20%+ below its 1-year high
            mode_, W_ = xg
            cal_g = P['calendar']
            spx = P['prices'].get('SPY') or G['D']['SPY']
            arr, last = [], None
            for d_ in cal_g:
                v_ = spx.get(d_)
                last = v_ if v_ else last
                arr.append(last)
            bad = []
            for k_ in range(len(arr)):
                if mode_ == 'spy6m':
                    bad.append(k_ >= 126 and arr[k_] and arr[k_ - 126] and arr[k_] < arr[k_ - 126])
                elif mode_.startswith('ma'):
                    n_ = int(mode_[2:])
                    seg_ = [x for x in arr[max(0, k_ - n_ + 1):k_ + 1] if x]
                    bad.append(k_ >= n_ and len(seg_) == n_ and arr[k_] < sum(seg_) / n_)
                else:
                    hi_ = max((x for x in arr[max(0, k_ - 251):k_ + 1] if x), default=None)
                    bad.append(bool(hi_ and arr[k_] and arr[k_] <= hi_ * (1 - int(mode_[2:]) / 100)))
            on_, lastbad = [], -10 ** 9
            for k_, b_ in enumerate(bad):
                lastbad = k_ if b_ else lastbad
                on_.append(k_ - lastbad <= W_)
            G['xgate_share'] = sum(on_) / len(on_)
            kw['hold_exit'] = lambda t, k, e, f_=hold_exit_x: on_[k] and f_(t, k, e)
    vx = kw.pop('vx', None)
    if vx:
        # extra exit on top of the plan's own: sell a holding after a big up move on heavy volume
        # (volume >= vol_k x its 50-day average); the slot goes to the next-best stock as usual
        if 'SVOL' not in G:
            _z = _np.load(os.path.join(SIDE_, 'stock_volume.npz'))
            _di = {d_: i_ for i_, d_ in enumerate(_z['dates'].tolist())}
            G['SVOL'] = ({t_: i_ for i_, t_ in enumerate(_z['tickers'].tolist())}, _z['vol'],
                         _np.array([_di.get(d_, -1) for d_ in P['calendar']]))
        cal_v, vcache = P['calendar'], {}
        XV = G['XF']

        def varr(t):
            if t not in vcache:
                ti_, M_, ci_ = G['SVOL']
                if t in ti_:
                    v_ = _np.where(ci_ >= 0, M_[ti_[t]][_np.maximum(ci_, 0)], _np.nan).astype(float)
                else:
                    v_ = _np.full(len(cal_v), _np.nan)
                avg = _np.full(len(v_), _np.nan)
                ok_ = ~_np.isnan(v_)
                cs = _np.concatenate([[0.0], _np.cumsum(_np.where(ok_, v_, 0.0))])
                cn = _np.concatenate([[0], _np.cumsum(ok_)])
                for k_ in range(50, len(v_)):
                    n_ = cn[k_] - cn[k_ - 50]
                    if n_ >= 40:
                        avg[k_] = (cs[k_] - cs[k_ - 50]) / n_
                vcache[t] = (v_, avg)
            return vcache[t]

        def vx_exit(t, k, e):
            dl_ = vx.get('delay', 0)
            if dl_:
                # sell `delay` sessions after the surge day, if the surge happened while held
                return k - dl_ >= e and vx_event(t, k - dl_, e)
            return vx_event(t, k, e)

        def vx_event(t, k, e):
            a = XV(t)
            if a is None or k < 60:
                return False
            c = a['c']
            p_, p1 = c[k], c[k - 1]
            if p_ != p_ or p1 != p1 or not p1:
                return False
            v_, avg = varr(t)
            if not (v_[k] == v_[k] and avg[k] == avg[k] and avg[k] > 0 and v_[k] >= vx['vol_k'] * avg[k]):
                return False
            day = p_ / p1 - 1
            m_ = vx['move']
            if m_ == 'day':
                return day >= vx['th']
            if m_ == 'week':
                p5 = c[k - 5]
                return day > 0 and p5 == p5 and p5 > 0 and p_ / p5 - 1 >= vx['th']
            if m_ == 'entry':
                return day > 0 and c[e] == c[e] and c[e] > 0 and p_ / c[e] - 1 >= vx['th']
            return False
        prev_x = kw.get('hold_exit')
        kw['hold_exit'] = (lambda t, k, e, f_=prev_x: f_(t, k, e) or vx_exit(t, k, e)) if prev_x else vx_exit
    if kw.pop('rsix', False):
        cal_x, px_x = P['calendar'], P['prices']
        from mtl.backtest import rsi_series as _rs2
        rcache = {}

        def rarr(t):
            if t not in rcache:
                arr = [px_x[t].get(d) for d in cal_x]
                last = None
                for i_, v in enumerate(arr):          # carry the last close over gaps
                    if v is None:
                        arr[i_] = last
                    else:
                        last = v
                first = next((i_ for i_, v in enumerate(arr) if v), None)
                out = [None] * len(arr)
                if first is not None:
                    rs = _rs2(arr[first:])
                    out[first:] = rs
                rcache[t] = out
            return rcache[t]

        def hold_exit(t, k, e):
            r = rarr(t)
            if r[k] is None or r[k] >= 30:
                return False
            return any(x is not None and x > 50 for x in r[e:k])
        kw['hold_exit'] = hold_exit
    zmode = kw.pop('zmode', None)
    if zmode:
        Z = G['Z']
        from bisect import bisect_right as _br2

        def zorder(k, rows):
            j = _br2(Z['eidx'], k) - 1            # last week end at or before day k
            if j < 26:
                return rows
            if zmode == 'top15':
                top = [r for r in rows if r[2]][:15]
                ids = [r[0] for r in top]
                tot = {t: 0.0 for t in ids}
                for w in range(j - 25, j + 1):
                    zz = {t: Z['z'][t][w] for t in ids if Z['z'].get(t) is not None and Z['z'][t][w] == Z['z'][t][w]}
                    order = sorted(zz, key=lambda t: -zz[t])
                    for i_, t in enumerate(order):
                        tot[t] += i_ + 1
                    for t in ids:
                        if t not in zz:
                            tot[t] += len(ids)
                top = sorted(top, key=lambda r: tot[r[0]])
                return top + [r for r in rows if r[0] not in set(ids)]
            key = Z['rsum'] if zmode == 'rankall' else Z['zsum']
            sc = {r[0]: key[r[0]][j] for r in rows if key.get(r[0]) is not None and key[r[0]][j] == key[r[0]][j]}
            good = [r for r in rows if r[0] in sc]
            good.sort(key=lambda r: sc[r[0]] if zmode == 'rankall' else -sc[r[0]])
            return good + [r for r in rows if r[0] not in sc]
        kw['reorder'] = zorder
    fac = kw.pop('fac', None)
    if fac:
        # selection factor: re-sort the momentum list by the average of its momentum rank and a second
        # factor's rank (weight fac['w'] on the factor), among the top 60 by momentum
        fname, fw = fac['f'], fac.get('w', 0.5)
        cal_f, px_f, carr = P['calendar'], P['prices'], {}

        def closes(t):
            if t not in carr:
                a_, last = _np.full(len(cal_f), _np.nan), _np.nan
                for i_, d_ in enumerate(cal_f):
                    v_ = px_f[t].get(d_)
                    if v_:
                        last = v_
                    a_[i_] = last
                carr[t] = a_
            return carr[t]
        if fname in ('upvol', 'vsurge') and 'SVOL' not in G:
            _z = _np.load(os.path.join(SIDE_, 'stock_volume.npz'))
            _di = {d_: i_ for i_, d_ in enumerate(_z['dates'].tolist())}
            G['SVOL'] = ({t_: i_ for i_, t_ in enumerate(_z['tickers'].tolist())}, _z['vol'],
                         _np.array([_di.get(d_, -1) for d_ in P['calendar']]))

        def fval(t, k, sc):
            c_ = closes(t)
            if fname == 'hi52':
                w_ = c_[max(0, k - 251):k + 1]
                return c_[k] / _np.nanmax(w_) if _np.isfinite(c_[k]) else None
            seg_ = c_[max(1, k - 126):k - 20]
            r_ = seg_[1:] / seg_[:-1] - 1
            r_ = r_[_np.isfinite(r_)]
            if len(r_) < 60:
                return None
            if fname == 'smooth':
                return float((r_ > 0).mean())
            if fname == 'radj':
                sd_ = r_.std()
                return sc / sd_ if sd_ > 0 else None
            if fname == 'blend':
                a3, a12, b_ = c_[k - 63], c_[k - 252] if k >= 252 else _np.nan, c_[k - 21]
                if not (_np.isfinite(a3) and _np.isfinite(a12) and _np.isfinite(b_)):
                    return None
                return (b_ / a3 - 1) + (b_ / a12 - 1) / 2
            if fname == 'r1m':
                return float(c_[k] / c_[k - 21] - 1) if _np.isfinite(c_[k - 21]) and _np.isfinite(c_[k]) else None
            if fname == 'hvol':   # higher recent volatility ranks better
                seg2 = c_[max(1, k - 63):k + 1]; r2 = seg2[1:] / seg2[:-1] - 1; r2 = r2[_np.isfinite(r2)]
                return float(r2.std()) if len(r2) > 40 else None
            if fname == 'ma200':  # further above the 200-day average ranks better
                w2 = c_[max(0, k - 199):k + 1]; w2 = w2[_np.isfinite(w2)]
                return float(c_[k] / w2.mean() - 1) if len(w2) > 180 and _np.isfinite(c_[k]) else None
            if fname == 'vsurge':  # 20-day volume vs 120-day volume
                ti_, M_, ci_ = G['SVOL']
                if t not in ti_:
                    return None
                idx_v = ci_[k - 119:k + 1]
                if (idx_v < 0).any():
                    return None
                v_ = M_[ti_[t]][idx_v].astype(float)
                return float(v_[-20:].mean() / v_.mean()) if v_.mean() > 0 else None
            if fname == 'upvol':
                ti_, M_, ci_ = G['SVOL']
                if t not in ti_:
                    return None
                idx_v = ci_[k - 63:k + 1]
                if (idx_v < 0).any():
                    return None
                v_ = M_[ti_[t]][idx_v].astype(float)
                cc = c_[k - 64:k + 1]
                rr = cc[1:] / cc[:-1] - 1
                up, dn = v_[rr > 0].sum(), v_[rr < 0].sum()
                return up / dn if dn > 0 else None
            return None

        def fac_order(k, rows):
            top = [r for r in rows if r[2]][:60]
            if len(top) < 6:
                return rows
            vals = {r[0]: fval(r[0], k, r[1]) for r in top}
            ok_ = [r for r in top if vals[r[0]] is not None and vals[r[0]] == vals[r[0]]]
            n_ = len(ok_)
            mrank = {r[0]: i_ for i_, r in enumerate(ok_)}
            frank = {t_: i_ for i_, t_ in enumerate(sorted([r[0] for r in ok_], key=lambda t_: -vals[t_]))}
            ok_.sort(key=lambda r: (1 - fw) * mrank[r[0]] + fw * frank[r[0]])
            ids = {r[0] for r in ok_}
            return ok_ + [r for r in rows if r[0] not in ids]
        kw['reorder'] = fac_order
    rise = kw.pop('rise', None)
    if rise:
        # buy filter: a new buy must still be rising (up over the last month and/or above its 50-day average)
        cal_r2, px_r2 = P['calendar'], P['prices']

        def still_rising(t, k):
            p_ = px_r2[t]; c0, c21 = p_.get(cal_r2[k]), p_.get(cal_r2[k - 21]) if k >= 21 else None
            if not (c0 and c21):
                return False
            ok = True
            if rise.get('r1m') is not None:
                ok = ok and c0 / c21 - 1 > rise['r1m']
            if rise.get('ma50'):
                w_ = [p_.get(cal_r2[j]) for j in range(k - 49, k + 1)]; w_ = [x for x in w_ if x]
                ok = ok and len(w_) > 40 and c0 > sum(w_) / len(w_)
            return ok
        kw['buy_when'] = still_rising
    ltk = kw.pop('ltk', None)
    if ltk:
        # tax: keep a winner held `from_`+ sessions until it has been held a year (long-term rate), if it
        # still ranks within `rank`; 'lose': sell a losing holding once it drops out of the top `lose`
        px_l, cal_l = P['prices'], P['calendar']

        def keep_fn(t, k, e, rank):
            p0, p1 = px_l[t].get(cal_l[e]), px_l[t].get(cal_l[k])
            if not (p0 and p1):
                return None
            held = k - e
            if ltk.get('from') and p1 > p0 and ltk['from'] <= held < 253 and rank < ltk.get('rank', 30):
                return True
            if ltk.get('lose') and p1 < p0 and rank >= ltk['lose']:
                return False
            return None
        kw['keep_fn'] = keep_fn
    rsum = kw.pop('rsum', None)
    if rsum:
        from mtl.momentum import last_sessions_of_weeks as _lw
        cal_r, px_r = P['calendar'], P['prices']
        ends_all = _lw(cal_r)
        pos_r = {d: i for i, d in enumerate(cal_r)}
        ends_idx = [pos_r[d] for d in ends_all]
        from bisect import bisect_right as _br

        def reorder(k, rows):
            top = [r for r in rows if r[2]][:10]
            if len(top) < 2:
                return rows
            j = _br(ends_idx, k)          # week ends up to and including day k
            ends = [cal_r[i] for i in ends_idx[max(0, j - rsum - 1):j]]
            if ends and ends[-1] != cal_r[k]:
                ends = (ends + [cal_r[k]])[-(rsum + 1):]
            sums = {r[0]: 0 for r in top}
            for a, b in zip(ends, ends[1:]):
                ch = {}
                for r in top:
                    pa, pb = px_r[r[0]].get(a), px_r[r[0]].get(b)
                    if pa and pb:
                        ch[r[0]] = pb / pa - 1
                order = sorted(ch, key=lambda t: -ch[t])
                for i, t in enumerate(order):
                    sums[t] += i + 1
                for t in sums:
                    if t not in ch:
                        sums[t] += len(top)      # no price that week: count as last
            ids = {r[0] for r in top}
            top = sorted(top, key=lambda r: sums[r[0]])
            return top + [r for r in rows if r[0] not in ids]
        kw['reorder'] = reorder
    dipf = kw.pop('dipf', None)
    if dipf:
        cal_d, px_d = P['calendar'], P['prices']

        def is_dip(t, k):
            if k < 126:
                return False
            px = px_d[t]
            now = px.get(cal_d[k])
            pts = [px.get(cal_d[j]) for j in range(k - 125, k + 1)]
            pts = [x for x in pts if x]
            return bool(now and pts and now <= max(pts) * (1 - dipf))
        kw['dip'] = is_dip
    sf = kw.pop('sfilt', None)
    sfw = kw.pop('sf_which', 'either')
    if sf:
        cal_ = P['calendar']

        def sf_ok(t, k):
            h, r_ = G['hl'](t, cal_[k]), G['rsi'](t, cal_[k])
            if sfw == 'hl':
                return h
            if sfw == 'rsi':
                return r_ is not None and r_ > 60
            return h or (r_ is not None and r_ > 60)
        if sf == 'all':
            kw['exit_when'] = lambda t, k: not sf_ok(t, k)
            kw['exit_daily'] = False
            kw['cooldown'] = 0
        else:
            kw['buy_when'] = sf_ok
            if sf in ('cash', 'wait'):
                kw['buy_max_rank'] = kw.get('top_n', 5)
            if sf == 'wait':
                kw['wait_buy'] = True
    pf_ = kw.pop('pf', None)
    nopf_ = None
    lr_pf = (plan or {}).get('legrot') or {}
    if pf_ and pf_.get('cash') and (lr_pf.get('side') or {}).get('metric') == 'whip' and lr_pf.get('whip_src', 'nopf') == 'nopf':
        # shadow count for the whipsaw half-switch: keep the buy rules from before the filter for a second run
        nopf_ = dict(buy_when=kw.get('buy_when'), buy_max_rank=kw.get('buy_max_rank'))
    if pf_:
        # pick filters on new buys (a stock already held is kept as usual; the next-ranked stock is bought instead).
        # Each kind flags a stock at the decision close k:
        #   fade_v  volume dried up: average volume of the last 21 sessions < th_v x the 105 sessions before
        #   fade_s  swings shrinking: daily volatility of the last 21 sessions < th_s x its normal (the 189 sessions
        #           before the last 63)
        #   fade_vs both of those;  calm  63-session volatility under th_c a year
        #   wdown   weekly chart in a downtrend: the last two confirmed weekly swing highs and lows both lower
        #           (swings 2 weeks either side, confirmed once the second week after closes)
        # need='any' skips a stock flagged by any listed kind.
        from bisect import bisect_right as _brp
        cal_p = P['calendar']
        if 'SVOL' not in G:
            _z = _np.load(os.path.join(SIDE_, 'stock_volume.npz'))
            _di = {d_: i_ for i_, d_ in enumerate(_z['dates'].tolist())}
            G['SVOL'] = ({t_: i_ for i_, t_ in enumerate(_z['tickers'].tolist())}, _z['vol'],
                         _np.array([_di.get(d_, -1) for d_ in cal_p]))
        XP = G['XF']
        th_v, th_s, th_c = pf_.get('th_v', 0.78), pf_.get('th_s', 0.64), pf_.get('th_c', 0.30)
        vc_p, wc_p = {}, {}

        def pf_vol(t):
            if t not in vc_p:
                ti_, M_, ci_ = G['SVOL']
                vc_p[t] = _np.where(ci_ >= 0, M_[ti_[t]][_np.maximum(ci_, 0)], _np.nan).astype(float) if t in ti_ else None
            return vc_p[t]

        def f_fade_v(t, k):
            v_ = pf_vol(t)
            if v_ is None or k < 130:
                return False
            a_, b_ = v_[k - 20:k + 1], v_[k - 125:k - 20]
            a_, b_ = a_[~_np.isnan(a_)], b_[~_np.isnan(b_)]
            if len(a_) < 15 or len(b_) < 70 or b_.mean() <= 0:
                return False
            return a_.mean() / b_.mean() < th_v

        def logret(t, k, n):
            a = XP(t)
            if a is None or k < n + 1:
                return None
            c = a['c'][k - n:k + 1]
            if _np.isnan(c).any() or (c <= 0).any():
                return None
            return _np.diff(_np.log(c))

        def f_fade_s(t, k):
            r_ = logret(t, k, 252)
            if r_ is None:
                return False
            nrm = r_[:189].std(ddof=1)
            return bool(nrm > 0 and r_[-21:].std(ddof=1) / nrm < th_s)

        def f_calm(t, k):
            r_ = logret(t, k, 63)
            return r_ is not None and r_.std(ddof=1) * math.sqrt(252) < th_c

        def wk_swings(t):
            if t not in wc_p:
                rows, cur = [], None
                for b in G['BARS'].get(t) or []:
                    key_ = date.fromisoformat(b[0][:10]).isocalendar()[:2]
                    if cur is None or key_ != cur:
                        rows.append([b[0][:10], b[2], b[3]]); cur = key_
                    else:
                        rows[-1][0] = b[0][:10]; rows[-1][1] = max(rows[-1][1], b[2]); rows[-1][2] = min(rows[-1][2], b[3])
                sw = []      # (confirmed on, 'h'/'l', price)
                for i in range(2, len(rows) - 2):
                    win = rows[i - 2:i + 3]
                    if rows[i][1] == max(r[1] for r in win):
                        sw.append((rows[i + 2][0], 'h', rows[i][1]))
                    if rows[i][2] == min(r[2] for r in win):
                        sw.append((rows[i + 2][0], 'l', rows[i][2]))
                sw.sort(key=lambda x: x[0])
                wc_p[t] = (sw, [x[0] for x in sw])
            return wc_p[t]

        def f_wdown(t, k):
            sw, cd = wk_swings(t)
            n_ = _brp(cd, cal_p[k])
            hs, ls = [], []
            for x in reversed(sw[:n_]):
                (hs if x[1] == 'h' else ls).append(x[2])
                if len(hs) >= 2 and len(ls) >= 2:
                    break
            return len(hs) >= 2 and len(ls) >= 2 and hs[0] < hs[1] and ls[0] < ls[1]

        PFK = dict(fade_v=f_fade_v, fade_s=f_fade_s, fade_vs=lambda t, k: f_fade_v(t, k) and f_fade_s(t, k),
                   calm=f_calm, wdown=f_wdown)
        fns_ = [PFK[x] for x in pf_['kinds']]

        def pf_ok(t, k):
            return not any(f_(t, k) for f_ in fns_)
        if pf_.get('cash'):
            # no replacement: only top-`top_n` names may be bought, so a skipped one leaves its slot in cash until it
            # drops out of the top `top_n` (or stops being flagged)
            kw.setdefault('buy_max_rank', kw.get('top_n', 5))
        prev_pf = kw.get('buy_when')
        kw['buy_when'] = (lambda t, k: prev_pf(t, k) and pf_ok(t, k)) if prev_pf else pf_ok
    fzr_ = kw.pop('fzr', None)
    fz_sets = None
    if fzr_ is not None:
        # the two-scale buy rules (the live repo's mtl/fractal.py, default since Oct 24, 2026): no new buys in a buy
        # freeze unless the green light is on (which also sets the fading filter aside), and never a stock whose weekly
        # and daily swing highs are both falling. Applied after the fading filter; the whipsaw's shadow list (nopf_) keeps
        # the buy rules from before both, as the live scanner's.
        cal_z = P['calendar']
        parts_ = fzr_.get('parts', 'fgs')   # f buy freeze, g green light, s stock lower highs (for checks of one part)
        fz_sets = fz_windows(G['SPYB'], cal_z, R.START, **{k_: v_ for k_, v_ in fzr_.items() if k_ in ('near', 'days', 'gl_near', 'gl_days')})
        fz_sets = (fz_sets[0] if 'f' in parts_ else set(), fz_sets[1] if 'g' in parts_ else set())
        frz_, grn_ = fz_sets
        RS_ = _FzReader(G['BARS'])

        def lowh_(t, d_):
            if 's' not in parts_ or t not in RS_.bars:
                return False
            w_ = RS_.two(t, d_, 'w', 'high')
            if not (len(w_) == 2 and w_[1] < w_[0]):
                return False
            h_ = RS_.two(t, d_, 'd', 'high')
            return len(h_) == 2 and h_[1] < h_[0]
        prev_fz = kw.get('buy_when')
        if fzr_.get('freeze_wins'):   # precedence test: a buy freeze also holds against the green light
            kw['buy_when'] = lambda t, k: k not in frz_ and (k in grn_ or (prev_fz(t, k) if prev_fz else True)) \
                and not lowh_(t, cal_z[min(k, len(cal_z) - 1)])
        else:
            kw['buy_when'] = lambda t, k: (k in grn_ or ((prev_fz(t, k) if prev_fz else True) and k not in frz_)) \
                and not lowh_(t, cal_z[min(k, len(cal_z) - 1)])
    hhl = kw.pop('hhline', None)
    if hhl:
        # don't buy a stock sitting at (or above) a rising line drawn through its last m swing highs when that line
        # fits well (R2 >= r2): it is stretched to the top of its channel; the next-ranked stock is bought instead.
        # Swing highs are 2-bar fractals on weekly (tf='w') or daily bars, used only once confirmed (two bars later).
        import math as _m
        from bisect import bisect_right as _br
        cal_h = P['calendar']; pos_h = {d_: i_ for i_, d_ in enumerate(cal_h)}
        hcache = {}

        def hh_swings(t):
            bars = G['BARS'].get(t) or []
            if hhl.get('tf', 'w') == 'w':
                rows, cur = [], None
                for b in bars:
                    key_ = date.fromisoformat(b[0][:10]).isocalendar()[:2]
                    if cur is None or key_ != cur:
                        rows.append([b[0][:10], b[2]]); cur = key_
                    else:
                        rows[-1][0] = b[0][:10]; rows[-1][1] = max(rows[-1][1], b[2])
            else:
                rows = [[b[0][:10], b[2]] for b in bars]
            sw = []      # (confirmed on date, bar index, high)
            for i in range(2, len(rows) - 2):
                h = rows[i][1]
                if h and h == max(r[1] for r in rows[i - 2:i + 3]):
                    sw.append((rows[i + 2][0], i, h))
            ends = [r[0] for r in rows]
            return sw, [x[0] for x in sw], ends
        def stretched_hh(t, k):
            d_ = cal_h[k]
            if t not in hcache:
                hcache[t] = hh_swings(t)
            sw, cds, ends = hcache[t]
            j = _br(cds, d_)
            m_ = hhl['m']
            if j < m_:
                return False
            pts = sw[j - m_:j]
            if any(pts[i_][2] <= pts[i_ - 1][2] for i_ in range(1, m_)):
                return False          # not a chain of higher highs
            xs = [p_[1] for p_ in pts]; ys = [_m.log(p_[2]) for p_ in pts]
            mx, my = sum(xs) / m_, sum(ys) / m_
            sxx = sum((x - mx) ** 2 for x in xs)
            if not sxx:
                return False
            b_ = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx; a_ = my - b_ * mx
            sst = sum((y - my) ** 2 for y in ys)
            r2 = 1 - sum((y - a_ - b_ * x) ** 2 for x, y in zip(xs, ys)) / sst if sst else 0
            if b_ <= 0 or r2 < hhl['r2']:
                return False
            xi = _br(ends, d_) if hhl.get('tf', 'w') == 'w' else _br(ends, d_) - 1
            line = _m.exp(a_ + b_ * xi)
            c_ = (P['prices'].get(t) or {}).get(d_)
            return bool(c_) and c_ >= line * (1 - hhl['tol'])
        G.setdefault('HHN', [0, 0])
        def hh_ok(t, k):
            bad = stretched_hh(t, k)
            G['HHN'][0] += 1; G['HHN'][1] += bad
            return not bad
        prev_bw = kw.get('buy_when')
        kw['buy_when'] = (lambda t, k: prev_bw(t, k) and hh_ok(t, k)) if prev_bw else hh_ok
    hhn = kw.pop('hhnow', None)
    if hhn:
        # today's close as the newest point: a stock is stretched when its close is above its last confirmed swing
        # high and the line through its last m confirmed higher highs plus today's close fits with R2 >= r2.
        # sell=False: don't buy it (next-ranked instead); sell=True: also sell it when held (checked every session).
        import math as _m
        from bisect import bisect_right as _br, bisect_left as _bl
        cal_n = P['calendar']; ncache = {}

        def hn_swings(t):
            bars = G['BARS'].get(t) or []
            if hhn.get('tf', 'd') == 'w':
                rows, cur = [], None
                for b in bars:
                    key_ = date.fromisoformat(b[0][:10]).isocalendar()[:2]
                    if cur is None or key_ != cur:
                        rows.append([b[0][:10], b[2]]); cur = key_
                    else:
                        rows[-1][0] = b[0][:10]; rows[-1][1] = max(rows[-1][1], b[2])
            else:
                rows = [[b[0][:10], b[2]] for b in bars]
            sw = []
            for i in range(2, len(rows) - 2):
                h = rows[i][1]
                if h and h == max(r[1] for r in rows[i - 2:i + 3]):
                    sw.append((rows[i + 2][0], i, h))
            return sw, [x[0] for x in sw], [r[0] for r in rows]

        def stretched_now(t, k):
            d_ = cal_n[k]
            if t not in ncache:
                ncache[t] = hn_swings(t)
            sw, cds, ends = ncache[t]
            j = _br(cds, d_); m_ = hhn['m']
            if j < m_:
                return False
            pts = sw[j - m_:j]
            if any(pts[i_][2] <= pts[i_ - 1][2] for i_ in range(1, m_)):
                return False
            c_ = (P['prices'].get(t) or {}).get(d_)
            if not c_ or c_ <= pts[-1][2]:
                return False          # not a new higher high today
            xi = _bl(ends, d_)
            if xi <= pts[-1][1]:
                return False
            xs = [p_[1] for p_ in pts] + [xi]; ys = [_m.log(p_[2]) for p_ in pts] + [_m.log(c_)]
            n_ = len(xs); mx, my = sum(xs) / n_, sum(ys) / n_
            sxx = sum((x - mx) ** 2 for x in xs)
            b_ = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx; a_ = my - b_ * mx
            sst = sum((y - my) ** 2 for y in ys)
            r2 = 1 - sum((y - a_ - b_ * x) ** 2 for x, y in zip(xs, ys)) / sst if sst else 0
            return b_ > 0 and r2 >= hhn['r2']
        if hhn.get('sell'):
            prev_ew = kw.get('exit_when')
            kw['exit_when'] = (lambda t, k: prev_ew(t, k) or stretched_now(t, k)) if prev_ew else stretched_now
        else:
            prev_bw2 = kw.get('buy_when')
            kw['buy_when'] = (lambda t, k: prev_bw2(t, k) and not stretched_now(t, k)) if prev_bw2 else (lambda t, k: not stretched_now(t, k))
    sxc = kw.pop('sectch', None)
    if sxc:
        # don't buy (or, with sell=True, also sell) a stock while its sector ETF is in a falling channel: the last
        # confirmed swing high was a lower high and (how='both') the last confirmed swing low a lower low.
        # Semiconductor stocks use SMH; others their SPDR sector ETF (IYR before XLRE, VOX before XLC).
        # Labels exist only for today's S&P 500 members; other stocks are not checked.
        import csv as _csv2
        from bisect import bisect_right as _br3
        E_ = json.load(open(os.path.join(ROOT, 'data', 'sector_etf.json')))
        sec_ = {r['symbol']: r['industry'] for r in _csv2.DictReader(open(os.path.join(ROOT, 'data', 'sectors.csv')))}
        ind_ = {r['symbol']: r['industry'] for r in _csv2.DictReader(open(os.path.join(ROOT, 'data', 'industries.csv')))}
        SEC_ETF = {'Information Technology': 'XLK', 'Technology': 'XLK', 'Financials': 'XLF', 'Energy': 'XLE', 'Health Care': 'XLV',
                   'Industrials': 'XLI', 'Consumer Discretionary': 'XLY', 'Consumer Staples': 'XLP', 'Utilities': 'XLU', 'Materials': 'XLB'}

        def etf_for(t, d_):
            if ind_.get(t) in ('Semiconductors', 'Semiconductor Materials & Equipment'):
                return 'SMH'
            s_ = sec_.get(t)
            if s_ == 'Real Estate':
                return 'XLRE' if d_ >= '2015-10-08' else 'IYR'
            if s_ == 'Communication Services':
                return 'XLC' if d_ >= '2018-06-19' else 'VOX'
            return SEC_ETF.get(s_)

        def channel_states(bars):
            if sxc.get('tf', 'd') == 'w':
                rows, cur = [], None
                for b in bars:
                    key_ = date.fromisoformat(b[0]).isocalendar()[:2]
                    if cur is None or key_ != cur:
                        rows.append([b[0], b[2], b[3]]); cur = key_
                    else:
                        rows[-1][0] = b[0]; rows[-1][1] = max(rows[-1][1], b[2]); rows[-1][2] = min(rows[-1][2], b[3])
            else:
                rows = [[b[0], b[2], b[3]] for b in bars]
            lastp = {'h': None, 'l': None}; lab = {'h': None, 'l': None}; out = []
            for i in range(2, len(rows) - 2):
                win = rows[i - 2:i + 3]; ch = False
                if rows[i][1] == max(r[1] for r in win):
                    if lastp['h'] is not None and rows[i][1] != lastp['h']:
                        lab['h'] = 'LH' if rows[i][1] < lastp['h'] else 'HH'; ch = True
                    lastp['h'] = rows[i][1]
                if rows[i][2] == min(r[2] for r in win):
                    if lastp['l'] is not None and rows[i][2] != lastp['l']:
                        lab['l'] = 'LL' if rows[i][2] < lastp['l'] else 'HL'; ch = True
                    lastp['l'] = rows[i][2]
                if ch:
                    down = lab['h'] == 'LH' and (sxc.get('how', 'both') == 'lh' or lab['l'] == 'LL')
                    out.append((rows[i + 2][0], down))
            return [x[0] for x in out], [x[1] for x in out]
        CH_ = {e_: channel_states(bs) for e_, bs in E_.items()}
        cal_s = P['calendar']
        G.setdefault('SXN', [0, 0])

        def sect_down(t, k):
            d_ = cal_s[k]; e_ = etf_for(t, d_)
            if not e_ or e_ not in CH_:
                return False
            ds_, st_ = CH_[e_]
            j = _br3(ds_, d_) - 1
            return j >= 0 and st_[j]
        if sxc.get('sell'):
            prev_ew3 = kw.get('exit_when')
            kw['exit_when'] = (lambda t, k: prev_ew3(t, k) or sect_down(t, k)) if prev_ew3 else sect_down
        else:
            prev_bw3 = kw.get('buy_when')
            kw['buy_when'] = (lambda t, k: prev_bw3(t, k) and not sect_down(t, k)) if prev_bw3 else (lambda t, k: not sect_down(t, k))
    rtp = kw.pop('rtop', None)
    if rtp:
        # rounded top: don't buy (sell=True: also sell) a stock while its own price ('stock') or its sector
        # ETF ('sector'; SMH for chip stocks) shows a rounded top over the last n sessions
        cal_t = P['calendar']; px_t = P['prices']; rcache = {}
        if rtp.get('on', 'stock') == 'sector':
            import csv as _csv4
            E4 = json.load(open(os.path.join(ROOT, 'data', 'sector_etf.json')))
            sec4 = {r['symbol']: r['industry'] for r in _csv4.DictReader(open(os.path.join(ROOT, 'data', 'sectors.csv')))}
            ind4 = {r['symbol']: r['industry'] for r in _csv4.DictReader(open(os.path.join(ROOT, 'data', 'industries.csv')))}
            SE4 = {'Information Technology': 'XLK', 'Technology': 'XLK', 'Financials': 'XLF', 'Energy': 'XLE', 'Health Care': 'XLV',
                   'Industrials': 'XLI', 'Consumer Discretionary': 'XLY', 'Consumer Staples': 'XLP', 'Utilities': 'XLU', 'Materials': 'XLB'}
            EF4 = {}
            for e_, bs_ in E4.items():
                ds_ = [b_[0] for b_ in bs_]; cs_ = [b_[4] for b_ in bs_]; fl_ = {}
                for i_ in range(rtp['n'], len(ds_) + 1):
                    fl_[ds_[i_ - 1]] = rtop_at(cs_[i_ - rtp['n']:i_], rtp['n'], rtp['r2'], rtp['mode'])
                EF4[e_] = (ds_, fl_)

            def etf4(t, d_):
                if ind4.get(t) in ('Semiconductors', 'Semiconductor Materials & Equipment'):
                    return 'SMH'
                s_ = sec4.get(t)
                if s_ == 'Real Estate':
                    return 'XLRE' if d_ >= '2015-10-08' else 'IYR'
                if s_ == 'Communication Services':
                    return 'XLC' if d_ >= '2018-06-19' else 'VOX'
                return SE4.get(s_)

            def topped(t, k):
                d_ = cal_t[k]; e_ = etf4(t, d_)
                if not e_ or e_ not in EF4:
                    return False
                ds_, fl_ = EF4[e_]
                j_ = bisect_right(ds_, d_) - 1
                return j_ >= 0 and fl_.get(ds_[j_], False)
        else:
            def topped(t, k):
                key_ = (t, k)
                if key_ not in rcache:
                    p_ = px_t.get(t) or {}
                    cs_ = [p_.get(cal_t[i_]) for i_ in range(max(0, k - rtp['n'] + 1), k + 1)]
                    rcache[key_] = rtop_at(cs_, rtp['n'], rtp['r2'], rtp['mode'])
                return rcache[key_]
        if rtp.get('sell'):
            prev_ew5 = kw.get('exit_when')
            kw['exit_when'] = (lambda t, k: prev_ew5(t, k) or topped(t, k)) if prev_ew5 else topped
        else:
            prev_bw5 = kw.get('buy_when')
            kw['buy_when'] = (lambda t, k: prev_bw5(t, k) and not topped(t, k)) if prev_bw5 else (lambda t, k: not topped(t, k))
    rwk = kw.pop('rsiweak', None)
    if rwk:
        # a stock whose own 14-day RSI is below th: don't buy it (sell=True: also sell it when held, checked
        # daily); macro=True: only while the 55/45 dollar-up / gold-and-bonds-down signal is on
        MS6 = json.load(open(os.path.join(ROOT, 'data', 'massell_55_45.json'))) if rwk.get('macro') else None
        cal_6 = P['calendar']

        def weak6(t, k):
            d_ = cal_6[k]
            if MS6 is not None and not MS6.get(d_, False):
                return False
            r_ = G['rsi'](t, d_)
            return r_ is not None and r_ < rwk['th']
        if rwk.get('sell'):
            prev_ew6 = kw.get('exit_when')
            kw['exit_when'] = (lambda t, k: prev_ew6(t, k) or weak6(t, k)) if prev_ew6 else weak6
        else:
            prev_bw6 = kw.get('buy_when')
            kw['buy_when'] = (lambda t, k: prev_bw6(t, k) and not weak6(t, k)) if prev_bw6 else (lambda t, k: not weak6(t, k))
    chb = kw.pop('chanbrk', None)
    if chb:
        # channel break: the stock ('stock') or its sector ETF ('sector'; SMH for chip stocks) closed below the lower band
        # of its rising regression channel on `confirm` sessions in a row; don't buy it (sell=True: also sell it)
        cal_c = P['calendar']; px_c = P['prices']; ccache = {}
        n_, k_, lag_, cf_ = chb['n'], chb.get('k', 2.0), chb.get('lag', 5), chb.get('confirm', 2)

        def brk_series(cs_):
            return all(chan_break_at(cs_[len(cs_) - (n_ + lag_ + 1) - j:len(cs_) - j], n_, k_, lag_) for j in range(cf_))
        if chb.get('on', 'stock') == 'sector':
            import csv as _csv7
            E7 = json.load(open(os.path.join(ROOT, 'data', 'sector_etf.json')))
            sec7 = {r['symbol']: r['industry'] for r in _csv7.DictReader(open(os.path.join(ROOT, 'data', 'sectors.csv')))}
            ind7 = {r['symbol']: r['industry'] for r in _csv7.DictReader(open(os.path.join(ROOT, 'data', 'industries.csv')))}
            SE7 = {'Information Technology': 'XLK', 'Technology': 'XLK', 'Financials': 'XLF', 'Energy': 'XLE', 'Health Care': 'XLV',
                   'Industrials': 'XLI', 'Consumer Discretionary': 'XLY', 'Consumer Staples': 'XLP', 'Utilities': 'XLU', 'Materials': 'XLB'}
            EF7 = {}
            for e_, bs_ in E7.items():
                ds_ = [b_[0] for b_ in bs_]; cs_ = [b_[4] for b_ in bs_]; fl_ = {}
                for i_ in range(n_ + lag_ + cf_, len(ds_) + 1):
                    fl_[ds_[i_ - 1]] = brk_series(cs_[i_ - (n_ + lag_ + cf_):i_])
                EF7[e_] = (ds_, fl_)

            def etf7(t, d_):
                if ind7.get(t) in ('Semiconductors', 'Semiconductor Materials & Equipment'):
                    return 'SMH'
                s_ = sec7.get(t)
                if s_ == 'Real Estate':
                    return 'XLRE' if d_ >= '2015-10-08' else 'IYR'
                if s_ == 'Communication Services':
                    return 'XLC' if d_ >= '2018-06-19' else 'VOX'
                return SE7.get(s_)

            def broke(t, k):
                d_ = cal_c[k]; e_ = etf7(t, d_)
                if not e_ or e_ not in EF7:
                    return False
                ds_, fl_ = EF7[e_]
                j_ = bisect_right(ds_, d_) - 1
                return j_ >= 0 and fl_.get(ds_[j_], False)
        else:
            def broke(t, k):
                key_ = (t, k)
                if key_ not in ccache:
                    p_ = px_c.get(t) or {}
                    m_ = n_ + lag_ + cf_
                    cs_ = [p_.get(cal_c[i_]) for i_ in range(max(0, k - m_ + 1), k + 1)]
                    ccache[key_] = len(cs_) == m_ and brk_series(cs_)
                return ccache[key_]
        if chb.get('sell'):
            prev_ew7 = kw.get('exit_when')
            kw['exit_when'] = (lambda t, k: prev_ew7(t, k) or broke(t, k)) if prev_ew7 else broke
        else:
            prev_bw7 = kw.get('buy_when')
            kw['buy_when'] = (lambda t, k: prev_bw7(t, k) and not broke(t, k)) if prev_bw7 else (lambda t, k: not broke(t, k))
    tx = kw.pop('techx', None)
    if tx:
        # a stock's own technical turns bearish: don't buy it (sell=True: also sell it when held, checked daily).
        # kinds: macd_sig (MACD 12/26 below its 9-day signal), macd_neg (MACD below zero), ichi_cloud (close below the
        # Ichimoku cloud plotted for today), tk (Tenkan 9 below Kijun 26), ma50 (close below its 50-day average)
        cal_x = P['calendar']; xcache = {}

        def tx_series(t):
            bs = G['BARS'].get(t) or []
            ds = [b[0][:10] for b in bs]; c = _np.array([b[4] for b in bs], dtype=float)
            h = _np.array([b[2] for b in bs], dtype=float); l = _np.array([b[3] for b in bs], dtype=float)
            n = len(c); bear = _np.zeros(n, bool)
            if n < 80:
                return ds, bear

            def ema(x, m):
                a = 2 / (m + 1); o = _np.empty(len(x)); o[0] = x[0]
                for i in range(1, len(x)):
                    o[i] = a * x[i] + (1 - a) * o[i - 1]
                return o
            kind = tx['kind']
            if kind in ('macd_sig', 'macd_neg'):
                m = ema(c, 12) - ema(c, 26)
                bear = (m < ema(m, 9)) if kind == 'macd_sig' else (m < 0)
                bear[:35] = False
            elif kind == 'ma50':
                cs = _np.cumsum(_np.insert(c, 0, 0)); ma = _np.full(n, _np.nan); ma[49:] = (cs[50:] - cs[:-50]) / 50
                bear = _np.where(_np.isnan(ma), False, c < _np.nan_to_num(ma))
            else:
                def mid(p_):
                    o = _np.full(n, _np.nan)
                    for i in range(p_ - 1, n):
                        o[i] = (h[i - p_ + 1:i + 1].max() + l[i - p_ + 1:i + 1].min()) / 2
                    return o
                ten, kij = mid(9), mid(26)
                if kind == 'tk':
                    bear = _np.where(_np.isnan(ten) | _np.isnan(kij), False, _np.nan_to_num(ten) < _np.nan_to_num(kij))
                else:
                    sb = mid(52); sa = (ten + kij) / 2
                    ca = _np.full(n, _np.nan); cb = _np.full(n, _np.nan); ca[26:] = sa[:-26]; cb[26:] = sb[:-26]
                    bot = _np.fmin(ca, cb)
                    bear = _np.where(_np.isnan(bot), False, c < _np.nan_to_num(bot))
            return ds, bear

        def tx_bear(t, k):
            if t not in xcache:
                xcache[t] = tx_series(t)
            ds, bear = xcache[t]
            j = bisect_right(ds, cal_x[k]) - 1
            return j >= 0 and bool(bear[j])
        if tx.get('sell'):
            prev_ew8 = kw.get('exit_when')
            kw['exit_when'] = (lambda t, k: prev_ew8(t, k) or tx_bear(t, k)) if prev_ew8 else tx_bear
        else:
            prev_bw8 = kw.get('buy_when')
            kw['buy_when'] = (lambda t, k: prev_bw8(t, k) and not tx_bear(t, k)) if prev_bw8 else (lambda t, k: not tx_bear(t, k))
    npz = kw.pop('narrowpause', None)
    if npz:
        # narrow-market warning (SPY within 2% of its 52-week high, equal-weight S&P lagging SPY by 1.5%+ over 3
        # months, VIX within 2 points of its 3-month low): starting `delay` sessions after each warning day, make no
        # new buys for `days` sessions; open slots stay in cash
        W9 = set(json.load(open(os.path.join(SIDE_, 'narrow_warn.json'))))
        cal_9 = P['calendar']; blk9 = [False] * len(cal_9)
        for i_, d_ in enumerate(cal_9):
            if d_ in W9:
                for j_ in range(i_ + 1 + npz.get('delay', 0), min(len(cal_9), i_ + 1 + npz.get('delay', 0) + npz['days'])):
                    blk9[j_] = True
        prev_bw9 = kw.get('buy_when')
        kw['buy_when'] = (lambda t, k: prev_bw9(t, k) and not blk9[k]) if prev_bw9 else (lambda t, k: not blk9[k])
    trg_ = kw.pop('trailg', None)
    cap = kw.pop('sector_cap', None)
    cap_level = kw.pop('cap_level', None)
    if cap:
        import csv
        with open(os.path.join(ROOT, 'data', 'sectors.csv' if cap_level == 'sector' else 'industries.csv')) as fh:
            ind = {r['symbol']: r['industry'] for r in csv.DictReader(fh) if r.get('industry')}
        kw['group_of'] = ind
        kw['max_per_group'] = cap
    if sig:
        nsig, upweek = sig
        prices_, cal_ = P['prices'], P['calendar']

        def day_drop(t, k):
            """True when the close at calendar[k] fell more than nsig x the stock's own daily
            volatility (standard deviation of the prior 63 daily returns)."""
            if k < 65:
                return False
            px = prices_[t]
            pts = [px.get(cal_[i]) for i in range(k - 64, k + 1)]
            if not all(pts):
                return False
            r = [pts[i + 1] / pts[i] - 1 for i in range(64)]
            hist = r[:-1]
            m = sum(hist) / len(hist)
            sd = (sum((x - m) ** 2 for x in hist) / (len(hist) - 1)) ** 0.5
            return sd > 0 and r[-1] < -nsig * sd
        kw['exit_when'] = day_drop
        kw['exit_daily'] = True
        if upweek:
            def up_week(t, k):
                px = prices_[t]
                a, b = px.get(cal_[k - 5]) if k >= 5 else None, px.get(cal_[k])
                return bool(a and b and b > a)
            kw['buy_when'] = up_week
    if accel:
        prices, cal = P['prices'], P['calendar']

        def seg(t, k):
            """Returns over 7-5, 5-3 and 3-1 months ago (42-session pieces after the skipped month)."""
            px = prices[t]
            pts = [px.get(cal[k - n]) if k - n >= 0 else None for n in (147, 105, 63, 21)]
            if not all(pts):
                return None
            return pts[1] / pts[0] - 1, pts[2] / pts[1] - 1, pts[3] / pts[2] - 1

        def key_first(t, k, sc):
            g = seg(t, k)
            fast = g is not None and g[2] > g[1] > g[0]
            return (0 if fast else 1, -sc)

        def key_blend(t, k, sc):
            g = seg(t, k)
            return -(sc + (g[2] - g[0] if g else 0.0))
        kw['rank_key'] = key_first if accel == 'first' else key_blend
    if trg_:
        # trailing stop: sell a holding that closes trg_['x'] below its best close since it was bought (traded at the
        # next close, barred like the other exits); with trg_['ma'] only while SPY is below that moving average
        th_, man_ = trg_['x'], trg_.get('ma')
        cal_t = P['calendar']; spx_ = P['prices'].get('SPY') or G['D']['SPY']
        sp_t, l_ = [], None
        for d_ in cal_t:
            l_ = spx_.get(d_) or l_; sp_t.append(l_)
        weak_ = [True] * len(sp_t)
        if man_:
            cs_, acc_ = [0.0], 0.0
            for x_ in sp_t:
                acc_ += x_ or 0.0; cs_.append(acc_)
            weak_ = [k_ >= man_ and sp_t[k_] is not None and sp_t[k_] < (cs_[k_ + 1] - cs_[k_ + 1 - man_]) / man_ for k_ in range(len(sp_t))]
        pxc_ = {}

        def tstop(t, k, e):
            if not weak_[k]:
                return False
            if t not in pxc_:
                p_ = P['prices'].get(t) or {}; o_, l2 = [], None
                for d_ in cal_t:
                    l2 = p_.get(d_) or l2; o_.append(l2)
                pxc_[t] = o_
            c_ = pxc_[t]
            if c_[k] is None:
                return False
            hi_ = max((x for x in c_[max(0, e):k + 1] if x), default=None)
            return hi_ is not None and c_[k] < hi_ * (1 - th_)
        prev_h = kw.get('hold_exit')
        kw['hold_exit'] = (lambda t, k, e, f_=prev_h: f_(t, k, e) or tstop(t, k, e)) if prev_h else tstop
    opts = dict(look=R.LOOK, skip=R.SKIP, eligible=elig, exec_next='close')
    opts.update(kw)
    if monthly:
        opts['rebal_dates'] = set(G['months'])
    if biweekly:
        opts['rebal_dates'] = set(G['biweeks'])
    if daily_rb:
        opts['rebal_dates'] = set(P['calendar'])
    if every_n:
        opts['rebal_dates'] = set(G['weeks'][offset::every_n])
    if boost:
        opts.update(prefer=booster(P['gaps'], P['calendar']), prefer_mode='force', prefer_rank=boost_rank,
                    prefer_pool='all')
        if fresh_:
            gaps_at = {}
            for t_, ds_ in P['gaps'].items():
                for d_ in ds_:
                    gaps_at.setdefault(d_, set()).add(t_)
            opts['prefer_now'] = lambda k_, g_=gaps_at, c_=P['calendar']: g_.get(c_[k_], ())
            opts['prefer_fill'] = fresh_
    prices_run = P['prices']
    regime_ = opts.pop('regime', None)
    wfo = opts.pop('weak_funds_only', False)
    ws = opts.pop('with_sleeve', False)
    if ws:
        prices_run = dict(P['prices'])
        sl_px = dict(P['sleeve_px'])
        if ws == 'lev':
            sl_px.update(G['LEVF'])
        elif ws == 'eq':
            sl_px = dict(G['LEVE'])
        elif ws == 'all':
            sl_px.update(G['LEVF'])
            sl_px.update(G['LEVE'])
        prices_run.update(sl_px)
        _e0 = opts['eligible']
        if regime_:
            strong = G['REG'][regime_]
            levset = set(G['LEVF']) | set(G['LEVE'])

            def _el(t, d, _e0=_e0, sl_px=sl_px):
                st = strong.get(d, True)
                if t in sl_px:
                    if sl_px[t].get(d) is None:
                        return False
                    return st or t not in levset
                if not st and wfo:
                    return False
                return _e0(t, d)
            opts['eligible'] = _el
        else:
            opts['eligible'] = lambda t, d, _e0=_e0, sl_px=sl_px: (t in sl_px and sl_px[t].get(d) is not None) or (t not in sl_px and _e0(t, d))
        if opts.get('prefer') is not None:
            _pf = opts['prefer']
            opts['prefer'] = lambda t, k, _pf=_pf: t not in sl_px and _pf(t, k)
    dt_ = opts.pop('dyn_top', None)
    if dt_:
        # holdings count by how far the leaders are ahead: mean score of the top 5 minus the median stock's score,
        # against its own history so far (needs 2 years of weekly readings first)
        import mtl.momentum as _mm0
        hist_, cache_ = [], {}

        def _top_n_at(k_, dt_=dt_):
            if k_ in cache_:
                return cache_[k_]
            rows_ = _mm0.score_table(prices_run, P['calendar'], k_, opts.get('look', R.LOOK), opts.get('skip', R.SKIP), None, 'rank', opts['eligible'], 'SPY')
            sc_ = [r_[1] for r_ in rows_]
            n_ = dt_.get('base', 5)
            if len(sc_) >= 20:
                sp_ = sum(sc_[:5]) / 5 - sorted(sc_)[len(sc_) // 2]
                if len(hist_) >= 104:
                    srt_ = sorted(hist_)
                    if sp_ > srt_[int(dt_['pct'] * (len(srt_) - 1))]:
                        n_ = dt_['n_hi']
                    elif dt_.get('lo_pct') is not None and sp_ < srt_[int(dt_['lo_pct'] * (len(srt_) - 1))]:
                        n_ = dt_['n_lo']
                hist_.append(sp_)
            cache_[k_] = n_
            return n_
        opts['top_n_at'] = _top_n_at
    pb_ = opts.pop('pullback', None)
    if pb_:
        # buy a new pick only on a pullback (close under its 5-day average, or a down day); the slot waits in cash,
        # optionally buying anyway after max_wait sessions
        calp_, clc_, first_ = P['calendar'], {}, {}

        def _cl(t):
            if t not in clc_:
                p_ = prices_run.get(t) or {}; o_, l_ = [], None
                for d_ in calp_:
                    l_ = p_.get(d_) or l_; o_.append(l_)
                clc_[t] = o_
            return clc_[t]

        def _buy_when(t, k_, pb_=pb_):
            c_ = _cl(t)
            if c_[k_] is None:
                return True
            if pb_['kind'] == 'sma5':
                w_ = [x for x in c_[max(0, k_ - 4):k_ + 1] if x]
                ok_ = len(w_) == 5 and c_[k_] < sum(w_) / 5
            else:
                ok_ = k_ >= 1 and bool(c_[k_ - 1]) and c_[k_] < c_[k_ - 1]
            mw_ = pb_.get('max_wait')
            if mw_:
                f_ = first_.get(t)
                if f_ is None or k_ - f_ > 10:
                    first_[t] = f_ = k_
                if k_ - f_ >= mw_:
                    ok_ = True
            if ok_:
                first_.pop(t, None)
            return ok_
        opts['buy_when'] = _buy_when
        opts['wait_buy'] = True
        opts['buy_max_rank'] = pb_.get('max_rank', 5)
    st_ = opts.pop('sec_top', None)
    if st_:
        import csv as _csv
        with open(os.path.join(ROOT, 'data', 'sectors.csv')) as fh_:
            opts['sector_of'] = {r_['symbol']: r_['industry'] for r_ in _csv.DictReader(fh_) if r_.get('industry')}
        opts['top_sectors'] = st_
        opts['sector_unknown_ok'] = True
    res_ = opts.pop('resid', None)
    if res_:
        # residual momentum: rank by the return not explained by market beta (scripts/resid_score.py)
        import mtl.momentum as _mm
        from resid_score import make_resid_table
        _orig_st = _mm.score_table
        _mm.score_table = make_resid_table(prices_run, P['calendar'], res_)
        try:
            r = run_momentum(prices_run, P['calendar'], R.START, **opts)
        finally:
            _mm.score_table = _orig_st
    else:
        r = run_momentum(prices_run, P['calendar'], R.START, **opts)
    out_ = dict(picks=r['picks'], weights=r['weights'], turnover=r['turnover'], plan=plan, curve=[[c_[0], c_[1]] for c_ in r['curve']])
    if pf_ and pf_.get('cash'):
        out_['spare_cash'] = True      # the filter's empty slot is plain cash, as the live scanner holds it
    if fz_sets:
        out_['fz_frozen'], out_['fz_green'] = fz_sets
        if fzr_.get('cash_wins'):   # precedence test: the green light leaves the narrow-market cash week alone
            out_['fz_green_cash'] = False
    if nopf_ is not None:
        # the same list with the filter off: the whipsaw half-switch counts its sales (Oct 16, 2026, as the live scanner)
        o2_ = dict(opts)
        for k2_, v2_ in nopf_.items():
            if v2_ is None:
                o2_.pop(k2_, None)
            else:
                o2_[k2_] = v2_
        out_['whip_picks'] = run_momentum(prices_run, P['calendar'], R.START, **o2_)['picks']
    return key, out_


def schedule(run, calendar, sleeve_f, down, start, frac=0.4):
    """[(trade date, {asset: weight})]: stocks at split x engine weight, unused stock
    weight in BIL, sleeve asset at 1-split when the downtrend share reaches `frac`.
    Plan options (run['plan']): ladder (True or a tuple of splits by downtrend count),
    one, trend, cash, cap, qqq, spy (SPY's own daily downtrend counts as one more),
    cash3 (3+ downtrends: the sleeve part goes to T-bills), daily (the split is
    re-checked every session, not only on the weekly trade)."""
    idx = {d: i for i, d in enumerate(calendar)}
    picks = run['picks']
    pdays = [p[0] for p in picks]
    po = run.get('plan') or {}
    wl = run['weights']
    wdays = [x[0] for x in wl]
    eng = set(wdays)

    def build(T, w):
        if po.get('same'):      # traded at the deciding close: read the charts at that close,
            f = T               # with the holdings going into it
            j = bisect_right(pdays, calendar[idx[T] - 1]) - 1
        else:
            f = calendar[idx[T] - 1]
            j = bisect_right(pdays, f) - 1
        before = picks[j][1] if j >= 0 else []
        if po.get('tl') is not None:   # a break of the rising higher-low trend line also counts
            n_down = sum(down(t, f) or G['tl_break'](t, f, po['tl']) for t in before)
        else:
            n_down = sum(down(t, f) for t in before)
        if po.get('spy') and before:
            n_down += G['spy_down'](f)
        lad = po.get('ladder')
        if lad:
            lad = (1.0, 0.8, 0.6, 0.4) if lad is True else lad
            split = lad[min(n_down, len(lad) - 1)] if before else 1.0
        elif po.get('one'):
            split = 0.6 if n_down >= 1 else 1.0
        else:
            split = 0.6 if before and n_down / len(before) >= frac - 1e-9 else 1.0
        if po.get('trend') is not None and G['spy_below'](f):
            split = min(split, po['trend'])
        if po.get('cap') is not None:
            split = min(split, po['cap'])
        out_w = {t: split * x for t, x in w.items()}
        spare = split * (1 - sum(w.values()))
        if spare > 1e-6:
            sp_a = 'SPY' if po.get('spare_spy') else 'CASH0' if run.get('spare_cash') else 'BIL'
            out_w[sp_a] = out_w.get(sp_a, 0.0) + spare
        if split < 1:
            if (po.get('cash') and G['spy_below'](f)) or (po.get('cash3') and n_down >= 3):
                a = 'BIL'
            elif po.get('slv_up'):     # only sleeve funds whose daily chart is in a higher-high uptrend
                ok = [x for x in ASSETS if x == 'BIL' or G['asset_up'](x, f)]
                a = best_of(sleeve_f, calendar, idx[f], assets=ok)
            elif po.get('slv_ok'):     # skip sleeve funds whose own daily chart is in a lower-low downtrend
                ok = [x for x in ASSETS if x == 'BIL' or not G['asset_down'](x, f)]
                a = best_of(sleeve_f, calendar, idx[f], assets=ok)
            elif po.get('srank'):      # sleeve fund by the weekly rank sum (like the stocks)
                a = sleeve_rank(sleeve_f, calendar, idx[f], po['srank'])
            elif po.get('btc'):        # Bitcoin as a seventh sleeve choice (from its first price, Sep 2014)
                gate = po.get('btc_gate')
                ok = True
                if gate in ('sma', 'both') and G['spy_below'](f):
                    ok = False
                if gate in ('lolo', 'both') and G['spy_down'](f):
                    ok = False
                a = best_of(G['sleeve_f_btc'], calendar, idx[f], assets=ASSETS + ['BTC-USD']) if ok else \
                    best_of(sleeve_f, calendar, idx[f])
            else:
                a = best_of(sleeve_f, calendar, idx[f], look=po.get('slook', 126))
            out_w[a] = out_w.get(a, 0.0) + (1 - split)
        if po.get('qqq'):
            out_w = {t: x * (1 - po['qqq']) for t, x in out_w.items()}
            out_w['QQQ'] = out_w.get('QQQ', 0.0) + po['qqq']
        return out_w

    out = []
    if not po.get('daily'):
        for T, w in wl:
            if T < start or idx[T] == 0:
                continue
            out.append((T, build(T, w)))
        return out
    last = None
    for T in calendar:
        if T < start or idx[T] == 0 or T < wdays[0]:
            continue
        w = wl[bisect_right(wdays, T) - 1][1]
        ow = build(T, w)
        sig = tuple(sorted((k, round(v, 4)) for k, v in ow.items() if k in ASSETS or v == 0))
        if T in eng or sig != last:
            out.append((T, ow))
        last = sig
    return out


SLOTS = (0.30, 0.30, 0.40 / 3, 0.40 / 3, 0.40 / 3)


def slot_weights(run, slots=SLOTS):
    """Fixed slot weights: the first holdings are placed best-ranked into the biggest
    slots; a holding keeps its slot until sold, and a new buy takes over the biggest
    free slot (best-ranked new buy first). Returns a copy of run with 'weights'
    replaced; slots left empty sit in cash."""
    occ = {}
    out = []
    for T, held in run['picks']:
        for t in list(occ):
            if t not in held:
                del occ[t]
        free = sorted(slots, reverse=True)
        for w in occ.values():
            free.remove(w)
        for t in held:               # held is keepers (by rank) then new buys (by rank)
            if t not in occ and free:
                occ[t] = free.pop(0)
        out.append([T, {t: occ[t] for t in held if t in occ}])
    r = dict(run)
    r['weights'] = out
    return r


def sleeve_rank(f, calendar, k, windows):
    """The sleeve fund with the best sum of weekly ranks (each week's return ranked
    across the 6 funds), T-bills included as one of them."""
    rets = {}
    for t in ASSETS:
        px = f.get(t) or {}
        r = []
        for lk, sk in windows:
            if k - lk < 0:
                break
            a, b = px.get(calendar[k - lk]), px.get(calendar[k - sk])
            if not (a and b):
                break
            r.append(b / a - 1)
        if len(r) == len(windows):
            rets[t] = r
    if not rets:
        return 'BIL'
    score = {t: 0 for t in rets}
    for w in range(len(windows)):
        for i, t in enumerate(sorted(rets, key=lambda t: rets[t][w])):
            score[t] += i
    return max(score, key=lambda t: score[t])


def longest_hold(sc):
    """Longest unbroken stretch any asset (stock or sleeve fund) is held, in days, and which."""
    open_, best = {}, (0, None, None)
    for T, w in sc:
        held = {t for t, x in w.items() if x > 1e-9}
        for t in list(open_):
            if t not in held:
                d = (date.fromisoformat(T) - date.fromisoformat(open_[t])).days
                best = max(best, (d, t, open_[t]))
                del open_[t]
        for t in held:
            open_.setdefault(t, T)
    last = sc[-1][0] if sc else None
    for t, a in open_.items():
        best = max(best, ((date.fromisoformat(last) - date.fromisoformat(a)).days, t, a))
    return list(best)


def yr_windows(curve, spy, starts):
    wins, n = 0, 0
    for s in starts:
        e = (date.fromisoformat(s) + timedelta(days=round(3 * 365.25))).isoformat()
        if e > curve[-1][0]:
            continue
        a, b = R.cagr_between(curve, s, e), R.cagr_between(spy, s, e)
        if a is not None and b is not None:
            n += 1
            wins += a > b
    return wins, n


def concentration(runs, scheds, px_all, cal, P, evaluate):
    extra = {}
    for key in ('v2_auto', 'v2_boost'):
        contrib = R.week_contrib(scheds[key], px_all, cal, P['prices']['SPY'])
        tab = R.outlier_table(contrib, P['prices']['SPY'], scheds[key], cal)
        extra[key] = dict(rows=tab['rows'], topStocks=tab['topStocks'][:5], weeksBeatSpy=tab['weeksBeatSpy'],
                          top10Share=tab['top10ShareOfExcess'])
    best = {k: [t for t, _ in extra[k]['topStocks'][:3]] for k in extra}
    jobs = []
    for k in ('v2_auto', 'v2_boost'):
        kw = VARIANTS['v2'][0]
        jobs.append((f'{k}_ex1', kw, k.endswith('boost'), tuple(best[k][:1])))
        jobs.append((f'{k}_ex3', kw, k.endswith('boost'), tuple(best[k][:3])))
    with get_context('fork').Pool(int(os.environ.get('ENGINE_PROCS', '4'))) as pool:
        for key, run in pool.imap_unordered(run_one, jobs):
            _, _, out = evaluate(key, run)
            base_key = key.rsplit('_', 1)[0]
            extra[base_key][key.rsplit('_', 1)[1]] = dict(excluded=best[base_key][:1 if key.endswith('ex1') else 3],
                                                          preTax=out['preTax'], afterTax=out['afterTax'])
            R.log(f"  {key}: pre {out['preTax'].get('cagr')}")

    return extra


def main():
    t0 = datetime.now()
    D = R.load_data()
    LEV = ['TQQQ', 'SOXL', 'UPRO', 'TECL']
    try:
        from momentum_scan import fetch as _fetch2
        lev = _fetch2(LEV, start=R.FROM, adjusted=True)
        for t_, bs_ in lev.items():
            if bs_:
                D['bars'][t_] = bs_
        R.log(f"leveraged ETFs: {sorted(t for t in lev if lev[t])}")
    except Exception as e:   # noqa: BLE001
        R.log(f"leveraged ETF fetch failed: {e}")
    G['LEV'] = set(LEV)
    bil = D['assets'].get('BIL') or []
    if bil and R.FROM < bil[0][0]:
        try:
            from momentum_scan import fetch as _f3
            irx = {b[0]: b[4] for b in (_f3(['^IRX'], start=R.FROM).get('^IRX') or []) if b[4]}
            calx = [b[0] for b in D['bench']['SPY']]
            first = bil[0][0]
            pre = [d_ for d_ in calx if d_ < first]
            v_, last_y, out_ = bil[0][4], None, []
            for d_ in reversed(pre):        # walk back from BIL's first close at the T-bill rate
                y_ = irx.get(d_, last_y) or 0.0
                last_y = y_
                v_ = v_ / (1 + y_ / 100 / 252)
                out_.append([d_, v_, v_, v_, v_])
            D['assets']['BIL'] = list(reversed(out_)) + bil
            R.log(f"synthetic BIL from {pre[0] if pre else None} ({len(pre)} sessions, ^IRX {len(irx)} days)")
        except Exception as e:   # noqa: BLE001
            R.log(f"synthetic BIL failed: {e}")
    if os.environ.get('WITH_VOLUME'):
        import yfinance as yf
        from itertools import accumulate
        tick = sorted(t for t, bs in D['bars'].items() if bs)
        calx = [b[0] for b in D['bench']['SPY']]
        pos = {d_: i_ for i_, d_ in enumerate(calx)}
        dvcum = {}
        for k_ in range(0, len(tick), 100):
            part = tick[k_:k_ + 100]
            df = yf.download(part, start=R.FROM, interval='1d', group_by='ticker', auto_adjust=False,
                             progress=False, threads=True)
            for t_ in part:
                try:
                    d_ = df[t_].dropna(subset=['Close'])
                except KeyError:
                    continue
                dv = [0.0] * len(calx)
                for ts, c_, v_ in zip(d_.index, d_['Close'], d_['Volume']):
                    i_ = pos.get(ts.date().isoformat())
                    if i_ is not None and c_ == c_ and v_ == v_:
                        dv[i_] = float(c_) * float(v_)
                acc = list(accumulate(dv))
                dvcum[t_] = acc
            R.log(f"  dollar volume {min(k_ + 100, len(tick))}/{len(tick)}")
        G['dvcum'] = dvcum
    if os.environ.get('EXCLUDE'):
        for t_ in os.environ['EXCLUDE'].split(','):
            D['bars'].pop(t_, None)
        R.log(f"excluded {os.environ['EXCLUDE']}")
    P = R.prepare(D)
    if R.START < '2009':
        cov = R.coverage(D, P)
        R.log("coverage: " + ", ".join(f"{c_['year']} {c_['priced']}/{c_['members']}" for c_ in cov['byYear'][:11]))
    G['P'] = P
    R.G['P'] = P
    G['BARS'] = D['bars']
    G['SPYB'] = D['bench']['SPY']
    cal = P['calendar']
    G['months'] = month_ends(cal)
    from mtl.momentum import last_sessions_of_weeks as _lsw
    G['weeks'] = [x for x in _lsw(cal) if x >= '2009-01-01']
    G['biweeks'] = [d_ for i_, d_ in enumerate(x for x in _lsw(cal) if x >= '2009-01-01') if i_ % 2 == 0]
    down = R.downtrend_fn(D['bars'])
    G['down'] = down
    from mtl.structure import structure_signal as _ss
    _bd = {t: [b[0] for b in bs] for t, bs in D['bars'].items()}
    _uc = {}

    def up_fn(t, d_):
        if (t, d_) not in _uc:
            j_ = bisect_right(_bd.get(t, []), d_)
            daily = [tuple(b) for b in D['bars'].get(t, [])[max(0, j_ - 320):j_]]
            _uc[(t, d_)] = _ss(daily, n=3, lookback=2)['state'] == 'uptrend'
        return _uc[(t, d_)]
    G['up'] = up_fn
    if any(k_.startswith('z') for k_ in [x for x in os.environ.get('ONLY', '').split(',') if x]):
        import numpy as np
        from mtl.momentum import last_sessions_of_weeks as _lw2
        ends_ = _lw2(cal)
        pos_ = {d: i for i, d in enumerate(cal)}
        tick_ = [t for t in P['prices'] if t != 'SPY']
        M = np.full((len(tick_), len(ends_)), np.nan)
        for a_, t in enumerate(tick_):
            px_ = P['prices'][t]
            M[a_] = [px_.get(d, np.nan) for d in ends_]
        with np.errstate(invalid='ignore', divide='ignore'):
            R_ = M[:, 1:] / M[:, :-1] - 1
        R_ = np.c_[np.full(len(tick_), np.nan), R_]
        R_[np.abs(R_) > 1.5] = np.nan
        zM = np.full_like(R_, np.nan)
        for w in range(9, R_.shape[1]):
            past = R_[:, max(0, w - 52):w]
            cnt = np.sum(np.isfinite(past), axis=1)
            sd = np.nanstd(past, axis=1, ddof=1)
            ok = (cnt >= 8) & (sd > 0)
            zM[ok, w] = R_[ok, w] / sd[ok]
        # rank of z among all stocks with a value that week (1 = most unusual gain)
        rk = np.full_like(zM, np.nan)
        for w in range(zM.shape[1]):
            col = zM[:, w]
            f = np.isfinite(col)
            if f.sum():
                order = np.argsort(-col[f])
                r_ = np.empty(f.sum()); r_[order] = np.arange(1, f.sum() + 1)
                rk[f, w] = r_ / f.sum()          # as a share of the field (0..1) so field size does not matter
        def roll(A):
            out = np.full_like(A, np.nan)
            for w in range(26, A.shape[1]):
                win = A[:, w - 25:w + 1]
                cnt = np.sum(np.isfinite(win), axis=1)
                v = np.nanmean(win, axis=1) * 26
                out[cnt >= 20, w] = v[cnt >= 20]
            return out
        G['Z'] = dict(eidx=[pos_[d] for d in ends_],
                      z={t: zM[a_] for a_, t in enumerate(tick_)},
                      zsum={t: v for t, v in zip(tick_, roll(zM))},
                      rsum={t: v for t, v in zip(tick_, roll(rk))})
        R.log('z-scores ready')
    from mtl.structure import find_swings as _fs
    _hc = {}

    def hl_fn(t, d_):
        if (t, d_) not in _hc:
            j_ = bisect_right(_bd.get(t, []), d_)
            daily = [tuple(b) for b in D['bars'].get(t, [])[max(0, j_ - 120):j_]]
            lows = [s_['price'] for s_ in _fs(daily, n=3) if s_['type'] == 'low']
            _hc[(t, d_)] = len(lows) >= 2 and lows[-1] > lows[-2]
        return _hc[(t, d_)]
    G['hl'] = hl_fn
    from mtl.backtest import rsi_series as _rs
    _rc = {}

    def rsi_fn(t, d_):
        if t not in _rc:
            px_ = P['prices'].get(t, {})
            ds_ = sorted(px_)
            _rc[t] = dict(zip(ds_, _rs([px_[x] for x in ds_])))
        return _rc[t].get(d_)
    G['rsi'] = rsi_fn
    from momentum_scan import fetch as _fl
    LEVF = ['UBT', 'TMF', 'UST', 'TYD', 'UGL', 'DGP', 'UGLD']
    G['LEVF'] = {t_: {b[0]: b[4] for b in bs_} for t_, bs_ in _fl(LEVF, start=R.FROM, adjusted=True).items() if bs_}
    R.log(f"leveraged funds: {sorted(G['LEVF'])}")
    LEVE = ['SSO', 'QLD', 'ROM', 'USD', 'UPRO', 'SPXL', 'TQQQ', 'UDOW', 'URTY', 'TNA', 'SOXL', 'TECL', 'FAS', 'CURE', 'LABU', 'DPST',
            'FNGU', 'FNGO', 'NVDL', 'NVDU', 'TSLL', 'CONL', 'MSTU', 'AMZU', 'AAPU', 'GGLL', 'MSFU', 'METU', 'AVL', 'PLTU', 'SMCX',
            'NAIL', 'RETL', 'DFEN', 'HIBL', 'BULZ', 'WEBL', 'UTSL', 'DUSL', 'MIDU', 'EDC', 'YINN', 'KORU', 'NUGT', 'JNUG', 'GUSH',
            'ERX', 'BOIL', 'UCO', 'AGQ']
    G['LEVE'] = {t_: {b[0]: b[4] for b in bs_} for t_, bs_ in _fl(LEVE, start=R.FROM, adjusted=True).items() if bs_}
    R.log(f"leveraged stock funds: {len(G['LEVE'])}")
    import numpy as _np
    _spy = [P['prices']['SPY'].get(d_) for d_ in cal]
    reg = {'spy200': {}, 'spy6m': {}, 'breadth': {}, 'both': {}}
    for k_ in range(len(cal)):
        if k_ >= 200 and all(_spy[k_ - 199:k_ + 1]):
            reg['spy200'][cal[k_]] = _spy[k_] > sum(_spy[k_ - 199:k_ + 1]) / 200
        for n_ in (100, 120, 150, 180):
            if k_ >= n_ and all(_spy[k_ - n_ + 1:k_ + 1]):
                reg.setdefault('spy%d' % n_, {})[cal[k_]] = _spy[k_] > sum(_spy[k_ - n_ + 1:k_ + 1]) / n_
        if k_ >= 126 and _spy[k_] and _spy[k_ - 126]:
            reg['spy6m'][cal[k_]] = _spy[k_] > _spy[k_ - 126]
    _tk = [t_ for t_ in P['prices'] if t_ != 'SPY']
    _M = _np.array([[P['prices'][t_].get(d_, _np.nan) for d_ in cal] for t_ in _tk], dtype=float)
    _cs = _np.nancumsum(_np.nan_to_num(_M), axis=1)
    _cn = _np.cumsum(_np.isfinite(_M), axis=1)
    for k_ in range(50, len(cal)):
        s50 = (_cs[:, k_] - _cs[:, k_ - 50]); n50 = (_cn[:, k_] - _cn[:, k_ - 50])
        okk = (n50 == 50) & _np.isfinite(_M[:, k_])
        if okk.sum() > 50:
            reg['breadth'][cal[k_]] = float(_np.mean(_M[okk, k_] > s50[okk] / 50)) >= 0.5
    for d_ in cal:
        if d_ in reg['spy200'] and d_ in reg['breadth']:
            reg['both'][d_] = reg['spy200'][d_] and reg['breadth'][d_]
    reg['s150or6m'] = {d_: reg.get('spy150', {}).get(d_, True) or reg['spy6m'].get(d_, True) for d_ in cal}
    for nm_, wins_ in (('manual3', [('2008-09-15', '2008-10-27'), ('2011-11-21', '2012-01-12'), ('2020-02-07', '2020-03-03'),
                                     ('2022-04-18', '2022-05-09'), ('2022-09-19', '2022-10-17'), ('2025-03-03', '2025-03-25')]),
                       ('manual', [('2020-03-06', '2020-03-24'), ('2022-04-04', '2022-07-05'), ('2025-02-25', '2025-03-19')]),
                       ('manual2', [('2020-03-06', '2020-03-24'), ('2022-04-04', '2022-07-05'), ('2025-02-25', '2025-04-03')])):
        reg[nm_] = {}
        for k_ in range(len(cal) - 1):
            n_ = cal[k_ + 1]       # weights decided at cal[k_] are held from the close of the next session
            reg[nm_][cal[k_]] = not any(a_ <= n_ < b_ for a_, b_ in wins_)
    try:
        XA_ = json.load(open(os.path.join(SIDE_, 'xasset.json')))

        def _fill(t):
            o_, l_ = [], None
            for d_ in cal:
                l_ = XA_.get(t, {}).get(d_) or l_
                o_.append(l_)
            return o_
        cu_, oil_, iwm_, spyx_, hyg_, lqd_, usd_ = (_fill(t) for t in ('HG=F', 'CL=F', 'IWM', 'SPY', 'HYG', 'LQD', 'DX-Y.NYB'))

        def ch_(a, k_, n=21):
            return a[k_] / a[k_ - n] - 1 if k_ >= n and a[k_] and a[k_ - n] else None

        def rat_(a, b, k_, n=21):
            return (a[k_] / b[k_]) / (a[k_ - n] / b[k_ - n]) - 1 if k_ >= n and all((a[k_], b[k_], a[k_ - n], b[k_ - n])) else None
        conf = {'cu': lambda k_: ch_(cu_, k_), 'hy': lambda k_: rat_(hyg_, lqd_, k_), 'sc': lambda k_: rat_(iwm_, spyx_, k_),
                'oil': lambda k_: (lambda v: None if v is None else v + 0.05)(ch_(oil_, k_)), 'usd': lambda k_: (lambda v: None if v is None else -v)(ch_(usd_, k_))}
        weak150 = reg['spy150']
        for nm_ in list(conf) + ['any2']:
            reg['c_' + nm_] = {}
        for k_, d_ in enumerate(cal):
            w_ = not weak150.get(d_, True)
            vals = {n_: f_(k_) for n_, f_ in conf.items()}
            for n_, v_ in vals.items():
                bad_ = True if v_ is None else v_ < 0      # no data yet: the plain 150-day rule
                reg['c_' + n_][d_] = not (w_ and bad_)
            have = [v_ for n_, v_ in vals.items() if n_ in ('cu', 'hy', 'sc', 'usd') and v_ is not None]
            nbad = sum(1 for v_ in have if v_ < 0)
            reg['c_any2'][d_] = not (w_ and (nbad >= 2 if len(have) >= 2 else True))
        for n_ in list(conf) + ['any2']:
            on_ = [d_ for d_ in cal if d_ >= R.START and not reg['c_' + n_][d_]]
            R.log(f"cushion confirm {n_}: on {len(on_)} sessions (plain 150-day: {sum(1 for d_ in cal if d_ >= R.START and not weak150.get(d_, True))})")
    except Exception as e_:   # noqa: BLE001
        R.log(f"confirm regimes failed: {e_}")
    try:
        VXD_ = json.load(open(os.path.join(SIDE_, 'vix_irx.json')))['^VIX']
        lv_ = None
        for th_ in (20, 25, 30, 35):
            reg[f'vix{th_}'] = {}
        for d_ in cal:
            lv_ = VXD_.get(d_) or lv_
            for th_ in (20, 25, 30, 35):
                reg[f'vix{th_}'][d_] = lv_ is None or lv_ <= th_     # strong = VIX at or below the level
        R.log('vix regimes: ' + ', '.join(f"{th_}: {sum(1 for d_ in cal if d_ >= R.START and not reg[f'vix{th_}'][d_])}" for th_ in (20, 25, 30, 35)))
    except Exception as e_:   # noqa: BLE001
        R.log(f"vix regimes failed: {e_}")
    try:
        IRX_ = json.load(open(os.path.join(SIDE_, 'vix_irx.json')))['^IRX']
        reg['lowrate'], li_ = {}, None
        for d_ in cal:
            li_ = IRX_.get(d_) or li_
            reg['lowrate'][d_] = li_ is None or li_ >= 1.0      # weak = 3-month T-bill under 1%
        R.log(f"low-rate sessions: {sum(1 for d_ in cal if d_ >= R.START and not reg['lowrate'][d_])}")
    except Exception as e_:   # noqa: BLE001
        R.log(f"lowrate failed: {e_}")
    G['REG'] = reg
    _pos = {d_: i_ for i_, d_ in enumerate(cal)}
    from mtl.backtest import rsi_series as _rsx
    _xc = {}

    def XF(t):
        if t not in _xc:
            px_ = P['prices'].get(t)
            if not px_:
                _xc[t] = None
                return None
            c = _np.full(len(cal), _np.nan)
            for d_, v_ in px_.items():
                i_ = _pos.get(d_)
                if i_ is not None:
                    c[i_] = v_
            for i_ in range(1, len(c)):          # carry gaps
                if c[i_] != c[i_]:
                    c[i_] = c[i_ - 1]
            cs = _np.nancumsum(_np.nan_to_num(c))
            ma50 = _np.full(len(c), _np.nan); ma200 = _np.full(len(c), _np.nan)
            ma50[50:] = (cs[50:] - cs[:-50]) / 50; ma200[200:] = (cs[200:] - cs[:-200]) / 200
            f0 = _np.argmax(_np.isfinite(c))
            ma50[:f0 + 50] = _np.nan; ma200[:f0 + 200] = _np.nan
            rs = _np.full(len(c), _np.nan)
            vals = _rsx(list(c[f0:]))
            rs[f0:] = [x if x is not None else _np.nan for x in vals]
            _xc[t] = dict(c=c, ma50=ma50, ma200=ma200, rsi=rs)
        return _xc[t]
    G['XF'] = XF
    R.log('regimes: ' + ', '.join(f"{k_} weak {sum(1 for d_, v in r_.items() if not v and d_ >= R.START) / max(1, sum(1 for d_ in r_ if d_ >= R.START)):.0%}" for k_, r_ in reg.items()))
    px_all = dict(P['prices'])
    px_all.update(P['sleeve_px'])
    px_all.update(G['LEVF'])
    px_all.update(G['LEVE'])
    px_all['QQQ'] = {b[0]: b[4] for b in D['bench']['QQQ']}
    try:   # long Treasuries / gold with older stand-ins: VUSTX before TLT (Jul 2002), gold futures before GLD (Nov 2004)
        SPL_ = json.load(open(os.path.join(SIDE_, 'spliced.json')))
        for t_, bs_ in SPL_.items():
            D['assets'][t_] = [tuple(b_) for b_ in bs_]
            px_all[t_] = {b_[0]: b_[4] for b_ in bs_}
    except Exception as e_:   # noqa: BLE001
        R.log(f"spliced assets failed: {e_}")
    try:
        from momentum_scan import fetch as _fetch
        from mtl.sleeve import filled as _filled
        _btc = _fetch(['BTC-USD'], start='2014-01-01', adjusted=True).get('BTC-USD') or []
        calset = set(cal)
        btc_px = {b[0]: b[4] for b in _btc if b[0] in calset and b[4]}
        R.log(f"BTC-USD closes: {len(btc_px)} from {min(btc_px) if btc_px else None}")
        px_all['BTC-USD'] = btc_px
        G['sleeve_f_btc'] = _filled(dict(P['sleeve_px'], **{'BTC-USD': btc_px}), cal)
    except Exception as e:   # noqa: BLE001
        R.log(f"BTC fetch failed: {e}")
    spx = P['prices']['SPY']
    sma_ok = {}
    for k_ in range(200, len(cal)):
        w_ = [spx.get(cal[j]) for j in range(k_ - 199, k_ + 1)]
        if all(w_):
            sma_ok[cal[k_]] = spx[cal[k_]] < sum(w_) / 200
    G['spy_below'] = lambda d_: sma_ok.get(d_, False)
    G['asset_down'] = R.downtrend_fn(D['assets'])
    from mtl.structure import find_swings, label_structure
    b_days = {t: [b[0] for b in bs] for t, bs in D['bars'].items()}
    tl_cache = {}

    def tl_break(t, d_, buf=0.0):
        """True when the last two swing lows are rising (a higher low) and the close at d_
        is below the line through them, extended to d_ (less `buf`, e.g. 0.02 = 2% below)."""
        key = (t, d_, buf)
        if key not in tl_cache:
            j_ = bisect_right(b_days.get(t, []), d_)
            bs = [tuple(b) for b in D['bars'].get(t, [])[max(0, j_ - 320):j_]]
            out = False
            if len(bs) > 20:
                lows = [x for x in label_structure(find_swings(bs, n=3)) if x['type'] == 'low']
                if len(lows) >= 2 and lows[-1]['price'] > lows[-2]['price']:
                    a, b = lows[-2], lows[-1]
                    slope = (b['price'] - a['price']) / (b['i'] - a['i'])
                    line = b['price'] + slope * (len(bs) - 1 - b['i'])
                    out = bs[-1][4] < line * (1 - buf)
            tl_cache[key] = out
        return tl_cache[key]
    G['tl_break'] = tl_break
    a_days = {t: [b[0] for b in bs] for t, bs in D['assets'].items()}
    a_cache = {}

    def asset_up(t, d_):
        if (t, d_) not in a_cache:
            j_ = bisect_right(a_days.get(t, []), d_)
            daily = [tuple(b) for b in D['assets'].get(t, [])[max(0, j_ - 320):j_]]
            a_cache[(t, d_)] = R.structure_signal(daily, n=3, lookback=2)['state'] == 'uptrend'
        return a_cache[(t, d_)]
    G['asset_up'] = asset_up
    G['spy_down'] = R.downtrend_fn({'SPY': D['bench']['SPY']})
    G['spy_down'] = (lambda f_, _d=G['spy_down']: _d('SPY', f_))
    spy = [[b[0], b[4]] for b in D['bench']['SPY'] if b[0] >= R.START]
    qqq = [[b[0], b[4]] for b in D['bench']['QQQ'] if b[0] >= R.START]
    starts = [d for d in (next((x for x in cal if x >= f'{y}-{m}-01'), None)
                          for y in range(int(R.START[:4]), 2024) for m in ('01', '07')) if d and d >= R.START]

    jobs = []
    only = [x for x in os.environ.get('ONLY', '').split(',') if x]
    for name, (kw, _) in VARIANTS.items():
        if only and name not in only:
            continue
        if not os.environ.get('BOOST_ONLY') or name == 'oldld':
            jobs.append((f'{name}_auto', kw, False, ()))
        jobs.append((f'{name}_boost', kw, True, ()))
    runs = {}
    with get_context('fork').Pool(int(os.environ.get('ENGINE_PROCS', '4'))) as pool:
        for key, res in pool.imap_unordered(run_one, jobs):
            runs[key] = res
            R.log(f"  run done: {key}")

    if os.environ.get('DUMP_PICKS'):
        kp = os.environ['DUMP_PICKS']
        pk = runs[kp]['picks']
        tk = sorted({t for _, h in pk for t in h} | {'SPY'})
        with open(os.path.join(ROOT, 'data', 'picks_dump.json'), 'w') as fh:
            json.dump(dict(key=kp, calendar=cal, picks=pk, prices={t: px_all.get(t, {}) for t in tk}), fh)
        R.log('wrote picks_dump.json')
    bil_ = P['sleeve_px']['BIL']
    syn = {}

    def synth(t, L):
        # daily-reset L x the stock, paying the T-bill rate on the borrowed part and a 0.95% a year fee
        key_ = f'{t}*{L}'
        if key_ not in syn:
            px_ = px_all[t]
            out, v, prev, pb = {}, None, None, None
            for d_ in cal:
                p_, b_ = px_.get(d_), bil_.get(d_)
                if p_ is None:
                    continue
                if v is None:
                    v = p_
                else:
                    r_ = p_ / prev - 1
                    rf = (b_ / pb - 1) if (b_ and pb) else 0.0
                    v = max(v * (1 + L * r_ - (L - 1) * rf - 0.0095 / 252), 1e-6)
                out[d_] = v
                prev, pb = p_, b_ if b_ else pb
            syn[key_] = out
            px_all[key_] = out
        return key_

    def lever(sc, plan):
        L, rg = plan['lev']
        strong = G['REG'][rg] if rg else None
        out = []
        for d_, w in sc:
            if strong is not None and not strong.get(d_, True):
                out.append((d_, w))
                continue
            out.append((d_, {(synth(t, L) if t not in ASSETS and t in P['prices'] else t): x for t, x in w.items()}))
        return out

    def evaluate(key, run):
        if run.get('spare_cash') and 'CASH0' not in px_all:
            px_all['CASH0'] = {d_: 1.0 for d_ in cal}
        sc = run['sched'] if 'sched' in run else schedule(run, cal, P['sleeve_f'], down, R.START)
        if (run.get('plan') or {}).get('lev'):
            sc = lever(sc, run['plan'])
        if (run.get('plan') or {}).get('trim'):
            mode_ = run['plan']['trim']
            idx_ = {d_: i_ for i_, d_ in enumerate(cal)}
            entry, sc2 = {}, []
            for d_, w in sc:
                f_k = idx_[d_] - 1
                held_now = {t for t, x in w.items() if t not in ASSETS and x > 0}
                for t in list(entry):
                    if t not in held_now:
                        del entry[t]
                for t in held_now:
                    entry.setdefault(t, f_k)
                w2, spare = {}, 0.0
                for t, x in w.items():
                    keep = 1.0
                    a = G['XF'](t) if t in held_now else None
                    if a is not None:
                        c = a['c']; e = entry[t]
                        seg = c[e:f_k + 1]
                        if len(seg) and seg[0] == seg[0]:
                            if mode_ == 'ext50':
                                ma = a['ma50'][f_k]
                                keep = 0.5 if (ma == ma and c[f_k] > ma * 1.5) else 1.0
                            elif mode_ == 'pt':
                                mx = _np.nanmax(seg) / seg[0] - 1
                                keep = 1/3 if mx >= 1.0 else 2/3 if mx >= 0.5 else 1.0
                            elif mode_ == 'bt50_25':
                                pk = _np.nanmax(seg)
                                keep = 0.5 if (pk >= seg[0] * 1.5 and c[f_k] <= pk * 0.75) else 1.0
                    w2[t] = x * keep
                    spare += x * (1 - keep)
                if spare > 1e-9:
                    w2['BIL'] = w2.get('BIL', 0.0) + spare
                sc2.append((d_, w2))
            sc = sc2
        if (run.get('plan') or {}).get('gates'):
            idx_ = {d_: i_ for i_, d_ in enumerate(cal)}
            cv = dict((c_[0], c_[1]) for c_ in run['curve'])
            cvl = run['curve']
            ma = {}
            acc = []
            for d_, v_ in cvl:
                acc.append(v_)
                if len(acc) > 100:
                    acc.pop(0)
                ma[d_] = len(acc) < 100 or v_ >= sum(acc) / 100
            sc2 = []
            for d_, w in sc:
                f_ = cal[idx_[d_] - 1]
                cut = 0.0
                for rg_, c_ in run['plan']['gates']:
                    ok_ = ma.get(f_, True) if rg_ == 'eq100' else G['REG'][rg_].get(f_, True)
                    if not ok_:
                        cut += c_
                if cut <= 0:
                    sc2.append((d_, w))
                    continue
                cut = min(cut, 1.0)
                asset = 'BIL' if cut >= 1.0 else best_of(P['sleeve_f'], cal, idx_[f_])
                w2 = {t: x * (1 - cut) for t, x in w.items()}
                w2[asset] = w2.get(asset, 0.0) + cut * sum(w.values()) + (1 - sum(w.values()))
                sc2.append((d_, w2))
            sc = sc2
        if (run.get('plan') or {}).get('gate'):
            rg_, sp_, a_ = run['plan']['gate']
            if rg_.startswith('rel'):
                # weak while the stock plan's trailing N-session return trails SPY's (optionally only at low rates)
                nrel = int(rg_[3:].split('_')[0])
                cvd = dict((c_[0], c_[1]) for c_ in run['curve'])
                spx_ = px_all['SPY']
                strong_ = {}
                for k_ in range(nrel, len(cal)):
                    a0, a1 = cal[k_ - nrel], cal[k_]
                    if cvd.get(a0) and cvd.get(a1) and spx_.get(a0) and spx_.get(a1):
                        lag = cvd[a1] / cvd[a0] < spx_[a1] / spx_[a0]
                        if rg_.endswith('_lr'):
                            lag = lag and not G['REG']['lowrate'].get(a1, True)
                        strong_[a1] = not lag
            elif rg_.startswith('eq'):
                nma = int(rg_[2:])
                cv = run['curve']
                strong_, acc = {}, []
                for i_, (d_, v_) in enumerate(cv):
                    acc.append(v_)
                    if len(acc) > nma:
                        acc.pop(0)
                    strong_[d_] = len(acc) < nma or v_ >= sum(acc) / nma
            else:
                strong_ = G['REG'][rg_]
            idx_ = {d_: i_ for i_, d_ in enumerate(cal)}
            sc2 = []
            for d_, w in sc:
                f_ = cal[idx_[d_] - 1]          # decided at the previous close
                if strong_.get(f_, True):
                    sc2.append((d_, w))
                    continue
                asset = best_of(P['sleeve_f'], cal, idx_[f_]) if a_ == 'best' else a_ if a_ in ('SPY', 'QQQ') else 'BIL'
                w2 = {t: x * sp_ for t, x in w.items()}
                w2[asset] = w2.get(asset, 0.0) + (1 - sp_) * sum(w.values()) + (1 - sum(w.values()))
                sc2.append((d_, w2))
            sc = sc2
        rot_ = (run.get('plan') or {}).get('rotate')
        if rot_:
            # default Boost; move 100% into TLT or GLD while that asset is in a higher-high/higher-low uptrend and
            # its trend strength (63/126-session log-price slope / volatility) beats SPY's (and a floor);
            # back to Boost when it makes a lower low (structure turns down)
            N_, thr_, tf_ = rot_.get('n', 63), rot_.get('thr', 1.0), rot_.get('tf', 'd')
            pool_ = rot_.get('assets', ('TLT', 'GLD'))
            idx_ = {d_: i_ for i_, d_ in enumerate(cal)}
            arr_ = {}
            cvs_ = dict((c_[0], c_[1]) for c_ in run['curve'])
            for t_ in ('SPY', '_STRAT') + tuple(pool_):
                src_ = cvs_ if t_ == '_STRAT' else px_all[t_]; a_, l_ = [], None
                for d_ in cal:
                    l_ = src_.get(d_) or l_; a_.append(l_)
                arr_[t_] = a_

            def strength(t_, k_):
                a_ = arr_[t_][k_ - N_ + 1:k_ + 1]
                if k_ < N_ or any(x is None for x in a_) or a_[0] is None:
                    return None
                ys = [math.log(x) for x in a_]; n_ = len(ys); xm = (n_ - 1) / 2; ym = sum(ys) / n_
                sl = sum((i_ - xm) * (y - ym) for i_, y in enumerate(ys)) / sum((i_ - xm) ** 2 for i_ in range(n_))
                r_ = [ys[i_] - ys[i_ - 1] for i_ in range(1, n_)]; mr = sum(r_) / len(r_)
                sd_ = (sum((x - mr) ** 2 for x in r_) / (len(r_) - 1)) ** 0.5
                return sl * 252 / (sd_ * math.sqrt(252)) if sd_ > 0 else None
            wk_cache = {}

            def wk_state(t_, d_):
                if (t_, d_) not in wk_cache:
                    src_b = D['bench']['SPY'] if t_ == 'SPY' else D['assets'].get(t_, [])
                    j_ = bisect_right([b_[0] for b_ in src_b] if t_ == 'SPY' else a_days.get(t_, []), d_)
                    bs_ = src_b[max(0, j_ - 900):j_]
                    wk, cur_ = [], None
                    for b_ in bs_:
                        key_ = date.fromisoformat(b_[0]).isocalendar()[:2]
                        if cur_ is None or key_ != cur_[0]:
                            cur_ = [key_, [b_[0], b_[1], b_[2], b_[3], b_[4]]]; wk.append(cur_)
                        else:
                            w_ = cur_[1]; w_[0] = b_[0]; w_[2] = max(w_[2], b_[2]); w_[3] = min(w_[3], b_[3]); w_[4] = b_[4]
                    wk_cache[(t_, d_)] = R.structure_signal([tuple(x[1]) for x in wk], n=2, lookback=2)['state']
                return wk_cache[(t_, d_)]

            def up_(t_, d_):
                return wk_state(t_, d_) == 'uptrend' if tf_ == 'w' else G['asset_up'](t_, d_)

            def lower_low(t_, d_):
                return wk_state(t_, d_) != 'uptrend' if tf_ == 'w' else not G['asset_up'](t_, d_)
            modes, mode_ = {}, 'boost'
            for k_ in range(1, len(cal)):
                f_ = cal[k_]
                if f_ < R.START:
                    continue
                if mode_ == 'boost':
                    sS = strength('_STRAT' if rot_.get('vs') == 'strat' else 'SPY', k_)
                    spy_st = (wk_state('SPY', f_) if rot_.get('spy_tf', 'w') == 'w' else ('downtrend' if G['spy_down'](f_) else 'other')) if rot_.get('spy_ll') else None
                    if (rot_.get('spy_weak') and wk_state('SPY', f_) == 'uptrend') or (rot_.get('spy_ll') and spy_st != 'downtrend'):
                        modes[f_] = mode_
                        continue
                    best_, bv = None, None
                    for t_ in pool_:
                        v_ = strength(t_, k_)
                        if v_ is None or v_ < thr_ or (sS is not None and v_ <= sS) or not up_(t_, f_):
                            continue
                        if bv is None or v_ > bv:
                            best_, bv = t_, v_
                    if best_:
                        mode_ = best_
                elif lower_low(mode_, f_):
                    mode_ = 'boost'
                modes[f_] = mode_
            G.setdefault('rot_modes', {})[key] = modes
            have = {d_ for d_, _ in sc}
            ws_ = []
            last_w = None
            sc_map = dict(sc)
            for d_ in cal:
                if d_ < sc[0][0]:
                    continue
                if d_ in sc_map:
                    last_w = sc_map[d_]
                f_ = cal[idx_[d_] - 1]
                m_ = modes.get(f_, 'boost')
                prev_m = modes.get(cal[idx_[f_] - 1], 'boost') if idx_[f_] > 0 else 'boost'
                if d_ in sc_map or m_ != prev_m:
                    ws_.append((d_, {m_: 1.0} if m_ != 'boost' else last_w))
            sc = ws_
            try:
                json.dump(modes, open(os.path.join(ROOT, 'data', f'rot_modes_{key}.json'), 'w'))
            except Exception:   # noqa: BLE001
                pass
        leg_ = (run.get('plan') or {}).get('legrot')
        if leg_:
            # gradient = slope of the current leg from the swing point that confirmed the trend:
            # uptrend -> from the last swing low to today; downtrend -> from the last swing high to today.
            # 'vol': divide by the asset's daily volatility so bonds, gold and stocks compare fairly.
            from mtl.structure import find_swings as _fs, label_structure as _ls, trend_state as _ts
            tfl, pool_ = leg_.get('tf', 'd'), leg_.get('assets', ('TLT', 'GLD'))
            idx_ = {d_: i_ for i_, d_ in enumerate(cal)}
            bars_src = {'SPY': D['bench']['SPY']}
            bars_src.update({t_: D['assets'][t_] for t_ in tuple(pool_) + tuple((leg_.get('major') or {}).get('pool', ())) if t_ in D['assets']})
            bdays = {t_: [b_[0] for b_ in bs_] for t_, bs_ in bars_src.items()}
            lcache = {}

            def weekly(bs_):
                wk, cur_ = [], None
                for b_ in bs_:
                    key_ = date.fromisoformat(b_[0]).isocalendar()[:2]
                    if cur_ is None or key_ != cur_[0]:
                        cur_ = [key_, [b_[0], b_[1], b_[2], b_[3], b_[4]]]; wk.append(cur_)
                    else:
                        w_ = cur_[1]; w_[0] = b_[0]; w_[2] = max(w_[2], b_[2]); w_[3] = min(w_[3], b_[3]); w_[4] = b_[4]
                return [tuple(x[1]) for x in wk]

            wex = {}
            labc = {}
            chc_ = {}

            def spy_in_channel(d_, cv):
                """SPY's close at or above (within tol under) the rising line through its last two weekly swing lows
                (the later one higher), projected to d_; False when the last two swing lows aren't rising."""
                key = (d_, cv.get('kind', 'chan'), cv.get('n', 2), cv.get('tol', 0.0), cv.get('near'), cv.get('span'))
                if key not in chc_:
                    j_ = bisect_right(bdays['SPY'], d_)
                    daily = [tuple(b_) for b_ in bars_src['SPY'][max(0, j_ - cv.get('look', 700)):j_]]
                    line_ = None
                    if cv.get('kind') == 'wbb':
                        # the weekly lower Bollinger band: 20-week average minus 2 standard deviations of weekly closes
                        w20 = [b_[4] for b_ in weekly(daily)[-20:]]
                        if len(w20) == 20:
                            m_ = sum(w20) / 20
                            line_ = m_ - 2 * (sum((x - m_) ** 2 for x in w20) / 20) ** 0.5
                    elif cv.get('kind') == 'wch':
                        # a true weekly channel (support and resistance lines, `span`+ weeks): its support line now
                        from chan_lines import find_channel as _fch2
                        ch_ = _fch2(weekly(daily), span=cv.get('span', 26))
                        line_ = ch_['low_now'] if ch_ else None
                    elif cv.get('kind') == 'bb':
                        # the lower Bollinger band: 20-day average minus 2 standard deviations of the closes
                        c20 = [b_[4] for b_ in daily[-20:]]
                        if len(c20) == 20:
                            m_ = sum(c20) / 20
                            line_ = m_ - 2 * (sum((x - m_) ** 2 for x in c20) / 20) ** 0.5
                    else:
                        bs_ = weekly(daily)
                        lo_ = [x for x in _fs(bs_, n=cv.get('n', 2)) if x['type'] == 'low']
                        if len(lo_) >= 2 and lo_[-1]['price'] > lo_[-2]['price']:
                            la_, lb_ = lo_[-2], lo_[-1]
                            sl_ = (math.log(lb_['price']) - math.log(la_['price'])) / max(1, lb_['i'] - la_['i'])
                            line_ = math.exp(math.log(lb_['price']) + sl_ * (len(bs_) - 1 - lb_['i']))
                    c_ = daily[-1][4]
                    # near: only within `near` above the line counts (None: anywhere above it)
                    chc_[key] = line_ is not None and c_ >= line_ * (1 - cv.get('tol', 0.0)) and (
                        cv.get('near') is None or c_ <= line_ * (1 + cv['near']))
                return chc_[key]

            def leg_lab_tf(t_, d_, tfu):
                if (t_, d_, tfu) not in labc:
                    j_ = bisect_right(bdays[t_], d_)
                    daily = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - (900 if tfu == 'w' else 320)):j_]]
                    bs_ = weekly(daily) if tfu == 'w' else daily
                    labc[(t_, d_, tfu)] = _ls(_fs(bs_, n=2 if tfu == 'w' else 3))
                return labc[(t_, d_, tfu)]

            def leg_lab(t_, d_):
                tfu = leg_.get('spy_tf2', tfl) if t_ == 'SPY' else leg_.get('asset_tf', tfl)
                if (t_, d_, tfu) not in labc:
                    j_ = bisect_right(bdays[t_], d_)
                    daily = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - (900 if tfu == 'w' else 320)):j_]]
                    bs_ = weekly(daily) if tfu == 'w' else daily
                    labc[(t_, d_, tfu)] = _ls(_fs(bs_, n=2 if tfu == 'w' else 3))
                return labc[(t_, d_, tfu)]

            def wk_exit(t_, d_):
                if (t_, d_) not in wex:
                    j_ = bisect_right(bdays[t_], d_)
                    daily = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - 900):j_]]
                    wb = weekly(daily)
                    wex[(t_, d_)] = _ts(_ls(_fs(wb, n=2)), lookback=2) != 'uptrend' if len(wb) > 10 else True
                return wex[(t_, d_)]

            def leg(t_, d_, tf_o=None):
                tfu = tf_o or (leg_.get('spy_tf2', tfl) if t_ == 'SPY' else leg_.get('asset_tf', tfl))
                if (t_, d_, tfu) not in lcache:
                    j_ = bisect_right(bdays[t_], d_)
                    daily = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - (900 if tfu == 'w' else 320)):j_]]
                    out_ = (None, None)
                    if len(daily) > 60:
                        bs_ = weekly(daily) if tfu == 'w' else daily
                        lab = _ls(_fs(bs_, n=2 if tfu == 'w' else 3))
                        st_ = _ts(lab, lookback=2)
                        piv = [x for x in lab if x['type'] == ('low' if st_ == 'uptrend' else 'high')]
                        if st_ in ('uptrend', 'downtrend') and piv and (leg_.get('slope') != 'pts' or len(piv) >= 2):
                            if leg_.get('slope') == 'pts':      # line through the last two higher lows / lower highs
                                p0, pv = piv[-2], piv[-1]
                                ndays = max(1, (date.fromisoformat(pv['ts'][:10]) - date.fromisoformat(p0['ts'][:10])).days * 252 / 365)
                                g_ = math.log(pv['price'] / p0['price']) / ndays
                            else:
                                pv = piv[-1]
                                ndays = max(1, (date.fromisoformat(daily[-1][0]) - date.fromisoformat(pv['ts'][:10])).days * 252 / 365)
                                g_ = math.log(daily[-1][4] / pv['price']) / ndays
                            if leg_.get('vol'):
                                rr = [math.log(daily[i_][4] / daily[i_ - 1][4]) for i_ in range(len(daily) - 63, len(daily))]
                                mr = sum(rr) / len(rr); sdv = (sum((x - mr) ** 2 for x in rr) / (len(rr) - 1)) ** 0.5
                                g_ = g_ / sdv if sdv > 0 else 0.0
                            out_ = (st_, g_)
                        else:
                            out_ = (st_, None)
                    lcache[(t_, d_, tfu)] = out_
                return lcache[(t_, d_, tfu)]
            rgx_ = {}
            if leg_.get('rg_conf') is not None or leg_.get('rg_boost'):
                # rate/gold regime: 10-year yield and gold each up or down over rg_n sessions
                tnx_ = {b_[0]: b_[4] for b_ in json.load(open(os.path.join(SIDE_, 'rates/tnx.json')))['^TNX'] if b_[4]}
                gl_ = {b_[0]: b_[4] for b_ in bars_src['GLDX']}
                rn_ = leg_.get('rg_n', 63); ly_ = lg_ = None; hy_, hg_ = [], []
                for d_ in cal:
                    ly_ = tnx_.get(d_, ly_); lg_ = gl_.get(d_, lg_); hy_.append(ly_); hg_.append(lg_)
                for k_, d_ in enumerate(cal):
                    if k_ >= rn_ and hy_[k_] and hy_[k_ - rn_] and hg_[k_] and hg_[k_ - rn_]:
                        rgx_[d_] = ('r' if hy_[k_] > hy_[k_ - rn_] else 'f') + ('u' if hg_[k_] > hg_[k_ - rn_] else 'd')
            thr_ = leg_.get('thr', 0.0)
            pk_ = leg_.get('pick')      # (where, n, qualify): choose TLT/GLD by % change over n sessions instead of the gradient
            cix_ = {d_: i_ for i_, d_ in enumerate(cal)}

            def pchg(t_, d_, n_):
                k_ = cix_.get(d_)
                if k_ is None or k_ < n_:
                    return None
                a_, b_ = (px_all.get(t_) or {}).get(cal[k_ - n_]), (px_all.get(t_) or {}).get(d_)
                return b_ / a_ - 1 if a_ and b_ else None
            zsd_ = {}

            def zret(t_, d_, n_):
                # log change over n_ sessions in units of the asset's normal move: its daily volatility over the
                # 252 sessions before the window, times sqrt(n_)
                k_ = cix_.get(d_)
                if k_ is None or k_ < n_ + 253:
                    return None
                if t_ not in zsd_:
                    p_ = px_all.get(t_) or {}; cs_, last_ = [], None
                    for d2 in cal:
                        last_ = p_.get(d2) or last_; cs_.append(last_)
                    lr_ = [0.0] + [math.log(cs_[i] / cs_[i - 1]) if cs_[i] and cs_[i - 1] else 0.0 for i in range(1, len(cs_))]
                    c1_, c2_ = [0.0], [0.0]
                    for x_ in lr_:
                        c1_.append(c1_[-1] + x_); c2_.append(c2_[-1] + x_ * x_)
                    zsd_[t_] = (cs_, c1_, c2_)
                cs_, c1_, c2_ = zsd_[t_]
                a_, b_ = cs_[k_ - n_], cs_[k_]
                if not a_ or not b_:
                    return None
                j1, j0 = k_ - n_ + 1, k_ - n_ - 251
                s1, s2 = c1_[j1] - c1_[j0], c2_[j1] - c2_[j0]
                var_ = (s2 - s1 * s1 / 252) / 251
                return math.log(b_ / a_) / (math.sqrt(var_ * n_)) if var_ > 0 else None
            if leg_.get('rg_z'):
                # rate/gold regime as a relative move: gold's scored move minus long Treasuries' above k
                nz_, kz_ = leg_['rg_z']
                rgx_ = {}
                for d_ in cal:
                    zg_, zt_ = zret('GLDX', d_, nz_), zret('TLTX', d_, nz_)
                    if zg_ is not None and zt_ is not None:
                        rgx_[d_] = 'ru' if zg_ - zt_ > kz_ else 'xx'
            conf_n, cool_n, spy_dd_ = leg_.get('confirm', 0), leg_.get('cool', 0), leg_.get('spy_dd', 0.0)
            min_lows = leg_.get('min_lows', 2)
            spyc_ = [px_all['SPY'].get(d_) for d_ in cal]
            lowcache = {}

            def rising_lows(t_, d_):
                # how many swing lows in a row are higher (daily structure)
                if (t_, d_) not in lowcache:
                    j_ = bisect_right(bdays[t_], d_)
                    daily = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - 320):j_]]
                    lows = [x['price'] for x in _fs(daily, n=3) if x['type'] == 'low'] if len(daily) > 30 else []
                    c_ = 1
                    for a_, b_ in zip(lows[-2::-1], lows[::-1]):
                        if b_ > a_:
                            c_ += 1
                        else:
                            break
                    lowcache[(t_, d_)] = c_ if lows else 0
                return lowcache[(t_, d_)]
            exit_tf = leg_.get('exit_tf', tfl)
            streak, cand_prev, cool_left = 0, None, 0
            gap_n = 0      # sessions in a row SPY has been out of its downtrend
            modes, mode_ = {}, 'boost'
            for k_ in range(1, len(cal)):
                f_ = cal[k_]
                if f_ < R.START:
                    continue
                if cool_left > 0:
                    cool_left -= 1
                if mode_ == 'boost' and (cool_left > 0 or (spy_dd_ and spyc_[k_] and max(x for x in spyc_[max(0, k_ - 252):k_ + 1] if x) and
                                                           spyc_[k_] / max(x for x in spyc_[max(0, k_ - 252):k_ + 1] if x) - 1 > -spy_dd_)):
                    streak = 0
                    modes[f_] = mode_
                    continue
                if leg_.get('spyout'):
                    # out of stocks while SPY is in a confirmed downtrend; dest: BIL, TLTX, or the steepest uptrending of TLT/GLD (else BIL)
                    sst = leg('SPY', f_)[0]
                    below_ = None
                    if leg_.get('ma150'):
                        w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                        below_ = len(w150) == 150 and spyc_[k_] < sum(w150) / 150
                    if leg_.get('lh150') and sst == 'downtrend':
                        # the last lower high itself sits below the 150-day average
                        lab_ = leg_lab('SPY', f_)
                        his = [x for x in lab_ if x['type'] == 'high']
                        k_h = idx_.get(his[-1]['ts'][:10]) if his else None
                        w150 = [x for x in spyc_[max(0, (k_h or 0) - 149):(k_h or 0) + 1] if x] if k_h else []
                        lh_ok = bool(his) and len(w150) == 150 and his[-1]['price'] < sum(w150) / 150
                    else:
                        lh_ok = True
                    if mode_ == 'boost':
                        cond = sst == 'downtrend' and lh_ok and (below_ is None or below_)
                        streak = streak + 1 if cond else 0
                        go = streak > conf_n
                    elif leg_.get('back') == 'ma':
                        go = bool(below_)
                    else:
                        go = (sst == 'downtrend') if leg_.get('back') != 'up' else (sst != 'uptrend')
                    if go:
                        dest = leg_['spyout']
                        if dest == 'best':
                            best_, bv = 'BIL', None
                            for t_ in pool_:
                                ast, ag = leg(t_, f_)
                                if ast == 'uptrend' and ag is not None and ag > 0 and (bv is None or ag > bv):
                                    best_, bv = t_, ag
                            dest = best_
                        mode_ = dest
                    else:
                        mode_ = 'boost'
                    modes[f_] = mode_
                    continue
                if mode_ == 'boost':
                    sst, sg = leg('SPY', f_)
                    if leg_.get('spy_pct'):
                        # SPY down over spy_pct sessions instead of a daily lower-high/lower-low downtrend
                        c_ = pchg('SPY', f_, leg_['spy_pct'])
                        if c_ is None or c_ >= -leg_.get('spy_pct_th', 0.0):
                            modes[f_] = mode_
                            continue
                    else:
                        if not (leg_.get('spy_free') or sst != 'uptrend'):
                            if leg_.get('conf_gap') is not None:
                                # the count starts over once SPY has been out of its downtrend more than conf_gap sessions in a row
                                gap_n += 1
                                if gap_n > leg_['conf_gap']:
                                    streak, cand_prev = 0, None
                            modes[f_] = mode_
                            continue
                        if leg_.get('spy_down') and sst != 'downtrend':
                            if leg_.get('conf_gap') is not None:
                                # the count starts over once SPY has been out of its downtrend more than conf_gap sessions in a row
                                gap_n += 1
                                if gap_n > leg_['conf_gap']:
                                    streak, cand_prev = 0, None
                            modes[f_] = mode_
                            continue
                    best_, bv = None, None
                    for t_ in pool_:
                        ast, ag = leg(t_, f_)
                        if leg_.get('relz'):
                            # qualify when the asset's scored move beats SPY's by more than k (SPY falling more than
                            # normal relative to the asset), optionally still needing the asset's own uptrend
                            za_, zs_ = zret(t_, f_, leg_['relz'][0]), zret('SPY', f_, leg_['relz'][0])
                            if (leg_.get('relz_up', True) and ast != 'uptrend') or za_ is None or zs_ is None or za_ - zs_ <= leg_['relz'][1]:
                                continue
                        elif pk_ and pk_[0] in ('rot', 'both') and len(pk_) > 2 and pk_[2]:
                            # qualify by % change: in an uptrend, up over n sessions, and up more than SPY
                            pc_, ps_ = pchg(t_, f_, pk_[1]), pchg('SPY', f_, pk_[1])
                            if ast != 'uptrend' or pc_ is None or pc_ <= 0 or (ps_ is not None and pc_ <= ps_):
                                continue
                        elif ast != 'uptrend' or ag is None or ag <= thr_ or (sg is not None and ag <= sg):
                            continue
                        if min_lows > 2 and rising_lows(t_, f_) < min_lows:
                            continue
                        key_ = (zret if leg_.get('pick_z') else pchg)(t_, f_, pk_[1]) if pk_ and pk_[0] in ('rot', 'both') else ag
                        if key_ is None:
                            continue
                        if bv is None or key_ > bv:
                            best_, bv = t_, key_
                    gap_n = 0
                    if leg_.get('any_lead'):
                        # count the sessions gold or bonds leads, whichever it is, and switch into the leader of the day
                        streak = streak + 1 if best_ and cand_prev else (1 if best_ else 0)
                    else:
                        streak = streak + 1 if best_ and best_ == cand_prev else (1 if best_ else 0)
                    cand_prev = best_
                    cn_ = conf_n
                    if leg_.get('rg_conf') is not None and rgx_.get(f_, '')[:len(leg_.get('rg_fear', 'fu'))] == leg_.get('rg_fear', 'fu'):
                        cn_ = leg_['rg_conf']      # fear regime: shorter wait to switch into TLT/GLD
                    if leg_.get('conf_below') is not None:
                        w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                        if len(w150) == 150 and spyc_[k_] < sum(w150) / 150:
                            cn_ = leg_['conf_below']      # shorter wait while SPY is under its 150-day average
                    cv_ = leg_.get('chveto')
                    if best_ and streak > cn_ and cv_ and spy_in_channel(f_, cv_):
                        pass       # SPY still at or above its rising channel's bottom line: stay in stocks
                    elif best_ and streak > cn_:
                        mode_, streak = best_, 0
                    wc_ = leg_.get('wait_cash')
                    if mode_ == 'boost' and wc_ and (wc_ == 'down' or best_):
                        w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                        if not leg_.get('wait150') or (len(w150) == 150 and spyc_[k_] < sum(w150) / 150):
                            modes[f_] = 'BIL'          # out of stocks into cash while the switch is being confirmed
                            continue
                else:
                    if exit_tf == 'w' and tfl != 'w':
                        gone = wk_exit(mode_, f_)
                    else:
                        gone = leg(mode_, f_)[0] != 'uptrend'
                    if gone:
                        mode_, cool_left = 'boost', cool_n
                modes[f_] = mode_
            ov_ = leg_.get('overlay')
            if ov_:
                # out of stocks while SPY's weekly downtrend has its last lower high under the 150-day and SPY is under it;
                # back when SPY shows higher highs (ov_['back_tf']) with a slope steeper than TLT/GLD, or SPY closes above the 150-day
                on_, final, bridge_on, fast_ = False, {}, False, False
                cur_, cstreak, ccand = None, 0, None
                stay_ = None

                def pchg_(t_, k_, n_):   # % change of t_ over n_ sessions to cal[k_]
                    a_, b_ = (px_all.get(t_) or {}).get(cal[k_ - n_]) if k_ >= n_ else None, (px_all.get(t_) or {}).get(cal[k_])
                    return b_ / a_ - 1 if a_ and b_ else None
                for k_ in range(1, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START:
                        continue
                    w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                    below = len(w150) == 150 and spyc_[k_] < sum(w150) / 150
                    if not on_ and ov_.get('trig') in ('ll2', 'll2|slow'):
                        # two lower lows in a row on SPY's chart (ll_tf) while SPY closes below its 150-day average
                        labx = leg_lab_tf('SPY', f_, ov_.get('ll_tf', 'd'))
                        lows_ = [x for x in labx if x['type'] == 'low' and x['label']]
                        on_ = below and len(lows_) >= 2 and lows_[-1]['label'] == 'LL' and lows_[-2]['label'] == 'LL'
                        bridge_on = False
                    tg_ = (ov_.get('trig') or '').split('|')[0]
                    if not on_ and below and tg_ == 'brk':
                        # close below the last confirmed swing low (a break of structure) while under the 150-day
                        lws = [x for x in leg_lab_tf('SPY', f_, ov_.get('brk_tf', 'd')) if x['type'] == 'low']
                        on_ = bool(lws) and spyc_[k_] < (min(x['price'] for x in lws[-2:]) if ov_.get('brk2') else lws[-1]['price'])
                        bridge_on, fast_ = False, on_
                    if not on_ and below and tg_ == 'don':
                        # close below the lowest close of the previous don_n sessions while under the 150-day
                        prv = [x for x in spyc_[max(0, k_ - ov_['don_n']):k_] if x]
                        on_ = len(prv) == ov_['don_n'] and spyc_[k_] < min(prv)
                        bridge_on, fast_ = False, on_
                    if not on_ and below and tg_ == 'big':
                        # a down day bigger than big_k x SPY's 63-day daily volatility while under the 150-day
                        rr = [math.log(spyc_[i_] / spyc_[i_ - 1]) for i_ in range(k_ - 62, k_ + 1) if spyc_[i_] and spyc_[i_ - 1]]
                        mr = sum(rr) / len(rr); sdv = (sum((x - mr) ** 2 for x in rr) / (len(rr) - 1)) ** 0.5
                        on_ = rr[-1] < -ov_['big_k'] * sdv
                        bridge_on, fast_ = False, on_
                    if not on_ and tg_ == 'vol' and (below or not ov_.get('vol_150', True)):
                        # heavy selling: a down day (at least vol_dn) on volume vol_k x or more its 50-day average
                        if 'SPYV' not in G:
                            G['SPYV'] = json.load(open(os.path.join(SIDE_, 'spy_volume.json')))['SPY']
                        sv_ = G['SPYV']
                        vv = [sv_.get(cal[i_]) for i_ in range(k_ - 50, k_)]
                        vv = [x for x in vv if x]
                        v0 = sv_.get(f_)
                        dn = spyc_[k_] / spyc_[k_ - 1] - 1 if spyc_[k_ - 1] else 0
                        on_ = bool(v0 and len(vv) >= 40) and dn < -ov_.get('vol_dn', 0.0) and v0 >= ov_['vol_k'] * sum(vv) / len(vv)
                        bridge_on, fast_ = False, on_
                    if not on_ and tg_ == 'rsi' and below:
                        # RSI(14) broke a support line through 3-4 of its swing lows within the last rsi_w sessions,
                        # and SPY now closes below its 150-day average
                        ck_ = ('RSIBRK', ov_.get('rsi_pts', 4), ov_.get('rsi_tol', 2.5))
                        if ck_ not in G:
                            import importlib.util as _iu
                            _sp = _iu.spec_from_file_location('rsi_line', os.path.join(os.environ.get('NIBII_REPO', '/home/user/NIBII'), 'mtl', 'rsi_line.py'))
                            _m = _iu.module_from_spec(_sp); _sp.loader.exec_module(_m)
                            cl_ = [x if x else 0.0 for x in spyc_]
                            G[ck_] = sorted(_m.support_breaks(_m.rsi(cl_), pts=ck_[1], tol=ck_[2]))
                        bl_ = G[ck_]
                        j_ = bisect_right(bl_, k_) - 1
                        on_ = j_ >= 0 and k_ - bl_[j_] <= ov_.get('rsi_w', 20)
                        bridge_on, fast_ = False, on_
                    if not on_ and tg_ == 'xdev' and (below or not ov_.get('x150', True)):
                        # stress: SPY's down move over the last xw sessions is a big deviation (x_k x its 63-day daily
                        # volatility) and TLT or GLD moved a big deviation too (x_a x its own volatility, up or either way)
                        if 'XZ' not in G:
                            zz = {}
                            for t_ in ['SPY'] + list(pool_):
                                cm_ = {b_[0][:10]: b_[4] for b_ in bars_src[t_]}
                                cs_ = [cm_.get(d2) for d2 in cal]
                                for i_ in range(1, len(cs_)):
                                    if cs_[i_] is None:
                                        cs_[i_] = cs_[i_ - 1]
                                rr_ = [math.log(cs_[i_] / cs_[i_ - 1]) if cs_[i_] and cs_[i_ - 1] else 0.0 for i_ in range(len(cs_))]
                                z_ = [0.0] * len(cs_)
                                for i_ in range(64, len(cs_)):
                                    w_r = rr_[i_ - 63:i_]
                                    m_r = sum(w_r) / 63; sd_r = (sum((x - m_r) ** 2 for x in w_r) / 62) ** 0.5
                                    z_[i_] = rr_[i_] / sd_r if sd_r > 0 else 0.0
                                zz[t_] = z_
                            G['XZ'] = zz
                        zz = G['XZ']
                        xw = ov_.get('xw', 1)
                        sdn = any(zz['SPY'][i_] < -ov_['x_k'] for i_ in range(k_ - xw + 1, k_ + 1))
                        if ov_.get('x_up'):
                            adv = any(zz[t_][i_] > ov_['x_a'] for t_ in pool_ for i_ in range(k_ - xw + 1, k_ + 1))
                        else:
                            adv = any(abs(zz[t_][i_]) > ov_['x_a'] for t_ in pool_ for i_ in range(k_ - xw + 1, k_ + 1))
                        on_ = sdn and adv
                        bridge_on, fast_ = False, on_
                    if not on_ and tg_ == 'ma20w':
                        # SPY's 20-week average (weekly closes, this week's close = today's) is falling vs last week
                        if 'WKC' not in G:
                            wk_, kl_ = {}, []
                            for i_, d2 in enumerate(cal):
                                kk = date.fromisoformat(d2).isocalendar()[:2]
                                if not kl_ or kl_[-1][0] != kk:
                                    kl_.append([kk, i_])
                                else:
                                    kl_[-1][1] = i_
                                wk_[i_] = len(kl_) - 1
                            G['WKC'] = (wk_, [x[1] for x in kl_])
                        wk_, wl_ = G['WKC']
                        w_ = wk_[k_]
                        nw = ov_.get('ma_w', 20)
                        if w_ >= nw + ov_.get('ma_fall', 1):
                            prevs = [spyc_[wl_[j]] for j in range(w_ - nw - ov_.get('ma_fall', 1) + 1, w_)]
                            cur = prevs + [spyc_[k_]]
                            if all(cur):
                                mas = [sum(cur[j:j + nw]) / nw for j in range(len(cur) - nw + 1)]
                                on_ = all(mas[j + 1] < mas[j] for j in range(len(mas) - 1))
                                if on_ and ov_.get('ma_below'):
                                    on_ = spyc_[k_] < mas[-1]
                                if on_ and ov_.get('ma_150'):
                                    on_ = below
                                if on_ and ov_.get('wk_red'):
                                    # the weekly candle is red: last completed week ('last') or this week so far ('cur')
                                    if 'WKO' not in G:
                                        so_ = {b_[0][:10]: b_[1] for b_ in bars_src['SPY']}
                                        wo_ = {}
                                        for i_, d2 in enumerate(cal):
                                            wo_.setdefault(wk_[i_], so_.get(d2))
                                        G['WKO'] = wo_
                                    wo_ = G['WKO']
                                    if ov_['wk_red'] == 'last':
                                        o_, c_ = wo_.get(w_ - 1), spyc_[wl_[w_ - 1]]
                                    else:
                                        o_, c_ = wo_.get(w_), spyc_[k_]
                                    on_ = bool(o_ and c_) and c_ < o_
                                if on_ and ov_.get('d_ll'):
                                    # SPY's daily chart has just made a lower low
                                    lws = [x for x in leg_lab_tf('SPY', f_, 'd') if x['type'] == 'low' and x['label']]
                                    on_ = bool(lws) and lws[-1]['label'] == 'LL'
                        bridge_on = False
                        if on_:
                            cur_, cstreak, ccand = None, 0, None
                    if not on_ and ov_.get('spy_pct'):
                        # SPY under its 150-day and down over spy_pct sessions, falling slowly (per-session log change / daily sd)
                        c_ = pchg_('SPY', k_, ov_['spy_pct'])
                        on_ = bool(below) and c_ is not None and c_ < 0
                        bridge_on = False
                        if on_ and ov_.get('slow') is not None:
                            rr = [math.log(spyc_[i_] / spyc_[i_ - 1]) for i_ in range(k_ - 62, k_ + 1) if spyc_[i_] and spyc_[i_ - 1]]
                            mr = sum(rr) / len(rr); sdv = (sum((x - mr) ** 2 for x in rr) / (len(rr) - 1)) ** 0.5
                            on_ = sdv > 0 and abs(math.log(1 + c_) / ov_['spy_pct'] / sdv) < ov_['slow']
                    elif not on_ and ov_.get('trig') not in ('ll2', 'brk', 'don', 'big', 'vol', 'rsi', 'ma20w', 'xdev'):
                        sst = leg('SPY', f_, 'w')[0]
                        if sst == 'downtrend' and below:
                            lab_ = leg_lab_tf('SPY', f_, 'w')
                            his = [x for x in lab_ if x['type'] == 'high']
                            k_h = idx_.get(his[-1]['ts'][:10]) if his else None
                            wh = [x for x in spyc_[max(0, (k_h or 0) - 149):(k_h or 0) + 1] if x] if k_h else []
                            on_ = bool(his) and len(wh) == 150 and his[-1]['price'] < sum(wh) / 150
                            bridge_on = False
                            if on_ and ov_.get('slow') is not None:
                                # slow decline: the line through the last two lower lows falls gently (per session, / SPY's daily swing)
                                los = [x for x in lab_ if x['type'] == 'low']
                                if len(los) >= 2:
                                    nd_ = max(1, (date.fromisoformat(los[-1]['ts'][:10]) - date.fromisoformat(los[-2]['ts'][:10])).days * 252 / 365)
                                    sl_ = math.log(los[-1]['price'] / los[-2]['price']) / nd_
                                    rr = [math.log(spyc_[i_] / spyc_[i_ - 1]) for i_ in range(k_ - 62, k_ + 1) if spyc_[i_] and spyc_[i_ - 1]]
                                    mr = sum(rr) / len(rr); sdv = (sum((x - mr) ** 2 for x in rr) / (len(rr) - 1)) ** 0.5
                                    on_ = sdv > 0 and abs(sl_ / sdv) < ov_['slow']
                                else:
                                    on_ = False
                    else:
                        wq = [x for x in spyc_[max(0, k_ - ov_.get('back_n', 20) + 1):k_ + 1] if x]
                        if fast_ and ov_.get('back_n') and spyc_[k_] > sum(wq) / len(wq):
                            on_, fast_ = False, False      # a sharp-drop exit ends once SPY closes back above its short average
                        elif fast_ and ov_.get('back_n'):
                            pass                            # a sharp-drop exit waits for the short-average recovery only
                        elif not below and ov_.get('back150', True):
                            on_ = False
                        elif ov_.get('back_pct'):
                            # back when SPY is up more than TLT and GLD over back_pct sessions
                            sp_ = pchg_('SPY', k_, ov_['back_pct'])
                            ot_ = [pchg_(t_, k_, ov_['back_pct']) for t_ in pool_]
                            if sp_ is not None and sp_ > 0 and all(o is None or sp_ > o for o in ot_):
                                on_ = False
                        else:
                            sst, sg = leg('SPY', f_, ov_.get('back_tf', 'd'))
                            steep = False
                            if sst == 'uptrend' and sg is not None and sg > 0:
                                others = [leg(t_, f_)[1] for t_ in pool_ if leg(t_, f_)[0] == 'uptrend']
                                steep = all(o is None or sg > o for o in others)
                            if ov_.get('bridge'):
                                bridge_on = steep          # hold SPY while its higher lows are steeper; full Boost only above the 150-day
                            elif steep:
                                on_ = False
                    if on_ and ov_.get('bridge') and bridge_on:
                        final[f_] = ov_['bridge']
                        continue
                    if on_ and tg_ == 'ma20w' and ov_.get('ma_up_exit'):
                        w_ = G['WKC'][0][k_]; wl_ = G['WKC'][1]; nw = ov_.get('ma_w', 20)
                        cur = [spyc_[wl_[j]] for j in range(w_ - nw, w_)] + [spyc_[k_]]
                        if all(cur) and sum(cur[1:]) > sum(cur[:-1]):
                            on_ = False
                    if on_ and ov_.get('confirm_out'):
                        # hold a rising asset only after it has led confirm_out sessions; cash meanwhile; back to cash if it breaks
                        if cur_ and leg(cur_, f_)[0] != 'uptrend':
                            cur_ = None
                        if not cur_:
                            bt, bv = None, None
                            for t_ in pool_:
                                ast, ag = leg(t_, f_)
                                if ast == 'uptrend' and ag is not None and ag > 0 and (bv is None or ag > bv):
                                    bt, bv = t_, ag
                            cstreak = cstreak + 1 if bt and bt == ccand else (1 if bt else 0)
                            ccand = bt
                            if bt and cstreak >= ov_['confirm_out']:
                                cur_ = bt
                        final[f_] = cur_ or 'BIL'
                        continue
                    if on_ and fast_ and tg_ == 'xdev':
                        final[f_] = 'BIL'
                        continue
                    if not on_:
                        stay_ = None
                    if on_ and ov_.get('dest') == 'pct':
                        # the biggest % gain over pn sessions among TLT, GLD and SPY (SPY -> stay in the Boost list); none up -> BIL
                        if ov_.get('stay') and stay_:
                            final[f_] = stay_
                            continue
                        dest, bv = 'BIL', 0.0
                        for t_ in tuple(pool_) + ('SPY',):
                            if ov_.get('nodown') and leg(t_, f_, 'w')[0] == 'downtrend':
                                continue
                            x_ = pchg_(t_, k_, ov_['pn'])
                            if x_ is not None and x_ > bv:
                                dest, bv = t_, x_
                        dest = 'boost' if dest == 'SPY' else dest
                        stay_ = dest
                        final[f_] = dest
                        continue
                    if on_:
                        dest = 'BIL'
                        if ov_.get('dest') == 'best':
                            bv = None
                            for t_ in pool_:
                                ast, ag = leg(t_, f_)
                                if pk_ and pk_[0] in ('ov', 'both'):
                                    pc_ = (zret if leg_.get('pick_z') else pchg)(t_, f_, pk_[1])
                                    if ast == 'uptrend' and pc_ is not None and pc_ > 0 and (bv is None or pc_ > bv):
                                        dest, bv = t_, pc_
                                elif ast == 'uptrend' and ag is not None and ag > 0 and (bv is None or ag > bv):
                                    dest, bv = t_, ag
                        final[f_] = dest
                    else:
                        final[f_] = modes.get(f_, 'boost') if not ov_.get('no_rot') else 'boost'
                modes = final
            stk_ = lambda m_: m_ == 'boost' or str(m_).startswith('SIDE')
            rg2_ = leg_.get('regate')
            if rg2_:
                # re-entry gate: a return from TLT / GLD / T-bills to the Boost list waits while SPY closes below its 150-day
                # average ('ma'), its last daily swing high is lower than the one before ('dlh'), or either ('either');
                # meanwhile hold plain cash ('cash'), T-bills ('bil', swapped by the no-T-bills rule) or the asset it was in ('stay')
                def _blocked(k_, f_):
                    c_ = False
                    if rg2_['when'] in ('ma', 'either'):
                        w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                        c_ = len(w150) == 150 and spyc_[k_] < sum(w150) / 150
                    if not c_ and rg2_['when'] in ('dlh', 'either'):
                        his_ = [x for x in leg_lab_tf('SPY', f_, 'd') if x['type'] == 'high']
                        c_ = len(his_) >= 2 and his_[-1]['price'] < his_[-2]['price']
                    return c_
                prev_, n_g = 'boost', 0
                for k_, f_ in enumerate(cal):
                    if f_ not in modes:
                        continue
                    if stk_(modes[f_]) and not stk_(prev_) and _blocked(k_, f_):
                        modes[f_] = {'cash': 'CASH0', 'bil': 'BIL', 'stay': prev_}[rg2_['hold']]
                        n_g += 1
                    prev_ = modes[f_]
                R.log(f"  {key} re-entry gate held {n_g} sessions")
            mh_ = leg_.get('minhold')
            if mh_:
                # after a switch between the Boost list and TLT / GLD / T-bills, stay at least mh_ sessions before switching back
                prev_, last_sw, n_h = None, -10 ** 9, 0
                for k_, f_ in enumerate(cal):
                    if f_ not in modes:
                        continue
                    if prev_ is not None and stk_(modes[f_]) != stk_(prev_):
                        if k_ - last_sw < mh_:
                            modes[f_] = prev_
                            n_h += 1
                        else:
                            last_sw = k_
                    prev_ = modes[f_]
                R.log(f"  {key} minimum hold kept {n_h} sessions")
            cap_ = leg_.get('cap')
            if cap_:
                # capitulation re-entry: SPY/QQQ falls k x its 63-day daily volatility (or more) on vol x its 50-day average
                # volume; `delay` sessions later, if the plan is out of stocks, it goes back to the Boost list for `hold` sessions
                if 'SPYV' not in G or 'QQQ' not in G['SPYV']:
                    G['SPYV'] = json.load(open(os.path.join(SIDE_, 'spy_volume.json')))
                vs_ = G['SPYV'][cap_.get('src', 'SPY')]
                pxs_ = {b_[0]: b_[4] for b_ in D['bench'][cap_.get('src', 'SPY')]}
                cl_ = [pxs_.get(d_) for d_ in cal]
                vv_ = [vs_.get(d_) for d_ in cal]
                ev_ = []
                for k_ in range(64, len(cal)):
                    if not (cl_[k_] and cl_[k_ - 1] and vv_[k_]):
                        continue
                    rr_ = [math.log(cl_[i_] / cl_[i_ - 1]) for i_ in range(k_ - 63, k_) if cl_[i_] and cl_[i_ - 1]]
                    if len(rr_) < 50:
                        continue
                    mr_ = sum(rr_) / len(rr_); sd_ = (sum((x - mr_) ** 2 for x in rr_) / (len(rr_) - 1)) ** 0.5
                    w_ = [x for x in vv_[k_ - 50:k_] if x]
                    if len(w_) < 40:
                        continue
                    dn_ = math.log(cl_[k_] / cl_[k_ - 1])
                    if dn_ <= -cap_['k'] * sd_ and vv_[k_] >= cap_['vol'] * sum(w_) / len(w_):
                        ev_.append(k_)
                force_ = set()
                for k_ in ev_:
                    j_ = k_ + cap_['delay']
                    if j_ < len(cal) and modes.get(cal[j_], 'boost') != 'boost':
                        for i_ in range(j_, min(len(cal), j_ + cap_['hold'])):
                            force_.add(cal[i_])
                json.dump([(cal[k_], cal[min(len(cal) - 1, k_ + cap_['delay'])], modes.get(cal[min(len(cal) - 1, k_ + cap_['delay'])], 'boost')) for k_ in ev_ if cal[k_] >= R.START],
                          open(os.path.join(ROOT, 'data', f"cap_log_{key}{os.environ.get('TAG', '')}.json"), 'w'))
                for d_ in force_:
                    if d_ in modes:
                        modes[d_] = 'boost'
                if os.environ.get('DUMP_MODES'):
                    json.dump(dict(modes=modes, bars={t_: bars_src[t_] for t_ in bars_src}), open(os.path.join(ROOT, 'data', f'leg_modes_{key}.json'), 'w'))
            wq_ = leg_.get('warnq')
            if wq_:
                # downtrend warning as a trade: SPY's daily structure down, SPY below its 150-day, TLT or GLD rising ->
                # (after `conf` sessions) move `out` of the Boost list into TLT+GLD (wq_['dest']: 'duo' = half each,
                # 'rising' = split among the rising ones, T-bills if none); back when SPY closes above its 150-day
                # (or, back='up', also when SPY's daily structure turns up)
                on_, cnt_, n_on = False, 0, 0
                for k_ in range(1, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START:
                        continue
                    w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                    below = len(w150) == 150 and spyc_[k_] < sum(w150) / 150
                    sst = leg('SPY', f_)[0]
                    rising = [t_ for t_ in pool_ if leg(t_, f_)[0] == 'uptrend']
                    if not on_:
                        tg_ = wq_.get('trig', 'd')
                        if tg_ == 'w':
                            cond = below and leg('SPY', f_, 'w')[0] == 'downtrend' and bool(rising)
                        elif tg_ == 'big':
                            pk_ = max(x for x in spyc_[max(0, k_ - 252):k_ + 1] if x)
                            cond = below and sst == 'downtrend' and bool(rising) and spyc_[k_] / pk_ - 1 <= -wq_.get('off', 0.10)
                        elif tg_ == 'broad':
                            # the selloff is broad: at least `bth` of S&P 500 members fell 10%+ over the last 20 sessions
                            if 'BREADTH' not in G:
                                G['BREADTH'] = json.load(open(os.path.join(SIDE_, 'breadth_series.json')))
                            cond = below and sst == 'downtrend' and bool(rising) and G['BREADTH'].get(f_, 0.0) >= wq_.get('bth', 0.20)
                        elif tg_ == 'fresh':
                            # the blind-test pattern: go out only while the drop is still fresh (SPY's 63-session
                            # return above -fr), stay once it has already fallen that much
                            r63_ = spyc_[k_] / spyc_[k_ - 63] - 1 if k_ >= 63 and spyc_[k_ - 63] else 0.0
                            cond = below and sst == 'downtrend' and bool(rising) and r63_ > -wq_.get('fr', 0.026)
                        elif tg_ == 'brk':
                            lws_ = [x for x in leg_lab_tf('SPY', f_, 'd') if x['type'] == 'low']
                            cond = below and bool(rising) and bool(lws_) and spyc_[k_] < lws_[-1]['price']
                        else:
                            cond = below and sst == 'downtrend' and bool(rising)
                        if wq_.get('noreset'):
                            cnt_ = cnt_ + 1 if (cond or (cnt_ and below)) else 0
                        else:
                            cnt_ = cnt_ + 1 if cond else 0
                        on_ = cnt_ > wq_.get('conf', 0)
                    else:
                        bk_ = wq_.get('back')
                        back_ = not below or (bk_ == 'up' and sst == 'uptrend')
                        if bk_ == 'hl':     # SPY's latest daily swing low is a higher low
                            lws_ = [x for x in leg_lab_tf('SPY', f_, 'd') if x['type'] == 'low']
                            back_ = back_ or (bool(lws_) and lws_[-1]['label'] == 'HL')
                        if bk_ == 'calm':   # the selloff has narrowed again
                            back_ = back_ or G['BREADTH'].get(f_, 0.0) < wq_.get('bth', 0.20) / 2
                        if bk_ == 'ma20':
                            w20 = [x for x in spyc_[max(0, k_ - 19):k_ + 1] if x]
                            back_ = back_ or spyc_[k_] > sum(w20) / len(w20)
                        if back_:
                            on_, cnt_ = False, 0
                    if on_ and modes.get(f_, 'boost') == 'boost':
                        if wq_['dest'] == 'duo':
                            dst = list(pool_)
                        else:
                            dst = rising or ['BIL']
                        modes[f_] = f"WQ:{1 - wq_.get('out', 1.0)}:" + '+'.join(dst)
                        n_on += 1
                R.log(f"  {key} warn-trade on {n_on} sessions")
            prec_ = leg_.get('prec') or {}   # precedence tests: which rule wins a clash
            pre_mj_modes = dict(modes)
            mj_ = leg_.get('major')
            pre_mj = dict(modes) if mj_ and os.environ.get('DUMP_MAJOR') == key else None
            if mj_:
                # bigger-picture SPY downtrend: the last major swing high is lower than the one before (optionally the last
                # major low too) and SPY is still under that last high -> while the plan holds the Boost list, hold the
                # strongest rising of TLT/GLD instead, else T-bills; back once SPY closes above the last lower high
                n_mj = 0
                bc_ = None
                if mj_.get('src') == 'boost' or mj_.get('bma'):
                    # the Boost list's own value (the stock engine before any switching), as a price series
                    cvb_ = dict((c_[0], c_[1]) for c_ in run['curve'])
                    bc_, l_ = [], None
                    for d_ in cal:
                        l_ = cvb_.get(d_) or l_
                        bc_.append(l_)
                    bbars_ = [(cal[i_], v_, v_, v_, v_) for i_, v_ in enumerate(bc_) if v_]
                    bbd_ = [b_[0] for b_ in bbars_]
                st_out = False
                ch_in, ch_hi, ch_block = False, None, None
                tx_key, tx_until, tx_from = None, -1, 0
                cn_st_ = {}

                def _chan(dl_, d_):
                    # down channel on SPY: last two swing highs lower, last two swing lows lower, similar slopes;
                    # returns (top line, bottom line) projected to d_, and the last swing low's date
                    cf_ = mj_['chan']
                    bs2_ = weekly(dl_) if cf_['tf'] == 'w' else dl_
                    sw2_ = _fs(bs2_, n=cf_['n'])
                    h2_ = [x for x in sw2_ if x['type'] == 'high']
                    l2_ = [x for x in sw2_ if x['type'] == 'low']
                    if len(h2_) < 2 or len(l2_) < 2:
                        return None, (l2_[-1]['ts'] if l2_ else None)
                    a_, b_, c_, e_ = h2_[-2], h2_[-1], l2_[-2], l2_[-1]
                    ix_ = [idx_.get(x['ts'][:10]) for x in (a_, b_, c_, e_)]
                    if None in ix_ or not (b_['price'] < a_['price'] and e_['price'] < c_['price']):
                        return None, e_['ts']
                    sh_ = math.log(b_['price'] / a_['price']) / max(1, ix_[1] - ix_[0])
                    sl_ = math.log(e_['price'] / c_['price']) / max(1, ix_[3] - ix_[2])
                    if not (sh_ < 0 and sl_ < 0 and 1 / cf_['k'] <= sl_ / sh_ <= cf_['k']):
                        return None, e_['ts']
                    i_ = idx_[d_]
                    return (math.exp(math.log(b_['price']) + sh_ * (i_ - ix_[1])),
                            math.exp(math.log(e_['price']) + sl_ * (i_ - ix_[3]))), e_['ts']

                def _rsi_w(cl_, n_):
                    # Wilder RSI on weekly closes
                    if len(cl_) <= n_:
                        return 50.0
                    ch_ = [b_ - a_ for a_, b_ in zip(cl_[:-1], cl_[1:])]
                    ag_ = sum(max(x_, 0) for x_ in ch_[:n_]) / n_
                    al_ = sum(max(-x_, 0) for x_ in ch_[:n_]) / n_
                    for x_ in ch_[n_:]:
                        ag_ = (ag_ * (n_ - 1) + max(x_, 0)) / n_
                        al_ = (al_ * (n_ - 1) + max(-x_, 0)) / n_
                    return 100.0 if al_ == 0 else 100 - 100 / (1 + ag_ / al_)
                for k_ in range(1, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START or modes.get(f_, 'boost') != 'boost':
                        continue
                    if mj_.get('src') == 'boost':
                        j_ = bisect_right(bbd_, f_)
                        daily = bbars_[max(0, j_ - mj_.get('look', 700)):j_]
                        if len(daily) < 60:
                            continue
                    else:
                        j_ = bisect_right(bdays['SPY'], f_)
                        daily = [tuple(b_) for b_ in bars_src['SPY'][max(0, j_ - mj_.get('look', 700)):j_]]
                    bs_ = weekly(daily) if mj_['tf'] == 'w' else daily
                    sw_ = _fs(bs_, n=mj_['n'])
                    hi_ = [x for x in sw_ if x['type'] == 'high']
                    lo_ = [x for x in sw_ if x['type'] == 'low']
                    if len(hi_) < 2:
                        continue
                    # an equal high (a double top) counts as lower, with a part-per-million tolerance so rounding in the
                    # adjusted prices can't decide a tie (as mtl/lowerhigh.py, Oct 16, 2026)
                    down_ = hi_[-1]['price'] <= hi_[-2]['price'] * (1 + 1e-6) and daily[-1][4] < hi_[-1]['price']
                    if mj_.get('nolh'):
                        down_ = True
                    if down_ and mj_.get('ll'):
                        down_ = len(lo_) >= 2 and lo_[-1]['price'] < lo_[-2]['price']
                    if down_ and (mj_.get('rsi') or mj_.get('round')):
                        wc_ = [b_[4] for b_ in weekly(daily)]
                        if mj_.get('rsi'):
                            # weekly RSI under the line (momentum has turned bearish)
                            down_ = _rsi_w(wc_, mj_['rsi'][0]) < mj_['rsi'][1]
                        if down_ and mj_.get('round'):
                            # rounding down: the m-week average has started to fall
                            m_ = mj_['round']
                            down_ = len(wc_) > m_ and sum(wc_[-m_:]) / m_ < sum(wc_[-m_ - 1:-1]) / m_
                    if down_ and mj_.get('ma150'):
                        w150 = [x for x in spyc_[max(0, k_ - 149):k_ + 1] if x]
                        down_ = len(w150) == 150 and spyc_[k_] < sum(w150) / 150
                    if down_ and mj_.get('ma'):
                        # back in as soon as SPY closes above its ma-day average, even under the last lower high
                        wma = [x for x in spyc_[max(0, k_ - mj_['ma'] + 1):k_ + 1] if x]
                        down_ = len(wma) == mj_['ma'] and spyc_[k_] < sum(wma) / mj_['ma']
                    if down_ and mj_.get('bma'):
                        # back in as soon as the Boost list itself closes above its bma-day average
                        wb_ = [x for x in bc_[max(0, k_ - mj_['bma'] + 1):k_ + 1] if x]
                        down_ = len(wb_) == mj_['bma'] and bc_[k_] < sum(wb_) / mj_['bma']
                    if down_ and mj_.get('dnotup'):
                        # back in once SPY's daily structure turns up (higher high and higher low)
                        down_ = leg('SPY', f_)[0] != 'uptrend'
                    if mj_.get('stay'):
                        # once out, stay out until SPY's daily structure turns up (higher high and higher low)
                        up_d = leg('SPY', f_)[0] == 'uptrend'
                        if not st_out and down_ and not up_d:
                            st_out = True
                        elif st_out and up_d:
                            st_out = False
                        down_ = st_out
                    sig_key = (hi_[-1]['ts'], 'c') if mj_.get('twice') else hi_[-1]['ts']
                    if mj_.get('prov') and not down_ and mj_['tf'] == 'w':
                        # unconfirmed lower high: the highest week since the last confirmed swing high (a peak at least
                        # a week old, the highest of the n weeks before it) sits under that high, SPY closes under it,
                        # and the daily chart has already turned (a daily lower high, or a daily downtrend)
                        # the latest completed week since that high which tops the n weeks before it and every week after it
                        pk_i = None
                        for q_ in range(len(bs_) - 2, hi_[-1]['i'], -1):
                            if q_ >= mj_['n'] and bs_[q_][2] >= max(b_[2] for b_ in bs_[q_ - mj_['n']:q_]) and \
                                    bs_[q_][2] > max(b_[2] for b_ in bs_[q_ + 1:]):
                                pk_i = q_
                                break
                        if pk_i is not None:
                            pk_ = bs_[pk_i]
                            if pk_[2] <= hi_[-1]['price'] * (1 + 1e-6) and daily[-1][4] < pk_[2]:
                                if mj_['prov'] == 'dd':
                                    turn_ = leg('SPY', f_)[0] == 'downtrend'
                                else:
                                    dh_ = [x for x in _fs(daily[-120:], n=3) if x['type'] == 'high']
                                    turn_ = len(dh_) >= 2 and dh_[-1]['price'] <= dh_[-2]['price'] * (1 + 1e-6) and daily[-1][4] < dh_[-1]['price']
                                if turn_:
                                    down_, sig_key = True, ((pk_[0], 'e') if mj_.get('twice') else pk_[0])
                    cn_ = mj_.get('chan2')
                    if cn_ and cn_.get('only'):
                        down_ = False
                    if cn_ and not down_:
                        # rising channel (support and resistance lines, each `span`+ weeks, similar length): a close under
                        # the support line fires once per line
                        from chan_lines import find_channel as _fch, find_touchline as _ftl
                        j3_ = bisect_right(bdays['SPY'], f_)
                        dl3_ = [tuple(b_) for b_ in bars_src['SPY'][max(0, j3_ - cn_.get('look', 1100)):j3_]]
                        kw3_ = {k3_: v3_ for k3_, v3_ in cn_.items() if k3_ not in ('only', 'look', 'kind', 'again')}
                        ch3_ = (_ftl if cn_.get('kind') == 'line' else _fch)(weekly(dl3_), **kw3_)
                        if ch3_ and cn_.get('again'):
                            # a line fires again after SPY closes back above it and then under it once more
                            key3_ = ('cn', ch3_['lower'][0]['ts'], ch3_['lower'][1]['ts'])
                            st3_ = cn_st_.setdefault(key3_, [0, True])
                            if dl3_[-1][4] >= ch3_['low_now']:
                                st3_[1] = True
                            else:
                                if st3_[1]:
                                    st3_[0], st3_[1] = st3_[0] + 1, False
                                down_, sig_key = True, key3_ + (st3_[0],)
                        elif ch3_ and dl3_[-1][4] < ch3_['low_now']:
                            down_, sig_key = True, ('cn', ch3_['lower'][0]['ts'], ch3_['lower'][1]['ts'])
                    tl_ = mj_.get('tline')
                    if tl_ and tl_.get('only'):
                        down_ = False
                    if tl_ and not down_:
                        # rising trendline: the line (in log price) through the last two weekly swing lows, when the later
                        # one is higher; a close more than tol under the line projected to this week fires once per line
                        sw2_ = sw_ if tl_.get('n', mj_['n']) == mj_['n'] else _fs(bs_, n=tl_['n'])
                        lo2_ = [x for x in sw2_ if x['type'] == 'low']
                        pair_ = None
                        if tl_.get('gap') and lo2_:
                            # a long line: from the latest lower swing low at least `gap` weeks before the last swing low,
                            # with no weekly low under the line (0.5% slack) in between
                            lb_ = lo2_[-1]
                            for la_ in reversed(lo2_[:-1]):
                                if lb_['i'] - la_['i'] < tl_['gap'] or la_['price'] >= lb_['price']:
                                    continue
                                sl_tl = (math.log(lb_['price']) - math.log(la_['price'])) / (lb_['i'] - la_['i'])
                                if all(bs_[q_][3] >= math.exp(math.log(la_['price']) + sl_tl * (q_ - la_['i'])) * 0.995
                                       for q_ in range(la_['i'] + 1, lb_['i'])):
                                    pair_ = (la_, lb_)
                                    break
                        elif len(lo2_) >= 2 and lo2_[-1]['price'] > lo2_[-2]['price']:
                            pair_ = (lo2_[-2], lo2_[-1])
                        if pair_:
                            la_, lb_ = pair_
                            sl_tl = (math.log(lb_['price']) - math.log(la_['price'])) / max(1, lb_['i'] - la_['i'])
                            line_ = math.exp(math.log(lb_['price']) + sl_tl * (len(bs_) - 1 - lb_['i']))
                            if daily[-1][4] < line_ * (1 - tl_.get('tol', 0.0)):
                                down_, sig_key = True, ('tl', la_['ts'], lb_['ts'])
                    if mj_.get('days'):
                        # timed exit: on a fresh signal (a new major lower high), out for `days` sessions, then back to
                        # whatever the plan holds; the same lower high can't fire it again
                        if down_ and sig_key != tx_key and k_ > tx_until:
                            # a trendline break may carry its own length / delay (tline days, lag)
                            tlx_ = (mj_.get('tline') or {}) if isinstance(sig_key, tuple) and sig_key and sig_key[0] == 'tl' else {}
                            lg_ = tlx_.get('lag', mj_.get('lag', 0))
                            tx_key, tx_until = sig_key, k_ + lg_ + tlx_.get('days', mj_['days']) - 1
                            tx_from = k_ + lg_
                        down_ = k_ <= tx_until and k_ >= tx_from
                    if mj_.get('chan'):
                        # buy the Boost list at the bottom of a parallel down channel; hold until a new major lower
                        # high forms or SPY closes stop% under the channel (then wait for a fresh swing low)
                        cf_ = mj_['chan']
                        j2_ = bisect_right(bdays['SPY'], f_)
                        dl_ = [tuple(b_) for b_ in bars_src['SPY'][max(0, j2_ - 500):j2_]]
                        ln_, lt_ = _chan(dl_, f_)
                        c0_ = dl_[-1][4]
                        if ch_in:
                            if ln_ and c0_ < ln_[1] * (1 - cf_.get('stop', 0.03)):
                                ch_in, ch_block = False, lt_
                            elif down_ and hi_[-1]['ts'] != ch_hi:
                                ch_in = False
                            else:
                                down_ = False
                        elif down_ and ln_ and c0_ <= ln_[1] * (1 + cf_.get('tol', 0.01)) and lt_ != ch_block:
                            ch_in, ch_hi, down_ = True, hi_[-1]['ts'], False
                    if not down_:
                        continue
                    best_, bv = 'BIL', None
                    for t_ in (() if mj_.get('to') == 'BIL' else mj_.get('pool', pool_)):
                        if mj_.get('dest') == 'pct':
                            if leg(t_, f_)[0] == 'downtrend':
                                continue
                            x_ = pchg(t_, f_, mj_.get('pn', 126))
                            if x_ is None or x_ <= 0:
                                continue
                        else:
                            ast, ag = leg(t_, f_)
                            if ast != 'uptrend' or ag is None or ag <= 0:
                                continue
                            x_ = ag
                        if bv is None or x_ > bv:
                            best_, bv = t_, x_
                    modes[f_] = ('SIDE:' + best_) if mj_.get('half') else best_
                    n_mj += 1
                R.log(f"  {key} major-downtrend sessions {n_mj}")
                if pre_mj is not None:
                    json.dump(dict(pre=pre_mj, cash=sorted(d_ for d_ in modes if modes[d_] != pre_mj.get(d_)),
                                   assets={d_: modes[d_] for d_ in modes if modes[d_] != pre_mj.get(d_)}),
                              open(os.path.join(ROOT, 'data', f"major_{key}{os.environ.get('TAG', '')}.json"), 'w'))
            lh_set_ = {d_ for d_, m_ in modes.items() if pre_mj_modes.get(d_, 'boost') == 'boost' and m_ != 'boost'}   # the lower-high exit's days
            wo_ = leg_.get('wkout')
            if wo_:
                # out of stocks while SPY's weekly chart shows a lower high and a lower low (swings wo_['n'] weeks
                # either side); back to the plan once the daily chart (swings 3 days either side) makes a higher low
                # after going out (back='hl'), or a higher high and a higher low (back='up'). The same weekly
                # pattern can't send it out again: it takes a new weekly swing.
                out_, since_, used_, n_wo = False, None, set(), 0
                for k_ in range(1, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START:
                        continue
                    j_ = bisect_right(bdays['SPY'], f_)
                    daily = [tuple(b_) for b_ in bars_src['SPY'][max(0, j_ - 700):j_]]
                    if len(daily) < 120:
                        continue
                    if not out_:
                        sw_ = _fs(weekly(daily), n=wo_.get('n', 2))
                        hi_ = [x for x in sw_ if x['type'] == 'high']
                        lo_ = [x for x in sw_ if x['type'] == 'low']
                        if len(hi_) >= 2 and len(lo_) >= 2 and hi_[-1]['price'] < hi_[-2]['price'] and lo_[-1]['price'] < lo_[-2]['price']:
                            sig_ = (hi_[-1]['ts'], lo_[-1]['ts'])
                            if sig_ not in used_ and (not wo_.get('below') or daily[-1][4] < hi_[-1]['price']):
                                out_, since_ = True, f_
                                used_.add(sig_)
                    else:
                        sd_ = _fs(daily[-320:], n=wo_.get('dn', 3))
                        dl_ = [x for x in sd_ if x['type'] == 'low']
                        dh_ = [x for x in sd_ if x['type'] == 'high']
                        hl_ = len(dl_) >= 2 and dl_[-1]['price'] > dl_[-2]['price'] and dl_[-1]['ts'][:10] >= since_
                        if wo_.get('back', 'hl') == 'up':
                            hl_ = hl_ and len(dh_) >= 2 and dh_[-1]['price'] > dh_[-2]['price']
                        if hl_:
                            out_ = False
                    if out_ and (modes.get(f_, 'boost') == 'boost' or str(modes.get(f_, '')).startswith('SIDE:')):
                        modes[f_] = 'BIL'
                        n_wo += 1
                R.log(f"  {key} weekly-downtrend sessions out {n_wo}")
            stx_ = leg_.get('stx')
            if stx_:
                # Supertrend on SPY (ATR stx_['n'] bars, Wilder; bands at the bar's midpoint -/+ m x ATR that only ratchet
                # in the trend's direction; flips on a close beyond the opposite band). Red -> out of stocks (T-bills,
                # which the no-T-bills rule turns into the stronger rising of gold / bonds, else cash). The weekly version
                # changes only at a week's last close.
                sb_ = [tuple(b_) for b_ in bars_src['SPY']]
                sbars_ = weekly(sb_) if stx_.get('tf', 'd') == 'w' else sb_
                n_st, m_st = stx_.get('n', 10), stx_.get('m', 3.0)
                atr_, fu_, fl_, dir_, pc_, trd_ = None, None, None, 1, None, []
                for i_, (d_, o_, h_, l_, c_) in enumerate(sbars_):
                    tr_ = h_ - l_ if pc_ is None else max(h_ - l_, abs(h_ - pc_), abs(l_ - pc_))
                    atr_ = tr_ if atr_ is None else (atr_ * (n_st - 1) + tr_) / n_st
                    mid_ = (h_ + l_) / 2
                    bu_, bl_ = mid_ + m_st * atr_, mid_ - m_st * atr_
                    if fu_ is None:
                        fu_, fl_ = bu_, bl_
                    else:
                        fu_ = bu_ if (bu_ < fu_ or pc_ > fu_) else fu_
                        fl_ = bl_ if (bl_ > fl_ or pc_ < fl_) else fl_
                    if dir_ == 1 and c_ < fl_:
                        dir_ = -1
                    elif dir_ == -1 and c_ > fu_:
                        dir_ = 1
                    pc_ = c_
                    if i_ >= n_st:
                        trd_.append((d_[:10], dir_))
                tdays_ = [x[0] for x in trd_]
                n_st_out = 0
                for k_ in range(1, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START:
                        continue
                    j_ = bisect_right(tdays_, f_) - 1
                    if j_ < 0:
                        continue
                    if stx_.get('tf', 'd') == 'w' and tdays_[j_] == f_ and k_ + 1 < len(cal) and \
                            date.fromisoformat(cal[k_ + 1]).isocalendar()[:2] == date.fromisoformat(f_).isocalendar()[:2]:
                        j_ -= 1         # a week still in progress (only at the data's end): use the last finished week
                    if j_ >= 0 and trd_[j_][1] < 0 and (modes.get(f_, 'boost') == 'boost' or str(modes.get(f_, '')).startswith('SIDE:')):
                        modes[f_] = 'BIL'
                        n_st_out += 1
                R.log(f"  {key} supertrend sessions out {n_st_out}")
            ts_ = leg_.get('tsym')
            if ts_:
                # time symmetry on SPY (weekly or daily swings): out of stocks while the time since the last swing high is
                # longer than the rally into it took (from the swing low before it) and SPY is still under that high.
                # Where to: haven='nb' -> T-bills (the no-T-bills rule picks); else gold / bonds that pass the check
                # ('t': time since its last swing low longer than the drop into it took, from the high before;
                # 'tu': that and up over 6 months; 'th': that and higher highs + higher lows; 'h': higher highs + higher
                # lows alone), the one up most over 6 months, else cash at 0%.
                tf_ts, n_ts, hv_ = ts_.get('tf', 'w'), ts_.get('n', 2 if ts_.get('tf', 'w') == 'w' else 3), ts_.get('haven', 'nb')
                if 'CASH0' not in px_all:
                    px_all['CASH0'] = {d_: 1.0 for d_ in cal}

                def ts_swings(t_, d_):
                    j_ = bisect_right(bdays[t_], d_)
                    daily = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - (700 if tf_ts == 'w' else 320)):j_]]
                    bs_ = weekly(daily) if tf_ts == 'w' else daily
                    return bs_, _fs(bs_, n=n_ts)

                def haven_ok(t_, d_):
                    bs_, sw_ = ts_swings(t_, d_)
                    his = [x for x in sw_ if x['type'] == 'high']
                    los = [x for x in sw_ if x['type'] == 'low']
                    hh_ = len(his) >= 2 and len(los) >= 2 and his[-1]['price'] > his[-2]['price'] and los[-1]['price'] > los[-2]['price']
                    if hv_ == 'h':
                        return hh_
                    if not los:
                        return False
                    lo_ = los[-1]
                    prev_ = [x for x in his if x['i'] < lo_['i']]
                    if not prev_:
                        return False
                    ok_ = (len(bs_) - 1 - lo_['i']) > (lo_['i'] - prev_[-1]['i'])
                    if ok_ and hv_ == 'tu':
                        c_ = pchg(t_, d_, 126)
                        ok_ = c_ is not None and c_ > 0
                    if ok_ and hv_ == 'th':
                        ok_ = hh_
                    return ok_
                n_ts_out, hold_ = 0, {}
                out_, ex_, used_ = False, None, set()
                for k_ in range(1, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START:
                        continue
                    bs_, sw_ = ts_swings('SPY', f_)
                    his = [x for x in sw_ if x['type'] == 'high']
                    if out_:
                        # back above the high that sent it out; with back='both' also once SPY's rise since its last swing
                        # low (made after that high) has lasted longer than the drop into it (from the high before it)
                        back_ = bs_[-1][4] > ex_[1]
                        if not back_ and ts_.get('back', 'hi') == 'both':
                            lw_ = [x for x in sw_ if x['type'] == 'low' and x['ts'] > ex_[0]]
                            if lw_:
                                hb_ = [x for x in his if x['i'] < lw_[-1]['i']]
                                back_ = bool(hb_) and (len(bs_) - 1 - lw_[-1]['i']) > (lw_[-1]['i'] - hb_[-1]['i'])
                        if back_:
                            out_ = False
                            used_.add(ex_[0])
                    if not out_ and his:
                        hi_ = his[-1]
                        lb_ = [x for x in sw_ if x['type'] == 'low' and x['i'] < hi_['i']]
                        if lb_ and hi_['ts'] not in used_ and (len(bs_) - 1 - hi_['i']) > (hi_['i'] - lb_[-1]['i']) and bs_[-1][4] < hi_['price']:
                            out_, ex_ = True, (hi_['ts'], hi_['price'])
                    if not out_ or not (modes.get(f_, 'boost') == 'boost' or str(modes.get(f_, '')).startswith('SIDE:')):
                        continue
                    if hv_ == 'nb':
                        modes[f_] = 'BIL'
                    else:
                        ok_ = [(pchg(t_, f_, 126) or -9, t_) for t_ in pool_ if t_ in bdays and haven_ok(t_, f_)]
                        modes[f_] = max(ok_)[1] if ok_ else 'CASH0'
                    hold_[modes[f_]] = hold_.get(modes[f_], 0) + 1
                    n_ts_out += 1
                R.log(f"  {key} time-symmetry sessions out {n_ts_out} {hold_}")
            side_ = leg_.get('side')
            if side_:
                # sideways SPY (checked at each week's last close): low efficiency ratio (net move / path length) or low R^2 of a
                # straight-line fit to log price over n sessions -> while the plan holds the Boost list, hold the calmer mode instead
                n_ = side_['n']
                sp_ = [px_all['SPY'].get(d_) for d_ in cal]
                for i_ in range(1, len(sp_)):
                    if sp_[i_] is None:
                        sp_[i_] = sp_[i_ - 1]
                reg_, on_ = [], False
                bval_ = None
                if side_['metric'] == 'mom':
                    # the Boost list's own daily value (before the plan's switches), to compare with SPY
                    scm_, lw_, bval_, v0_ = dict(sc), None, [], 1.0
                    for k_, d_ in enumerate(cal):
                        if lw_ and k_:
                            r_ = 0.0
                            for t_, x_ in lw_.items():
                                a_, b_ = px_all.get(t_, {}).get(cal[k_ - 1]), px_all.get(t_, {}).get(d_)
                                if a_ and b_:
                                    r_ += x_ * (b_ / a_ - 1)
                            v0_ *= 1 + r_
                        if d_ in scm_:
                            lw_ = scm_[d_]
                        bval_.append(v0_)

                tev_ = None
                if side_['metric'] in ('turn', 'whip'):
                    # the Boost list's own trades: per session, names that left the list and (for 'whip') whether each lost money
                    scm_, held_, tev_ = dict(sc), {}, []
                    if run.get('whip_picks') is not None:
                        # shadow count: the stock list with the pick filter off (a skipped stock counts as if bought and sold)
                        scm_ = {d_: {t_: 1.0 for t_ in nm_} for d_, nm_ in run['whip_picks']}
                    for k_, d_ in enumerate(cal):
                        ex_ = []
                        if d_ in scm_:
                            nw_ = {t_ for t_, x_ in (scm_[d_] or {}).items() if x_ > 0}
                            for t_ in list(held_):
                                if t_ not in nw_:
                                    b_ = px_all.get(t_, {}).get(d_)
                                    ex_.append(bool(b_ and held_[t_] and b_ < held_[t_]))
                                    del held_[t_]
                            for t_ in nw_:
                                if t_ not in held_:
                                    held_[t_] = px_all.get(t_, {}).get(d_)
                        tev_.append(ex_)

                def sdv_(k_):
                    rr_ = [math.log(sp_[i_] / sp_[i_ - 1]) for i_ in range(k_ - 62, k_ + 1)]
                    m_ = sum(rr_) / len(rr_)
                    return (sum((x - m_) ** 2 for x in rr_) / (len(rr_) - 1)) ** 0.5

                def grad_(p0, p1, d0, d1, k_):   # log slope per session through two points, / SPY's daily volatility
                    ns_ = max(1.0, (date.fromisoformat(d1[:10]) - date.fromisoformat(d0[:10])).days * 252 / 365)
                    sd_ = sdv_(k_)
                    return math.log(p1 / p0) / ns_ / sd_ if sd_ else 0.0
                for k_ in range(len(cal)):
                    wk_end = k_ + 1 == len(cal) or date.fromisoformat(cal[k_ + 1]).isocalendar()[:2] != date.fromisoformat(cal[k_]).isocalendar()[:2]
                    if wk_end and k_ >= n_ and all(sp_[k_ - n_:k_ + 1]):
                        seg_ = sp_[k_ - n_:k_ + 1]
                        if side_['metric'] in ('turn', 'whip'):
                            # churn in the top 5: names replaced over the last n sessions (turn), or the share of those exits that
                            # lost money, needing at least `min` exits (whip)
                            ex_ = [e for i_ in range(k_ - n_ + 1, k_ + 1) for e in tev_[i_]]
                            if side_['metric'] == 'turn':
                                v_ = 0.0 if len(ex_) >= side_['cnt'] else 1.0
                            else:
                                v_ = 0.0 if len(ex_) >= side_.get('min', 3) and sum(ex_) / len(ex_) >= side_['loss'] else 1.0
                        elif side_['metric'] == 'mom':
                            # momentum not working: the Boost list trailed SPY by more than thr over n sessions
                            rel_ = (bval_[k_] / bval_[k_ - n_] - 1) - (sp_[k_] / sp_[k_ - n_] - 1) if bval_[k_ - n_] else 0.0
                            v_ = 0.0 if rel_ < side_['lag'] else 1.0
                        elif side_['metric'] == 'hh':
                            # flat swing highs: |gradient| through the last two weekly swing highs (and optionally weekly lows,
                            # and a line fitted through all daily swing highs of the last n sessions) below `flat`
                            fl_ = side_['flat']
                            labw_ = leg_lab_tf('SPY', cal[k_], 'w')
                            hw_ = [x for x in labw_ if x['type'] == 'high']
                            ok_ = len(hw_) >= 2 and abs(grad_(hw_[-2]['price'], hw_[-1]['price'], hw_[-2]['ts'], hw_[-1]['ts'], k_)) < fl_
                            if ok_ and side_.get('lows'):
                                lw2_ = [x for x in labw_ if x['type'] == 'low']
                                ok_ = len(lw2_) >= 2 and abs(grad_(lw2_[-2]['price'], lw2_[-1]['price'], lw2_[-2]['ts'], lw2_[-1]['ts'], k_)) < fl_
                            if ok_ and side_.get('daily'):
                                hd_ = [x for x in leg_lab_tf('SPY', cal[k_], 'd') if x['type'] == 'high' and x['ts'][:10] >= cal[k_ - n_]]
                                if len(hd_) >= 3:
                                    xs_ = [(date.fromisoformat(x['ts'][:10]) - date.fromisoformat(hd_[0]['ts'][:10])).days * 252 / 365 for x in hd_]
                                    ys_ = [math.log(x['price']) for x in hd_]
                                    mx_, my_ = sum(xs_) / len(xs_), sum(ys_) / len(ys_)
                                    sxx_ = sum((a - mx_) ** 2 for a in xs_)
                                    sl_ = sum((a - mx_) * (b - my_) for a, b in zip(xs_, ys_)) / sxx_ if sxx_ else 0.0
                                    sd_ = sdv_(k_)
                                    ok_ = abs(sl_ / sd_ if sd_ else 0.0) < fl_
                                else:
                                    ok_ = False
                            v_ = 0.0 if ok_ else 1.0
                        elif side_['metric'] == 'band':
                            # near a flat 150-day average: |SPY / MA150 - 1| < gap and the MA150 moved less than `slope` over n sessions
                            ma_now = sum(sp_[k_ - 149:k_ + 1]) / 150 if k_ >= 150 + n_ else None
                            ma_then = sum(sp_[k_ - n_ - 149:k_ - n_ + 1]) / 150 if k_ >= 150 + n_ else None
                            v_ = 0.0 if (ma_now and abs(sp_[k_] / ma_now - 1) < side_['gap'] and abs(ma_now / ma_then - 1) < side_['slope']) else 1.0
                        elif side_['metric'] == 'er':
                            path_ = sum(abs(seg_[i_] - seg_[i_ - 1]) for i_ in range(1, len(seg_)))
                            v_ = abs(seg_[-1] - seg_[0]) / path_ if path_ else 1.0
                        else:
                            ys_ = [math.log(x) for x in seg_]; xs_ = list(range(len(ys_)))
                            mx_, my_ = sum(xs_) / len(xs_), sum(ys_) / len(ys_)
                            sxy_ = sum((a - mx_) * (b - my_) for a, b in zip(xs_, ys_)); sxx_ = sum((a - mx_) ** 2 for a in xs_); syy_ = sum((b - my_) ** 2 for b in ys_)
                            v_ = sxy_ * sxy_ / (sxx_ * syy_) if sxx_ and syy_ else 1.0
                        on_ = v_ < side_['thr']
                        if on_ and side_.get('near') and k_ >= 150:
                            on_ = abs(sp_[k_] / (sum(sp_[k_ - 149:k_ + 1]) / 150) - 1) < side_['near']
                    reg_.append(on_)
                n_side = 0
                for k_, d_ in enumerate(cal):
                    if d_ in modes and modes[d_] == 'boost' and reg_[k_]:
                        modes[d_] = 'SIDE'
                        if side_['mode'] in ('BEST', 'BMIX', 'BNS'):
                            # the steepest higher-high/higher-low uptrend among TLT, GLD (and SPY unless BNS); none -> BIL
                            best_, bv = 'BIL', None
                            for t_ in tuple(pool_) + (() if side_['mode'] == 'BNS' else ('SPY',)):
                                ast, ag = leg(t_, d_)
                                if ast == 'uptrend' and ag is not None and ag > 0 and (bv is None or ag > bv):
                                    best_, bv = t_, ag
                            modes[d_] = 'SIDE:' + best_
                        elif side_['mode'] in ('PROT', 'PROTMIX'):
                            # rotation-style: the best of TLT, GLD, SPY by % change (or gradient); SPY best -> stay in the Boost list
                            best_, bv = side_.get('none', 'BIL'), 0.0 if side_.get('sel') != 'grad' else None
                            for t_ in tuple(pool_) + ('SPY',):
                                if side_.get('nodown') and leg(t_, d_, 'w')[0] == 'downtrend':
                                    continue
                                if side_.get('sel') == 'grad':
                                    ast, ag = leg(t_, d_)
                                    if ast == 'uptrend' and ag is not None and ag > 0 and (bv is None or ag > bv):
                                        best_, bv = t_, ag
                                    continue
                                a_ = px_all.get(t_, {}).get(cal[k_ - side_['pn']]) if k_ >= side_['pn'] else None
                                b_ = px_all.get(t_, {}).get(d_)
                                if a_ and b_ and b_ / a_ - 1 > bv:
                                    best_, bv = t_, b_ / a_ - 1
                            if best_ in ('SPY', 'boost'):
                                modes[d_] = 'boost'
                                n_side -= 1
                            else:
                                modes[d_] = 'SIDE:' + best_
                        elif side_['mode'] in ('PBEST', 'PBMIX'):
                            # biggest % change over pn sessions among TLT, GLD, SPY (optionally skipping weekly downtrends); none up -> BIL
                            best_, bv = 'BIL', 0.0
                            for t_ in tuple(pool_) + ('SPY',):
                                if side_.get('nodown') and leg(t_, d_, 'w')[0] == 'downtrend':
                                    continue
                                if side_.get('zsel'):
                                    z_ = zret(t_, d_, side_['pn'])
                                    if z_ is not None and z_ > bv:
                                        best_, bv = t_, z_
                                    continue
                                a_ = px_all.get(t_, {}).get(cal[k_ - side_['pn']]) if k_ >= side_['pn'] else None
                                b_ = px_all.get(t_, {}).get(d_)
                                if a_ and b_ and b_ / a_ - 1 > bv:
                                    best_, bv = t_, b_ / a_ - 1
                            modes[d_] = 'SIDE:' + best_
                        n_side += 1
                if tev_ is not None:
                    vals_ = [len([e for i_ in range(max(0, k_ - n_ + 1), k_ + 1) for e in tev_[i_]]) for k_ in range(len(cal))]
                    vs_ = sorted(v for k_, v in enumerate(vals_) if cal[k_] >= R.START)
                    R.log(f"  {key} churn over {n_} sessions: p25 {vs_[len(vs_)//4]} p50 {vs_[len(vs_)//2]} p75 {vs_[3*len(vs_)//4]} p90 {vs_[9*len(vs_)//10]}")
                json.dump(dict(share=n_side / max(1, sum(1 for d_ in modes if d_ >= R.START)), weeks=[cal[k_] for k_ in range(len(cal)) if reg_[k_] and cal[k_] >= R.START and (k_ + 1 == len(cal) or cal[k_ + 1][:7] != cal[k_][:7])]),
                          open(os.path.join(ROOT, 'data', f"side_log_{key}{os.environ.get('TAG', '')}.json"), 'w'))

            af_ = leg_.get('allfall')
            if af_:
                # SPY, TLT and GLD all falling: 100% T-bills until one of them turns up
                ix_ = {d_: i_ for i_, d_ in enumerate(cal)}
                trio_ = ('SPY',) + tuple(pool_)

                def chg_(t_, k_, n_):
                    a_ = (px_all.get(t_) or {}).get(cal[k_ - n_]) if k_ >= n_ else None
                    b_ = (px_all.get(t_) or {}).get(cal[k_])
                    return b_ / a_ - 1 if a_ and b_ else None

                def falling_(t_, k_):
                    if af_['how'] == 'pct':
                        c_ = chg_(t_, k_, af_['n']); return c_ is not None and c_ < 0
                    return leg(t_, cal[k_], af_['how'])[0] == 'downtrend'

                def rising_(t_, k_):
                    if af_.get('out') == 'pct':
                        c_ = chg_(t_, k_, af_['out_n']); return c_ is not None and c_ > 0
                    return not falling_(t_, k_)
                out_, n_af = False, 0
                for d_ in sorted(modes):
                    k_ = ix_[d_]
                    if not out_:
                        out_ = all(falling_(t_, k_) for t_ in trio_)
                    else:
                        out_ = not any(rising_(t_, k_) for t_ in trio_)
                    if out_:
                        ds_ = af_.get('dest', 'BIL')
                        if isinstance(ds_, tuple):     # the best rising of these by % change over dn sessions, else T-bills
                            bv_, ds2_ = None, 'BIL'
                            for t_ in ds_:
                                c_ = chg_(t_, k_, af_.get('dn', 63))
                                if c_ is not None and c_ > 0 and (bv_ is None or c_ > bv_):
                                    ds2_, bv_ = t_, c_
                            ds_ = ds2_
                        modes[d_] = ds_; n_af += 1
                R.log(f"  {key} all-falling days out of stocks/bonds/gold: {n_af}")
            bs_ = leg_.get('bilsub')
            if bs_:
                # wherever the plan would sit in T-bills (all of it, or the half-switch's half), hold the best rising
                # of bs_['assets'] by % change over bs_['n'] sessions instead; none rising -> T-bills as before
                ixb_ = {d_: i_ for i_, d_ in enumerate(cal)}

                def chgb_(t_, k_, n_):
                    a_ = (px_all.get(t_) or {}).get(cal[k_ - n_]) if k_ >= n_ else None
                    b_ = (px_all.get(t_) or {}).get(cal[k_])
                    return b_ / a_ - 1 if a_ and b_ else None
                n_bs, n_b0 = 0, 0
                for d_ in sorted(modes):
                    m_ = modes[d_]
                    if m_ not in ('BIL', 'SIDE:BIL'):
                        continue
                    n_b0 += 1
                    bv_, ds_ = None, None
                    for t_ in bs_['assets']:
                        c_ = chgb_(t_, ixb_[d_], bs_.get('n', 63))
                        if c_ is not None and c_ > 0 and (bv_ is None or c_ > bv_):
                            ds_, bv_ = t_, c_
                    if ds_:
                        modes[d_] = ds_ if m_ == 'BIL' else 'SIDE:' + ds_
                        n_bs += 1
                R.log(f"  {key} T-bill days {n_b0}, swapped {n_bs}")
            if leg_.get('rg_boost'):
                # reflation regime (rates and gold both up): stay fully in the Boost list
                rb_ = leg_['rg_boost']
                for d_ in list(modes):
                    if rgx_.get(d_) == 'ru' and (rb_ == 'all' or str(modes[d_]).startswith('SIDE')):
                        modes[d_] = 'boost'
            wc_ = leg_.get('warnconf')
            if wc_:
                # narrow-market warning arms the rule for `armed` sessions; if SPY ('spy'), the held Boost stocks
                # ('basket') or either falls `drop` below its close on the latest warning day (ref 'warn') or below its
                # 20-session high (ref 'hi20'), the account sits in T-bills for `days` sessions, then follows the plan
                W11 = set(json.load(open(os.path.join(SIDE_, 'narrow_warn.json'))))
                ixw_ = {d_: i_ for i_, d_ in enumerate(cal)}
                scd11 = dict(sc); cur11 = None; bas11 = []
                for i_, d_ in enumerate(cal):          # equal-weight index of the stocks held (the plan's stock part)
                    if cur11:
                        rs_ = []
                        for t_ in cur11:
                            pt_ = px_all.get(t_) or {}
                            a_, b_ = pt_.get(cal[i_ - 1]), pt_.get(d_)
                            if a_ and b_:
                                rs_.append(b_ / a_ - 1)
                        bas11.append((bas11[-1] if bas11 else 1.0) * (1 + (sum(rs_) / len(rs_) if rs_ else 0.0)))
                    else:
                        bas11.append(bas11[-1] if bas11 else 1.0)
                    if d_ in scd11:
                        cur11 = [t_ for t_, w_ in (scd11[d_] or {}).items() if w_ > 0 and t_ not in ('TLTX', 'GLDX', 'BIL', 'SPY', 'CASH0')]
                spx11 = px_all.get('SPY') or {}
                spy11 = []
                for d_ in cal:
                    spy11.append(spx11.get(d_) or (spy11[-1] if spy11 else None))
                armed_until, ref_s, ref_b, cash_until, n_wc, fired = -1, None, None, -1, 0, False
                for i_, d_ in enumerate(cal):
                    if d_ in W11:
                        armed_until = i_ + wc_['armed']; ref_s, ref_b = spy11[i_], bas11[i_]; fired = False
                    if i_ <= cash_until:
                        modes[d_] = 'BIL'; n_wc += 1
                        continue
                    if i_ <= armed_until and not fired and i_ >= 20:
                        if wc_.get('ref') == 'hi20':
                            hs_ = max(x_ for x_ in spy11[i_ - 19:i_ + 1] if x_); hb_ = max(bas11[i_ - 19:i_ + 1])
                            ds_, db_ = spy11[i_] / hs_ - 1, bas11[i_] / hb_ - 1
                        else:
                            ds_ = spy11[i_] / ref_s - 1 if ref_s else 0.0; db_ = bas11[i_] / ref_b - 1 if ref_b else 0.0
                        hit = (wc_['src'] in ('spy', 'either') and ds_ <= -wc_['drop']) or (wc_['src'] in ('basket', 'either') and db_ <= -wc_['drop'])
                        if hit:
                            fired = True; cash_until = i_ + wc_['days']
                R.log(f"  {key} warning-confirmed cash days {n_wc}")
            nc_ = leg_.get('narrowcash')
            if nc_:
                # narrow-market warning: starting `delay` sessions after each warning day, the whole account sits in
                # T-bills for `days` sessions, whatever the plan would hold
                W10 = set(json.load(open(os.path.join(SIDE_, 'narrow_warn' + ('_' + nc_['w'] if nc_.get('w') else '') + '.json'))))
                n_nc = 0; on10 = set()
                for i_, d_ in enumerate(cal):
                    if d_ in W10:
                        for j_ in range(i_ + 1 + nc_['delay'], min(len(cal), i_ + 1 + nc_['delay'] + nc_['days'])):
                            on10.add(cal[j_])
                if run.get('fz_green') and run.get('fz_green_cash', True):   # the two-scale green light skips the cash week (live repo, Oct 26, 2026)
                    on10 = {d_ for d_ in on10 if idx_[d_] not in run['fz_green']}
                for d_ in cal:
                    if d_ in on10:
                        if nc_.get('half'):
                            # half size: half the account to T-bills while the plan is in stocks (or half-switched);
                            # left alone while it already holds TLT, GLD or T-bills
                            m_ = modes.get(d_, 'boost')
                            if m_ == 'boost' or str(m_).startswith('SIDE:'):
                                modes[d_] = 'SIDE:BIL'; n_nc += 1
                        else:
                            modes[d_] = 'BIL'; n_nc += 1
                R.log(f"  {key} narrow-warning cash days {n_nc}")
            try:
                nc_days_ = set(on10) if nc_ else set()
            except NameError:
                nc_days_ = set()
            cr_ = leg_.get('crash')
            if cr_:
                # crash exit: T-bills while a stress signal is on, only replacing stock exposure (boost or half-switch)
                vx_ = json.load(open(os.path.join(ROOT, 'data', 'vix_long.json')))
                v3_ = json.load(open(os.path.join(ROOT, 'data', 'vix3m.json')))
                vixc, v3c, lv, l3 = [], [], None, None
                for d_ in cal:
                    lv = vx_.get(d_, lv); l3 = v3_.get(d_, l3); vixc.append(lv); v3c.append(l3)
                on_, n_cr, streak_on, streak_off = False, 0, 0, 0
                for k_, d_ in enumerate(cal):
                    if cr_['kind'] == 'vixdd':
                        hi_ = max((x for x in spyc_[max(0, k_ - 251):k_ + 1] if x), default=None)
                        dd_ = spyc_[k_] / hi_ - 1 if hi_ and spyc_[k_] else 0.0
                        if not on_:
                            on_ = vixc[k_] is not None and vixc[k_] > cr_['on'] and dd_ <= -cr_['dd']
                        else:
                            if cr_.get('off_ma'):
                                w_ = [x for x in spyc_[max(0, k_ - cr_['off_ma'] + 1):k_ + 1] if x]
                                on_ = not (len(w_) == cr_['off_ma'] and spyc_[k_] > sum(w_) / len(w_))
                            else:
                                on_ = not (vixc[k_] is not None and vixc[k_] < cr_['off'])
                    else:   # term structure: VIX above VIX3M
                        r_ = vixc[k_] / v3c[k_] if vixc[k_] and v3c[k_] else None
                        if r_ is None:
                            streak_on = streak_off = 0
                        elif r_ > cr_['on']:
                            streak_on += 1; streak_off = 0
                        elif r_ < cr_['off']:
                            streak_off += 1; streak_on = 0
                        else:
                            streak_on = streak_off = 0
                        if not on_ and streak_on >= cr_.get('days', 1):
                            on_ = True
                        elif on_ and streak_off >= cr_.get('days', 1):
                            on_ = False
                    if on_ and d_ in modes and (modes[d_] == 'boost' or str(modes[d_]).startswith('SIDE')):
                        modes[d_] = 'BIL'; n_cr += 1
                R.log(f"  {key} crash-exit days {n_cr}")
            ms_ = leg_.get('massell')
            if ms_:
                # "mass selling": dollar index RSI(14) above 50 while gold and long-Treasury RSI(14) are both below 50.
                # On after ms_['on'] days in a row, off after ms_['off'] days in a row without it (strict=True: off
                # only when each of the three readings has been on the other side for ms_['off'] days). While on,
                # scope 'all' replaces whatever the plan holds, scope 'boost' only the days it is in stocks.
                def _rsi(pairs, n=14):
                    out, g, l, prev = {}, 0.0, 0.0, None
                    for i, (d, c) in enumerate(pairs):
                        if prev is not None:
                            ch = c - prev; up, dn = max(ch, 0.0), max(-ch, 0.0)
                            if i <= n:
                                g += up / n; l += dn / n
                            else:
                                g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n
                            if i >= n:
                                out[d] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
                        prev = c
                    return out
                dxj_ = json.load(open(os.path.join(ROOT, 'data', 'dxy.json')))['DX-Y.NYB']
                rs_ = {'D': _rsi([(d, c) for d, c in dxj_]),
                       'G': _rsi([(d, px_all['GLDX'][d]) for d in cal if (px_all.get('GLDX') or {}).get(d)]),
                       'T': _rsi([(d, px_all['TLTX'][d]) for d in cal if (px_all.get('TLTX') or {}).get(d)])}
                rk_ = {k: sorted(v) for k, v in rs_.items()}

                def rat_(k, d):
                    j = bisect_right(rk_[k], d) - 1
                    return rs_[k][rk_[k][j]] if j >= 0 else None
                st_, rt_, rf_, rfx_, n_ms = False, 0, 0, {'D': 0, 'G': 0, 'T': 0}, 0
                for d_ in cal:
                    a_, g_, t_ = rat_('D', d_), rat_('G', d_), rat_('T', d_)
                    if a_ is None or g_ is None or t_ is None:
                        continue
                    c3 = {'D': a_ > ms_.get('hi', 50), 'G': g_ < ms_.get('lo', 50), 'T': t_ < ms_.get('lo', 50)}
                    sig_ = all(c3.values())
                    rt_ = rt_ + 1 if sig_ else 0; rf_ = rf_ + 1 if not sig_ else 0
                    for k_ in c3:
                        rfx_[k_] = rfx_[k_] + 1 if not c3[k_] else 0
                    if not st_ and rt_ >= ms_['on']:
                        st_ = True
                    elif st_ and (all(v_ >= ms_['off'] for v_ in rfx_.values()) if ms_.get('strict') else rf_ >= ms_['off']):
                        st_ = False
                    if st_ and (ms_['scope'] == 'all' or str(modes.get(d_, 'boost')) == 'boost' or str(modes.get(d_, '')).startswith('SIDE')):
                        modes[d_] = ms_['to']
                        n_ms += 1
                R.log(f"  {key} mass-selling days {n_ms}")
            sr_ = leg_.get('spytop')
            if sr_:
                # SPY rounded top while the plan is in stocks: half (or all) to T-bills until it clears
                spx_ = px_all.get('SPY') or {}
                n_sr = 0
                wkend_ = []      # weekly: index of each week's last session, for tf='w' (n counted in weeks)
                if sr_.get('tf') == 'w':
                    for j_, d_ in enumerate(cal):
                        if j_ + 1 == len(cal) or date.fromisoformat(cal[j_ + 1]).isocalendar()[:2] != date.fromisoformat(d_).isocalendar()[:2]:
                            wkend_.append(j_)
                for i_, d_ in enumerate(cal):
                    if modes.get(d_, 'boost') != 'boost' or i_ < sr_['n']:
                        continue
                    if sr_.get('tf') == 'w':
                        prev_ = [j_ for j_ in wkend_[max(0, bisect_right(wkend_, i_ - 1) - sr_['n'] + 1):bisect_right(wkend_, i_ - 1)] if j_ < i_]
                        prev_ = [j_ for j_ in prev_ if date.fromisoformat(cal[j_]).isocalendar()[:2] != date.fromisoformat(d_).isocalendar()[:2]]
                        cs_ = [spx_.get(cal[j_]) for j_ in prev_[-(sr_['n'] - 1):]] + [spx_.get(d_)]
                    else:
                        cs_ = [spx_.get(cal[j_]) for j_ in range(i_ - sr_['n'] + 1, i_ + 1)]
                    if rtop_at(cs_, sr_['n'], sr_['r2'], sr_['mode']):
                        modes[d_] = 'BIL' if sr_.get('full') else 'SIDE:BIL'
                        n_sr += 1
                R.log(f"  {key} SPY rounded-top days {n_sr}")
            bk_ = leg_.get('brake')
            if bk_:
                # holdings brake: an equal-weight index of the Boost stocks held; when it falls bk_['th'] below its
                # 20-session high (and, with 'stretch', the median holding is up more than bk_['stretch'] over 6 months)
                # move part of the account to bk_['to'] while the plan is in stocks; release when the index closes
                # back above its 10-session average
                ixk_ = {d_: i_ for i_, d_ in enumerate(cal)}
                scd_ = dict(sc); cur_, B_, bd_ = None, [], []
                for d_ in cal:
                    if d_ < sc[0][0]:
                        continue
                    k_ = ixk_[d_]
                    if cur_:
                        rs_ = []
                        for t_ in cur_:
                            pt_ = px_all.get(t_) or {}
                            a_, b_ = pt_.get(cal[k_ - 1]), pt_.get(d_)
                            if a_ and b_:
                                rs_.append(b_ / a_ - 1)
                        B_.append((B_[-1] if B_ else 1.0) * (1 + (sum(rs_) / len(rs_) if rs_ else 0.0)))
                    else:
                        B_.append(B_[-1] if B_ else 1.0)
                    bd_.append(d_)
                    if d_ in scd_:
                        cur_ = [t_ for t_, w_ in (scd_[d_] or {}).items() if w_ > 0 and t_ not in ('TLTX', 'GLDX', 'BIL', 'SPY', 'CASH0')]
                def stretched_(d_):
                    k_ = ixk_[d_]
                    st_ = [t_ for t_ in (cur_map_.get(d_) or [])]
                    gs_ = []
                    for t_ in st_:
                        pt_ = px_all.get(t_) or {}
                        a_, b_ = pt_.get(cal[k_ - 126]) if k_ >= 126 else None, pt_.get(d_)
                        if a_ and b_:
                            gs_.append(b_ / a_ - 1)
                    gs_.sort()
                    return bool(gs_) and gs_[len(gs_) // 2] > bk_['stretch']
                cur_map_, cc_ = {}, None
                for d_ in bd_:
                    if d_ in scd_:
                        cc_ = [t_ for t_, w_ in (scd_[d_] or {}).items() if w_ > 0 and t_ not in ('TLTX', 'GLDX', 'BIL', 'SPY', 'CASH0')]
                    cur_map_[d_] = cc_
                on_, n_on = False, 0
                for i_, d_ in enumerate(bd_):
                    if modes.get(d_, 'boost') != 'boost':
                        on_ = False
                        continue
                    hi_ = max(B_[max(0, i_ - 19):i_ + 1]); ma_ = sum(B_[max(0, i_ - 9):i_ + 1]) / len(B_[max(0, i_ - 9):i_ + 1])
                    if not on_:
                        trig_ = B_[i_] / hi_ - 1 <= -bk_['th'] if bk_.get('th') is not None else True
                        if trig_ and bk_.get('stretch') is not None:
                            trig_ = stretched_(d_)
                        on_ = trig_
                    elif bk_.get('th') is not None and B_[i_] > ma_:
                        on_ = False
                    elif bk_.get('th') is None and not stretched_(d_):
                        on_ = False
                    if on_:
                        modes[d_] = bk_['to'] if bk_.get('full') else 'SIDE:' + bk_['to']
                        n_on += 1
                R.log(f"  {key} brake days {n_on}")
            fs_ = leg_.get('fstock')
            reb_days_ = set()
            lh_days_ = lh_set_ if prec_.get('lh_over_reb') else set()
            if fs_:
                # stay in (or get back into) stocks, whatever the other rules say, while SPY is a set % under its
                # 63-session high close and gold / bonds (the better of the two, from the high's date) did a set thing:
                # rules = [(min drop, max drop or None, 'moved' (2%+ either way) | 'rallied' (+2%+) | 'fell' (-2%+))]
                spc_, lst_ = {b_[0]: b_[4] for b_ in bars_src['SPY']}, None
                hpx_ = {t_: {b_[0]: b_[4] for b_ in bars_src[t_]} for t_ in ('TLTX', 'GLDX') if t_ in bars_src}
                scl_ = []
                for d_ in cal:
                    lst_ = spc_.get(d_, lst_)
                    scl_.append(lst_)
                n_fs = 0
                for k_ in range(63, len(cal)):
                    f_ = cal[k_]
                    if f_ < R.START or modes.get(f_, 'boost') == 'boost' or scl_[k_] is None:
                        continue
                    if (prec_.get('nc_over_reb') and f_ in nc_days_) or f_ in lh_days_:
                        continue
                    w_ = [x for x in scl_[k_ - 62:k_ + 1]]
                    if None in w_:
                        continue
                    hi_ = max(w_)
                    a_ = cal[k_ - 62 + w_.index(hi_)]
                    dd_ = 1 - scl_[k_] / hi_
                    mv_ = [hp_[f_] / hp_[a_] - 1 for hp_ in hpx_.values() if a_ in hp_ and f_ in hp_]
                    if not mv_:
                        continue
                    best_ = max(mv_)
                    if fs_.get('hl'):
                        # only once SPY's daily chart (swings 3 days either side) has made a higher low during this drop
                        j_ = bisect_right(bdays['SPY'], f_)
                        dlo_ = [x for x in _fs([tuple(b_) for b_ in bars_src['SPY'][max(0, j_ - 320):j_]], n=3) if x['type'] == 'low']
                        if not (len(dlo_) >= 2 and dlo_[-1]['price'] > dlo_[-2]['price'] and dlo_[-1]['ts'][:10] >= a_):
                            continue
                    for lo_, up_, cond_ in fs_['rules']:
                        if dd_ < lo_ or (up_ is not None and dd_ >= up_):
                            continue
                        if (cond_ == 'moved' and abs(best_) >= 0.02) or (cond_ == 'rallied' and best_ >= 0.02) or \
                                (cond_ == 'fell' and best_ <= -0.02):
                            modes[f_] = 'boost'
                            n_fs += 1
                            reb_days_.add(f_)
                            break
                R.log(f"  {key} stay-in-stocks days {n_fs}")
            if key in os.environ.get('DUMP_FMODES', '').split(','):
                json.dump(modes, open(os.path.join(ROOT, 'data', f'fmodes_{key}.json'), 'w'))
            def mode_w(m_, base_):
                if m_ == 'boost':
                    return base_
                if m_.startswith('WQ:'):
                    _, sh_, al_ = m_.split(':')
                    sh_ = float(sh_); al_ = al_.split('+')
                    w_ = {t_: x_ * sh_ for t_, x_ in (base_ or {}).items()} if sh_ else {}
                    for a_ in al_:
                        w_[a_] = w_.get(a_, 0.0) + (1 - sh_) / len(al_)
                    return w_
                if m_.startswith('SIDE:'):
                    a_ = m_[5:]
                    if side_['mode'] in ('BMIX', 'PBMIX', 'PROTMIX'):
                        sh_ = side_.get('share', 0.5)      # the haven's share of the account while the switch is on
                        w_ = {t_: x_ * (1 - sh_) for t_, x_ in (base_ or {}).items()}
                        w_[a_] = w_.get(a_, 0.0) + sh_
                        return w_
                    return {a_: 1.0}
                if m_ == 'SIDE':
                    sm_ = side_['mode']
                    if sm_ == 'MIX':
                        w_ = {t_: x_ * 0.5 for t_, x_ in (base_ or {}).items()}
                        w_['SPY'] = w_.get('SPY', 0.0) + 0.5
                        return w_
                    return {sm_: 1.0}
                return {m_: 1.0}
            last_w, ws_, sc_map = None, [], dict(sc)
            for d_ in cal:
                if d_ < sc[0][0]:
                    continue
                if d_ in sc_map:
                    last_w = sc_map[d_]
                f_ = cal[idx_[d_] - 1]
                m_ = modes.get(f_, 'boost')
                pm_ = modes.get(cal[idx_[f_] - 1], 'boost') if idx_[f_] > 0 else 'boost'
                if d_ in sc_map or m_ != pm_:
                    ws_.append((d_, mode_w(m_, last_w)))
            sc = ws_
            nb_ = leg_.get('nobil')
            if nb_:
                nbn_ = leg_.get('nobil_n', 126)   # the pick's lookback in sessions (63 in the default since Oct 19, 2026)
                # no T-bills: wherever the plan would hold T-bills, hold instead 'gb' = the stronger of TLT / GLD by
                # 6-month (nobil_n) % change (even if both are falling), or 'cash' = uninvested cash at 0%; a dict
                # {'narrow': .., 'other': ..} treats the narrow-market cash week apart from everything else
                if 'CASH0' not in px_all:
                    px_all['CASH0'] = {d_: 1.0 for d_ in cal}
                try:
                    nar_ = on10
                except NameError:
                    nar_ = set()

                def _rep(d_):
                    f_ = cal[idx_[d_] - 1] if idx_[d_] > 0 else d_
                    kind_ = nb_.get('narrow' if f_ in nar_ else 'other') if isinstance(nb_, dict) else nb_
                    if kind_ == 'cash':
                        return 'CASH0'
                    if kind_ == 'bil':
                        return 'BIL'
                    a_, b_ = pchg('TLTX', f_, nbn_), pchg('GLDX', f_, nbn_)
                    if isinstance(kind_, str) and kind_.startswith('gb:'):
                        # the strongest of the listed assets over 6 months if it is up, else cash at 0%
                        up_ = [(v_, t_) for t_ in kind_[3:].split(',') for v_ in (pchg(t_, f_, nbn_),) if v_ is not None and v_ > 0]
                        return max(up_)[1] if up_ else 'CASH0'
                    if kind_ == 'gbuu':
                        # the strongest of TLT / GLD / the dollar (UUP) over 6 months if it is up, else cash at 0%
                        c_ = pchg('UUPX', f_, nbn_)
                        up_ = [(v_, t_) for v_, t_ in ((a_, 'TLTX'), (b_, 'GLDX'), (c_, 'UUPX')) if v_ is not None and v_ > 0]
                        return max(up_)[1] if up_ else 'CASH0'
                    if isinstance(kind_, str) and kind_.startswith('ts:'):
                        # time check: gold / bonds whose time since its last swing low (weekly or daily swings) is longer
                        # than the drop into it took (from the high before it); 'tu' also needs it up over 6 months.
                        # The one up most over 6 months, else cash at 0%.
                        _, tfh_, hvh_ = kind_.split(':')
                        okh_ = []
                        for t_ in ('TLTX', 'GLDX'):
                            if t_ not in bdays:
                                continue
                            j_ = bisect_right(bdays[t_], f_)
                            dly_ = [tuple(b_) for b_ in bars_src[t_][max(0, j_ - (700 if tfh_ == 'w' else 320)):j_]]
                            bsh_ = weekly(dly_) if tfh_ == 'w' else dly_
                            swh_ = _fs(bsh_, n=2 if tfh_ == 'w' else 3)
                            lsh_ = [x for x in swh_ if x['type'] == 'low']
                            if not lsh_:
                                continue
                            hph_ = [x for x in swh_ if x['type'] == 'high' and x['i'] < lsh_[-1]['i']]
                            if not hph_ or (len(bsh_) - 1 - lsh_[-1]['i']) <= (lsh_[-1]['i'] - hph_[-1]['i']):
                                continue
                            c_ = pchg(t_, f_, nbn_)
                            if hvh_ == 'tu' and (c_ is None or c_ <= 0):
                                continue
                            okh_.append((c_ if c_ is not None else -9, t_))
                        return max(okh_)[1] if okh_ else 'CASH0'
                    if kind_ == 'gbup':
                        # the stronger of TLT / GLD over 6 months (nobil_n) if it is up, else the nobil_fb fund (DBMF,
                        # managed futures, in the default since Oct 20, 2026) once it has begun trading (the live scan
                        # carries its last close over a missing day), else cash at 0%
                        up_ = [(v_, t_) for v_, t_ in ((a_, 'TLTX'), (b_, 'GLDX')) if v_ is not None and v_ > 0]
                        fb_ = leg_.get('nobil_fb')
                        return max(up_)[1] if up_ else fb_ if fb_ and px_all.get(fb_) and min(px_all[fb_]) <= f_ else 'CASH0'
                    return 'TLTX' if (b_ is None or (a_ is not None and a_ >= b_)) else 'GLDX'
                scm_, out_, cur_raw, last_out = dict(sc), [], None, None
                for d_ in cal:
                    if d_ < sc[0][0]:
                        continue
                    if d_ in scm_:
                        cur_raw = scm_[d_]
                    if cur_raw is None:
                        continue
                    if cur_raw.get('BIL'):
                        w2_ = dict(cur_raw); x_ = w2_.pop('BIL'); r_ = _rep(d_); w2_[r_] = w2_.get(r_, 0.0) + x_
                    else:
                        w2_ = cur_raw
                    if d_ in scm_ or w2_ != last_out:
                        out_.append((d_, w2_)); last_out = w2_
                sc = out_
                R.log(f"  {key} no-T-bills days {sum(1 for d_, w_ in sc if any(t_ in w_ for t_ in ('CASH0',)))} cash entries, "
                      f"{sum(1 for d_, w_ in sc if leg_.get('nobil_fb') and leg_['nobil_fb'] in w_)} {leg_.get('nobil_fb')} entries")
            if run.get('fz_frozen') and run.get('spare_cash'):
                # the two-scale buy freeze (live repo mtl/fractal.py slot_haven): a slot left empty at a trade inside a
                # freeze holds the haven pick (the stronger of TLT / GLD over 63 sessions if it is up, else nobil_fb, else
                # cash), read at the close before that trade, until the next trade
                from bisect import bisect_right as _bz
                frz3_ = run['fz_frozen']
                pkd_ = sorted(p_[0] for p_ in run['picks'])
                fb3_ = leg_.get('nobil_fb')
                hvs_ = {'TLTX', 'GLDX', 'DBMF', 'CASH0', 'BIL', 'UUPX', 'SPY'}

                def hpick3_(f_):
                    a_, b_ = pchg('TLTX', f_, 63), pchg('GLDX', f_, 63)
                    up_ = [(v_, t_) for v_, t_ in ((a_, 'TLTX'), (b_, 'GLDX')) if v_ is not None and v_ > 0]
                    return max(up_)[1] if up_ else fb3_ if fb3_ and px_all.get(fb3_) and min(px_all[fb3_]) <= f_ else 'CASH0'
                out3_, n_fz = [], 0
                for d_, w_ in sc:
                    j_ = _bz(pkd_, d_) - 1
                    if j_ >= 0 and idx_.get(pkd_[j_]) in frz3_ and w_.get('CASH0') and any(t_ not in hvs_ for t_ in w_):
                        tr_ = pkd_[j_]
                        h3_ = hpick3_(cal[idx_[tr_] - 1])
                        if h3_ != 'CASH0':
                            w_ = dict(w_); x_ = w_.pop('CASH0'); w_[h3_] = w_.get(h3_, 0.0) + x_; n_fz += 1
                    out3_.append((d_, w_))
                sc = out3_
                R.log(f"  {key} buy freeze: {len(frz3_)} frozen sessions, {len(run.get('fz_green') or ())} green-light sessions, "
                      f"{n_fz} schedule entries with an empty slot in the haven pick")
            pb_ = leg_.get('pbreak')
            if pb_:
                # the price-break haven rule (mtl/pricebreak.py): the day SPY closes under its slow-day average for the first time
                # while that average and its fast-day average are both lower than `slope` sessions earlier, the haven pick (the
                # stronger of TLT / GLD over nobil_n sessions if it is up, else nobil_fb) for the break day and `hold` sessions
                # after it, wherever the plan would hold stocks. Decided at that close, traded at the next, like the rest.
                sl_, fa_, sp_n, ho_ = pb_['slow'], pb_['fast'], pb_['slope'], pb_['hold']
                cl_ = [px_all['SPY'].get(d_) for d_ in cal]

                def avg_(k_, n_):
                    w_ = cl_[k_ - n_ + 1:k_ + 1] if k_ >= n_ - 1 else []
                    return sum(w_) / n_ if len(w_) == n_ and None not in w_ else None
                brk_days = []
                for k_ in range(sl_ + sp_n, len(cal)):
                    if cl_[k_] is None or cl_[k_ - 1] is None:
                        continue
                    s0, s1, s5 = avg_(k_, sl_), avg_(k_ - 1, sl_), avg_(k_ - sp_n, sl_)
                    f0, f5 = avg_(k_, fa_), avg_(k_ - sp_n, fa_)
                    if None in (s0, s1, s5, f0, f5):
                        continue
                    if cl_[k_] < s0 and cl_[k_ - 1] >= s1 and s0 < s5 and f0 < f5:
                        brk_days.append(k_)
                pbh_ = {cal[j_] for k_ in brk_days for j_ in range(k_, min(len(cal), k_ + ho_ + 1))}
                nbn2_ = leg_.get('nobil_n', 126)
                hv_ = {'TLTX', 'GLDX', 'DBMF', 'CASH0', 'BIL', 'UUPX'}
                fb2_ = leg_.get('nobil_fb')

                def hpick_(f_):
                    a_, b_ = pchg('TLTX', f_, nbn2_), pchg('GLDX', f_, nbn2_)
                    up_ = [(v_, t_) for v_, t_ in ((a_, 'TLTX'), (b_, 'GLDX')) if v_ is not None and v_ > 0]
                    return max(up_)[1] if up_ else fb2_ if fb2_ and px_all.get(fb2_) and min(px_all[fb2_]) <= f_ else 'CASH0'
                scm2_, out_, cur_w, last_out, n_pb = dict(sc), [], None, None, 0
                for d_ in cal:
                    if d_ < sc[0][0]:
                        continue
                    if d_ in scm2_:
                        cur_w = scm2_[d_]
                    if cur_w is None:
                        continue
                    f_ = cal[idx_[d_] - 1] if idx_[d_] > 0 else d_
                    w2_ = cur_w
                    if f_ in pbh_ and idx_[f_] >= 63 and any(t_ not in hv_ for t_ in cur_w) and not (prec_.get('reb_over_pb') and f_ in reb_days_):
                        w2_ = {hpick_(f_): 1.0}; n_pb += 1
                    if d_ in scm2_ or w2_ != last_out:
                        out_.append((d_, w2_)); last_out = w2_
                sc = out_
                R.log(f"  {key} price-break rule: {len(brk_days)} breaks, {n_pb} days in a haven instead of stocks")
            dp_ = leg_.get('dip')
            if dp_:
                # a held Boost stock that closed down dp_['th'] or more on the day: buy the dip at the next close,
                # either back to the plan's weights ('eq') or overweight it x dp_['m'] for dp_['hold'] sessions
                scd = dict(sc); new_ = dict(scd); cur_, rev_, n_dip, ow_ = None, {}, 0, {}
                for k_ in range(2, len(cal)):
                    d_ = cal[k_]
                    if d_ < sc[0][0]:
                        continue
                    if d_ in scd:
                        cur_ = scd[d_]; rev_ = {} if not dp_.get('persist') else rev_
                        if dp_.get('persist'):
                            # keep live overweights through the weekly rebalance while the stock is still held
                            act = {t_ for t_, (u_, _) in ow_.items() if u_ > d_ and cur_.get(t_)}
                            if act:
                                w2 = dict(cur_); tot = sum(w2.values())
                                for t_ in act:
                                    w2[t_] *= dp_['m']
                                sc2 = tot / sum(w2.values()); new_[d_] = {t_: v * sc2 for t_, v in w2.items()}
                    elif d_ in rev_ and cur_:
                        act = {t_ for t_, (u_, _) in ow_.items() if u_ > d_ and cur_.get(t_)} if dp_.get('persist') else set()
                        w2 = dict(cur_); tot = sum(w2.values())
                        for t_ in act:
                            w2[t_] *= dp_['m']
                        sc2 = tot / sum(w2.values()); new_[d_] = {t_: v * sc2 for t_, v in w2.items()}; del rev_[d_]
                    f_, g_ = cal[k_ - 1], cal[k_ - 2]
                    if modes.get(f_, 'boost') != 'boost' or not cur_ or d_ in scd:
                        continue
                    drops = [t_ for t_, w_ in cur_.items() if w_ > 0 and t_ not in ('TLTX', 'GLDX', 'BIL', 'SPY', 'CASH0', 'DBMF')
                             and (px_all.get(t_) or {}).get(f_) and (px_all.get(t_) or {}).get(g_)
                             and px_all[t_][f_] / px_all[t_][g_] - 1 <= -dp_['th']]
                    if not drops:
                        continue
                    n_dip += 1
                    if dp_['how'] == 'eq':
                        new_[d_] = dict(cur_)
                    else:
                        tot = sum(cur_.values()); w2 = dict(cur_)
                        for t_ in drops:
                            w2[t_] = w2[t_] * dp_['m']
                            if k_ + dp_['hold'] < len(cal):
                                ow_[t_] = (cal[k_ + dp_['hold']], d_)
                        sc2 = tot / sum(w2.values()); new_[d_] = {t_: v * sc2 for t_, v in w2.items()}
                        if k_ + dp_['hold'] < len(cal):
                            rev_[cal[k_ + dp_['hold']]] = True
                sc = sorted(new_.items())
                R.log(f"  {key} dip buys: {n_dip}")
            json.dump(modes, open(os.path.join(ROOT, 'data', f'rot_modes_{key}.json'), 'w'))
        mp_ = (run.get('plan') or {}).get('manualplan')
        if mp_:
            # [(from, mode)] in date order; mode: boost (unchanged), bonds (100% TLT), cash (100% BIL),
            # cushion (75% stocks / 25% best sleeve fund while SPY < 150-day and HYG lags LQD)
            idx_ = {d_: i_ for i_, d_ in enumerate(cal)}
            hy_ = G['REG']['c_hy']
            have = {d_ for d_, _ in sc}
            extra = []
            for a_, _m in mp_:      # a trade on each switch day, not only on the strategy's own trade days
                if a_ in idx_ and idx_[a_] + 1 < len(cal):
                    T_ = cal[idx_[a_] + 1]
                    if T_ not in have and sc and T_ > sc[0][0]:
                        prev_w = [w for d_, w in sc if d_ < T_][-1]
                        extra.append((T_, prev_w))
            sc = sorted(sc + extra, key=lambda x: x[0])
            sc2 = []
            for d_, w in sc:
                f_ = cal[idx_[d_] - 1]
                mode_ = 'boost'
                for a_, m_ in mp_:
                    if f_ >= a_:
                        mode_ = m_
                if mode_ == 'bonds':
                    sc2.append((d_, {'TLT': 1.0}))
                elif mode_ == 'cash':
                    sc2.append((d_, {'BIL': 1.0}))
                elif mode_ == 'cushion' and not hy_.get(f_, True):
                    asset = best_of(P['sleeve_f'], cal, idx_[f_])
                    w2 = {t: x * 0.75 for t, x in w.items()}
                    w2[asset] = w2.get(asset, 0.0) + 0.25 * sum(w.values()) + (1 - sum(w.values()))
                    sc2.append((d_, w2))
                else:
                    sc2.append((d_, w))
            sc = sc2
        pre = R.simulate(sc, px_all, cal, SLIP, taxes=False)
        tax = R.simulate(sc, px_all, cal, SLIP, taxes=True)
        st = R.stats(pre['curve'], 0.015)
        yrs = len(tax['curve']) / 252
        w3 = yr_windows(pre['curve'], spy, starts)
        ystats = {}
        c = pre['curve']
        for y in range(int(R.START[:4]), int(cal[-1][:4]) + 1):
            pts = [v for d, v in c if d[:4] == str(y)]
            prev = [v for d, v in c if d[:4] == str(y - 1)]
            if pts:
                ystats[y] = round((pts[-1] / (prev[-1] if prev else pts[0]) - 1), 4)
        near = sells = 0
        if run.get('picks') and 'XF' in G:
            idx2 = {d_: i_ for i_, d_ in enumerate(cal)}
            pk_ = run['picks']
            for (d0, h0), (d1, h1) in zip(pk_, pk_[1:]):
                for t in set(h0) - set(h1):
                    a = G['XF'](t)
                    i_ = idx2.get(d1)
                    if a is None or i_ is None or a['c'][i_] != a['c'][i_]:
                        continue
                    win = a['c'][max(0, i_ - 63):i_ + 64]
                    sells += 1
                    near += a['c'][i_] >= 0.9 * _np.nanmax(win)
        return sc, pre, dict(
            preTax=R.s4(st), afterTax=R.r4((tax['final'] / R.START_CASH) ** (1 / yrs) - 1),
            afterTaxSharpe=R.r4(R.stats(tax['curve'], 0.015).get('sharpe')),
            afterTaxDD=R.r4(R.stats(tax['curve'], 0.015).get('maxDD')),
            longestHold=longest_hold(sc),
            btcWeeks=sum(1 for _, w in sc if w.get('BTC-USD', 0) > 0),
            btcMax=R.r4(max((w.get('BTC-USD', 0) for _, w in sc), default=0)),
            final=round(tax['final'], 2), finalPre=round(pre['final'], 2),
            taxPaid=round(tax['taxPaid'], 2), wash=round(tax['wash'], 2), stShare=R.r4(tax['stShare']),
            turnover=R.r4(pre['turnover']),
            first=R.r4(R.cagr_between(c, R.START, '2019-12-31')), second=R.r4(R.cagr_between(c, '2020-01-01', cal[-1])),
            p0009=R.r4(R.cagr_between(c, R.START, '2009-12-31')) if R.START < '2009' else None,
            p0009after=R.r4(R.cagr_between(tax['curve'], R.START, '2009-12-31')) if R.START < '2009' else None,
            dd0009=R.r4(R.stats([p_ for p_ in c if p_[0] <= '2009-12-31'], 0.015).get('maxDD')) if R.START < '2009' else None,
            win3=list(w3), years=ystats, nearTop=round(near / sells, 3) if sells else None, sells=sells,
            avgStock=R.r4(sum(sum(x for t, x in w.items() if t not in ASSETS) for _, w in sc) / len(sc)),
            lowWeeks=R.r4(sum(1 for _, w in sc if any(t in ASSETS and t != 'BIL' for t in w)) / len(sc)))

    res, scheds = {}, {}
    for key, run in list(runs.items()):
        sc, pre, out = evaluate(key, run)
        res[key] = out
        scheds[key] = sc
        if os.environ.get('DUMP_SCHED') == key:
            tk_ = sorted({t_ for _, w_ in sc for t_ in w_} | {'SPY'})
            json.dump(dict(sched=sc, prices={t_: px_all.get(t_, {}) for t_ in tk_}),
                      open(os.path.join(ROOT, 'data', f"sched_{key}{os.environ.get('TAG', '')}.json"), 'w'))
            R.log(f"  wrote sched_{key}")
        R.log(f"  {key}: pre {out['preTax'].get('cagr')} after {out['afterTax']}")
        if key.startswith(('cur_', 'n5m_')):
            sk = key + '_slot'
            sc2, _, out2 = evaluate(sk, slot_weights(run))
            res[sk] = out2
            scheds[sk] = sc2
            R.log(f"  {sk}: pre {out2['preTax'].get('cagr')} after {out2['afterTax']}")

    # two engines side by side: fixed capital split between two independent plans
    def combine(sa, sb, wa):
        da, db = dict(sa), dict(sb)
        dates = sorted(set(da) | set(db))
        ia = ib = None
        out = []
        for T in dates:
            ia = da.get(T, ia)
            ib = db.get(T, ib)
            if ia is None or ib is None:
                continue
            w = {}
            for t, x in ia.items():
                w[t] = w.get(t, 0.0) + wa * x
            for t, x in ib.items():
                w[t] = w.get(t, 0.0) + (1 - wa) * x
            out.append((T, w))
        return out
    for name, a_k, b_k, wa in (('two50', 'ldt2x', 'cur', 0.5), ('two70', 'ldt2x', 'cur', 0.7)):
        for side in ('auto', 'boost'):
            ka, kb = f'{a_k}_auto', f'{b_k}_{side}'
            if ka in scheds and kb in scheds:
                key = f'{name}_{side}'
                _, _, out = evaluate(key, dict(sched=combine(scheds[ka], scheds[kb], wa)))
                res[key] = out
                R.log(f"  {key}: pre {out['preTax'].get('cagr')} after {out['afterTax']}")
    # adaptive breadth: top 5 while enough stocks doubled over the last year, else the top-10 plan
    if 'SLb12_boost' in scheds and any(k in scheds for k in ('SL10_boost', 'SL10L_boost')):
        pxa, el_, ci_ = P['prices'], P['elig_pit'], {d_: i_ for i_, d_ in enumerate(cal)}
        dcache = {}

        def ndbl(d_):
            if d_ not in dcache:
                i_ = ci_[d_]
                a_ = cal[i_ - 252] if i_ >= 252 else None
                n_ = 0
                if a_:
                    for t_, px_ in pxa.items():
                        if t_ in ('SPY',) or not el_(t_, d_):
                            continue
                        p0_, p1_ = px_.get(a_), px_.get(d_)
                        if p0_ and p1_ and p1_ / p0_ >= 2.0:
                            n_ += 1
                dcache[d_] = n_
            return dcache[d_]

        def switch(sa, sb, thr):
            da, db = dict(sa), dict(sb)
            ia = ib = None
            out, last, used = [], None, {}
            for T in sorted(set(da) | set(db)):
                ia = da.get(T, ia)
                ib = db.get(T, ib)
                if ia is None or ib is None:
                    continue
                f_ = cal[ci_[T] - 1]
                use_b = ndbl(f_) < thr
                w = ib if use_b else ia
                used.setdefault(T[:4], []).append(use_b)
                if w != last:
                    out.append((T, w))
                    last = w
            return out, used
        for bk in ('SL10', 'SL10L'):
            if f'{bk}_boost' not in scheds:
                continue
            for thr in (3, 4, 6):
                key = f'DB{thr}{bk}_boost'
                sc_, used = switch(scheds['SLb12_boost'], scheds[f'{bk}_boost'], thr)
                _, _, out = evaluate(key, dict(sched=sc_))
                res[key] = out
                R.log(f"  {key}: pre {out['preTax'].get('cagr')} after {out['afterTax']}  top10 share by year: " + ' '.join(f"{y}:{sum(v)/len(v):.0%}" for y, v in sorted(used.items())))
        R.log('  doublers (last 252 sessions) at each year start: ' + ' '.join(f"{d_[:4]}:{ndbl(d_)}" for d_ in cal if d_ >= R.START and (cal[ci_[d_] - 1][:4] != d_[:4])))
    extra = {}
    if only:
        global OUT
        OUT = OUT.replace('improve.json', 'improve_only' + os.environ.get('TAG', '') + '.json')
    # concentration check on the new rule
    for key in (() if only else ('v2_auto', 'v2_boost')):
        pass
    if not only:
        extra = concentration(runs, scheds, px_all, cal, P, evaluate)

    yrs = len(spy) / 252
    spy_t = R.bench_after_tax(D, 'SPY', cal, R.START)
    qqq_t = R.bench_after_tax(D, 'QQQ', cal, R.START)
    if os.environ.get('DUMP_CURVES'):
        def me(c):
            out = {}
            for d_, v_ in c:
                out[d_ if os.environ.get('DUMP_DAILY') else d_[:7]] = [d_, round(v_, 2)]
            return list(out.values())
        dump = {}
        for key in list(scheds):
            if not key.startswith(tuple(os.environ['DUMP_CURVES'].split(','))):
                continue
            pre_ = R.simulate(scheds[key], px_all, cal, SLIP, taxes=False)
            tax_ = R.simulate(scheds[key], px_all, cal, SLIP, taxes=True)
            dump[key] = dict(pre=me(pre_['curve']), tax=me(tax_['curve']), finalPre=pre_['final'], finalTax=tax_['final'],
                             preLiq=tax_.get('preLiq'), taxPaid=tax_.get('taxPaid'))
        dump['spy'] = dict(pre=me(spy), tax=me(spy_t['curve']), finalTax=spy_t['final'], preLiq=spy_t['preLiq'])
        dump['qqq'] = dict(pre=me(qqq), tax=me(qqq_t['curve']), finalTax=qqq_t['final'], preLiq=qqq_t['preLiq'])
        with open(os.path.join(ROOT, 'data', 'curves_dump' + os.environ.get('TAG', '') + '.json'), 'w') as fh:
            json.dump(dict(start=R.START, end=cal[-1], series=dump), fh)
        R.log('wrote curves_dump.json')
    bench = {}
    for k, c, t in (('spy', spy, spy_t), ('qqq', qqq, qqq_t)):
        w3 = yr_windows(c, spy, starts)
        ystats = {}
        for y in range(int(R.START[:4]), int(cal[-1][:4]) + 1):
            pts = [v for d, v in c if d[:4] == str(y)]
            prev = [v for d, v in c if d[:4] == str(y - 1)]
            if pts:
                ystats[y] = round((pts[-1] / (prev[-1] if prev else pts[0]) - 1), 4)
        bench[k] = dict(preTax=R.s4(R.stats(c, 0.015)), afterTax=R.r4((t['final'] / R.START_CASH) ** (1 / yrs) - 1),
                        final=round(t['final'], 2), first=R.r4(R.cagr_between(c, R.START, '2019-12-31')),
                        p0009=R.r4(R.cagr_between(c, R.START, '2009-12-31')) if R.START < '2009' else None,
                        dd0009=R.r4(R.stats([p_ for p_ in c if p_[0] <= '2009-12-31'], 0.015).get('maxDD')) if R.START < '2009' else None,
                        second=R.r4(R.cagr_between(c, '2020-01-01', cal[-1])), win3=list(w3), years=ystats)
    payload = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), start=R.START, end=cal[-1],
                   slip=SLIP, results=res, concentration=extra, bench=bench,
                   runtimeMin=round((datetime.now() - t0).total_seconds() / 60, 1))
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    R.log(f"wrote {OUT} in {payload['runtimeMin']} min")


if __name__ == '__main__':
    main()

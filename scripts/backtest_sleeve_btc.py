#!/usr/bin/env python3
"""Best-of sleeve with and without BTC-USD as a seventh choice, alone and in the
60/40 plan at x1.0/1.3/1.5 (6% margin), since 2020.

Usage:
    python scripts/backtest_sleeve_btc.py
"""
import sys; import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest_leverage import *
from backtest_drawdown import row
from momentum_scan import fetch
from mtl.sleeve import sleeve_curve, plan_curve, ASSETS
from collections import Counter
names = default_universe(refresh=False); raw, bench = load_data(list(names)); extra = load_extra(); added = load_added()
px = load_assets()
btc = fetch(['BTC-USD'], start='2018-06-01', adjusted=True)['BTC-USD']; px['BTC-USD'] = {b[0]: b[4] for b in btc}
sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
comb = {t: {b[0][:10]: b[4] for b in raw[t]['daily']} for t in sp}
comb.update({t: {b[0][:10]: b[4] for b in bars} for t, bars in extra.items()}); comb['SPY']=dict(bench['SPY'])
cal=[d for d,_ in bench['SPY']]
member=lambda t,d: t in extra or added.get(t,'0000')<=d
top5=[p[:2] for p in run_momentum(comb,cal,START,look=126,skip=21,top_n=5,eligible=member)['curve']]
print(f"{'':30} {'total':>8} {'CAGR':>5} {'maxDD':>6} {'ret/DD':>6} | {'2020-24':>8} {'2025-26':>8} | windows")
row('top 5 alone', top5)
for lab, assets in [('sleeve (current 6)', ASSETS), ('sleeve + BTC', ASSETS+['BTC-USD'])]:
    sc, picks = sleeve_curve(px, cal, START, assets=assets)
    print('--', lab); row('  sleeve alone', sc)
    for lev in (1.0, 1.3, 1.5):
        row(f'  60/40 x{lev}', plan_curve(top5, sc, .6*lev, .4*lev, cal, .06))
    if 'BTC-USD' in assets:
        held = {}
        cur=None; pk=dict(picks); 
        for d in cal:
            if d < START: continue
            cur = pk.get(d, cur); held.setdefault(d[:4], Counter())[cur]+=1
        for y in sorted(held): print('   ', y, dict(held[y]))
row('BTC buy & hold', [[d, px['BTC-USD'][d]] for d in cal if d>=START and d in px['BTC-USD']])

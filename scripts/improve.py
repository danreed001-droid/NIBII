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
import os
import sys
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from multiprocessing import get_context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robustness as R  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.news import booster  # noqa: E402
from mtl.sleeve import ASSETS, best_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    'n12w': (dict(top_n=12), None),
    'n12m': (dict(top_n=12, monthly=True), None),
    'n12m_ra': (dict(top_n=12, monthly=True, risk_adj=True), None),
    'v2': (dict(top_n=12, monthly=True, risk_adj=True, vol_target=0.20, vol_window=126), None),
}


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
    ex = set(exclude)
    elig = (lambda t, d: t not in ex and base(t, d)) if ex else base
    kw = dict(kw)
    monthly = kw.pop('monthly', False)
    accel = kw.pop('accel', None)
    boost_rank = kw.pop('boost_rank', None)
    sig = kw.pop('sig_exit', None)
    plan = kw.pop('plan', None)
    cap = kw.pop('sector_cap', None)
    if cap:
        import csv
        with open(os.path.join(ROOT, 'data', 'industries.csv')) as fh:
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
    opts = dict(look=R.LOOK, skip=R.SKIP, eligible=elig, exec_next='close')
    opts.update(kw)
    if monthly:
        opts['rebal_dates'] = set(G['months'])
    if boost:
        opts.update(prefer=booster(P['gaps'], P['calendar']), prefer_mode='force', prefer_rank=boost_rank,
                    prefer_pool='all')
    r = run_momentum(P['prices'], P['calendar'], R.START, **opts)
    return key, dict(picks=r['picks'], weights=r['weights'], turnover=r['turnover'], plan=plan)


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
        f = calendar[idx[T] - 1]
        j = bisect_right(pdays, f) - 1
        before = picks[j][1] if j >= 0 else []
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
            out_w['BIL'] = out_w.get('BIL', 0.0) + spare
        if split < 1:
            if (po.get('cash') and G['spy_below'](f)) or (po.get('cash3') and n_down >= 3):
                a = 'BIL'
            else:
                a = best_of(sleeve_f, calendar, idx[f])
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
    with get_context('fork').Pool(4) as pool:
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
    P = R.prepare(D)
    G['P'] = P
    R.G['P'] = P
    cal = P['calendar']
    G['months'] = month_ends(cal)
    down = R.downtrend_fn(D['bars'])
    px_all = dict(P['prices'])
    px_all.update(P['sleeve_px'])
    px_all['QQQ'] = {b[0]: b[4] for b in D['bench']['QQQ']}
    spx = P['prices']['SPY']
    sma_ok = {}
    for k_ in range(200, len(cal)):
        w_ = [spx.get(cal[j]) for j in range(k_ - 199, k_ + 1)]
        if all(w_):
            sma_ok[cal[k_]] = spx[cal[k_]] < sum(w_) / 200
    G['spy_below'] = lambda d_: sma_ok.get(d_, False)
    G['spy_down'] = R.downtrend_fn({'SPY': D['bench']['SPY']})
    G['spy_down'] = (lambda f_, _d=G['spy_down']: _d('SPY', f_))
    spy = [[b[0], b[4]] for b in D['bench']['SPY'] if b[0] >= R.START]
    qqq = [[b[0], b[4]] for b in D['bench']['QQQ'] if b[0] >= R.START]
    starts = [d for d in (next((x for x in cal if x >= f'{y}-{m}-01'), None)
                          for y in range(2010, 2024) for m in ('01', '07')) if d and d >= R.START]

    jobs = []
    only = [x for x in os.environ.get('ONLY', '').split(',') if x]
    for name, (kw, _) in VARIANTS.items():
        if only and name not in only:
            continue
        jobs.append((f'{name}_auto', kw, False, ()))
        jobs.append((f'{name}_boost', kw, True, ()))
    runs = {}
    with get_context('fork').Pool(4) as pool:
        for key, res in pool.imap_unordered(run_one, jobs):
            runs[key] = res
            R.log(f"  run done: {key}")

    def evaluate(key, run):
        sc = schedule(run, cal, P['sleeve_f'], down, R.START)
        pre = R.simulate(sc, px_all, cal, SLIP, taxes=False)
        tax = R.simulate(sc, px_all, cal, SLIP, taxes=True)
        st = R.stats(pre['curve'], 0.015)
        yrs = len(tax['curve']) / 252
        w3 = yr_windows(pre['curve'], spy, starts)
        ystats = {}
        c = pre['curve']
        for y in range(2010, int(cal[-1][:4]) + 1):
            pts = [v for d, v in c if d[:4] == str(y)]
            prev = [v for d, v in c if d[:4] == str(y - 1)]
            if pts:
                ystats[y] = round((pts[-1] / (prev[-1] if prev else pts[0]) - 1), 4)
        return sc, pre, dict(
            preTax=R.s4(st), afterTax=R.r4((tax['final'] / R.START_CASH) ** (1 / yrs) - 1),
            afterTaxSharpe=R.r4(R.stats(tax['curve'], 0.015).get('sharpe')),
            afterTaxDD=R.r4(R.stats(tax['curve'], 0.015).get('maxDD')),
            longestHold=longest_hold(sc),
            final=round(tax['final'], 2), finalPre=round(pre['final'], 2),
            taxPaid=round(tax['taxPaid'], 2), wash=round(tax['wash'], 2), stShare=R.r4(tax['stShare']),
            turnover=R.r4(pre['turnover']),
            first=R.r4(R.cagr_between(c, R.START, '2019-12-31')), second=R.r4(R.cagr_between(c, '2020-01-01', cal[-1])),
            win3=list(w3), years=ystats,
            avgStock=R.r4(sum(sum(x for t, x in w.items() if t not in ASSETS) for _, w in sc) / len(sc)),
            lowWeeks=R.r4(sum(1 for _, w in sc if any(t in ASSETS and t != 'BIL' for t in w)) / len(sc)))

    res, scheds = {}, {}
    for key, run in list(runs.items()):
        sc, pre, out = evaluate(key, run)
        res[key] = out
        scheds[key] = sc
        R.log(f"  {key}: pre {out['preTax'].get('cagr')} after {out['afterTax']}")
        if key.startswith(('cur_', 'n5m_')):
            sk = key + '_slot'
            sc2, _, out2 = evaluate(sk, slot_weights(run))
            res[sk] = out2
            scheds[sk] = sc2
            R.log(f"  {sk}: pre {out2['preTax'].get('cagr')} after {out2['afterTax']}")

    extra = {}
    if only:
        global OUT
        OUT = OUT.replace('improve.json', 'improve_only.json')
    # concentration check on the new rule
    for key in (() if only else ('v2_auto', 'v2_boost')):
        pass
    if not only:
        extra = concentration(runs, scheds, px_all, cal, P, evaluate)

    yrs = len(spy) / 252
    spy_t = R.bench_after_tax(D, 'SPY', cal, R.START)
    qqq_t = R.bench_after_tax(D, 'QQQ', cal, R.START)
    bench = {}
    for k, c, t in (('spy', spy, spy_t), ('qqq', qqq, qqq_t)):
        w3 = yr_windows(c, spy, starts)
        ystats = {}
        for y in range(2010, int(cal[-1][:4]) + 1):
            pts = [v for d, v in c if d[:4] == str(y)]
            prev = [v for d, v in c if d[:4] == str(y - 1)]
            if pts:
                ystats[y] = round((pts[-1] / (prev[-1] if prev else pts[0]) - 1), 4)
        bench[k] = dict(preTax=R.s4(R.stats(c, 0.015)), afterTax=R.r4((t['final'] / R.START_CASH) ** (1 / yrs) - 1),
                        final=round(t['final'], 2), first=R.r4(R.cagr_between(c, R.START, '2019-12-31')),
                        second=R.r4(R.cagr_between(c, '2020-01-01', cal[-1])), win3=list(w3), years=ystats)
    payload = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), start=R.START, end=cal[-1],
                   slip=SLIP, results=res, concentration=extra, bench=bench,
                   runtimeMin=round((datetime.now() - t0).total_seconds() / 60, 1))
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    R.log(f"wrote {OUT} in {payload['runtimeMin']} min")


if __name__ == '__main__':
    main()

"""Class-layer check on a weekly, 5-day horizon, with combinatorial purged cross-validation (CPCV).

Question: does teaching the stock ranking a layer of classes (macro-sector, size, volatility, market season) pick
better stocks than the plain ranking? Everything is graded on the exact horizon of a weekly trade.

Steps
  1. Universe: S&P 500 members at each date (delisted ones included), from the engine's data cache.
  2. Classes, measured with data up to each Friday:
       macro-sector  5 groups (reviewer's map of the 11 sectors),
       size          thirds by trailing 1-year average daily trading value (free data has no history of market
                     cap, so trading value stands in for it),
       volatility    thirds by trailing 1-year daily volatility,
       season        4 market seasons from a k-means on 8 monthly measures (S&P 500 12- and 3-month returns, VIX,
                     CPI inflation, 3-month T-bill rate and its 12-month change, gold and oil 12-month changes).
  3. Target: the 5-trading-day return from the next close (when a weekly trade is placed).
  4. Size check: assert every macro-sector is at least 10% of the FULL dataset (by stock-weeks and by trading
     value). Subsets are only reported, so shifts between periods show.
  5. CPCV on 2000-2015: 6 time groups, 2 held out per split (15 splits, 5 paths), training weeks purged before
     and embargoed after each held-out group. A ridge regression with class x signal interactions is fitted on the
     training groups (its strength chosen inside them) and its weekly top 5 is compared with the plain top 5.
  6. Chronological check on 2016-2026: learn on everything before 2021 (then before 2024), score 2021-2023
     and 2024 on.
  7. Every 1-, 2- and 3-class combination: edge of the top-ranked 10% inside it, found on 2000-2020, checked on
     2021-2023 and 2024 on, with a Benjamini-Hochberg false-discovery check.

The ranking signal used here is a simplified weekly version (6-month change, skipping the last month), so the
figures describe stock selection only, without the risk layer.

usage:
  python research/validation/class_cpcv.py --engine <engine folder> --side <side data folder> [--repo .]
         [--cpi CPIAUCSL.csv] [--out class_cpcv.json]
The engine folder must hold the data cache (data/.robust_1998-06-01.pkl); the side folder is the one the
backtest uses (stock_volume.npz, vix_irx.json, xasset.json). Without --cpi the CPI series is read from FRED.
"""
import argparse
import csv
import io
import itertools
import json
import math
import os
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date

import numpy as np

MACRO = {'Information Technology': 'Technology', 'Communication Services': 'Technology',
         'Financials': 'Financials', 'Real Estate': 'Financials', 'Health Care': 'Healthcare',
         'Consumer Discretionary': 'Consumer', 'Consumer Staples': 'Consumer',
         'Industrials': 'Industrials_Energy', 'Energy': 'Industrials_Energy', 'Materials': 'Industrials_Energy',
         'Utilities': 'Industrials_Energy'}
MACROS = ['Technology', 'Financials', 'Healthcare', 'Consumer', 'Industrials_Energy']
# companies that left the index and have no sector in the repo's lists
MANUAL = {'QRVO': 'Information Technology', 'AVB': 'Real Estate', 'SUN': 'Energy', 'EA': 'Communication Services',
          'GENZ': 'Health Care', 'PSKY': 'Communication Services', 'BBWI': 'Consumer Discretionary',
          'FLS': 'Industrials', 'HOG': 'Consumer Discretionary', 'KG': 'Health Care', 'MBI': 'Financials',
          'R': 'Industrials', 'WU': 'Financials', 'AMTM': 'Industrials', 'ETSY': 'Consumer Discretionary',
          'LKQ': 'Consumer Discretionary', 'WBD': 'Communication Services'}
RULES = [(('Electric Utilities', 'Water Supply', 'Power Generation', 'Natural Gas Distribution'), 'Utilities'),
         (('Real Estate',), 'Real Estate'),
         (('Oil', 'Gas', 'Coal', 'Petroleum'), 'Energy'),
         (('Bank', 'Insurance', 'Investment', 'Finance', 'Broker', 'Savings', 'Credit', 'Trust'), 'Financials'),
         (('Biotech', 'Pharma', 'Medical', 'Dental', 'Hospital', 'Health', 'Ophthalmic'), 'Health Care'),
         (('Telecommunications Equipment', 'Computer', 'Software', 'Semiconductor', 'Electronic', 'EDP',
           'Radio And Television Broadcasting And Communications Equipment'), 'Information Technology'),
         (('Telecommunication', 'Broadcasting', 'Cable', 'Newspaper', 'Publishing', 'Advertising', 'Movies',
           'Entertainment'), 'Communication Services'),
         (('Food', 'Beverage', 'Tobacco', 'Farming', 'Grocery', 'Household', 'Cosmetic', 'Packaged'), 'Consumer Staples'),
         (('Chemical', 'Metal', 'Steel', 'Aluminum', 'Mining', 'Container', 'Packaging', 'Paper', 'Forest', 'Plastic',
           'Precious'), 'Materials'),
         (('Retail', 'Apparel', 'Garment', 'Furnishing', 'Auto', 'Restaurant', 'Hotel', 'Recreational',
           'Consumer Specialties', 'Other Consumer Services', 'Homebuilding', 'Clothing', 'Shoe', 'Department',
           'Catalog', 'Leisure'), 'Consumer Discretionary'),
         (('Aerospace', 'Industrial', 'Machinery', 'Railroad', 'Trucking', 'Air Freight', 'Construction', 'Electrical',
           'Office Equipment', 'Engineering', 'Diversified', 'Building', 'Marine', 'Transportation', 'Professional',
           'Military', 'Tools', 'Pollution', 'Environmental'), 'Industrials')]
SEASONS = ['Bear / crisis', 'Bull, near-zero rates', 'Bull, normal rates', 'Inflation / rising rates']
NG, KT, PURGE, EMB = 6, 2, 1, 8           # CPCV: groups, held out per split, weeks purged before / embargoed after
LAMS = (30, 300, 3000, 30000)


def sectors(repo):
    sec = {r['symbol']: r['sector'] for r in csv.DictReader(open(os.path.join(repo, 'data', 'sp500.csv')))}
    ind = {r['symbol']: r['industry'] for r in csv.DictReader(open(os.path.join(repo, 'data', 'industries_all.csv')))}

    def of(t):
        if t in sec:
            return sec[t]
        if t in MANUAL:
            return MANUAL[t]
        s = ind.get(t, '').lower()
        for keys, lab in RULES:
            if any(k.lower() in s for k in keys):
                return lab
        return None
    return of


def month_last(d):
    o = {}
    for k in sorted(d):
        o[k[:7]] = d[k]
    return o


def month_mean(d):
    g = defaultdict(list)
    for k, v in d.items():
        g[k[:7]].append(v)
    return {k: float(np.mean(v)) for k, v in g.items()}


def ym_back(ym, k):
    y, m = int(ym[:4]), int(ym[5:]) - k
    while m <= 0:
        y, m = y - 1, m + 12
    return f'{y:04d}-{m:02d}'


def seasons(spy_daily, side, cpi_path):
    """Monthly market seasons: k-means (k=4, best of 60 starts) on 8 standardized measures."""
    vx = json.load(open(os.path.join(side, 'vix_irx.json')))
    xa = json.load(open(os.path.join(side, 'xasset.json')))
    if cpi_path:
        txt = open(cpi_path).read()
    else:
        txt = urllib.request.urlopen('https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL', timeout=60).read().decode()
    cpi = {r['observation_date'][:7]: float(r['CPIAUCSL']) for r in csv.DictReader(io.StringIO(txt)) if r['CPIAUCSL'].strip()}
    spy, vix, irx = month_last(spy_daily), month_mean(vx['^VIX']), month_last(vx['^IRX'])
    gold, oil = month_last(xa['GC=F']), month_last(xa['CL=F'])
    months = sorted(m for m in spy if m >= '2000-01')

    def base6(ym):
        return [spy[ym] / spy[ym_back(ym, 12)] - 1, spy[ym] / spy[ym_back(ym, 3)] - 1, vix[ym],
                cpi[ym] / cpi[ym_back(ym, 12)] - 1, irx[ym], irx[ym] - irx[ym_back(ym, 12)]]
    rows, keep = [], []
    for ym in months:
        try:
            rows.append(base6(ym) + [gold[ym] / gold[ym_back(ym, 12)] - 1, oil[ym] / oil[ym_back(ym, 12)] - 1])
            keep.append(ym)
        except (KeyError, TypeError):
            continue
    X = np.array(rows)
    mu, sd = X.mean(0), X.std(0)
    Z = (X - mu) / sd
    best = None
    for seed in range(60):
        rng = np.random.default_rng(seed)
        Cn = Z[rng.choice(len(Z), 4, replace=False)]
        for _ in range(200):
            L = ((Z[:, None, :] - Cn[None]) ** 2).sum(-1).argmin(1)
            C2 = np.array([Z[L == j].mean(0) if (L == j).any() else Cn[j] for j in range(4)])
            if np.allclose(C2, Cn):
                break
            Cn = C2
        sse = ((Z - Cn[L]) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, L, Cn)
    _, L, Cn = best
    cent = mu + Cn * sd

    def name(c):
        if c[0] < -0.05 or c[2] > 30:
            return 'Bear / crisis'
        if c[3] > 0.035 or c[5] > 1.0:
            return 'Inflation / rising rates'
        return 'Bull, near-zero rates' if c[4] < 1.0 else 'Bull, normal rates'
    labels = [name(c) for c in cent]
    out = {ym: labels[l] for ym, l in zip(keep, L)}
    for ym in months:                         # months before gold/oil history: nearest season on six measures
        if ym in out:
            continue
        try:
            z = (np.array(base6(ym)) - mu[:6]) / sd[:6]
        except (KeyError, TypeError):
            continue
        out[ym] = labels[int(((Cn[:, :6] - z) ** 2).sum(1).argmin())]
    return out


def build_panel(D, R, side, sector_of, season):
    """Weekly rows: (friday, ticker, signal pct, macro, size third, vol third, season, excess 5-day, 5-day, trading value)."""
    for t in ('EP', 'CPWR'):
        D['bars'].pop(t, None)
    ok = {t for t, ivs in D['iv'].items() if t in D['bars'] and D['bars'][t] and R.usable(D['bars'][t], ivs)}
    cal = [b[0] for b in D['bench']['SPY']]
    pos = {d: i for i, d in enumerate(cal)}
    tick = sorted(t for t in ok if sector_of(t))
    z = np.load(os.path.join(side, 'stock_volume.npz'), allow_pickle=True)
    vt = {t: i for i, t in enumerate(z['tickers'])}
    vpos = {str(d): i for i, d in enumerate(z['dates'])}
    T = len(cal)
    PX = np.full((len(tick), T), np.nan)
    VOL = np.full((len(tick), T), np.nan, dtype=np.float32)
    vmap = np.array([vpos.get(d, -1) for d in cal])
    for a, t in enumerate(tick):
        for b in D['bars'][t]:
            i = pos.get(b[0])
            if i is not None:
                PX[a, i] = b[4]
        if t in vt:
            row = z['vol'][vt[t]]
            okv = vmap >= 0
            VOL[a, okv] = row[vmap[okv]]
    wk = [date.fromisoformat(d).isocalendar()[:2] for d in cal]
    fridays = [i for i in range(T - 1) if cal[i] >= '2000-01-01' and wk[i + 1] != wk[i]]

    def member(ivs, d):
        return any((s is None or s <= d) and (e is None or d < e) for s, e in ivs)
    rows = []
    for i in fridays:
        if i + 6 >= T or i < 260 or cal[i][:7] not in season:
            continue
        d = cal[i]
        recs = []
        for a, t in enumerate(tick):
            if not member(D['iv'][t], d):
                continue
            p = PX[a]
            if np.isnan(p[[i, i - 21, i - 126, i + 1, i + 6]]).any():
                continue
            w = p[i - 251:i + 1]
            w = w[~np.isnan(w)]
            if len(w) < 200:
                continue
            seg = p[i - 251:i + 1] * VOL[a, i - 251:i + 1]
            dv = float(np.nanmean(seg)) if np.isfinite(seg).any() else np.nan
            recs.append((t, p[i - 21] / p[i - 126] - 1, float(np.diff(np.log(w)).std(ddof=1)), dv, p[i + 6] / p[i + 1] - 1))
        if len(recs) < 100:
            continue
        arr = np.array([r[1:] for r in recs], dtype=float)

        def pct(x):
            return (np.argsort(np.argsort(x)) + 0.5) / len(x)
        mp, vp = pct(arr[:, 0]), pct(arr[:, 1])
        dvp = np.full(len(arr), np.nan)
        okd = ~np.isnan(arr[:, 2])
        dvp[okd] = pct(arr[okd, 2])

        def third(q):
            return 'n/a' if np.isnan(q) else ('Low' if q < 1 / 3 else ('Mid' if q < 2 / 3 else 'High'))
        ex = arr[:, 3] - arr[:, 3].mean()
        for k, r in enumerate(recs):
            rows.append(dict(date=d, t=r[0], mp=float(mp[k]), macro=MACRO[sector_of(r[0])], sizeT=third(dvp[k]),
                             volT=third(vp[k]), season=season[d[:7]], ex=float(ex[k]), fwd=float(arr[k, 3]),
                             dv=None if np.isnan(arr[k, 2]) else float(arr[k, 2])))
    return rows


def period(d):
    y = int(d[:4])
    return '2000-2015' if y <= 2015 else ('2016-2020' if y <= 2020 else ('2021-2023' if y <= 2023 else '2024 on'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', required=True)
    ap.add_argument('--side', required=True)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--cpi', default='')
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    os.environ.setdefault('START', '2000-01-03')
    os.environ.setdefault('FROM', '1998-06-01')
    sys.path[:0] = [os.path.join(a.engine, 'scripts'), a.engine]
    cwd = os.getcwd()
    os.chdir(a.engine)
    import robustness as R  # noqa: E402  (engine module; reads data/.robust_<FROM>.pkl)
    D = R.load_data()
    os.chdir(cwd)
    spy_daily = {b[0]: b[4] for b in D['bench']['SPY']}
    season = seasons(spy_daily, a.side, a.cpi)
    rows = build_panel(D, R, a.side, sectors(a.repo), season)
    OUT = {}
    print(f"weekly panel: {len(rows):,} stock-weeks, {len({r['date'] for r in rows})} weeks")

    # ---- 4. size check: every macro-sector >= 10% of the full dataset ----
    cnt, val, per, perv = Counter(), Counter(), defaultdict(Counter), defaultdict(Counter)
    for r in rows:
        cnt[r['macro']] += 1
        per[period(r['date'])][r['macro']] += 1
        if r['dv']:
            val[r['macro']] += r['dv']
            perv[period(r['date'])][r['macro']] += r['dv']
    tc, tv = sum(cnt.values()), sum(val.values())
    for m in MACROS:
        assert cnt[m] / tc >= 0.10, f'macro-sector {m} is only {cnt[m] / tc:.1%} of stock-weeks'
        assert val[m] / tv >= 0.10, f'macro-sector {m} is only {val[m] / tv:.1%} of trading value'
    OUT['macro'] = {'full': {m: [cnt[m] / tc, val[m] / tv] for m in MACROS}}
    print('\nmacro-sector share (stock-weeks / trading value); assert >= 10% on the full dataset passed')
    print('  full     ' + ' | '.join(f"{m} {cnt[m] / tc:.1%} / {val[m] / tv:.1%}" for m in MACROS))
    for p in ('2000-2015', '2016-2020', '2021-2023', '2024 on'):
        c_, v_ = sum(per[p].values()), sum(perv[p].values())
        OUT['macro'][p] = {m: [per[p][m] / c_, perv[p][m] / v_] for m in MACROS}
        print(f"  {p:9}" + ' | '.join(f"{m} {per[p][m] / c_:.1%} / {perv[p][m] / v_:.1%}" for m in MACROS))

    weeks = sorted({r['date'] for r in rows})
    widx = {w: i for i, w in enumerate(weeks)}
    byw = defaultdict(list)
    for r in rows:
        byw[r['date']].append(r)
    DIMS = ['macro', 'sizeT', 'volT', 'season']
    lev = {d: sorted({r[d] for r in rows}) for d in DIMS}
    cols = [(dims, key) for k in (1, 2) for dims in itertools.combinations(DIMS, k)
            for key in itertools.product(*[lev[d] for d in dims])]
    ci = {c: i for i, c in enumerate(cols)}
    NC = len(cols)
    NF = 2 + 2 * NC

    def X_of(v):
        X = np.zeros((len(v), NF))
        for i, r in enumerate(v):
            m = r['mp'] - 0.5
            X[i, 0], X[i, 1] = 1, m
            for k in (1, 2):
                for dims in itertools.combinations(DIMS, k):
                    j = ci[(dims, tuple(r[d] for d in dims))]
                    X[i, 2 + j], X[i, 2 + NC + j] = 1, m
        return X
    WX, WXX, WXY = {}, np.zeros((len(weeks), NF, NF), dtype=np.float32), np.zeros((len(weeks), NF))
    for w in weeks:
        X = X_of(byw[w])
        y = np.array([r['ex'] for r in byw[w]])
        WX[w], WXX[widx[w]], WXY[widx[w]] = X, X.T @ X, X.T @ y

    def fit(ws, lam):
        Rg = np.eye(NF) * lam
        Rg[0, 0] = Rg[1, 1] = 0
        return np.linalg.solve(WXX[ws].sum(0).astype(np.float64) + Rg, WXY[ws].sum(0))

    def score(ws, beta):
        cls, pln, ic = [], [], []
        for i in ws:
            v = byw[weeks[i]]
            sc = WX[weeks[i]] @ beta
            mp = np.array([r['mp'] for r in v])
            fw = np.array([r['fwd'] for r in v])
            ex = np.array([r['ex'] for r in v])
            top_c, top_p = np.argsort(-sc)[:5], np.argsort(-mp)[:5]
            cls.append((fw[top_c].mean(), ex[top_c].mean()))
            pln.append((fw[top_p].mean(), ex[top_p].mean()))
            ic.append(np.corrcoef(np.argsort(np.argsort(sc)), np.argsort(np.argsort(fw)))[0, 1])
        return np.array(cls), np.array(pln), np.array(ic)

    def path_stats(wr):
        eq = np.cumprod(1 + wr)
        return float(eq[-1] ** (52 / len(wr)) - 1), float((eq / np.maximum.accumulate(eq) - 1).min())

    # ---- 5. CPCV on 2000-2015 ----
    old = [i for i, w in enumerate(weeks) if w <= '2015-12-31']
    groups = np.array_split(np.array(old), NG)
    splits = list(itertools.combinations(range(NG), KT))

    def train_weeks(test_g, pool):
        bad = set()
        for g in test_g:
            lo, hi = int(groups[g][0]), int(groups[g][-1])
            bad |= set(range(lo - PURGE, lo)) | set(range(hi + 1, hi + 1 + EMB))
        return [int(x) for g in pool for x in groups[g] if int(x) not in bad]
    res = {}
    for sp in splits:
        trg = [g for g in range(NG) if g not in sp]
        best = None
        for lam in LAMS:                       # ridge strength chosen inside the training groups only
            ics = [score([int(x) for x in groups[h]], fit(train_weeks([h], [g for g in trg if g != h]), lam))[2].mean() for h in trg]
            if best is None or np.mean(ics) > best[1]:
                best = (lam, np.mean(ics))
        beta = fit(train_weeks(list(sp), trg), best[0])
        for g in sp:
            res[(sp, g)] = score([int(x) for x in groups[g]], beta) + (best[0],)
    npath = len(splits) * KT // NG
    paths = [[None] * NG for _ in range(npath)]
    for g in range(NG):
        for j, sp in enumerate([sp for sp in splits if g in sp]):
            paths[j][g] = res[(sp, g)]
    OUT['cpcv'] = []
    print(f'\nCPCV on 2000-2015: {NG} groups, {KT} held out, {len(splits)} splits, {npath} paths, purge {PURGE} wk, embargo {EMB} wk')
    for j, pth in enumerate(paths):
        cls = np.concatenate([p[0] for p in pth])
        pln = np.concatenate([p[1] for p in pth])
        (cc, cd), (pc, pd_) = path_stats(cls[:, 0]), path_stats(pln[:, 0])
        OUT['cpcv'].append(dict(classEdge=float(cls[:, 1].mean()), plainEdge=float(pln[:, 1].mean()), classCagr=cc,
                                classDD=cd, plainCagr=pc, plainDD=pd_, lams=sorted({p[3] for p in pth})))
        print(f"  path {j + 1}: class-aware top 5 {cls[:, 1].mean():+.3%}/wk ({cc:.1%} a year, worst {cd:.0%}) | "
              f"plain {pln[:, 1].mean():+.3%}/wk ({pc:.1%}, worst {pd_:.0%})")
    better = sum(p['classEdge'] > p['plainEdge'] for p in OUT['cpcv'])
    print(f'  class-aware better on {better} of {npath} paths')

    # ---- 6. chronological 2016-2026 ----
    lam = Counter(l for p in OUT['cpcv'] for l in p['lams']).most_common(1)[0][0]
    OUT['chrono'] = {}
    print(f'\nchronological (ridge {lam}): learned on all earlier weeks')
    for lab, s_, e_ in (('2021-2023', '2021-01-01', '2023-12-31'), ('2024 on', '2024-01-01', '9999')):
        first = widx[min(w for w in weeks if w >= s_)]
        beta = fit(list(range(0, first - PURGE)), lam)
        cls, pln, _ = score([i for i, w in enumerate(weeks) if s_ <= w <= e_], beta)
        OUT['chrono'][lab] = dict(classEdge=float(cls[:, 1].mean()), plainEdge=float(pln[:, 1].mean()))
        print(f"  {lab:9} class-aware {cls[:, 1].mean():+.3%}/wk | plain {pln[:, 1].mean():+.3%}/wk")

    # ---- 7. all class combinations, false-discovery check ----
    def cells(ws, dims):
        g = defaultdict(lambda: defaultdict(list))
        for i in ws:
            for r in byw[weeks[i]]:
                k = tuple(r[d] for d in dims)
                if r['mp'] >= 0.9 and 'n/a' not in k:
                    g[k][weeks[i]].append(r['ex'])
        out = {}
        for k, mm in g.items():
            mv = np.array([np.mean(x) for x in mm.values()])
            t = float(mv.mean() / (mv.std(ddof=1) / math.sqrt(len(mv)))) if len(mv) > 2 and mv.std() > 0 else 0.0
            out[k] = (float(mv.mean()), t, sum(len(x) for x in mm.values()), len(mv))
        return out
    disc = [i for i, w in enumerate(weeks) if w <= '2020-12-31']
    tst = [i for i, w in enumerate(weeks) if '2021' <= w[:4] <= '2023']
    hol = [i for i, w in enumerate(weeks) if w[:4] >= '2024']
    combos = []
    for k in (1, 2, 3):
        for dims in itertools.combinations(DIMS, k):
            cd, ct, ch = cells(disc, dims), cells(tst, dims), cells(hol, dims)
            for key, (m, t, n, nw) in cd.items():
                if n < 100 or nw < 40:
                    continue
                te, ho = ct.get(key), ch.get(key)
                combos.append(dict(dims=dims, key=key, edge=m, t=t, te=te[0] if te and te[2] >= 30 else None,
                                   ho=ho[0] if ho and ho[2] >= 30 else None))
    pv = [2 * (1 - 0.5 * (1 + math.erf(abs(c['t']) / math.sqrt(2)))) for c in combos]
    order, sig = np.argsort(pv), []
    for r_, i in enumerate(order, 1):
        if pv[i] <= 0.10 * r_ / len(pv):
            sig = list(order[:r_])
    both = [c for c in combos if c['te'] is not None and c['ho'] is not None]
    OUT['combos'] = dict(tested=len(combos), passFDR=len(sig),
                         sameSignTest=float(np.mean([np.sign(c['edge']) == np.sign(c['te']) for c in both])),
                         sameSignHoldout=float(np.mean([np.sign(c['edge']) == np.sign(c['ho']) for c in both])),
                         significant=[dict(key=combos[i]['key'], edge=combos[i]['edge'], t=combos[i]['t'],
                                           test=combos[i]['te'], holdout=combos[i]['ho']) for i in sig])
    print(f"\nclass combinations: {len(combos)} tested on 2000-2020, {len(sig)} pass the false-discovery check; "
          f"same sign in 2021-2023 {OUT['combos']['sameSignTest']:.0%}, in 2024 on {OUT['combos']['sameSignHoldout']:.0%}")
    if a.out:
        json.dump(OUT, open(a.out, 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()

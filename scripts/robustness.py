#!/usr/bin/env python3
"""Robustness audit of the Top 5 / Auto / Boost plans, 2010 onward.

Addresses four review points, each against the current dashboard method:

A. Lookahead / data leakage
   - Truncation test: for sample Fridays D, every input is cut to dates <= D
     (prices, bars, news gaps, glitch blocks, sleeve prices) and the rule is
     re-run; the trades it would place after D must match the full-data run.
   - Sleeve timing fix: the dashboard's sleeve switched at the same Friday
     close it decided on; here it is decided Friday and traded Monday.

B. Survivorship / selection bias
   - Point-in-time S&P 500 membership rebuilt from Wikipedia's change log
     (adds and removals by date), so a stock is only rankable while it was
     actually in the index, including companies since removed.
   - Removed companies' prices are pulled where Yahoo still has them; a
     recycled ticker (series starting after the removal) is rejected.
   - Nasdaq-100-only names (no join dates = hindsight) are dropped.
   - Coverage: share of each year's members with usable prices.

C. Start-date and outlier sensitivity
   - The Boost plan restarted every January and July 2010-2023.
   - Best stock-weeks swapped for SPY's return that week (top 1/5/10/25/1%).
   - Re-runs with the single best stock, then the best 3, made ineligible.

D. Costs, slippage and taxes (position-level ledger, $100,000 start)
   - Closing-auction slippage per side: 0.05% / 0.15% / 0.30%.
   - Lots with holding periods: short-term (held one year or less) at 37%,
     long-term 20% (GLD long-term 28%, collectible); optional 3.8% NIIT.
   - Schedule D netting each calendar year, $3,000 ordinary-income offset,
     loss carryforward keeping its short/long character.
   - Wash sales: a loss sale with a purchase of the same ticker within 30
     days before or after is disallowed and added to the replacement lot's
     basis, with the holding period tacked on.
   - Taxes leave the account when the IRS wants them: quarterly estimated
     payments (Apr 15, Jun 15, Sep 15, Jan 15) on year-to-date gains, then an
     April 15 true-up / refund; cash is raised by selling pro rata.
   - Lot relief: tax-optimal specific identification (losses first, then
     highest basis), with FIFO as a check.
   - Benchmarks: SPY / QQQ bought once, dividends taxed at 20% when paid and
     reinvested, long-term tax on liquidation.

Writes data/robustness.json. Needs network (Yahoo Finance, Wikipedia).

Usage:
    python scripts/robustness.py
"""
import io
import json
import math
import os
import pickle
import random
import sys
import urllib.request
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from multiprocessing import get_context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_scan import blocked_dates, fetch  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, run_momentum  # noqa: E402
from mtl.news import booster, news_gap_days  # noqa: E402
from mtl.sleeve import ASSETS, best_of, filled, plan_curve_dynamic, sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import URL as SP_URL, load_added, load_sp500, momentum_universe  # noqa: E402

HIST_URL = 'https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'robustness.json')
CACHE = os.path.join(ROOT, 'data', '.robust.pkl')
START, FROM = '2010-01-04', '2008-06-01'
LOOK, SKIP, TOP_N = 126, 21, 5
SLIPS = (0.0005, 0.0015, 0.0030)
BASE_SLIP = 0.0015
START_CASH = 100_000.0
G = {}   # shared read-only state for worker processes (fork)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- B: universe

def fetch_sp500_changes():
    """[(date, added, removed)] from Wikipedia's 'Selected changes' table, Yahoo symbols."""
    import pandas as pd
    t = None
    for url in (HIST_URL, SP_URL):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=60).read().decode()
        try:
            tables = pd.read_html(io.StringIO(html), flavor='lxml')
        except ValueError:
            continue
        t = next((x for x in tables if any('Removed' in str(c) for c in x.columns)), None)
        if t is not None:
            break
    if t is None:
        raise ValueError('no S&P 500 change table found on Wikipedia')
    cols = []
    for c in t.columns:
        parts = [str(x) for x in (c if isinstance(c, tuple) else (c,)) if 'Unnamed' not in str(x)]
        cols.append(' '.join(dict.fromkeys(parts)).strip())
    t.columns = cols
    dcol = next(c for c in cols if 'Date' in c)
    acol = next(c for c in cols if c.startswith('Added') and 'Ticker' in c)
    rcol = next(c for c in cols if c.startswith('Removed') and 'Ticker' in c)

    def norm(s):
        if not isinstance(s, str):
            return None
        s = s.strip().split('[')[0].strip()
        return s.replace('.', '-') if s and s.lower() != 'nan' else None
    out = []
    for _, r in t.iterrows():
        d = pd.to_datetime(r[dcol], errors='coerce')
        if pd.isna(d):
            continue
        out.append((d.strftime('%Y-%m-%d'), norm(r[acol]), norm(r[rcol])))
    out.sort(key=lambda x: (x[0], x[1] or '', x[2] or ''))
    if len(out) < 200:
        raise ValueError(f"only {len(out)} S&P changes parsed - page layout changed?")
    return out


def membership(current, changes):
    """{ticker: [[start|None, end|None], ...]} - walk the change log backwards from today."""
    members, end_of, iv = set(current), {}, {}
    for d, a, x in reversed(changes):
        if a and a in members:
            iv.setdefault(a, []).append([d, end_of.get(a)])
            members.discard(a)
        if x and x not in members:
            members.add(x)
            end_of[x] = d
    for t in members:
        iv.setdefault(t, []).append([None, end_of.get(t)])
    return iv


def is_member(ivs, d):
    return any((s is None or s <= d) and (e is None or d < e) for s, e in ivs)


def usable(bars, ivs):
    """Reject series that can't be the same company over its membership (recycled tickers)."""
    if not bars:
        return False
    first, last = bars[0][0], bars[-1][0]
    for s, e in ivs:
        lo = max(s or START, START)
        hi = e or '9999-12-31'
        if hi <= START:
            continue
        if first > max(lo, '2009-07-01') and (e is None or first > e):
            return False          # series starts after the membership ended: a recycled ticker
        if e and last < (date.fromisoformat(e) - timedelta(days=45)).isoformat():
            return False          # no prices near the removal date
    return True


def load_data():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    names = momentum_universe(refresh=False)
    sp, added = load_sp500(), load_added()
    changes = fetch_sp500_changes()
    iv = membership(set(sp), changes)
    relevant = {t for t, ivs in iv.items() if any(e is None or e > FROM for s, e in ivs)}
    tickers = sorted(set(names) | relevant)
    log(f"universe: dashboard {len(names)}, point-in-time S&P candidates {len(relevant)}, fetching {len(tickers)}")
    bars = fetch(tickers, start=FROM)
    bench = fetch(['SPY', 'QQQ'], start=FROM, adjusted=True)
    bench_raw = fetch(['SPY', 'QQQ'], start=FROM, adjusted=False)
    assets = fetch(ASSETS, start=FROM, adjusted=True)
    divs = {}
    try:
        import yfinance as yf
        for t in ('SPY', 'QQQ'):
            s = yf.Ticker(t).dividends
            divs[t] = {ts.date().isoformat(): float(v) for ts, v in s.items() if ts.date().isoformat() >= FROM}
    except Exception as e:   # noqa: BLE001
        log(f"dividends failed: {e}")
    data = dict(names=names, sp=sp, added=added, changes=changes, iv=iv, bars=bars,
                bench=bench, bench_raw=bench_raw, assets=assets, divs=divs)
    with open(CACHE, 'wb') as f:
        pickle.dump(data, f)
    return data


def prepare(D):
    calendar = [b[0] for b in D['bench']['SPY']]
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in D['bars'].items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in D['bench']['SPY']}
    blocked = {t: blocked_dates(bs) for t, bs in D['bars'].items()}
    sp, added, iv = D['sp'], D['added'], D['iv']
    names = D['names']

    def elig_base(t, d):
        if t not in names or d in blocked.get(t, ()):
            return False
        return t not in sp or added.get(t, '0000') <= d

    ok = {t for t, ivs in iv.items() if t in D['bars'] and usable(D['bars'][t], ivs)}

    def elig_pit(t, d):
        if t not in ok or d in blocked.get(t, ()):
            return False
        if not is_member(iv[t], d):
            return False
        return t not in sp or added.get(t, '0000') <= d

    gaps = {t: news_gap_days(bs) for t, bs in D['bars'].items() if bs}
    sleeve_px = {t: {b[0]: b[4] for b in bs} for t, bs in D['assets'].items()}
    return dict(calendar=calendar, prices=prices, elig_base=elig_base, elig_pit=elig_pit, ok=ok,
                gaps=gaps, sleeve_px=sleeve_px, sleeve_f=filled(sleeve_px, calendar))


def coverage(D, P):
    """Per year: point-in-time members on the first session, and how many have usable prices."""
    iv, out = D['iv'], []
    cal = P['calendar']
    for y in range(2010, int(cal[-1][:4]) + 1):
        d = next(x for x in cal if x >= f'{y}-01-01')
        mem = [t for t, ivs in iv.items() if is_member(ivs, d)]
        have = [t for t in mem if t in P['ok'] and P['prices'].get(t, {}).get(d)]
        out.append(dict(year=y, members=len(mem), priced=len(have)))
    removed = {t for t, ivs in iv.items() if any(e and e > START for s, e in ivs) and t not in D['sp']}
    return dict(byYear=out, removedSince2010=len(removed), removedPriced=len(removed & P['ok']))


# ---------------------------------------------------------------- engine runs

def run_core(universe, start, boost, exclude=()):
    P = G['P']
    base = P['elig_base'] if universe == 'base' else P['elig_pit']
    ex = set(exclude)
    elig = (lambda t, d: t not in ex and base(t, d)) if ex else base
    kw = dict(look=LOOK, skip=SKIP, top_n=TOP_N, eligible=elig, exec_next='close')
    if boost:
        kw.update(prefer=booster(P['gaps'], P['calendar']), prefer_mode='force', prefer_rank=None, prefer_pool='all')
    return run_momentum(P['prices'], P['calendar'], start, **kw)


def _job(args):
    key, universe, start, boost, exclude = args
    r = run_core(universe, start, boost, exclude)
    return key, dict(curve=[[d, v] for d, v, _ in r['curve']], picks=r['picks'], turnover=r['turnover'])


def run_many(jobs, procs=4):
    ctx = get_context('fork')
    out = {}
    with ctx.Pool(procs) as pool:
        for key, res in pool.imap_unordered(_job, jobs):
            out[key] = res
            log(f"  run done: {key}")
    return out


# ---------------------------------------------------------------- plans

def downtrend_fn(bars):
    days = {t: [b[0] for b in bs] for t, bs in bars.items()}
    cache = {}

    def down(t, d):
        if (t, d) not in cache:
            j = bisect_right(days.get(t, []), d)
            daily = [tuple(b) for b in bars.get(t, [])[max(0, j - 320):j]]
            cache[(t, d)] = structure_signal(daily, n=3, lookback=2)['state'] == 'downtrend'
        return cache[(t, d)]
    return down


def plan_schedule(picks, calendar, sleeve_f, down, start, top_n=TOP_N):
    """[(trade date, {asset: weight})] - stocks at split/top_n each, sleeve 1-split.
    Split and sleeve asset decided at the previous session's close (Friday), traded at
    this session's close (Monday) together with the stock picks."""
    idx = {d: i for i, d in enumerate(calendar)}
    pdays = [p[0] for p in picks]
    out = []
    for T, held in picks:
        if T < start or idx[T] == 0:
            continue
        f = calendar[idx[T] - 1]
        j = bisect_right(pdays, f) - 1
        before = picks[j][1] if j >= 0 else []
        split = 0.6 if sum(down(t, f) for t in before) >= 2 else 1.0
        w = {t: split / top_n for t in held}
        if split < 1:
            a = best_of(sleeve_f, calendar, idx[f])
            w[a] = w.get(a, 0.0) + (1 - split)
        out.append((T, w))
    return out


def dashboard_plan(run, calendar, sleeve_px, down, start):
    """The dashboard's own construction (sleeve switching at the Friday close)."""
    sl, _ = sleeve_curve(sleeve_px, calendar, start)
    picks = run['picks']
    pdays = [p[0] for p in picks]

    def split(f):
        j = bisect_right(pdays, f) - 1
        held = picks[j][1] if j >= 0 else []
        return 0.6 if sum(down(t, f) for t in held) >= 2 else 1.0
    return plan_curve_dynamic(run['curve'], sl, calendar, split)


# ---------------------------------------------------------------- D: ledger

def plus_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


class Ledger:
    """Lot-level account with slippage, wash sales and IRS-timed tax payments."""

    def __init__(self, cash, slip, st=0.37, lt=0.20, coll=0.28, niit=0.0, method='taxopt',
                 taxes=True, loss_offset=3000.0, collectibles=('GLD',)):
        self.cash, self.slip, self.method, self.taxes = cash, slip, method, taxes
        self.rates = dict(st=st + niit, lt=lt + niit, coll=coll + niit, ordinary=st)
        self.loss_offset, self.coll = loss_offset, set(collectibles)
        self.lots = {}        # t -> [dict(sh, ps, acq, buy, cap)]
        self.recs = []        # realized: dict(d, t, gain, term, coll)
        self.pending = []     # loss sales awaiting a replacement buy within 30 days
        self.paid = {}        # year -> net payments made (refunds negative)
        self.px = {}
        self.wash_total = 0.0
        self.tax_paid_total = 0.0
        self.traded = 0.0

    # positions
    def shares(self, t):
        return sum(l['sh'] for l in self.lots.get(t, []))

    def equity(self):
        return self.cash + sum(self.shares(t) * self.px[t] for t in self.lots)

    def _order(self, t, d, pps):
        lots = self.lots[t]
        if self.method == 'fifo':
            return sorted(lots, key=lambda l: l['acq'])

        def key(l):
            gain = pps - l['ps']
            lt = d > plus_year(l['acq'])
            grp = (0 if not lt else 1) if gain < 0 else (2 if lt else 3)
            return (grp, -l['ps'])
        return sorted(lots, key=key)

    def sell(self, t, sh, d):
        if sh <= 1e-9:
            return
        px = self.px[t]
        pps = px * (1 - self.slip)
        left = sh
        sold = []
        for l in self._order(t, d, pps):
            if left <= 1e-12:
                break
            q = min(l['sh'], left)
            gain = q * (pps - l['ps'])
            term = 'LT' if d > plus_year(l['acq']) else 'ST'
            rec = dict(d=d, t=t, gain=gain, term=term, coll=t in self.coll)
            self.recs.append(rec)
            l['sh'] -= q
            left -= q
            self.cash += q * pps
            self.traded += q * px
            sold.append(l)
            if gain < 0 and self.taxes:
                self._wash_back(t, d, q, -gain / q, rec, l['acq'], sold)
        self.lots[t] = [l for l in self.lots[t] if l['sh'] > 1e-9]
        if not self.lots[t]:
            del self.lots[t]

    def _apply_wash(self, lot, q, loss_ps, rec, acq_sold, d_sale):
        """q replacement shares of `lot` absorb the disallowed loss."""
        rec['gain'] += q * loss_ps
        self.wash_total += q * loss_ps
        held_days = max(0, (d_sale - acq_sold).days)
        if q < lot['sh'] - 1e-9:
            rest = dict(lot)
            rest['sh'] = lot['sh'] - q
            rest['cap'] = min(rest['sh'], max(0.0, lot['cap'] - q))
            self.lots[rec['t']].append(rest)
            lot['sh'] = q
        lot['cap'] = 0.0          # each replacement share absorbs one disallowed loss
        lot['ps'] += loss_ps
        lot['acq'] = lot['acq'] - timedelta(days=held_days)

    def _wash_back(self, t, d, q, loss_ps, rec, acq_sold, sold):
        left = q
        for l in list(self.lots.get(t, [])):
            if left <= 1e-12:
                break
            if l in sold or l['sh'] <= 1e-9 or l['cap'] <= 1e-9:
                continue
            if d - timedelta(days=30) <= l['buy'] < d:
                m = min(left, l['sh'], l['cap'])
                self._apply_wash(l, m, loss_ps, rec, acq_sold, d)
                left -= m
        if left > 1e-12:
            self.pending.append(dict(t=t, d=d, sh=left, loss_ps=loss_ps, rec=rec, acq=acq_sold))

    def buy(self, t, sh, d):
        if sh <= 1e-9:
            return
        px = self.px[t]
        lot = dict(sh=sh, ps=px * (1 + self.slip), acq=d, buy=d, cap=sh)
        self.lots.setdefault(t, []).append(lot)
        self.cash -= sh * px * (1 + self.slip)
        self.traded += sh * px
        if self.taxes:
            for p in self.pending:
                if p['t'] != t or p['sh'] <= 1e-12 or (d - p['d']).days > 30 or lot['cap'] <= 1e-9:
                    continue
                m = min(p['sh'], lot['sh'], lot['cap'])
                self._apply_wash(lot, m, p['loss_ps'], p['rec'], p['acq'], p['d'])
                p['sh'] -= m

    def expire(self, d):
        self.pending = [p for p in self.pending if (d - p['d']).days <= 30 and p['sh'] > 1e-12]

    def rebalance(self, w, d):
        E = self.equity()
        tgt = {t: w.get(t, 0.0) * E / self.px[t] for t in set(w) | set(self.lots)}
        for t, n in tgt.items():
            have = self.shares(t)
            if have > n + 1e-9:
                self.sell(t, have - n, d)
        need = {t: n - self.shares(t) for t, n in tgt.items() if n > self.shares(t) + 1e-9}
        cost = sum(q * self.px[t] * (1 + self.slip) for t, q in need.items())
        scale = min(1.0, self.cash / cost) if cost > 0 else 1.0
        for t, q in need.items():
            self.buy(t, q * scale, d)

    def raise_cash(self, amount, d):
        if self.cash >= amount:
            return
        need = amount - self.cash
        pos = {t: self.shares(t) * self.px[t] for t in self.lots}
        tot = sum(pos.values())
        if tot <= 0:
            return
        frac = min(1.0, need / (tot * (1 - self.slip)) * 1.0005)
        for t in list(self.lots):
            self.sell(t, self.shares(t) * frac, d)

    # taxes
    def year_tax(self, year, cutoff=None, cf=(0.0, 0.0)):
        """(tax, carryforward (st, lt), detail) for `year` from realized records <= cutoff."""
        st = ltn = ltc = 0.0
        for r in self.recs:
            if r['d'].year != year or (cutoff and r['d'] > cutoff):
                continue
            if r['term'] == 'ST':
                st += r['gain']
            elif r['coll']:
                ltc += r['gain']
            else:
                ltn += r['gain']
        raw = dict(st=st, lt=ltn + ltc)
        S = st - cf[0]
        if ltn < 0:              # long-term losses offset 28% gains first
            ltc, ltn = ltc + ltn, 0.0
        L = ltn + ltc - cf[1]
        coll_part = max(0.0, min(ltc, L))
        rt = self.rates
        if S >= 0 and L >= 0:
            tax = rt['st'] * S + rt['coll'] * coll_part + rt['lt'] * (L - coll_part)
            return tax, (0.0, 0.0), dict(raw=raw, st=S, lt=L)
        if S < 0 <= L and L + S >= 0:
            L2 = L + S
            coll_part = min(coll_part, L2)
            return rt['coll'] * coll_part + rt['lt'] * (L2 - coll_part), (0.0, 0.0), dict(raw=raw, st=0.0, lt=L2)
        if L < 0 <= S and S + L >= 0:
            return rt['st'] * (S + L), (0.0, 0.0), dict(raw=raw, st=S + L, lt=0.0)
        st_loss = max(0.0, -S) if L >= 0 or S < 0 else 0.0
        lt_loss = max(0.0, -L) if S >= 0 or L < 0 else 0.0
        if S < 0 <= L:
            st_loss, lt_loss = -(S + L), 0.0
        if L < 0 <= S:
            st_loss, lt_loss = 0.0, -(S + L)
        total = st_loss + lt_loss
        ded = min(self.loss_offset, total)
        cf_st = max(0.0, st_loss - ded)
        cf_lt = max(0.0, lt_loss - max(0.0, ded - st_loss))
        return -rt['ordinary'] * ded, (cf_st, cf_lt), dict(raw=raw, st=-st_loss, lt=-lt_loss)

    def chain(self, upto_year, cutoff=None):
        """Final taxes per year up to upto_year-1, then `upto_year` through cutoff."""
        cf, out = (0.0, 0.0), {}
        years = sorted({r['d'].year for r in self.recs} | {upto_year})
        for y in years:
            if y > upto_year:
                break
            tax, cf2, det = self.year_tax(y, cutoff if y == upto_year else None, cf)
            out[y] = dict(tax=tax, cf_in=cf, detail=det)
            cf = cf2
        return out

    def pay(self, year, amount, d):
        if abs(amount) < 0.005:
            return
        if amount > 0:
            self.raise_cash(amount, d)
        self.cash -= amount
        self.paid[year] = self.paid.get(year, 0.0) + amount
        self.tax_paid_total += amount


def due_events(calendar):
    """{trade date: [(kind, year, cutoff)]} - estimated payments and April true-ups, moved to
    the next session when the due date is not a trading day."""
    cal = calendar
    out = {}

    def at(dt):
        s = dt.isoformat()
        i = bisect_right(cal, s) - 1
        if i < 0 or cal[i] != s:
            i += 1
        return cal[i] if i < len(cal) else None
    y0, y1 = int(cal[0][:4]), int(cal[-1][:4])
    for y in range(y0, y1 + 1):
        for due, cut in ((date(y, 4, 15), date(y, 3, 31)), (date(y, 6, 15), date(y, 5, 31)),
                         (date(y, 9, 15), date(y, 8, 31))):
            d = at(due)
            if d:
                out.setdefault(d, []).append(('est', y, cut))
        d = at(date(y + 1, 1, 15))
        if d:
            out.setdefault(d, []).append(('est', y, date(y, 12, 31)))
        d = at(date(y + 1, 4, 15))
        if d:
            out.setdefault(d, []).append(('final', y, None))
    return out


def simulate(schedule, prices, calendar, slip, taxes=True, method='taxopt', niit=0.0, start_cash=START_CASH):
    """Replays a weight schedule through the ledger. Returns curve and tax detail."""
    led = Ledger(start_cash, slip, niit=niit, method=method, taxes=taxes)
    sched = dict(schedule)
    first = schedule[0][0]
    events = due_events(calendar) if taxes else {}
    curve = []
    last = {}
    for d in calendar:
        if d < first:
            continue
        dd = date.fromisoformat(d)
        for t in set(led.lots) | set(sched.get(d, {})):
            p = prices.get(t, {}).get(d)
            if p:
                last[t] = p
            if t in last:
                led.px[t] = last[t]
        led.expire(dd)
        if d in sched:
            w = {t: x for t, x in sched[d].items() if t in led.px}
            led.rebalance(w, dd)
        for kind, y, cut in events.get(d, []):
            ch = led.chain(y, cut)
            due = ch[y]['tax'] - led.paid.get(y, 0.0)
            if kind == 'est':
                if due > 0:
                    led.pay(y, due, dd)
            else:
                led.pay(y, due, dd)       # true-up or refund
        curve.append([d, led.equity()])
    # liquidation at the last close
    end = date.fromisoformat(calendar[-1])
    pre_liq = led.equity()
    for t in list(led.lots):
        led.sell(t, led.shares(t), end)
    liq_tax = 0.0
    if taxes:
        ch = led.chain(end.year)
        for y in range(end.year - 1, end.year + 1):
            if y in ch:
                owe = ch[y]['tax'] - led.paid.get(y, 0.0)
                liq_tax += owe
                led.pay(y, owe, end)
    years = {}
    if taxes:
        ch = led.chain(end.year)
        for y, v in ch.items():
            det = v['detail']
            years[y] = dict(stNet=round(det['raw']['st'], 2), ltNet=round(det['raw']['lt'], 2),
                            tax=round(v['tax'], 2), paid=round(led.paid.get(y, 0.0), 2),
                            cfIn=[round(x, 2) for x in v['cf_in']])
    gains = [r['gain'] for r in led.recs]
    st_g = sum(g for r, g in zip(led.recs, gains) if r['term'] == 'ST' and g > 0)
    lt_g = sum(g for r, g in zip(led.recs, gains) if r['term'] == 'LT' and g > 0)
    return dict(curve=curve, preLiq=pre_liq, final=led.cash, liqTax=liq_tax,
                taxPaid=led.tax_paid_total, wash=led.wash_total, years=years,
                stShare=st_g / (st_g + lt_g) if st_g + lt_g else None,
                turnover=led.traded / (sum(v for _, v in curve) / len(curve)) / (len(curve) / 252) / 2)


def bench_after_tax(D, t, calendar, start, div_rate=0.20, lt_rate=0.20):
    """Buy and hold with dividends taxed when paid and reinvested; LT tax at the end."""
    raw = {b[0]: b[4] for b in D['bench_raw'][t]}
    divs = D['divs'].get(t, {})
    days = [d for d in calendar if d >= start and d in raw]
    sh = START_CASH / raw[days[0]]
    basis = START_CASH
    curve = []
    for d in days:
        if d in divs and d != days[0]:
            cash = sh * divs[d] * (1 - div_rate)
            sh += cash / raw[d]
            basis += cash
        curve.append([d, sh * raw[d]])
    gain = curve[-1][1] - basis
    return dict(curve=curve, preLiq=curve[-1][1], final=curve[-1][1] - lt_rate * max(0.0, gain))


# ---------------------------------------------------------------- stats

def stats(curve, rf=0.0):
    v = [x for _, x in curve]
    r = [b / a - 1 for a, b in zip(v, v[1:]) if a > 0]
    n = len(r)
    if n < 2:
        return {}
    mean = sum(r) / n
    sd = (sum((x - mean) ** 2 for x in r) / (n - 1)) ** 0.5
    ex = [x - rf / 252 for x in r]
    dd = (sum(min(x, 0) ** 2 for x in ex) / n) ** 0.5
    peak, mdd = v[0], 0.0
    for x in v:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1)
    cagr = (v[-1] / v[0]) ** (252 / n) - 1
    return dict(cagr=cagr, vol=sd * 252 ** 0.5, sharpe=(sum(ex) / n) / sd * 252 ** 0.5 if sd else None,
                sortino=(sum(ex) / n) / dd * 252 ** 0.5 if dd else None, maxDD=mdd, total=v[-1] / v[0] - 1)


def cagr_between(curve, a, b):
    pts = [(d, v) for d, v in curve if a <= d <= b]
    if len(pts) < 2:
        return None
    yrs = (date.fromisoformat(pts[-1][0]) - date.fromisoformat(pts[0][0])).days / 365.25
    return (pts[-1][1] / pts[0][1]) ** (1 / yrs) - 1 if yrs > 0 else None


def weekly(curve):
    out, wk = [], None
    for d, v in curve:
        k = date.fromisoformat(d).isocalendar()[:2]
        if k != wk:
            out.append([d, v])
            wk = k
        else:
            out[-1] = [d, v]
    return out


# ---------------------------------------------------------------- A: truncation test

def leak_test(D, P, dates):
    """Re-run Boost with every input cut at Friday D; compare with the full run."""
    full = G['runs']['pit_boost']
    cal = P['calendar']
    idx = {d: i for i, d in enumerate(cal)}
    sp, added, iv, ok = D['sp'], D['added'], D['iv'], P['ok']
    res = []
    for Dd in dates:
        k = idx[Dd]
        nxt = cal[k + 1]
        cal_t = cal[:k + 1] + [nxt]
        bars_t = {t: [b for b in bs if b[0] <= Dd] for t, bs in D['bars'].items()}
        prices_t = {t: {b[0]: b[4] for b in bs} for t, bs in bars_t.items() if bs}
        prices_t['SPY'] = {b[0]: b[4] for b in D['bench']['SPY'] if b[0] <= Dd}
        for t in list(prices_t):   # Monday fill placeholder: carry Friday's close
            if Dd in prices_t[t]:
                prices_t[t][nxt] = prices_t[t][Dd]
        blocked_t = {t: blocked_dates(bs) for t, bs in bars_t.items()}
        gaps_t = {t: news_gap_days(bs) for t, bs in bars_t.items() if bs}

        def elig(t, d):
            if t not in ok or d in blocked_t.get(t, ()) or not is_member(iv[t], d):
                return False
            return t not in sp or added.get(t, '0000') <= d
        r = run_momentum(prices_t, cal_t, START, look=LOOK, skip=SKIP, top_n=TOP_N, eligible=elig,
                         exec_next='close', prefer=booster(gaps_t, cal_t), prefer_mode='force',
                         prefer_rank=None, prefer_pool='all')
        fp = {d: sorted(h) for d, h in full['picks'] if d <= nxt}
        tp = {d: sorted(h) for d, h in r['picks']}
        past_ok = all(fp.get(d) == h for d, h in tp.items() if d < nxt)
        next_ok = tp.get(nxt) == fp.get(nxt)
        down_full, down_t = G['down'], downtrend_fn(bars_t)
        held = fp.get(max(d for d in fp if d <= Dd), [])
        split_ok = all(down_full(t, Dd) == down_t(t, Dd) for t in held)
        sf_t = filled({t: {d: v for d, v in s.items() if d <= Dd} for t, s in P['sleeve_px'].items()}, cal[:k + 1])
        sleeve_ok = best_of(sf_t, cal[:k + 1], k) == best_of(P['sleeve_f'], cal, k)
        res.append(dict(friday=Dd, pastTrades=past_ok, nextTrade=next_ok, nextPicks=tp.get(nxt),
                        downtrendRead=split_ok, sleevePick=sleeve_ok))
        log(f"  leak test {Dd}: past {past_ok} next {next_ok} split {split_ok} sleeve {sleeve_ok}")
    return res


# ---------------------------------------------------------------- C: outliers

def week_contrib(schedule, prices, calendar, spy):
    """[(trade date, asset, weight, asset return, SPY return)] per holding week."""
    days = [d for d, _ in schedule] + [calendar[-1]]
    out = []

    def px(t, d):
        s = prices.get(t, {})
        if d in s:
            return s[d]
        ks = [x for x in s if x <= d]
        return s[max(ks)] if ks else None
    for (d, w), nd in zip(schedule, days[1:]):
        if nd <= d:
            continue
        rs = spy[nd] / spy[d] - 1
        for t, x in w.items():
            a, b = px(t, d), px(t, nd)
            if a and b:
                out.append((d, t, x, b / a - 1, rs))
    return out


def outlier_table(contrib, spy, schedule, calendar):
    weeks = {}
    for d, t, x, r, rs in contrib:
        weeks.setdefault(d, [0.0, rs])
        weeks[d][0] += x * r
    order = sorted(weeks)

    def cagr(adj):
        v, n0 = 1.0, order[0]
        for d in order:
            v *= 1 + weeks[d][0] - adj.get(d, 0.0)
        yrs = (date.fromisoformat(calendar[-1]) - date.fromisoformat(n0)).days / 365.25
        return v ** (1 / yrs) - 1
    stock = [c for c in contrib if c[1] not in ASSETS]
    ranked = sorted(stock, key=lambda c: -c[2] * (c[3] - c[4]))
    spy_v = 1.0
    for d in order:
        spy_v *= 1 + weeks[d][1]
    yrs = (date.fromisoformat(calendar[-1]) - date.fromisoformat(order[0])).days / 365.25
    out = dict(base=cagr({}), spy=spy_v ** (1 / yrs) - 1, stockWeeks=len(stock), rows=[])
    for k in (1, 5, 10, 25, max(1, len(stock) // 100)):
        adj = {}
        for d, t, x, r, rs in ranked[:k]:
            adj[d] = adj.get(d, 0.0) + x * (r - rs)
        out['rows'].append(dict(removed=k, cagr=cagr(adj)))
    by_stock = {}
    for d, t, x, r, rs in stock:
        by_stock[t] = by_stock.get(t, 0.0) + math.log1p(x * (r - rs)) if x * (r - rs) > -1 else by_stock.get(t, 0.0)
    out['topStocks'] = [[t, round(v, 4)] for t, v in sorted(by_stock.items(), key=lambda kv: -kv[1])[:10]]
    beat = sum(1 for d in order if weeks[d][0] > weeks[d][1])
    ex = sorted(weeks[d][0] - weeks[d][1] for d in order)
    out.update(weeksBeatSpy=beat / len(order), weeks=len(order), medianWeeklyExcess=ex[len(ex) // 2],
               top10ShareOfExcess=sum(c[2] * (c[3] - c[4]) for c in ranked[:10]) /
               max(1e-12, sum(c[2] * (c[3] - c[4]) for c in stock)))
    return out


# ---------------------------------------------------------------- main

def r4(x):
    return None if x is None else round(float(x), 4)


def s4(st):
    return {k: r4(v) for k, v in st.items()}


def main():
    t0 = datetime.now()
    D = load_data()
    P = prepare(D)
    G['P'] = P
    G['down'] = downtrend_fn(D['bars'])
    cal = P['calendar']
    log(f"calendar {cal[0]} - {cal[-1]}; usable point-in-time series {len(P['ok'])}")
    cov = coverage(D, P)

    # 1. main runs
    jobs = [('base_top5', 'base', START, False, ()), ('base_boost', 'base', START, True, ()),
            ('pit_top5', 'pit', START, False, ()), ('pit_boost', 'pit', START, True, ())]
    runs = run_many(jobs)
    G['runs'] = runs
    down = G['down']

    # current (dashboard) plans, pre-tax, 0.05% costs
    cur_auto = dashboard_plan(runs['base_top5'], cal, P['sleeve_px'], down, START)
    cur_boost = dashboard_plan(runs['base_boost'], cal, P['sleeve_px'], down, START)
    spy_curve = [[b[0], b[4]] for b in D['bench']['SPY'] if b[0] >= START]
    qqq_curve = [[b[0], b[4]] for b in D['bench']['QQQ'] if b[0] >= START]
    px_all = dict(P['prices'])
    px_all.update(P['sleeve_px'])

    sched = {}
    for name in ('base_top5', 'base_boost', 'pit_top5', 'pit_boost'):
        sched[name] = plan_schedule(runs[name]['picks'], cal, P['sleeve_f'], down, START)
    sched['pit_top5_only'] = [(d, {t: 1 / TOP_N for t in h}) for d, h in runs['pit_boost']['picks'] if d >= START]

    # 2. ledger scenarios
    scen = {}

    def sim(key, s, **kw):
        res = simulate(s, px_all, cal, **kw)
        scen[key] = res
        log(f"  ledger {key}: final {res['final']:,.0f}")
        return res
    sim('base_boost_ledger_005', sched['base_boost'], slip=0.0005, taxes=False)
    for sl in SLIPS:
        sim(f'pit_boost_pretax_{sl}', sched['pit_boost'], slip=sl, taxes=False)
        sim(f'pit_auto_pretax_{sl}', sched['pit_top5'], slip=sl, taxes=False)
    sim('pit_boost_tax', sched['pit_boost'], slip=BASE_SLIP)
    sim('pit_boost_tax_fifo', sched['pit_boost'], slip=BASE_SLIP, method='fifo')
    sim('pit_boost_tax_niit', sched['pit_boost'], slip=BASE_SLIP, niit=0.038)
    sim('pit_auto_tax', sched['pit_top5'], slip=BASE_SLIP)
    spy_t = bench_after_tax(D, 'SPY', cal, START)
    qqq_t = bench_after_tax(D, 'QQQ', cal, START)
    spy_t2 = bench_after_tax(D, 'SPY', cal, START, 0.238, 0.238)
    qqq_t2 = bench_after_tax(D, 'QQQ', cal, START, 0.238, 0.238)

    # 3. leak test on sample Fridays
    rnd = random.Random(7)
    fridays = [f for f in last_sessions_of_weeks(cal) if '2011-01-01' <= f <= cal[-10]]
    sample = sorted(rnd.sample(fridays, 6))
    leaks = leak_test(D, P, sample)

    # 4. start dates + exclusions
    starts = []
    for y in range(2010, 2024):
        for m in ('01', '07'):
            s = next((d for d in cal if d >= f'{y}-{m}-01'), None)
            if s and s > START and s < cal[-260]:
                starts.append(s)
    contrib = week_contrib(sched['pit_boost'], px_all, cal, P['prices']['SPY'])
    out_tab = outlier_table(contrib, P['prices']['SPY'], sched['pit_boost'], cal)
    best = [t for t, _ in out_tab['topStocks'][:3]]
    jobs = [(f'start_{s}', 'pit', s, True, ()) for s in starts]
    jobs += [('ex_best1', 'pit', START, True, tuple(best[:1])), ('ex_best3', 'pit', START, True, tuple(best[:3]))]
    more = run_many(jobs)
    sweep = []
    for s in starts:
        sc = plan_schedule(more[f'start_{s}']['picks'], cal, P['sleeve_f'], down, s)
        res = simulate(sc, px_all, cal, BASE_SLIP, taxes=False)
        c = res['curve']
        end3 = (date.fromisoformat(s) + timedelta(days=round(3 * 365.25))).isoformat()
        sweep.append(dict(start=s, cagr=r4(cagr_between(c, s, cal[-1])), spy=r4(cagr_between(spy_curve, s, cal[-1])),
                          qqq=r4(cagr_between(qqq_curve, s, cal[-1])),
                          cagr3=r4(cagr_between(c, s, end3)) if end3 <= cal[-1] else None,
                          spy3=r4(cagr_between(spy_curve, s, end3)) if end3 <= cal[-1] else None))
    excl = {}
    for key in ('ex_best1', 'ex_best3'):
        sc = plan_schedule(more[key]['picks'], cal, P['sleeve_f'], down, START)
        res = simulate(sc, px_all, cal, BASE_SLIP, taxes=False)
        excl[key] = s4(stats(res['curve'], 0.015))

    # 5. assemble
    def summ(res):
        st = stats(res['curve'], 0.015)
        yrs = len(res['curve']) / 252
        return dict(**s4(st), final=round(res['final'], 2), preLiq=round(res['preLiq'], 2),
                    finalCagr=r4((res['final'] / START_CASH) ** (1 / yrs) - 1),
                    taxPaid=round(res.get('taxPaid', 0.0), 2), wash=round(res.get('wash', 0.0), 2),
                    stShare=r4(res.get('stShare')), turnover=r4(res.get('turnover')))
    yrs = len(spy_t['curve']) / 252
    bench = {k: dict(**s4(stats(v['curve'], 0.015)), final=round(v['final'], 2), preLiq=round(v['preLiq'], 2),
                     finalCagr=r4((v['final'] / START_CASH) ** (1 / yrs) - 1))
             for k, v in (('spy', spy_t), ('qqq', qqq_t), ('spy_niit', spy_t2), ('qqq_niit', qqq_t2))}
    payload = dict(
        generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), start=START, end=cal[-1],
        coverage=cov,
        current=dict(auto=s4(stats(cur_auto, 0.015)), boost=s4(stats(cur_boost, 0.015)),
                     top5=s4(stats([[d, v] for d, v in runs['base_top5']['curve'] if d >= START], 0.015)),
                     spy=s4(stats(spy_curve, 0.015)), qqq=s4(stats(qqq_curve, 0.015))),
        ledgerCheck=dict(dashboardBoost=s4(stats(cur_boost, 0.015)),
                         ledgerBoost=summ(scen['base_boost_ledger_005'])),
        pit=dict(top5=s4(stats([[d, v] for d, v in runs['pit_top5']['curve'] if d >= START], 0.015)),
                 boostTop5=s4(stats([[d, v] for d, v in runs['pit_boost']['curve'] if d >= START], 0.015))),
        scenarios={k: summ(v) for k, v in scen.items()},
        taxYears=scen['pit_boost_tax']['years'],
        taxYearsAuto=scen['pit_auto_tax']['years'],
        bench=bench,
        leakTest=leaks,
        startSweep=sweep,
        outliers=out_tab, exclusions=dict(stocks=best, **excl),
        curves={k: [[d, round(v, 2)] for d, v in weekly(c)] for k, c in (
            ('currentBoost', [[d, v * START_CASH] for d, v in cur_boost]),
            ('robustBoostPreTax', scen[f'pit_boost_pretax_{BASE_SLIP}']['curve']),
            ('robustBoostAfterTax', scen['pit_boost_tax']['curve']),
            ('spyAfterTax', spy_t['curve']), ('qqqAfterTax', qqq_t['curve']))},
        runtimeMin=round((datetime.now() - t0).total_seconds() / 60, 1))
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    log(f"wrote {OUT} in {payload['runtimeMin']} min")


if __name__ == '__main__':
    main()

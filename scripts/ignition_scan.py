#!/usr/bin/env python3
"""Builds data/ignition_scan.json for the "Next big thing watch" section of
docs/scanner.html (rendered by scripts/render_scanner.py).

Scans every US-listed common stock (Nasdaq Trader's nasdaqlisted.txt +
otherlisted.txt: Nasdaq, NYSE, NYSE American - not just the S&P 500 /
Nasdaq-100, since many 2021-2026 winners such as Celestica were outside
them) with a price of at least $5 and $10M+ average daily dollar volume, for
the ignition signatures in mtl/ignition.py. Then replays the same rules over
the last ~3 years to show how such flags actually did afterwards.

Usage:
    python scripts/ignition_scan.py                # full run (~5,000 tickers)
    python scripts/ignition_scan.py --limit 300    # quick test on a sample
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl import ignition as ig  # noqa: E402
from mtl.universe import load_ndx, load_sp500  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'ignition_scan.json')
LISTED = os.path.join(ROOT, 'data', 'listed.csv')
IND_CACHE = os.path.join(ROOT, 'data', 'ignition_industries.json')
URLS = ('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',
        'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt')
YEARS = 4                 # 1 year of warm-up for the 52-week / 200-day rules + ~3 years of flags
CHUNK = 200
RECENT = 20               # sessions of recent flags listed with their return since
GROUP_LOOK, GROUP_MIN = 5, 2
INFO_LIMIT = 120          # industry look-ups per run (cached in IND_CACHE)
SKIP_NAME = re.compile(r'warrant|\bunits?\b|\brights?\b|preferred|\bnotes?\b|debenture|%|\bdue 20|'
                       r'acquisition corp|\btrust\b.*\bunit|\bETN\b|exchange[- ]traded', re.I)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def short_name(n):
    n = re.split(r' - | Common Stock| Class [A-Z]\b| Ordinary Shares| American Depositary| Common Shares', n)[0]
    return n.strip().rstrip(',')


def parse_listed(text, other):
    """[(yahoo_symbol, name)] of the common stocks in one Nasdaq Trader file."""
    out = []
    rows = csv.DictReader(io.StringIO(text), delimiter='|')
    for r in rows:
        sym = (r.get('ACT Symbol') if other else r.get('Symbol')) or ''
        name = r.get('Security Name') or ''
        if not sym or sym.startswith('File Creation') or r.get('ETF') == 'Y' or r.get('Test Issue') == 'Y':
            continue
        if any(ch in sym for ch in '$^=+') or SKIP_NAME.search(name):
            continue
        out.append((sym.replace('.', '-'), short_name(name)))
    return out


def load_universe():
    """{symbol: name}: every listed common stock; falls back to the saved
    data/listed.csv when Nasdaq Trader can't be reached."""
    got = {}
    try:
        for url, other in zip(URLS, (False, True)):
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                got.update(parse_listed(resp.read().decode('utf-8', 'replace'), other))
        if len(got) < 3000:
            raise ValueError(f'only {len(got)} symbols parsed')
        with open(LISTED, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['symbol', 'name'])
            w.writerows(sorted(got.items()))
    except Exception as e:
        log(f'listing download failed ({e}); using saved {LISTED}')
        with open(LISTED, newline='') as f:
            got = {r['symbol']: r['name'] for r in csv.DictReader(f)}
    for s, (n, _) in {**load_sp500(), **load_ndx()}.items():
        got.setdefault(s, n)
    return got


SCREENER = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true'
IND_ALL = os.path.join(ROOT, 'data', 'industries_all.csv')
THEME_HISTORY = os.path.join(ROOT, 'data', 'theme_history.json')
WATCHLIST = os.path.join(ROOT, 'data', 'watchlist.json')
WATCH_FLAG_LOOK = 60      # sessions back to show a watchlist stock's latest flag


def load_watchlist():
    """{group: [ticker, ...]} from data/watchlist.json ('_'-prefixed keys are notes)."""
    try:
        with open(WATCHLIST) as f:
            w = json.load(f)
    except (OSError, ValueError):
        return {}
    return {g: [t.strip().upper() for t in ts] for g, ts in w.items() if not g.startswith('_') and isinstance(ts, list)}


def load_industries():
    """{symbol: industry} for ~6,000 US stocks from Nasdaq's stock screener (one
    request, one taxonomy for every exchange); the saved copy if it's unreachable."""
    try:
        req = urllib.request.Request(SCREENER, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=90) as resp:
            rows = json.load(resp)['data']['rows']
        got = {r['symbol'].strip().replace('/', '-').replace('.', '-'): r['industry'].strip()
               for r in rows if r.get('symbol') and (r.get('industry') or '').strip()}
        if len(got) < 3000:
            raise ValueError(f'only {len(got)} industries parsed')
        with open(IND_ALL, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['symbol', 'industry'])
            w.writerows(sorted(got.items()))
        return got
    except Exception as e:
        log(f'industry download failed ({e}); using saved {IND_ALL}')
        try:
            with open(IND_ALL, newline='') as f:
                return {r['symbol']: r['industry'] for r in csv.DictReader(f)}
        except OSError:
            return {}


def download(tickers, start):
    """Wide adjusted O/H/L/C/V DataFrames (dates x tickers)."""
    import pandas as pd
    import yfinance as yf
    parts = {k: [] for k in ('Open', 'High', 'Low', 'Close', 'Volume')}
    for k in range(0, len(tickers), CHUNK):
        part = tickers[k:k + CHUNK]
        log(f'  prices {k + len(part)}/{len(tickers)}')
        for attempt in range(3):
            try:
                df = yf.download(part, start=start, interval='1d', group_by='column', auto_adjust=True,
                                 threads=True, progress=False)
                break
            except Exception as e:
                log(f'    retry {attempt + 1}: {e}')
                time.sleep(5 * (attempt + 1))
        else:
            continue
        if df is None or df.empty:
            continue
        for f in parts:
            sub = df[f] if isinstance(df.columns, pd.MultiIndex) else df[[f]].rename(columns={f: part[0]})
            parts[f].append(sub)
    out = {f: pd.concat(v, axis=1).sort_index() for f, v in parts.items()}
    out = {f: d.loc[:, ~d.columns.duplicated()] for f, d in out.items()}
    keep = out['Close'].columns[out['Close'].notna().sum() > 0]
    return {f: d.reindex(columns=keep).astype(float) for f, d in out.items()}


def drop_partial_session(frames):
    """Before 4:30 pm New York the latest bar is today's unfinished session."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo('America/New_York'))
    C = frames['Close']
    if len(C) and C.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 30):
        log(f'dropping unfinished session {now.date()}')
        return {f: d.iloc[:-1] for f, d in frames.items()}
    return frames


def drop_thin_sessions(frames, share=0.5):
    """Yahoo sometimes has the latest session for only a few stocks; scoring that session would blank every
    stock's latest close. Drop trailing sessions priced for under `share` of the stocks the session before had."""
    C = frames['Close']
    n = len(C)
    while n > 1 and C.iloc[n - 1].notna().sum() < share * C.iloc[n - 2].notna().sum():
        log(f'dropping {C.index[n - 1].date()}: only {int(C.iloc[n - 1].notna().sum())} stocks priced')
        n -= 1
    return frames if n == len(C) else {f: d.iloc[:n] for f, d in frames.items()}


def industries(tickers, cache):
    """{ticker: industry}, filling the cache from Yahoo for unknown tickers."""
    import yfinance as yf
    seed = {}
    try:
        with open(os.path.join(ROOT, 'data', 'industries.csv'), newline='') as f:
            seed = {r['symbol']: r['industry'] for r in csv.DictReader(f)}
    except OSError:
        pass
    looked = 0
    for t in tickers:
        if t in cache or t in seed:
            continue
        if looked >= INFO_LIMIT:
            break
        looked += 1
        try:
            info = yf.Ticker(t).info or {}
        except Exception:
            continue                      # try again next run rather than caching a failure
        if info.get('industry') or info.get('sector'):
            cache[t] = info.get('industry') or info.get('sector')
    return {t: seed.get(t) or cache.get(t) or '' for t in tickers}


def next_earnings(t):
    """Next earnings date (ISO) from Yahoo, or None if unknown."""
    try:
        import yfinance as yf
        cal = yf.Ticker(t).calendar
        ds = cal.get('Earnings Date') if isinstance(cal, dict) else None
        ds = [d for d in (ds or []) if d]
        return min(ds).isoformat() if ds else None
    except Exception:   # noqa: BLE001
        return None


def watchlist_rows(watch, C, res, evs, spy, names, ind_all, theme_rows, last):
    """[{group, rows: [...], up, r63}] - nightly status of every watchlist stock:
    close, day, 1- and 3-month return vs SPY, relative strength, uptrend or
    not, distance from the 52-week high and its latest flag (last 60 sessions)."""
    latest = {}
    for r, t, k in evs:
        if r > last - WATCH_FLAG_LOOK:
            latest[t] = (r, k)               # evs are sorted by row: the last one wins
    rank = {r['ind']: (i, r['heat']) for i, r in enumerate(theme_rows, 1)}
    sp = lambda n: spy.iat[last] / spy.iat[last - n] - 1
    out = []
    for g, ts in watch.items():
        rows = []
        for t in ts:
            if t not in C.columns or not C[t].iloc[-5:].notna().any():
                rows.append(dict(t=t, n=names.get(t, ''), missing=True))
                continue
            c = C[t].iat[last]
            ret = lambda n: r4(c / C[t].iat[last - n] - 1 - sp(n)) if C[t].iat[last - n] == C[t].iat[last - n] else None
            hi = C[t].iloc[last - 251:last + 1].max()
            sma50 = C[t].iloc[last - 49:last + 1].mean()
            rs = res['rs'][t].iat[last]
            fl = latest.get(t)
            trend = bool(res['trend'][t].iat[last])
            earn = next_earnings(t)
            if earn and earn < C.index[last].date().isoformat():
                earn = None
            rows.append(dict(t=t, n=names.get(t, ''), close=r4(c), chg=r4(res['chg'][t].iat[last]), r21=ret(21), r63=ret(63),
                             rs=None if rs != rs else int(rs), offHigh=r4(c / hi - 1) if hi == hi else None,
                             state='up' if trend else ('mixed' if c > sma50 else 'down'),
                             flag=None if not fl else dict(kind=fl[1], d=C.index[fl[0]].date().isoformat(), days=last - fl[0]),
                             earn=earn, ind=ind_all.get(t, ''), indRank=rank.get(ind_all.get(t, ''), (None, None))[0]))
        live = [r for r in rows if not r.get('missing')]
        r63s = [r['r63'] for r in live if r.get('r63') is not None]
        out.append(dict(group=g, rows=rows, up=sum(r['state'] == 'up' for r in live), n=len(live),
                        r63=r4(float(sorted(r63s)[len(r63s) // 2])) if r63s else None))
    return out


def r4(x):
    return None if x is None or x != x else round(float(x), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='scan only the first N tickers (testing)')
    ap.add_argument('--cache', help='pickle the downloaded prices here and reuse them (testing)')
    a = ap.parse_args()

    names = load_universe()
    tickers = sorted(names)
    if a.limit:
        tickers = tickers[:a.limit]
    watch = load_watchlist()
    tickers = sorted(set(tickers) | {t for ts in watch.values() for t in ts})
    log(f'{len(tickers)} listed common stocks')
    start = (date.today() - timedelta(days=int(365.25 * YEARS) + 10)).isoformat()
    if a.cache and os.path.exists(a.cache):
        import pickle
        with open(a.cache, 'rb') as f:
            fr = pickle.load(f)
    else:
        fr = download(tickers + ['SPY'], start)
        if a.cache:
            import pickle
            with open(a.cache, 'wb') as f:
                pickle.dump(fr, f)
    fr = drop_thin_sessions(drop_partial_session(fr))
    O, H, L, C, V = (fr[k] for k in ('Open', 'High', 'Low', 'Close', 'Volume'))
    spy = C.pop('SPY').ffill()
    for d in (O, H, L, V):
        d.drop(columns=['SPY'], inplace=True, errors='ignore')
    log(f'{C.shape[1]} tickers with prices, {len(C)} sessions to {C.index[-1].date()}')

    res = ig.compute(O, H, L, C, V)
    flags, last = res['flags'], len(C) - 1
    warm = 252
    evs = ig.events(flags, start_row=warm)

    try:
        with open(IND_CACHE) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    recent_rows = [(r, t, k) for r, t, k in evs if r > last - RECENT and k != 'pocket']
    today = [(t, k) for r, t, k in evs if r == last]
    need = list(dict.fromkeys([t for t, _ in today] + [t for _, t, _ in recent_rows]))
    ind_all = load_industries()       # one taxonomy for display, groups and the industry ranking
    ind = {**industries([t for t in need if not ind_all.get(t)], cache), **{t: ind_all[t] for t in need if ind_all.get(t)}}
    with open(IND_CACHE, 'w') as f:
        json.dump(dict(sorted(cache.items())), f, indent=0)

    # industries with 2+ different stocks flagging (not pocket pivots) in the last few sessions
    grp = {}
    for r, t, k in recent_rows:
        if r > last - GROUP_LOOK and ind.get(t):
            grp.setdefault(ind[t], set()).add(t)
    groups = sorted(([g, sorted(ts)] for g, ts in grp.items() if len(ts) >= GROUP_MIN), key=lambda x: -len(x[1]))
    hot = {g for g, _ in groups}

    def row(t, k, r=last):
        c, hi = C[t].iat[r], res['hi52'][t].iat[r]
        off = c / hi - 1 if hi == hi and hi else None
        reps = int(res['repeats'][t].iat[r])
        rs = res['rs'][t].iat[r]
        return dict(t=t, n=names.get(t, ''), ind=ind.get(t, ''), kind=k, close=r4(c), low=r4(L[t].iat[r]), chg=r4(res['chg'][t].iat[r]),
                    gap=r4(res['gap'][t].iat[r]), vr=r4(res['vr'][t].iat[r]), rs=None if rs != rs else int(rs),
                    offHigh=r4(off), repeats=reps, group=ind.get(t, '') in hot,
                    score=ig.score(k, None if rs != rs else rs, reps, off, ind.get(t, '') in hot))

    today_rows = sorted((row(t, k) for t, k in today), key=lambda x: -x['score'])
    recent = []
    for r, t, k in sorted(recent_rows, key=lambda x: (-x[0], x[1])):
        entry, now = C[t].iat[r], C[t].iat[last]
        recent.append(dict(d=C.index[r].date().isoformat(), t=t, n=names.get(t, ''), ind=ind.get(t, ''), kind=k,
                           days=last - r, since=r4(now / entry - 1), ex=r4(now / entry - spy.iat[last] / spy.iat[r]),
                           held=bool(now >= L[t].iat[r]), entry=r4(entry), close=r4(now), low=r4(L[t].iat[r]),
                           sma20=r4(C[t].iloc[last - 19:last + 1].mean()), repeats=int(res['repeats'][t].iat[last])))

    flagged20 = {t for r, t, k in evs if r > last - ig.THEME_LOOK and k != 'pocket'}
    theme_rows = ig.themes(C, res, ind_all or ind, flagged20, spy)
    try:
        with open(THEME_HISTORY) as f:
            history = json.load(f)
    except (OSError, ValueError):
        history = []
    as_of = C.index[last].date().isoformat()
    history = [h for h in history if h[0] != as_of]
    fresh = set(ig.new_leaders([r['ind'] for r in theme_rows], history))
    for r in theme_rows:
        r['newTop'] = r['ind'] in fresh
    history = (history + [[as_of, [r['ind'] for r in theme_rows[:25]]]])[-60:]
    with open(THEME_HISTORY, 'w') as f:
        json.dump(history, f, separators=(',', ':'))

    watch_out = watchlist_rows(watch, C, res, evs, spy, names, ind_all, theme_rows, last)

    scan = dict(
        generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        asOf=C.index[last].date().isoformat(),
        listed=len(tickers), priced=int(C.shape[1]), liquid=int(res['liquid'].iloc[last].sum()),
        mechanical=bool(res['mech'].iat[last]),
        market=dict(spy=r4(spy.iat[last]), sma50=r4(spy.iloc[-50:].mean()), sma200=r4(spy.iloc[-200:].mean())),
        watch=watch_out,
        today=today_rows, recent=recent, groups=groups, themes=theme_rows[:25], themeCount=len(theme_rows),
        stats={**ig.hit_stats(C, spy, evs), 'all': ig.baseline(C, spy, res['liquid'], warm)}, statsFrom=C.index[warm].date().isoformat(),
        rules=dict(minPrice=ig.MIN_PRICE, minDollarVol=ig.MIN_DOLLAR_VOL, ignGap=ig.IGN_GAP, ignVol=ig.IGN_VOL,
                   turnGap=ig.TURN_GAP, turnVol=ig.TURN_VOL, brkVol=ig.BRK_VOL, recent=RECENT),
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(scan, f, separators=(',', ':'))
    log(f"wrote {OUT}: {len(today_rows)} flags today, {len(recent)} in the last {RECENT} sessions, {len(evs)} since {scan['statsFrom']}")


if __name__ == '__main__':
    main()

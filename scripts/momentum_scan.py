#!/usr/bin/env python3
"""Builds data/momentum_scan.json for the "Top 5 Strongest" dashboard
(docs/scanner.html, rendered by scripts/render_scanner.py).

The rule (same as scripts/backtest_momentum.py's best fair version):
every week's last session, rank the S&P 500 + Nasdaq-100 stocks by their
6-month return skipping the latest month (126 / 21 sessions), require
beating SPY over the same window, and hold the top 5 in equal weight; a
holding stays while it still ranks in the top 10. S&P stocks count only
from the day they joined the index; the Nasdaq-only members have no join
dates, so the track record carries a little hindsight from them. A stock
is skipped for 150 sessions after a one-day close move beyond +200% /
-80% (unadjusted spin-offs and data glitches read as crashes).

Usage:
    python scripts/momentum_scan.py               # writes data/momentum_scan.json
    python scripts/momentum_scan.py --no-refresh  # don't refresh the index lists
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.backtest import curve_stats, resample  # noqa: E402
from mtl.momentum import ranking, run_momentum, trades_from_picks  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500, momentum_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'momentum_scan.json')
START, LOOK, SKIP, TOP_N, TABLE = '2020-01-02', 126, 21, 5, 100
GLITCH_BLOCK = 150
STATE = {'uptrend': 'up', 'downtrend': 'down', 'choppy': 'chop', None: None}


def fetch(tickers, start='2015-01-01', chunk=100, adjusted=False):
    """{ticker: [(date, open, high, low, close)]} - closes are split-adjusted
    (adjusted=True: also dividend-adjusted, used for the benchmarks)."""
    import yfinance as yf
    out = {}
    for k in range(0, len(tickers), chunk):
        part = tickers[k:k + chunk]
        print(f"  prices {k + len(part)}/{len(tickers)}", file=sys.stderr, flush=True)
        df = yf.download(part, interval='1d', start=start, group_by='ticker', auto_adjust=adjusted,
                         threads=True, progress=False)
        for t in part:
            try:
                d = df[t].dropna(subset=['Close'])
            except KeyError:
                continue
            out[t] = [(ts.date().isoformat(), float(o), float(h), float(l), float(c))
                      for ts, o, h, l, c in zip(d.index, d['Open'], d['High'], d['Low'], d['Close'])]
    return out


def blocked_dates(bars):
    """Dates on which the stock is skipped: within GLITCH_BLOCK sessions after
    a one-day close move beyond +200% / -80%."""
    out, last = set(), -10 ** 9
    for i in range(1, len(bars)):
        r = bars[i][4] / bars[i - 1][4] - 1 if bars[i - 1][4] else 0
        if r > 2.0 or r < -0.8:
            last = i
        if i - last <= GLITCH_BLOCK:
            out.add(bars[i][0])
    return out


def yearly(points):
    """{year: return} from [[date, value], ...]."""
    out, base, cur, last = {}, None, None, None
    for d, v in points:
        if d[:4] != cur:
            if cur is not None:
                out[cur] = last / base - 1
                base = last
            else:
                base = v
            cur = d[:4]
        last = v
    if cur is not None:
        out[cur] = last / base - 1
    return out


def ret(px, calendar, k, n):
    a = px.get(calendar[k - n]) if k - n >= 0 else None
    b = px.get(calendar[k])
    return b / a - 1 if a and b else None


def r4(x):
    return None if x is None else round(x, 4)


def growth(points):
    base = points[0][1]
    return [[d, round(100 * v / base, 3)] for d, v in points]


def weekly_thin(points):
    """Every 5th point plus the last - enough for a multi-year chart."""
    return points[::5] + ([points[-1]] if (len(points) - 1) % 5 else [])


def main():
    names = momentum_universe(refresh='--no-refresh' not in sys.argv)
    sp = load_sp500()
    added = load_added()
    tickers = sorted(names)
    print(f"Fetching daily history for {len(tickers)} stocks + SPY/QQQ...", file=sys.stderr)
    bars = fetch(tickers)
    bench = fetch(['SPY', 'QQQ'], adjusted=True)
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    calendar = [b[0] for b in bench['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        if d in blocked.get(t, ()):
            return False
        return t not in sp or added.get(t, '0000') <= d

    r = run_momentum(prices, calendar, START, look=LOOK, skip=SKIP, top_n=TOP_N, eligible=eligible)
    K = len(calendar) - 1
    as_of = calendar[K]
    now = ranking(prices, calendar, K, LOOK, SKIP, eligible)
    rank = {t: i + 1 for i, (t, _) in enumerate(now)}
    prev1 = {t: i + 1 for i, (t, _) in enumerate(ranking(prices, calendar, K - 5, LOOK, SKIP, eligible))}
    prev4 = {t: i + 1 for i, (t, _) in enumerate(ranking(prices, calendar, K - 20, LOOK, SKIP, eligible))}
    spy_score = (prices['SPY'][calendar[K - SKIP]] / prices['SPY'][calendar[K - LOOK]] - 1)

    picks = r['picks']
    holdings = picks[-1][1] if picks else []
    last_rebalance = picks[-1][0] if picks else None
    trades = trades_from_picks(picks)
    entry = {}
    for d, side, t in trades:
        if side == 'buy':
            entry[t] = d

    # what the rule would hold if the rebalance happened at today's close
    keep = sorted((t for t in holdings if rank.get(t, 10 ** 9) <= 2 * TOP_N), key=lambda t: rank[t])[:TOP_N]
    qualifying = [t for t, s in now if s > spy_score]
    preview = keep + [t for t in qualifying if t not in keep][:TOP_N - len(keep)]

    def row(t, detail=False):
        px, k = prices[t], K
        hi = max((px[d] for d in calendar[max(0, k - 251):k + 1] if d in px), default=None)
        out = dict(t=t, n=names.get(t, ('', ''))[0], sec=names.get(t, ('', ''))[1] or '',
                   ndx=t not in sp, rank=rank.get(t), score=r4(dict(now).get(t)),
                   vsSpy=r4(dict(now).get(t, 0) - spy_score) if t in rank else None,
                   r1m=r4(ret(px, calendar, k, 21)), r3m=r4(ret(px, calendar, k, 63)),
                   r12m=r4(ret(px, calendar, k, 252)), close=r4(px.get(calendar[k])),
                   d1w=(prev1[t] - rank[t]) if t in prev1 and t in rank else None,
                   d4w=(prev4[t] - rank[t]) if t in prev4 and t in rank else None,
                   offHigh=r4(px[calendar[k]] / hi - 1) if hi and px.get(calendar[k]) else None)
        bs = bars.get(t, [])
        if bs:
            daily = [(b[0],) + b[1:] for b in bs[-320:]]
            weekly = resample([(b[0] + "T00:00:00",) + b[1:] for b in bs[-800:]], 'W')[0]
            out['trend'] = [STATE[structure_signal(weekly, n=2, lookback=2)['state']],
                            STATE[structure_signal(daily, n=3, lookback=2)['state']]]
        if detail:
            out['spark'] = [r4(b[4]) for b in bs[-130:]][::3]
        return out

    table = [row(t, detail=i < 25) for i, (t, _) in enumerate(now[:TABLE])]
    held_rows = []
    for t in holdings:
        h = row(t, detail=True)
        h['since'] = entry.get(t)
        buy_px = prices[t].get(entry.get(t)) if entry.get(t) else None
        h['sinceRet'] = r4(prices[t][as_of] / buy_px - 1) if buy_px and prices[t].get(as_of) else None
        h['weeks'] = sum(1 for _ in [p for p in picks if entry.get(t) and p[0] >= entry[t]])
        held_rows.append(h)

    strat = [[d, v] for d, v, _ in r['curve']]
    spy = [[d, c] for d, c in ((b[0], b[4]) for b in bench['SPY']) if d >= START]
    qqq = [[d, c] for d, c in ((b[0], b[4]) for b in bench['QQQ']) if d >= START]
    curves = {'strategy': growth(strat), 'SPY': growth(spy), 'QQQ': growth(qqq)}
    years = {k: yearly(v) for k, v in curves.items()}
    stats = {k: curve_stats([p[1] for p in v]) for k, v in curves.items()}
    one_year = {k: (v[-1][1] / next(p[1] for p in v if p[0] >= calendar[max(0, K - 252)]) - 1) for k, v in curves.items()}

    d = date.fromisoformat(as_of)
    next_rebal = d + timedelta(days=(4 - d.weekday()) % 7 or (7 if d.weekday() == 4 else 0))
    payload = dict(
        generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), asOf=as_of,
        lastRebalance=last_rebalance, nextRebalance=next_rebal.isoformat(),
        rule=dict(look=LOOK, skip=SKIP, topN=TOP_N, keepRank=2 * TOP_N, start=START),
        universe=dict(total=len(names), sp=sum(1 for t in names if t in sp), ndxOnly=sum(1 for t in names if t not in sp)),
        spyScore=r4(spy_score), holdings=held_rows, preview=preview,
        changes=dict(sell=[t for t in holdings if t not in preview], buy=[t for t in preview if t not in holdings]),
        trades=[dict(d=d_, side=s, t=t, n=names.get(t, ('', ''))[0], px=r4(prices[t].get(d_)))
                for d_, s, t in trades[-24:]][::-1],
        table=table,
        curves={k: weekly_thin(v) for k, v in curves.items()},
        years=years,
        stats={k: dict(total=r4(s['total']), annual=r4(s['annual']), maxDD=r4(s['maxDD']), oneYear=r4(one_year[k]))
               for k, s in stats.items()},
        turnover=r4(r['turnover']))
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f"wrote {OUT}: as of {as_of}, holdings {', '.join(holdings)}", file=sys.stderr)


if __name__ == '__main__':
    main()

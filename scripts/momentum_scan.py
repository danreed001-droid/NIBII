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

The page's plan pairs the rule with the best-of sleeve (mtl/sleeve.py), whichever
of gold / bonds / dollar / commodities / T-bills had the best 6 months, no
leverage. 'Auto' (the default) holds 100% in the top 5 and moves to 60/40 for
the week when 2 or more holdings are in a daily lower-low downtrend at Friday's
close (the swing read shown on each card). 'Steps' scales with the count instead:
1 holding down -> 80/20, 2 -> 60/40, 3+ -> 40/60. Fixed 100/0, 80/20 and 60/40 mixes
are offered too. Signals come from each Friday's close; trades (stocks,
sleeve switch, reset to the split) are made on Monday before the close, and the
track record is computed that way.

Usage:
    python scripts/momentum_scan.py               # writes data/momentum_scan.json
    python scripts/momentum_scan.py --no-refresh  # don't refresh the index lists
"""
import json
import os
import sys
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.backtest import curve_stats, resample  # noqa: E402
from mtl.human import score as score_calls, signature  # noqa: E402
from mtl.momentum import last_sessions_of_weeks, ranking, run_momentum, trades_from_picks  # noqa: E402
from mtl.news import NEWS_GAP, NEWS_WINDOW, booster, news_gap_days, recent_gaps  # noqa: E402
from mtl.sleeve import ASSETS, NAMES, best_of, filled, plan_curve_dynamic, plan_curve_mix, six_month, sleeve_curve  # noqa: E402
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500, momentum_universe  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'momentum_scan.json')
START, LOOK, SKIP, TOP_N, TABLE = '2020-01-02', 126, 21, 5, 100
GLITCH_BLOCK = 150
PLAN_SPLITS = (1.0, 0.8, 0.6)          # fixed mixes offered next to 'auto'
AUTO_NEED, AUTO_LOW = 2, 0.6            # auto: 60/40 while 2+ holdings are in a daily downtrend, else 100%
STEPS = {0: 1.0, 1: 0.8, 2: 0.6}        # steps: 1 down -> 80/20, 2 -> 60/40, 3+ -> STEPS_MIN
STEPS_MIN = 0.4
CALLS_PATH = os.path.join(ROOT, 'docs', 'my_calls.json')   # the viewer's calls, synced from the page
GUARD_SHARE = 0.5                       # bear guard: this much of the stock part goes to SPY while SPY < a year ago
HUMAN_FROM = '2024-01-01'               # daily series shipped for scoring the viewer's own weekly calls
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


def split_key(x):
    """0.8 -> '80/20'."""
    a = round(x * 100)
    return f"{a}/{100 - a}"


def chart_data(bs, sessions=90):
    """The card's swing chart: the last `sessions` daily candles, every labeled
    swing in that window (from a 320-session read; each is only known 3 sessions
    after it forms), the daily read at each Friday close in the window (data up
    to that Friday only), and today's read."""
    if len(bs) < 40:
        return None
    window = bs[-sessions:]
    first = window[0][0]
    daily = [(b[0],) + tuple(b[1:]) for b in bs[-320:]]
    sig = structure_signal(daily, n=3, lookback=2)
    swings = [dict(d=s_['ts'], k=s_['type'][0], p=round(s_['price'], 2), l=s_['label'])
              for s_ in sig['swings'] if s_['label'] and s_['ts'] >= first]
    fridays = []
    for j, b in enumerate(bs):
        if b[0] >= first and date.fromisoformat(b[0]).weekday() == 4:
            part = [(x[0],) + tuple(x[1:]) for x in bs[max(0, j + 1 - 320):j + 1]]
            fridays.append([b[0], STATE[structure_signal(part, n=3, lookback=2)['state']]])
    return dict(c=[[b[0], round(b[1], 2), round(b[2], 2), round(b[3], 2), round(b[4], 2)] for b in window],
                sw=swings, fri=fridays, now=STATE[sig['state']])


def r4s(st):
    return dict(total=r4(st['total']), annual=r4(st['annual']), maxDD=r4(st['maxDD']))


def growth(points):
    base = points[0][1]
    return [[d, round(100 * v / base, 3)] for d, v in points]


def main():
    names = momentum_universe(refresh='--no-refresh' not in sys.argv)
    sp = load_sp500()
    added = load_added()
    tickers = sorted(names)
    print(f"Fetching daily history for {len(tickers)} stocks + SPY/QQQ...", file=sys.stderr)
    bars = fetch(tickers)
    bench = fetch(['SPY', 'QQQ'], adjusted=True)
    sleeve_px = {t: {b[0]: b[4] for b in bs} for t, bs in fetch(ASSETS, adjusted=True).items()}
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    calendar = [b[0] for b in bench['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        if d in blocked.get(t, ()):
            return False
        return t not in sp or added.get(t, '0000') <= d

    # decided on each Friday close, traded at Monday's close (you can't trade after the bell)
    r = run_momentum(prices, calendar, START, look=LOOK, skip=SKIP, top_n=TOP_N, eligible=eligible,
                     exec_next='close')
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
        if detail == 'chart':
            out['chart'] = chart_data(bs)
        return out

    # ranks 1-20 carry the swing chart (on-deck cards open it); the next few keep a sparkline
    table = [row(t, detail='chart' if i < 20 else i < 25) for i, (t, _) in enumerate(now[:TABLE])]
    # on a Friday the cards show what to own after Monday's trades (new buys flagged)
    signal_day = date.fromisoformat(as_of).weekday() == 4
    held_rows = []
    for t in (preview if signal_day else holdings):
        h = row(t, detail='chart')
        if t not in holdings:
            h['new'] = True
            held_rows.append(h)
            continue
        h['since'] = entry.get(t)
        buy_px = prices[t].get(entry.get(t)) if entry.get(t) else None
        h['sinceRet'] = r4(prices[t][as_of] / buy_px - 1) if buy_px and prices[t].get(as_of) else None
        h['weeks'] = sum(1 for _ in [p for p in picks if entry.get(t) and p[0] >= entry[t]])
        held_rows.append(h)

    # news boost: a second run where any stock that gapped up 12%+ on news (mtl/news.py) in the
    # last 4 weeks replaces the weakest holding. On a Friday the post-trade holdings come from a
    # run with one more (flat) session appended, so the pending Monday trade fills.
    gaps = {t: news_gap_days(bs) for t, bs in bars.items() if bs}
    boost_kw = dict(look=LOOK, skip=SKIP, top_n=TOP_N, eligible=eligible, exec_next='close',
                    prefer_mode='force', prefer_rank=None, prefer_pool='all')
    rb = run_momentum(prices, calendar, START, prefer=booster(gaps, calendar), **boost_kw)
    picks_b = rb['picks']
    hold_b = picks_b[-1][1] if picks_b else []
    after_b = hold_b
    if signal_day:
        nd = (today_d := date.fromisoformat(as_of)) + timedelta(days=3 if today_d.weekday() == 4 else 1)
        nd = nd.isoformat()
        added_px = [t for t in prices if prices[t].get(as_of)]
        for t in added_px:
            prices[t][nd] = prices[t][as_of]
        cal_x = calendar + [nd]
        try:
            rx = run_momentum(prices, cal_x, START, prefer=booster(gaps, cal_x), **boost_kw)
            if rx['picks'] and rx['picks'][-1][0] == nd:
                after_b = rx['picks'][-1][1]
        finally:
            for t in added_px:
                prices[t].pop(nd, None)

    strat = [[d, v] for d, v, _ in r['curve']]
    strat_b = [[d, v] for d, v, _ in rb['curve']]
    spy = [[d, c] for d, c in ((b[0], b[4]) for b in bench['SPY']) if d >= START]
    qqq = [[d, c] for d, c in ((b[0], b[4]) for b in bench['QQQ']) if d >= START]
    curves = {'strategy': growth(strat), 'SPY': growth(spy), 'QQQ': growth(qqq)}

    # the plan: top 5 + best-of sleeve at each split, no leverage
    sl_curve, sl_picks = sleeve_curve(sleeve_px, calendar, START)
    pick_days = [p[0] for p in picks]
    bar_days = {t: [b[0] for b in bs] for t, bs in bars.items()}
    down_cache = {}

    def held_at(d_):
        i = bisect_right(pick_days, d_) - 1
        return picks[i][1] if i >= 0 else []

    def in_downtrend(t, d_):
        if (t, d_) not in down_cache:
            j = bisect_right(bar_days.get(t, []), d_)
            daily = [(b[0],) + tuple(b[1:]) for b in bars.get(t, [])[max(0, j - 320):j]]
            down_cache[(t, d_)] = structure_signal(daily, n=3, lookback=2)['state'] == 'downtrend'
        return down_cache[(t, d_)]

    def auto_split(d_):
        return AUTO_LOW if sum(in_downtrend(t, d_) for t in held_at(d_)) >= AUTO_NEED else 1.0

    pick_days_b = [p[0] for p in picks_b]

    def held_at_b(d_):
        i = bisect_right(pick_days_b, d_) - 1
        return picks_b[i][1] if i >= 0 else []

    def auto_split_b(d_):
        return AUTO_LOW if sum(in_downtrend(t, d_) for t in held_at_b(d_)) >= AUTO_NEED else 1.0

    def n_down(d_):
        return sum(in_downtrend(t, d_) for t in held_at(d_))

    def steps_split(d_, n=None):
        return STEPS.get(n_down(d_) if n is None else n, STEPS_MIN)

    # bear guard: Auto, but while SPY closes below its level a year (252 sessions)
    # earlier, half of the stock part sits in SPY instead of the top 5
    kidx = {d_: i for i, d_ in enumerate(calendar)}
    spy_px = prices['SPY']

    def bear(d_):
        k = kidx[d_]
        return k >= 252 and spy_px[calendar[k]] < spy_px[calendar[k - 252]]

    def guard_weights(d_):
        s_ = auto_split(d_)
        g = GUARD_SHARE if bear(d_) else 0.0
        return {'top5': s_ * (1 - g), 'sleeve': 1 - s_, 'spy': s_ * g}

    spy_curve = [[d_, spy_px[d_]] for d_ in calendar if d_ >= START and d_ in spy_px]
    plans = {'auto': plan_curve_dynamic(strat, sl_curve, calendar, auto_split),
             'boost': plan_curve_dynamic(strat_b, sl_curve, calendar, auto_split_b),
             'steps': plan_curve_dynamic(strat, sl_curve, calendar, steps_split),
             'guard': plan_curve_mix({'top5': strat, 'sleeve': sl_curve, 'spy': spy_curve}, calendar, guard_weights)}
    for x in PLAN_SPLITS:
        plans[split_key(x)] = plan_curve_dynamic(strat, sl_curve, calendar, lambda d_, x=x: x)
    curves['plan'] = growth(plans['auto'])
    curves['steps'] = growth(plans['steps'])
    curves['guard'] = growth(plans['guard'])
    curves['boost'] = growth(plans['boost'])
    f = filled(sleeve_px, calendar)
    today = date.fromisoformat(as_of)
    week_ends = [k for k in range(K) if date.fromisoformat(calendar[k]).isocalendar()[:2]
                 != date.fromisoformat(calendar[k + 1]).isocalendar()[:2]]
    signal_k = K if signal_day else week_ends[-1]
    prev_k = max(k for k in week_ends if k < signal_k)
    six = six_month(f, calendar, K)
    sleeve = dict(
        held=best_of(f, calendar, signal_k), prevHeld=best_of(f, calendar, prev_k), preview=best_of(f, calendar, K),
        assets=[dict(t=t, n=NAMES[t], r6=r4(six[t]), r1m=r4(ret(f[t], calendar, K, 21)), close=r4(f[t].get(as_of)))
                for t in ASSETS],
        history=[dict(d=d_, t=t) for d_, t in sl_picks[-8:]][::-1],
        stats=r4s(curve_stats([p[1] for p in sl_curve])))
    plan_stats = {}
    for key, c in plans.items():
        st = curve_stats([p[1] for p in c])
        plan_stats[key] = dict(total=r4(st['total']), annual=r4(st['annual']), maxDD=r4(st['maxDD']))
    # this week's auto mix: decided at the signal Friday's close from the holdings going into it
    sig_d, prev_d = calendar[signal_k], calendar[prev_k]
    auto = dict(need=AUTO_NEED, low=split_key(AUTO_LOW),
                split=split_key(auto_split(sig_d)), prevSplit=split_key(auto_split(prev_d)),
                down=[t for t in held_at(sig_d) if in_downtrend(t, sig_d)],
                checked=held_at(sig_d), decided=sig_d,
                weeksLow=sum(1 for f in last_sessions_of_weeks(calendar) if f >= START and auto_split(f) < 1),
                weeks=sum(1 for f in last_sessions_of_weeks(calendar) if f >= START),
                steps=dict(split=split_key(steps_split(sig_d)), prevSplit=split_key(steps_split(prev_d)),
                           weeksLow=sum(1 for f in last_sessions_of_weeks(calendar) if f >= START and steps_split(f) < 1)))
    gw, gp = guard_weights(sig_d), guard_weights(prev_d)
    k_sig = kidx[sig_d]
    auto['guard'] = dict(bear=bear(sig_d), prevBear=bear(prev_d), share=GUARD_SHARE,
                         weights=[r4(gw['top5']), r4(gw['sleeve']), r4(gw['spy'])],
                         prevWeights=[r4(gp['top5']), r4(gp['sleeve']), r4(gp['spy'])],
                         spyNow=r4(spy_px[sig_d]), spyYearAgo=r4(spy_px[calendar[k_sig - 252]]) if k_sig >= 252 else None,
                         spyClose=r4(spy_px[as_of]),
                         weeksBear=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START and bear(f_)))
    news_now = recent_gaps(gaps, calendar, K)
    auto['boost'] = dict(
        gap=NEWS_GAP, window=NEWS_WINDOW,
        split=split_key(auto_split_b(sig_d)), prevSplit=split_key(auto_split_b(prev_d)),
        down=[t for t in held_at_b(sig_d) if in_downtrend(t, sig_d)],
        holdings=after_b, prev=hold_b,
        sell=[t for t in hold_b if t not in after_b], buy=[t for t in after_b if t not in hold_b],
        boosted=[t for t in after_b if t not in (preview if signal_day else holdings)],
        replaced=[t for t in (preview if signal_day else holdings) if t not in after_b],
        gaps=[dict(t=t, d=d_, n=names.get(t, ('', ''))[0], held=t in after_b) for t, d_ in sorted(news_now.items(), key=lambda x: x[1], reverse=True)],
        rows=[row(t, detail='chart') for t in after_b],
        weeksDiff=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START and set(held_at(f_)) != set(held_at_b(f_))),
        top5=r4s(curve_stats([p[1] for p in strat_b])))
    if not signal_day:   # mid-week preview with today's charts
        auto['previewDown'] = [t for t in holdings if in_downtrend(t, as_of)]
        auto['preview'] = split_key(AUTO_LOW if len(auto['previewDown']) >= AUTO_NEED else 1.0)
        auto['steps']['preview'] = split_key(steps_split(as_of, len(auto['previewDown'])))
        auto['guard']['previewBear'] = bear(as_of)

    # the viewer's own calls ("Mine") are scored in the browser from these: daily
    # values of the top-5 rule, the sleeve and T-bills (cash), and each week's
    # signal Friday -> trade day with the Auto and Steps stock shares
    sl_val, bil = dict(sl_curve), f['BIL']
    human_days = [[d_, round(v, 6), round(sl_val[d_], 6), r4(bil[d_])] for d_, v in strat
                  if d_ >= HUMAN_FROM and d_ in sl_val and bil.get(d_)]
    nxt = {calendar[i]: calendar[i + 1] for i in range(len(calendar) - 1)}
    coming_trade = (today + timedelta(days=(4 - today.weekday()) % 7 + 3)).isoformat()
    human_weeks = [[f_, nxt.get(f_, coming_trade), auto_split(f_), steps_split(f_)]
                   for f_ in [calendar[k] for k in week_ends] + ([as_of] if signal_day else [])
                   if f_ >= HUMAN_FROM]

    # score the viewer's own calls (swaps / drops on real prices) from the repo copy
    mine = None
    try:
        with open(CALLS_PATH) as fh:
            my_calls = (json.load(fh) or {}).get('calls') or {}
    except (OSError, ValueError):
        my_calls = {}
    if signature(my_calls):
        pick_at = {d_: h for d_, h in picks}
        kidx = {d_: i for i, d_ in enumerate(calendar)}
        rank_cache = {}

        def ranks_at(f_):
            if f_ not in rank_cache:
                rank_cache[f_] = {t: i + 1 for i, (t, _) in enumerate(ranking(prices, calendar, kidx[f_], LOOK, SKIP, eligible))}
            return rank_cache[f_]
        wk = [(w[0], w[1], w[2], w[3]) for w in human_weeks]
        args = (my_calls, calendar, wk, lambda d_: pick_at.get(d_, []), ranks_at, prices, sl_val, bil)
        scored, base = score_calls(*args), score_calls(*args, apply_picks=False)
        if scored:
            mine = dict(sig=signature(my_calls), curve=scored['curve'], base=base['curve'], weeks=scored['weeks'][-60:])

    years = {k: yearly(v) for k, v in curves.items()}
    stats = {k: curve_stats([p[1] for p in v]) for k, v in curves.items()}
    one_year = {k: (v[-1][1] / next(p[1] for p in v if p[0] >= calendar[max(0, K - 252)]) - 1) for k, v in curves.items()}

    signal_date = today + timedelta(days=(4 - today.weekday()) % 7)   # today if Friday, else the coming Friday
    trade_date = signal_date + timedelta(days=3)
    payload = dict(
        generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), asOf=as_of,
        lastRebalance=last_rebalance, signalDay=signal_day, signalDate=signal_date.isoformat(),
        tradeDate=trade_date.isoformat(),
        rule=dict(look=LOOK, skip=SKIP, topN=TOP_N, keepRank=2 * TOP_N, start=START),
        universe=dict(total=len(names), sp=sum(1 for t in names if t in sp), ndxOnly=sum(1 for t in names if t not in sp)),
        spyScore=r4(spy_score), holdings=held_rows, preview=preview,
        changes=dict(sell=[t for t in holdings if t not in preview], buy=[t for t in preview if t not in holdings]),
        trades=[dict(d=d_, side=s, t=t, n=names.get(t, ('', ''))[0], px=r4(prices[t].get(d_)))
                for d_, s, t in trades[-24:]][::-1],
        table=table,
        curves={k: [[d_, round(v, 2)] for d_, v in c] for k, c in curves.items()},   # daily: the page filters by date range
        years=years,
        stats={k: dict(total=r4(s['total']), annual=r4(s['annual']), maxDD=r4(s['maxDD']), oneYear=r4(one_year[k]))
               for k, s in stats.items()},
        turnover=r4(r['turnover']),
        sleeve=sleeve,
        human=dict(days=human_days, weeks=human_weeks, mine=mine),
        plan=dict(splits=['auto', 'boost', 'guard', 'steps', 'mine'] + [split_key(x) for x in PLAN_SPLITS], default='auto', stats=plan_stats, auto=auto))
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f"wrote {OUT}: as of {as_of}, holdings {', '.join(holdings)}", file=sys.stderr)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Builds data/momentum_scan.json for the "Top 5 Strongest" dashboard
(docs/scanner.html, rendered by scripts/render_scanner.py).

The rule (same as scripts/backtest_momentum.py's best fair version):
every week's last NYSE session (usually Friday), rank the S&P 500 stocks by their
6-month return skipping the latest month (126 / 21 sessions), require
beating SPY over the same window, and hold the top 5 in equal weight; a
holding stays while it still ranks in the top 10. Stocks count only from
the day they joined the index (the Nasdaq-100 names outside the S&P 500 are
fetched but not picked since Oct 19, 2026). A run on another weekday previews
the week's decision without trading it (stops aside). A stock
is skipped for 150 sessions after a one-day close move beyond +200% /
-80% (unadjusted spin-offs and data glitches read as crashes).

The page's plan pairs the rule with the best-of sleeve (mtl/sleeve.py), whichever
of gold / bonds / dollar / commodities / T-bills had the best 6 months, no
leverage. 'Auto' holds 100% in the top 5 and moves to 60/40 for
the week when 2 or more holdings are in a daily lower-low downtrend at Friday's
close (the swing read shown on each card). 'Steps' scales with the count instead:
1 holding down -> 80/20, 2 -> 60/40, 3+ -> 40/60. Fixed 100/0, 80/20 and 60/40 mixes
are offered too. The default plan is Boost + rotation (mtl/rotation.py): the Boost 100%
list, moved into TLT / GLD (or cash, the account can't hold T-bills) when SPY's swing structure turns down,
and all of it moved into whichever of TLT / GLD / SPY is up most over 3 months while most of the list's recent
sales were losers (the whipsaw switch; it stands aside while the 10-year yield and gold
are both up over 3 months), decided at any close and traded at the next. Signals come from each week's last
close; trades (stocks, sleeve switch, reset to the split) are made at the next session's close (usually
Monday), and the track record is computed that way. Data problems that change or stop a rule are listed
in the payload's dataIssues (shown on the page and sent as an alert).

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
from mtl.calendar_nyse import add_trading_days, is_trading_day, month_end_session, next_trading_day, previous_trading_day, week_end_session, week_ended  # noqa: E402
from mtl.momentum import blowoff_exit, last_sessions_of_weeks, surge_exit, market_armed, ranking, run_momentum, score_at, score_table, trades_from_picks  # noqa: E402
from mtl.heat import daily_closes, daily_heat, price_volume, weekly_heat  # noqa: E402
from mtl.options_sim import SLEEVE_SPREAD, call_sleeve_curve, quote_check, sleeve_call  # noqa: E402
from mtl.revisions import fetch_revisions, log_revisions  # noqa: E402
from mtl.rsi_line import rsi as rsi14, rsi_warning, support_breaks
from mtl.lowerhigh import apply_lowerhigh, lowerhigh_cash, lowerhigh_state, LH_DAYS  # noqa: E402
from mtl.trendline import TL_DAYS, trendline_state  # noqa: E402
from mtl.pricebreak import apply_pricebreak, break_days, hold_days, pricebreak_state  # noqa: E402
from mtl import fractal  # noqa: E402
from mtl.rebound import apply_rebound, rebound_days, rebound_state  # noqa: E402
from mtl.reentry import apply_reentry, reentry_days, reentry_state  # noqa: E402
from mtl.you2 import YOU2_START, block as you2_block, entries_of as you2_entries  # noqa: E402
from mtl import health, paper as paper_rec  # noqa: E402
from mtl.phase import market_phase  # noqa: E402
from mtl.fade import SWING_TH as FADE_SWING, VOL_TH as FADE_VOL, buy_ok as fade_buy_ok, fading as fade_check, ratios as fade_ratios  # noqa: E402
from mtl.narrow import apply_narrow, narrow_cash_days, narrow_reading, narrow_state, narrow_warnings, NARROW_DAYS, NARROW_DELAY, NARROW_HIGH, NARROW_LAG, NARROW_VIX  # noqa: E402
from mtl.rotation import CONFIRM as ROT_CONFIRM, CONFIRM_GAP as ROT_CONFIRM_GAP, MA as ROT_MA, ROT_ASSETS, SLOW as ROT_SLOW, WHIP_ASSETS, WHIP_LOOK, WHIP_LOSS, WHIP_MIN, WHIP_PCT, WHIP_SHARE, rotation_curve, rotation_modes, sales, switch_log, warning_log, warnings, whip_halves, whip_log, whip_pick, whipsaw, reflation, REGIME_LOOK, PICK_LOOK, BILLS_LOOK, CASH, CASH_FUND, bills_pick, no_bills  # noqa: E402
from mtl.chop import watch as chop_watch  # noqa: E402
from mtl.news import NEWS_GAP, NEWS_WINDOW, booster, news_gap_days, recent_gaps  # noqa: E402
from mtl.sleeve import (ASSETS, NAMES, best_of, filled, plan_curve_dynamic, plan_curve_mix,  # noqa: E402
                        plan_curve_scheduled, six_month, sleeve_curve)
from mtl.structure import structure_signal  # noqa: E402
from mtl.universe import load_added, load_sp500, momentum_universe  # noqa: E402
from mtl.widenet import WIDE_NET, scan as wide_net_scan  # noqa: E402
from mtl import crowding  # noqa: E402
from mtl import stress  # noqa: E402
from mtl.credit import BANKS as CREDIT_BANKS, JUNK as CREDIT_JUNK, watch as credit_watch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'momentum_scan.json')
START, LOOK, SKIP, TOP_N, TABLE = '2010-01-04', 126, 21, 5, 100
# the rule ranks by the plain 6-1 month return in equal weight. (Oct 2026: a weekly rank sum with the
# #1 holding at 2x was tried and reverted - it did worse on 2000-2009 data the rules were never tuned on.)
WIN = None
RANK = {}
RK = dict(open_end=True)   # live runs: the last day is a week-end only if it is the week's last NYSE session
GLITCH_BLOCK = 150
HEAT_EXTRA = ('AAPL', 'GOOGL', 'MSFT', 'NVDA', 'JNJ', 'UNH')   # always shown in the daily heatmap
PV3D_OTHERS = ['AAPL', 'NVDA', 'MSFT', 'SPY', 'QQQ']   # reference tickers beside the top 10 in the 3D price-volume chart
PV3D_NAMES = {'SPY': 'S&P 500 ETF', 'QQQ': 'Nasdaq-100 ETF'}
PLAN_SPLITS = (1.0, 0.8, 0.6)          # fixed mixes offered next to 'auto'
AUTO_NEED, AUTO_LOW = 2, 0.6            # monthly plans: 60/40 while 2+ holdings are in a daily downtrend, else 100%
# weekly Auto and Boost use the STEPS tiers below (1 holding down -> 80/20, 2 -> 60/40, 3+ -> 40/60)
STEPS = {0: 1.0, 1: 0.8, 2: 0.6}        # steps: 1 down -> 80/20, 2 -> 60/40, 3+ -> STEPS_MIN
STEPS_MIN = 0.4
BLOWOFF = 2.0                          # blow-off exit for Boost 100% / Boost + cushion (mtl.momentum.blowoff_exit)
BLOWOFF_MA = 150                       # ... only while SPY closes below its 150-session average
SURGE_UP, SURGE_VOL, SURGE_DELAY = 0.05, 4.0, 5   # surge exit (mtl.momentum.surge_exit): a 5%+ up day on 4x+ volume -> sold 5 sessions later
CUSHION, CUSHION_MA = 0.75, 150      # Boost + cushion: 25% in the sleeve while SPY closes below its 150-session average
REVISIONS_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'revisions_log.json')
CREDIT_LOOK = 21                       # ... and junk bonds (HYG) lagged quality bonds (LQD) over the last 21 sessions
CALLS_PATH = os.path.join(ROOT, 'docs', 'my_calls.json')   # the viewer's calls, synced from the page
PAPER_PATH = os.path.join(ROOT, 'data', 'paper_ledger.json')   # the default plan's paper record (mtl/paper.py)
GUARD_SHARE = 0.5                       # bear guard: this much of the stock part goes to SPY while SPY < a year ago
HUMAN_FROM = '2024-01-01'               # daily series shipped for scoring the viewer's own weekly calls
STATE = {'uptrend': 'up', 'downtrend': 'down', 'choppy': 'chop', None: None}


def cushion_log(calendar, week_ends, start, split, spy_gap, credit_gap, n=12):
    """The last n week-end signals where Boost + cushion changed its mix, newest first:
    [date, split, SPY vs its average, HYG vs LQD over the credit window]."""
    out, prev = [], None
    for f_ in week_ends:
        if f_ < start:
            continue
        s_ = split(f_)
        if prev is not None and s_ != prev:
            g_, c_ = spy_gap(f_), credit_gap(f_)
            out.append([f_, split_key(s_), None if g_ is None else round(g_, 4), None if c_ is None else round(c_, 4)])
        prev = s_
    return out[::-1][:n]


MACRO = sorted(({t for t, _ in stress.DOMINOES} | set(crowding.PRICE.values()) | {'IWM', 'GC=F'})
               - {'SPY', 'TLT', 'IEF', 'GLD', 'QQQ'})   # those come with the benchmark and haven prices


def fetch(tickers, start='2008-06-01', chunk=100, adjusted=False, volumes=None):
    """{ticker: [(date, open, high, low, close)]} - closes are split-adjusted
    (adjusted=True: also dividend-adjusted, used for the benchmarks). Pass a dict as
    `volumes` to also collect {ticker: {date: shares traded}}."""
    import yfinance as yf
    out = {}
    for k in range(0, len(tickers), chunk):
        part = tickers[k:k + chunk]
        print(f"  prices {k + len(part)}/{len(tickers)}", file=sys.stderr, flush=True)
        df = yf.download(part, interval='1d', start=start, group_by='ticker', auto_adjust=adjusted,
                         threads=True, progress=False)
        blank = {}   # ticker -> the latest day, when Yahoo's daily bar for it has no prices yet
        for t in part:
            try:
                d = df[t].dropna(subset=['Close'])
                raw = df[t]
            except KeyError:
                continue
            out[t] = [(ts.date().isoformat(), float(o), float(h), float(l), float(c))
                      for ts, o, h, l, c in zip(d.index, d['Open'], d['High'], d['Low'], d['Close'])]
            if volumes is not None and 'Volume' in raw:
                volumes[t] = {ts.date().isoformat(): int(v) for ts, v in zip(raw.index, raw['Volume']) if v == v}
            if len(raw) and raw['Close'].iloc[-1] != raw['Close'].iloc[-1]:
                blank[t] = raw.index[-1].date().isoformat()
        if blank:
            fill_from_minutes(out, blank, adjusted)
    return out


def minute_bar(day, rows):
    """One day's (date, open, high, low, close) from its 1-minute (New York time, open, high, low, close) rows,
    regular session only (9:30 to 16:00); None without any. The close is the last minute's, which can differ
    from the official closing print by a cent or two."""
    rows = [r for r in rows if r[0].date().isoformat() == day and (9, 30) <= (r[0].hour, r[0].minute) < (16, 0)
            and r[4] == r[4]]
    if not rows:
        return None
    return (day, float(rows[0][1]), float(max(r[2] for r in rows)), float(min(r[3] for r in rows)), float(rows[-1][4]))


def fill_from_minutes(out, blank, adjusted=False):
    """In the evening Yahoo's daily bar for the session just closed can come back with no prices (only volume) for
    hours (seen Oct 19-21, 2026), and the scan fell a day behind. Rebuild that day from its 1-minute bars; the next
    run reads the official daily bar again."""
    import yfinance as yf
    from zoneinfo import ZoneInfo
    try:
        df = yf.download(sorted(blank), interval='1m', period='5d', group_by='ticker', auto_adjust=adjusted,
                         prepost=False, threads=True, progress=False)
    except Exception as e:
        print(f"  1-minute fill failed: {e}", file=sys.stderr)
        return
    ny = ZoneInfo('America/New_York')
    for t, day in blank.items():
        try:
            m = df[t] if len(blank) > 1 or t in df.columns.get_level_values(0) else df
        except (KeyError, AttributeError):
            continue
        rows = [(ts.astimezone(ny), o, h, l, c) for ts, o, h, l, c in zip(m.index, m['Open'], m['High'], m['Low'], m['Close'])]
        bar = minute_bar(day, rows)
        if bar and (not out.get(t) or out[t][-1][0] < day):
            out.setdefault(t, []).append(bar)


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


def option_check(held_rows, bars, as_of, calendar, signal_day):
    """How to tell whether a 4-week at-the-money call on the #1 holding is cheap.
    Fair price ~ half the stock's usual 4-week move (~ 0.113 x HV x price); from the
    backtest the overlay paid when calls cost up to ~1.15x that and lost above ~1.35x."""
    import math
    if not held_rows:
        return None
    top = max(held_rows, key=lambda h: (h.get('w') or 0, -(h.get('rank') or 99)))
    bs = bars.get(top['t']) or []
    c = [b[4] for b in bs if b[4]]
    if len(c) < 80:
        return None
    S = c[-1]
    r = [math.log(c[i + 1] / c[i]) for i in range(len(c) - 64, len(c) - 1)]
    m = sum(r) / len(r)
    hv = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252)
    span = c[-273:] if len(c) >= 273 else c
    moves = [abs(span[i + 20] / span[i] - 1) for i in range(len(span) - 20)]
    usual = sum(moves) / len(moves)
    fair = 0.113 * hv * S
    trade = next_trading_day(as_of) if signal_day else date.fromisoformat(as_of)   # a Friday signal trades the next session
    exp = trade + timedelta(days=28)
    while exp.weekday() != 4:
        exp -= timedelta(days=1)
    earn = next_earnings(top['t'])
    return dict(t=top['t'], n=top.get('n'), price=r4(S), hv=r4(hv), usual=r4(usual), usualUsd=r4(usual * S),
                fair=r4(fair), cheap=r4(min(0.13 * hv * S, 0.57 * usual * S)),
                skip=r4(min(0.15 * hv * S, 0.70 * usual * S)),   # the stricter of the two reads
                expiry=exp.isoformat(), earnings=earn,
                earningsInside=bool(earn and trade.isoformat() <= earn <= exp.isoformat()))


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


def haven_closes(px, calendar, n=300):
    """The last n sessions' closes of SPY, GLD and TLT, for the scanner page's "Where the plan was" chart: it draws the
    backtest's lines (data/plan_history.json) and carries them on with these after the backtest ends."""
    days = calendar[-n:]
    out = dict(dates=days)
    for t in ('SPY', 'GLD', 'TLT'):
        c = px.get(t) or {}
        out[t] = [r4(c[d]) if c.get(d) else None for d in days]
    return out


def month_ends(calendar):
    """Completed month-ends only: sessions whose next session is in another month."""
    return [d for d, n in zip(calendar, calendar[1:]) if d[:7] != n[:7]]


def last_business_day(d):
    """The last NYSE session of d's month."""
    return date.fromisoformat(month_end_session(d))


def next_session(d_):
    """The next NYSE session after d_ (weekends and market holidays skipped)."""
    return next_trading_day(d_).isoformat()


WARN_HOLD = 63   # sessions a downtrend-warning call is held before it is scored


def warn_calls_block(warn, calendar, K, spy_px, asset_px, hold=WARN_HOLD, plan_px=None):
    """The viewer's own calls on downtrend-warning days (docs/my_calls.json 'warn'), scored from the
    call day's close over `hold` sessions (so far, until then): 'stay' earns the plan (plan_px, the
    default plan's value by date; SPY when not given), 'out' half TLT / half GLD. SPY is shown too."""
    plan_px = plan_px or spy_px
    kidx = {d: i for i, d in enumerate(calendar)}
    rows = []
    for d_, c in sorted((warn or {}).items(), reverse=True):
        if not isinstance(c, dict) or c.get('c') not in ('out', 'stay'):
            continue
        k = kidx.get(d_)
        if k is None:
            k = next((i for i, x in enumerate(calendar) if x >= d_), None)
        if k is None:
            continue
        e = min(K, k + hold)

        def r(px):
            a, b = px.get(calendar[k]), px.get(calendar[e])
            return b / a - 1 if a and b else None
        spy_r, t, g, pl = r(spy_px), r(asset_px.get('TLT', {})), r(asset_px.get('GLD', {})), r(plan_px)
        if spy_r is None or t is None or g is None or pl is None:
            continue
        duo = (t + g) / 2
        done = k + hold <= K
        due = calendar[k + hold] if done else None
        if not done:   # the NYSE session k + hold sessions on
            due = add_trading_days(calendar[K], k + hold - K)
        rows.append(dict(d=d_, c=c['c'], note=c.get('note') or '', spy=r4(spy_r), plan=r4(pl), duo=r4(duo), done=done, due=due,
                         right=(duo > pl) == (c['c'] == 'out') if done else None))
    sc = [x for x in rows if x['done']]
    me = st = ou = 1.0
    for x in reversed(sc):
        me *= 1 + (x['duo'] if x['c'] == 'out' else x['plan'])
        st *= 1 + x['plan']
        ou *= 1 + x['duo']
    return dict(hold=hold, calls=rows, n=len(sc), right=sum(1 for x in sc if x['right']),
                me=r4(me - 1), stay=r4(st - 1), out=r4(ou - 1))


BROAD_DOWN, BROAD_SHARE = -0.10, 0.20   # breadth read: a stock down 10%+ over 20 sessions; 20%+ of them = a broad selloff


def breadth(prices, calendar, K, n=20, down=BROAD_DOWN, skip=('SPY',)):
    """Share of the universe down `down` or more over the last n sessions at calendar[K] (and how many stocks were read)."""
    a, b = calendar[K - n], calendar[K]
    rr = [px[b] / px[a] - 1 for t, px in prices.items() if t not in skip and px.get(a) and px.get(b)]
    return (sum(1 for x in rr if x <= down) / len(rr) if rr else None), len(rr)


def whip_sales(picks, prices, held=None):
    """The sales the whipsaw check counts: [[date, ticker, buy close, sell close, return]] from `picks` (the Boost
    list with the fading-energy filter off). With `held` (the list actually held), a counted sale it never made (a
    stock the filter skipped) gets a sixth field, True."""
    real = {(d_, t) for d_, t, _, _ in sales(held, prices)} if held is not None else None
    return [[d_, t, r4(a_), r4(b_), r4(b_ / a_ - 1) if a_ and b_ else None] + ([True] if real is not None and (d_, t) not in real else [])
            for d_, t, a_, b_ in sales(picks, prices)]


def whip_block(modes, on, half, read, px, calendar, K, picks, prices, held=None):
    """The whipsaw switch now: on/off from the last weekly check, today's reading, the asset it moves
    into (part: the account's share in it), the Boost list's recent sales behind it (whip_sales), and its log."""
    as_of, y = calendar[K], calendar[K - 1]
    first = K - WHIP_LOOK + 1
    rec = [r_ for r_ in whip_sales(picks, prices, held) if calendar[max(0, first)] <= r_[0] <= as_of]
    lost = sum(1 for r_ in rec if r_[4] is not None and r_[4] < 0)
    pick, chg = whip_pick(read, px, calendar, K)
    days = [d_ for d_ in calendar if d_ in on]
    weekly = {t: STATE.get(read.leg(t, as_of, 'w')[0], read.leg(t, as_of, 'w')[0]) for t in WHIP_ASSETS}
    return dict(on=on.get(as_of, False), prevOn=on.get(y, False), half=half.get(as_of), held=half.get(y),
                trade=next_session(as_of) if half.get(as_of) != half.get(y) and modes.get(as_of, 'boost') == 'boost' else None,
                look=WHIP_LOOK, need=WHIP_MIN, loss=WHIP_LOSS, pctLook=WHIP_PCT, assets=list(WHIP_ASSETS), part=WHIP_SHARE,
                sales=rec[::-1][:12], n=len(rec), lost=lost, share=r4(lost / len(rec)) if rec else None,
                previewOn=len(rec) >= WHIP_MIN and lost / len(rec) >= WHIP_LOSS,
                pick=pick, chg={t: r4(v) for t, v in chg.items()}, weekly=weekly,
                daysOn=sum(1 for d_ in days if on[d_]), days=len(days), log=whip_log(on, half, calendar))


def regime_block(regime, rate, gold, calendar, K, look=REGIME_LOOK):
    """The rate/gold regime now: the 10-year yield and gold today and `look` sessions ago, whether
    both are up (reflation: the whipsaw half-switch stands aside), and the days it held."""
    def at(px, k):
        v = None
        for d_ in calendar[:k + 1]:
            v = px.get(d_, v)
        return v
    r1, r0, g1, g0 = at(rate, K), at(rate, K - look), at(gold, K), at(gold, K - look)
    days = [d_ for d_ in calendar if d_ >= START and regime.get(d_) is not None]
    return dict(on=regime.get(calendar[K]), look=look, rate=r4(r1), rate0=r4(r0), gold=r4(g1), gold0=r4(g0),
                goldChg=r4(g1 / g0 - 1) if g1 and g0 else None, daysOn=sum(1 for d_ in days if regime[d_]), days=len(days))


def rotation_block(modes, why, read, state, calendar, K, spy_gap, px):
    """What Boost + rotation holds, what changes at the next close, and the readings behind it."""
    as_of = calendar[K]
    mode, held = modes.get(as_of, 'boost'), modes.get(calendar[K - 1], 'boost')

    def leg(t, tf='d'):
        st, g = read.leg(t, as_of, tf)
        return [STATE.get(st, st), None if g is None else round(g, 4)]
    lab = read.labels('SPY', as_of, 'w')
    his = [x for x in lab if x['type'] == 'high']
    los = [x for x in lab if x['type'] == 'low']
    lh = None
    if his:
        k_h = calendar.index(his[-1]['ts'][:10]) if his[-1]['ts'][:10] in calendar else None
        g_h = spy_gap(calendar[k_h]) if k_h is not None else None
        c_h = {b_[0]: b_[4] for b_ in read.bars['SPY']}.get(his[-1]['ts'][:10])
        lh = dict(d=his[-1]['ts'][:10], px=r4(his[-1]['price']), label=his[-1]['label'],
                  ma=r4(c_h / (1 + g_h)) if g_h is not None and c_h else None)
    days = [d_ for d_ in calendar if d_ in modes]
    warn = warnings(read, read.bars, calendar, days[0] if days else as_of)
    spy_c = {b_[0]: b_[4] for b_ in read.bars['SPY']}
    closes = [spy_c.get(d_) for d_ in calendar]
    for i_ in range(1, len(closes)):
        closes[i_] = closes[i_] or closes[i_ - 1]
    brk = support_breaks(rsi14(closes))
    rw, rw_prev = rsi_warning(closes, calendar, K, brk=brk), rsi_warning(closes, calendar, K - 1, brk=brk)
    rw['prevOn'] = rw_prev['on']
    rw['log'] = [[calendar[i_], brk[i_][0], r4(spy_gap(calendar[i_]))] for i_ in sorted(brk)[-8:]][::-1]
    return dict(rsiWarn=rw,warn=warn.get(as_of), prevWarn=warn.get(calendar[K - 1]), warnDays=len(warn), warnLog=warning_log(warn, calendar),
                mode=mode, held=held, trade=next_session(as_of) if mode != held else None,
                confirm=ROT_CONFIRM, confirmGap=ROT_CONFIRM_GAP, slow=ROT_SLOW, ma=ROT_MA, assets=list(ROT_ASSETS),
                spy=dict(daily=leg('SPY'), weekly=leg('SPY', 'w'), gap=r4(spy_gap(as_of)), lastHigh=lh,
                         lows=[[x['ts'][:10], r4(x['price']), x['label']] for x in los[-2:]]),
                legs={t: leg(t) for t in ROT_ASSETS}, px={t: r4((px.get(t) or {}).get(as_of)) for t in ROT_ASSETS + ('BIL', CASH_FUND)},
                pick=PICK_LOOK, pickPct={t: r4(read.pct(t, as_of)) for t in ROT_ASSETS},
                rot=state['rot'], streak=state['streak'], cand=state['cand'], out=state['out'],
                daysOut=sum(1 for d_ in days if modes[d_] != 'boost'), days=len(days),
                switches=sum(1 for a_, b_ in zip(days, days[1:]) if modes[a_] != modes[b_]),
                log=switch_log(modes, why))


def plan_rules(spy_bars, calendar, start):
    """The two-scale buy rules (mtl/fractal.py, since Oct 26, 2026): the buy-freeze and green-light windows (calendar
    indices) read from SPY, and their signal log."""
    frozen, green, log = fractal.spy_windows(spy_bars, calendar, start)
    return dict(frozen=frozen, green=green, log=log)


def plan_exits(prices, volumes, cal_, fade=True, rules=None):
    """The default plan's stock part on top of the Boost list (scripts/backtest_strategies.py runs the same): the
    blow-off exit (a holding whose last month's gain is more than BLOWOFF times the 5 months before it is sold and
    barred for 4 weeks, only while SPY is below its BLOWOFF_MA-session average), the surge exit (a 5%+ up close on
    4x+ its 50-day volume -> sold a week later), and with `fade` the fading-energy filter (mtl/fade.py, since Oct 16,
    2026: a top-5 stock whose volume and daily swings have both faded isn't bought; its slot stays in cash until it
    leaves the top 5 or stops fading), and with `rules` (plan_rules) the two-scale buy rules on top of it: no new buys
    in a buy freeze, and the green light setting the filters aside (mtl/fractal.py, since Oct 26, 2026). fade=False is the list the whipsaw half-switch counts sales on."""
    blow_, surge_ = blowoff_exit(prices, cal_, BLOWOFF, market='SPY', ma=BLOWOFF_MA), surge_exit(prices, volumes, cal_, SURGE_UP, SURGE_VOL, SURGE_DELAY)
    out = dict(hold_exit=lambda t, k, e=None: blow_(t, k, e) or surge_(t, k, e))
    if fade:
        bw = fade_buy_ok(prices, volumes, cal_)
        if rules:
            bw = fractal.buy_rule(bw, rules['frozen'], rules['green'])
        out.update(buy_when=bw, buy_max_rank=TOP_N)
    return out


def plan_overlay(spy_bars, asset_bars, whip_px, picks_whip, prices, calendar, start, rate_px, rsp_px, vix_px, green=None,
                 spy_vol=None, week_closed=True):
    """Every rule of the default plan above its stock list, in the order the live plan applies them (the scanner and
    scripts/backtest_strategies.py both run this). Returns the day-by-day modes, why, half-switch and what the
    page shows of each rule. spy_vol: SPY's {date: volume} for the break re-entry rule (without it the rule doesn't
    run); week_closed: whether the calendar's last day closes a week (False on a live run before the week's last
    session)."""
    # the rotation: out of stocks into TLT / GLD when the swing structure says so (mtl/rotation.py); decided at any
    # close, traded at the next close
    rot_bars = {'SPY': spy_bars, **{t: asset_bars[t] for t in ROT_ASSETS if asset_bars.get(t)}}
    modes, why, read, state = rotation_modes(rot_bars, calendar, start)
    # ... plus the lower-high exit: when SPY's weekly swings make a lower high (or an early one with the
    # daily chart already turned down), two weeks in the stronger of TLT / GLD (T-bills if neither is
    # rising), then back to the plan (mtl/lowerhigh.py)
    lh_cash, lh_log = lowerhigh_cash(spy_bars, calendar, start, modes, dest=lambda d_: read.steepest(d_) or 'BIL')
    modes, why = apply_lowerhigh(modes, why, lh_cash, calendar)
    # ... plus the whipsaw half-switch: when most of the Boost list's recent sales were losers, half
    # goes into whichever of TLT / GLD / SPY is up most over 3 months (skipping weekly downtrends)
    whip_on = whipsaw(picks_whip, prices, calendar, start, open_end=True)
    # ... except while the 10-year yield and gold are both up over 3 months (reflation): then it stays in the Boost list
    regime = reflation(rate_px, whip_px.get('GLD') or {}, calendar)
    half = whip_halves(modes, whip_on, read, whip_px, calendar, skip=regime)
    # ... and the narrow-market cash week: a week after SPY sits near its high on a calm VIX while the
    # equal-weight S&P lags it, the whole account holds T-bills for a week (mtl/narrow.py)
    narrow_warn = narrow_warnings(prices['SPY'], rsp_px, vix_px, calendar) if rsp_px and vix_px else []
    narrow_cash = narrow_cash_days(narrow_warn, calendar)
    if green:   # ... except under the two-scale green light (mtl/fractal.py, since Oct 24, 2026)
        kidx = {d_: i for i, d_ in enumerate(calendar)}
        narrow_cash = {d_ for d_ in narrow_cash if kidx.get(d_) not in green}
    modes, why = apply_narrow(modes, why, {d_ for d_ in narrow_cash if d_ >= start}, calendar)
    # ... and the rebound rule: while SPY is 12%+ under its 3-month high, gold or bonds is up 2%+ since that high
    # and SPY's daily chart has made a higher low, the plan holds the Boost list whatever the rules above say
    # (mtl/rebound.py)
    reb_days = rebound_days(spy_bars, whip_px, calendar, start)
    modes, why, half, reb_held = apply_rebound(modes, why, half, reb_days, calendar)
    # ... and the break re-entry rule: after a 10% drop, SPY's weekly downtrend break and its daily break on fading
    # volume within 21 sessions of each other -> the Boost list for 21 decision days (mtl/reentry.py, since Oct 27, 2026)
    re_days, re_sig = reentry_days(prices['SPY'], spy_vol, calendar, start, week_closed) if spy_vol else (set(), [])
    modes, why, half, re_held = apply_reentry(modes, why, half, re_days, calendar)
    # ... and no T-bills (they can't be held in the account): wherever the rules above would hold T-bills, the
    # stronger of TLT / GLD over 3 months if it is up, else DBMF managed futures (mtl/rotation.py no_bills)
    modes, why, half = no_bills(modes, why, half, whip_px, calendar)
    # ... and the price-break haven rule: the day SPY closes under its 100-day average with that average and its 7-day
    # average both lower than 5 sessions ago, the haven pick (as above) for the next 10 sessions wherever the plan would
    # hold stocks (mtl/pricebreak.py)
    pb_breaks = break_days(prices['SPY'], calendar, start)
    modes, why, half, pb_held = apply_pricebreak(modes, why, half, hold_days(pb_breaks, calendar, start), whip_px, calendar)
    return dict(modes=modes, why=why, half=half, read=read, state=state, lh_cash=lh_cash, lh_log=lh_log,
                whip_on=whip_on, regime=regime, narrow_warn=narrow_warn, narrow_cash=narrow_cash, reb_held=reb_held, re_held=re_held, re_sig=re_sig,
                pb_breaks=pb_breaks, pb_held=pb_held)


def last_closed_session(now=None):
    """The latest NYSE session whose closing prices should be in by `now` (default: the clock), New York time:
    today once the close has printed (16:15, as for the paper record) on a trading day, else the session before.
    The scheduled run starts at 16:20 New York time in winter and 17:20 in summer, so both expect today's close."""
    from zoneinfo import ZoneInfo
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('America/New_York'))
    d = now.date()
    if is_trading_day(d) and now.time() >= paper_rec.CLOSE_ET:
        return d.isoformat()
    return previous_trading_day(d).isoformat()


def data_problems(as_of, calendar, bars, bench, asset_bars, rate_px, vix_px, sp, held, logged, expected=None,
                  watch=(), volumes=None, fund_px=None):
    """Plain-language problems with tonight's data that change (or stop) a rule: prices that stop before the
    last close that should be in (`expected`), a series a rule needs missing or behind, a stock the plan holds
    (or one near the top of the ranking, `watch`) with no price or no recent volume, a held stock out of the
    S&P 500, a stale member list, or many stocks that failed to download. The page shows them and the alert
    step opens an issue."""
    out, prev = [], calendar[-2] if len(calendar) > 1 else as_of
    if expected and as_of < expected:
        out.append(f"Prices stop on {as_of}, but {expected}'s close should be in: a data delay (the next run usually "
                   f"catches up), or a market closure the calendar doesn't know (add it to EXTRA_CLOSURES in "
                   f"mtl/calendar_nyse.py). Tonight's decision is from {as_of}'s close.")

    def last(ser):
        return max(ser) if ser else None
    # due: the last day each series should have. The bond market closes on Columbus and Veterans Day while
    # stocks trade, so the 10-year yield may be a session behind; everything else trades every NYSE session.
    for name, ser, what, due in (
            ('the 10-year Treasury yield (^TNX)', rate_px, "the rate/gold rule can't run, so the whipsaw switch can't stand aside", prev),
            ('the VIX', vix_px, "the narrow-market rule can't run", as_of),
            ('RSP (equal-weight S&P 500)', {b[0]: 1 for b in bench.get('RSP') or []}, "the narrow-market rule can't run", as_of),
            ('TLT', {b[0]: 1 for b in asset_bars.get('TLT') or []}, "the bond haven can't be read", as_of),
            ('GLD', {b[0]: 1 for b in asset_bars.get('GLD') or []}, "the gold haven can't be read", as_of),
            *([(f'{CASH_FUND} (managed futures)', fund_px, f"where neither gold nor bonds is up the plan falls back to plain cash instead of {CASH_FUND}", as_of)]
              if fund_px is not None else []),
            *([("SPY's trading volume", (volumes or {}).get('SPY') or {}, "the break re-entry rule can't run", as_of)]
              if volumes is not None else [])):
        ld = last(ser)
        if ld is None:
            out.append(f"No data for {name}: {what}.")
        elif ld < due:
            out.append(f"{name} stops on {ld} (data through {as_of} expected): {what} on current data.")
    for t in sorted(set(held) | set(logged)):
        if t not in sp:
            out.append(f"{t} has left the S&P 500 list: the plan no longer ranks it, so no sell signal will show. "
                       f"If you hold it, sell it at the next close.")
        elif not bars.get(t) or bars[t][-1][0] < as_of:
            out.append(f"{t} (held by the plan) has no price for {as_of}: check the stock before trading.")
    for t in [t for t in watch if t not in held and t not in logged]:
        if not bars.get(t) or bars[t][-1][0] < as_of:
            out.append(f"{t} (near the top of the ranking) has no price for {as_of}, so it dropped out of tonight's "
                       f"ranking: the stock list may be off until it comes back.")
    recent = calendar[-6:]
    for t in sorted(set(held) | set(logged) | set(watch)):
        v = (volumes or {}).get(t) or {}
        if volumes is not None and bars.get(t) and not any(v.get(d_) for d_ in recent):
            out.append(f"{t} has no trading volume in the last {len(recent)} sessions: the fading-energy and surge "
                       f"checks can't read it.")
    from mtl.universe import last_refreshed
    lr_ = last_refreshed()
    if lr_ is None or (date.fromisoformat(as_of) - lr_).days > 10:
        out.append(f"The S&P 500 member list was last refreshed {lr_ or 'never'}: its weekly refresh from Wikipedia keeps "
                   f"failing (the page layout may have changed), so index joins and removals since then are missing.")
    miss = sorted(t for t in sp if not bars.get(t) or bars[t][-1][0] < as_of)
    if len(miss) > 10:
        out.append(f"{len(miss)} S&P 500 stocks have no price for {as_of} (e.g. {', '.join(miss[:5])}): rankings and "
                   f"sales may be off.")
    return out


def main():
    names = momentum_universe(refresh='--no-refresh' not in sys.argv)
    sp = load_sp500()
    added = load_added()
    tickers = sorted(names)
    print(f"Fetching daily history for {len(tickers)} stocks + SPY/QQQ...", file=sys.stderr)
    volumes = {}   # share volume, for the 3D price-volume chart
    bars = fetch(tickers, volumes=volumes)
    bench = fetch(['SPY', 'QQQ', 'SPMO', 'HYG', 'LQD', 'RSP'], adjusted=True, volumes=volumes)   # SPMO: S&P 500 Momentum ETF, from Oct 2015; HYG/LQD: the cushion's credit check; RSP: equal-weight S&P 500 (narrow-market warning)
    asset_bars = fetch(ASSETS, adjusted=True)   # OHLC: Boost + rotation reads TLT's and GLD's swing structure
    try:   # managed futures (DBMF): held instead of plain cash when neither TLT nor GLD is up (mtl/rotation.py no_bills)
        fund_px = {b[0]: b[4] for b in (fetch([CASH_FUND], adjusted=True).get(CASH_FUND) or []) if b[4]}
    except Exception as e:
        print(f"  {CASH_FUND} fetch failed: {e}", file=sys.stderr)
        fund_px = {}
    try:   # the 10-year Treasury yield, for the rate/gold regime that can stand the half-switch aside
        rate_px = {b[0]: b[4] for b in (fetch(['^TNX']).get('^TNX') or []) if b[4]}
    except Exception as e:
        print(f"  10-year yield fetch failed: {e}", file=sys.stderr)
        rate_px = {}
    try:   # the VIX, for the narrow-market warning (mtl/narrow.py)
        vix_px = {b[0]: b[4] for b in (fetch(['^VIX']).get('^VIX') or []) if b[4]}
    except Exception as e:
        print(f"  VIX fetch failed: {e}", file=sys.stderr)
        vix_px = {}
    try:   # the wide-net watch (information only): about 40 assets the plan never holds (mtl/widenet.py)
        wide_bars = fetch(list(WIDE_NET), adjusted=True)
    except Exception as e:
        print(f"  wide-net fetch failed: {e}", file=sys.stderr)
        wide_bars = {}
    try:   # speculator crowding gauge (information only): CFTC weekly futures positions in their 3-year range (mtl/crowding.py)
        y_ = date.today().year
        crowd_gauge = crowding.gauge(crowding.fetch_years(range(y_ - crowding.YEARS + 1, y_ + 1)))
    except Exception as e:
        print(f"  crowding-gauge fetch failed: {e}", file=sys.stderr)
        crowd_gauge = None
    try:   # market stress card + crowding charts (information only): futures, the dollar index, 5 currencies, small caps
        macro_bars = fetch(MACRO, adjusted=True)   # (mtl/stress.py, mtl/crowding.py)
    except Exception as e:
        print(f"  market-stress fetch failed: {e}", file=sys.stderr)
        macro_bars = {}
    try:   # the credit watch (information only): banks and junk bonds against their 1-year highs, back to 1999
        credit_bars = fetch([CREDIT_BANKS, CREDIT_JUNK, 'SPY'], start='1999-01-01', adjusted=True)   # (mtl/credit.py)
    except Exception as e:
        print(f"  credit-watch fetch failed: {e}", file=sys.stderr)
        credit_bars = {}
    # a run before the close (by hand during the day, or the quarterly track refresh in the morning) must not read
    # the session still trading: keep only closes up to the last session that has closed
    cut_ = last_closed_session()
    for src_ in (bars, bench, asset_bars, wide_bars, credit_bars):
        for t_ in src_:
            src_[t_] = [b_ for b_ in src_[t_] or [] if b_[0] <= cut_]
    rate_px = {d_: v_ for d_, v_ in rate_px.items() if d_ <= cut_}
    vix_px = {d_: v_ for d_, v_ in vix_px.items() if d_ <= cut_}
    for t_ in volumes:
        volumes[t_] = {d_: v_ for d_, v_ in volumes[t_].items() if d_ <= cut_}
    sleeve_px = {t: {b[0]: b[4] for b in bs} for t, bs in asset_bars.items()}
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    calendar = [b[0] for b in bench['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        # picks come from S&P 500 members only (since Oct 19, 2026; the Nasdaq-100 names outside the S&P 500 were
        # dropped: the plan was tested on S&P 500 members, and adding them did worse point in time)
        if t not in sp or d in blocked.get(t, ()):
            return False
        return added.get(t, '0000') <= d

    # decided on each Friday close, traded at Monday's close (you can't trade after the bell)
    r = run_momentum(prices, calendar, START, look=LOOK, skip=SKIP, top_n=TOP_N, eligible=eligible,
                     exec_next='close', **RK)
    K = len(calendar) - 1
    as_of = calendar[K]
    rows_now = score_table(prices, calendar, K, LOOK, SKIP, WIN, 'rank', eligible)
    now = [(t, sc) for t, sc, _ in rows_now]
    rank = {t: i + 1 for i, (t, _) in enumerate(now)}
    prev1 = {t: i + 1 for i, (t, _) in enumerate(ranking(prices, calendar, K - 5, LOOK, SKIP, eligible, **RANK))}
    prev4 = {t: i + 1 for i, (t, _) in enumerate(ranking(prices, calendar, K - 20, LOOK, SKIP, eligible, **RANK))}
    spy_score = (prices['SPY'][calendar[K - SKIP]] / prices['SPY'][calendar[K - LOOK]] - 1)
    ret61 = {t: score_at(prices[t], calendar, K, LOOK, SKIP) for t, _ in now}   # shown as the 6-1m column
    # the monthly plans' own ranking (plain 6-1 month score)
    now_m = ranking(prices, calendar, K, LOOK, SKIP, eligible)
    rank_m = {t: i + 1 for i, (t, _) in enumerate(now_m)}
    qualifying_m = [t for t, s in now_m if s > spy_score]

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
    qualifying = [t for t, _, ok in rows_now if ok]
    preview = keep + [t for t in qualifying if t not in keep][:TOP_N - len(keep)]

    def row(t, detail=False):
        px, k = prices[t], K
        hi = max((px[d] for d in calendar[max(0, k - 251):k + 1] if d in px), default=None)
        out = dict(t=t, n=names.get(t, ('', ''))[0], sec=names.get(t, ('', ''))[1] or '',
                   ndx=t not in sp, rank=rank.get(t), score=r4(ret61.get(t)),
                   vsSpy=r4(ret61[t] - spy_score) if ret61.get(t) is not None else None,
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
    signal_day = week_ended(as_of)   # the week's last NYSE session: a Friday, or a Thursday before a Friday holiday
    held_rows = []
    shown = preview if signal_day else holdings
    if signal_day or not r['weights']:   # Monday's weights: equal
        wnow = {t: 1.0 / TOP_N for t in shown}
    else:
        wnow = r['weights'][-1][1]
    for t in shown:
        h = row(t, detail='chart')
        h['w'] = r4(wnow.get(t))
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
                    prefer_mode='force', prefer_rank=None, prefer_pool='all', **RK)
    def boost_run(extra=None):
        """The Boost run (and, on a Friday, its post-trade holdings from a run with one more
        flat session appended). extra(cal) -> more run_momentum kwargs for that calendar."""
        rr = run_momentum(prices, calendar, START, prefer=booster(gaps, calendar), **boost_kw, **(extra(calendar) if extra else {}))
        held = rr['picks'][-1][1] if rr['picks'] else []
        after = held
        if signal_day:
            nd = next_session(as_of)
            added_px = [t for t in prices if prices[t].get(as_of)]
            for t in added_px:
                prices[t][nd] = prices[t][as_of]
            cal_x = calendar + [nd]
            try:
                rx = run_momentum(prices, cal_x, START, prefer=booster(gaps, cal_x), **boost_kw, **(extra(cal_x) if extra else {}))
                if rx['picks'] and rx['picks'][-1][0] == nd:
                    after = rx['picks'][-1][1]
            finally:
                for t in added_px:
                    prices[t].pop(nd, None)
        return rr, held, after
    rb, hold_b, after_b = boost_run()
    picks_b = rb['picks']
    # Boost 100% and Boost + cushion: the Boost list with the blow-off and surge exits and the fading-energy
    # filter (plan_exits)
    # ... and the two-scale buy rules (mtl/fractal.py, since Oct 26, 2026): the buy freeze and the green light
    fz_rules = plan_rules(bench['SPY'], calendar, START)
    rbx, hold_bx, after_bx = boost_run(lambda cal_: plan_exits(prices, volumes, cal_, rules=fz_rules))
    picks_bx = rbx['picks']
    # the whipsaw half-switch reads the same list with the fading-energy filter off (since Oct 16, 2026): a stock the filter
    # skipped counts as if it had been bought and later sold, so the filter changes which stocks are bought, never when
    # half the account steps out (an empty slot is not a sale)
    picks_whip = run_momentum(prices, calendar, START, prefer=booster(gaps, calendar), **boost_kw,
                              **plan_exits(prices, volumes, calendar, fade=False))['picks']

    strat = [[d, v] for d, v, _ in r['curve']]
    strat_b = [[d, v] for d, v, _ in rb['curve']]
    strat_bx = [[d, v] for d, v, _ in rbx['curve']]
    spy = [[d, c] for d, c in ((b[0], b[4]) for b in bench['SPY']) if d >= START]
    qqq = [[d, c] for d, c in ((b[0], b[4]) for b in bench['QQQ']) if d >= START]
    curves = {'strategy': growth(strat), 'SPY': growth(spy), 'QQQ': growth(qqq)}
    spmo = [[b[0], b[4]] for b in bench.get('SPMO') or [] if b[0] >= START]
    if spmo:
        curves['SPMO'] = growth(spmo)   # starts later than the rest: the page lines it up with SPY on its first day

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
        return STEPS.get(sum(in_downtrend(t, d_) for t in held_at(d_)), STEPS_MIN)

    pick_days_b = [p[0] for p in picks_b]

    def held_at_b(d_):
        i = bisect_right(pick_days_b, d_) - 1
        return picks_b[i][1] if i >= 0 else []

    def auto_split_b(d_):
        return STEPS.get(sum(in_downtrend(t, d_) for t in held_at_b(d_)), STEPS_MIN)

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

    def spy_gap(d_):    # SPY vs its CUSHION_MA-session average (negative = below)
        k = kidx[d_]
        if k < CUSHION_MA - 1:
            return None
        return spy_px[calendar[k]] / (sum(spy_px[calendar[j]] for j in range(k - CUSHION_MA + 1, k + 1)) / CUSHION_MA) - 1

    hyg_px = {b[0]: b[4] for b in bench.get('HYG') or []}
    lqd_px = {b[0]: b[4] for b in bench.get('LQD') or []}

    def credit_gap(d_):  # HYG vs LQD over the last CREDIT_LOOK sessions (negative = junk bonds lagging)
        k = kidx[d_]
        if k < CREDIT_LOOK:
            return None
        a_, b_ = calendar[k - CREDIT_LOOK], d_
        if not all((hyg_px.get(a_), hyg_px.get(b_), lqd_px.get(a_), lqd_px.get(b_))):
            return None
        return (hyg_px[b_] / lqd_px[b_]) / (hyg_px[a_] / lqd_px[a_]) - 1

    def cushion_split(d_):
        # on only when both agree: SPY below its average AND junk bonds lagging (no credit data: SPY alone)
        r_, c_ = spy_gap(d_), credit_gap(d_)
        return CUSHION if r_ is not None and r_ < 0 and (c_ is None or c_ < 0) else 1.0

    def guard_weights(d_):
        s_ = auto_split(d_)
        g = GUARD_SHARE if bear(d_) else 0.0
        return {'top5': s_ * (1 - g), 'sleeve': 1 - s_, 'spy': s_ * g}

    spy_curve = [[d_, spy_px[d_]] for d_ in calendar if d_ >= START and d_ in spy_px]
    plans = {'auto': plan_curve_dynamic(strat, sl_curve, calendar, auto_split),
             'boost': plan_curve_dynamic(strat_b, sl_curve, calendar, auto_split_b),
             'boost100': plan_curve_dynamic(strat_bx, sl_curve, calendar, lambda d_: 1.0),   # Boost list + blow-off exit, always 100% stocks
             'cushion': plan_curve_dynamic(strat_bx, sl_curve, calendar, cushion_split),
             'steps': plan_curve_dynamic(strat, sl_curve, calendar, steps_split),
             'guard': plan_curve_mix({'top5': strat, 'sleeve': sl_curve, 'spy': spy_curve}, calendar, guard_weights)}
    # Boost + rotation (the default): the Boost 100% list with every rule above it (plan_overlay): the rotation,
    # the lower-high exit, the whipsaw half-switch, the narrow-market cash week, the rebound rule and no T-bills
    whip_px = {**filled({**sleeve_px, CASH_FUND: fund_px}, calendar), 'SPY': prices['SPY']}
    rsp_px = {b[0]: b[4] for b in bench.get('RSP') or []}
    ov = plan_overlay(bench['SPY'], asset_bars, whip_px, picks_whip, prices, calendar, START, rate_px, rsp_px, vix_px,
                      green=fz_rules['green'], spy_vol=volumes.get('SPY'), week_closed=week_ended(calendar[-1]))
    rot_modes, rot_why, whip_half, rot_read, rot_state = ov['modes'], ov['why'], ov['half'], ov['read'], ov['state']
    lh_cash, lh_log, whip_on, regime = ov['lh_cash'], ov['lh_log'], ov['whip_on'], ov['regime']
    narrow_warn, narrow_cash, reb_held = ov['narrow_warn'], ov['narrow_cash'], ov['reb_held']
    re_held, re_sig = ov['re_held'], ov['re_sig']
    pb_held = ov['pb_held']
    # a slot left empty at a trade inside a buy freeze holds the haven pick until the next trade (mtl/fractal.py)
    fz_pick = lambda k_: bills_pick(whip_px, calendar, k_)
    fz_fill = fractal.slot_fill(picks_bx, fz_rules['frozen'], calendar, START, fz_pick)
    strat_rot = fractal.slot_haven(strat_bx, picks_bx, fz_rules['frozen'], whip_px, calendar, START, fz_pick)
    plans['rotation'] = rotation_curve(strat_rot, whip_px, calendar, rot_modes, half=whip_half)
    for x in PLAN_SPLITS:
        plans[split_key(x)] = plan_curve_dynamic(strat, sl_curve, calendar, lambda d_, x=x: x)
    curves['plan'] = growth(plans['auto'])

    # monthly plans (tracked alongside the weekly ones): the same rule decided at the last
    # close of each month and traded at the next session's close; the auto mix and the
    # sleeve asset are decided and traded on the same schedule
    months = month_ends(calendar)
    mkw = dict(look=LOOK, skip=SKIP, top_n=TOP_N, eligible=eligible, exec_next='close', rebal_dates=set(months))
    rm = run_momentum(prices, calendar, START, **mkw)
    rmb = run_momentum(prices, calendar, START, prefer=booster(gaps, calendar), prefer_mode='force',
                       prefer_rank=None, prefer_pool='all', **mkw)

    def monthly_plan(run):
        pk = run['picks']
        pdays_ = [p[0] for p in pk]

        def held_m(d_):
            i = bisect_right(pdays_, d_) - 1
            return pk[i][1] if i >= 0 else []

        def split_m(d_):
            return AUTO_LOW if sum(in_downtrend(t, d_) for t in held_m(d_)) >= AUTO_NEED else 1.0
        curve = plan_curve_scheduled([[d_, v] for d_, v, _ in run['curve']], f_sl, calendar, months, split_m)
        return curve, held_m, split_m
    f_sl = filled(sleeve_px, calendar)
    m_auto, m_held, m_split = monthly_plan(rm)
    m_boost, mb_held, mb_split = monthly_plan(rmb)
    curves['monthly'] = growth(m_auto)
    curves['monthlyBoost'] = growth(m_boost)
    today_d = date.fromisoformat(as_of)
    dec_d = last_business_day(today_d)          # the month's last NYSE session
    if dec_d < today_d:
        dec_d = last_business_day(dec_d + timedelta(days=7))
    trd_d = next_trading_day(dec_d)
    last_dec = months[-1] if months else None

    def monthly_block(run, held_fn, split_fn, curve):
        pk = run['picks']
        hold = pk[-1][1] if pk else []
        tr = trades_from_picks(pk)
        ent = {}
        for d_, side_, t in tr:
            if side_ == 'buy':
                ent[t] = d_
        rows = []
        for t in hold:
            buy_px = prices[t].get(ent.get(t)) if ent.get(t) else None
            rows.append(dict(t=t, n=names.get(t, ('', ''))[0], sec=names.get(t, ('', ''))[1] or '',
                             since=ent.get(t), close=r4(prices[t].get(as_of)),
                             sinceRet=r4(prices[t][as_of] / buy_px - 1) if buy_px and prices[t].get(as_of) else None,
                             spark=[r4(b[4]) for b in bars.get(t, [])[-130:]][::3]))
        sp = split_fn(last_dec) if last_dec else 1.0
        st = curve_stats([p[1] for p in curve])
        return dict(holdings=rows, lastTrade=pk[-1][0] if pk else None, decided=last_dec,
                    split=split_key(sp), sleeve=best_of(f_sl, calendar, calendar.index(last_dec)) if last_dec and sp < 1 else None,
                    trades=[dict(d=d_, side=s_, t=t, n=names.get(t, ('', ''))[0], px=r4(prices[t].get(d_)))
                            for d_, s_, t in tr[-16:]][::-1],
                    stats=dict(total=r4(st['total']), annual=r4(st['annual']), maxDD=r4(st['maxDD'])),
                    turnover=r4(run['turnover']))
    # what the auto list would hold if the month ended at today's close
    keep_m = sorted((t for t in (rm['picks'][-1][1] if rm['picks'] else []) if rank_m.get(t, 10 ** 9) <= 2 * TOP_N),
                    key=lambda t: rank_m[t])[:TOP_N]
    preview_m = keep_m + [t for t in qualifying_m if t not in keep_m][:TOP_N - len(keep_m)]
    monthly = dict(nextDecision=dec_d.isoformat(), nextTrade=trd_d.isoformat(),
                   auto=monthly_block(rm, m_held, m_split, m_auto),
                   boost=monthly_block(rmb, mb_held, mb_split, m_boost),
                   preview=preview_m)
    curves['steps'] = growth(plans['steps'])
    curves['guard'] = growth(plans['guard'])
    curves['boost'] = growth(plans['boost'])
    curves['boost100'] = growth(plans['boost100'])
    curves['cushion'] = growth(plans['cushion'])
    curves['rotation'] = growth(plans['rotation'])
    # Boost 100% + call sleeve: 80% the plan, 20% best-case-priced 6-month calls on its new picks (mtl.options_sim)
    curves['calls'] = growth(call_sleeve_curve(plans['boost100'], picks_bx, prices, calendar))
    curves['cushionCalls'] = growth(call_sleeve_curve(plans['cushion'], picks_bx, prices, calendar))
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
    auto = dict(need=1, low=split_key(STEPS[1]), tiers=True,
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
    pick_days_bx = [p[0] for p in picks_bx]

    def held_at_bx(d_):
        i = bisect_right(pick_days_bx, d_) - 1
        return picks_bx[i][1] if i >= 0 else []
    blow_now = blowoff_exit(prices, calendar, BLOWOFF, market='SPY', ma=BLOWOFF_MA)
    surge_now = surge_exit(prices, volumes, calendar, SURGE_UP, SURGE_VOL, SURGE_DELAY)

    def surge_info(t, j):   # one surge day: date, % up, volume vs its 50-day average
        px_, vol_ = prices.get(t, {}), volumes.get(t, {})
        w_ = [vol_.get(calendar[i_]) for i_ in range(j - 50, j) if vol_.get(calendar[i_])]
        return dict(t=t, d=calendar[j], up=r4(px_[calendar[j]] / px_[calendar[j - 1]] - 1), x=round(vol_[calendar[j]] / (sum(w_) / len(w_)), 1))

    def sessions_ahead(n):   # the NYSE session n sessions after as_of
        return add_trading_days(as_of, n)
    # holdings with a surge in the last SURGE_DELAY sessions while held: sold on the scheduled day unless an
    # earlier rule sells them first
    surge_pending = []
    for t in after_bx:
        for j in sorted(surge_now.events(t)):
            if K - SURGE_DELAY < j <= K and t in held_at_bx(calendar[j]):
                surge_pending.append(dict(surge_info(t, j), sell=sessions_ahead(j + SURGE_DELAY + 1 - K)))   # decided j + delay, sold at the next close
    surge_log = []   # surge days of stocks held at the time, last 6 months (most recent first)
    for t in sorted({x for p_ in picks_bx for x in p_[1]}):
        for j in surge_now.events(t):
            if j >= K - 126 and t in held_at_bx(calendar[j]):
                surge_log.append(surge_info(t, j))
    surge_log.sort(key=lambda x: x['d'], reverse=True)
    armed_bx = market_armed(prices, calendar, 'SPY', ma=BLOWOFF_MA)
    spy_ma = sum(spy_px[calendar[k_]] for k_ in range(K - BLOWOFF_MA + 1, K + 1)) / BLOWOFF_MA
    last_flip = next((calendar[k_] for k_ in range(K, 0, -1) if armed_bx[k_] != armed_bx[k_ - 1]), None)

    def blow_ratio(t):     # last month's gain / the 5 months before it (None unless both are gains)
        px_ = prices.get(t, {})
        a_, b_, c_ = px_.get(calendar[K - 126]), px_.get(calendar[K - 21]), px_.get(calendar[K])
        if not (a_ and b_ and c_) or b_ <= a_ or c_ <= b_:
            return None
        return r4((c_ / b_ - 1) / (b_ / a_ - 1))
    sold_bx = [t for t in hold_bx if t not in after_bx]
    auto['boostx'] = dict(
        mult=BLOWOFF, ma=BLOWOFF_MA, armed=armed_bx[K], spy=r4(spy_px[calendar[K]]), spyMa=r4(spy_ma), since=last_flip,
        armedWeeks=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START and armed_bx[kidx[f_]]),
        holdings=after_bx, prev=hold_bx, sell=sold_bx, buy=[t for t in after_bx if t not in hold_bx],
        blown=[t for t in sold_bx if blow_now(t, K)],
        surged=[t for t in sold_bx if surge_now(t, K) and not blow_now(t, K)],
        surge=dict(up=SURGE_UP, vol=SURGE_VOL, delay=SURGE_DELAY, pending=surge_pending, log=surge_log[:10]),
        boosted=[t for t in after_bx if t not in (preview if signal_day else holdings)],
        replaced=[t for t in (preview if signal_day else holdings) if t not in after_bx],
        gaps=[dict(t=t, d=d_, n=names.get(t, ('', ''))[0], held=t in after_bx) for t, d_ in sorted(news_now.items(), key=lambda x: x[1], reverse=True)],
        rows=[row(t, detail='chart') for t in after_bx],
        ratio={t: blow_ratio(t) for t in after_bx},
        weeksDiff=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START and set(held_at_bx(f_)) != set(held_at_b(f_))),
        stops=rbx.get('stops', 0),
        armedAt=armed_bx[kidx[sig_d]], prevArmed=armed_bx[kidx[prev_d]])
    # fading-energy filter: top-5 stocks at the last decision that weren't bought (their slot sits in cash)
    fade_k = K if signal_day else kidx[sig_d]
    fade_now = fade_check(prices, volumes, calendar)
    cur_bx = after_bx if signal_day else hold_bx
    top_now = [t_ for t_, sc_, beats_ in score_table(prices, calendar, fade_k, LOOK, SKIP, eligible=eligible) if beats_][:TOP_N]
    skipped_bx = []
    for i_, t_ in enumerate(top_now):
        if t_ not in cur_bx and fade_now(t_, fade_k):
            vr_, sr_ = fade_ratios(prices, volumes, calendar, t_, fade_k)
            skipped_bx.append(dict(t=t_, rank=i_ + 1, vol=r4(vr_), swing=r4(sr_), n=names.get(t_, ('', ''))[0]))
    auto['boostx']['fade'] = dict(vol=FADE_VOL, swing=FADE_SWING, decided=calendar[fade_k], skipped=skipped_bx,
                                  cash=max(0, TOP_N - len(cur_bx)) if cur_bx else 0)

    def call_for(t):   # optional call sleeve: the 20% OTM 6-month call at best-case pricing
        cl = [prices[t].get(calendar[k_]) for k_ in range(max(0, K - 80), K + 1)]
        c = sleeve_call([c for c in cl if c], as_of)
        if c and '--no-quotes' not in sys.argv:
            c['quote'] = quote_check(t, c, as_of)
        return c
    auto['boostx']['calls'] = {t: call_for(t) for t in after_bx}
    auto['boostx']['callSpread'] = SLEEVE_SPREAD
    auto['boostx']['callBudget'], auto['boostx']['callSleeve'] = 0.10, 0.20
    # a blow-off sale decided at today's close on a weekday other than Friday fills at the next
    # session's close: flag it so the alert can go out the same evening
    pend_bx = rbx.get('pending')
    if not signal_day and pend_bx is not None and set(pend_bx) != set(hold_bx):
        nd_ = next_trading_day(as_of)
        auto['boostx']['midweek'] = dict(
            date=nd_.isoformat(), sell=[t for t in hold_bx if t not in pend_bx], buy=[t for t in pend_bx if t not in hold_bx],
            blown=[t for t in hold_bx if t not in pend_bx and blow_now(t, K)],
            surged=[t for t in hold_bx if t not in pend_bx and surge_now(t, K) and not blow_now(t, K)])
        for t in auto['boostx']['midweek']['buy']:
            auto['boostx']['calls'][t] = call_for(t)
    auto['cushion'] = dict(share=CUSHION, split=split_key(cushion_split(sig_d)), prevSplit=split_key(cushion_split(prev_d)),
                           ma=CUSHION_MA, spyGap=r4(spy_gap(sig_d)), previewSplit=split_key(cushion_split(as_of)), previewSpyGap=r4(spy_gap(as_of)),
                           weeksLow=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START and cushion_split(f_) < 1),
                           weeks=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START),
                           creditLook=CREDIT_LOOK, credit=r4(credit_gap(sig_d)), previewCredit=r4(credit_gap(as_of)),
                           weeksSpyLow=sum(1 for f_ in last_sessions_of_weeks(calendar) if f_ >= START and (spy_gap(f_) or 0) < 0),
                           log=cushion_log(calendar, last_sessions_of_weeks(calendar), START, cushion_split, spy_gap, credit_gap))
    auto['rotation'] = rotation_block(rot_modes, rot_why, rot_read, rot_state, calendar, K, spy_gap, {**sleeve_px, CASH_FUND: fund_px})
    nr_ = narrow_reading(prices['SPY'], rsp_px, vix_px, calendar, K) if rsp_px and vix_px else None
    auto['rotation']['narrow'] = dict(narrow_state(narrow_warn, narrow_cash, calendar, K),
                                      reading=None if nr_ is None else {k_: (r4(v_) if isinstance(v_, float) else v_) for k_, v_ in nr_.items()},
                                      delay=NARROW_DELAY, days=NARROW_DAYS, high=NARROW_HIGH, lag=NARROW_LAG, vix=NARROW_VIX,
                                      log=narrow_warn[-12:][::-1], ok=bool(rsp_px and vix_px),
                                      asset=rot_modes.get(as_of) if as_of in narrow_cash else None)
    if narrow_warn:   # the last decision day of the current or next cash run, rolled past today when needed
        end_k = calendar.index(narrow_warn[-1]) + NARROW_DELAY + NARROW_DAYS
        if end_k > K - 1:
            until = calendar[min(end_k, K)]
            for _ in range(max(0, end_k - K)):
                until = next_session(until)
            auto['rotation']['narrow']['until'] = until
    lh_ = lowerhigh_state(bench['SPY'], lh_cash, lh_log, calendar, K)
    if lh_['inCash']:   # what the account holds there after the no-T-bills swap
        lh_['asset'] = rot_modes.get(as_of, lh_['asset'])
    if lh_['reading']:
        lh_['reading'] = {k_: (r4(v_) if isinstance(v_, float) else v_) for k_, v_ in lh_['reading'].items()}
    if lh_log:   # the last decision day of the current two weeks, rolled past today when needed
        end_k = calendar.index(lh_log[-1][0]) + LH_DAYS - 1
        if end_k >= K:
            until = calendar[K]
            for _ in range(end_k - K):
                until = next_session(until)
            lh_['until'] = until
    auto['rotation']['lowerhigh'] = lh_
    rb_ = rebound_state(bench['SPY'], whip_px, calendar, K, reb_held)
    auto['rotation']['rebound'] = {k_: (r4(v_) if isinstance(v_, float) else v_) for k_, v_ in rb_.items()}
    auto['rotation']['pricebreak'] = pricebreak_state(prices['SPY'], calendar, K, pb_held)
    # the break re-entry rule (mtl/reentry.py): tonight's reading, whether it holds stocks next session, the signals
    re_ = reentry_state(prices['SPY'], volumes.get('SPY') or {}, calendar, K, re_held, re_sig, week_ended(calendar[K]))
    auto['rotation']['reentry'] = re_
    # the two-scale buy rules (mtl/fractal.py): SPY's weekly + daily reading and the freeze / green light now
    auto['rotation']['fractal'] = fractal.state(bench['SPY'], calendar, K, fz_rules['frozen'], fz_rules['green'], fz_rules['log'])
    # SPY trendline watch (information only): a rising weekly line touched 3 or 4 times about evenly (mtl/trendline.py)
    tw_ = trendline_state(bench['SPY'][:K + 1])
    tw_['prevOn'] = bool(tw_['last']) and 1 <= tw_['last']['ago'] <= TL_DAYS
    auto['rotation']['trendWatch'] = tw_
    try:
        with open(CALLS_PATH) as fh:
            warn_calls = (json.load(fh) or {}).get('warn') or {}
    except (OSError, ValueError):
        warn_calls = {}
    auto['rotation']['warnCalls'] = warn_calls_block(warn_calls, calendar, K, prices['SPY'], filled(sleeve_px, calendar),
                                                     plan_px=dict(plans['rotation']))
    br_now, br_n = breadth(prices, calendar, K)
    br_prev = breadth(prices, calendar, K - 1)[0]
    auto['rotation']['breadth'] = dict(down=r4(br_now), prev=r4(br_prev), n=br_n, cut=BROAD_DOWN, broad=BROAD_SHARE,
                                       hist=[[calendar[k_], r4(breadth(prices, calendar, k_)[0])] for k_ in range(K - 20, K + 1)])
    auto['rotation']['whip'] = whip_block(rot_modes, whip_on, whip_half, rot_read, whip_px, calendar, K, picks_whip, prices, held=picks_bx)
    # choppy-market watch (information only): the plan moved the whole account 3+ times in the last 40 sessions (mtl/chop.py)
    auto['rotation']['chop'] = chop_watch(rot_modes, whip_half, calendar, K)
    # credit watch (information only): banks and junk bonds cracking before SPY (mtl/credit.py)
    cr_ = {t_: {b_[0]: b_[4] for b_ in credit_bars.get(t_) or [] if b_[4]} for t_ in (CREDIT_BANKS, CREDIT_JUNK, 'SPY')}
    auto['rotation']['credit'] = credit_watch(cr_[CREDIT_BANKS], cr_[CREDIT_JUNK], cr_['SPY']) if all(cr_.values()) else None
    # wide-net watch (information only): the strongest of about 40 assets the plan never holds (mtl/widenet.py)
    px_ = lambda bs: {b_[0]: b_[4] for b_ in bs or [] if b_[4]}
    mx_ = {**{t_: px_(bs_) for t_, bs_ in macro_bars.items()}, **{t_: px_(bench.get(t_)) for t_ in ('SPY', 'QQQ', 'HYG', 'RSP')},
           **{t_: px_(asset_bars.get(t_)) for t_ in ('TLT', 'IEF', 'GLD')}}
    if crowd_gauge:   # the price under each crowding chart, at each report's Tuesday close (or the session before)
        for r_ in crowd_gauge['rows']:
            p_ = mx_.get(crowding.PRICE.get(r_['name'])) or {}
            ks_ = sorted(p_)
            for h_ in r_['hist']:
                j_ = bisect_right(ks_, h_[0]) - 1
                h_.append(round(p_[ks_[j_]], 4) if j_ >= 0 else None)
    auto['crowding'] = crowd_gauge
    # market stress card (information only): dominoes across 12 asset classes and the drop study's warning signs
    dom_ = stress.dominoes(mx_, calendar[K])
    auto['stress'] = dict(asOf=calendar[K], dominoes=dom_, hist=[[calendar[k_], stress.dominoes(mx_, calendar[k_])['n']] for k_ in range(K - 59, K + 1)],
                          warn=stress.warnings(mx_['SPY'], calendar[K], rsp=mx_.get('RSP'), iwm=mx_.get('IWM'), copper=mx_.get('HG=F'),
                                               gold=mx_.get('GC=F'), hyg=mx_.get('HYG'), ief=mx_.get('IEF')))
    auto['wideNet'] = wide_net_scan({t_: {b_[0]: b_[4] for b_ in bs_ if b_[4]} for t_, bs_ in wide_bars.items()},
                                    prices['SPY'], calendar, K) if wide_bars else None
    if auto['rotation']['whip']['pick'] == 'BIL':   # nothing up over 3 months: the no-T-bills swap
        auto['rotation']['whip']['pick'] = bills_pick(whip_px, calendar, K)
    auto['rotation']['noBills'] = dict(look=BILLS_LOOK, assets=list(ROT_ASSETS), pick=bills_pick(whip_px, calendar, K),
                                       pct={t: r4(whip_px[t][calendar[K]] / whip_px[t][calendar[K - BILLS_LOOK]] - 1)
                                            if whip_px.get(t, {}).get(calendar[K]) and whip_px.get(t, {}).get(calendar[K - BILLS_LOOK]) else None
                                            for t in ROT_ASSETS},
                                       fund=CASH_FUND, days=sum(1 for d_, m_ in rot_modes.items() if m_ in (CASH, CASH_FUND)))
    auto['rotation']['whip']['regime'] = regime_block(regime, rate_px, whip_px.get('GLD') or {}, calendar, K)
    if not signal_day:   # mid-week preview with today's charts
        auto['previewDown'] = [t for t in holdings if in_downtrend(t, as_of)]
        auto['preview'] = split_key(STEPS.get(len(auto['previewDown']), STEPS_MIN))
        auto['steps']['preview'] = split_key(steps_split(as_of, len(auto['previewDown'])))
        auto['guard']['previewBear'] = bear(as_of)

    # the viewer's own calls ("Mine") are scored in the browser from these: daily
    # values of the top-5 rule, the sleeve and cash, and each week's signal
    # Friday -> trade day with the Auto and Steps stock shares. Cash earns nothing:
    # the account can't hold T-bills, so cash is a flat 1.0 on the T-bill calendar.
    sl_val, bil = dict(sl_curve), {d_: 1.0 for d_, v_ in f['BIL'].items() if v_}
    strat_b_val = dict((d_, v) for d_, v in strat_b)
    strat_bx_val = dict((d_, v) for d_, v in strat_bx)
    # ... then the default plan's value and the GLD / TLT / DBMF closes, for the whole-account calls ('rotation', 'gold', 'bonds', 'mf')
    rot_val = {d_: v for d_, v in plans['rotation']}
    whole = {'rotation': rot_val, 'gold': whip_px.get('GLD') or {}, 'bonds': whip_px.get('TLT') or {}, 'mf': whip_px.get(CASH_FUND) or {}}
    human_days = [[d_, round(v, 6), round(sl_val[d_], 6), r4(bil[d_]), round(strat_b_val.get(d_, v), 6), round(strat_bx_val.get(d_, v), 6),
                   round(rot_val[d_], 6) if rot_val.get(d_) else None, r4(whole['gold'].get(d_)), r4(whole['bonds'].get(d_)), r4(whole['mf'].get(d_))] for d_, v in strat
                  if d_ >= HUMAN_FROM and d_ in sl_val and bil.get(d_)]
    nxt = {calendar[i]: calendar[i + 1] for i in range(len(calendar) - 1)}
    coming_trade = next_session(week_end_session(today))
    human_weeks = [[f_, nxt.get(f_, coming_trade), auto_split(f_), steps_split(f_), auto_split_b(f_), cushion_split(f_)]
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
                rank_cache[f_] = {t: i + 1 for i, (t, _) in enumerate(ranking(prices, calendar, kidx[f_], LOOK, SKIP, eligible, **RANK))}
            return rank_cache[f_]
        pick_at_b = {d_: h for d_, h in picks_b}
        wk = [tuple(w) for w in human_weeks]
        args = (my_calls, calendar, wk, lambda d_: pick_at.get(d_, []), ranks_at, prices, sl_val, bil)
        pick_at_bx = {d_: h for d_, h in picks_bx}
        kw = dict(boost_picks_at=lambda d_: pick_at_b.get(d_, []), boostx_picks_at=lambda d_: pick_at_bx.get(d_, []), whole=whole)
        scored, base = score_calls(*args, **kw), score_calls(*args, apply_picks=False, **kw)
        if scored:
            mine = dict(sig=signature(my_calls), curve=scored['curve'], base=base['curve'], weeks=scored['weeks'][-60:])

    # You-2: the viewer's own stocks, timed by the default plan (mtl/you2.py; docs/my_calls.json "you2")
    try:
        with open(CALLS_PATH) as fh:
            you2_doc = json.load(fh) or {}
    except (OSError, ValueError):
        you2_doc = {}
    you2_px, you2_t = dict(prices), {t for l in you2_entries(you2_doc).values() for t in l}
    if you2_t - set(prices):
        try:
            for t, bs in fetch(sorted(you2_t - set(prices)), start=(date.fromisoformat(as_of) - timedelta(days=400)).isoformat(), volumes=volumes).items():   # a year back: the fading check
                if bs:
                    you2_px[t] = {b[0]: b[4] for b in bs}
        except Exception as e:   # noqa: BLE001
            print(f"  You-2 price fetch failed: {e}", file=sys.stderr)
    you2_fade = fade_check(you2_px, volumes, calendar)
    you2 = you2_block(you2_doc, you2_px, whip_px, calendar, rot_modes, whip_half, plans['rotation'], prices['SPY'], K,
                      skip=you2_fade, why=lambda t_, k_: fade_ratios(you2_px, volumes, calendar, t_, k_))

    # Paper record (mtl/paper.py): log tonight's decision for the next close - only in the scheduled scanner
    # run (PAPER_LEDGER_WRITE=1) and only after the close - then score the ledger and replay each logged day
    paper_fp, paper_files = paper_rec.fingerprint(ROOT)
    ledger = paper_rec.load(PAPER_PATH) or paper_rec.new_ledger(paper_fp, paper_files)
    top_prev = [t for t, _, _ in score_table(prices, calendar, K - 1, LOOK, SKIP, WIN, 'rank', eligible)[:10]]
    data_issues = data_problems(as_of, calendar, bars, bench, asset_bars, rate_px, vix_px, sp, hold_bx,
                                ((ledger.get('entries') or [{}])[-1].get('list') or []), expected=last_closed_session(),
                                watch=top_prev, volumes=volumes, fund_px=fund_px)
    p_idx = {d_: i for i, d_ in enumerate(calendar)}
    p_days = [p_[0] for p_ in picks_bx]

    def p_list(s_):   # the Boost list held after the close of session s_
        i_ = bisect_right(p_days, s_) - 1
        return picks_bx[i_][1] if i_ >= 0 else []

    def p_replay(d_):
        i_ = p_idx.get(d_)
        if i_ is None or i_ + 1 >= len(calendar):
            return None
        return paper_rec.decision(d_, rot_modes.get(d_, 'boost'), whip_half.get(d_), p_list(calendar[i_ + 1]),
                                  slot=(fz_fill.get(calendar[i_ + 1]) or (None,))[0])
    p_stocks = after_bx if signal_day else (list(pend_bx) if pend_bx is not None else hold_bx)
    # tonight's empty slots: the haven pick when the next trade falls inside a buy freeze, else what the last trade put there
    p_slot = (fz_pick(K) if K + 1 in fz_rules['frozen'] else (fz_fill.get(as_of) or (None,))[0]) if len(p_stocks) < TOP_N else None
    p_now = paper_rec.decision(as_of, rot_modes.get(as_of, 'boost'), whip_half.get(as_of), p_stocks,
                               slot=p_slot if p_slot != CASH else None)
    auto['rotation']['fractal']['slot'] = p_slot if p_slot != CASH else None
    if os.environ.get('PAPER_LEDGER_WRITE') == '1' and paper_rec.after_close(as_of):
        if paper_rec.record(ledger, p_now, datetime.now(timezone.utc).isoformat(timespec='seconds'), paper_fp):
            paper_rec.save(PAPER_PATH, ledger)
            print(f"paper record: logged {as_of} ({p_now['mode']})", file=sys.stderr)
    paper = paper_rec.block(ledger, {**whip_px, **prices}, calendar, K, prices['SPY'], p_replay, paper_fp)
    paper['tonight'] = p_now
    data_issues += paper_rec.problems(ledger, paper, p_now, as_of, calendar)
    if not wide_bars:
        data_issues.append('The wide-net watch prices could not be downloaded, so that list is missing tonight (it never affects the plan).')
    if not macro_bars:
        data_issues.append('The futures and currency prices could not be downloaded, so the market stress card and the crowding charts are thin tonight (they never affect the plan).')
    if not crowd_gauge:
        data_issues.append('The CFTC futures positions could not be downloaded, so the crowding gauge is missing tonight (it never affects the plan).')
    # every problem also goes into the dated issues log behind the page's "Issues (last 2 weeks)" section
    issue_log = health.load()
    for x_ in data_issues:
        health.add(issue_log, as_of, 'scan', x_)
    health.save(issue_log)

    years = {k: yearly(v) for k, v in curves.items()}
    for k, v in curves.items():   # a curve that starts mid-year (SPMO, Oct 2015): no return for that part year
        if v and v[0][0][5:] > '01-15':
            years[k].pop(v[0][0][:4], None)
    stats = {k: curve_stats([p[1] for p in v]) for k, v in curves.items()}
    one_year = {k: (v[-1][1] / next(p[1] for p in v if p[0] >= calendar[max(0, K - 252)]) - 1) for k, v in curves.items()}

    # analyst estimate revisions for the top of the list and every plan's holdings (information only)
    if '--no-revisions' not in sys.argv:
        bx_hold = (auto.get('boostx') or {}).get('holdings') or []
        rev_t = list(dict.fromkeys([r_['t'] for r_ in table[:25]] + [h_['t'] for h_ in held_rows] + list(bx_hold)))
        print(f"Fetching estimate revisions for {len(rev_t)} stocks...", file=sys.stderr)
        revs = fetch_revisions(rev_t)
        for r_ in table + held_rows:
            if r_['t'] in revs:
                r_['rev'] = revs[r_['t']]
        if signal_day and revs:
            log_revisions(REVISIONS_LOG, as_of, revs, {t: rank.get(t) for t in revs})
    signal_date = date.fromisoformat(as_of if signal_day else week_end_session(today))   # this week's last NYSE session
    trade_date = next_trading_day(signal_date)
    payload = dict(
        generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), asOf=as_of,
        # the page turns red after this: the next session's run (22:20 UTC, a backup at 02:20) should be in by then
        nextUpdateBy=(next_trading_day(as_of) + timedelta(days=1)).isoformat() + 'T05:00:00Z',
        # bull run / correction / bear market label for the masthead (information only, mtl/phase.py)
        market=market_phase(calendar, [b_[4] for b_ in bench['SPY']], volumes.get('SPY') or {}, vix_px, prices,
                            [t_ for t_ in prices if t_ in sp]),
        lastRebalance=last_rebalance, signalDay=signal_day, signalDate=signal_date.isoformat(),
        tradeDate=trade_date.isoformat(),
        rule=dict(look=LOOK, skip=SKIP, topN=TOP_N, keepRank=2 * TOP_N, start=START),
        universe=dict(total=len(names), sp=sum(1 for t in names if t in sp), ndxOnly=sum(1 for t in names if t not in sp), picks='sp'),
        spyScore=r4(spy_score), holdings=held_rows, preview=preview,
        changes=dict(sell=[t for t in holdings if t not in preview], buy=[t for t in preview if t not in holdings]),
        trades=[dict(d=d_, side=s, t=t, n=names.get(t, ('', ''))[0], px=r4(prices[t].get(d_)))
                for d_, s, t in trades[-24:]][::-1],
        table=table,
        heat=dict(weekly_heat(prices, calendar, [t for t, _ in now[:15]], breadth=[t for t in prices if t != 'SPY']),   # top 15's weekly ranks, last 26 weeks
                  daily=daily_closes(prices, calendar, [t for t, _ in now[:15]])),   # their daily closes, ~6 months, for the overlay chart
        pv3d=price_volume({**prices, 'QQQ': {b[0]: b[4] for b in bench.get('QQQ', [])}}, volumes, calendar,
                          [t for t, _ in now[:10]], PV3D_OTHERS, {t: names.get(t, ('', ''))[0] or t for t in names} | PV3D_NAMES,
                          held=[h['t'] for h in held_rows]),   # top 10 + reference tickers: daily close and volume, ~6 months
        dheat=daily_heat(prices, calendar, [t for t, _ in now[:30]] + [t for t in HEAT_EXTRA if t in prices and t not in dict(now[:30])],
                         extra=[t for t in HEAT_EXTRA if t not in dict(now[:30])], breadth=[t for t in prices if t != 'SPY']),   # top 30 + a few large caps, last 30 days
        curves={k: [[d_, round(v, 2)] for d_, v in c] for k, c in curves.items()},   # daily: the page filters by date range
        havens=haven_closes(whip_px, calendar),   # SPY / GLD / TLT closes, last 300 sessions: the "Where the plan was" chart
        years=years,
        stats={k: dict(total=r4(s['total']), annual=r4(s['annual']), maxDD=r4(s['maxDD']), oneYear=r4(one_year[k]))
               for k, s in stats.items()},
        turnover=r4(r['turnover']),
        sleeve=sleeve,
        human=dict(days=human_days, weeks=human_weeks, mine=mine),
        monthly=monthly,
        option=option_check(held_rows, bars, as_of, calendar, signal_day),
        plan=dict(splits=['rotation', 'boost100', 'cushion', 'boost', 'auto', 'guard', 'steps', 'mine'] + [split_key(x) for x in PLAN_SPLITS], default='rotation', stats=plan_stats, auto=auto, you2=you2, paper=paper),
        dataIssues=data_issues)
    with open(OUT, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    print(f"wrote {OUT}: as of {as_of}, holdings {', '.join(holdings)}", file=sys.stderr)


if __name__ == '__main__':
    main()

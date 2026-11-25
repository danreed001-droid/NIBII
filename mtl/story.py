"""The "Today's story" card on the scanner page (information only; never part of the plan).

Each weekday evening a scheduled writer adds a short account of the day to data/story_log.json: what SPY did and why,
why it matters, and what to watch. The parts that come from the plan's own data are never written by hand: the
scanner run adds SPY's recent closes and, while the resistance-line exit (rule 22, mtl/resistline.py) holds the plan out
of stocks, the falling line and the close that would take it back in (scan_part below), and the page states where the
plan stands from that night's data. This module reads the rule's settings and its line-finding; it changes nothing the
rule does.

Pure apart from load(); no network."""
import json
import os
from datetime import date, timedelta

from mtl import calendar_nyse, resistline


def _next(d):
    return calendar_nyse.next_trading_day(d).isoformat()

KEEP = 30            # stories shown on the page (newest first)
SPY_N = 70           # sessions of SPY closes kept for the card's chart
AHEAD = 8            # sessions of the back-in level shown ahead


def load(path):
    """The story log's items, newest first ([] when the file is missing or broken)."""
    try:
        with open(path) as f:
            items = (json.load(f) or {}).get('items') or []
    except (OSError, ValueError):
        return []
    items = [x for x in items if isinstance(x, dict) and x.get('date') and x.get('headline')]
    return sorted(items, key=lambda x: x['date'], reverse=True)


def _limit(calendar, fired):
    """The decision day the rule hands back to the plan at the latest: the MAX_WEEKS-th week's last session after the
    day it fired (resistline.out_days), reaching past the data with the exchange calendar; and the trade day after it."""
    seen, d, n = 0, fired, 0
    while n < 40:
        d = _next(d)
        n += 1
        if calendar_nyse.week_ended(d):
            seen += 1
            if seen >= resistline.MAX_WEEKS:
                return d, _next(d)
    return None, None


def back_in(bars, calendar, k, resist):
    """While the resistance-line exit holds the plan out of stocks: its line (from its first top, falling `slope` a
    session), the close a session needs to go back in (line + BREAK) for the last sessions and the next AHEAD, the
    day it fired and the latest day it hands back. None when the rule is not holding the plan out."""
    if not (resist or {}).get('active'):
        return None
    log = resist.get('log') or []
    cur = next((x for x in log if x.get('back') is None and x.get('test')), None)
    if not cur or cur['test'] not in calendar:
        return None
    h, c = resistline._series(bars, calendar)
    r = resistline.reading(h, c, calendar.index(cur['test']))
    if not r or not r.get('line'):
        return None
    L = r['line']
    a, m, top = L['fromDate'], L['slope'], h[L['fromDate']]
    brk = 1 + resistline.BREAK
    past = [[calendar[j], round((top + m * (j - a)) * brk, 2)] for j in range(a, k + 1)]
    ahead, d = [], calendar[k]
    for i in range(1, AHEAD + 1):
        d = _next(d)
        ahead.append([d, round((top + m * (k + i - a)) * brk, 2)])
    last, trade = _limit(calendar, cur['date'])
    return dict(fromDate=calendar[a], top=round(top, 2), slope=round(m, 3), test=cur['test'], fired=cur['date'],
                to=cur.get('to') or 'CASH', line=past, ahead=ahead, next=ahead[0] if ahead else None,
                lastDecision=last, lastTrade=trade, brk=resistline.BREAK)


def scan_part(bars, calendar, k, rotation):
    """What the scanner run adds for the card: SPY's last SPY_N closes and the back-in line (or None)."""
    closes = [[b[0][:10], round(b[4], 2)] for b in bars if b[4] and b[0][:10] <= calendar[k]][-SPY_N:]
    try:
        bi = back_in(bars, calendar, k, (rotation or {}).get('resist'))
    except (ValueError, IndexError, KeyError, TypeError):
        bi = None
    return dict(spy=closes, backIn=bi)


def holding_words(mode):
    """The plan's holding in words."""
    return {'boost': 'stocks (the plan’s Boost list)', 'CASH': 'cash', 'TLT': 'long Treasury bonds (TLT)', 'GLD': 'gold (GLD)',
            'DBMF': 'managed futures (DBMF)', 'BIL': 'T-bills (BIL)'}.get(mode, mode or 'unknown')


def _fmt(d, year=False):
    x = date.fromisoformat(d)
    return x.strftime('%a %b ') + str(x.day) + (x.strftime(', %Y') if year else '')


def plan_lines(scan):
    """Where the plan stands, from that night's data: [(text, kind)], kind in {'state', 'back', 'note'}."""
    R = (((scan or {}).get('plan') or {}).get('auto') or {}).get('rotation') or {}
    mode, out = R.get('mode'), []
    if not mode:
        return out
    log = R.get('log') or []
    since = next((x[0] for x in log if x and x[2] == mode), None) if mode != 'boost' else next((x[0] for x in log if x and x[2] == 'boost'), None)
    out.append(('Holds ' + holding_words(mode) + (' since ' + _fmt(since) if since else '') + '.', 'state'))
    bi = ((scan or {}).get('story') or {}).get('backIn')
    if mode != 'boost' and bi and bi.get('next'):
        nd, lv = bi['next']
        out.append(('Back into stocks on a close above %s on %s (the falling line plus %.1f%%; it drops about %.2f a session)'
                    % (f'{lv:,.2f}', _fmt(nd), bi['brk'] * 100, -bi['slope']) +
                    (', or at the latest at the %s close (decided %s).' % (_fmt(bi['lastTrade']), _fmt(bi['lastDecision']))
                     if bi.get('lastTrade') else '.'), 'back'))
    t = R.get('trade')
    if t:
        out.append(('Trade at the %s close.' % _fmt(t), 'note'))
    else:
        out.append(('Tonight: no change.', 'note'))
    return out


def plan_short(scan):
    """The plan's position in a line or two for the WhatsApp version."""
    R = (((scan or {}).get('plan') or {}).get('auto') or {}).get('rotation') or {}
    mode = R.get('mode')
    if not mode:
        return []
    out = ['In ' + ('stocks' if mode == 'boost' else holding_words(mode)) + '.']
    bi = ((scan or {}).get('story') or {}).get('backIn')
    if mode != 'boost' and bi and bi.get('next'):
        nd, lv = bi['next']
        out.append('Back into stocks on a close above %s (%s)' % (f'{lv:,.1f}', _fmt(nd)) +
                   (', or at the latest at the %s close.' % _fmt(bi['lastTrade']) if bi.get('lastTrade') else '.'))
    if R.get('trade'):
        out.append('Trade at the %s close.' % _fmt(R['trade']))
    return out


# ---- the script-built story (no AI writing): numbers from the scanner's prices, words from news headlines ----

STRONG_SRC = {'AP News': 4, 'Reuters': 4, 'The Wall Street Journal': 4, 'WSJ': 4, 'Bloomberg.com': 3, 'Bloomberg': 3,
              'Kiplinger': 3, 'CNBC': 3, "Barron's": 2, 'The New York Times': 2, 'The Washington Post': 1, 'MarketWatch': 1,
              "Investor's Business Daily": 1, 'Yahoo Finance': 1, 'Axios': 1, 'Fortune': 1, 'Associated Press': 4}
_MARKET = ('stock market today', 'wall street', 's&p 500', 'dow ', 'dow,', 'nasdaq', 'markets wrap', 'us market',
           'u.s. market', 'u.s. stocks', 'us stocks', 'stock indexes', 'stocks fall', 'stocks rise', 'stocks drop',
           'stocks rally', 'stocks slide', 'stocks jump', 'stocks sink', 'stocks climb', 'stocks tumble', 'stocks soar',
           'stocks end', 'stocks close', 'stocks sell-off', 'stock sell-off', 'stock selloff', 'stock market')
_SKIP = ('?', 'to buy', 'cheap', 'soar in 20', 'should you', 'best stock', 'could ', 'might ', 'cramer', 'asian', 'asia ',
         'australia', 'europe', 'ftse', 'nikkei', 'delisting', 'futures', 'premarket', 'pre-market', 'what you should know',
         'outperforms competitors', 'underperforms', 'how major us stock indexes fared', 'canadian', 'dollar', 'yen ',
         'euro ', 'bitcoin', 'uk stocks', 'london', 'british', "i'm ", 'my ', 'investing move', 'crypto', 'tsx', 'india', 'china stocks', 'hong kong', 'week ahead', 'live updates')
_BAD_SRC = ('Facebook', 'The Motley Fool', 'YouTube', 'Reddit', 'X', 'Instagram', 'TikTok')
HEADLINES = 4


def pick_headlines(items, day, n=HEADLINES):
    """The day's market-wrap headlines from the saved news feeds (data/headlines_log.json): scored by source and by
    market words, previews and other markets skipped, one per source; [{src, t, link}]."""
    scored = []
    for x in items or []:
        if x.get('d') != day or not x.get('t') or x.get('src') in _BAD_SRC:
            continue
        t, low = x['t'].strip(), x['t'].lower()
        if any(k in low for k in _SKIP):
            continue
        s = STRONG_SRC.get(x.get('src'), 0) + (3 if any(k in low for k in _MARKET) else 0)
        if s >= 4:
            scored.append((-s, len(scored), x))
    out, seen = [], set()
    for _, _, x in sorted(scored):
        key = x['t'].lower()[:40]
        if x.get('src') in seen or key in seen:
            continue
        seen.update((x.get('src'), key))
        out.append(dict(src=x.get('src') or '', t=x['t'].strip(), link=x.get('link') or ''))
        if len(out) >= n:
            break
    return out


def _holiday_name(d):
    m, dd = int(d[5:7]), int(d[8:10])
    return {1: "New Year's Day" if dd <= 2 else 'Martin Luther King Jr. Day', 2: "Presidents' Day", 3: 'Good Friday',
            4: 'Good Friday', 5: 'Memorial Day', 6: 'Juneteenth', 7: 'Independence Day', 9: 'Labor Day',
            11: 'Thanksgiving', 12: "Christmas" if dd >= 24 else "New Year's Day"}.get(m, 'holiday')


def early_close(d):
    """The NYSE's scheduled 1pm closes: the day after Thanksgiving, Christmas Eve and July 3 when they are sessions
    (July 3 only when the 4th falls Tuesday to Friday)."""
    x = date.fromisoformat(d)
    if not calendar_nyse.is_trading_day(x):
        return False
    if x.month == 11 and calendar_nyse.previous_trading_day(x).isoformat() != (x - timedelta(days=1)).isoformat() \
            and (x - timedelta(days=1)).isoformat() in calendar_nyse.holidays(x.year) and x.weekday() == 4:
        return True
    if x.month == 12 and x.day == 24:
        return True
    return x.month == 7 and x.day == 3 and date(x.year, 7, 4).weekday() in (1, 2, 3, 4)


def coming_up(day, fomc=(), days=8):
    """Market closures, half days and Fed decision days in the next `days` calendar days after `day`."""
    out, x = [], date.fromisoformat(day)
    for i in range(1, days + 1):
        d = x + timedelta(days=i)
        s = d.isoformat()
        lab = _fmt(s)
        if d.weekday() < 5 and s in calendar_nyse.holidays(d.year):
            out.append(f'{lab}: market closed ({_holiday_name(s)})')
        elif early_close(s):
            out.append(f'{lab}: half day (closes 1pm ET)')
        if s in set(fomc):
            out.append(f'{lab}: Fed rate decision (2pm ET)')
    return out


def _chg(series, i):
    a, b = series[i - 1] if i else None, series[i]
    return None if not (a and b) else b[3] / a[3] - 1


def build_item(day, ohlc, headlines, members=(), fomc=()):
    """One day's script-built story from docs/ohlc.json-style data ({'dates', 't': {T: [[o,h,l,c,v]|None]}, 'n'}):
    SPY / QQQ / RSP moves, SPY's streak and distance from its 1-year high, the S&P 500's biggest movers, the day's
    market headlines and what's coming up. None when the data has no SPY close for the day."""
    dates = ohlc.get('dates') or []
    if day not in dates:
        return None
    i = dates.index(day)
    T, names = ohlc.get('t') or {}, ohlc.get('n') or {}
    spy = T.get('SPY') or []
    if i < 1 or i >= len(spy) or not spy[i] or not spy[i - 1]:
        return None
    sp = spy[i][3] / spy[i - 1][3] - 1
    run, j = 0, i
    while j >= 1 and spy[j] and spy[j - 1] and (spy[j][3] > spy[j - 1][3]) == (sp > 0):
        run += 1
        j -= 1
    prev_run, j2 = 0, j
    while j2 >= 1 and spy[j2] and spy[j2 - 1] and (spy[j2][3] > spy[j2 - 1][3]) != (sp > 0):
        prev_run += 1
        j2 -= 1
    lo = max(0, i - 251)
    hi_k = max((k for k in range(lo, i + 1) if spy[k]), key=lambda k: spy[k][3])
    off = spy[i][3] / spy[hi_k][3] - 1
    a = abs(sp)
    verb = ('little changed' if a < 0.003 else ('edge up' if a < 0.01 else 'rise' if a < 0.02 else 'surge') if sp > 0
            else ('slip' if a < 0.01 else 'fall' if a < 0.02 else 'sink'))
    head = 'Stocks ' + verb + ('' if a < 0.003 else f' {a * 100:.1f}%')
    word = 'gain' if sp > 0 else 'loss'
    if run >= 3 and a >= 0.003:
        head += f'; {run}{_th(run)} {word} in a row'
    elif run == 1 and prev_run >= 3 and a >= 0.003:
        head += f"; first {word} after {prev_run} {'losses' if sp > 0 else 'gains'}"
    facts = []
    if off < -0.001:
        facts.append(f'SPY is {-off * 100:.1f}% under its 1-year high ({_fmt(dates[hi_k], True)}).')
    else:
        facts.append('SPY closed at a 1-year high.')
    moves = []
    for t in (members or T):
        bs = T.get(t)
        if t in ('SPY', 'QQQ', 'RSP') or not bs or i >= len(bs):
            continue
        c = _chg(bs, i)
        if c is not None:
            moves.append((c, t))
    moves.sort()
    up = [dict(t=t, n=names.get(t, ''), pct=round(c, 4)) for c, t in moves[::-1][:3] if c > 0]
    down = [dict(t=t, n=names.get(t, ''), pct=round(c, 4)) for c, t in moves[:3] if c < 0]
    if moves:
        n_up = sum(1 for c, _ in moves if c > 0)
        facts.append(f'{n_up} of {len(moves)} S&P 500 stocks rose.')
    tape = [dict(t='SPY', n='S&P 500', pct=round(sp, 4), close=round(spy[i][3], 2))]
    for t, n in (('QQQ', 'Nasdaq-100'), ('RSP', 'Equal-weight S&P')):
        c = _chg(T.get(t) or [], i) if T.get(t) and i < len(T[t]) else None
        if c is not None:
            tape.append(dict(t=t, n=n, pct=round(c, 4)))
    return dict(date=day, headline=head, tape=tape, facts=facts, up=up, down=down,
                headlines=pick_headlines(headlines, day), coming=coming_up(day, fomc), by='script')


def _th(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def upsert(log, item, keep=60):
    """The log ({'about', 'items'}) with `item` in place of any item for its date, oldest first, the last `keep`."""
    items = [x for x in (log or {}).get('items') or [] if x.get('date') != item['date']] + [item]
    items.sort(key=lambda x: x['date'])
    return dict((log or {}), items=items[-keep:])

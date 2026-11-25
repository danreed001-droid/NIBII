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
from datetime import date

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

"""Major market events since 2000 (data/major_events.json) and the nightly rules that add new ones. Information only:
no trading rule reads this. Each event has its date (the first session the market could react), what happened, where
it came from ('curated', or which automatic rule found it) and SPY's move that day and over the next 21 sessions.

From AUTO_SINCE on, each run adds:
  - a day SPY closes 2.5%+ up or down, with that day's main headline: from the Claude news log (data/news_log.json)
    when it has one, else from the free feeds saved in data/headlines_log.json (MarketWatch, Google News);
  - a Fed rate change, read from the Fed's own FOMC statement (mtl/news_feeds.py), or failing that a high-impact Fed
    decision in the news log;
  - the VIX closing above 30 for the first time in three months;
  - the market label (mtl/phase.py) turning to a correction, a bear market, a new bull run, or back to a bull run.
Your own items, sent from the page's "Add news" form, live in data/my_events.json (written only by that form's
workflow) and are copied in on every run as 'added by you'."""
import json
import os
import re
from bisect import bisect_left
from datetime import date

from mtl.phase import market_phase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data', 'major_events.json')
NEWS = os.path.join(ROOT, 'data', 'news_log.json')
MINE = os.path.join(ROOT, 'data', 'my_events.json')
MINE_SRC = 'added by you'
ADD_URL = 'https://github.com/danreed001-droid/NIBII/issues/new?template=market-event.yml'   # the "Add news" form
AUTO_SINCE = '2026-10-19'
BIG_MOVE, VIX_SPIKE = 0.025, 30.0
FED = re.compile(r'^\s*(the\s+)?(Fed|Federal Reserve|FOMC)\b[^.;]{0,40}?\b(raises|cuts|hikes|lowers)\b', re.I)   # a decision, not odds or talk
PHASE_TEXT = {'correction': 'S&P 500 enters a correction (10%+ below its high)',
              'bear market': 'S&P 500 enters a bear market (20%+ below its high)',
              'new bull run': 'New bull run: S&P 500 up 20% from its bear-market low',
              'bull run': 'S&P 500 back in a bull run (new high after a bear market)'}


# The events search, shared by docs/events.html and the scanner page so both find the same events: every typed word
# must appear in the event's search text, and the move filter keeps events whose Day (or 1 month) move is at least
# `lim` up, down or either way; an event without that figure yet drops out while the filter is on.
MATCH_JS = r"""function evFilter(q, per, dir, min) {
  var m = parseFloat(min.value);
  return {words: q.value.toLowerCase().split(/\s+/).filter(Boolean), per: per.value, way: dir.value,
          lim: isNaN(m) ? 0 : Math.abs(m) / 100};
}
function evOn(f) { return f.words.length > 0 || f.lim > 0 || f.way !== 'any'; }
function evMatch(s, day, month, f) {
  for (var i = 0; i < f.words.length; i++) if (s.indexOf(f.words[i]) < 0) return false;
  if (!(f.lim > 0) && f.way === 'any') return true;
  var v = f.per === 'month' ? month : day;
  if (v === undefined || v === null || v === '') return false;
  v = +v;
  return Math.abs(v) >= f.lim - 1e-9 && (f.way === 'any' || (f.way === 'up' ? v > 0 : v < 0));
}"""


def tag(e):
    """The event's tag as shown on the page ('' for the curated list)."""
    return '' if e['src'] == 'curated' else e['src'].replace('auto: ', 'auto · ')


def search_text(e):
    """What the search box matches: the date (month name, day, year), the event text and its tag, lower case."""
    d = date.fromisoformat(e['d'])
    return ' '.join([d.strftime('%B %b'), str(d.day), str(d.year), e['what'], tag(e)]).lower()


def load(path=PATH):
    with open(path) as fh:
        return json.load(fh)


def save(doc, path=PATH):
    doc['events'].sort(key=lambda e: (e['d'], e['what']))
    with open(path, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')


def add(events, d, what, src):
    """Add an event unless one from the same rule is already on that day. Returns True when added."""
    if any(e['d'] == d and e['src'] == src for e in events):
        return False
    events.append(dict(d=d, what=what, src=src, day=None, month=None))
    return True


def load_mine(path=MINE):
    try:
        with open(path) as fh:
            return json.load(fh)['events']
    except FileNotFoundError:
        return []


def sync_mine(events, mine):
    """Make the 'added by you' events match data/my_events.json, keeping the moves already worked out."""
    want = {(m['d'], m['what']): m for m in mine}
    events[:] = [e for e in events if e['src'] != MINE_SRC or (e['d'], e['what']) in want]
    have = {(e['d'], e['what']): e for e in events if e['src'] == MINE_SRC}
    for key, m in want.items():
        e = have.get(key)
        if e is None:
            e = dict(d=m['d'], what=m['what'], src=MINE_SRC, day=None, month=None)
            events.append(e)
        e.pop('link', None)
        if m.get('link'):
            e['link'] = m['link']


def headline(news, d, sign):
    """The day's main headline in the news log: high impact first, then the one leaning the same way as the move."""
    day = [r for r in news if r.get('date') == d]
    if not day:
        return None
    lean = 'Bearish' if sign < 0 else 'Bullish'
    day.sort(key=lambda r: (r.get('impact') != 'High', r.get('direction') != lean, r.get('order') or 0))
    return day[0]['event'].split(';')[0].strip()


def day_headline(news, headlines, d, sign):
    """(headline, where it came from) for a big-move day: the Claude news log first, then the free feeds."""
    from mtl.news_feeds import pick
    h = headline(news, d, sign)
    if h:
        return h, 'news log'
    x = pick(headlines, d, sign)
    if x:
        return x['t'], x['src'] if x['src'] == x['feed'] else f"{x['src']} via {x['feed']}"
    return None, None


def auto(events, cal, spy, vix, news, since=AUTO_SINCE, headlines=(), fed=()):
    """Apply the automatic rules to every session from `since` (re-running is safe). `headlines` are the saved feed
    items, `fed` the Fed's decisions [{d, action, lo, hi}]. Returns the events added."""
    from mtl.news_feeds import fmt_rate
    new, idx = [], {d: k for k, d in enumerate(cal)}
    for k in range(max(1, bisect_left(cal, since)), len(cal)):
        d = cal[k]
        r = spy[k] / spy[k - 1] - 1
        if abs(r) >= BIG_MOVE:
            h, via = day_headline(news, headlines, d, r)
            txt = (f"S&P 500 {r * 100:+.1f}% in a day" + (f": {h} ({via})" if h else '')).replace('-', '−', 1 if r < 0 else 0)
            old = next((e for e in events if e['d'] == d and e['src'] == 'auto: big move'), None)
            if old and h and ':' not in old['what']:
                old['what'] = txt   # a headline that arrived after the first run
            elif add(events, d, txt, 'auto: big move'):
                new.append(d)
        v = vix.get(d)
        prior = [vix[x] for x in cal[max(0, k - 63):k] if vix.get(x) is not None]
        if v is not None and v >= VIX_SPIKE and prior and max(prior) < VIX_SPIKE:
            if add(events, d, f"Fear spike: the VIX closes at {v:.0f}, its first close above 30 in three months", 'auto: VIX'):
                new.append(d)
        a, b = market_phase(cal[:k], spy[:k]), market_phase(cal[:k + 1], spy[:k + 1])
        recent = any(e['src'] == 'auto: market phase' and e['what'] == PHASE_TEXT.get(b['phase']) and
                     idx.get(e['d'], -999) >= k - 63 for e in events)   # no repeat while it hovers at a line
        if a['phase'] != b['phase'] and b['phase'] in PHASE_TEXT and not recent \
                and not (a['phase'] == 'correction' and b['phase'] == 'bull run'):
            if add(events, d, PHASE_TEXT[b['phase']], 'auto: market phase'):
                new.append(d)
    for f in fed:
        k = bisect_left(cal, f['d'])
        if f['d'] >= since and f['action'] in ('raise', 'lower') and k < len(cal) \
                and not any(x['d'] == cal[k] and 'Fed' in x['what'] for x in events):
            verb = 'raises' if f['action'] == 'raise' else 'cuts'
            if add(events, cal[k], f"Fed {verb} rates to {fmt_rate(f['lo'])}–{fmt_rate(f['hi'])}% (FOMC statement)", 'auto: Fed'):
                new.append(cal[k])
    for r_ in news:
        d = r_.get('date') or ''
        if d >= since and r_.get('impact') == 'High' and (r_.get('category') or '') in ('Fed', 'Central bank') \
                and FED.search(r_['event']):
            k = bisect_left(cal, d)
            if k < len(cal) and not any(x['d'] == cal[k] and 'Fed' in x['what'] for x in events) \
                    and add(events, cal[k], r_['event'].split(';')[0].strip(), 'auto: Fed'):
                new.append(cal[k])
    return new


def reactions(events, cal, spy):
    """SPY's move on each event's first session and over the next 21 sessions (left empty until they exist)."""
    for e in events:
        k = bisect_left(cal, e['d'])
        if k == 0 or k >= len(cal):
            continue
        e['day'] = round(spy[k] / spy[k - 1] - 1, 4)
        e['month'] = round(spy[k + 21] / spy[k - 1] - 1, 4) if k + 21 < len(cal) else None

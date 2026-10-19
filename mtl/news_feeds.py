"""Free news sources for the market events page (mtl/events.py), no account needed:
  - the Federal Reserve's monetary-policy press releases (its own feed): every FOMC statement, and from the statement's
    text whether it raised, lowered or held rates and the new target range;
  - MarketWatch top stories and a Google News search for "stock market": the day's market headlines, saved nightly to
    data/headlines_log.json (last 90 days) so a big-move day can be matched to its headline.
Each fetch is independent: one source failing leaves the others working, and a source that hasn't worked for three days
is reported in the scanner page's issues list."""
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, 'data', 'headlines_log.json')
NY = ZoneInfo('America/New_York')
UA = 'NIBII market dashboard (personal; github.com/danreed001-droid/NIBII)'
FEEDS = {'MarketWatch': 'https://feeds.content.dowjones.io/public/rss/mw_topstories',
         'Google News': 'https://news.google.com/rss/search?q=stock+market+when:1d&hl=en-US&gl=US&ceid=US:en'}
FED_FEED = 'https://www.federalreserve.gov/feeds/press_monetary.xml'
KEEP_DAYS, STALE_DAYS = 90, 3
MARKET = re.compile(r"\b(stocks?|S&P|Dow|Nasdaq|Wall Street|markets?|equities|index|indexes|selloff|sell-off)\b", re.I)
CAUSE = re.compile(r"\b(Fed|Powell|Warsh|rates?|yields?|inflation|CPI|jobs|payrolls|tariffs?|trade|war|Iran|China|oil|"
                   r"recession|earnings|Nvidia|AI|banks?|default|shutdown|crash)\b", re.I)
DOWN = re.compile(r"\b(fall|falls|fell|drop|drops|slide|slides|slump|tumble|tumbles|plunge|plunges|sink|sinks|sell-?off|"
                  r"losses|lower|rout|worst)\b", re.I)
UP = re.compile(r"\b(rally|rallies|surge|surges|jump|jumps|soar|soars|gain|gains|rise|rises|climb|climbs|higher|record|best)\b", re.I)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def ny_date(pub):
    """An RSS pubDate as the New York calendar date."""
    return parsedate_to_datetime(pub).astimezone(NY).date().isoformat()


def parse_rss(text, feed):
    """[{d, t, src, link, feed}] from an RSS document; Google News titles end in ' - Publisher'."""
    out = []
    for it in ET.fromstring(text.lstrip('﻿')).iter('item'):
        t, pub = (it.findtext('title') or '').strip(), it.findtext('pubDate')
        if not t or not pub:
            continue
        src = (it.findtext('source') or '').strip() or feed
        if feed == 'Google News' and ' - ' in t:
            t, src = t.rsplit(' - ', 1)
        out.append(dict(d=ny_date(pub), t=html.unescape(t.strip()), src=src.strip(), link=(it.findtext('link') or '').strip(), feed=feed))
    return out


def load_log(path=LOG):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return dict(about='Market headlines saved nightly from free news feeds (mtl/news_feeds.py), last 90 days.', feeds={}, items=[])


def save_log(doc, today, path=LOG):
    cut = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS)).isoformat()
    seen, keep = set(), []
    for x in sorted(doc['items'], key=lambda x: (x['d'], x['feed'], x['t'])):
        if x['d'] >= cut and (x['d'], x['t']) not in seen:
            seen.add((x['d'], x['t'])); keep.append(x)
    doc['items'] = keep
    with open(path, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')


def collect(doc, today, get=fetch):
    """Fetch every headline feed into the log; returns [(feed, error)] for the ones that failed."""
    bad = []
    for name, url in FEEDS.items():
        try:
            items = parse_rss(get(url), name)
            doc['items'] += items
            doc['feeds'][name] = today
        except Exception as e:   # noqa: BLE001 - one feed failing must not stop the others
            bad.append((name, f'{type(e).__name__}: {e}'[:200]))
    return bad


def stale(doc, today, names=FEEDS):
    """Feeds that haven't worked for STALE_DAYS days (or ever)."""
    t = date.fromisoformat(today)
    return [n for n in names if not doc['feeds'].get(n) or (t - date.fromisoformat(doc['feeds'][n])).days >= STALE_DAYS]


def pick(items, d, sign):
    """The day's most market-relevant headline: about the market, naming a cause, leaning the way the market moved."""
    best, score = None, 0
    for x in items:
        if x['d'] != d:
            continue
        t = x['t']
        s = 2 * bool(MARKET.search(t)) + bool(CAUSE.search(t)) + bool((DOWN if sign < 0 else UP).search(t))
        s -= bool((UP if sign < 0 else DOWN).search(t))
        if s > score or (s == score and best is not None and x['feed'] == 'MarketWatch' and best['feed'] != 'MarketWatch'):
            best, score = x, s
    return best if score >= 3 else None


# ---- Federal Reserve decisions -------------------------------------------------------------------------------------
DECISION = re.compile(r"decided to (raise|lower|maintain)[^.]*?target range for the federal funds rate"
                      r"(?: by ([0-9/ \-]+?) percentage points?)? (?:to|at) ([0-9][0-9/\-]*) to ([0-9][0-9/\-]*) percent", re.I)


def num(s):
    """'3-3/4' -> 3.75, '4' -> 4.0, '1/2' -> 0.5."""
    s = s.strip()
    whole, _, frac = s.partition('-') if '/' in s and '-' in s else (s, '', '')
    if '/' in whole and not frac:
        a, b = whole.split('/'); return int(a) / int(b)
    v = float(whole)
    if frac:
        a, b = frac.split('/'); v += int(a) / int(b)
    return v


def decision(statement_html):
    """(action, low, high) from an FOMC statement page, or None."""
    t = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', statement_html))).replace('‑', '-')
    m = DECISION.search(t)
    if not m:
        return None
    return m.group(1).lower(), num(m.group(3)), num(m.group(4))


def fed_statements(feed_text):
    """[(date, link)] for each 'FOMC statement' item in the Fed's monetary-policy feed."""
    out = []
    for it in ET.fromstring(feed_text.lstrip('﻿')).iter('item'):
        t = it.findtext('title') or ''
        if 'FOMC statement' in t and it.findtext('pubDate'):
            out.append((ny_date(it.findtext('pubDate')), (it.findtext('link') or '').strip()))
    return out


def fmt_rate(x):
    return f"{x:.2f}".rstrip('0').rstrip('.')

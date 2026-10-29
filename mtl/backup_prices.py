"""Backup prices for the nightly scan, for the nights Yahoo Finance fails.

Yahoo (through the unofficial yfinance library) stays the main source. Two backups fill what it leaves out:

1. A saved copy of every series the last runs read (PRICE_CACHE: a gzipped JSON file kept between runs in GitHub's
   Actions cache, not in the repo). A ticker Yahoo returns nothing for is read from it.
2. Tiingo's end-of-day quotes for every US stock and fund, in one request (TIINGO_KEY, a repository secret). A series
   that stops before the last close gets that close appended. The quote's previous close is checked against the
   series' last close first: a split (or, for the dividend-adjusted series, a dividend) in between rescales the
   history, as Yahoo would. The 10-year yield (^TNX) and the VIX aren't on Tiingo; they come from FRED (DGS10,
   VIXCLS) when FRED already has the day and agrees with the series on its last day.

Every night the copy is updated with what the run read, backup rows included, so a Yahoo outage of several nights
still leaves an unbroken series; Yahoo's own rows replace them as soon as it works again.

Both backups are opt-in: without PRICE_CACHE and TIINGO_KEY set (tests, research scripts) fill() changes nothing.
used() says what came from where, for the page's data warnings.
"""
import gzip
import json
import math
import os
import sys
from datetime import datetime, timezone

from mtl.calendar_nyse import is_trading_day, previous_trading_day

TIINGO_URL = 'https://api.tiingo.com/iex/?token={key}'   # every ticker's latest quote in one response
FRED_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'
FRED_ALT = {'^TNX': 'DGS10', '^VIX': 'VIXCLS'}            # Yahoo index -> the same series on FRED
SPLIT = math.log(1.2)       # a jump in the previous close beyond 20% is a split, not a data correction
QUIET = 10                  # fewer series filled than this aren't worth a line on the page
BROKEN = 0.5                # Yahoo is "down" when it missed the last close for half or more of a large request

_cache = None               # {'raw'|'adj': {ticker: 'date,open,high,low,close,volume' lines}}
_quotes = None
_fred = {}
_used = {'cache': set(), 'tiingo': set(), 'fred': set(), 'gap': set()}
_asked = [0, 0]             # tickers asked for in large requests, of which Yahoo missed the last close


def reset():
    """Forget tonight's state (tests)."""
    global _cache, _quotes
    _cache, _quotes = None, None
    _fred.clear()
    for v in _used.values():
        v.clear()
    _asked[:] = [0, 0]


def last_closed(now=None):
    """The latest NYSE session that has closed by `now` (16:15 New York time, as for the paper record)."""
    from zoneinfo import ZoneInfo
    from mtl.paper import CLOSE_ET
    ny = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('America/New_York'))
    if is_trading_day(ny.date()) and ny.time() >= CLOSE_ET:
        return ny.date().isoformat()
    return previous_trading_day(ny.date()).isoformat()


def _num(x):
    return '' if x is None else f'{x:.10g}'


def to_text(rows, vol):
    return '\n'.join(f"{r[0]},{_num(r[1])},{_num(r[2])},{_num(r[3])},{_num(r[4])},{_num(vol.get(r[0]))}"
                     for r in rows)


def from_text(text):
    """(rows [(date, open, high, low, close)], {date: volume})"""
    rows, vol = [], {}
    for ln in (text or '').splitlines():
        d, o, h, l, c, v = ln.split(',')
        rows.append((d, float(o), float(h), float(l), float(c)))
        if v:
            vol[d] = int(float(v))
    return rows, vol


def _load():
    global _cache
    if _cache is None:
        _cache = {'raw': {}, 'adj': {}}
        path = os.environ.get('PRICE_CACHE')
        if path and os.path.exists(path):
            try:
                with gzip.open(path, 'rt') as f:
                    _cache = json.load(f)
            except Exception as e:   # noqa: BLE001 - a damaged copy is rebuilt from tonight's prices
                print(f"  price cache unreadable ({e}): starting a new one", file=sys.stderr)
    return _cache


def merge(old_text, rows, vol):
    """The saved series after tonight: tonight's rows, plus any older saved rows before them, rescaled to join
    (Yahoo's adjusted history moves with each dividend)."""
    new = to_text(rows, vol)
    if not old_text or not rows or old_text[:10] >= rows[0][0]:
        return new
    old, ovol = from_text(old_text)
    first = rows[0][0]
    at = {r[0]: r[4] for r in old}
    k = rows[0][4] / at[first] if at.get(first) else 1.0
    keep = [(r[0], r[1] * k, r[2] * k, r[3] * k, r[4] * k) for r in old if r[0] < first]
    return to_text(keep, ovol) + ('\n' + new if new else '')


def quotes():
    """{ticker: (date, open, high, low, close, volume, previous close)} for quotes stamped after a closed session."""
    global _quotes
    if _quotes is None:
        _quotes = {}
        key = os.environ.get('TIINGO_KEY')
        if key:
            import urllib.request
            from zoneinfo import ZoneInfo
            ny = ZoneInfo('America/New_York')
            try:
                req = urllib.request.Request(TIINGO_URL.format(key=key), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
                for q in data:
                    c, ts = q.get('tngoLast'), q.get('timestamp')
                    if not c or not ts or not q.get('ticker'):
                        continue
                    t_ = datetime.fromisoformat(ts).astimezone(ny)
                    if t_.hour < 16:   # still trading (or a pre-market stamp): not a close
                        continue
                    _quotes[q['ticker'].upper()] = (t_.date().isoformat(), q.get('open') or c, q.get('high') or c,
                                                    q.get('low') or c, c, q.get('volume'), q.get('prevClose'))
                print(f"  backup quotes: {len(_quotes)} tickers from Tiingo", file=sys.stderr)
            except Exception as e:   # noqa: BLE001
                print(f"  backup quotes failed: {e}", file=sys.stderr)
    return _quotes


def fred(sid):
    """{date: value} for a FRED series, {} when it can't be read."""
    if sid not in _fred:
        import csv
        import io
        import urllib.request
        out = {}
        try:
            with urllib.request.urlopen(FRED_URL.format(sid=sid), timeout=30) as r:
                text = r.read().decode('utf-8')
            for row in csv.DictReader(io.StringIO(text)):
                d, v = row.get('observation_date') or row.get('DATE'), row.get(sid)
                if v not in (None, '', '.'):
                    out[d] = float(v)
        except Exception as e:   # noqa: BLE001
            print(f"  FRED {sid} failed: {e}", file=sys.stderr)
        _fred[sid] = out
    return _fred[sid]


def append(t, rows, vol, adjusted, target, quote=None, fred_ser=None):
    """Rows (and volumes) carried up to `target` from a backup, or None when no backup has a newer close.
    `quote`: Tiingo's (date, open, high, low, close, volume, previous close); `fred_ser`: {date: value}."""
    last = rows[-1]
    if fred_ser is not None:
        v0 = fred_ser.get(last[0])
        if not v0 or abs(v0 / last[4] - 1) > 0.02:   # can't confirm FRED's series matches this one
            return None
        add = [(d, v, v, v, v) for d, v in sorted(fred_ser.items()) if last[0] < d <= target and is_trading_day(d)]
        return (rows + add, vol) if add else None
    if not quote or quote[0] != target or quote[0] <= last[0]:
        return None
    d, o, h, l, c, v, prev = quote
    if prev and last[0] == previous_trading_day(d).isoformat():
        r = last[4] / prev
        if abs(math.log(r)) > SPLIT or (adjusted and abs(r - 1) > 0.0005):
            rows = [(x[0], x[1] / r, x[2] / r, x[3] / r, x[4] / r) for x in rows]
            if abs(math.log(r)) > SPLIT:
                vol = {k: int(x * r) for k, x in vol.items()}
    vol = dict(vol)
    if v:
        vol[d] = int(v)
    return rows + [(d, float(o), float(h), float(l), float(c))], vol


def fill(out, tickers, adjusted=False, start='0000', volumes=None, target=None):
    """Fill what Yahoo left out of fetch()'s `out` (and `volumes`) in place, then save tonight's series to the copy."""
    if not (os.environ.get('PRICE_CACHE') or os.environ.get('TIINGO_KEY')):
        return
    target = target or last_closed()
    mode = 'adj' if adjusted else 'raw'
    saved = _load()[mode]
    behind = [t for t in tickers if not out.get(t) or out[t][-1][0] < target]
    if len(tickers) >= 20:
        _asked[0] += len(tickers)
        _asked[1] += len(behind)
    for t in behind:
        rows = out.get(t) or []
        vol = dict((volumes or {}).get(t) or {})
        if not rows and saved.get(t):
            rows, cvol = from_text(saved[t])
            rows = [r for r in rows if start <= r[0] <= target]
            vol = {**{d: x for d, x in cvol.items() if d >= start}, **vol}
            if rows:
                _used['cache'].add(t)
        if not rows:
            continue
        if t in FRED_ALT:
            got = append(t, rows, vol, adjusted, target, fred_ser=fred(FRED_ALT[t]))
        else:
            got = append(t, rows, vol, adjusted, target, quote=quotes().get(t.upper()))
        if got:
            if t not in FRED_ALT and rows[-1][0] != previous_trading_day(target).isoformat():
                _used['gap'].add(t)   # the backup has only the latest close: the sessions in between stay missing
            rows, vol = got
            _used['fred' if t in FRED_ALT else 'tiingo'].add(t)
        if rows[-1][0] >= target:   # complete (the copy already had the day, or a backup added it)
            _used['cache'].discard(t)
        if got:
            print(f"  {t}: {rows[-1][0]} close from the backup", file=sys.stderr)
        out[t] = rows
        if volumes is not None and vol:
            volumes[t] = vol
    for t in tickers:
        rows = [r for r in out.get(t) or [] if r[0] <= target]   # never save a session still trading
        if rows:
            saved[t] = merge(saved.get(t), rows, (volumes or {}).get(t) or {})


def save():
    """Write the copy (PRICE_CACHE) for the next run."""
    path = os.environ.get('PRICE_CACHE')
    if not path or _cache is None:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + '.tmp'
    with gzip.open(tmp, 'wt', compresslevel=6) as f:
        json.dump(_cache, f, separators=(',', ':'))
    os.replace(tmp, path)
    print(f"  price cache saved: {sum(len(v) for v in _cache.values())} series", file=sys.stderr)


def used():
    """{'cache'|'tiingo'|'fred'|'gap': sorted tickers} filled from each backup tonight, and whether Yahoo looked down."""
    return {**{k: sorted(v) for k, v in _used.items()}, 'yahoo_down': bool(_asked[0]) and _asked[1] >= BROKEN * _asked[0]}


def problems(u, target):
    """Plain-language lines for the page's data warnings."""
    out = []
    names = sorted(set(u.get('tiingo') or []) | set(u.get('fred') or []))
    if u.get('yahoo_down'):
        out.append("Yahoo Finance, the main price source, was missing tonight's close for most tickers: the plan ran "
                   "on the backup source instead (Tiingo's official closing prices). Nothing to do unless this "
                   "repeats for days; if it does, the download library likely needs an update.")
    if len(names) >= QUIET and not u.get('yahoo_down'):   # a few filled closes are routine: the run log has them
        out.append(f"{len(names)} price series came from the backup source tonight because Yahoo was missing "
                   f"{target}'s close (e.g. {', '.join(names[:5])}).")
    if u.get('gap'):
        g = u['gap']
        out.append(f"{len(g)} of them skip a session or more (e.g. {', '.join(g[:5])}): the backup has only the latest "
                   f"close, so moves measured across the missing days are slightly off until Yahoo is back.")
    if u.get('cache'):
        c = u['cache']
        out.append(f"{len(c)} series Yahoo returned nothing for were read from the saved copy of earlier runs, and no "
                   f"backup had {target}'s close (e.g. {', '.join(c[:5])}): they stop a day or more early.")
    return out

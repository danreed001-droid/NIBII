"""Nightly: the news forward test (mtl/news_forward.py, data/news_forward.json). Information only.

Writes tonight's calls from today's news-log entries and closes, but only between today's close and the next
session's open (a run after the open would see where the next day is heading; a missed night stays missed), then
scores every call whose horizon has passed.

    python scripts/news_forward.py"""
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtl import calendar_nyse as cn, health, news_forward as NF  # noqa: E402
from scripts.momentum_scan import last_closed_session  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'news_forward.json')
NEWS = os.path.join(ROOT, 'data', 'news_log.json')
NY = ZoneInfo('America/New_York')
OPEN = time(9, 30)


def load(path=OUT):
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return NF.new_doc()
    return doc


def before_next_open(day, now):
    """True while `now` is before the open of the session after `day`."""
    nxt = cn.next_trading_day(day)
    return now < datetime.combine(nxt, OPEN, tzinfo=NY)


def fetch_closes(start, day):
    """{ticker: {date: close}} from `start`; when the daily series lacks `day` (Yahoo can be a day late with it), that
    close comes from the day's last 30-minute bar."""
    import yfinance as yf
    out = {}
    for t in NF.ASSETS:
        df = yf.download(t, start=start, auto_adjust=True, progress=False)
        c = df['Close']
        c = c[t] if hasattr(c, 'columns') else c
        ser = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
        if day not in ser:
            h = yf.Ticker(t).history(period='5d', interval='30m', auto_adjust=True)
            bars = h[[d.date().isoformat() == day for d in h.index]]
            if len(bars):
                ser[day] = float(bars['Close'].iloc[-1])
        out[t] = ser
    return out


def day_inputs(closes, day):
    """({ticker: day's return}, S&P's typical absolute daily move over the 20 sessions before), or None when a
    close is missing."""
    moves = {}
    for t, ser in closes.items():
        cal = [d for d in sorted(ser) if d <= day]
        if not cal or cal[-1] != day or len(cal) < 22:
            return None
        moves[t] = ser[day] / ser[cal[-2]] - 1
    s = closes['SPY']
    cal = [d for d in sorted(s) if d < day][-21:]
    typical = median(abs(s[b] / s[a] - 1) for a, b in zip(cal, cal[1:]))
    return moves, typical


def main(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(NY)
    day = last_closed_session(now)
    doc = load()
    start = min([c['d'] for c in doc['calls'] if 'hit' not in c] + [day])
    start = (date.fromisoformat(start) - timedelta(days=45)).isoformat()
    try:
        closes = fetch_closes(start, day)
    except Exception as e:   # noqa: BLE001 - the page keeps the last scoreboard
        log = health.load()
        health.add(log, now.date().isoformat(), 'newsfwd', f"The news forward test couldn't get prices ({type(e).__name__}), "
                   "so tonight's calls weren't written (information only; the plan is unaffected).")
        health.save(log)
        raise SystemExit(f"news forward: {type(e).__name__}: {e}")
    wrote = None
    if not before_next_open(day, now):
        print(f"{now:%Y-%m-%d %H:%M} New York is after the next open; {day}'s calls are not written now")
    elif any(d['d'] == day for d in doc['days']):
        print(f"{day}'s calls are already logged")
    else:
        got = day_inputs(closes, day)
        if got is None:
            log = health.load()
            health.add(log, day, 'newsfwd', f"No {day} close for every market in the news forward test, so that day's "
                       "calls weren't written (information only; the plan is unaffected).")
            health.save(log)
        else:
            with open(NEWS) as fh:
                news = [x['data'] for x in json.load(fh)]
            cal = [cn.previous_trading_day(day).isoformat(), day, cn.next_trading_day(day).isoformat()]
            wrote = NF.write(doc, day, NF.entries_for(news, cal, day), *got)
    scored = NF.score(doc, closes)
    doc['summary'] = NF.summary(doc)
    doc = dict(about='News forward test: fixed guesses about what follows each day\'s news, written before the next open '
                     'and scored afterwards (mtl/news_forward.py). Information only.',
               updated=datetime.now(timezone.utc).isoformat(timespec='seconds'),
               **{k: v for k, v in doc.items() if k not in ('about', 'updated')})
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    print(f"news forward: {day} wrote {len(wrote) if wrote is not None else 'no'} calls, scored {scored}; "
          f"{len(doc['calls'])} calls in all")


if __name__ == '__main__':
    main()

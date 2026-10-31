"""Nightly: the rates model forward test (mtl/rates_forward.py, data/rates_forward.json). Information only.

On a month's last session, between its close and the next open, logs the model's pick and the plan-style rule's for the
next month (a missed night stays missed); every night, scores the months whose next month-end has passed.

    python scripts/rates_forward.py"""
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtl import calendar_nyse as cn, health, rates_forward as RF  # noqa: E402
from scripts.momentum_scan import last_closed_session  # noqa: E402
from scripts.news_forward import NY, before_next_open  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'rates_forward.json')
TICKERS = {'SPY': 'SPY', 'GLD': 'GLD', 'TLT': 'TLT', 'TNX': '^TNX', 'IRX': '^IRX'}


def fetch(day):
    """{name: {date: close}} from 1999; a close Yahoo's daily series lacks for `day` comes from its last 30-minute bar."""
    import yfinance as yf
    out = {}
    for name, t in TICKERS.items():
        df = yf.download(t, start='1999-01-01', auto_adjust=True, progress=False)
        c = df['Close']
        c = c.iloc[:, 0] if hasattr(c, 'columns') else c
        ser = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
        if day not in ser:
            h = yf.Ticker(t).history(period='5d', interval='30m', auto_adjust=True)
            bars = h[[x.date().isoformat() == day for x in h.index]]
            if len(bars):
                ser[day] = float(bars['Close'].iloc[-1])
        out[name] = ser
    return out


def main(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(NY)
    day = last_closed_session(now)
    try:
        with open(OUT) as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        doc = RF.new_doc()
    try:
        series = fetch(day)
    except Exception as e:   # noqa: BLE001 - the page keeps the last record
        log = health.load()
        health.add(log, now.date().isoformat(), 'ratesfwd', f"The rates model forward test couldn't get prices ({type(e).__name__}), "
                   "so tonight's update was skipped (information only; the plan is unaffected).")
        health.save(log)
        raise SystemExit(f"rates forward: {type(e).__name__}: {e}")
    px = RF.Px(series)
    cal = sorted(d for d in series['SPY'] if d <= day)
    month_end = cn.next_trading_day(day).isoformat()[:7] != day[:7]
    row = None
    if month_end and before_next_open(day, now) and cal and cal[-1] == day:
        row = RF.write(doc, day, px, cal, now.astimezone(timezone.utc).isoformat(timespec='seconds'))
    scored = RF.score(doc, px, cal)
    doc['summary'] = RF.summary(doc)
    doc = dict(about='Rates model forward test: each month-end a model of the 10-year yield picks SPY, gold, bonds or cash '
                     'for the next month, scored against a plan-style rule and SPY (mtl/rates_forward.py). Information only.',
               updated=datetime.now(timezone.utc).isoformat(timespec='seconds'),
               **{k: v for k, v in doc.items() if k not in ('about', 'updated')})
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, indent=1)
        fh.write('\n')
    print(f"rates forward: {day} {'month-end pick ' + row['pick'] + ' (rule ' + str(row['rule']) + ')' if row else 'no pick tonight'}; "
          f"scored {scored}; {len(doc['months'])} months logged")


if __name__ == '__main__':
    main()

"""Nightly: score the analyst-revisions forward test (mtl/revisions_forward.py) from data/revisions_log.json and
write data/revisions_forward.json for docs/forward.html. Information only; a failure keeps the last file.

    python scripts/revisions_forward.py"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtl import health, revisions_forward as RF  # noqa: E402

LOG = os.path.join(ROOT, 'data', 'revisions_log.json')
OUT = os.path.join(ROOT, 'data', 'revisions_forward.json')


def fetch_closes(tickers, start):
    """{ticker: {date: close}} (adjusted) for the tickers, from `start`; a ticker that fails comes back empty."""
    import yfinance as yf
    out = {}
    for t in tickers:
        try:
            df = yf.download(t.replace('.', '-'), start=start, auto_adjust=True, progress=False)
            c = df['Close']
            c = c.iloc[:, 0] if hasattr(c, 'columns') else c
            out[t] = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
        except Exception:   # noqa: BLE001 - that stock is left out of its group's average
            out[t] = {}
    return out


def main():
    with open(LOG) as fh:
        log = json.load(fh)
    log = {d: v for d, v in log.items() if d >= '2026-10-01'}
    if not log:
        print('no revisions logged yet')
        return
    tickers = sorted({t for v in log.values() for t in v} | {'SPY'})
    start = (date.fromisoformat(min(log)) - timedelta(days=7)).isoformat()
    closes = fetch_closes(tickers, start)
    if not closes.get('SPY'):
        log_ = health.load()
        health.add(log_, datetime.now(timezone.utc).date().isoformat(), 'revfwd', "The analyst-revisions forward test "
                   "couldn't get prices tonight, so its scoreboard shows the last figures (information only).")
        health.save(log_)
        raise SystemExit('revisions forward: no SPY prices')
    doc = RF.build(log, closes, asof=max(closes['SPY']))
    doc = dict(about='Analyst-revisions forward test: do the ranked stocks with the biggest rises in estimates beat the '
                     'rest over the next 4 weeks? (mtl/revisions_forward.py). Information only.',
               updated=datetime.now(timezone.utc).isoformat(timespec='seconds'), **doc)
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, indent=1)
        fh.write('\n')
    print(f"revisions forward: {len(doc['weeks'])} Fridays; scored " +
          ', '.join(f"{r['id']} {r['n']}" for r in doc['summary']['rows']))


if __name__ == '__main__':
    main()

"""Weekly: what followed speculator crowding since 2000, market by market (data/crowding_history.json,
mtl/crowding_history.py), for the crowding gauge on the scanner and stress pages. Information only.

Reads the CFTC's full legacy history (one file for 1986-2016, then a file a year) and each market's price history,
and rebuilds the four reads. Runs when the saved file is a week old (or with --force); a failed download keeps the last
file and goes in the issues log.

    python scripts/crowding_history.py [--force]"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtl import crowding as C, crowding_history as CH, health  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'crowding_history.json')
FULL = 'https://www.cftc.gov/files/dea/history/deacot1986_2016.zip'
DAYS = 7


def stale(path=OUT, days=DAYS, now=None):
    try:
        with open(path) as fh:
            t = datetime.fromisoformat(json.load(fh)['updated'])
    except (OSError, ValueError, KeyError):
        return True
    return ((now or datetime.now(timezone.utc)) - t).days >= days


def fetch_positions(timeout=120):
    """The merged CFTC history since 1986 (network)."""
    req = urllib.request.Request(FULL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        parts = [C.parse(resp.read())]
    merged = C.merge(parts + [C.fetch_years(range(2017, datetime.now(timezone.utc).year + 1), timeout=timeout)])
    return merged


def fetch_prices():
    """{market name: {date: close}} for the price under each gauge (mtl/crowding.PRICE)."""
    import yfinance as yf
    out = {}
    for name, t in C.PRICE.items():
        try:
            df = yf.download(t, start='1999-01-01', auto_adjust=True, progress=False)
            c = df['Close']
            c = c[t] if hasattr(c, 'columns') else c
            out[name] = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
        except Exception:   # noqa: BLE001 - that market is left out, the others still build
            out[name] = {}
    return out


def main(argv):
    if '--force' not in argv and not stale():
        print(f"{OUT} is under {DAYS} days old; nothing to do")
        return
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        pos = fetch_positions()
        px = fetch_prices()
    except Exception as e:   # noqa: BLE001 - the page keeps last week's figures
        log = health.load()
        health.add(log, today, 'crowding', f"The weekly crowding-history refresh failed ({type(e).__name__}), so the crowding "
                   "gauge shows last week's what-followed figures (it never affects the plan).")
        health.save(log)
        raise SystemExit(f"crowding history: {type(e).__name__}: {e}")
    missing = [n for n in C.MARKETS.values() if len(px.get(n) or {}) < 2000 or len(pos.get(n) or {}) <= C.WINDOW]
    asof = max((max(s) for s in pos.values() if s), default=None)
    doc = CH.build(pos, px, asof=asof)
    doc = dict(about='What followed speculator crowding since 2000 (mtl/crowding_history.py, scripts/crowding_history.py). '
                     'Information only.', updated=datetime.now(timezone.utc).isoformat(timespec='seconds'), missing=missing, **doc)
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    if missing:
        log = health.load()
        health.add(log, today, 'crowding', f"No full history for {', '.join(missing)} in this week's crowding-history refresh, so "
                   'those rows are left out (it never affects the plan).')
        health.save(log)
    print(f"wrote {OUT}: {len(doc['markets'])} markets, CFTC reports to {asof}")


if __name__ == '__main__':
    main(sys.argv[1:])

"""Write tonight's "Today's story" into data/story_log.json, from scripts only (no AI writing): SPY / QQQ / RSP and
the S&P 500's biggest movers from docs/ohlc.json (written by scripts/momentum_scan.py), the day's market headlines
from the saved news feeds (data/headlines_log.json, scripts/major_events.py) and the exchange and Fed calendars
(mtl/story.py). Runs in the scanner workflow after the events step and before the page is drawn. Information only.

    python scripts/story_build.py              # the last session in docs/ohlc.json
    python scripts/story_build.py 2026-11-24   # a given session (rebuilds it)"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtl import fedday, story  # noqa: E402

OHLC = os.path.join(ROOT, 'docs', 'ohlc.json')
HEADLINES = os.path.join(ROOT, 'data', 'headlines_log.json')
LOG = os.path.join(ROOT, 'data', 'story_log.json')
SP500 = os.path.join(ROOT, 'data', 'sp500.csv')
ABOUT = ("Today's story on the scanner page (docs/scanner.html), built each weekday evening by scripts/story_build.py "
         "from the scanner's prices (docs/ohlc.json), the saved news headlines (data/headlines_log.json) and the exchange "
         "and Fed calendars - no AI writing. Oldest first, the last 60 sessions. Information only: never part of the plan.")


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def members():
    try:
        with open(SP500) as f:
            return [r['symbol'] for r in csv.DictReader(f)]
    except OSError:
        return []


def main(argv):
    ohlc = _load(OHLC, {})
    dates = ohlc.get('dates') or []
    if not dates:
        sys.exit('docs/ohlc.json has no dates')
    days = argv[1:] or [dates[-1]]
    heads = (_load(HEADLINES, {}) or {}).get('items') or []
    log = _load(LOG, {}) or {}
    fomc, mem = fedday.load(), members()
    for d in days:
        item = story.build_item(d, ohlc, heads, mem, fomc)
        if item is None:
            print(f'no SPY close for {d} in docs/ohlc.json: nothing written', file=sys.stderr)
            continue
        log = story.upsert(log, item)
        print(f"{d}: {item['headline']} · {len(item['headlines'])} headlines")
    log['about'] = ABOUT
    with open(LOG, 'w') as f:
        json.dump(log, f, indent=1, ensure_ascii=False)
        f.write('\n')


if __name__ == '__main__':
    main(sys.argv)

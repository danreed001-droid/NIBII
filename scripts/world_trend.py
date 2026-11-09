"""Refresh data/world_trend.json: weekly closes and the trend of the S&P 500, the DAX, the FTSE 100 and seven other
markets since 2005 (mtl/world.py), for the scanner page's world markets section. Information only; run nightly by
the scanner workflow, where a failure never blocks the page (it keeps the last file)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import world  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'world_trend.json')


def main():
    series = world.fetch_all()
    doc = world.build(series)
    got = {m['t'] for m in doc['markets']}
    if not set(world.SHOWN) <= got:
        sys.exit(f'world trend: missing {sorted(set(world.SHOWN) - got)}; keeping the last file')
    doc['asOf'] = max(m['trend']['asOf'] for m in doc['markets'] if m['trend'])
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
        fh.write('\n')
    for m in doc['markets']:
        tr = m['trend'] or {}
        print(f"{m['name']:10s} {tr.get('asOf')} 12m {tr.get('m12') or 0:+.1%} vs 200d {tr.get('vsMa') or 0:+.1%} {tr.get('trend')}")


if __name__ == '__main__':
    main()

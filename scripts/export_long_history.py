#!/usr/bin/env python3
"""Exports the since-2000 replay from scripts/backtest_long_history.py as daily
curves to data/long_history.json (auto mix, auto + news boost, plain top 5,
top 5 + boost, SPY, QQQ), so the results can be charted and analysed elsewhere.

Same caveat as backtest_long_history.py: the stock list is today's S&P 500
(with join dates) + Nasdaq-100, so stocks that left the indexes or failed are
missing, and that flatters the record more the further back it goes.

Usage:
    python scripts/export_long_history.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_long_history import START, build  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'long_history.json')


def main():
    plain, _, _ = build()
    boost, _, _ = build(boost=True)
    curves = {'auto': plain['Current setup (auto mix)'], 'boost': boost['Current setup (auto mix)'],
              'top5': plain['Top 5 in stock'], 'top5boost': boost['Top 5 in stock'],
              'spy': plain['SPY'], 'qqq': plain['QQQ (Nasdaq-100)']}
    out = dict(generatedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'), start=START,
               curves={k: [[d, round(float(v), 6)] for d, v in c] for k, c in curves.items()})
    with open(OUT, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f"wrote {OUT}: " + ', '.join(f"{k} {len(c)} days" for k, c in curves.items()), file=sys.stderr)


if __name__ == '__main__':
    main()

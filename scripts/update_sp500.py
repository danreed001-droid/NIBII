#!/usr/bin/env python3
"""Refreshes data/sp500.csv (symbol,name,sector) from Wikipedia's
"List of S&P 500 companies" constituents table. Symbols are written in
Yahoo's form (BRK.B -> BRK-B). Run it when the index changes.

Usage:
    python scripts/update_sp500.py
"""
import csv
import io
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.universe import SP500_PATH

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def main():
    import pandas as pd
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=60).read().decode()
    t = pd.read_html(io.StringIO(html), attrs={'id': 'constituents'})[0]
    rows = sorted((s.replace('.', '-'), n, sec)
                  for s, n, sec in zip(t['Symbol'], t['Security'], t['GICS Sector']))
    if len(rows) < 490:
        sys.exit(f"only {len(rows)} constituents parsed - page layout changed? not writing")
    with open(SP500_PATH, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['symbol', 'name', 'sector'])
        w.writerows(rows)
    print(f"wrote {len(rows)} symbols to {SP500_PATH}")


if __name__ == '__main__':
    main()

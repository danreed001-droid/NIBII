#!/usr/bin/env python3
"""Forces a refresh of data/sp500.csv from Wikipedia right now. Not
normally needed: scripts/mtf_scan.py refreshes it on its own once the
saved copy is more than a week old (see mtl/universe.py).

Usage:
    python scripts/update_sp500.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.universe import SP500_PATH, refresh_sp500


def main():
    added, removed = refresh_sp500()
    print(f"wrote {SP500_PATH}; added: {' '.join(added) or 'none'}; removed: {' '.join(removed) or 'none'}")


if __name__ == '__main__':
    main()

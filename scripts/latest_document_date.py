#!/usr/bin/env python3
"""Print the date of the most recently published documents/<date>.json,
or nothing (and exit 0) if none exist yet. Used by daily-fetch.yml to know
which report to re-render after refreshing the live price snapshot -
documents/live.json itself is excluded, it isn't a ledger document.

Usage:
    python scripts/latest_document_date.py
"""
import glob
import os


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    documents_dir = os.path.join(root, "documents")
    files = sorted(
        f for f in glob.glob(os.path.join(documents_dir, "*.json"))
        if os.path.basename(f) != "live.json"
    )
    if files:
        print(os.path.basename(files[-1])[:-len(".json")])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Print the date of the most recently published documents/<date>.json,
or nothing (and exit 0) if none exist yet. Used by daily-fetch.yml to know
which report to re-render after refreshing the live price snapshot -
documents/live.json itself is excluded, it isn't a ledger document.

Usage:
    python scripts/latest_document_date.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.documents import iter_document_paths


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    documents_dir = os.path.join(root, "documents")
    files = iter_document_paths(documents_dir)
    if files:
        print(os.path.basename(files[-1])[:-len(".json")])


if __name__ == "__main__":
    main()

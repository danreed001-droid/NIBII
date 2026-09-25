"""Shared helper for listing published ledger documents on disk.

documents/ holds one <date>.json per published session PLUS live.json (a
live-price snapshot from scripts/fetch_live.py - see its docstring). Every
script that walks documents/*.json needs to skip live.json or it crashes
trying to read it as a ledger document (no 'assets' key). That happened
three separate times (settle.py, patterns.py, run_verify.py) before this
was pulled into one place - see git history around when scripts/fetch_live.py
was added.
"""
import glob
import os

NON_DOCUMENT_FILES = {"live.json"}


def iter_document_paths(documents_dir):
    """Sorted paths of every documents/*.json file that is an actual ledger
    document - excludes live.json and any future addition to
    NON_DOCUMENT_FILES."""
    return [
        p for p in sorted(glob.glob(os.path.join(documents_dir, "*.json")))
        if os.path.basename(p) not in NON_DOCUMENT_FILES
    ]

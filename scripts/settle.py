#!/usr/bin/env python3
"""Settle matured horizons across every published document with a now-final close.

For each asset/horizon whose maturity date has a close print available and
hasn't been settled yet, fetches that close and marks correctness in place.
Never touches a horizon whose maturity hasn't happened yet, never re-derives
a vote's side or reason (assert_no_reason_drift catches that if it happened),
and aborts without writing if verification fails after settlement.

Usage:
    python scripts/settle.py
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.documents import iter_document_paths
from mtl.fetch import close_on
from mtl.score import document_fully_settled, settle_horizon
from mtl.verify import assert_no_reason_drift, verify_document


def settle_document(doc, close_fn=close_on):
    before = copy.deepcopy(doc)
    changed = False
    for a in doc['assets']:
        for h in a['horizons']:
            if h.get('maturityClose') is not None:
                continue
            mc = close_fn(a['key'], h['maturity'])
            if mc is None:
                continue
            settle_horizon(h, a['close'], mc)
            changed = True
    if changed:
        doc['scored'] = document_fully_settled(doc)
    return changed, before


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    doc_dir = os.path.join(root, "documents")
    any_changed = False

    for path in iter_document_paths(doc_dir):
        doc = json.load(open(path))
        changed, before = settle_document(doc)
        if not changed:
            continue

        drift = assert_no_reason_drift(before, doc)
        if drift:
            print(f"{path}: ABORTING - reason drift detected, not writing:")
            for d in drift:
                print("  ", d)
            sys.exit(1)

        errs = verify_document(doc)
        if errs:
            print(f"{path}: ABORTING - verify errors after settlement, not writing:")
            for e in errs:
                print("  ", e)
            sys.exit(1)

        with open(path, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
        print(f"{path}: settled")
        any_changed = True

    if not any_changed:
        print("nothing to settle")


if __name__ == "__main__":
    main()

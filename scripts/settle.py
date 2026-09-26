#!/usr/bin/env python3
"""Settle matured horizons across every published document.

For each asset/horizon whose maturity date has a print available and hasn't
been settled yet, fetches it via mtl.fetch.close_on() and marks correctness
in place. Since TICKERS is mostly futures (near-24h trading), "a print
available" does not mean a finalized end-of-day close - it can be a live
snapshot taken while that date's session is still in progress. That's
intentional (confirmed 2026-09-25): this project wants continuous
snapshot-based grading, not a wait for a formal close - see close_on()'s
docstring. Never touches a horizon whose maturity hasn't happened yet,
never re-derives a vote's side or reason (assert_no_reason_drift catches
that if it happened), and aborts without writing if verification fails
after settlement.

Usage:
    python scripts/settle.py
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.documents import iter_document_paths
from mtl.fetch import LEGACY_TICKERS, TICKERS, ticker_close_on
from mtl.score import document_fully_settled, settle_horizon
from mtl.verify import assert_no_reason_drift, verify_document


def settlement_plan(doc, a):
    """(ticker, proxy) to grade asset `a` of `doc` against. A document's own
    close came from a['ticker'] (or, for documents drafted before that field
    existed, the LEGACY_TICKERS instrument), so its maturity print has to
    come from the same instrument - grading a TLT close against a ZN=F
    print (or SPX against ES=F) produced nonsense returns. proxy=True means
    no source for the document's own instrument exists, so the current
    TICKERS contract's return over the same dates stands in for it."""
    own = a.get('ticker') or LEGACY_TICKERS.get(a['key'])
    if own:
        return own, False
    return TICKERS[a['key']], True


def settle_document(doc, close_fn=ticker_close_on):
    """close_fn(ticker, date) -> print or None."""
    before = copy.deepcopy(doc)
    changed = False
    for a in doc['assets']:
        ticker, proxy = settlement_plan(doc, a)
        for h in a['horizons']:
            if h.get('maturityClose') is not None:
                continue
            mc = close_fn(ticker, h['maturity'])
            if mc is None:
                continue
            if proxy:
                base = close_fn(ticker, doc['date'])
                if not base:
                    continue
                mc = round(a['close'] * mc / base, 6)
                note = (f"graded on {ticker}'s return from {doc['date']} to {h['maturity']} "
                        f"(no source for this document's own instrument); maturityClose is "
                        f"that return applied to the document's close")
            else:
                note = f"graded against {ticker}"
            settle_horizon(h, a['close'], mc, settlement_note=note)
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

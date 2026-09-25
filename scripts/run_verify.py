#!/usr/bin/env python3
"""Verify every ledger document in a directory. Exit 1 on any failure."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.documents import iter_document_paths
from mtl.verify import verify_document
from mtl.record import aggregate

def main(d="documents"):
    docs, bad = {}, 0
    for f in iter_document_paths(d):
        doc = json.load(open(f))
        doc.pop('version', None)
        docs[doc['date']] = doc
        errs = verify_document(doc)
        print(f"{doc['date']}: {'OK' if not errs else str(len(errs)) + ' ERRORS'}")
        for e in errs:
            print("   !", e); bad += 1
    if docs:
        r = aggregate(docs)
        o = r['overall']
        print(f"\nrecord: {o['hits']}/{o['n']}" + (f" = {o['pct']}%" if o['pct'] is not None else "")
              + f", edge {r['overallEdge']}, settled cells {r['settledCells']}")
        print("overlay:", r['overlay']['caveat'])
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "documents"))

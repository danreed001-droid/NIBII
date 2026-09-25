#!/usr/bin/env python3
"""Build, verify, and write today's document from completed contracts/ files.

The second half of the daily cycle: scripts/prepare_daily.py drafts the
computed fields and stubs the judgment ones; once a human or the model has
replaced every TODO in contracts/inputs.<S>.json and contracts/votes.<S>.json,
this assembles the document, runs the independent verifier against it, and
only writes documents/<S>.json if verification is clean. It never writes a
document that fails its own audit.

Usage:
    python scripts/publish.py 2026-09-25
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.build import build_document
from mtl.verify import verify_document

TODO_MARKER = "TODO"


def find_todos(obj, path="") -> list:
    found = []
    if isinstance(obj, str):
        if TODO_MARKER in obj:
            found.append(path or "<root>")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(find_todos(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(find_todos(v, f"{path}[{i}]"))
    return found


def main(s: str):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    inputs_path = os.path.join(root, "contracts", f"inputs.{s}.json")
    votes_path = os.path.join(root, "contracts", f"votes.{s}.json")
    out_path = os.path.join(root, "documents", f"{s}.json")

    inputs = json.load(open(inputs_path))
    votes = json.load(open(votes_path))

    todos = find_todos(inputs) + find_todos(votes)
    if todos:
        print(f"{len(todos)} unresolved TODO field(s) - not publishing:")
        for t in todos[:20]:
            print("  ", t)
        if len(todos) > 20:
            print(f"   ... and {len(todos) - 20} more")
        return 1

    if os.path.exists(out_path):
        print(f"{out_path} already exists - not overwriting a published document")
        return 1

    doc = build_document(inputs, votes)
    errs = verify_document(doc)
    if errs:
        print(f"{len(errs)} verification error(s) - not publishing:")
        for e in errs:
            print("  ", e)
        return 1

    with open(out_path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(f"published {out_path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    sys.exit(main(sys.argv[1]))

#!/usr/bin/env python3
"""Calls intake: merges calls submitted from the dashboard (a GitHub issue whose
body carries a ```json block) into docs/my_calls.json.

Run by .github/workflows/calls-intake.yml, only for issues the repo owner
opens. The issue body is untrusted text: only the JSON block is read, and
every field is validated - dates, modes, percentages, tickers. The newest
edit per week wins ('at'); a removed call is kept as {m: 'del'}.

Usage:
    ISSUE_BODY="..." python scripts/intake_calls.py      # prints how many calls changed
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'docs', 'my_calls.json')
MODES = ('auto', 'boost', 'boost100', 'steps', 'cash', 'custom', 'del')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TICKER = re.compile(r'^[A-Z][A-Z0-9.\-]{0,9}$')
STAMP = re.compile(r'^[0-9T:.\-+Z]{0,40}$')


def clean(c):
    if not isinstance(c, dict) or c.get('m') not in MODES:
        return None
    at = str(c.get('at') or '')
    out = {'m': c['m'], 'note': str(c.get('note') or '')[:300], 'at': at if STAMP.match(at) else ''}
    if c['m'] == 'custom':
        s = max(0, min(100, int(round(float(c.get('s') or 0)))))
        v = max(0, min(100 - s, int(round(float(c.get('v') or 0)))))
        out.update(s=s, v=v, c=100 - s - v)
    if c['m'] not in ('cash', 'del'):
        swaps = [[a, b] for a, b in (x for x in (c.get('swaps') or []) if isinstance(x, list) and len(x) == 2)
                 if isinstance(a, str) and isinstance(b, str) and TICKER.match(a) and TICKER.match(b)][:5]
        drops = [t for t in (c.get('drops') or []) if isinstance(t, str) and TICKER.match(t)][:5]
        if swaps:
            out['swaps'] = swaps
        if drops:
            out['drops'] = drops
    return out


def parse(body):
    """The calls map from the issue body's ```json block (or {})."""
    m = re.search(r'```json\s*(\{.*?\})\s*```', body or '', re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    calls = data.get('calls') if isinstance(data, dict) else None
    out = {}
    for k, c in (calls or {}).items() if isinstance(calls, dict) else []:
        cc = clean(c)
        if isinstance(k, str) and DATE.match(k) and cc:
            out[k] = cc
    return out


def merge(current, incoming):
    """Newest 'at' wins per week; returns (merged, changed keys)."""
    merged, changed = dict(current), []
    for k, c in incoming.items():
        old = merged.get(k)
        if old is None or (c.get('at') or '') >= (old.get('at') or ''):
            if old != c:
                merged[k] = c
                changed.append(k)
    return dict(sorted(merged.items())), changed


def main():
    incoming = parse(os.environ.get('ISSUE_BODY', ''))
    try:
        with open(PATH) as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = {}
    current = {k: c for k, c in ((doc.get('calls') or {}).items()) if clean(c)}
    merged, changed = merge(current, incoming)
    if changed:
        with open(PATH, 'w') as f:
            json.dump({'app': 'nibii-calls', 'v': 1, 'calls': merged}, f, indent=1)
            f.write('\n')
    print(len(changed))
    print(f"calls received {len(incoming)}, changed {len(changed)}: {', '.join(changed) or '-'}", file=sys.stderr)


if __name__ == '__main__':
    main()

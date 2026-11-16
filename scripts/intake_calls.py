#!/usr/bin/env python3
"""Calls intake: merges calls submitted from the dashboard (a GitHub issue whose
body carries a ```json block) into docs/my_calls.json.

Run by .github/workflows/calls-intake.yml, only for issues the repo owner
opens. The issue body is untrusted text: only the JSON block is read, and
every field is validated - dates, modes, percentages, tickers. The newest
edit per week wins ('at'); a removed call is kept as {m: 'del'}. The same block can carry
"warn": {date: {c: 'out' | 'stay', at, note}} - the viewer's call on a downtrend-warning
day (stay in stocks, or out into bonds and gold), scored 3 months later by the daily scan. And
"you2": {date: {stocks: [tickers], note, at}} - the viewer's own stock list for You-2 (the default plan's
timing on the viewer's stocks, mtl/you2.py), from that date's close on; {m: 'del'} removes one. And
"plans": {name: {date: {stocks, note, at}}} - the viewer's own named plans, each like You-2 (up to 10 plans; a name
is 1-30 letters, digits, spaces or - _ & ').

Usage:
    ISSUE_BODY="..." python scripts/intake_calls.py      # prints how many calls changed
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'docs', 'my_calls.json')
MODES = ('rotation', 'gold', 'bonds', 'mf', 'auto', 'boost', 'boost100', 'cushion', 'steps', 'cash', 'custom', 'del')
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
    if c['m'] not in ('cash', 'del', 'rotation', 'gold', 'bonds', 'mf'):   # whole-account calls hold no stocks to swap
        swaps = [[a, b] for a, b in (x for x in (c.get('swaps') or []) if isinstance(x, list) and len(x) == 2)
                 if isinstance(a, str) and isinstance(b, str) and TICKER.match(a) and TICKER.match(b)][:5]
        drops = [t for t in (c.get('drops') or []) if isinstance(t, str) and TICKER.match(t)][:5]
        if swaps:
            out['swaps'] = swaps
        if drops:
            out['drops'] = drops
    return out


def block(body):
    """The parsed ```json block of the issue body (or {})."""
    m = re.search(r'```json\s*(\{.*?\})\s*```', body or '', re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_warn(body):
    """The downtrend-warning calls {date: {c, note, at}} from the issue body (or {})."""
    w = block(body).get('warn')
    out = {}
    for k, c in (w.items() if isinstance(w, dict) else []):
        if isinstance(k, str) and DATE.match(k) and isinstance(c, dict) and c.get('c') in ('out', 'stay', 'del'):
            at = str(c.get('at') or '')
            out[k] = {'c': c['c'], 'note': str(c.get('note') or '')[:300], 'at': at if STAMP.match(at) else ''}
    return out


def parse_you2(body):
    """You-2 stock lists {date: {stocks, note, at}} (or {m: 'del'}) from the issue body (or {})."""
    y = block(body).get('you2')
    out = {}
    for k, c in (y.items() if isinstance(y, dict) else []):
        if not (isinstance(k, str) and DATE.match(k) and isinstance(c, dict)):
            continue
        at = str(c.get('at') or '')
        at = at if STAMP.match(at) else ''
        if c.get('m') == 'del':
            out[k] = {'m': 'del', 'at': at}
            continue
        st = list(dict.fromkeys(t.strip().upper() for t in (c.get('stocks') or []) if isinstance(t, str)))
        st = [t for t in st if TICKER.match(t)][:10]
        if st:
            out[k] = {'stocks': st, 'note': str(c.get('note') or '')[:300], 'at': at}
    return out


PLAN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _&'\-]{0,29}$")
MAX_PLANS = 10


def parse_plans(body):
    """Named plans {name: {date: {stocks, note, at}}} (or {m: 'del'} entries) from the issue body (or {})."""
    p = block(body).get('plans')
    out = {}
    for nm, ent in (p.items() if isinstance(p, dict) else []):
        if not (isinstance(nm, str) and PLAN_NAME.match(nm.strip())):
            continue
        got = parse_you2('```json\n' + json.dumps({'you2': ent}) + '\n```')
        if got:
            out[nm.strip()] = got
    return dict(list(out.items())[:MAX_PLANS])


def parse(body):
    """The calls map from the issue body's ```json block (or {})."""
    data = block(body)
    calls = data.get('calls')
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
    w_in = parse_warn(os.environ.get('ISSUE_BODY', ''))
    w_cur = {k: c for k, c in (doc.get('warn') or {}).items() if isinstance(c, dict) and c.get('c') in ('out', 'stay', 'del')}
    w_merged, w_changed = merge(w_cur, w_in)
    y_in = parse_you2(os.environ.get('ISSUE_BODY', ''))
    y_cur = {k: c for k, c in (doc.get('you2') or {}).items() if isinstance(c, dict) and (c.get('stocks') or c.get('m') == 'del')}
    y_merged, y_changed = merge(y_cur, y_in)
    p_in = parse_plans(os.environ.get('ISSUE_BODY', ''))
    p_cur = {nm: {k: c for k, c in ent.items() if isinstance(c, dict) and (c.get('stocks') or c.get('m') == 'del')}
             for nm, ent in (doc.get('plans') or {}).items() if isinstance(ent, dict)}
    p_merged, p_changed = dict(p_cur), []
    for nm, ent in p_in.items():
        if nm not in p_merged and len(p_merged) >= MAX_PLANS:
            continue
        m_, ch_ = merge(p_merged.get(nm, {}), ent)
        p_merged[nm] = m_
        p_changed += [f'{nm} {k}' for k in ch_]
    if changed or w_changed or y_changed or p_changed:
        out = {'app': 'nibii-calls', 'v': 1, 'calls': merged}
        if w_merged:
            out['warn'] = w_merged
        if y_merged:
            out['you2'] = y_merged
        if p_merged:
            out['plans'] = p_merged
        with open(PATH, 'w') as f:
            json.dump(out, f, indent=1)
            f.write('\n')
    print(len(changed) + len(w_changed) + len(y_changed) + len(p_changed))
    print(f"calls received {len(incoming)}, changed {len(changed)}: {', '.join(changed) or '-'}; "
          f"warning calls received {len(w_in)}, changed {len(w_changed)}: {', '.join(w_changed) or '-'}; "
          f"You-2 lists received {len(y_in)}, changed {len(y_changed)}: {', '.join(y_changed) or '-'}; "
          f"plan lists changed {len(p_changed)}: {', '.join(p_changed) or '-'}", file=sys.stderr)


if __name__ == '__main__':
    main()

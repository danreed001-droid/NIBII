#!/usr/bin/env python3
"""Add (or remove) your own item on the market events page from the "Market event" issue form
(.github/ISSUE_TEMPLATE/market-event.yml), in data/my_events.json.

Run by .github/workflows/event-from-issue.yml, which only calls it for issues opened by the repository owner.
Reads the issue body from ISSUE_BODY and the issue number from ISSUE_NUMBER. Prints what it did; exits non-zero
with a readable message when the form can't be used (bad date or link, a duplicate, nothing to remove).

    ISSUE_BODY=... ISSUE_NUMBER=12 python scripts/add_event_from_issue.py
"""
import json
import os
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl.event_types import TYPES  # noqa: E402
PATH = os.path.join(ROOT, 'data', 'my_events.json')
FIELDS = {'Date': 'date', 'What happened': 'what', 'Link': 'link', 'Type': 'type', 'Add or remove': 'action'}
NO_RESPONSE = '_No response_'
MAX_LEN = 300


def parse_issue_form(body):
    """GitHub renders an issue form as '### <label>' headings each followed by the answer."""
    out = {}
    for block in re.split(r'^###\s+', body or '', flags=re.M)[1:]:
        label, _, value = block.partition('\n')
        field = FIELDS.get(label.strip())
        if field:
            value = value.strip()
            out[field] = '' if value == NO_RESPONSE else value
    return out


def load(path=PATH):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return dict(about='Your own items for the market events page, from its "Add news" form '
                          '(scripts/add_event_from_issue.py).', events=[])


def save(doc, path=PATH):
    doc['events'].sort(key=lambda e: (e['d'], e['what']))
    with open(path, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')


def same(a, b):
    return ' '.join(a.split()).casefold() == ' '.join(b.split()).casefold()


def apply(form, doc, issue, today):
    """Add or remove the form's item in doc. Returns a one-line description; raises ValueError when unusable."""
    what = ' '.join((form.get('what') or '').split())
    if not what:
        raise ValueError('"What happened" is empty')
    if len(what) > MAX_LEN:
        raise ValueError(f'"What happened" is {len(what)} characters; keep it under {MAX_LEN}')
    raw = (form.get('date') or '').strip() or today
    try:
        d = date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(f'date {raw!r} is not YYYY-MM-DD') from None
    if not '2000-01-01' <= d <= today:
        raise ValueError(f'date {d} is outside 2000-01-01 to today')
    link = (form.get('link') or '').strip()
    if link and not re.match(r'https?://\S+$', link):
        raise ValueError(f'link {link!r} must start with http:// or https://')
    evs = doc['events']
    if (form.get('action') or 'Add').strip().lower() == 'remove':
        hit = [e for e in evs if e['d'] == d and same(e['what'], what)]
        if not hit:
            mine = [e['what'] for e in evs if e['d'] == d]
            raise ValueError(f'nothing you added on {d} reads "{what}"' +
                             (f' (that day has: {"; ".join(mine)})' if mine else ' (you added nothing that day)'))
        doc['events'] = [e for e in evs if e not in hit]
        return f'removed {d}: {what}'
    if any(e['d'] == d and same(e['what'], what) for e in evs):
        raise ValueError(f'"{what}" is already on {d}')
    kind = (form.get('type') or '').strip()
    evs.append(dict(d=d, what=what, **({'link': link} if link else {}), **({'type': kind} if kind in TYPES else {}), issue=issue))
    return f'added {d}: {what}' + (f' ({kind})' if kind in TYPES else '')


def main():
    doc = load()
    today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    num = os.environ.get('ISSUE_NUMBER', '?')
    try:
        msg = apply(parse_issue_form(os.environ.get('ISSUE_BODY', '')), doc, int(num) if num.isdigit() else num, today)
    except ValueError as e:
        print(f'ERROR: {e}')
        sys.exit(1)
    save(doc)
    print(msg)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Append a news event submitted through the "News event" issue form
(.github/ISSUE_TEMPLATE/news-event.yml) to data/news_log.json.

Run by .github/workflows/news-from-issue.yml, which only calls it for
issues opened by the repository owner. Reads the issue body from the
ISSUE_BODY environment variable and the issue number from ISSUE_NUMBER.
Prints the new entry's id; exits non-zero with a readable message if the
form is missing a required field or the date is malformed.

The entry has the same shape the "Daily market news log" Routine writes,
plus origin="manual (issue #N)" so a hand-entered event stays
distinguishable from a researched one.

Usage:
    ISSUE_BODY=... ISSUE_NUMBER=12 python scripts/add_news_from_issue.py
"""
import json
import os
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

# issue-form label -> news-log field
FIELDS = {
    'Date': 'date', 'Time': 'time', 'Event': 'event', 'Tickers': 'tickers',
    'Direction': 'direction', 'Impact': 'impact', 'Category': 'category',
    'Region': 'region', 'Numbers': 'numbers', 'Vs. expectations': 'vsExp',
    'Market reaction': 'reaction', 'Source URL': 'source',
}
REQUIRED = ('date', 'time', 'event', 'tickers', 'direction', 'impact', 'category')
NO_RESPONSE = '_No response_'


def parse_issue_form(body):
    """GitHub renders an issue form as '### <label>' headings each followed
    by the answer. Returns {field: value} for the labels in FIELDS."""
    out = {}
    for block in re.split(r'^###\s+', body or '', flags=re.M)[1:]:
        label, _, value = block.partition('\n')
        field = FIELDS.get(label.strip())
        if field:
            value = value.strip()
            out[field] = '' if value == NO_RESPONSE else value
    return out


def slug(text, n=40):
    s = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return s[:n].rstrip('-')


def build_entry(form, log, issue_number, today):
    missing = [f for f in REQUIRED if not form.get(f)]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")
    try:
        d = date.fromisoformat(form['date'])
    except ValueError:
        raise ValueError(f"date {form['date']!r} is not YYYY-MM-DD")
    ds = d.isoformat()
    order = 1 + max((r['data'].get('order') or 0 for r in log if r['data'].get('date') == ds),
                    default=0)
    data = dict(
        addedAt=today, category=form['category'], date=ds, day=d.strftime('%a'),
        direction=form['direction'], event=' '.join(form['event'].split()),
        impact=form['impact'], numbers=form.get('numbers') or 'n/a', order=order,
        reaction=' '.join((form.get('reaction') or 'n/a').split()),
        region=form.get('region') or 'US', source=form.get('source') or 'n/a',
        tickers=form['tickers'], time=form['time'], vsExp=form.get('vsExp') or 'n/a',
        origin=f"manual (issue #{issue_number})",
    )
    entry_id = f"{ds}-{order}-{slug(data['event'])}"
    if any(r['id'] == entry_id for r in log):
        raise ValueError(f"an entry with id {entry_id} already exists")
    return dict(id=entry_id, data=data)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "news_log.json")
    log = json.load(open(path))
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    try:
        entry = build_entry(parse_issue_form(os.environ.get('ISSUE_BODY', '')), log,
                            os.environ.get('ISSUE_NUMBER', '?'), today)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    log.append(entry)
    log.sort(key=lambda r: (r['data']['date'], r['data'].get('order') or 0))
    # Same serialization the news-log sync Routines use, so diffs stay append-only.
    with open(path, "w") as f:
        f.write(json.dumps(log, indent=2, ensure_ascii=False))
    print(entry['id'])


if __name__ == "__main__":
    main()

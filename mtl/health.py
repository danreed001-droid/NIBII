"""Issues log behind the scanner page's "Issues (last 2 weeks)" section: every data problem a run finds and every
failed workflow run, one line each, dated. scripts/momentum_scan.py adds tonight's data problems; a failed run's
own step adds its line with scripts/log_issue.py. Entries older than KEEP_DAYS are dropped on each save, so the
file stays small year after year."""
import json
import os
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, 'data', 'issues_log.json')
SHOW_DAYS = 14      # the page lists the last two weeks
KEEP_DAYS = 60


def load(path=LOG_PATH):
    """The log's entries, oldest first; a missing file is an empty log, a corrupt one raises (never overwritten)."""
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return []
    return list(doc.get('entries') or [])


def save(entries, path=LOG_PATH, today=None):
    cut = ((today or date.today()) - timedelta(days=KEEP_DAYS)).isoformat()
    keep = [e for e in entries if e['d'] >= cut]
    with open(path, 'w') as fh:
        json.dump(dict(about='Issues found by the scanner and its workflows (mtl/health.py); the page shows the last '
                             f'{SHOW_DAYS} days.', entries=keep), fh, indent=1)
        fh.write('\n')
    return keep


def add(entries, d, src, text, at=None):
    """Append one issue for day `d` from `src` ('scan', 'run', ...) unless the same line is already logged for
    that day. Returns True when it was added."""
    if any(e['d'] == d and e['src'] == src and e['text'] == text for e in entries):
        return False
    entries.append(dict(d=d, src=src, text=text, at=at or datetime.now(timezone.utc).isoformat(timespec='seconds')))
    entries.sort(key=lambda e: (e['d'], e['at']))
    return True


def recent(entries, today, days=SHOW_DAYS):
    """Entries from the last `days` calendar days up to `today` (a date or 'YYYY-MM-DD'), newest first."""
    if isinstance(today, str):
        today = date.fromisoformat(today)
    cut = (today - timedelta(days=days)).isoformat()
    return sorted((e for e in entries if e['d'] > cut), key=lambda e: (e['d'], e['at']), reverse=True)

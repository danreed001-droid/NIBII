"""Add one line to the scanner page's issues log (mtl/health.py), from a workflow step that failed:

    python scripts/log_issue.py run "The scanner run failed: tonight's decision may be missing."

The date is today in New York unless --date YYYY-MM-DD is given."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl import health  # noqa: E402


def main(argv):
    args = list(argv)
    d = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    if '--date' in args:
        i = args.index('--date')
        d = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit('usage: log_issue.py SOURCE "TEXT" [--date YYYY-MM-DD]')
    src, text = args
    entries = health.load()
    if health.add(entries, d, src, text):
        health.save(entries)
        print(f"logged: {d} {src}: {text}")
    else:
        print("already logged")


if __name__ == '__main__':
    main(sys.argv[1:])

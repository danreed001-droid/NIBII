"""Is the nightly scanner run in? Every run logs the default plan's decision for the session it read to the paper
record (data/paper_ledger.json), so the record's last day says which close the last run used.

    python scripts/check_scanner_fresh.py gate    # the backup run: run=false in $GITHUB_OUTPUT when tonight's is in
    python scripts/check_scanner_fresh.py watch   # the morning watchdog: exits 1 when last night's run is missing
    python scripts/check_scanner_fresh.py kick    # the hourly data fetch: run=true from 6pm New York time when
                                                  # tonight's run is missing (it then starts the scanner by hand)
"""
import os
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

WATCH_LAG = 8   # hours: the watchdog's checks (3:23am to 9:31am New York) all look back to last night
KICK_FROM = time(18, 0)   # New York: the kick waits for the day's end-of-day prices (the scanner's own first try is 6:20pm)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import paper  # noqa: E402
from mtl.calendar_nyse import is_trading_day, previous_trading_day  # noqa: E402


def last_closed(now):
    """The latest NYSE session that has closed by `now` (16:15 New York time, as for the paper record)."""
    ny = now.astimezone(ZoneInfo('America/New_York'))
    d = ny.date()
    if is_trading_day(d) and ny.time() >= paper.CLOSE_ET:
        return d.isoformat()
    return previous_trading_day(d).isoformat()


def last_logged():
    led = paper.load(os.path.join(ROOT, 'data', 'paper_ledger.json')) or {}
    ent = led.get('entries') or []
    return ent[-1]['d'] if ent else None


def main(mode, now=None):
    now = now or datetime.now(timezone.utc)
    # the watchdog asks for last night's run: a check GitHub starts hours late (even past today's close) still
    # looks for the session before, not one tonight's run hasn't had a chance to log yet
    want, have = last_closed(now if mode in ('gate', 'kick') else now - timedelta(hours=WATCH_LAG)), last_logged()
    if mode == 'kick':
        # GitHub starts the scanner's own scheduled runs hours late or drops them (none fired Nov 2, 2026), while the
        # hourly data fetch keeps running: from 6pm on a trading day (or any time after a missed one) it starts the
        # scanner when the last closed session's decision isn't logged yet
        ny = now.astimezone(ZoneInfo('America/New_York'))
        early = want == ny.date().isoformat() and ny.time() < KICK_FROM
        run = (have is None or have < want) and not early
        print(f"last logged {have}, last closed {want}, New York {ny:%H:%M}: {'start the scanner' if run else 'nothing to do'}")
        out = os.environ.get('GITHUB_OUTPUT')
        if out:
            with open(out, 'a') as fh:
                fh.write(f"run={'true' if run else 'false'}\n")
        return 0
    if mode == 'gate':
        run = have is None or have < want
        print(f"last logged {have}, last closed {want}: {'run' if run else 'already in, skip'}")
        out = os.environ.get('GITHUB_OUTPUT')
        if out:
            with open(out, 'a') as fh:
                fh.write(f"run={'true' if run else 'false'}\n")
        return 0
    if have is None or have < want:
        print(f"The scanner's last logged decision is for {have}, but {want}'s close should be in: the nightly run "
              f"failed, was skipped, or never started.")
        return 1
    print(f"ok: {have}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'watch'))

#!/usr/bin/env python3
"""Ignition alert: writes a GitHub issue title/body when tonight's ignition
scan (data/ignition_scan.json, written by scripts/ignition_scan.py) flagged
any stock as an Ignition - a gap up of 8%+ on 3x+ normal volume in an
uptrend. The workflow opens the issue with an @mention of the repo owner so
GitHub emails / pushes it.

Writes nothing (no alert) when there are no ignitions or when the scan file
wasn't refreshed today (the scan step failed and the file is yesterday's).

Usage:
    python scripts/ignition_alert.py OUT_DIR [owner]   # writes OUT_DIR/alert_title.txt + alert_body.md
"""
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = os.path.join(ROOT, 'data', 'ignition_scan.json')
PAGE = 'https://danreed001-droid.github.io/NIBII/scanner.html#watch'


def pct(x, d=1):
    return '–' if x is None else f'{x * 100:+.{d}f}%'


def vol(v):
    return '–' if v is None else f'{v:.1f}x'


def fmt(d):
    x = date.fromisoformat(d)
    return x.strftime('%a %b ') + str(x.day)


def build(scan, owner=None, today=None):
    """(title, body) when the scan has ignitions and is fresh, else None."""
    today = today or datetime.now(timezone.utc).date()
    gen = (scan.get('generatedAt') or '')[:10]
    if gen != today.isoformat():
        return None
    ign = [r for r in scan.get('today') or [] if r.get('kind') == 'ignition']
    if not ign:
        return None
    ign.sort(key=lambda r: -(r.get('score') or 0))
    when = fmt(scan['asOf'])
    title = f"Ignition: {', '.join(r['t'] for r in ign[:8])}{' +' + str(len(ign) - 8) if len(ign) > 8 else ''} ({when} close)"
    rows = '\n'.join(
        f"| **{r['t']}** | {r.get('n') or ''} | {r.get('ind') or ''} | {pct(r.get('chg'))} | {pct(r.get('gap'))} | "
        f"{vol(r.get('vr'))} | {r.get('rs') if r.get('rs') is not None else '–'} | "
        f"{pct(r.get('offHigh'))} | {r.get('repeats') or 1}{' · group move' if r.get('group') else ''} |" for r in ign)
    st = (scan.get('stats') or {}).get('ignition') or {}
    base = (scan.get('stats') or {}).get('all') or {}
    odds = ''
    if st.get('up50') is not None and base.get('up50') is not None:
        odds = (f"\n\nSince {scan.get('statsFrom')}, {round(st['up50'] * 100)}% of ignitions reached +50% within 120 sessions "
                f"(vs {round(base['up50'] * 100)}% for any liquid stock), but the median one did "
                f"{pct(st.get('ex60'))} vs SPY over 60 sessions - most fail, so use the stop.")
    body = (f"{'@' + owner + ' ' if owner else ''}**{len(ign)} ignition{'s' if len(ign) != 1 else ''} at the {when} close** "
            f"- a gap up of 8%+ on 3x+ normal volume, in an uptrend.\n\n"
            "| Stock | Name | Industry | Day | Gap | Vol vs 50d | RS | Off 52w high | Gaps 12m |\n"
            "|---|---|---|---|---|---|---|---|---|\n" + rows +
            "\n\n**Before acting:** check the news behind each gap (guidance raise, big contract, first profit = the winners' pattern; "
            "a buyout or one-off = skip). The usual stop is the flag day's low; a second or third gap on later earnings is the "
            "stronger signal." + odds +
            f"\n\n[Next big thing watch]({PAGE}) · automated scan, not investment advice.")
    return title, body


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    owner = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        with open(SCAN) as f:
            scan = json.load(f)
    except (OSError, ValueError):
        print('no ignition scan - no alert', file=sys.stderr)
        return
    res = build(scan, owner)
    if not res:
        print('no ignitions today - no alert', file=sys.stderr)
        return
    title, body = res
    with open(os.path.join(out, 'alert_title.txt'), 'w') as f:
        f.write(title)
    with open(os.path.join(out, 'alert_body.md'), 'w') as f:
        f.write(body)
    print(title, file=sys.stderr)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Ignition alert: writes a GitHub issue title/body when tonight's ignition
scan (data/ignition_scan.json, written by scripts/ignition_scan.py) flagged
any stock as an Ignition (a gap up of 8%+ on 3x+ normal volume in an uptrend)
or a Turnaround (a gap up of 15%+ on 5x+ volume while still beaten down), with
the Action plan's line for each and the market note. The workflow opens the
issue with an @mention of the repo owner so GitHub emails / pushes it.

Writes nothing (no alert) when there are no such flags or when the scan file
wasn't refreshed today (the scan step failed and the file is yesterday's).

Usage:
    python scripts/ignition_alert.py OUT_DIR [owner]   # writes OUT_DIR/alert_title.txt + alert_body.md
"""
import json
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.ignition import market_note, plan  # noqa: E402

KINDS = {'ignition': 'Ignition', 'turnaround': 'Turnaround'}
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
    ign = [r for r in scan.get('today') or [] if r.get('kind') in KINDS]
    heating = [r for r in scan.get('themes') or [] if r.get('emerging') and r.get('newTop')]
    theme_txt = ('\n\n**Industries heating up** (new in the top 10, uptrend share rising fast): ' + '; '.join(
        f"{r['ind']} (heat {r['heat']}, {round(r['up'] * 100)}% in uptrend, {r['dUp'] * 100:+.0f} pts in 4 weeks; strongest "
        f"{', '.join(r.get('leaders') or [])})" for r in heating)) if heating else ''
    wl = [(g['group'], r) for g in scan.get('watch') or [] for r in g.get('rows') or []
          if (r.get('flag') or {}).get('days') == 0 and r['flag']['kind'] != 'pocket' and r['t'] not in {x['t'] for x in ign}]
    wl_txt = ('\n\n**Watchlist:** ' + '; '.join(f"{r['t']} ({g}) {r['flag']['kind']}" for g, r in wl)
              + ' - check the news; stop under the flag day\'s low.') if wl else ''
    if not ign and wl:
        when = fmt(scan['asOf'])
        title = f"Watchlist alert: {', '.join(r['t'] + ' ' + r['flag']['kind'] for _, r in wl[:6])} ({when} close)"
        body = (f"{'@' + owner + ' ' if owner else ''}A watchlist stock flagged at the {when} close." + wl_txt + theme_txt +
                f"\n\n[Watchlist and action plan]({PAGE}) · automated scan, not investment advice.")
        return title, body
    if not ign:
        if not heating:
            return None
        when = fmt(scan['asOf'])
        title = f"Theme alert: {', '.join(r['ind'] for r in heating[:3])} heating up ({when} close)"
        body = (f"{'@' + owner + ' ' if owner else ''}No ignitions tonight, but a field is heating up." + theme_txt +
                f"\n\nWatch these for ignitions on their next earnings. [Hot industries]({PAGE}) · automated scan, not investment advice.")
        return title, body
    ign.sort(key=lambda r: -(r.get('score') or 0))
    when = fmt(scan['asOf'])
    title = f"Ignition alert: {', '.join(r['t'] for r in ign[:8])}{' +' + str(len(ign) - 8) if len(ign) > 8 else ''} ({when} close)"
    rows = '\n'.join(
        f"| **{r['t']}** | {KINDS[r['kind']]} | {r.get('n') or ''} | {r.get('ind') or ''} | {pct(r.get('chg'))} | {pct(r.get('gap'))} | "
        f"{vol(r.get('vr'))} | {r.get('rs') if r.get('rs') is not None else '–'} | "
        f"{pct(r.get('offHigh'))} | {r.get('repeats') or 1}{' · group move' if r.get('group') else ''} |" for r in ign)
    acts = plan(scan)
    flagged = {r['t'] for r in ign}
    todo = [a for a in acts if a['t'] in flagged and a['act'] == 'new']
    exits = [a for a in acts if a['act'] in ('exit', 'trail', 'profit') and a['t'] not in flagged]
    lines = '\n'.join(f"- **{a['t']}**: {a['text']}" for a in todo)
    if exits:
        lines += '\n\n**Earlier flags:**\n' + '\n'.join(f"- **{a['t']}** ({a['act']}): {a['text']}" for a in exits[:10])
    stats = scan.get('stats') or {}
    base = stats.get('all') or {}
    odds = []
    for k, label in KINDS.items():
        st = stats.get(k) or {}
        if st.get('up50') is not None and base.get('up50') is not None:
            odds.append(f"{label.lower()}s {round(st['up50'] * 100)}% (median {pct(st.get('ex60'))} vs SPY over 60 sessions)")
    odds_txt = (f"\n\nSince {scan.get('statsFrom')}, share reaching +50% within 120 sessions: " + '; '.join(odds) +
                f"; any liquid stock {round(base['up50'] * 100)}%. Most flags fail - use the stop.") if odds and base.get('up50') is not None else ''
    n = len(ign)
    body = (f"{'@' + owner + ' ' if owner else ''}**{n} flag{'s' if n != 1 else ''} at the {when} close** "
            "- Ignition = gap up 8%+ on 3x+ volume in an uptrend; Turnaround = gap up 15%+ on 5x+ volume while beaten down.\n\n"
            "| Stock | Setup | Name | Industry | Day | Gap | Vol vs 50d | RS | Off 52w high | Gaps 12m |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n" + rows +
            f"\n\n**Market:** {market_note(scan.get('market'))[1]}\n\n**What to do:**\n" + lines + wl_txt + theme_txt + odds_txt +
            f"\n\n[Action plan and position sizes]({PAGE}) · automated scan, not investment advice.")
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

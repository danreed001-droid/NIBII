"""Paper record of the default plan (Boost + rotation): a frozen, time-stamped forward test.

Each evening after the close, the scanner run appends the decision it made at that close to
data/paper_ledger.json: what the plan will hold after the next close (the mode, the whipsaw half and
the Boost list) and the weights that follow. Entries are only ever added, never edited, and each one
carries the time it was logged and a fingerprint of the rule code, so the record shows exactly what was
known when, and whether the rules changed along the way.

From the ledger alone it then builds:
- the paper account: each decision fills at the next session's close with SLIP per side on what
  changes hands; positions drift between trades and are reset to their weights on the weekly trade;
- a replay check: the run's own replay of each past day (on today's data and code) must give the decision
  that was logged at the time; any difference is listed;
- the status against the ranges the 2000-2026 backtest gives for 3, 6 and 12 months.
A deliberate rule change is listed in the ledger's `updates` (date, new fingerprint, what changed); entries logged
under a listed version aren't flagged, and the replay check only compares entries logged under today's rules.
Pure apart from load/save and the code fingerprint; no network."""
import hashlib
import json
import os
from datetime import date, datetime, time, timezone

from mtl.rotation import WHIP_SHARE

START = '2026-10-14'            # the day the current default plan (with the rebound rule) went live
SLIP = 0.0015                   # per side, as in the backtest
CASH = 'CASH'
RULE_FILES = ('mtl/momentum.py', 'mtl/rotation.py', 'mtl/rebound.py', 'mtl/narrow.py', 'mtl/lowerhigh.py',
              'mtl/news.py', 'mtl/structure.py', 'mtl/universe.py', 'mtl/fade.py', 'mtl/calendar_nyse.py')
SLOTS = 5                       # the Boost list's slots: each stock is a fifth, an empty slot (fading filter) is cash
SCAN = 'scripts/momentum_scan.py'   # only its module-level CONSTANTS count (settings, not page code)
CLOSE_ET = time(16, 15)             # a decision is logged only after the close it is read from

# The 2000-2026 backtest of the default plan (with the fading-energy filter, its whipsaw shadow count and the whole-account
# whipsaw switch since Oct 16, 2026) on S&P 500 members at each date - the stocks the live plan picks from since
# Oct 19, 2026 (engine NBup, 41.0% a year) - 0.15% per side, every window of that length: return percentiles, share
# ahead of SPY, the 1-in-10 shortfall against SPY, and the worst drop inside the window (typical, and the 1-in-20 worst).
BANDS = {
    63: dict(label='3 months', p5=-0.096, p25=-0.008, p50=0.077, p75=0.168, p95=0.355, ahead=0.68, lag10=-0.073, dd50=-0.095, dd95=-0.19),
    126: dict(label='6 months', p5=-0.091, p25=0.028, p50=0.148, p75=0.330, p95=0.729, ahead=0.78, lag10=-0.070, dd50=-0.128, dd95=-0.24),
    252: dict(label='12 months', p5=-0.085, p25=0.110, p50=0.313, p75=0.655, p95=1.466, ahead=0.83, lag10=-0.061, dd50=-0.163, dd95=-0.28),
}
WORST_DD = -0.34                # the backtest's worst drop, 2000-2026


def fingerprint(root):
    """sha256 over the rule modules and the scanner's settings lines; {file: short hash} alongside."""
    parts, files = [], {}
    for f in RULE_FILES:
        try:
            with open(os.path.join(root, f), 'rb') as fh:
                b = fh.read()
        except OSError:
            b = b''
        files[f] = hashlib.sha256(b).hexdigest()[:12]
        parts.append(b)
    try:
        with open(os.path.join(root, SCAN)) as fh:
            consts = ''.join(l for l in fh if l[:1].isupper() and ' = ' in l.split('#')[0] and 'os.path' not in l)   # settings, not file paths
    except OSError:
        consts = ''
    files[SCAN + ' (settings)'] = hashlib.sha256(consts.encode()).hexdigest()[:12]
    parts.append(consts.encode())
    return hashlib.sha256(b'\0'.join(parts)).hexdigest()[:16], files


def weights(mode, half, stocks):
    """Target weights after the next close: a fifth per Boost-list stock while the mode is 'boost' (an empty
    slot, e.g. a stock the fading filter skipped, is cash; WHIP_SHARE of the account in `half` during the whipsaw
    switch, all of it since Oct 16, 2026), otherwise all in the mode's asset (or cash)."""
    if mode != 'boost':
        return {mode or CASH: 1.0}
    if half and WHIP_SHARE >= 1:
        return {half: 1.0}
    stocks = [t for t in stocks or []]
    if not stocks:
        return {CASH: 1.0}
    part = 1 - WHIP_SHARE if half else 1.0
    each = part / max(SLOTS, len(stocks))
    w = {t: each for t in stocks}
    if part - each * len(stocks) > 1e-12:
        w[CASH] = part - each * len(stocks)
    if half:
        w[half] = w.get(half, 0.0) + WHIP_SHARE
    return w


def decision(day, mode, half, stocks):
    mode = mode or 'boost'
    half = half if mode == 'boost' else None
    return dict(d=day, mode=mode, half=half, list=sorted(stocks or []), w={k: round(v, 6) for k, v in weights(mode, half, stocks).items()})


def after_close(day, now=None):
    """True once the session `day` has closed in New York (so its decision can be logged)."""
    from zoneinfo import ZoneInfo
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('America/New_York'))
    d = date.fromisoformat(day)
    return now.date() > d or (now.date() == d and now.time() >= CLOSE_ET)


def new_ledger(fp, files):
    return dict(about='Paper record of the default plan: one decision per session, logged after the close it is '
                      'read from and never edited (mtl/paper.py).',
                start=START, slip=SLIP, frozen=dict(since=START, fingerprint=fp, files=files), entries=[])


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save(path, ledger):
    with open(path, 'w') as fh:
        json.dump(ledger, fh, indent=1)
        fh.write('\n')


def record(ledger, dec, at, fp, src='scanner run'):
    """Append the decision for dec['d'] unless that day is already logged (or is before the start).
    Returns True when it was added. Earlier entries are never touched."""
    if dec['d'] < ledger['start'] or any(e['d'] == dec['d'] for e in ledger['entries']):
        return False
    if ledger['entries'] and dec['d'] < ledger['entries'][-1]['d']:
        return False
    ledger['entries'].append(dict(dec, at=at, fp=fp, src=src))
    return True


def account(entries, prices, calendar, slip=SLIP):
    """[[date, value]] from 1.0 at the first fill: each decision fills at the next session's close. On a fill
    the account moves to the target weights when the holdings change or on the weekly trade (a Friday
    decision); otherwise positions drift. Costs `slip` per side on the value traded. CASH earns nothing; a
    missing close keeps the last one."""
    idx = {d: i for i, d in enumerate(calendar)}
    fills = {}
    for e in sorted(entries, key=lambda e: e['d']):
        k = idx.get(e['d'])
        if k is not None and k + 1 < len(calendar):
            fills[calendar[k + 1]] = e
    if not fills:
        return []
    first = min(fills)
    last_px, units, out, val = {}, {}, [], 1.0

    def px(t, d):
        if t == CASH:
            return 1.0
        p = (prices.get(t) or {}).get(d)
        if p:
            last_px[t] = p
        return last_px.get(t)
    for d in calendar[idx[first]:]:
        if units:
            val = sum(n * (px(t, d) or 0.0) for t, n in units.items())
        else:
            for t in fills.get(d, {}).get('w', {}):
                px(t, d)
        e = fills.get(d)
        if e:
            cur = {t: n * (px(t, d) or 0.0) / val for t, n in units.items()} if units and val else {}
            tgt = e['w']
            weekly = date.fromisoformat(e['d']).weekday() == 4
            if not units or set(k for k, v in cur.items() if v > 1e-9) != set(tgt) or weekly:
                traded = sum(abs(tgt.get(t, 0.0) - cur.get(t, 0.0)) for t in set(tgt) | set(cur) if t != CASH)
                val *= 1 - slip * traded
                units = {t: val * w / px(t, d) for t, w in tgt.items() if px(t, d)}
        out.append([d, val])
    return out


def replay_check(entries, replay, as_of, fp=None):
    """Compare each logged decision before `as_of` with replay(day) -> decision dict on today's data and
    code (with fp given, only decisions logged under those same rules). Returns (checked, [differences])."""
    diffs, n = [], 0
    for e in entries:
        if e['d'] >= as_of or (fp is not None and e.get('fp') and e['fp'] != fp):
            continue
        r = replay(e['d'])
        if r is None:
            continue
        n += 1
        bad = []
        if r['mode'] != e['mode']:
            bad.append(f"mode {e['mode']} logged, {r['mode']} in the replay")
        if (r.get('half') or None) != (e.get('half') or None):
            bad.append(f"half {e.get('half')} logged, {r.get('half')} in the replay")
        if e['mode'] == 'boost' and r['mode'] == 'boost' and sorted(r['list']) != sorted(e['list']):
            bad.append(f"list {', '.join(e['list'])} logged, {', '.join(sorted(r['list']))} in the replay")
        if bad:
            diffs.append(dict(d=e['d'], what='; '.join(bad)))
    return n, diffs


def drop(curve):
    peak, worst = None, 0.0
    for _, v in curve:
        peak = v if peak is None else max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def status(curve, spy_px):
    """Where the record stands against the backtest's ranges: sessions so far, return, SPY over the same
    closes, worst drop, the band for the nearest horizon reached, and any warning."""
    if len(curve) < 2:
        return dict(sessions=max(0, len(curve) - 1), ret=0.0, spy=0.0, dd=0.0, band=None, flags=[])
    n = len(curve) - 1
    ret = curve[-1][1] / curve[0][1] - 1
    s0, s1 = spy_px.get(curve[0][0]), spy_px.get(curve[-1][0])
    spy = s1 / s0 - 1 if s0 and s1 else None
    dd = drop(curve)
    reached = [h for h in sorted(BANDS) if n >= h]
    band = reached[-1] if reached else None
    flags = []
    if dd < WORST_DD:
        flags.append(f"worst drop {dd:.0%} is deeper than the backtest's worst ({WORST_DD:.0%})")
    if band:
        b = BANDS[band]
        # judge the last `band` sessions, the window the range describes
        w = curve[-band - 1:]
        r_w = w[-1][1] / w[0][1] - 1
        sp0, sp1 = spy_px.get(w[0][0]), spy_px.get(w[-1][0])
        if r_w < b['p5']:
            flags.append(f"last {b['label']} {r_w:+.1%}, below the backtest's 1-in-20 floor ({b['p5']:+.1%})")
        if sp0 and sp1 and r_w - (sp1 / sp0 - 1) < b['lag10']:
            flags.append(f"last {b['label']} trail SPY by more than the 1-in-10 margin ({b['lag10'] * 100:+.1f} pts)")
    return dict(sessions=n, ret=ret, spy=spy, dd=dd, band=band, flags=flags)


def block(ledger, prices, calendar, k, spy_px, replay, fp):
    """The dashboard's paper-record payload at calendar[k]."""
    day = calendar[k]
    ent = ledger['entries']
    curve = account(ent, prices, calendar[:k + 1], ledger.get('slip', SLIP))
    n, diffs = replay_check(ent, replay, day, fp)
    base = curve[0][0] if curve else None
    spy = [[d, spy_px[d] / spy_px[base]] for d, _ in curve if base and spy_px.get(d) and spy_px.get(base)]
    known = {ledger['frozen']['fingerprint']} | {u['fingerprint'] for u in ledger.get('updates') or []}
    changed = sorted({e['d'] for e in ent if e.get('fp') and e['fp'] not in known})
    return dict(start=ledger['start'], frozen=ledger['frozen'], updates=ledger.get('updates') or [], fpNow=fp, rulesChanged=changed[:1],
                entries=len(ent), last=ent[-8:][::-1], curve=[[d, round(v, 5)] for d, v in curve],
                spy=[[d, round(v, 5)] for d, v in spy], checked=n, diffs=diffs[-10:],
                status=status(curve, spy_px), bands={str(h): b for h, b in BANDS.items()}, worstDD=WORST_DD)

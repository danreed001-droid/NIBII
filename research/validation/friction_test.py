"""Trading-cost stress test for a backtested plan.

Replays the plan's exact holdings schedule (same picks, same timing, same switches into gold or bonds) through the
engine's ledger with higher round-trip costs, and prints return a year and worst drop for each cost level. The
engine's default is 0.15% per side (0.30% round trip). It also finds the round-trip cost at which the plan would
only match SPY over the whole run.

The schedule comes from the engine itself: run scripts/improve.py with DUMP_SCHED=<key> (for the default,
DUMP_SCHED=NBup_boost); it writes data/sched_<key><TAG>.json in the engine folder.

usage:
  python research/validation/friction_test.py --engine <engine folder> --sched <sched json>
         [--costs 0.15,0.30,0.50,1,5,10] [--out friction.json]
"""
import argparse
import json
import os
import sys

import numpy as np

WINDOWS = [('Whole run', '0000', '9999'), ('2016-2020', '2015-12-31', '2020-12-31'),
           ('2021-2023', '2020-12-31', '2023-12-31'), ('2024 on', '2023-12-31', '9999')]


def stats(curve, a='0000', b='9999'):
    """Return a year and worst drop of an equity curve [(date, value)] between dates a (exclusive) and b."""
    v = np.array([y for x, y in curve if a <= x <= b], dtype=float)
    if len(v) < 2:
        return None, None
    r = v[1:] / v[:-1] - 1
    return float((v[-1] / v[0]) ** (252 / len(r)) - 1), float((v / np.maximum.accumulate(v) - 1).min())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--engine', required=True, help='engine folder (worktree with overlay applied)')
    ap.add_argument('--sched', required=True, help='sched_<key>.json written by improve.py with DUMP_SCHED')
    ap.add_argument('--costs', default='0.15,0.30,0.50,1,5,10', help='round-trip costs in percent')
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    os.environ.setdefault('START', '2000-01-03')
    os.environ.setdefault('FROM', '1998-06-01')
    sys.path[:0] = [os.path.join(a.engine, 'scripts'), a.engine]
    import robustness as R  # noqa: E402  (engine module)

    d = json.load(open(a.sched))
    sched, px = [tuple(x) for x in d['sched']], d['prices']
    cal = sorted(x for x in px['SPY'] if x >= sched[0][0])
    spy = [(x, px['SPY'][x]) for x in cal]
    out = {'SPY': {w[0]: stats(spy, w[1], w[2]) for w in WINDOWS}, 'costs': {}}
    print('| Round-trip cost | ' + ' | '.join(w[0] for w in WINDOWS) + ' |')
    print('|---|' + '---|' * len(WINDOWS))
    for c in (float(x) / 100 for x in a.costs.split(',')):
        res = R.simulate(sched, px, cal, c / 2, taxes=False)          # engine cost is per side
        row = {w[0]: stats(res['curve'], w[1], w[2]) for w in WINDOWS}
        row['turnover'] = res['turnover']
        out['costs'][f'{c * 100:.2f}%'] = row
        cells = ' | '.join(f"{row[w[0]][0] * 100:.1f}% ({row[w[0]][1] * 100:.0f}%)" for w in WINDOWS)
        print(f"| {c * 100:.2f}% | {cells} |")
    cells = ' | '.join(f"{out['SPY'][w[0]][0] * 100:.1f}% ({out['SPY'][w[0]][1] * 100:.0f}%)" for w in WINDOWS)
    print(f"| SPY | {cells} |")
    lo, hi = 0.0, 0.25                                               # break-even round trip vs SPY, whole run
    for _ in range(16):
        mid = (lo + hi) / 2
        cagr = stats(R.simulate(sched, px, cal, mid / 2, taxes=False)['curve'])[0]
        lo, hi = (mid, hi) if cagr > out['SPY']['Whole run'][0] else (lo, mid)
    out['breakEven'] = (lo + hi) / 2
    print(f"\nReturn a year (worst drop), before tax. Turnover about {out['costs'][next(iter(out['costs']))]['turnover']:.0f}x a year.")
    print(f"Break-even round-trip cost against SPY over the whole run: {out['breakEven'] * 100:.2f}%")
    if a.out:
        json.dump(out, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()

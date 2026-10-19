"""data/plan_history.json for the market events page from the backtest engine's schedule dump of the default plan
(DUMP_SCHED=NBup_boost in refresh.sh): what the plan held after each session's close, as shares of stocks, gold, bonds
and cash, kept only where it changed.

usage: python research/backtest/build_plan_history.py <sched_NBup_boost_track.json> <data/plan_history.json>"""
import json
import sys

KIND = {'GLDX': 'gold', 'TLTX': 'bonds', 'CASH0': 'cash', 'BIL': 'cash', 'CASH': 'cash'}
ORDER = ('stocks', 'gold', 'bonds', 'cash')
ABOUT = ('What the default plan held after each close in the point-in-time backtest (research/backtest/refresh.sh), '
         'as shares of stocks, gold, bonds and cash; a row stays in force until the next one. The market events page '
         'reads it, with the paper record (data/paper_ledger.json) after its end.')


def shares(w):
    out = dict.fromkeys(ORDER, 0.0)
    for t, x in w.items():
        out[KIND.get(t, 'stocks')] += x
    tot = sum(out.values()) or 1.0
    return [round(out[k] / tot, 2) for k in ORDER]


def build(sched, end):
    held, last = [], None
    for d, w in sorted(sched, key=lambda x: x[0]):
        row = shares(w)
        if row != last:
            held.append([d[:10], *row])
            last = row
    return dict(about=ABOUT, columns=['from close of', *ORDER], start=held[0][0] if held else None, end=end, held=held)


def main(src, dst):
    dump = json.load(open(src))
    spy = dump.get('prices', {}).get('SPY', {})
    end = max(spy)[:10] if spy else max(d for d, _ in dump['sched'])[:10]
    out = build(dump['sched'], end)
    with open(dst, 'w') as fh:
        json.dump(out, fh, separators=(',', ':'))
        fh.write('\n')
    print(f"plan history: {len(out['held'])} changes, {out['start']} to {out['end']}")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

"""data/plan_history.json for the market events page from the backtest engine's schedule dump of the default plan
(DUMP_SCHED=NBup_boost in refresh.sh): what the plan held after each session's close, as shares of stocks, gold, bonds,
cash and managed futures, kept only where it changed; and the daily closes of SPY and the gold and bond lines the backtest
used (TLT / GLD spliced onto a Treasury fund / gold futures before they existed), for the scanner page's
"Where the plan was" chart.

usage: python research/backtest/build_plan_history.py <sched_NBup_boost_track.json> <data/plan_history.json>"""
import json
import sys

KIND = {'GLDX': 'gold', 'TLTX': 'bonds', 'CASH0': 'cash', 'BIL': 'cash', 'CASH': 'cash', 'MFX': 'futures', 'DBMF': 'futures'}
ORDER = ('stocks', 'gold', 'bonds', 'cash', 'futures')
PRICES = (('SPY', 'SPY'), ('gold', 'GLDX'), ('bonds', 'TLTX'))   # name in the file -> the engine's ticker
ABOUT = ('What the default plan held after each close in the point-in-time backtest (research/backtest/refresh.sh), '
         'as shares of stocks, gold, bonds, cash and managed futures; a row stays in force until the next one. The market events page '
         'reads it, with the paper record (data/paper_ledger.json) after its end. prices: the daily closes of SPY and the '
         'gold and bond lines the backtest used, for the scanner page\'s "Where the plan was" chart.')


def shares(w):
    out = dict.fromkeys(ORDER, 0.0)
    for t, x in w.items():
        out[KIND.get(t, 'stocks')] += x
    tot = sum(out.values()) or 1.0
    return [round(out[k] / tot, 2) for k in ORDER]


def _sig(v, n=5):
    """v rounded to n significant digits (closes from about 20 to 800 keep 2-3 decimals)."""
    return float(f'{v:.{n}g}')


def price_block(prices, start, end):
    """{'dates': [...], 'SPY': [...], 'gold': [...], 'bonds': [...]}: the sessions from start to end with an SPY close,
    each line's close that day (None before a line starts). prices: {engine ticker: {date: close}}."""
    spy = prices.get('SPY') or {}
    dates = sorted(d[:10] for d, v in spy.items() if v and start <= d[:10] <= end)
    out = dict(dates=dates)
    for name, t in PRICES:
        px = {d[:10]: v for d, v in (prices.get(t) or {}).items() if v}
        out[name] = [_sig(px[d]) if d in px else None for d in dates]
    return out


def build(sched, end, prices=None):
    held, last = [], None
    for d, w in sorted(sched, key=lambda x: x[0]):
        row = shares(w)
        if row != last:
            held.append([d[:10], *row])
            last = row
    out = dict(about=ABOUT, columns=['from close of', *ORDER], start=held[0][0] if held else None, end=end, held=held)
    if prices and held:
        out['prices'] = price_block(prices, held[0][0], end)
    return out


def main(src, dst):
    dump = json.load(open(src))
    spy = dump.get('prices', {}).get('SPY', {})
    end = max(spy)[:10] if spy else max(d for d, _ in dump['sched'])[:10]
    out = build(dump['sched'], end, dump.get('prices'))
    with open(dst, 'w') as fh:
        json.dump(out, fh, separators=(',', ':'))
        fh.write('\n')
    print(f"plan history: {len(out['held'])} changes, {out['start']} to {out['end']}, "
          f"{len((out.get('prices') or {}).get('dates') or [])} days of SPY / gold / bond closes")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

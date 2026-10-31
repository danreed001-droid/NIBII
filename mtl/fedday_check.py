"""The Fed-day hold's probation check (information only; the rule itself is mtl/fedday.py). Each time the hold acts, it
is scored on the decision day: the plan's stocks against the haven it was about to move into, from the close the trade
would have happened at to the decision day's close. Live cases count from PROBATION_START; once FIRST of them are
scored, LOSE_LIMIT or more losses among them mean the rule should be reviewed for removal (the scanner logs an issue).
The backtest's own cases are shown alongside."""

PROBATION_START = '2026-11-02'
FIRST, LOSE_LIMIT = 4, 3


def scorecard(held, before, boost_curve, asset_px, calendar, since=PROBATION_START):
    """The hold's record. held: the decision closes it changed; before: {close: the mode the rules had chosen there
    (the haven)}; boost_curve: [[date, value]] of the stock list; asset_px: {asset: {date: close}}. Each case: the stock
    list's move and the haven's over the decision day (close after the held one -> the decision day's close) and
    whether waiting paid (won). Returns live cases (from `since`), the backtest's, and the verdict on the live ones."""
    bv, idx = dict(boost_curve), {d: i for i, d in enumerate(calendar)}

    def case(d):
        i, h = idx.get(d), before.get(d)
        row = dict(d=d, haven=h, decision=calendar[i + 2] if i is not None and i + 2 < len(calendar) else None)
        if i is None or i + 2 >= len(calendar):
            return row
        a, b = calendar[i + 1], calendar[i + 2]
        hp = (asset_px.get(h) or {})
        if not (bv.get(a) and bv.get(b)):
            return row
        hr = hp[b] / hp[a] - 1 if hp.get(a) and hp.get(b) else 0.0     # cash or no price: flat
        sr = bv[b] / bv[a] - 1
        row.update(stocks=round(sr, 5), havenRet=round(hr, 5), edge=round(sr - hr, 5), won=sr > hr)
        return row
    rows = [case(d) for d in sorted(held)]
    live = [r for r in rows if r['d'] >= since]
    past = [r for r in rows if r['d'] < since and 'won' in r]
    scored = [r for r in live if 'won' in r]
    first = scored[:FIRST]
    lost = sum(1 for r in first if not r['won'])
    verdict = ('review: remove' if len(first) == FIRST and lost >= LOSE_LIMIT else
               'keep' if len(first) == FIRST else 'too early')
    return dict(live=live, won=sum(1 for r in scored if r['won']), lost=sum(1 for r in scored if not r['won']),
                pending=len(live) - len(scored), verdict=verdict, first=FIRST, limit=LOSE_LIMIT, since=since,
                past=dict(n=len(past), won=sum(1 for r in past if r['won']),
                          avg=round(sum(r['edge'] for r in past) / len(past), 5) if past else None))


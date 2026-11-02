"""Hot-commodity buy skip (the default plan, from Nov 2, 2026, on probation): no new buy of a metals or energy stock while
its commodity has risen JUMP (50%) or more over the last LOOK sessions (6 months): copper for metals, steel, mining and
farm chemicals, crude oil for energy. A stock already held is kept; like the fading filter, the skipped stock's slot
stays in cash until it leaves the top 5 or the commodity cools, and the green light sets the skip aside.

Why: the plan buys the strongest stocks, and at the top of a commodity boom (2006, 2008, 2021) those are the miners,
steel makers and drillers, just before the commodity breaks. Part of the three-rule change of Nov 2, 2026 (with
mtl/nearhigh.py and mtl/jobwarn.py; see mtl/nearhigh.py for the strict-test figures); on its own it added 0.4 points a
year from 2000, nearly all of it in 2021: on probation.

Pure: industries {ticker: industry}, commodity closes {symbol: {date: close}}, a session calendar."""
import csv
import os
import re
from bisect import bisect_right

JUMP = 0.50
LOOK = 126
MIN_K = 252          # sessions of calendar before the skip can act (as the backtest)
START = '2026-11-02'
COPPER, OIL = 'HG=F', 'CL=F'
METALS = re.compile(r'Aluminum|Metal Mining|Precious Metals|Other Metals|Steel|Agricultural Chemicals|Nonmetallic Minerals')
ENERGY = re.compile(r'Oil|Coal Mining|Gas Production|Gas Transmission|Gas Field')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data', 'industries_all.csv')


def themes(path=PATH):
    """{ticker: commodity symbol} for the metals and energy stocks in data/industries_all.csv."""
    out = {}
    try:
        with open(path) as fh:
            for r in csv.DictReader(fh):
                ind = r.get('industry') or ''
                if METALS.search(ind):
                    out[r['symbol']] = COPPER
                elif ENERGY.search(ind):
                    out[r['symbol']] = OIL
    except OSError:
        pass
    return out


def onto(closes, calendar):
    """The last close on or before each session ([None] where none yet)."""
    ks = sorted(closes)
    out = []
    for d in calendar:
        j = bisect_right(ks, d) - 1
        out.append(closes[ks[j]] if j >= 0 else None)
    return out


class HotComm:
    def __init__(self, theme_of, comm_closes, calendar, jump=JUMP, look=LOOK):
        self.theme_of, self.jump, self.look = theme_of, jump, look
        self.cal = calendar
        self.series = {s: onto(comm_closes.get(s) or {}, calendar) for s in (COPPER, OIL)}

    def change(self, sym, k):
        a = self.series.get(sym) or []
        if k < MIN_K or k >= len(a) or a[k] is None or a[k - self.look] is None or a[k - self.look] <= 0:
            return None
        return a[k] / a[k - self.look] - 1

    def hot(self, sym, k):
        c = self.change(sym, k)
        return c is not None and c >= self.jump

    def blocked(self, t, k):
        """True when t is a metals / energy stock and its commodity is hot at close k."""
        s = self.theme_of.get(t)
        return bool(s) and self.hot(s, k)

    def buy_ok(self, prev=None):
        """buy_when(t, k) for mtl.momentum.run_momentum: prev(t, k) and not blocked."""
        return lambda t, k: (prev(t, k) if prev else True) and not self.blocked(t, k)

    def state(self, k):
        return {s: dict(change=round(self.change(s, k), 4) if self.change(s, k) is not None else None, hot=self.hot(s, k))
                for s in (COPPER, OIL)}

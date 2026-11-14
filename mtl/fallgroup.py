"""The falling stock-and-industry skip (rule 24 of the default plan, from Nov 14, 2026, on probation): no new buy of a
stock that is falling with its whole industry, unless it is at a low worth buying or has already turned.

The stock is skipped when all of these hold at the decision close:
- its daily chart makes lower highs and lower lows: of its swing highs (a session whose high is the highest of the W (3)
  sessions either side) in the last LOOK (120) sessions, the last is under the one before; the same for its swing lows;
- its industry (an equal-weight index of the stocks in the universe with the same industry, data/industries*.csv) does
  the same on its closes over the last LOOK sessions, and is down over the last DOWN (42) sessions;
and none of these:
- an extreme low: its 14-day RSI under RSI_LOW (30), or a close FAR (10%) or more under its 20-day average;
- the channel low: the day's low within CHAN (2%) above the line through its last two swing lows (or under it);
- a break of the down channel: a close over the line through its last two swing highs.
The next stock in the ranking is bought instead. Applied with the other buy filters.

Why: the owner's reading of the plan's losing buys (AMD 2001, NVDA 2022, CCL 2023) and of the ones that should still be
bought (RCL 2023, WFC 2009: bought at a low or after a break). Strict test (S&P 500 members as of each date, 0.15% a
side; Nov 14, 2026), with rule 23 (mtl/earnsell.py): see its AUDIT. Alone it was 62.0% vs 61.5% from 2000 with only 13
skips and a t-stat of 0.9, but together with rule 23 it was ahead in 15 years and behind in 2: on probation.

Pure: daily bars {ticker: [(date, open, high, low, close, ...)]}, closes {ticker: {date: close}} (the universe the
industry indexes are built from), industries {ticker: industry}, a session calendar."""
from mtl.backtest import rsi_series

W = 3
LOOK = 120
DOWN = 42
RSI_LOW = 30
FAR = 0.10
CHAN = 0.02
MIN_K = 260
START = '2026-11-14'


def pivots(a, k, look=LOOK, hi=True, w=W):
    """Swing highs (hi) or lows confirmed by session k: indexes in [k - look, k - w] whose value is the extreme of the
    w sessions either side (None anywhere in the window: not a swing)."""
    out = []
    for i in range(max(w, k - look), k - w + 1):
        win = a[i - w:i + w + 1]
        if a[i] is None or None in win:
            continue
        if a[i] == (max(win) if hi else min(win)):
            out.append(i)
    return out


def lower_both(highs, lows, k, look=LOOK):
    """(swing high indexes, swing low indexes) when the last two of each are both lower, else None."""
    ph, pl = pivots(highs, k, look, True), pivots(lows, k, look, False)
    if len(ph) < 2 or len(pl) < 2:
        return None
    if highs[ph[-1]] < highs[ph[-2]] and lows[pl[-1]] < lows[pl[-2]]:
        return ph, pl
    return None


def line_at(a, i, j, k):
    """The line through (i, a[i]) and (j, a[j]) at k."""
    return a[i] + (a[j] - a[i]) / (j - i) * (k - i)


def load_industries(root):
    """{ticker: industry} from data/industries.csv, then data/industries_all.csv for the rest."""
    import csv
    import os
    out = {}
    for fn in ('industries.csv', 'industries_all.csv'):
        p = os.path.join(root, 'data', fn)
        if os.path.exists(p):
            with open(p) as fh:
                for r in csv.DictReader(fh):
                    if r.get('symbol') and r.get('industry'):
                        out.setdefault(r['symbol'], r['industry'])
    return out


class FallGroup:
    def __init__(self, bars, prices, industries, calendar):
        self.bars, self.prices, self.ind, self.cal = bars or {}, prices or {}, industries or {}, calendar
        self.pos = {d: i for i, d in enumerate(calendar)}
        self._hlc, self._rsi, self._idx = {}, {}, None

    def hlc(self, t):
        """(highs, lows, closes) from the bars on the calendar, carried over a missing session."""
        if t not in self._hlc:
            n = len(self.cal)
            h, l, c = [None] * n, [None] * n, [None] * n
            for b in self.bars.get(t) or []:
                i = self.pos.get(str(b[0])[:10])
                if i is not None:
                    h[i], l[i], c[i] = b[2], b[3], b[4]
            for i in range(1, n):
                if h[i] is None:
                    h[i], l[i], c[i] = h[i - 1], l[i - 1], c[i - 1]
            self._hlc[t] = (h, l, c)
        return self._hlc[t]

    def _closes(self, t):
        px, out, last = self.prices.get(t) or {}, [], None
        for d in self.cal:
            v = px.get(d)
            last = v if v else last
            out.append(last)
        return out

    def rsi(self, t):
        if t not in self._rsi:
            c = self._closes(t)
            f = next((i for i, x in enumerate(c) if x), None)
            out = [None] * len(c)
            if f is not None:
                out[f:] = rsi_series(c[f:])
            self._rsi[t] = out
        return self._rsi[t]

    def index(self, group):
        """The industry's equal-weight index on the calendar (daily moves over 50% left out; flat where under 3 stocks)."""
        if self._idx is None:
            groups = {}
            for t in self.prices:
                g = self.ind.get(t)
                if g:
                    groups.setdefault(g, []).append(t)
            self._idx = {'_groups': groups}
        if group not in self._idx:
            n = len(self.cal)
            s, m = [0.0] * n, [0] * n
            for t in self._idx['_groups'].get(group, []):
                c = self._closes(t)
                for i in range(1, n):
                    if c[i] and c[i - 1]:          # a carried close counts as an unchanged day, as in the test
                        r = c[i] / c[i - 1] - 1
                        if abs(r) <= 0.5:
                            s[i] += r
                            m[i] += 1
            out, v = [], 1.0
            for i in range(n):
                v *= 1 + (s[i] / m[i] if m[i] >= 3 else 0.0)
                out.append(v)
            self._idx[group] = out if len(self._idx['_groups'].get(group, [])) >= 3 else None
        return self._idx[group]

    def reading(self, t, k):
        """dict(skip, why) at session k, or None when the stock isn't making lower highs and lower lows."""
        if k < MIN_K:
            return None
        h, l, c = self.hlc(t)
        if k >= len(c) or c[k] is None:
            return None
        lb = lower_both(h, l, k)
        if not lb:
            return None
        ph, pl = lb
        rs = self.rsi(t)[k]
        m20 = [x for x in c[k - 19:k + 1] if x is not None]
        if (rs is not None and rs < RSI_LOW) or (len(m20) == 20 and c[k] < sum(m20) / 20 * (1 - FAR)):
            return dict(skip=False, why='extreme low')
        if l[k] <= line_at(l, pl[-2], pl[-1], k) * (1 + CHAN):
            return dict(skip=False, why='channel low')
        if c[k] > line_at(h, ph[-2], ph[-1], k):
            return dict(skip=False, why='broke its down channel')
        ix = self.index(self.ind.get(t))
        if not ix:
            return dict(skip=False, why='no industry index')
        seg = ix[k - 130:k + 1]
        if lower_both(seg, seg, 130) is None:
            return dict(skip=False, why='industry not making lower lows')
        if not ix[k] < ix[k - DOWN]:
            return dict(skip=False, why='industry not down over 2 months')
        return dict(skip=True, why='falling with its industry')

    def blocked(self, t, k):
        r = self.reading(t, k)
        return bool(r and r['skip'])

    def buy_ok(self, prev=None):
        """buy_when(t, k) for mtl.momentum.run_momentum: prev(t, k) and not falling with its industry."""
        return lambda t, k: (prev(t, k) if prev else True) and not self.blocked(t, k)

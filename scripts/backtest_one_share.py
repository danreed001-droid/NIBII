#!/usr/bin/env python3
"""The top-5 rule holding ONE SHARE of each pick instead of equal dollars, since 2020.

Signals at Friday's close, trades at Monday's close (like the live page). A
pick is bought as 1 real share at that day's actual traded price (prices are
un-split-adjusted with each stock's split history) and held - still 1 share,
or whatever a split turned it into - until the rule sells it. When a sale
doesn't cover the next buy, the shortfall is new money put in; leftover cash
stays in the account. Reports money put in, what it grew to, and the dollar
P&L by year and by stock.

--capital N: instead, start with $N and at each Monday trade hold the most
WHOLE shares that fit in an equal fifth of the account (rounded down; the rest
stays in cash) - the realistic way to run it without fractional shares.

Usage:
    python scripts/backtest_one_share.py [start]                  # default 2020-01-02
    python scripts/backtest_one_share.py --capital 10000 [start]
"""
import os
import pickle
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_combined import load_extra  # noqa: E402
from backtest_momentum import BROKEN  # noqa: E402
from backtest_variants import load_data  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import ETFS, default_universe, load_added  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.splits.pkl')


def splits_for(tickers):
    """{ticker: [(date, ratio)]} from Yahoo, cached in data/.splits.pkl."""
    have = {}
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            have = pickle.load(f)
    need = [t for t in tickers if t not in have]
    if need:
        import yfinance as yf
        for t in need:
            try:
                s = yf.Ticker(t).splits
                have[t] = [(d.date().isoformat(), float(r)) for d, r in s.items() if r and r > 0]
            except Exception:
                have[t] = []
        with open(CACHE, 'wb') as f:
            pickle.dump(have, f)
    return {t: have.get(t, []) for t in tickers}


def main():
    args = [a for a in sys.argv[1:]]
    capital = None
    if '--capital' in args:
        i = args.index('--capital')
        capital = float(args[i + 1])
        del args[i:i + 2]
    start = args[0] if args else '2020-01-02'
    names = default_universe(refresh=False)
    raw, bench = load_data(list(names))
    extra = load_extra()
    added = load_added()
    sp = [t for t in names if t not in ETFS and t not in BROKEN and raw[t].get('daily')]
    bars = {t: raw[t]['daily'] for t in sp}
    bars.update(extra)
    px = {t: {b[0][:10]: b[4] for b in bs} for t, bs in bars.items()}
    px['SPY'] = dict(bench['SPY'])
    calendar = [d for d, _ in bench['SPY']]

    def member(t, d):
        return t in extra or added.get(t, '0000') <= d

    r = run_momentum(px, calendar, start, look=126, skip=21, top_n=5, eligible=member, exec_next='close')
    picks = r['picks']
    tickers = sorted({t for _, h in picks for t in h})
    print(f"fetching split history for {len(tickers)} stocks the rule held...", file=sys.stderr)
    spl = splits_for(tickers)

    def real(t, d):
        """Actual traded price on d: the split-adjusted close times every split after d."""
        f = 1.0
        for sd, ratio in spl[t]:
            if sd > d:
                f *= ratio
        return px[t][d] * f

    def last_close(t, d):
        while d not in px[t]:
            d = calendar[calendar.index(d) - 1]
        return px[t][d]

    if capital:
        return whole_shares(capital, picks, calendar, px, real, last_close)
    held = {}                 # ticker -> (buy date, real buy price, adj buy close)
    cash, put_in = 0.0, 0.0
    trades, pnl_year, pnl_stock = [], defaultdict(float), defaultdict(float)
    curve = []
    pick_at = {d: h for d, h in picks}
    for d in calendar:
        if d < picks[0][0]:
            continue
        if d in pick_at:
            target = pick_at[d]
            for t in [t for t in held if t not in target]:
                bd, bp, ba = held.pop(t)
                sell = bp * last_close(t, d) / ba          # 1 original share, split-proof
                cash += sell
                pnl = sell - bp
                pnl_year[d[:4]] += pnl
                pnl_stock[t] += pnl
                trades.append((d, 'sell', t, sell, pnl))
            for t in [t for t in target if t not in held]:
                bp = real(t, d)
                if cash < bp:
                    put_in += bp - cash
                    cash = bp
                cash -= bp
                held[t] = (d, bp, px[t][d])
                trades.append((d, 'buy', t, bp, None))
        val = cash + sum(bp * last_close(t, d) / ba for t, (bd, bp, ba) in held.items())
        curve.append((d, val, put_in))
    end = calendar[-1]
    for t, (bd, bp, ba) in held.items():   # unrealized P&L on what's still held
        pnl = bp * last_close(t, end) / ba - bp
        pnl_year[end[:4]] += pnl
        pnl_stock[t] += pnl
    final, deposits = curve[-1][1], curve[-1][2]
    first_cost = sum(bp for d, s, t, bp, _ in trades if d == picks[0][0] and s == 'buy')
    print(f"\nTop 5, ONE SHARE of each pick, {picks[0][0]} -> {end} (Monday-close trades, no costs)\n")
    print(f"  first 5 shares cost        ${first_cost:12,.2f}   ({', '.join(t for t in pick_at[picks[0][0]])})")
    print(f"  total money put in         ${deposits:12,.2f}   (first buy + any shortfalls when a new pick cost more)")
    print(f"  account value now          ${final:12,.2f}")
    print(f"  profit                     ${final - deposits:12,.2f}   ({final / deposits - 1:+.0%} on the money put in)")
    print(f"  trades                     {sum(1 for x in trades if x[1] == 'buy')} buys, {sum(1 for x in trades if x[1] == 'sell')} sells")
    peak, dd, dd_at = 0, 0, None
    for d, v, dep in curve:
        gain = v - dep
        if gain > peak:
            peak = gain
        if gain - peak < dd:
            dd, dd_at = gain - peak, d
    print(f"  worst fall in profit       ${dd:12,.2f}   (from the high-water mark, low on {dd_at})")
    print("\n  Year    profit/loss     money put in by year end   account value at year end")
    ye = {}
    for d, v, dep in curve:
        ye[d[:4]] = (v, dep)
    for y in sorted(pnl_year):
        print(f"  {y}   ${pnl_year[y]:12,.2f}   ${ye[y][1]:12,.2f}              ${ye[y][0]:12,.2f}")
    print("\n  Holding now (1 share each, actual price today):")
    for t, (bd, bp, ba) in sorted(held.items()):
        now = bp * last_close(t, end) / ba
        print(f"    {t:6} bought {bd} at ${bp:9,.2f}  ->  ${now:9,.2f}  ({now / bp - 1:+.0%})")
    cost_now = sum(real(t, end) for t in held)
    print(f"    cost to buy 1 share of each today: ${cost_now:,.2f}")
    best = sorted(pnl_stock.items(), key=lambda x: -x[1])
    print("\n  Biggest winners: " + ', '.join(f"{t} ${v:,.0f}" for t, v in best[:6]))
    print("  Biggest losers:  " + ', '.join(f"{t} ${v:,.0f}" for t, v in best[-5:][::-1]))


def whole_shares(capital, picks, calendar, px, real, last_close):
    """Start with `capital`; at each Monday trade hold floor(account / 5 / price) shares of each pick."""
    pick_at = {d: h for d, h in picks}
    shares, cash, curve, idle = {}, capital, [], []
    ref = {}                               # ticker -> (real price, adj close) at the last trade, to follow splits

    def price(t, d):
        rp, ra = ref[t]
        return rp * last_close(t, d) / ra

    for d in calendar:
        if d < picks[0][0]:
            continue
        if d in pick_at:
            for t in list(shares):         # mark to today's actual price, then rebuild the five slots
                cash += shares.pop(t) * price(t, d)
            for t in pick_at[d]:
                ref[t] = (real(t, d), px[t][d])
            slot = cash / 5
            for t in pick_at[d]:
                n = int(slot // ref[t][0])
                if n:
                    shares[t] = n
                    cash -= n * ref[t][0]
        val = cash + sum(n * price(t, d) for t, n in shares.items())
        curve.append((d, val))
        idle.append(cash / val if val else 0)
    end = calendar[-1]
    peak, dd = 0, 0
    for _, v in curve:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    years = {}
    for d, v in curve:
        years.setdefault(d[:4], [v, v])[1] = v
    print(f"\nTop 5, ${capital:,.0f} start, WHOLE shares (equal fifths, rounded down), {picks[0][0]} -> {end}\n")
    print(f"  account value now   ${curve[-1][1]:14,.2f}   ({curve[-1][1] / capital - 1:+,.0%})")
    print(f"  worst drop          {dd:.0%}")
    print(f"  cash left idle      {sum(idle) / len(idle):.1%} of the account on average (rounding to whole shares)")
    print("\n  Year   start of year      end of year     return")
    prev = capital
    for y in sorted(years):
        print(f"  {y}  ${prev:14,.2f}  ${years[y][1]:14,.2f}   {years[y][1] / prev - 1:+.0%}")
        prev = years[y][1]
    print("\n  Holding now:")
    for t, n in sorted(shares.items()):
        print(f"    {t:6} {n:5} sh x ${price(t, end):9,.2f} = ${n * price(t, end):12,.2f}")
    print(f"    cash  ${cash:,.2f}")


if __name__ == '__main__':
    main()

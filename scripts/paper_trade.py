#!/usr/bin/env python3
"""Paper-trade the Top 5 Strongest rule from a start date with a fixed dollar
amount per stock, valued hour by hour.

Selection is exactly the dashboard's rule (scripts/momentum_scan.py): S&P 500
+ Nasdaq-100 ranked by 6-1 month return, must beat SPY, top 5, a holding stays
while it ranks in the top 10, changes only at the Friday close - plus an
initial buy at the start date's close. Money is handled the way a person
would: buy $PER_STOCK of each, and when one is sold its whole value goes into
its replacement (winners are not trimmed back). Positions are marked on the
1-hour chart; buys and sells fill at that day's closing price. No trading costs.

Usage:
    python scripts/paper_trade.py                         # from 2026-09-01, $100 a stock
    python scripts/paper_trade.py --start 2026-08-03 --per-stock 1000
    python scripts/paper_trade.py --start 2026-01-01 --end 2026-03-31   # a past window
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from momentum_scan import LOOK, SKIP, TOP_N, blocked_dates, fetch  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402
from mtl.universe import load_added, load_sp500, momentum_universe  # noqa: E402


def hourly(tickers, start, end):
    """{ticker: [(datetime_iso, close)]} on the 1h chart from `start` to `end`
    (Yahoo keeps about two years of hourly bars)."""
    import yfinance as yf
    df = yf.download(tickers, interval='60m', period='730d', group_by='ticker', auto_adjust=False,
                     progress=False, threads=True)
    out = {}
    for t in tickers:
        d = df[t].dropna(subset=['Close']) if len(tickers) > 1 else df.dropna(subset=['Close'])
        out[t] = [(ts.isoformat(), float(c)) for ts, c in zip(d.index, d['Close'])
                  if start <= ts.date().isoformat() <= end]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--start', default='2026-09-01')
    ap.add_argument('--per-stock', type=float, default=100.0)
    ap.add_argument('--end', default='9999-12-31', help='value the account at this date\'s close (default: latest)')
    args = ap.parse_args()

    names = momentum_universe(refresh=False)
    sp, added = load_sp500(), load_added()
    print(f"Fetching daily history for {len(names)} stocks...", file=sys.stderr)
    bars = fetch(sorted(names), start='2025-01-01')
    bench = fetch(['SPY', 'QQQ'], start='2025-01-01', adjusted=True)
    bars = {t: [b for b in bs if b[0] <= args.end] for t, bs in bars.items()}
    bench = {t: [b for b in bs if b[0] <= args.end] for t, bs in bench.items()}
    prices = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items() if bs}
    prices['SPY'] = {b[0]: b[4] for b in bench['SPY']}
    calendar = [b[0] for b in bench['SPY']]
    blocked = {t: blocked_dates(bs) for t, bs in bars.items()}

    def eligible(t, d):
        return d not in blocked.get(t, ()) and (t not in sp or added.get(t, '0000') <= d)

    r = run_momentum(prices, calendar, args.start, look=LOOK, skip=SKIP, top_n=TOP_N, eligible=eligible,
                     cost=0.0, rebalance_on_start=True)
    picks = r['picks']

    # dollars: $per-stock each at the start; a sale's proceeds buy its replacement
    shares, trades, cash = {}, [], 0.0
    for i, (d, held) in enumerate(picks):
        if i == 0:
            for t in held:
                shares[t] = args.per_stock / prices[t][d]
                trades.append((d, 'buy', t, prices[t][d], args.per_stock))
            continue
        sold = [t for t in shares if t not in held]
        bought = [t for t in held if t not in shares]
        for t in sold:
            v = shares.pop(t) * prices[t][d]
            cash += v
            trades.append((d, 'sell', t, prices[t][d], v))
        for t in bought:
            v = cash / len(bought) if bought else 0
            shares[t] = v / prices[t][d]
            trades.append((d, 'buy', t, prices[t][d], v))
        if bought:
            cash = 0.0

    # hour-by-hour value of the real share counts
    involved = sorted({t for _, h in picks for t in h})
    hr = hourly(involved + ['SPY', 'QQQ'], args.start, calendar[-1])
    timeline = sorted({ts for t in involved for ts, _ in hr[t]})
    holding_at = []   # share map in force at each hour (changes take effect after the rebalance day's close)
    sh_state, last_px = {}, {}
    events = sorted({d for d, *_ in trades})
    ledger = {d: [x for x in trades if x[0] == d] for d in events}
    sh_hist = {}
    cur = {}
    for d in events:
        for _, side, t, px, v in ledger[d]:
            if side == 'sell':
                cur.pop(t, None)
            else:
                cur[t] = v / px
        sh_hist[d] = dict(cur)
    values = []
    for ts in timeline:
        day = ts[:10]
        active = [d for d in events if d < day or (d == day and ts[11:16] >= '15:30')]
        if not active:
            continue
        sh_state = sh_hist[active[-1]]
        for t in involved:
            for x_ts, px in hr[t]:
                if x_ts == ts:
                    last_px[t] = px
        if all(t in last_px for t in sh_state):
            values.append((ts, cash + sum(n * last_px[t] for t, n in sh_state.items())))

    start_value = args.per_stock * TOP_N
    for t in shares:          # a holding without a close on the last day carries its last price
        prices[t].setdefault(calendar[-1], prices[t][max(d for d in prices[t] if d <= calendar[-1])])
    final = cash + sum(n * prices[t][calendar[-1]] for t, n in shares.items())
    print(f"\nStarted {args.start} with ${start_value:,.0f} (${args.per_stock:,.0f} in each of {TOP_N}); "
          f"valued at the {calendar[-1]} close\n")
    print("Trades (filled at that day's close):")
    for d, side, t, px, v in trades:
        print(f"  {d}  {side:4}  {t:5} {names.get(t, ('', ''))[0][:26]:26} at ${px:9,.2f}   ${v:8,.2f}")
    print("\nHoldings now:")
    for t, n in sorted(shares.items(), key=lambda x: -x[1] * prices[x[0]][calendar[-1]]):
        px = prices[t][calendar[-1]]
        print(f"  {t:5} {n:9.4f} sh x ${px:9,.2f} = ${n * px:8,.2f}")
    print(f"\nValue now: ${final:,.2f}  ({final / start_value - 1:+.1%})")
    for b in ('SPY', 'QQQ'):
        d0, p0 = next((x[0], x[4]) for x in bench[b] if x[0] >= args.start)
        p1 = bench[b][-1][4]
        print(f"  same ${start_value:,.0f} in {b} (bought {d0} close): ${start_value * p1 / p0:,.2f} ({p1 / p0 - 1:+.1%})")
    if values:
        peak, dd, lo, hi = values[0][1], 0.0, min(values, key=lambda x: x[1]), max(values, key=lambda x: x[1])
        for _, v in values:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1)
        print(f"\nHour by hour: low ${lo[1]:,.2f} ({lo[0][:16]}), high ${hi[1]:,.2f} ({hi[0][:16]}), "
              f"worst dip from a high {dd:.1%}")
        print("Each Friday close:")
        for ts, v in values:
            if datetime.fromisoformat(ts).weekday() == 4 and ts[11:16] == '15:30':
                print(f"  {ts[:10]}  ${v:8,.2f}")


if __name__ == '__main__':
    main()

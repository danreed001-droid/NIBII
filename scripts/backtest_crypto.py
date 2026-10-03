#!/usr/bin/env python3
"""The top-N momentum rule on crypto only.

Universe: about 45 large coins on Yahoo Finance, including ones that collapsed
(LUNA, FTT, EOS, ...) so the test isn't only today's survivors - though it
still misses coins Yahoo no longer lists. A coin is eligible once it has a
year of history. Crypto trades every day, so windows are in calendar days:
6 months = 182 days, skip the latest 30. Signal at Sunday's close (end of the
ISO week), trade at Monday's close. A coin must beat BTC over the same
window. 0.25% cost per trade (crypto fees run higher than stocks).
Optional trend filter: all cash while BTC is below its 200-day average.

Usage:
    python scripts/backtest_crypto.py
"""
import os
import pickle
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.backtest import curve_stats  # noqa: E402
from mtl.momentum import run_momentum  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'data', '.crypto.pkl')
COINS = ['BTC', 'ETH', 'XRP', 'BNB', 'SOL', 'ADA', 'DOGE', 'TRX', 'AVAX', 'DOT', 'LINK', 'LTC', 'BCH', 'XLM',
         'ATOM', 'ETC', 'XMR', 'ALGO', 'VET', 'FIL', 'HBAR', 'ICP', 'NEAR', 'UNI7083', 'AAVE', 'SHIB', 'MATIC',
         'APT21794', 'ARB11841', 'SUI20947', 'INJ', 'RNDR', 'GRT6719', 'SAND', 'MANA', 'AXS', 'THETA', 'XTZ',
         'EOS', 'NEO', 'IOTA', 'DASH', 'ZEC', 'BSV', 'CRO', 'LUNA1', 'FTT', 'KSM', 'CAKE', 'QNT']
START, TEST = '2018-01-01', '2020-01-06'


def load():
    if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 24 * 3600:
        with open(CACHE, 'rb') as f:
            return pickle.load(f)
    import yfinance as yf
    syms = [c + '-USD' for c in COINS]
    df = yf.download(syms, start=START, interval='1d', group_by='ticker', auto_adjust=True, progress=False, threads=True)
    out = {}
    for s in syms:
        try:
            d = df[s].dropna(subset=['Close'])
        except KeyError:
            continue
        if len(d) > 400:
            out[s.replace('-USD', '').rstrip('0123456789')] = {ts.date().isoformat(): float(c) for ts, c in zip(d.index, d['Close']) if c > 0}
    with open(CACHE, 'wb') as f:
        pickle.dump(out, f)
    return out


def glitches(px):
    """Days to skip a coin: within 60 days after a one-day move beyond +300% / -80% (bad prints, redenominations)."""
    out, ds, last = set(), sorted(px), -10 ** 9
    for i in range(1, len(ds)):
        r = px[ds[i]] / px[ds[i - 1]] - 1
        if r > 3 or r < -0.8:
            last = i
        if i - last <= 60:
            out.add(ds[i])
    return out


def main():
    px = load()
    cal = sorted(px['BTC'])
    first = {t: min(p) for t, p in px.items()}
    bad = {t: glitches(p) for t, p in px.items()}
    print(f"{len(px)} coins with data: {', '.join(sorted(px))}\n", file=sys.stderr)

    back = {d: cal[max(0, i - 365)] for i, d in enumerate(cal)}

    def eligible(t, d):
        return d not in bad[t] and first[t] <= back[d]

    btc = [px['BTC'][d] for d in cal]
    trend = {cal[i]: btc[i] > sum(btc[i - 199:i + 1]) / 200 for i in range(199, len(cal))}
    prices = dict(px)
    prices['_BENCH'] = px['BTC']

    def run(top, look, skip, filt=False, bench='_BENCH'):
        r = run_momentum(prices, cal, TEST, benchmark=bench, look=look, skip=skip, top_n=top, eligible=eligible,
                         cost=0.0025, exec_next='close',
                         risk_on=(lambda d: trend.get(d, True)) if filt else None, risk_daily=filt)
        return r

    def line(label, c):
        f = curve_stats([p[1] for p in c])
        yrs = {}
        for d, v in c:
            yrs.setdefault(d[:4], [v, v])[1] = v
        prev, ys = c[0][1], []
        for y in sorted(yrs):
            ys.append(f"{yrs[y][1] / prev - 1:+6.0%}")
            prev = yrs[y][1]
        print(f"{label:40} {f['total']:+9.0%} {f['annual']:+6.0%} {f['maxDD']:6.0%} | " + ' '.join(ys))

    years = sorted({d[:4] for d in cal if d >= TEST})
    print(f"{'since ' + TEST:40} {'total':>9} {'/yr':>6} {'worst':>6} | " + ' '.join(f"{y:>6}" for y in years))
    for top in (3, 5):
        for look, skip, name in ((182, 30, '6-1m'), (91, 0, '3m'), (365, 30, '12-1m')):
            r = run(top, look, skip)
            line(f"top {top}, {name}", [p[:2] for p in r['curve']])
    r = run(3, 182, 30, filt=True)
    line("top 3, 6-1m, cash when BTC < 200-day", [p[:2] for p in r['curve']])
    r = run(5, 182, 30, filt=True)
    line("top 5, 6-1m, cash when BTC < 200-day", [p[:2] for p in r['curve']])
    for coin in ('BTC', 'ETH'):   # the coin itself, held only while BTC is above its 200-day average
        c, v, prev = [], 1.0, None
        for d in cal:
            if d < TEST or d not in px[coin]:
                continue
            if prev and trend.get(prev, True):
                v *= px[coin][d] / px[coin][prev] * (1 - 0.0025 * (not trend.get(cal[cal.index(prev) - 1], True)))
            c.append([d, v])
            prev = d
        line(f"{coin} only while BTC > 200-day", c)
    for coin in ('BTC', 'ETH', 'XRP', 'SOL'):
        c = [[d, px[coin][d]] for d in cal if d >= TEST and d in px[coin]]
        line(f"buy & hold {coin}" + (' (from ' + c[0][0] + ')' if c[0][0] > TEST else ''), c)
    r = run(3, 182, 30)
    print("\nTop 3 (6-1m) holdings, last few weeks:")
    for d, h in r['picks'][-4:]:
        print(f"  {d}: {', '.join(h) or 'cash'}")


if __name__ == '__main__':
    main()

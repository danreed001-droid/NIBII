"""Side series the backtest engine reads, rebuilt from Yahoo Finance up to today, into the folder given as argv[1]:

xasset.json    {ticker: {date: close}}             cross-asset closes (gold, rates, dollar, VIX, credit, breadth)
vix_irx.json   {'^VIX': {date: close}, '^IRX': ...} VIX and the 13-week T-bill yield
rates/tnx.json {'^TNX': [[date, o, h, l, c], ...]}  10-year Treasury yield
spliced.json   {name: [[date, o, h, l, c], ...]}    funds extended back with an older stand-in, scaled to meet the fund
               on its first day: TLTX = Vanguard long Treasury fund (VUSTX) then TLT; GLDX = gold futures then GLD;
               UUPX = dollar index then UUP; FXYX = 1 / USDJPY then FXY; DBCX = S&P GSCI then DBC; USOX = crude
               futures then USO. DBMF = the managed-futures fund alone, from May 2019 (no stand-in: the default plan
               holds it instead of cash only on days it has a price, as live).
narrow_warn.json [date, ...]                        the narrow-market warning days (mtl/narrow.py) from SPY, the
               equal-weight S&P 500 (RSP) and the VIX over their full history (RSP from May 2003), so the
               warning also fires in 2006-07, as it would have live. The Oct 2026 audit read them from 2007 on and
               missed those three cash weeks (two cost money in 2006, the Oct 2007 one caught the top); with
               them the default made about 0.5 points a year less from 2000.
"""
import json
import os
import sys

import yfinance as yf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from mtl.narrow import narrow_warnings  # noqa: E402

START = '1998-01-01'
XASSET = ['CL=F', 'DX-Y.NYB', 'GC=F', 'GLD', 'HG=F', 'HYG', 'IEF', 'IWM', 'LQD', 'RSP', 'SPY', 'TLT', 'XLK', 'XLU',
          '^FVX', '^IRX', '^TNX', '^VIX']


def bars(t, adjusted=True):
    """[[date, open, high, low, close], ...] oldest first, rows with no close dropped."""
    df = yf.download(t, start=START, auto_adjust=adjusted, progress=False)
    if df is None or df.empty:
        raise SystemExit(f'no data for {t}')
    col = lambda c: df[c][df[c].columns[0]] if hasattr(df[c], 'columns') else df[c]
    o, h, l, c = col('Open'), col('High'), col('Low'), col('Close')
    out = []
    for ts in df.index:
        v = [float(o.loc[ts]), float(h.loc[ts]), float(l.loc[ts]), float(c.loc[ts])]
        if v[3] == v[3] and v[3] > 0:
            out.append([ts.date().isoformat()] + v)
    return out


def splice(proxy, fund):
    """proxy bars before the fund's first day, scaled so the two meet; then the fund."""
    first = fund[0][0]
    anchor = [b for b in proxy if b[0] <= first][-1]
    k = fund[0][4] / anchor[4]
    return [[b[0]] + [x * k for x in b[1:5]] for b in proxy if b[0] < first] + [b[:5] for b in fund]


def inverse(proxy, fund):
    """A currency fund extended back with 1 / an exchange rate (USDJPY -> yen), scaled to meet the fund."""
    first = fund[0][0]
    anchor = [b for b in proxy if b[0] <= first][-1]
    k = fund[0][4] * anchor[4]
    pre = [[b[0], k / b[1], k / b[3], k / b[2], k / b[4]] for b in proxy if b[0] < first and b[1] and b[2] and b[3]]
    return pre + [b[:5] for b in fund]


def main(out):
    os.makedirs(os.path.join(out, 'rates'), exist_ok=True)
    closes = lambda bs: {b[0]: b[4] for b in bs}
    xa = {t: closes(bars(t, adjusted=not t.startswith('^'))) for t in XASSET}
    json.dump(xa, open(os.path.join(out, 'xasset.json'), 'w'))
    json.dump({'^VIX': xa['^VIX'], '^IRX': xa['^IRX']}, open(os.path.join(out, 'vix_irx.json'), 'w'))
    json.dump({'^TNX': bars('^TNX', adjusted=False)}, open(os.path.join(out, 'rates', 'tnx.json'), 'w'))
    nw = narrow_warnings(xa['SPY'], xa['RSP'], xa['^VIX'], sorted(xa['SPY']))
    json.dump(nw, open(os.path.join(out, 'narrow_warn.json'), 'w'))
    sp = {'TLTX': splice(bars('VUSTX'), bars('TLT')), 'GLDX': splice(bars('GC=F'), bars('GLD')),
          'UUPX': splice(bars('DX-Y.NYB'), bars('UUP')), 'FXYX': inverse(bars('JPY=X'), bars('FXY')),
          'DBCX': splice(bars('^SPGSCI'), bars('DBC')), 'USOX': splice(bars('CL=F'), bars('USO')),
          'DBMF': [b[:5] for b in bars('DBMF')]}
    json.dump(sp, open(os.path.join(out, 'spliced.json'), 'w'))
    for k, v in sp.items():
        print(k, v[0][0], v[-1][0], len(v))
    print('xasset through', max(xa['SPY']), '· VIX through', max(xa['^VIX']), f'· {len(nw)} narrow-market warning days, last', nw[-1] if nw else None)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'side')

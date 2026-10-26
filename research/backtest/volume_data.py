"""Daily volumes the backtest engine reads, from Yahoo Finance, into the folder given as argv[2]:

stock_volume.npz  tickers (every ticker in the engine's dataset argv[1]), dates (every date any of them traded),
                  vol[ticker, date] as float32, NaN where there is no volume (or Yahoo reports 0)
spy_volume.json   {'SPY': {date: volume}, 'QQQ': {...}}

usage: python research/backtest/volume_data.py <engine/data/.robust_1998-06-01.pkl> <side folder>"""
import json
import os
import pickle
import sys
import time

import numpy as np
import yfinance as yf

START = '1998-06-01'


def volumes(tickers):
    out = {}
    for k in range(0, len(tickers), 80):
        part = tickers[k:k + 80]
        df = None
        for attempt in range(3):
            try:
                df = yf.download(part, interval='1d', start=START, group_by='ticker', auto_adjust=False, threads=True,
                                 progress=False)
                break
            except Exception as e:   # noqa: BLE001
                print('retry', k, e, flush=True)
                time.sleep(5)
        for t in part:
            try:
                v = df[t]['Volume'].dropna()
            except (KeyError, TypeError):
                continue
            out[t] = {i.date().isoformat(): int(x) for i, x in v.items() if x == x}
        print(f'volume {k + len(part)}/{len(tickers)}, {len(out)} found', flush=True)
    return out


def main(dataset, side):
    os.makedirs(side, exist_ok=True)
    data = pickle.load(open(dataset, 'rb'))
    tickers = sorted(data['bars'])
    extra = data.get('extra_vol', {})   # members Yahoo no longer carries (membership.py)
    V = volumes([t for t in tickers if t not in extra])
    V.update({t: v for t, v in extra.items() if v})
    dates = sorted({d for v in V.values() for d in v})
    di = {d: j for j, d in enumerate(dates)}
    M = np.full((len(tickers), len(dates)), np.nan, dtype=np.float32)
    for i, t in enumerate(tickers):
        for d, x in V.get(t, {}).items():
            if x:
                M[i, di[d]] = x
    np.savez_compressed(os.path.join(side, 'stock_volume.npz'), tickers=np.array(tickers), dates=np.array(dates), vol=M)
    B = volumes(['SPY', 'QQQ'])
    json.dump({t: B[t] for t in ('SPY', 'QQQ')}, open(os.path.join(side, 'spy_volume.json'), 'w'))
    print(f'stock volumes: {sum(1 for t in tickers if V.get(t))} of {len(tickers)} tickers, through {dates[-1]}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

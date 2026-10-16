"""mtl/fade.py - the fading-energy filter - and run_momentum's buy_max_rank (a skipped top-5 stock leaves cash)."""
import math

import pandas as pd

from mtl import fade
from mtl.momentum import run_momentum

CAL = [d.date().isoformat() for d in pd.bdate_range('2024-01-01', periods=420)]


def wave(n, amp, vol_last=1.0, amp_last=None, drift=0.001):
    """closes with daily moves of +/-amp (amp_last over the last 21 sessions) and volumes 1e6 (vol_last x over the last 21)"""
    px, vol, p = {}, {}, 100.0
    for i, d in enumerate(CAL[:n]):
        a = amp_last if amp_last is not None and i >= n - 21 else amp
        p *= math.exp(drift + (a if i % 2 else -a))
        px[d] = p
        vol[d] = 1e6 * (vol_last if i >= n - 21 else 1.0)
    return px, vol


def test_fading_needs_both_quiet_volume_and_small_swings():
    k = 400
    cases = {'BOTH': wave(k + 1, 0.02, 0.5, 0.005), 'VOLONLY': wave(k + 1, 0.02, 0.5), 'SWINGONLY': wave(k + 1, 0.02, 1.0, 0.005),
             'NONE': wave(k + 1, 0.02)}
    prices = {t: c[0] for t, c in cases.items()}
    vols = {t: c[1] for t, c in cases.items()}
    f = fade.fading(prices, vols, CAL)
    assert f('BOTH', k) and not f('VOLONLY', k) and not f('SWINGONLY', k) and not f('NONE', k)
    vr, sr = fade.ratios(prices, vols, CAL, 'BOTH', k)
    assert abs(vr - 0.5) < 1e-9 and sr < 0.3
    assert not f('BOTH', 100)                                      # too little history: never flagged
    assert fade.ratios(prices, {}, CAL, 'BOTH', k)[0] is None      # no volume data: not flagged


def test_skipped_top_stock_leaves_cash_with_buy_max_rank():
    # five stocks rising at different speeds; 'S1' (the strongest) is refused by buy_when
    prices = {'SPY': {d: 100.0 * (1.0002 ** i) for i, d in enumerate(CAL)}}
    for j in range(1, 8):
        prices[f'S{j}'] = {d: 50.0 * ((1 + 0.004 - 0.0004 * j) ** i) for i, d in enumerate(CAL)}
    no_s1 = lambda t, k: t != 'S1'
    base = run_momentum(prices, CAL, CAL[200], top_n=5, buy_when=no_s1, exec_next='close')
    held = base['picks'][-1][1]
    assert 'S1' not in held and len(held) == 5 and 'S6' in held   # the next-ranked stock fills the slot
    capped = run_momentum(prices, CAL, CAL[200], top_n=5, buy_when=no_s1, buy_max_rank=5, exec_next='close')
    held = capped['picks'][-1][1]
    assert 'S1' not in held and len(held) == 4 and 'S6' not in held  # ...or the slot stays in cash

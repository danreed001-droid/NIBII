"""Option simulation pieces - synthetic data, no network."""
import math
from datetime import date, timedelta

from mtl.options_sim import bs_call, bs_delta, simulate, strike_for_delta


def test_black_scholes_textbook_value_and_put_call_sense():
    # S=100, K=100, T=1, vol=20%, r=5% -> 10.45 (textbook)
    assert abs(bs_call(100, 100, 1.0, 0.2, 0.05) - 10.4506) < 1e-3
    assert bs_call(100, 50, 0.5, 0.3, 0.04) > 50 and bs_call(100, 150, 0.5, 0.3, 0.04) < 5


def test_strike_for_delta_hits_the_target():
    k = strike_for_delta(100, 0.5, 0.4, 0.04, 0.75)
    assert k < 100 and abs(bs_delta(100, k, 0.5, 0.4, 0.04) - 0.75) < 1e-6


def _cal(n):
    d0, out, d = date(2024, 1, 1), [], 0
    while len(out) < n:
        day = d0 + timedelta(days=d)
        if day.weekday() < 5:
            out.append(day.isoformat())
        d += 1
    return out


def test_stock_mode_tracks_shares_and_calls_amplify_a_rise():
    c = _cal(200)
    closes = {'A': {d: 100 * 1.003 ** i * (1 + 0.01 * math.sin(i)) for i, d in enumerate(c)}}
    picks = [[c[70], ['A']]]
    stock = simulate(picks, closes, c, start_value=100, n=1, mode='stock')
    assert abs(stock['curve'][-1][1] - 100 * closes['A'][c[-1]] / closes['A'][c[70]]) < 1e-6
    lev = simulate(picks, closes, c, start_value=100, n=1, mode='all_in')
    eq = simulate(picks, closes, c, start_value=100, n=1, mode='equiv')
    gain = stock['curve'][-1][1] - 100
    assert lev['curve'][-1][1] - 100 > 2 * gain           # leverage on a rise
    assert 0.5 * gain < eq['curve'][-1][1] - 100 < 1.3 * gain   # roughly stock-like
    assert lev['rolls'] >= 1                               # 6-month contract rolled before expiry


def test_all_in_calls_lose_more_than_stock_on_a_fall_but_equiv_is_capped():
    c = _cal(200)
    closes = {'A': {d: 100 * 0.995 ** i for i, d in enumerate(c)}}
    picks = [[c[70], ['A']]]
    stock = simulate(picks, closes, c, start_value=100, n=1, mode='stock')['curve'][-1][1]
    lev = simulate(picks, closes, c, start_value=100, n=1, mode='all_in')['curve'][-1][1]
    eq = simulate(picks, closes, c, start_value=100, n=1, mode='equiv')['curve'][-1][1]
    assert lev < stock < 100 and eq > lev

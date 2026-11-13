"""The crash-call watch list (mtl/crashcalls.py): on only when SPY is 20%+ under its 1-year high; oversold stocks listed."""
import random

from mtl import crashcalls


def _market(crash):
    cal = [f"2020-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    spy = {d: 300 * (0.7 if crash and '2020-03' <= d < '2020-05' else 1.0) for d in cal}
    px = {'SPY': spy}
    random.seed(1)
    for t in ('AAA', 'BBB', 'CCC'):
        v, ser = 100.0, {}
        for d in cal:
            v *= 1 + random.gauss(-0.004 if t == 'AAA' and d >= '2020-03' else 0.0005, 0.02)
            ser[d] = v
        px[t] = ser
    return cal, px


def test_on_in_a_crash_lists_oversold_stocks():
    cal, px = _market(True)
    W = crashcalls.watch(px, cal, lambda t, d: True, cal.index('2020-04-20'))
    assert W['on'] and W['dd'] <= -0.2
    assert [r['t'] for r in W['rows']] == ['AAA'] and all(r['rsi'] <= 30 for r in W['rows'])


def test_off_near_the_high_keeps_no_list():
    cal, px = _market(False)
    W = crashcalls.watch(px, cal, lambda t, d: True)
    assert not W['on'] and W['rows'] == [] and len(W['near']) == 3
    assert W['near'] == sorted(W['near'], key=lambda r: r['rsi'])


def test_ineligible_stocks_are_left_out():
    cal, px = _market(True)
    W = crashcalls.watch(px, cal, lambda t, d: t != 'AAA', cal.index('2020-04-20'))
    assert all(r['t'] != 'AAA' for r in W['rows'] + W['near'])


def test_normal_market_lists_big_winners_turned_oversold():
    cal = [f"2021-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
    px = {'SPY': {d: 400.0 for d in cal}}
    up = {}
    for i, d in enumerate(cal):           # doubles over the year, then a sharp two-week dip
        up[d] = 50 * (3.0 ** (i / len(cal))) * (0.85 if i >= len(cal) - 10 else 1.0)
    px['WIN'] = up
    px['FLAT'] = {d: 100.0 + (i % 3) for i, d in enumerate(cal)}
    W = crashcalls.watch(px, cal, lambda t, d: True)
    assert not W['on'] and W['normal']['on']
    assert [r['t'] for r in W['normal']['rows']] == ['WIN']
    r = W['normal']['rows'][0]
    assert r['up'] >= 0.8 and r['rsi'] <= 41

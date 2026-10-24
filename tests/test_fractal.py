"""mtl/fractal.py - the default plan's two-scale buy rules: buy freeze and green light."""
import numpy as np
import pandas as pd

from mtl import fractal as fz
from mtl import paper
from mtl.rotation import Reader

CAL = [d.date().isoformat() for d in pd.bdate_range('2022-01-03', periods=700)]


def walk(seed, drift=0.0, vol=0.012):
    c = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(drift, vol, len(CAL))))
    return [(d, x, x * 1.004, x * 0.996, x) for d, x in zip(CAL, c.tolist())]


SPY = walk(3)


def test_windows_follow_the_signals_read_at_week_ends():
    frozen, green, log = fz.spy_windows(SPY, CAL, CAL[200])
    assert log, 'a 700-session random walk should give at least one signal'
    R = Reader({'SPY': SPY})
    ix = {d: i for i, d in enumerate(CAL)}
    for d, kind in log:
        k = ix[d]
        assert fz._week_end(CAL, k)
        r = fz.spy_reading(R, d, SPY[k][4])
        assert r[kind]
        win = frozen if kind == 'freeze' else green
        assert set(range(k + 1, k + 1 + (fz.FZ_DAYS if kind == 'freeze' else fz.GL_DAYS))) <= win
    # every frozen session comes from a freeze signal in the 10 sessions before it
    fk = {ix[d] for d, kind in log if kind == 'freeze'}
    assert all(any(j - fz.FZ_DAYS <= k < j for k in fk) for j in frozen)


def test_freeze_needs_the_daily_lower_high_too():
    R = Reader({'SPY': SPY})
    for k in range(250, len(CAL), 5):
        d = CAL[k]
        r = fz.spy_reading(R, d, SPY[k][4])
        if r['freeze']:
            assert r['dHigh'][1][1] < r['dHigh'][0][1] and r['wHigh'][1][1] < r['wHigh'][0][1]
        if r['green']:
            assert r['dLow'][1][1] > r['dLow'][0][1] and r['wLow'][1][1] > r['wLow'][0][1]


def test_buy_rule_order():
    base = lambda t, k: t != 'FADED'
    ok = fz.buy_rule(base, frozen={5}, green={7})
    assert ok('A', 4) and not ok('FADED', 4)                  # outside both: the fading filter decides
    assert not ok('A', 5)                                       # buy freeze: no new stock
    assert ok('FADED', 7)                                       # green light: the fading filter stands aside
    assert fz.buy_rule(base, frozen={9}, green={9})('A', 9)     # the green light overrides a freeze
    assert fz.buy_rule(None, frozen=set(), green=set())('A', 3)


def test_slot_haven_holds_the_pick_only_for_slots_emptied_in_a_freeze():
    cal = CAL[:30]
    stock = [[d, 100.0] for d in cal]                          # the stock part flat
    gld = {d: 100.0 * 1.01 ** i for i, d in enumerate(cal)}    # the haven up 1% a session
    picks = [[cal[2], ['A', 'B', 'C', 'D', 'E']], [cal[10], ['A', 'B', 'C', 'D']], [cal[20], ['A', 'B', 'C', 'D', 'E']]]
    out = fz.slot_haven(stock, picks, frozen={10}, closes={'GLD': gld}, calendar=cal, start=cal[0], pick=lambda k: 'GLD', cost=0.0)
    g = out[20][1] / out[10][1] - 1
    assert abs(g - 0.2 * (1.01 ** 10 - 1)) < 0.002              # a fifth in GLD from that trade to the next
    assert out[10][1] == 100.0 and abs(out[29][1] - out[20][1]) < 1e-9
    same = fz.slot_haven(stock, picks, frozen={5}, closes={'GLD': gld}, calendar=cal, start=cal[0], pick=lambda k: 'GLD')
    assert [v for _, v in same] == [v for _, v in stock]       # no trade inside the freeze: nothing changes
    cash = fz.slot_haven(stock, picks, frozen={10}, closes={'GLD': gld}, calendar=cal, start=cal[0], pick=lambda k: 'CASH')
    assert [v for _, v in cash] == [v for _, v in stock]


def test_paper_weights_put_the_empty_slot_in_the_haven_pick():
    w = paper.weights('boost', None, ['A', 'B', 'C', 'D'], 'GLD')
    assert w == {'A': 0.2, 'B': 0.2, 'C': 0.2, 'D': 0.2, 'GLD': 0.2} or abs(w['GLD'] - 0.2) < 1e-9
    assert paper.weights('boost', None, ['A', 'B', 'C', 'D'])['CASH'] > 0.199
    assert 'GLD' not in paper.decision('2026-10-26', 'boost', None, ['A', 'B', 'C', 'D', 'E'], 'GLD')['w']


def test_state_reports_the_next_session():
    frozen, green, log = fz.spy_windows(SPY, CAL, CAL[200])
    k = min(frozen) - 1
    st = fz.state(SPY, CAL, k, frozen, green, log)
    assert st['frozen'] and st['frozenFor'] >= 1 and st['fzDays'] == fz.FZ_DAYS

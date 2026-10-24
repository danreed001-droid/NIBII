"""mtl/pricebreak.py - the default plan's price-break haven rule: SPY breaks its 100-day average with both averages falling."""
import numpy as np
import pandas as pd

from mtl import pricebreak as pb

CAL = [d.date().isoformat() for d in pd.bdate_range('2024-01-01', periods=400)]
# a seeded random walk: it has a first close under the 100-day average with both averages falling on day 374
SPY = (100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0.0, 0.012, 400)))).tolist()
PX = dict(zip(CAL, SPY))


def first_break():
    days = sorted(pb.break_days(PX, CAL, CAL[0]))
    return days[0] if days else None


def test_break_day_needs_a_first_close_under_with_both_averages_falling():
    d = first_break()
    assert d == CAL[374]
    k = CAL.index(d)
    r = pb.reading([PX[x] for x in CAL], k)
    assert r['brk'] and r['below'] and r['down']
    prev = pb.reading([PX[x] for x in CAL], k - 1)
    assert not prev['below'] or not prev['down']          # not already under (and falling) the day before


def test_no_break_in_a_steady_uptrend_or_before_enough_history():
    up = {d: 100 + i for i, d in enumerate(CAL)}
    assert pb.break_days(up, CAL, CAL[0]) == set()
    assert pb.reading([100.0] * 50, 40) is None


def test_hold_days_run_the_break_day_and_ten_sessions_after():
    d = first_break()
    held = pb.hold_days({d}, CAL, CAL[0])
    k = CAL.index(d)
    assert held == set(CAL[k:k + pb.PB_HOLD + 1]) and len(held) == 11


def havens(tlt_up=0.05):
    tlt = [100 * (1 + tlt_up * i / 399) for i in range(400)]
    return {'TLT': dict(zip(CAL, tlt)), 'GLD': {d: 50.0 for d in CAL}, 'DBMF': {d: 10.0 for d in CAL}}


def test_apply_swaps_stock_days_for_the_haven_pick_and_leaves_haven_days_alone():
    d = first_break()
    k = CAL.index(d)
    modes = {x: 'boost' for x in CAL[k - 2:k + 15]}
    modes[CAL[k + 3]] = 'GLD'                       # the plan is already in a haven on one of those days
    days = pb.hold_days({d}, CAL, CAL[0])
    m, w, h, held = pb.apply_pricebreak(modes, {}, {CAL[k + 1]: 'GLD'}, days, havens(), CAL)
    assert m[CAL[k - 1]] == 'boost' and m[d] == 'TLT' and m[CAL[k + 10]] == 'TLT' and m[CAL[k + 11]] == 'boost'
    assert m[CAL[k + 3]] == 'GLD' and CAL[k + 3] not in held        # unchanged: not the rule's doing
    assert held == days - {CAL[k + 3]} and w[d] == 'pricebreak' and CAL[k + 1] not in h
    assert w[CAL[k + 11]] == 'pricebreak-end'


def test_haven_pick_is_dbmf_when_neither_bond_nor_gold_is_up():
    d = first_break()
    k = CAL.index(d)
    flat = havens(tlt_up=-0.02)
    m, *_ = pb.apply_pricebreak({x: 'boost' for x in CAL[k:k + 3]}, {}, {}, {d}, flat, CAL)
    assert m[d] == 'DBMF'


def test_state_reports_active_and_the_last_stretch():
    d = first_break()
    k = CAL.index(d)
    days = pb.hold_days({d}, CAL, CAL[0])
    _, _, _, held = pb.apply_pricebreak({x: 'boost' for x in CAL[k:k + 12]}, {}, {}, days, havens(), CAL)
    st = pb.pricebreak_state(PX, CAL, k + 2, held)
    assert st['active'] and st['log'] == [[d, CAL[k + 10]]] and st['n'] == 1 and st['slow_n'] == 100
    assert not pb.pricebreak_state(PX, CAL, k + 20, held)['active']

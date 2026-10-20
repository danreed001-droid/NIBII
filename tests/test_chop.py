"""Choppy-market watch: counts the default plan's whole-account moves in the last 40 sessions."""
from mtl.chop import holding, moves, watch


def cal(n):
    return [f"2026-01-{i + 1:02d}" if i < 31 else f"2026-02-{i - 30:02d}" for i in range(n)]


def test_holding_reads_the_whipsaw_pick_while_in_stocks():
    assert holding({'d': 'boost'}, {'d': 'GLD'}, 'd') == 'GLD'
    assert holding({'d': 'boost'}, {}, 'd') == 'boost'
    assert holding({'d': 'TLT'}, {'d': 'GLD'}, 'd') == 'TLT'     # out of stocks: the rotation's asset


def test_moves_lists_each_change_once():
    c = cal(6)
    modes = {d: 'boost' for d in c}
    modes[c[2]] = modes[c[3]] = 'TLT'
    half = {c[5]: 'GLD'}
    assert moves(modes, half, c, 5) == [(c[2], 'boost', 'TLT'), (c[4], 'TLT', 'boost'), (c[5], 'boost', 'GLD')]


def test_watch_turns_on_at_the_third_move_and_off_when_one_ages_out():
    c = cal(50)
    modes = {d: 'boost' for d in c}
    modes[c[5]] = 'TLT'          # boost → TLT (5), TLT → boost (6), boost → GLD (10)
    for i in range(10, 50):
        modes[c[i]] = 'GLD'
    w = watch(modes, {}, c, 9, look=40, need=3)
    assert not w['on'] and w['n'] == 2
    w = watch(modes, {}, c, 10, look=40, need=3)
    assert w['on'] and not w['prevOn'] and w['n'] == 3 and w['since'] == c[10]
    assert w['moves'] == [[c[5], 'boost', 'TLT'], [c[6], 'TLT', 'boost'], [c[10], 'boost', 'GLD']]
    w = watch(modes, {}, c, 45, look=40, need=3)     # the close-5 move left the window at close 45
    assert not w['on'] and w['prevOn'] and w['n'] == 2
    assert w['spells'] == [[c[10], c[44]]] and w['daysOn'] == 35

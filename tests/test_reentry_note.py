"""Re-entry note (mtl/reentry_note.py): back into stocks after 10+ sessions out, the list's sectors by the fund each
stock tracked, and which kind of re-entry it is."""
import math

from mtl import reentry_note as R


def sessions(n):
    return [f'2026-{1 + i // 28:02d}-{1 + i % 28:02d}' for i in range(n)]


def test_concentrated_reentry_is_named_with_its_sector():
    cal = sessions(300)
    wave = lambda ph: {d: 100 * math.exp(0.02 * math.sin(i / 3 + ph) + 0.0001 * i) for i, d in enumerate(cal)}
    funds = {'XLK': wave(0.0), 'XLE': wave(2.0), 'XLF': wave(4.0)}
    prices = {'A': wave(0.05), 'B': wave(0.1), 'C': wave(-0.05), 'D': wave(2.05), 'E': wave(4.1)}
    modes = {d: ('GLD' if 280 <= i < 295 else 'boost') for i, d in enumerate(cal)}
    picks = [[cal[200], ['A', 'B', 'C', 'D', 'E']]]
    n = R.note(modes, cal, 297, picks, prices, funds)
    assert n['show'] and n['d'] == cal[295] and n['ago'] == 2
    assert n['kind'] == 'concentrated' and n['most'] == 3 and n['mostIn'] == 'tech' and n['sectors']['D'] == 'energy'


def test_no_note_without_a_reentry_or_long_after_one():
    cal = sessions(300)
    modes = {d: ('GLD' if 250 <= i < 270 else 'boost') for i, d in enumerate(cal)}
    assert R.note(modes, cal, 299, [], {}, {}) == dict(show=False)           # 29 sessions on
    short = {d: ('GLD' if 290 <= i < 295 else 'boost') for i, d in enumerate(cal)}
    assert R.reentry_day(short, cal, 297) is None                             # only 5 sessions out

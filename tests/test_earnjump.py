import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import earnjump, volweight  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_volweight import _cal, _universe  # noqa: E402


def test_reaction_session_follows_the_report_time():
    cal = ['2026-07-29', '2026-07-30', '2026-07-31', '2026-08-03']
    assert earnjump.reaction_sessions([['2026-07-30', 'bmo']], cal) == [1]
    assert earnjump.reaction_sessions([['2026-07-30', 'amc']], cal) == [2]
    assert earnjump.reaction_sessions([['2026-08-01', 'amc']], cal) == [3]     # a weekend date: the next session


def test_jump_within_the_window_doubles_the_money():
    cal = _cal(300)
    px = {d: 100.0 for d in cal}
    px[cal[250]] = 104.0                      # +4% on the reaction day
    for d in cal[251:]:
        px[d] = 104.0
    ej = earnjump.EarnJump({'A': px, 'B': {d: 100.0 for d in cal}}, {'A': [[cal[250], 'bmo']], 'B': [[cal[250], 'bmo']]})
    assert ej.hit('A', cal, 299) and not ej.hit('B', cal, 299)
    assert ej.factor('A', cal, 299) == 2.0 and ej.factor('A', cal, 249) == 1.0
    info = ej.info('A', cal, 299)
    assert info['d'] == cal[250] and info['ago'] == 49 and abs(info['move'] - 0.04) < 1e-9
    ej_far = earnjump.EarnJump({'A': px}, {'A': [[cal[200], 'bmo']]})
    assert not ej_far.hit('A', cal, 299)      # outside the 63-session window


def test_both_rules_multiply():
    cal, prices, volumes = _universe()
    ej = earnjump.EarnJump(prices, {'S44': [[cal[280], 'bmo']]})
    prices['S44'][cal[280]] = prices['S44'][cal[279]] * 1.05      # S44 also jumped on its report
    vw = volweight.VolWeight(prices, volumes, lambda t, d: True, top_n=5, extra=ej)
    w = vw.weights(['S0', 'S1', 'S44', 'S43', 'S2'], cal, 299)
    assert abs(w['S44'] - 4 / 9) < 1e-9 and abs(w['S43'] - 2 / 9) < 1e-9 and abs(w['S0'] - 1 / 9) < 1e-9
    card = vw.card(['S44'], cal, 299)
    assert card['stocks'][0]['earn']['hit']


def test_merge_and_yahoo_times():
    dates = {'A': [['2026-07-30', 'bmo']]}
    rows = earnjump.from_yahoo(['2026-10-29 16:05:00-04:00', '2026-07-30 07:00:00-04:00', '2027-01-28 16:00:00-05:00'], '2026-10-31')
    assert rows == [['2026-10-29', 'amc'], ['2026-07-30', 'bmo']]
    assert earnjump.merge(dates, 'A', rows) == 1 and dates['A'] == [['2026-07-30', 'bmo'], ['2026-10-29', 'amc']]

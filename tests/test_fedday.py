"""Fed-day hold (mtl/fedday.py): a move out of stocks whose trade would land just before a scheduled Fed decision day
waits one session; it never moves the account into stocks."""
from mtl import fedday as F

CAL = ['2026-12-03', '2026-12-04', '2026-12-07', '2026-12-08', '2026-12-09', '2026-12-10']
FED = ['2026-12-09']


def test_an_exit_traded_just_before_the_decision_waits_one_session():
    modes = {'2026-12-07': 'TLT', '2026-12-08': 'TLT', '2026-12-09': 'TLT'}
    m, w, h, held = F.apply_fedday(modes, {'2026-12-07': 'exit'}, {'2026-12-07': 'GLD'}, FED, CAL)
    assert held == {'2026-12-07'} and m['2026-12-07'] == 'boost' and m['2026-12-08'] == 'TLT'
    assert w['2026-12-07'] == 'fedday' and w['2026-12-08'] == 'exit' and '2026-12-07' not in h


def test_other_days_and_moves_into_stocks_are_left_alone():
    early = {'2026-12-04': 'TLT', '2026-12-07': 'TLT'}               # trade on Dec 7, two sessions before: no hold
    assert F.apply_fedday(early, {}, {}, FED, CAL)[3] == set()
    stay_out = {'2026-12-04': 'TLT', '2026-12-07': 'TLT', '2026-12-08': 'boost'}
    m, _, _, held = F.apply_fedday(stay_out, {}, {}, FED, CAL)     # already out: nothing to hold
    assert held == set() and m == stay_out
    assert F.apply_fedday({'2026-12-07': 'TLT'}, {}, {}, [], CAL)[3] == set()


def test_tonight_on_a_live_run_uses_the_upcoming_sessions():
    cal = CAL[:3]                                                     # tonight = Dec 7
    m, _, _, held = F.apply_fedday({'2026-12-07': 'GLD'}, {}, {}, FED, cal, upcoming=['2026-12-08', '2026-12-09'])
    assert held == {'2026-12-07'} and m['2026-12-07'] == 'boost'
    st = F.fedday_state(FED, cal, 2, ['2026-12-08', '2026-12-09'], held)
    assert st['active'] and st['watch'] and st['next'] == '2026-12-09' and not st['covered']


def test_schedule_version_moves_the_trade_to_the_decision_day():
    sc = [('2026-12-03', {'AAA': 0.2, 'BBB': 0.8}), ('2026-12-08', {'TLTX': 1.0}), ('2026-12-10', {'AAA': 1.0})]
    out, held = F.apply_to_schedule(sc, FED, CAL)
    assert held == ['2026-12-08'] and out[1] == ('2026-12-08', sc[0][1]) and out[2] == ('2026-12-09', {'TLTX': 1.0})


def test_the_date_list_is_scheduled_meetings_and_runs_ahead():
    fed = F.load()
    assert len([d for d in fed if d.startswith('2024')]) == 8 and '2025-08-22' not in fed
    assert F.covered(fed, '2026-10-31') and F.next_decision(fed, '2026-10-31') == '2026-12-09'

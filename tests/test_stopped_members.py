import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import momentum_scan as M  # noqa: E402

CAL = ['2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03']


def _bars(last):
    return [(d, 1, 1, 1, 1) for d in CAL if d <= last]


def test_a_member_with_no_close_for_2_sessions_counts_as_stopped():
    bars = {'KVUE': _bars('2026-10-30'), 'AAPL': _bars('2026-11-03'), 'LATE': _bars('2026-11-02'), 'XNOT': _bars('2026-10-29')}
    st = M.stopped_members(bars, {'KVUE': 1, 'AAPL': 1, 'LATE': 1}, CAL)
    assert st == {'KVUE': '2026-10-30'}               # one missed session is not enough; non-members are ignored


def test_the_page_line_says_when_a_holding_stopped():
    lines = M.stopped_problems({'KVUE': '2026-10-30'}, ['KVUE', 'DELL'], CAL)
    assert lines and lines[0].startswith('HELD stock KVUE') and 'broker' in lines[0]
    other = M.stopped_problems({'KVUE': '2026-10-30'}, ['DELL'], CAL)
    assert 'KVUE (last close 2026-10-30)' in other[0] and 'Left out of the ranking' in other[0]
    assert M.stopped_problems({}, ['DELL'], CAL) == []

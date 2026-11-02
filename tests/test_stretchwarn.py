import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import stretchwarn as sw  # noqa: E402


def _cal(n, start=date(2020, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_weekly_z_is_high_after_a_late_surge_and_holds_between_weeks():
    cal = _cal(400)
    px = {d: 100 * 1.0005 ** i for i, d in enumerate(cal)}
    for i, d in enumerate(cal[-10:]):
        px[d] *= 1 + 0.03 * (i + 1)          # a sharp run-up in the last two weeks
    zs = sw.weekly_z(px, cal)
    assert zs[cal[-1]] > 2
    mid = cal[300]
    assert cal[200] not in zs and mid in zs and abs(zs[mid]) < 2.5    # 52 weeks needed first
    # a Wednesday carries the reading of the week before it
    wed = next(d for d in cal[300:] if date.fromisoformat(d).weekday() == 2)
    fri = max(d for d in cal if d < wed and date.fromisoformat(d).weekday() == 4)
    assert zs[wed] == zs[fri]


def test_onsets_need_both_and_count_only_the_first_close():
    cal = _cal(10)
    counts = {d: 3 for d in cal}
    zs = {d: (2.5 if 2 <= i <= 5 or i == 8 else 0.0) for i, d in enumerate(cal)}
    assert sw.onsets(cal, counts, zs) == [cal[2], cal[8]]
    counts[cal[8]] = sw.K - 1
    assert sw.onsets(cal, counts, zs) == [cal[2]]


def test_out_days_only_from_a_start_in_stocks_and_only_on_stock_days():
    cal = _cal(30)
    stocks = set(cal) - {cal[3], cal[12]}
    out = sw.out_days(cal, [cal[0], cal[12]], lambda d: d in stocks, hold=5)
    assert out == {cal[0], cal[1], cal[2], cal[4]}       # the start at cal[12] was not in stocks; cal[3] already out


def test_state_reports_a_running_spell_and_apply_moves_to_the_haven():
    cal = _cal(40)
    counts = {d: 4 for d in cal}
    zs = {d: (2.2 if i >= 25 else 0.0) for i, d in enumerate(cal)}
    starts = sw.onsets(cal, counts, zs)
    assert starts == [cal[25]]
    days = sw.out_days(cal, starts, lambda d: True)
    modes = {d: 'boost' for d in cal}
    m, w, h, held = sw.apply_stretchwarn(modes, {}, {cal[26]: 'GLD'}, days, cal)
    assert m[cal[25]] == 'BIL' and m[cal[24]] == 'boost' and w[cal[25]] == 'stretchwarn' and cal[26] not in h
    assert held == set(cal[25:40])
    st = sw.state(cal, 30, counts, zs, held, starts)
    assert st['active'] and st['since'] == cal[25] and st['left'] == 14 and st['count'] == 4 and st['z'] == 2.2
    assert st['warn'] and st['stretched'] and st['log'] == [[cal[25], cal[39]]]
    st2 = sw.state(cal, 20, counts, zs, set(), starts)
    assert not st2['active'] and st2['since'] is None and not st2['stretched']


def test_warn_counts_read_fred_dominoes_a_session_late():
    cal = _cal(300)
    flat = {d: 100.0 for d in cal}
    ser = {'tech': flat, 'small': flat, 'banks': flat, 'transport': flat, 'junk': flat,
           'fed': {d: 1.0 for d in cal}, 'curve': {d: 1.0 for d in cal},
           'oil': {d: (100.0 if i < 299 else 200.0) for i, d in enumerate(cal)}}
    ser['oil'][cal[0]] = 50.0
    for i, d in enumerate(cal[:260]):
        ser['oil'][d] = 50.0
    ser['oil'][cal[-2]] = 50.0 * 1.2
    ser['oil'][cal[-1]] = 50.0 * 2.0          # a 100% jump on the last day only
    c = sw.warn_counts(cal, ser)
    assert c[cal[-1]] == 0                    # oil is read one session late
    c0 = sw.warn_counts(cal, ser, fred_lag=0)
    assert c0[cal[-1]] == 1

"""mtl/reentry.py - the default plan's break re-entry rule."""
import pandas as pd

from mtl import reentry as re_

CAL = [d.date().isoformat() for d in pd.bdate_range('2021-01-04', periods=520)]


def path():
    """A run-up to 400 sessions, a 25% fall in lower highs, then a recovery that breaks out on quiet volume."""
    px, v = [], []
    for k in range(len(CAL)):
        if k < 300:
            x = 100 + k * 0.1 + (2 if k % 20 == 10 else 0)
        elif k < 380:
            j = k - 300
            x = 130 - j * 0.4 + (4 if j % 16 == 8 else 0)          # falling with bounces: lower highs
        else:
            j = k - 380
            x = 98 + j * 1.2 + (3 if j % 16 == 8 else 0)          # a quick turn
        px.append(x)
        v.append(1000 if k < 360 else 600)                          # volume dries up into the turn
    return dict(zip(CAL, px)), dict(zip(CAL, v))


def test_breaks_need_a_lower_high_and_a_prior_drop():
    c, v = path()
    r = re_.readings(c, v, CAL)
    for k in r['weekly'] + r['dailyAll']:
        assert r['deep'][k]
    for k in r['daily']:
        assert k in r['dailyAll'] and r['fade'][k] < re_.RE_FADE


def test_the_path_fires_once_where_both_breaks_meet():
    c, v = path()
    r = re_.readings(c, v, CAL)
    assert len(re_.signals(r)) == 1 and r['weekly'] and r['daily']


def test_signal_timing_and_spacing():
    r = dict(deep=[True] * 300, weekly=[100, 200], daily=[90, 150, 230])
    assert re_.signals(r) == [100]                        # 200 / 230: 30 sessions apart, too far; 150 has no weekly break
    r = dict(deep=[True] * 300, weekly=[100, 115], daily=[95, 110])
    assert re_.signals(r) == [100]                        # the later hits inside the window don't start a new signal


def test_signals_need_both_breaks_within_the_window():
    c, v = path()
    r = re_.readings(c, v, CAL)
    for k in re_.signals(r):
        near_w = any(abs(k - i) < re_.RE_WIN and i <= k for i in r['weekly'])
        near_d = any(abs(k - i) < re_.RE_WIN and i <= k for i in r['daily'])
        assert near_w and near_d
    ks = re_.signals(r)
    assert all(b - a > re_.RE_WIN for a, b in zip(ks, ks[1:]))


def test_no_signal_on_loud_volume():
    c, v = path()
    loud = {d: 1000 for d in CAL}
    assert re_.signals(re_.readings(c, loud, CAL)) == []
    assert re_.readings(c, loud, CAL)['daily'] == []
    assert re_.readings(c, v, CAL)['weekly'] == re_.readings(c, loud, CAL)['weekly']


def test_days_cover_the_hold_and_apply_overrides():
    c, v = path()
    days, sig = re_.reentry_days(c, v, CAL, CAL[0])
    ix = {d: i for i, d in enumerate(CAL)}
    for d in sig:
        assert {CAL[j] for j in range(ix[d], min(len(CAL), ix[d] + re_.RE_HOLD))} <= days
    modes = {d: ('GLD' if i % 2 else 'boost') for i, d in enumerate(CAL)}
    half = {d: 'TLT' for d in CAL[::3]}
    m, w, h, held = re_.apply_reentry(modes, {}, half, days, CAL)
    assert all(m[d] == 'boost' and d not in h for d in days)
    assert held == {d for d in days if modes[d] != 'boost' or d in half}
    assert all(m[d] == modes[d] for d in CAL if d not in days)


def test_an_open_week_does_not_count_as_a_week_close():
    c, v = path()
    a = re_.readings(c, v, CAL, last_is_end=True)
    b = re_.readings(c, v, CAL, last_is_end=False)
    assert [k for k in a['weekly'] if k < len(CAL) - 15] == [k for k in b['weekly'] if k < len(CAL) - 15]


def test_state_reports_signals_and_hold():
    c, v = path()
    days, sig = re_.reentry_days(c, v, CAL, CAL[0])
    held = set(days)
    k = CAL.index(sig[0]) + 3 if sig else len(CAL) - 1
    st = re_.reentry_state(c, v, CAL, k, held, sig)
    assert st['hold'] == re_.RE_HOLD and st['win'] == re_.RE_WIN
    if sig:
        assert st['left'] == re_.RE_HOLD - 1 - 3 and st['onNext'] and st['active']

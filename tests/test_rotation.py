"""Boost + rotation: structure reads, the mode schedule and the curve."""
import math
from datetime import date, timedelta

from mtl.rotation import Reader, rotation_curve, rotation_modes, switch_log, weekly


def days(n, start='2020-01-06'):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def zigzag(cal, drift, amp=0.04, period=12, base=100.0):
    """Bars that swing up and down around a steady drift (per session)."""
    out = []
    for i, d in enumerate(cal):
        c = base * math.exp(drift * i + amp * math.sin(2 * math.pi * i / period))
        out.append((d, c, c * 1.002, c * 0.998, c))
    return out


def test_weekly_bars_are_dated_by_their_last_session():
    cal = days(10)
    wk = weekly(zigzag(cal, 0.0))
    assert [w[0] for w in wk] == ['2020-01-10', '2020-01-17']


def test_reader_trend_and_gradient_sign():
    cal = days(300)
    R = Reader({'UP': zigzag(cal, 0.003), 'DN': zigzag(cal, -0.003)})
    up, dn = R.leg('UP', cal[-1]), R.leg('DN', cal[-1])
    assert up[0] == 'uptrend' and up[1] > 0
    assert dn[0] == 'downtrend' and dn[1] < 0
    assert R.steepest(cal[-1], ('UP', 'DN')) == 'UP'


def test_rotates_into_the_rising_asset_after_the_confirmation_wait():
    cal = days(400)
    bars = {'SPY': zigzag(cal, 0.002)[:200] + zigzag(cal[200:], -0.002, base=zigzag(cal, 0.002)[199][4]),
            'TLT': zigzag(cal, 0.002, period=10), 'GLD': zigzag(cal, -0.001, period=14)}
    modes, why, _, state = rotation_modes(bars, cal, cal[1], confirm=5)
    first = next(d for d in cal if modes.get(d) == 'TLT')
    assert why[first] in ('rotate', 'exit') and first > cal[200]
    assert 'GLD' not in modes.values()
    assert switch_log(modes, why)[-1][:3] == [first, 'boost', 'TLT']


def test_curve_trades_the_day_after_the_decision_and_charges_the_switch():
    cal = days(4)
    boost = [[d, v] for d, v in zip(cal, (1.0, 1.1, 1.2, 1.3))]
    px = {'TLT': dict(zip(cal, (10.0, 10.0, 20.0, 40.0)))}
    modes = {cal[0]: 'TLT', cal[1]: 'TLT', cal[2]: 'TLT', cal[3]: 'TLT'}
    c = rotation_curve(boost, px, cal, modes, cost=0.01)
    # day 1: Boost's gain, then the switch at day 1's close; day 2 on: TLT
    assert abs(c[1][1] - 1.1 * 0.99) < 1e-12
    assert abs(c[3][1] - 1.1 * 0.99 * 4) < 1e-12


def test_warning_needs_spy_down_below_its_average_and_a_rising_asset():
    from mtl.rotation import warning_log, warnings
    cal = days(400)
    spy = zigzag(cal, 0.002)[:200] + zigzag(cal[200:], -0.003, base=zigzag(cal, 0.002)[199][4])
    bars = {'SPY': spy, 'TLT': zigzag(cal, 0.002, period=10), 'GLD': zigzag(cal, -0.001, period=14)}
    R = Reader(bars)
    w = warnings(R, bars, cal, cal[1])
    assert w and set(w.values()) == {'TLT'} and min(w) > cal[200]
    log = warning_log(w, cal)
    assert log[-1][0] == min(w) and log[0][1] == max(w)

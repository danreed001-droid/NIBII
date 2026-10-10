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


def test_sales_record_buy_and_sell_closes():
    from mtl.rotation import sales
    picks = [['2020-01-06', ['A', 'B']], ['2020-01-13', ['A', 'C']], ['2020-01-21', ['C']]]
    px = {'A': {'2020-01-06': 10.0, '2020-01-21': 12.0}, 'B': {'2020-01-06': 5.0, '2020-01-13': 4.0}, 'C': {'2020-01-13': 3.0}}
    assert sales(picks, px) == [('2020-01-13', 'B', 5.0, 4.0), ('2020-01-21', 'A', 10.0, 12.0)]


def test_whipsaw_switches_on_at_the_week_end_when_most_sales_lost():
    from mtl.rotation import whipsaw
    cal = days(60)
    # a name bought and sold at a loss every session from day 5 on (the sale lands the next session)
    picks, px = [], {}
    for i in range(1, 40):
        t = f'T{i}'
        px[t] = {cal[i]: 10.0, cal[i + 1]: 9.0}
        picks.append([cal[i], [t]])
    on = whipsaw(picks, px, cal, cal[0], look=10, need=6, loss=0.65)
    first = min(d for d in on if on[d])
    assert date.fromisoformat(first).weekday() == 4          # decided at a week's last close
    assert not on[cal[0]] and on[cal[cal.index(first) + 1]]   # carried into the next week
    assert not on[cal[-1]]                                    # sales stopped: off again
    assert not any(whipsaw(picks, px, cal, cal[0], look=10, need=20).values())   # too few sales


def test_whip_pick_takes_the_biggest_gain_and_skips_weekly_downtrends():
    from mtl.rotation import whip_pick
    cal = days(400)
    bars = {'SPY': zigzag(cal, 0.001), 'TLT': zigzag(cal, -0.003), 'GLD': zigzag(cal, 0.002)}
    R = Reader(bars)
    closes = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    best, chg = whip_pick(R, closes, cal, len(cal) - 1, look=63)
    assert best == 'GLD' and chg['GLD'] > chg['SPY'] > 0 > chg['TLT']
    # TLT up most but in a weekly downtrend: skipped
    closes['TLT'] = {d: 1000.0 * (1 + i / 1e4) for i, d in enumerate(cal)}
    assert whip_pick(R, closes, cal, len(cal) - 1, look=63)[0] == 'GLD'
    # nothing up -> T-bills
    flat = {t: {d: 100.0 for d in cal} for t in bars}
    assert whip_pick(R, flat, cal, len(cal) - 1, look=63)[0] == 'BIL'


def test_curve_holds_half_in_the_whipsaw_asset():
    cal = days(4)
    boost = [[d, v] for d, v in zip(cal, (1.0, 1.0, 1.2, 1.2))]
    px = {'GLD': dict(zip(cal, (10.0, 10.0, 10.0, 15.0)))}
    modes = {d: 'boost' for d in cal}
    c = rotation_curve(boost, px, cal, modes, cost=0.0, half={cal[0]: 'GLD', cal[1]: 'GLD', cal[2]: 'GLD'})
    # from day 1's close half Boost, half gold: day 2 Boost +20% -> +10%; day 3 gold +50% -> +25%
    assert abs(c[2][1] - 1.1) < 1e-12 and abs(c[3][1] - 1.1 * 1.25) < 1e-12


def test_reflation_needs_the_yield_and_gold_both_up():
    from mtl.rotation import reflation
    cal = days(10)
    rate = {d: 4.0 + 0.1 * i for i, d in enumerate(cal)}               # yield climbing
    gold = {d: 100.0 + i for i, d in enumerate(cal)}                    # gold climbing
    r = reflation(rate, gold, cal, look=3)
    assert r[cal[2]] is None and r[cal[3]] is True and r[cal[-1]] is True
    falling = {d: 100.0 - i for i, d in enumerate(cal)}
    assert not any(reflation(rate, falling, cal, look=3)[d] for d in cal[3:])
    # a missing yield reading is carried forward from the last one
    gap = {d: v for d, v in rate.items() if d != cal[5]}
    assert reflation(gap, gold, cal, look=3)[cal[5]] is True


def test_whip_halves_stand_aside_in_the_reflation_regime():
    from mtl.rotation import whip_halves
    cal = days(400)
    bars = {'SPY': zigzag(cal, 0.001), 'TLT': zigzag(cal, -0.003), 'GLD': zigzag(cal, 0.002)}
    R = Reader(bars)
    closes = {t: {b[0]: b[4] for b in bs} for t, bs in bars.items()}
    last = cal[-3:]
    modes = {d: 'boost' for d in last}
    on = {d: True for d in last}
    assert whip_halves(modes, on, R, closes, cal, look=63) == {d: 'GLD' for d in last}
    half = whip_halves(modes, on, R, closes, cal, look=63, skip={last[1]: True})
    assert last[1] not in half and half[last[0]] == half[last[2]] == 'GLD'

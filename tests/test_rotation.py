"""Bond / gold rotation (mtl/rotation.py): information only, on top of Boost + cushion."""
from mtl.rotation import rotation_curve, rotation_signal


def zigzag(legs, start=100.0):
    """Daily bars walking straight between the given turning points, 6 sessions a leg,
    with a 0.5% high-low range around each close."""
    closes, px = [], start
    for target in legs:
        step = (target / px) ** (1 / 6)
        for _ in range(6):
            px *= step
            closes.append(px)
    return [(f"d{i:04d}", c, c * 1.0025, c * 0.9975, c) for i, c in enumerate(closes)]


def setup(asset_legs, wait=3):
    spy = zigzag([98, 99.5, 97, 98.5, 96, 97.5, 95, 96.5, 94, 95.5, 93, 94.5, 92, 93.5, 91])   # a gentle downtrend
    gld = zigzag(asset_legs)
    cal = [b[0] for b in spy]
    return spy, gld, cal, rotation_signal(spy, {'GLD': gld}, cal, wait=wait)


def test_switches_into_a_steep_uptrend_while_spy_falls_then_exits_on_a_lower_low():
    up = [110, 105, 120, 115, 130, 125, 140, 135, 150]
    spy, gld, cal, r = setup(up + [100, 105, 90, 95, 80])
    assert r['switches'], 'never switched'
    d, t, out = r['switches'][0]
    assert t == 'GLD' and out is not None and d < out
    assert r['held'][d] == 'GLD' and r['held'][cal[-1]] is None
    assert len(r['switches']) == 1             # no re-entry into the trend that just broke
    # the switch waited for the setup to hold `wait` sessions in a row
    assert r['streak'][d]['GLD'] >= 3
    # no switch before both trends were confirmed by swings a bar could have seen
    assert all(r['held'][x] is None for x in cal[:24])


def test_no_switch_when_the_asset_trend_is_not_up():
    _, _, cal, r = setup([95, 100, 90, 95, 85, 90, 80, 85, 75])
    assert r['switches'] == [] and all(v is None for v in r['held'].values())


def test_curve_follows_the_base_until_the_switch_and_the_asset_from_the_next_close():
    cal = ['a', 'b', 'c', 'd', 'e']
    base = [[d, v] for d, v in zip(cal, [1.0, 1.1, 1.2, 1.3, 1.4])]
    gld = {'a': 10, 'b': 10, 'c': 10, 'd': 20, 'e': 40}
    held = {'a': None, 'b': 'GLD', 'c': 'GLD', 'd': None, 'e': None}
    out = dict(rotation_curve(base, {'GLD': gld}, cal, held))
    # decided at b's close, bought at c's close: c's gain is still the base's
    assert abs(out['c'] - 1.2) < 1e-9
    assert abs(out['d'] - 2.4) < 1e-9          # in GLD from c to d (doubled)
    assert abs(out['e'] - 4.8) < 1e-9          # exit decided at d's close, sold at e's close

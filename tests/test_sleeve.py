"""Best-of sleeve and the levered plan - synthetic prices, no network."""
from datetime import date, timedelta

from mtl.sleeve import ASSETS, best_of, filled, plan_curve, sleeve_curve


def cal(n, start='2024-01-01'):
    d0, out, d = date.fromisoformat(start), [], 0
    while len(out) < n:
        day = d0 + timedelta(days=d)
        if day.weekday() < 5:
            out.append(day.isoformat())
        d += 1
    return out


def flat(c, v=100.0):
    return {d: v for d in c}


def test_best_of_picks_the_strongest_six_month_asset_and_cash_when_all_fall():
    c = cal(200)
    px = {t: flat(c) for t in ASSETS}
    px['GLD'] = {d: 100 * 1.002 ** i for i, d in enumerate(c)}
    px['DBC'] = {d: 100 * 1.001 ** i for i, d in enumerate(c)}
    assert best_of(filled(px, c), c, 199) == 'GLD'
    px = {t: {d: 100 * 0.999 ** i for i, d in enumerate(c)} for t in ASSETS}
    px['BIL'] = {d: 100 * 1.0001 ** i for i, d in enumerate(c)}
    assert best_of(filled(px, c), c, 199) == 'BIL'


def test_sleeve_switches_to_the_new_leader_at_a_week_end():
    c = cal(300)
    px = {t: flat(c) for t in ASSETS}
    px['GLD'] = {d: 100 * (1.003 ** i if i < 150 else 1.003 ** 150 * 0.997 ** (i - 150)) for i, d in enumerate(c)}
    px['DBC'] = {d: 100 * (1.0 if i < 150 else 1.004 ** (i - 150)) for i, d in enumerate(c)}
    curve, picks = sleeve_curve(px, c, c[130])
    assert picks[0][1] == 'GLD' and picks[-1][1] == 'DBC'
    assert curve[0][1] == 1.0 and len(curve) == 170


def test_plan_without_leverage_is_the_weighted_mix_and_borrowing_costs_money():
    c = cal(60)
    main = [[d, 1.0 * 1.01 ** i] for i, d in enumerate(c)]
    flat_sleeve = [[d, 1.0] for d in c]
    p = plan_curve(main, flat_sleeve, 0.6, 0.4, c, rate=0.06)
    assert 1.0 < p[-1][1] < main[-1][1]
    # levered with a flat main and sleeve: only the interest shows
    lev = plan_curve(flat_sleeve, flat_sleeve, 0.78, 0.52, c, rate=0.06)
    assert lev[-1][1] < 1.0
    assert abs(lev[-1][1] - (1 - 0.30 * 0.06 / 252) ** 59) < 1e-3


def test_dynamic_plan_changes_the_mix_at_the_session_after_the_decision():
    from mtl.momentum import last_sessions_of_weeks
    from mtl.sleeve import plan_curve_dynamic
    c = cal(30)
    main = [[d, 1.0 * 1.01 ** i] for i, d in enumerate(c)]
    flat_sleeve = [[d, 1.0] for d in c]
    full = plan_curve_dynamic(main, flat_sleeve, c, lambda d: 1.0)
    assert abs(full[-1][1] - main[-1][1]) < 1e-9
    fri = last_sessions_of_weeks(c)[1]
    p = plan_curve_dynamic(main, flat_sleeve, c, lambda d: 0.6 if d >= fri else 1.0)
    k = c.index(fri)
    # identical through Monday's close, then only 60% keeps growing
    assert abs(p[k + 1][1] - full[k + 1][1]) < 1e-9
    assert p[k + 2][1] < full[k + 2][1]


def test_plan_curve_mix_matches_the_two_part_version():
    from mtl.sleeve import plan_curve_dynamic, plan_curve_mix
    c = cal(40)
    a = [[d, 1.01 ** i] for i, d in enumerate(c)]
    b = [[d, 0.995 ** i] for i, d in enumerate(c)]
    s = [[d, 1.0] for d in c]
    two = plan_curve_dynamic(a, b, c, lambda f: 0.7)
    three = plan_curve_mix({'a': a, 'b': b, 's': s}, c, lambda f: {'a': 0.7, 'b': 0.3})
    assert abs(two[-1][1] - three[-1][1]) < 1e-9
    half = plan_curve_mix({'a': a, 'b': b, 's': s}, c, lambda f: {'a': 0.35, 'b': 0.3, 's': 0.35})
    assert 1.0 < half[-1][1] < two[-1][1]

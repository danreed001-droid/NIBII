from mtl.widenet import LOOK, SKIP, scan

CAL = [f'd{i:05d}' for i in range(400)]


def flat(v=100.0):
    return {d: v for d in CAL}


def test_scores_like_the_plan_and_flags_beating_spy():
    up = {d: 100.0 * (1.001 ** i) for i, d in enumerate(CAL)}
    w = scan({'AAA': up, 'BBB': flat()}, flat(), CAL, len(CAL) - 1, names={'AAA': 'a', 'BBB': 'b'})
    k = len(CAL) - 1
    a = w['rows'][0]
    assert a['t'] == 'AAA' and a['beats'] and abs(a['score'] - (1.001 ** (k - SKIP) / 1.001 ** (k - LOOK) - 1)) < 1e-4
    assert w['rows'][1]['t'] == 'BBB' and not w['rows'][1]['beats'] and w['n'] == 2
    assert a['nearHigh'] and a['offHigh'] == 0


def test_breakout_after_a_base_only_when_fresh():
    # rises to a high, sits below it for longer than BASE sessions, then breaks out at session j
    j = 380
    c = {}
    for i, d in enumerate(CAL):
        c[d] = 100 + i if i < 200 else (290.0 if i < j else 310.0 + (i - j))
    w = scan({'X': c}, flat(), CAL, j + 2, names={'X': 'x'})
    assert w['breakouts'] and w['breakouts'][0]['breakout'] == CAL[j]
    # a new high without the quiet spell before it is not a breakout
    steady = {d: 100 + i for i, d in enumerate(CAL)}
    assert scan({'Y': steady}, flat(), CAL, j + 2, names={'Y': 'y'})['breakouts'] == []
    # nor is one older than a week
    assert scan({'X': c}, flat(), CAL, j + 8, names={'X': 'x'})['breakouts'] == []


def test_skips_assets_without_enough_history():
    young = {d: 50.0 for d in CAL[-50:]}
    w = scan({'NEW': young}, flat(), CAL, len(CAL) - 1, names={'NEW': 'n'})
    assert w['n'] == 0 and w['rows'] == []

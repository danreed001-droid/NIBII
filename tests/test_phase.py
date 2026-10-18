from mtl.phase import market_phase, swings


def series(*legs, start=100.0):
    """Closes moving by each (sessions, total move) leg in turn."""
    out = [start]
    for n, mv in legs:
        step = (1 + mv) ** (1 / n)
        out += [out[-1] * step ** (i + 1) for i in range(n)]
    return out


def phase_at(c):
    cal = [f'd{i:04d}' for i in range(len(c))]
    return market_phase(cal, c)


def test_phases_follow_the_20_percent_swings():
    up = series((250, 0.5))
    assert phase_at(up)['phase'] == 'bull run'
    assert phase_at(series((250, 0.5), (40, -0.15)))['phase'] == 'correction'
    bear = series((250, 0.5), (60, -0.30))
    assert phase_at(bear)['phase'] == 'bear market'
    assert phase_at(series((250, 0.5), (60, -0.30), (20, 0.15)))['phase'] == 'recovering'
    nb = phase_at(series((250, 0.5), (60, -0.30), (40, 0.25)))
    assert nb['phase'] == 'new bull run' and nb['since'] == 'd0310'
    assert phase_at(series((250, 0.5), (60, -0.30), (120, 0.60)))['phase'] == 'bull run'


def test_a_new_bull_run_that_fails_turns_back_into_a_bear():
    c = series((250, 0.5), (60, -0.30), (30, 0.22), (40, -0.30))
    assert [s[0] for s in swings(c)] == ['bull', 'bear', 'bull', 'bear']
    assert phase_at(c)['phase'] == 'bear market'

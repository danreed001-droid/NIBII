from datetime import date, timedelta

from mtl.lowerhigh import LH_DAYS, apply_lowerhigh, lowerhigh_cash, lowerhigh_reading, lowerhigh_state


def _days(n):
    out, d = [], date(2020, 1, 6)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(anchors, extra=()):
    """Daily bars along straight lines between (session, close) anchors, then `extra` closes."""
    cl = []
    for (i0, p0), (i1, p1) in zip(anchors[:-1], anchors[1:]):
        cl += [p0 + (p1 - p0) * (i - i0) / (i1 - i0) for i in range(i0, i1)]
    cl += [anchors[-1][1]] + list(extra)
    return [(d, c, c * 1.002, c * 0.998, c) for d, c in zip(_days(len(cl)), cl)]


# weekly swing highs 115 -> 130 (higher), then a slow slide and a rally to 125 that tops out
BASE = [(0, 100), (50, 115), (75, 105), (100, 130), (170, 100), (240, 125)]


def test_confirmed_lower_high_fires():
    bars = _bars([(0, 100), (50, 115), (75, 105), (100, 130), (125, 110), (150, 120), (200, 105)])
    r = lowerhigh_reading(bars)
    assert r['on'] and r['kind'] == 'confirmed'
    assert r['highs'][1][1] < r['highs'][0][1] and r['close'] < r['highs'][1][1]


def test_early_lower_high_needs_the_daily_chart_to_turn():
    # straight down from the 125 peak: no daily lower high yet, so no signal
    off = lowerhigh_reading(_bars(BASE, extra=[124, 123, 122, 121, 120, 119, 118, 117, 116, 115]))
    assert not off['on'] and off['peak'][1] < off['highs'][1][1]
    # a small bounce that tops out lower: the daily chart has turned, the early signal fires
    on = lowerhigh_reading(_bars(BASE, extra=[124, 122, 120, 121.5, 122.5, 121, 119.5, 118, 117, 116]))
    assert on['on'] and on['kind'] == 'early'
    assert on['daily'][1][1] < on['daily'][0][1] and on['key'][:10] == on['peak'][0]


def test_no_signal_without_two_weekly_highs_or_while_making_higher_highs():
    assert lowerhigh_reading(_bars([(0, 100), (60, 130)])) is None
    up = lowerhigh_reading(_bars([(0, 100), (50, 115), (75, 105), (100, 130), (125, 110), (200, 140)]))
    assert up is not None and not up['on']


def test_early_then_confirmed_each_get_two_weeks_and_nothing_fires_twice():
    bars = _bars([(0, 100), (50, 115), (75, 105), (100, 130), (125, 110), (150, 120), (200, 105)])
    cal = [b[0] for b in bars]
    cash, log = lowerhigh_cash(bars, cal, cal[0], {d: 'boost' for d in cal})
    assert [x[1] for x in log] == ['early', 'confirmed'] and log[0][2] == log[1][2]   # the same high, both triggers
    assert len(cash) == 2 * LH_DAYS                           # on for weeks after that, but no third stretch
    for x in log:
        k = cal.index(x[0])
        assert all(d in cash for d in cal[k:k + LH_DAYS])


def test_only_acts_while_the_plan_holds_the_boost_list():
    bars = _bars([(0, 100), (50, 115), (75, 105), (100, 130), (125, 110), (150, 120), (200, 105)])
    cal = [b[0] for b in bars]
    first = lowerhigh_cash(bars, cal, cal[0], {d: 'boost' for d in cal})[1][0][0]
    k = cal.index(first)
    modes = {d: ('TLT' if k <= i < k + 5 else 'boost') for i, d in enumerate(cal)}
    cash, log = lowerhigh_cash(bars, cal, cal[0], modes)
    assert log[0][0] == cal[k + 5]                              # fires on the first Boost-list day
    assert not any(modes[d] == 'TLT' for d in cash)


def test_apply_and_state():
    cal = _days(30)
    modes = {d: 'boost' for d in cal}
    cash = set(cal[5:15])
    m, why = apply_lowerhigh(modes, {}, cash, cal)
    assert all(m[d] == 'BIL' for d in cal[5:15]) and m[cal[15]] == 'boost'
    assert why[cal[5]] == 'lowerhigh' and why[cal[15]] == 'lowerhigh-end'
    bars = [(d, 100.0, 100.2, 99.8, 100.0) for d in cal]
    st = lowerhigh_state(bars, cash, [[cal[5], 'confirmed', cal[4]]], cal, 8)
    assert st['inCash'] and st['run'] == [cal[5], cal[14]] and st['n'] == 1
    assert not lowerhigh_state(bars, cash, [[cal[5], 'confirmed', cal[4]]], cal, 20)['inCash']


def test_the_two_weeks_hold_the_chosen_asset_and_log_changes():
    bars = _bars([(0, 100), (50, 115), (75, 105), (100, 130), (125, 110), (150, 120), (200, 105)])
    cal = [b[0] for b in bars]
    first = lowerhigh_cash(bars, cal, cal[0], {d: 'boost' for d in cal})[1][0][0]
    k = cal.index(first)
    pick = {d: ('GLD' if i < k + 4 else 'TLT') for i, d in enumerate(cal)}
    cash, _ = lowerhigh_cash(bars, cal, cal[0], {d: 'boost' for d in cal}, dest=lambda d: pick[d])
    assert [cash[d] for d in cal[k:k + LH_DAYS]] == ['GLD'] * 4 + ['TLT'] * (LH_DAYS - 4)
    none, _ = lowerhigh_cash(bars, cal, cal[0], {d: 'boost' for d in cal}, dest=lambda d: None)
    assert set(none.values()) == {'BIL'}                          # nothing rising: T-bills
    m, why = apply_lowerhigh({d: 'boost' for d in cal}, {}, cash, cal)
    assert m[cal[k]] == 'GLD' and m[cal[k + 4]] == 'TLT' and m[cal[k + LH_DAYS]] == 'boost'
    assert why[cal[k]] == why[cal[k + 4]] == 'lowerhigh' and why[cal[k + LH_DAYS]] == 'lowerhigh-end'
    assert lowerhigh_state(bars, cash, [[first, 'early', first]], cal, k + 5)['asset'] == 'TLT'

from mtl.dip import DIP_MULT, dip_curve, dip_events, dip_weights


CAL = ['2026-09-%02d' % d for d in (1, 2, 3, 4, 8, 9, 10, 11, 14, 15)]


def px(changes):
    """{ticker: {date: close}} from per-session % changes."""
    out = {}
    for t, ch in changes.items():
        v, d = 100.0, {}
        for day, c in zip(CAL, ch):
            v *= 1 + c
            d[day] = v
        out[t] = d
    return out


def test_dip_weights_scale_the_dropped_stock_and_keep_the_total():
    w = dip_weights(['A', 'B', 'C', 'D', 'E'], {'A'}, 5)
    assert abs(sum(w.values()) - 1.0) < 1e-12
    assert abs(w['A'] / w['B'] - DIP_MULT) < 1e-12
    w2 = dip_weights(['A', 'B'], {'A'}, 5)              # empty slots stay cash
    assert abs(sum(w2.values()) - 0.4) < 1e-12


def test_dip_events_need_a_10pct_fall_a_boost_day_and_no_trade_next_session():
    prices = px({'A': [0, 0, -0.12, 0, 0, 0, 0, 0, 0, 0], 'B': [0, 0, -0.08, 0, 0, 0, 0, 0, 0, 0]})
    picks = [[CAL[0], ['A', 'B']]]
    ev = dip_events(picks, prices, CAL, lambda d: True)
    assert [(f, d, sorted(c)) for f, d, c in ev] == [(CAL[2], CAL[3], ['A'])]
    assert dip_events(picks, prices, CAL, lambda d: False) == []                  # plan not in the Boost list
    assert dip_events([[CAL[0], ['A', 'B']], [CAL[3], ['A', 'B']]], prices, CAL, lambda d: True) == []   # the list trades anyway


def test_dip_curve_adds_the_extra_weight_until_the_list_trades():
    # A falls 12% on day 2, then rises 10% on day 4; B flat. Weekly trade on day 5 resets the weights.
    prices = px({'A': [0, 0, -0.12, 0, 0.10, 0, 0, 0, 0, 0], 'B': [0] * 10})
    picks = [[CAL[0], ['A', 'B']], [CAL[5], ['A', 'B']]]
    base = [[d, 1.0] for d in CAL]                       # the base curve is flat: only the add moves it
    ev = dip_events(picks, prices, CAL, lambda d: True)
    c = dip_curve(base, picks, prices, CAL, ev, top_n=2, cost=0.0)
    w = dip_weights(['A', 'B'], {'A'}, 2)
    extra = (w['A'] - 0.5) * 0.10 + (w['B'] - 0.5) * 0.0
    assert abs(c[4][1] - (1 + extra)) < 1e-12 and abs(c[-1][1] - c[4][1]) < 1e-12
    assert c[3][1] == 1.0                                # the add is bought at day 3's close: nothing before


def test_dip_call_target_is_three_months_at_the_money():
    from mtl.dip import dip_call_target, DIP_CALL_MAX_IV
    c = dip_call_target(120.0, '2026-10-12')
    assert c['expiry'] == '2027-01-11' and c['strike'] == 120.0 and c['price'] == 120.0 and c['maxIv'] == DIP_CALL_MAX_IV

from mtl.heat import daily_heat, weekly_heat

# two full weeks (Mon-Fri) plus the Friday before: 2026-01-02 (Fri), 05-09, 12-16
CAL = ['2026-01-02'] + [f'2026-01-{d:02d}' for d in range(5, 10)] + [f'2026-01-{d:02d}' for d in range(12, 17)]


def px(fri0, fri1, fri2):
    return {'2026-01-02': fri0, '2026-01-09': fri1, '2026-01-16': fri2}


def test_ranks_each_week_and_orders_by_rank_sum():
    prices = {'A': px(100, 110, 110), 'B': px(100, 105, 120), 'C': px(100, 90, 81)}
    h = weekly_heat(prices, CAL, ['C', 'A', 'B'], weeks=2)
    assert h['weeks'] == ['2026-01-09', '2026-01-16']
    assert [c[:2] for c in h['cells']['A']] == [[0.1, 1], [0.0, 2]]
    assert [c[:2] for c in h['cells']['B']] == [[0.05, 2], [0.1429, 1]]
    assert [c[:2] for c in h['cells']['C']] == [[-0.1, 3], [-0.1, 3]]
    assert h['cells']['A'][0][2] is None              # too little history for a normal move
    assert h['sums'] == {'A': 3, 'B': 3, 'C': 6}
    assert h['tickers'] == ['A', 'B', 'C']          # tie keeps input order among A/B
    assert h['total']['B'] == 0.2
    assert h['partial'] is False


def test_missing_week_gets_no_rank():
    prices = {'A': px(100, 110, 121), 'B': {'2026-01-09': 50, '2026-01-16': 60}}
    h = weekly_heat(prices, CAL, ['A', 'B'], weeks=2)
    assert h['cells']['B'][0] is None
    assert h['cells']['B'][1][:2] == [0.2, 1]
    assert h['tickers'] == ['B', 'A']               # average rank 1 vs 1.5
    assert h['total']['B'] is None


def test_partial_week_flag():
    cal = CAL + ['2026-01-19', '2026-01-20']        # Mon/Tue of the next week
    prices = {'A': dict(px(100, 110, 121), **{'2026-01-20': 125})}
    h = weekly_heat(prices, cal, ['A'], weeks=2)
    assert h['weeks'] == ['2026-01-16', '2026-01-20'] and h['partial'] is True


def test_z_is_change_over_normal_weekly_move():
    from datetime import date, timedelta
    d0 = date(2025, 1, 3)                            # a Friday; 40 Fridays of prices
    cal = [(d0 + timedelta(weeks=i)).isoformat() for i in range(40)]
    p, v = {}, 100.0
    for i, d in enumerate(cal):
        p[d] = v
        v *= 1.02 if i % 2 == 0 else 0.98              # alternating +2% / -2% weeks
    p[cal[-1]] = p[cal[-2]] * 1.08                    # last week: +8%
    h = weekly_heat({'A': p}, cal, ['A'], weeks=2)
    chg, rank, z, close = h['cells']['A'][-1]
    assert chg == 0.08 and rank == 1
    assert abs(close - p[cal[-1]]) / p[cal[-1]] < 1e-5   # the period's close, for the price view
    assert 3.5 < z < 4.5                              # about 4x a 2% normal move


def test_daily_heat_ranks_each_session():
    prices = {'A': {'2026-01-05': 100, '2026-01-06': 101, '2026-01-07': 99},
              'B': {'2026-01-05': 50, '2026-01-06': 49, '2026-01-07': 51}}
    cal = ['2026-01-05', '2026-01-06', '2026-01-07']
    h = daily_heat(prices, cal, ['A', 'B'], days=2, extra=['B', 'ZZZ'], breadth=['A', 'B'])
    assert h['weeks'] == ['2026-01-06', '2026-01-07'] and h['unit'] == 'day'
    assert [c[:2] for c in h['cells']['A']] == [[0.01, 1], [-0.0198, 2]]
    assert [c[:2] for c in h['cells']['B']] == [[-0.02, 2], [0.0408, 1]]
    assert h['extra'] == ['B'] and h['partial'] is False
    assert h['breadth'] == [0.5, 0.5] and h['breadthN'] == 2

"""The human model's scoring - synthetic prices, no network."""
from mtl.human import call_for, live_calls, mix_of, score, signature, slots_for

CAL = ['2026-01-02', '2026-01-05', '2026-01-06', '2026-01-09', '2026-01-12', '2026-01-13']
WEEKS = [('2026-01-02', '2026-01-05', 1.0, 0.8), ('2026-01-09', '2026-01-12', 0.6, 0.6)]
FLAT = {d: 1.0 for d in CAL}


def picks(_):
    return ['A', 'B', 'C', 'D', 'E']


def closes(growth):
    return {t: {d: 100 * g ** i for i, d in enumerate(CAL)} for t, g in growth.items()}


def test_carry_forward_and_mixes():
    calls = {'2026-01-02': {'m': 'auto'}, '2026-01-09': {'m': 'del'}}
    assert list(live_calls(calls)) == ['2026-01-02']
    assert call_for(live_calls(calls), '2026-01-09')['m'] == 'auto'
    assert [round(x, 9) for x in mix_of({'m': 'steps'}, 1.0, 0.8)] == [0.8, 0.2, 0.0]
    assert mix_of({'m': 'custom', 's': 70, 'v': 40}, 1, 1) == (0.7, 0.3, 0.0)   # sleeve capped at what's left


def test_slots_apply_swaps_only_while_the_replacement_ranks_top_10():
    call = {'m': 'auto', 'swaps': [['B', 'X']], 'drops': ['D']}
    assert slots_for(['A', 'B', 'C', 'D', 'E'], call, {'X': 7}) == ['A', 'X', 'C', None, 'E']
    assert slots_for(['A', 'B', 'C', 'D', 'E'], call, {'X': 14}) == ['A', 'B', 'C', None, 'E']
    assert slots_for(['A', 'Q', 'C', 'E', 'F'], call, {'X': 7}) == ['A', 'Q', 'C', 'E', 'F']   # model sold B and D


def test_all_auto_with_flat_sleeve_tracks_the_stocks_and_a_drop_holds_cash():
    px = closes({'A': 1.01, 'B': 1.01, 'C': 1.01, 'D': 1.01, 'E': 1.01, 'X': 1.05})
    plain = score({'2026-01-02': {'m': 'custom', 's': 100, 'v': 0}}, CAL, WEEKS, picks, lambda f: {}, px, FLAT, FLAT)
    assert abs(plain['curve'][-1][1] - 1.01 ** 4) < 1e-6          # Jan 5 -> Jan 13 = 4 sessions
    swap = score({'2026-01-02': {'m': 'custom', 's': 100, 'v': 0, 'swaps': [['B', 'X']]}}, CAL, WEEKS, picks,
                 lambda f: {'X': 6}, px, FLAT, FLAT)
    assert swap['curve'][-1][1] > plain['curve'][-1][1]
    assert swap['weeks'][0][2] == ['A', 'X', 'C', 'D', 'E']
    drop = score({'2026-01-02': {'m': 'custom', 's': 100, 'v': 0, 'drops': ['A']}}, CAL, WEEKS, picks, lambda f: {}, px, FLAT, FLAT)
    assert drop['curve'][-1][1] < plain['curve'][-1][1]
    base = score({'2026-01-02': {'m': 'custom', 's': 100, 'v': 0, 'drops': ['A']}}, CAL, WEEKS, picks, lambda f: {}, px,
                 FLAT, FLAT, apply_picks=False)
    assert abs(base['curve'][-1][1] - plain['curve'][-1][1]) < 1e-9
    assert signature({'2026-01-02': {'m': 'auto', 'swaps': [['B', 'X']]}}) == [['2026-01-02', 'auto', None, None, [['B', 'X']], []]]


def test_auto_call_uses_that_weeks_auto_share():
    px = closes({t: 1.02 for t in 'ABCDE'})
    r = score({'2026-01-02': {'m': 'auto'}}, CAL, WEEKS, picks, lambda f: {}, px, FLAT, FLAT)
    assert [w[3][0] for w in r['weeks']] == [1.0, 0.6]


def test_boost_call_uses_the_boost_list_and_its_mix():
    from mtl.human import score
    cal = ['2024-01-05', '2024-01-08', '2024-01-09']
    closes = {'A': {d: 10.0 for d in cal}, 'B': {'2024-01-05': 10.0, '2024-01-08': 10.0, '2024-01-09': 12.0}}
    flat = {d: 1.0 for d in cal}
    weeks = [('2024-01-05', '2024-01-08', 1.0, 1.0, 1.0)]
    r = score({'2024-01-05': {'m': 'boost'}}, cal, weeks, lambda d: ['A'], lambda f: {}, closes, flat, flat,
              slots_n=1, boost_picks_at=lambda d: ['B'])
    assert r['weeks'][0][2] == ['B'] and abs(r['curve'][-1][1] - 1.2) < 1e-9
    r = score({'2024-01-05': {'m': 'auto'}}, cal, weeks, lambda d: ['A'], lambda f: {}, closes, flat, flat,
              slots_n=1, boost_picks_at=lambda d: ['B'])
    assert r['weeks'][0][2] == ['A'] and abs(r['curve'][-1][1] - 1.0) < 1e-9


def test_boost100_call_holds_the_boost_list_fully_in_stocks():
    from mtl.human import mix_of, score
    assert mix_of({'m': 'boost100'}, 0.6, 0.6, 0.4) == (1.0, 0.0, 0.0)
    cal = ['2024-01-05', '2024-01-08', '2024-01-09']
    closes = {'A': {d: 10.0 for d in cal}, 'B': {'2024-01-05': 10.0, '2024-01-08': 10.0, '2024-01-09': 12.0}}
    flat = {d: 1.0 for d in cal}
    weeks = [('2024-01-05', '2024-01-08', 0.6, 0.6, 0.4)]     # Boost itself would be 40/60 this week
    r = score({'2024-01-05': {'m': 'boost100'}}, cal, weeks, lambda d: ['A'], lambda f: {}, closes, flat, flat,
              slots_n=1, boost_picks_at=lambda d: ['B'])
    assert r['weeks'][0][2] == ['B'] and abs(r['curve'][-1][1] - 1.2) < 1e-9


def test_cushion_call_uses_the_boost_list_and_the_cushion_share():
    from mtl.human import mix_of, score
    assert mix_of({'m': 'cushion'}, 0.6, 0.6, 0.4, 0.75) == (0.75, 0.25, 0.0)
    assert mix_of({'m': 'cushion'}, 0.6, 0.6, 0.4) == (1.0, 0.0, 0.0)
    cal = ['2024-01-05', '2024-01-08', '2024-01-09']
    closes = {'A': {d: 10.0 for d in cal}, 'B': {'2024-01-05': 10.0, '2024-01-08': 10.0, '2024-01-09': 12.0}}
    flat = {d: 1.0 for d in cal}
    weeks = [('2024-01-05', '2024-01-08', 1.0, 1.0, 1.0, 0.75)]
    r = score({'2024-01-05': {'m': 'cushion'}}, cal, weeks, lambda d: ['A'], lambda f: {}, closes, flat, flat,
              slots_n=1, boost_picks_at=lambda d: ['B'])
    assert r['weeks'][0][2] == ['B'] and abs(r['curve'][-1][1] - (0.75 * 1.2 + 0.25)) < 1e-9

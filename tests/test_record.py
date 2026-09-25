"""mtl.record.aggregate: Result vs Real Result dual metrics."""
from mtl.record import aggregate

BASE_HORIZON = dict(
    band=0.01, bull=7, bear=3, neutral=3, margin=4, clusterDowngrade=False,
    families=['A'], flatHi=0, flatLo=0, maturity='2026-09-25',
    preReversionCall=None, preReversionConfidence=None, preReversionCorrect=None,
    reversionAligned='none', reversionFlag=False, reversionNote='',
    shadowCall=None, shadowConfidence=None, shadowCorrect=None, votes=[],
)


def _horizon(h, call, confidence, ret):
    from mtl.score import outcome, _mark
    band = BASE_HORIZON['band']
    oc = outcome(ret, band)
    return dict(BASE_HORIZON, h=h, call=call, confidence=confidence, ret=ret,
                maturityClose=100 * (1 + ret), correct=_mark(call, oc))


def _doc(date, horizons):
    return dict(date=date, overlay={}, assets=[dict(
        key='equities', name='x', categories=['a'] * 12, horizons=horizons)])


def test_directional_call_landing_flat_is_excluded_from_real_result():
    # bullish call, ret lands inside the flat band -> a push, not settled
    # as a hit or a miss under Real Result, but still an "incorrect" miss
    # under the strict Result field.
    doc = _doc('2026-01-01', [_horizon(1, 'bullish', 'lean', ret=0.002)])
    agg = aggregate({doc['date']: doc})

    assert agg['overall']['n'] == 1
    assert agg['overall']['hits'] == 0  # bullish != flat -> incorrect under strict Result

    assert agg['overallReal']['n'] == 0  # excluded entirely, not counted as a miss
    assert agg['noCallCells'] == 1


def test_opposite_direction_counts_as_a_miss_in_both():
    # bearish call, actual move is bullish - a real miss either way
    doc = _doc('2026-01-01', [_horizon(1, 'bearish', 'solid', ret=0.05)])
    agg = aggregate({doc['date']: doc})

    assert agg['overall']['n'] == 1 and agg['overall']['hits'] == 0
    assert agg['overallReal']['n'] == 1 and agg['overallReal']['hits'] == 0
    assert agg['noCallCells'] == 0


def test_matching_call_counts_as_a_hit_in_both():
    doc = _doc('2026-01-01', [_horizon(1, 'bullish', 'solid', ret=0.05)])
    agg = aggregate({doc['date']: doc})

    assert agg['overall']['hits'] == 1 and agg['overall']['n'] == 1
    assert agg['overallReal']['hits'] == 1 and agg['overallReal']['n'] == 1


def test_mixed_slate_real_result_pct_exceeds_strict_result_pct():
    # 1 real hit, 1 real miss, 1 no-call push (excluded) - Real Result
    # should read a higher/equal pct than strict Result since the push
    # counts against Result (call != flat) but not against Real Result.
    doc = _doc('2026-01-01', [
        _horizon(1, 'bullish', 'solid', ret=0.05),   # hit both
        _horizon(5, 'bearish', 'solid', ret=0.05),   # miss both (opposite direction)
        _horizon(10, 'bearish', 'lean', ret=0.002),  # push: miss under Result, excluded under Real
    ])
    agg = aggregate({doc['date']: doc})

    assert agg['overall']['n'] == 3 and agg['overall']['hits'] == 1  # 33.3%
    assert agg['overallReal']['n'] == 2 and agg['overallReal']['hits'] == 1  # 50%
    assert agg['overallReal']['pct'] > agg['overall']['pct']
    assert agg['noCallCells'] == 1


def test_by_horizon_and_by_asset_carry_a_real_sub_rate():
    doc = _doc('2026-01-01', [_horizon(1, 'bullish', 'solid', ret=0.05)])
    agg = aggregate({doc['date']: doc})

    assert 'real' in agg['byHorizon'][1]
    assert agg['byHorizon'][1]['real']['hits'] == 1
    assert 'real' in agg['byAsset']['equities']
    assert agg['byAsset']['equities']['real']['n'] == 1

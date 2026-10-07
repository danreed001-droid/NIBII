"""Offline tests for the mechanical Breadth / Volatility / Credit votes."""
import pytest

from mtl import mechvotes as mv
from mtl.build import ASSET_ORDER


def rows(vals, start=0):
    return [(f"2026-01-{i + 1:02d}" if i < 31 else f"2026-02-{i - 30:02d}", v)
            for i, v in enumerate(vals, start)]


def test_trend_read_bull_bear_neu_and_short_history():
    up = [1 + i * 0.01 for i in range(80)]
    down = [2 - i * 0.01 for i in range(80)]
    flat_then_dip = [1.0] * 79 + [0.999]       # below mean but only just; chg < 0 -> bear
    assert mv.trend_read(up)[0] == 'bull'
    assert mv.trend_read(down)[0] == 'bear'
    # above the 50d mean but down over 20 sessions -> mixed -> neutral
    mixed = [1 + i * 0.02 for i in range(60)] + [2.18 - i * 0.002 for i in range(20)]
    assert mv.trend_read(mixed)[0] == 'neu'
    side, why = mv.trend_read([1.0] * 10)
    assert side == 'neu' and 'need' in why
    assert mv.trend_read(flat_then_dip)[0] in ('bear', 'neu')


def test_vol_read_is_inverted_and_banded():
    calm = [20.0] * 20 + [18.0] * 5   # falling and >5% under its mean
    stress = [15.0] * 20 + [18.0] * 5  # rising and >5% over its mean
    flat = [16.0] * 30
    assert mv.vol_read(calm)[0] == 'bull'
    assert mv.vol_read(stress)[0] == 'bear'
    assert mv.vol_read(flat)[0] == 'neu'
    assert mv.vol_read([16.0] * 3)[0] == 'neu'


def test_ratio_series_never_uses_data_after_the_cutoff():
    a = [("2026-01-01", 10.0), ("2026-01-02", 11.0), ("2026-01-03", 99.0)]
    b = [("2026-01-01", 5.0), ("2026-01-02", 5.0), ("2026-01-03", 5.0)]
    out = mv.ratio_series(a, b, "2026-01-02")
    assert [d for d, _ in out] == ["2026-01-01", "2026-01-02"]
    assert out[-1][1] == pytest.approx(2.2)


def test_votes_only_speak_for_applicable_assets():
    up = [1 + i * 0.01 for i in range(80)]
    assert mv.breadth_vote('equities', up)[0] == 'bull'
    assert mv.breadth_vote('gold', up)[0] == 'neu'
    assert mv.credit_vote('qqq', up)[0] == 'bull'
    assert mv.credit_vote('bonds', up)[0] == 'neu'
    assert mv.vol_vote('bonds', [20.0] * 20 + [18.0] * 5, '^X')[0] == 'neu'


def test_no_vote_text_can_trip_the_publish_todo_gate():
    for v in (mv.breadth_vote('equities', None), mv.credit_vote('iwm', [1.0] * 5),
              mv.vol_vote('qqq', None, '^VXN'), mv.unavailable('HYG/IEF credit', 'OSError')):
        assert 'TODO' not in v[1]
        assert v[1].startswith(mv.PREFIX)


def test_draft_votes_fills_2_3_4_and_leaves_the_rest():
    from scripts.prepare_daily import draft_votes
    sig = dict(state='choppy', swings=[], lookback=1, lastBreak=None)
    assets = {k: {'structure': {'hourly': sig, 'weekly': sig}} for k in ASSET_ORDER}
    mech = {k: {2: ['bull', 'Mechanical: b'], 3: ['bear', 'Mechanical: v'],
                4: ['neu', 'Mechanical: c']} for k in ASSET_ORDER}
    votes = draft_votes(assets, mech)
    h = votes['equities']['5']
    assert len(h) == 13
    assert h[1][0] == 'bull' and h[2][0] == 'bear' and h[3][0] == 'neu'
    assert all('TODO' in h[i][1] for i in (0, 4, 5, 6, 7, 8, 9, 10, 11))
    # backwards compatible: no mech -> every judgment slot is still a stub
    plain = draft_votes(assets)['equities']['5']
    assert all('TODO' in plain[i][1] for i in range(12))


def test_fetch_mech_degrades_to_neutral_when_every_feed_fails(monkeypatch):
    import scripts.prepare_daily as pd

    def boom(*a, **k):
        raise OSError("blocked")
    monkeypatch.setattr(pd, 'fetch_closes', boom)
    out = pd.fetch_mech("2026-10-06")
    for key in ASSET_ORDER:
        for cat in (2, 3, 4):
            side, why = out[key][cat]
            assert side == 'neu' and 'TODO' not in why
    assert 'unavailable' in out['equities'][2][1]
    assert 'unavailable' in out['equities'][4][1]


def test_fetch_mech_with_synthetic_feeds(monkeypatch):
    import scripts.prepare_daily as pd
    n = 120
    dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    series = {
        'RSP': [100 + i * 0.5 for i in range(n)], 'SPY': [100.0] * n,       # breadth rising
        'HYG': [80 - i * 0.1 for i in range(n)], 'IEF': [100.0] * n,         # credit falling
        '^VIX': [25.0] * 100 + [24.0 - i * 0.3 for i in range(20)], '^VXN': [20.0] * n, '^RVX': [22.0] * n,
        '^GVZ': [18.0] * n,
    }
    monkeypatch.setattr(pd, 'fetch_closes',
                        lambda t, **k: list(zip(dates, series[t])))
    out = pd.fetch_mech(dates[-1])
    assert out['equities'][2][0] == 'bull'
    assert out['equities'][4][0] == 'bear'
    assert out['equities'][3][0] == 'bull'        # VIX well under its 20d mean and falling
    assert out['gold'][2][0] == out['gold'][3][0] == out['gold'][4][0] == 'neu'

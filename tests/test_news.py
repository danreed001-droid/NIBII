"""News-gap boost helpers - synthetic bars."""
from mtl.news import booster, news_gap_days, recent_gaps


def test_news_gap_needs_open_and_close_up_and_a_strong_close():
    bars = [('2024-01-01', 100, 101, 99, 100),
            ('2024-01-02', 113, 120, 112, 118),   # gap +13%, close +18%, near the high -> yes
            ('2024-01-03', 118, 119, 117, 118),
            ('2024-01-04', 133, 134, 118, 120),   # gap +13% but closes weak (where 0.12) -> no
            ('2024-01-05', 121, 122, 120, 121),
            ('2024-01-08', 130, 131, 125, 126)]   # gap +7% -> no
    assert news_gap_days(bars) == ['2024-01-02']


def test_booster_window_and_recent_gaps():
    cal = [f"2024-01-{d:02d}" for d in range(1, 31)]
    pref = booster({'A': ['2024-01-05']}, cal, window=3)
    assert [k for k in range(len(cal)) if pref('A', k)] == [4, 5, 6]
    assert not pref('B', 5)
    assert recent_gaps({'A': ['2024-01-05'], 'B': ['2024-01-01']}, cal, 6, window=3) == {'A': '2024-01-05'}

"""mtl/growth_rank.py + the render section: pure logic, no network."""
from datetime import date, timedelta

from mtl import growth_rank
from mtl.documents import NON_DOCUMENT_FILES
from scripts.render_html import growth_rank_section


def _rows(start, n, step):
    """n weekday closes from `start`, each `step` (fractional) above the last."""
    out, d, px = [], start, 100.0
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d.isoformat(), px))
            px *= 1 + step
        d += timedelta(days=1)
    return out


def test_ranks_best_gain_first_and_sums_ranks():
    start = date(2025, 1, 6)
    steps = {'NQ=F': 0.004, 'ES=F': 0.003, 'DX-Y.NYB': 0.002, 'CL=F': 0.001, 'GC=F': 0.0, 'ZN=F': -0.001}
    rows = {t: _rows(start, 400, s) for t, s in steps.items()}
    grids = growth_rank.build(rows, date(2026, 12, 31))
    for view, n in (('weekly', growth_rank.WEEKS), ('daily', growth_rank.DAYS)):
        g = grids[view]
        assert len(g['rows']) == n
        assert [t for t, _ in g['assets']] == [t for t, _ in growth_rank.GRID_ASSETS]  # fixed column order
        for row in g['rows']:
            assert [row['cells'][t]['rank'] for t, _ in growth_rank.GRID_ASSETS] == [1, 2, 3, 4, 5, 6]
        assert g['rankSum']['NQ=F'] == n and g['rankSum']['ZN=F'] == 6 * n
        assert g['rows'][0]['period'] > g['rows'][-1]['period']  # newest first


def test_daily_skips_days_not_every_asset_traded():
    start = date(2025, 1, 6)
    rows = {t: _rows(start, 400, 0.001) for t, _ in growth_rank.GRID_ASSETS}
    holiday = rows['ES=F'][-5][0]
    rows['ES=F'] = [r for r in rows['ES=F'] if r[0] != holiday]
    g = growth_rank.build(rows, date(2026, 12, 31))['daily']
    assert holiday not in [r['period'] for r in g['rows']]
    assert all(r['n'] == 6 for r in g['rows'])


def test_section_renders_both_views_and_is_empty_without_data():
    rows = {t: _rows(date(2025, 1, 6), 400, 0.001 * i) for i, (t, _) in enumerate(growth_rank.GRID_ASSETS)}
    html = growth_rank_section(growth_rank.build(rows, date(2026, 12, 31)))
    assert 'id="growthRank"' in html
    assert 'data-view="weekly"' in html and 'data-view="daily"' in html
    assert '--gr-bg-range' in html and '--gr-bg-sigma' in html
    assert growth_rank_section(None) == ''


def test_growth_rank_json_is_not_a_ledger_document():
    assert 'growth_rank.json' in NON_DOCUMENT_FILES

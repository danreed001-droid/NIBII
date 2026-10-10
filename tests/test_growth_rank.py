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


def test_history_file_is_aligned_to_one_weekday_calendar():
    rows = {'NQ=F': [('2026-01-02', 100.0), ('2026-01-03', 99.0), ('2026-01-05', 101.234567)],
            'GC=F': [('2026-01-05', 2000.0)]}
    h = growth_rank.history(rows)
    assert h['days'] == ['2026-01-02', '2026-01-05']          # Saturday dropped
    assert h['closes']['NQ=F'] == [100.0, 101.235] and h['closes']['GC=F'] == [None, 2000.0]
    assert [a[0] for a in h['assets']] == ['NQ=F', 'GC=F']


def test_section_has_the_end_date_picker():
    from scripts.render_html import growth_rank_section
    grids = growth_rank.build({'NQ=F': [(f'2026-0{m}-{d:02d}', 100.0 + m + d) for m in range(1, 8) for d in range(1, 28)]},
                              date(2026, 7, 31))
    html = growth_rank_section(dict(fetchedAt='2026-07-31T21:00:00Z', **grids))
    assert 'class="gr-date"' in html and 'max="2026-07-31"' in html and 'growth_history.json' in html


def test_overlay_keeps_the_last_sessions_plus_a_base_day():
    rows = {t: _rows(date(2025, 1, 6), 300, 0.001) for t, _ in growth_rank.GRID_ASSETS}
    rows['CL=F'] = rows['CL=F'][:100]                      # oil stops early: still drawn, padded with None
    h = growth_rank.history(rows)
    ov = growth_rank.overlay(h)
    assert len(ov['days']) == growth_rank.OVERLAY_DAYS + 1 and ov['days'][-1] == h['days'][-1]
    assert all(len(c) == len(ov['days']) for c in ov['closes'].values())
    assert 'CL=F' not in ov['closes']                       # nothing in the window -> left out
    assert [a[0] for a in ov['assets']] == [t for t, _ in growth_rank.GRID_ASSETS if t != 'CL=F']
    end = h['days'][200]
    assert growth_rank.overlay(h, end=end)['days'][-1] == end   # same slice the page makes for a picked date
    assert growth_rank.overlay(h, end='2000-01-01') is None and growth_rank.overlay(None) is None


def test_section_draws_the_overlay_chart_only_with_overlay_data():
    rows = {t: _rows(date(2025, 1, 6), 400, 0.001 * i) for i, (t, _) in enumerate(growth_rank.GRID_ASSETS)}
    grids = growth_rank.build(rows, date(2026, 12, 31))
    assert 'class="gr-ov"' not in growth_rank_section(grids)
    html = growth_rank_section(dict(grids, overlay=growth_rank.overlay(growth_rank.history(rows))))
    assert 'class="gr-ov"' in html and 'data-ov="' in html and 'gr-ov-mode' in html and "'gr-end'" in html

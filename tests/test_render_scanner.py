"""docs/scanner.html - the Top 5 Strongest dashboard - embeds its data as JSON."""
import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location(
    'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
render_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_scanner)

SCAN = dict(generatedAt='2026-10-03T03:22:15+00:00', asOf='2026-10-02',
            holdings=[dict(t='EVIL', n='</script><script>alert(1)</script>', sec='X', rank=1)],
            table=[], trades=[], curves={}, years={}, stats={})


def test_data_is_embedded_and_cannot_close_the_script_block():
    page = render_scanner.render(SCAN)
    start = page.index('id="scan-data">') + len('id="scan-data">')
    blob = page[start:page.index('</script>', start)]
    assert json.loads(blob)['holdings'][0]['n'] == SCAN['holdings'][0]['n']
    assert '__DATA__' not in page


def test_page_links_to_the_ledger_and_the_backtests():
    page = render_scanner.render(SCAN)
    assert 'href="index.html"' in page and 'href="backtest.html"' in page


def test_page_has_the_plan_section_and_tolerates_old_data_without_it():
    page = render_scanner.render(SCAN)
    assert 'id="alloc"' in page and 'id="mix-seg"' in page and 'id="assets"' in page
    assert "if (!P || !SL)" in page          # scans without plan data still render


def test_holding_cards_open_a_swing_chart_panel():
    page = render_scanner.render(SCAN)
    assert 'id="swpanel"' in page and 'function drawSwing' in page
    assert "h.chart ?" in page            # cards without chart data stay plain


def test_page_has_the_human_calls_model():
    page = render_scanner.render(SCAN)
    for needle in ('id="choices"', 'id="call-save"', 'id="rec"', "nibii-calls-v1", 'id="call-import"'):
        assert needle in page
    assert "if (!P || !SL)" in page and "!HU || !HU.days.length" in page   # old data without the series still renders


def test_calls_sync_to_the_repo_and_ranges_filter_the_record():
    page = render_scanner.render(SCAN)
    assert "docs/my_calls.json" in page and "api.github.com/repos/" in page and "my_calls.json?t=" in page
    assert 'id="r-from"' in page and 'id="rr-from"' in page
    assert "m: 'del'" in page          # removals sync as tombstones, not silent deletes


def test_calls_can_swap_or_drop_stocks():
    page = render_scanner.render(SCAN)
    assert 'id="picks"' in page and 'Drop → cash' in page and 'function sigOf' in page and 'function slotsFor' in page


def test_on_deck_cards_open_their_own_swing_chart():
    page = render_scanner.render(SCAN)
    assert 'id="swpanel2"' in page and "openSwing(c.getAttribute('data-t'), 'swpanel2')" in page


def test_calls_are_submitted_as_a_github_issue():
    page = render_scanner.render(SCAN)
    assert 'id="call-submit"' in page and '/issues/new?title=' in page and 'Calls intake workflow' in page


def test_page_offers_the_bear_guard_mix():
    page = render_scanner.render(SCAN)
    assert "m === 'guard' ? 'Guard'" in page and 'bear guard' in page and 'A.guard.weights' in page


def test_cross_asset_growth_grid_from_the_main_page():
    page = render_scanner.render(SCAN)
    assert '__GROWTH__' not in page
    if os.path.exists(render_scanner.GROWTH_PATH):
        assert 'id="growthRank"' in page and 'Cross-asset growth ranking' in page
    assert '__GROWTH__' not in render_scanner.render(SCAN, growth='')


def test_weekly_grid_has_the_overlay_chart():
    page = render_scanner.render(SCAN, growth='')
    assert 'id="heat-ov"' in page and 'window.mtlOverlay' in page and "mtlOverlay(box, { title: 'Top '" in page
    assert '__OVLIB__' not in page


def test_page_has_the_3d_price_volume_chart():
    page = render_scanner.render(SCAN, growth='')
    assert 'id="pv"' in page and 'plotly.js-dist-min@2.35.2' in page and 'D.pv3d' in page


def test_rotation_explains_the_whipsaw_switch():
    page = render_scanner.render(SCAN)
    assert 'function whipNote(RT)' in page and 'Whipsaw switch' in page
    assert 'whipsaw switch' in page and 'whipTag(RT)' in page and 'Until Oct 16, 2026 only half the account moved' in page


def test_page_flags_the_choppy_market_watch():
    page = render_scanner.render(SCAN)
    assert 'function chopNote(C)' in page and 'trendNote(RT.trendWatch) + chopNote(RT.chop)' in page
    assert 'Choppy-market watch' in page and 'choppy-market watch ON: the plan moved' in page
    assert 'choppy market: the plan is whipsawing (info only)' in page


def test_warning_shows_breadth_and_scores_calls_against_the_plan():
    page = render_scanner.render(SCAN)
    assert 'function breadthNote(RT)' in page and 'breadthNote(RT) + warnCallNote(RT)' in page
    assert 'always staying in the plan' in page


def test_page_has_the_five_year_winners_research_section():
    page = render_scanner.render(SCAN)
    assert 'id="winners"' in page and '__RESEARCH__' not in page
    assert page.index('id="winners"') < page.index('<footer>')


def test_wall_street_tests_explain_each_number():
    ws = dict(asOf='2026-10-13', period='Jan 2000 – Oct 2026', plan='the plan', previous='the old plan', source='audit',
              scorecard=[dict(k='sharpe', plan='0.98', prev='0.96', spy='0.41'), dict(k='nope', plan='1')],
              monteCarlo=dict(paths=20000, horizons=['5 years', '10 years'], rows=[dict(k='beatSpy', v=['96%', '99%']),
                                                                                   dict(k='beatPrev', v=['69%', '77%'])]),
              other=[dict(k='pbo', v='17%', n=580)])
    out = render_scanner.wallst_html(ws)
    assert 'Wall Street tests' in out and 'Sharpe ratio' in out and 'Above 1 is excellent' in out and 'nope' not in out
    assert 'Chance of beating SPY' in out and '96%' in out and 'Chance of beating the previous plan' in out and '20,000' in out
    assert 'a 17% chance that the best-looking version is a fluke' in out
    assert render_scanner.wallst_html(dict(scorecard=[])) == ''
    page = render_scanner.render(SCAN)
    assert '__WALLST__' not in page and 'id="wallst"' in page     # the committed data file is on the page


def test_track_record_comes_from_the_backtest_and_carries_on_with_the_scan(tmp_path):
    track = dict(source='point-in-time backtest', start='2000-01-03', end='2000-01-05',
                 series={'rotation': [['2000-01-03', 100.0], ['2000-01-04', 90.0], ['2000-01-05', 99.0]],
                         'strategy': [['2000-01-03', 100.0], ['2000-01-05', 80.0]]},
                 stats={'rotation': dict(annual=0.3, maxDD=-0.1), 'strategy': dict(annual=0.1, maxDD=-0.2)})
    path = tmp_path / 'track.json'
    path.write_text(json.dumps(track))
    scan = dict(SCAN, curves={'strategy': [['2000-01-05', 50.0], ['2000-01-06', 55.0]],
                              'rotation': [['2000-01-05', 200.0], ['2001-01-02', 220.0]],
                              'cushion': [['2000-01-05', 1.0]], 'calls': [['2000-01-05', 1.0]]},
                years={'cushion': {'2000': 0.5}}, stats={'strategy': dict(annual=0.9, maxDD=-0.05)})
    out = render_scanner.with_track_record(scan, path=str(path))
    # the backtest line, then the scan's own moves after the backtest ends (+10% from Jan 5)
    assert out['curves']['rotation'] == [['2000-01-03', 100.0], ['2000-01-04', 90.0], ['2000-01-05', 99.0], ['2001-01-02', 108.9]]
    assert out['years']['rotation'] == {'2000': -0.01, '2001': 0.1}
    assert out['curves']['strategy'][-1] == ['2000-01-06', 88.0]
    assert 'cushion' not in out['curves'] and 'calls' not in out['curves'] and 'cushion' not in out['years']
    assert out['stats']['strategy']['annual'] == 0.1 and out['track']['stats']['rotation']['maxDD'] == -0.1
    assert render_scanner.with_track_record(scan, path=str(tmp_path / 'missing.json')) is scan


def test_bottom_of_the_page_has_the_track_record_refresh_button():
    page = render_scanner.render(SCAN)
    i = page.index('id="trk-refresh"')
    assert page.index('id="trk-card"') < i < page.index('<footer>')
    assert 'actions/workflows/track-refresh.yml' in page[i:page.index('</a>', i)]
    assert os.path.exists(os.path.join(os.path.dirname(__file__), '..', '.github', 'workflows', 'track-refresh.yml'))


def test_page_installs_as_an_app_and_asks_search_engines_to_skip_it():
    page = render_scanner.render(SCAN)
    head = page[:page.index('<style>')]
    assert 'rel="manifest" href="manifest.webmanifest"' in head and "serviceWorker.register('sw.js')" in head
    assert '<meta name="robots" content="noindex">' in head
    docs = os.path.join(os.path.dirname(__file__), '..', 'docs')
    man = json.load(open(os.path.join(docs, 'manifest.webmanifest')))
    assert man['start_url'] == 'scanner.html' and man['display'] == 'standalone'
    sizes = {i['sizes'] for i in man['icons']}
    assert {'192x192', '512x512'} <= sizes
    for i in man['icons']:
        assert os.path.exists(os.path.join(docs, i['src']))
    assert os.path.exists(os.path.join(docs, 'sw.js'))


def test_rebalance_banner_explains_the_call():
    page = render_scanner.render(SCAN)
    assert 'function callWhy(pm)' in page and 'callWhy(pm)' in page and 'callWhy(pm2)' in page
    assert '.banner .why' in page
    for s in ('narrow-market cash week', 'No stock swaps', 'Closest to the edge', 'blow-off exit: its last month',
              'surge exit: it closed', 'news boost: it gapped up', 'best-ranked stock not held', 'not gold or bonds, because over 3 months', 'otherwise DBMF'):
        assert s in page


def test_rotation_explains_the_rebound_rule():
    page = render_scanner.render(SCAN)
    assert 'function reboundNote(RT)' in page and 'reboundNote(RT) + pricebreakNote(RT)' in page and '7. Rebound rule' in page
    assert 'In stocks because of the rebound rule' in page and "rebound: 'rebound rule: back in stocks'" in page


def test_rotation_explains_the_price_break_rule():
    page = render_scanner.render(SCAN)
    assert 'function pricebreakNote(RT)' in page and '8. Price-break rule' in page
    assert "pricebreak: 'price-break rule: SPY broke its 100-day average'" in page and "'pricebreak-end': 'price-break stay over'" in page


def test_your_record_shows_recent_weeks_and_counts_cash_as_earning_nothing():
    page = render_scanner.render(SCAN)
    assert 'var REC_WEEKS = 8;' in page and "'rr-more'" in page
    assert 'cash earns nothing (no T-bills)' in page and 'cash earns the T-bill rate' not in page


def test_wall_street_tests_show_back_to_the_peak_and_the_deflated_sharpe():
    rc = dict(cut=0.15, end='2026-10-06', count=2, years=26.7, median=5.8, medianDown=3.7, medianUp=2.5, newHighs=802, gapMedianDays=2,
              gap90Days=19, now=dict(below=-0.0133, since='2026-09-25'),
              longest=dict(plan=dict(months=24, peak='2001-05-21', back='2003-05-14'), spy=dict(months=79, peak='2000-03-24', back='2006-10-26')),
              drops=[dict(peak='2001-05-21', low='2002-06-13', back='2003-05-14', depth=-0.3358, down=12.7, up=11.0, total=23.8),
                     dict(peak='2025-03-24', low='2025-04-08', back='2025-05-09', depth=-0.2307, down=0.5, up=1.0, total=1.5)])
    ws = dict(period='Jan 2000 – Oct 2026', asOf='2026-10-16', scorecard=[dict(k='under', plan='24 months', prev='24 months', spy='79 months')],
              recovery=rc, monteCarlo=dict(paths=20000, horizons=['5 years', '10 years', '20 years'], rows=[dict(k='under', v=['11 months', '15 months', '21 months'])]),
              other=[dict(k='dsr', v='99.94%', n=1081, luck='0.64', sharpe='1.27')])
    h = render_scanner.wallst_html(ws)
    assert 'Back to the peak' in h and 'May 2001' in h and 'May 2003' in h and '−34%' in h and 'SPY waited <b>79 months</b>' in h
    assert '1.3% below its high of Sep 2026' in h
    assert 'Typical longest wait for a new high' in h and 'Deflated Sharpe ratio (1,081 versions)' in h
    assert render_scanner.recovery_html({}) == ''


def test_add_news_button_opens_the_events_form():
    from mtl.events import ADD_URL
    page = render_scanner.render(SCAN)
    assert f'<a class="bt add" href="{ADD_URL}" target="_blank"' in page and '__ADD_URL__' not in page


def test_events_search_embeds_the_events_safely(tmp_path):
    p = tmp_path / 'ev.json'
    p.write_text(json.dumps(dict(events=[
        dict(d='2026-10-16', what='</script><script>alert(1)</script> __DATA__', src='added by you', day=-0.01, month=None,
             link='javascript:alert(1)'),
        dict(d='2008-09-15', what='Lehman bankruptcy', src='curated', day=-0.048, month=-0.203, link='https://x.test/a')])))
    sec = render_scanner.events_html(str(p))
    assert '<script>alert' not in sec and '__DATA__' not in sec and 'id="ev-q"' in sec
    assert 'SHOW = 5;' in sec and "w.className = 'clamp'" in sec   # a fixed ceiling: 5 hits, two lines each
    blob = sec[sec.index('id="ev-data">') + len('id="ev-data">'):sec.index('</script>')]
    rows = json.loads(blob)
    assert rows[0][1].startswith('</script>') and rows[0][2] == 'added by you' and rows[0][6] == ''
    assert rows[1][5] == 'september sep 15 2008 lehman bankruptcy' and rows[1][6] == 'https://x.test/a'
    page = render_scanner.render(SCAN)
    assert page.index('id="events-find"') < page.index('Your plan') and '__EVENTS__' not in page


def test_wide_net_watch_lists_the_strongest_assets_and_breakouts():
    W = dict(asOf='2026-10-19', spyScore=0.05, n=40,
             rows=[dict(t='SLV', name='silver', score=0.42, beats=True, r1m=0.08, offHigh=0.0, nearHigh=True, breakout='2026-10-17'),
                   dict(t='EWZ', name='Brazil', score=0.21, beats=True, r1m=-0.02, offHigh=-0.06, nearHigh=False, breakout=None)],
             breakouts=[dict(t='SLV', name='silver', score=0.42, breakout='2026-10-17'),
                        dict(t='URA', name='uranium', score=0.03, breakout='2026-10-16')])
    html = render_scanner.widenet_html(dict(plan=dict(auto=dict(wideNet=W))))
    assert 'id="widenet"' in html and 'Wide net' in html and 'the strongest of 40 assets the plan never holds' in html
    assert 'Breakout after a base' in html and '<b>SLV</b>' in html and '+42%' in html
    assert 'Also breaking out after a base:</b> URA (uranium, +3%)' in html
    assert render_scanner.widenet_html(dict(plan=dict(auto=dict(wideNet=None)))) == ''


def test_rotation_explains_the_two_scale_buy_rules():
    page = render_scanner.render(SCAN)
    assert 'function fractalNote(RT)' in page and 'pricebreakNote(RT) + fractalNote(RT);' in page and '9. Two-scale buy rules' in page
    assert '<b>Buy freeze</b> for the next' in page and '<b>Green light</b> for the next' in page

import json
from datetime import date

import pytest

from mtl import health


def test_add_dedupes_and_recent_keeps_two_weeks(tmp_path):
    e = []
    assert health.add(e, '2026-10-01', 'scan', 'old', at='2026-10-01T22:00:00+00:00')
    assert health.add(e, '2026-10-16', 'scan', 'TLT stops', at='2026-10-16T22:00:00+00:00')
    assert not health.add(e, '2026-10-16', 'scan', 'TLT stops')
    assert health.add(e, '2026-10-19', 'run', 'Scanner run failed', at='2026-10-19T23:00:00+00:00')
    got = health.recent(e, '2026-10-19')
    assert [x['text'] for x in got] == ['Scanner run failed', 'TLT stops']


def test_save_prunes_and_a_corrupt_log_raises(tmp_path):
    p = tmp_path / 'log.json'
    assert health.load(str(p)) == []
    e = [dict(d='2026-01-02', src='scan', text='a', at=''), dict(d='2026-10-16', src='scan', text='b', at='')]
    kept = health.save(e, str(p), today=date(2026, 10, 19))
    assert [x['text'] for x in kept] == ['b'] and json.load(open(p))['entries'][0]['text'] == 'b'
    p.write_text('{"entries": [')
    with pytest.raises(ValueError):
        health.load(str(p))


def test_issues_section_lists_last_two_weeks_or_says_none():
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    scan = dict(asOf='2026-10-16', track=dict(end='2026-10-16'))
    rs.IGNITION_PATH = '/nonexistent'
    e = [dict(d='2026-10-01', src='scan', text='too old', at=''), dict(d='2026-10-15', src='run', text='Scanner run failed', at='')]
    out = rs.issues_html(scan, e, today=date(2026, 10, 19))
    assert 'Scanner run failed' in out and 'too old' not in out and 'Next big thing scan is from no date' in out
    rs.IGNITION_PATH = os.path.join(os.path.dirname(__file__), 'nope.json')
    out = rs.issues_html(dict(asOf='2026-10-16', track={}), [], today=date(2026, 10, 19))
    assert 'track record' in out


def test_runtime_check_warns_six_months_before_end_of_life():
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'check_runtime', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'check_runtime.py'))
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    assert cr.end_of_life(13) == date(2029, 10, 1)
    eol = cr.end_of_life(__import__('sys').version_info.minor)
    assert cr.main(date(eol.year - 1, 1, 1)) == 0 and cr.main(date(eol.year, 6, 1)) == 1


def test_watchdog_reads_the_last_closed_session():
    import importlib.util, os
    from datetime import datetime, timezone
    spec = importlib.util.spec_from_file_location(
        'check_scanner_fresh', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'check_scanner_fresh.py'))
    cf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cf)
    assert cf.last_closed(datetime(2026, 10, 20, 13, 31, tzinfo=timezone.utc)) == '2026-10-19'   # Tue morning
    assert cf.last_closed(datetime(2026, 10, 19, 13, 31, tzinfo=timezone.utc)) == '2026-10-16'   # Mon morning
    assert cf.last_closed(datetime(2026, 10, 20, 2, 20, tzinfo=timezone.utc)) == '2026-10-19'    # backup run Mon evening


def test_issues_card_shows_the_newest_five_and_links_the_rest():
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    rs.IGNITION_PATH = '/nonexistent'
    scan = dict(asOf='2026-10-16', track=dict(end='2026-10-16'))   # adds the stale side-scan line on top
    e = [dict(d=f'2026-10-{d:02d}', src='scan', text=f'problem <{d}>', at='') for d in range(6, 19)]
    card = rs.issues_html(scan, e, today=date(2026, 10, 19))
    assert card.count('<li>') == 5 and 'problem &lt;18&gt;' in card and 'problem &lt;14&gt;' not in card
    assert '+ 9 more · see all' in card and 'href="issues.html"' in card and 'class="clamp"' in card
    page = rs.issues_page(scan, e, today=date(2026, 10, 19))
    assert page.count('<li>') == 14 and 'problem &lt;6&gt;' in page and '14 issues' in page
    few = rs.issues_html(scan, e[-2:], today=date(2026, 10, 19))
    assert few.count('<li>') == 3 and 'see all' not in few
    assert 'href="issues.html">issues page →' in few and 'href="issues.html">issues page →' in rs.issues_html(dict(asOf='2026-10-16', track={}), [], today=date(2026, 10, 19))

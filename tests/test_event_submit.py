"""The market events page's "Add news" form -> data/my_events.json."""
import pytest

from scripts.add_event_from_issue import apply, parse_issue_form

TODAY = '2026-10-18'


def body(date='2026-10-16', what='Regional bank\nfails', link='https://news.test/a', action='Add'):
    return (f"### Date\n\n{date or '_No response_'}\n\n### What happened\n\n{what}\n\n"
            f"### Link\n\n{link or '_No response_'}\n\n### Add or remove\n\n{action}\n")


def test_add_then_remove():
    doc = dict(events=[])
    assert apply(parse_issue_form(body()), doc, 7, TODAY) == 'added 2026-10-16: Regional bank fails'
    assert doc['events'] == [dict(d='2026-10-16', what='Regional bank fails', link='https://news.test/a', issue=7)]
    with pytest.raises(ValueError, match='already'):
        apply(parse_issue_form(body()), doc, 8, TODAY)
    assert apply(parse_issue_form(body(action='Remove', what='regional bank  FAILS', link='')), doc, 9, TODAY) \
        == 'removed 2026-10-16: regional bank FAILS'
    assert doc['events'] == []


def test_empty_date_is_today_and_link_is_optional():
    doc = dict(events=[])
    apply(parse_issue_form(body(date='', link='')), doc, 1, TODAY)
    assert doc['events'] == [dict(d=TODAY, what='Regional bank fails', issue=1)]


@pytest.mark.parametrize('kw, msg', [
    (dict(date='16/10/2026'), 'YYYY-MM-DD'),
    (dict(date='2026-10-19'), 'outside'),
    (dict(link='javascript:alert(1)'), 'http'),
    (dict(what='x' * 301), 'under 300'),
    (dict(action='Remove'), 'nothing you added'),
])
def test_rejected(kw, msg):
    with pytest.raises(ValueError, match=msg):
        apply(parse_issue_form(body(**kw)), dict(events=[]), 1, TODAY)


def test_page_links_your_item_and_has_the_add_button():
    from mtl.events import ADD_URL
    from scripts.major_events import render
    page = render(dict(updated='2026-10-18', events=[
        dict(d='2026-10-16', what='Bank <fails>', src='added by you', link='https://news.test/a?b=1&c=2', day=-0.031, month=None),
        dict(d='2026-10-15', what='Bad link', src='added by you', link='javascript:alert(1)', day=None, month=None)]))
    assert '<a href="https://news.test/a?b=1&amp;c=2" target="_blank" rel="noopener">Bank &lt;fails&gt;</a>' in page
    assert 'javascript:' not in page
    assert f'href="{ADD_URL}"' in page and '<span class="tag">added by you</span>' in page


def test_page_rows_carry_search_text_and_moves_for_the_filters():
    import re
    from scripts.major_events import render
    page = render(dict(updated='2026-10-18', events=[
        dict(d='2020-03-16', what='Fed cuts to zero + QE', src='curated', day=-0.1094, month=0.037),
        dict(d='2026-10-16', what='My <note>', src='added by you', day=None, month=None)]))
    rows = re.findall(r'<tr data-s="([^"]*)"([^>]*)>', page)
    assert rows[0] == ('october oct 16 2026 my &lt;note&gt; added by you', '')
    assert rows[1] == ('march mar 16 2020 fed cuts to zero + qe ', ' data-day="-0.1094" data-month="0.037"')
    assert 'id="q" type="search"' in page and 'id="min"' in page and page.count('<section class="yr">') == 2

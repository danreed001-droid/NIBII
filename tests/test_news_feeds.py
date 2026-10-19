from mtl import news_feeds as nf

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Stocks slide as yields jump - Reuters</title><source url="x">Reuters</source><link>http://a</link>
<pubDate>Fri, 16 Oct 2026 21:30:00 GMT</pubDate></item>
<item><title>Late item</title><link>http://b</link><pubDate>Sat, 17 Oct 2026 02:00:00 GMT</pubDate></item>
</channel></rss>"""

STATEMENT = ('<p>In support of its goals, the Committee decided to raise the target range for the federal funds rate by '
             '1/4 percentage point to 3&#8209;3/4 to 4 percent.</p>')


def test_rss_items_get_new_york_dates_and_publishers():
    items = nf.parse_rss(RSS, 'Google News')
    assert items[0] == dict(d='2026-10-16', t='Stocks slide as yields jump', src='Reuters', link='http://a', feed='Google News')
    assert items[1]['d'] == '2026-10-16'   # 2am GMT Saturday is Friday evening in New York


def test_fed_statement_decisions():
    assert nf.decision(STATEMENT) == ('raise', 3.75, 4.0)
    held = 'the Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent.'
    assert nf.decision(held) == ('maintain', 3.5, 3.75)
    cut = 'decided to lower the target range for the federal funds rate by 1/2 percentage point to 4-3/4 to 5 percent.'
    assert nf.decision(cut) == ('lower', 4.75, 5.0)
    assert nf.decision('<p>No decision here.</p>') is None


def test_one_feed_failing_leaves_the_others_and_stale_feeds_are_reported():
    doc = dict(feeds={'Google News': '2026-10-10'}, items=[])

    def get(url):
        if 'google' in url:
            raise OSError('blocked')
        return RSS
    bad = nf.collect(doc, '2026-10-18', get)
    assert [b[0] for b in bad] == ['Google News'] and doc['feeds']['MarketWatch'] == '2026-10-18' and doc['items']
    assert nf.stale(doc, '2026-10-18') == ['Google News']

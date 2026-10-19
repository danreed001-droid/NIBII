from mtl import events as ev


def cal_spy(moves, start=100.0):
    cal = [f'2026-10-{i + 1:02d}' if i < 31 else f'2026-11-{i - 30:02d}' for i in range(len(moves) + 1)]
    spy = [start]
    for m in moves:
        spy.append(spy[-1] * (1 + m))
    return cal, spy


def test_big_move_takes_the_days_headline_and_runs_are_idempotent():
    cal, spy = cal_spy([0.001] * 5 + [-0.031] + [0.001] * 3)
    news = [dict(date=cal[6], impact='Medium', direction='Bullish', event='Something minor'),
            dict(date=cal[6], impact='High', direction='Bearish', event='Bank fails; contagion fears')]
    evs = []
    ev.auto(evs, cal, spy, {}, news, since=cal[0])
    assert [e['what'] for e in evs] == ['S&P 500 −3.1% in a day: Bank fails (news log)']
    ev.auto(evs, cal, spy, {}, news, since=cal[0])
    assert len(evs) == 1


def test_vix_spike_only_on_the_first_close_above_30():
    cal, spy = cal_spy([0.0] * 8)
    vix = {d: 20.0 for d in cal}
    vix[cal[4]] = 33.0; vix[cal[5]] = 35.0
    evs = []
    ev.auto(evs, cal, spy, vix, [], since=cal[1])
    assert [(e['d'], e['src']) for e in evs] == [(cal[4], 'auto: VIX')]


def test_fed_decisions_but_not_talk_about_them():
    assert ev.FED.search('Fed raises rates 25bp to 3.75-4.00%')
    assert ev.FED.search('Federal Reserve cuts its policy rate by half a point')
    assert not ev.FED.search('Odds of an October Fed rate hike jump after hot CPI')
    assert not ev.FED.search('Fed minutes: most participants favor another hike')


def test_reactions_fill_the_month_once_it_exists():
    cal, spy = cal_spy([0.01] * 30)
    evs = [dict(d=cal[2], what='x', src='curated', day=None, month=None), dict(d=cal[20], what='y', src='curated', day=None, month=None)]
    ev.reactions(evs, cal, spy)
    assert evs[0]['day'] == 0.01 and evs[0]['month'] is not None and evs[1]['month'] is None


def test_feed_headline_when_the_news_log_has_none_and_fed_from_its_statement():
    cal, spy = cal_spy([0.001] * 5 + [0.03] + [0.001] * 3)
    heads = [dict(d=cal[6], t='Mortgage tips for retirees', src='MarketWatch', feed='MarketWatch', link=''),
             dict(d=cal[6], t='Stocks surge as Fed signals rate cuts', src='Reuters', feed='Google News', link='')]
    fed = [dict(d=cal[3], action='lower', lo=3.5, hi=3.75), dict(d=cal[4], action='maintain', lo=3.5, hi=3.75)]
    evs = []
    ev.auto(evs, cal, spy, {}, [], since=cal[0], headlines=heads, fed=fed)
    whats = [e['what'] for e in sorted(evs, key=lambda e: e['d'])]
    assert whats == ['Fed cuts rates to 3.5–3.75% (FOMC statement)',
                     'S&P 500 +3.0% in a day: Stocks surge as Fed signals rate cuts (Reuters via Google News)']


def test_a_headline_that_arrives_later_fills_in_the_event():
    cal, spy = cal_spy([0.001] * 5 + [-0.03] + [0.001] * 3)
    evs = []
    ev.auto(evs, cal, spy, {}, [], since=cal[0])
    assert evs[0]['what'] == 'S&P 500 −3.0% in a day'
    heads = [dict(d=cal[6], t='Stocks tumble as oil spikes on Iran strikes', src='MarketWatch', feed='MarketWatch', link='')]
    ev.auto(evs, cal, spy, {}, [], since=cal[0], headlines=heads)
    assert len(evs) == 1 and evs[0]['what'].endswith('Stocks tumble as oil spikes on Iran strikes (MarketWatch)')


def test_your_items_are_copied_in_kept_and_removed_with_the_file():
    evs = [dict(d='2026-10-01', what='Old one', src='added by you', day=0.01, month=None),
           dict(d='2026-10-01', what='Curated', src='curated', day=0.01, month=None)]
    ev.sync_mine(evs, [dict(d='2026-10-01', what='New one', link='https://x.test/a'),
                       dict(d='2026-10-02', what='Second')])
    mine = sorted((e['d'], e['what'], e.get('link')) for e in evs if e['src'] == 'added by you')
    assert mine == [('2026-10-01', 'New one', 'https://x.test/a'), ('2026-10-02', 'Second', None)]
    assert any(e['what'] == 'Curated' for e in evs)
    evs[-1]['day'] = 0.02
    ev.sync_mine(evs, [dict(d='2026-10-02', what='Second')])
    assert [(e['what'], e['day']) for e in evs if e['src'] == 'added by you'] == [('Second', 0.02)]

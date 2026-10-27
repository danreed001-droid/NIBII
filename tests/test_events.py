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


def test_shared_search_matches_words_and_moves():
    import json, shutil, subprocess
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    js = ev.MATCH_JS + """
var el = function (v) { return {value: v}; };
var f = function (q, per, dir, min) { return evFilter(el(q), el(per), el(dir), el(min)); };
var s = 'march mar 16 2020 fed cuts to zero + qe';
console.log(JSON.stringify([
  evMatch(s, -0.109, 0.037, f('fed  QE', 'day', 'any', '')),
  evMatch(s, -0.109, 0.037, f('fed bank', 'day', 'any', '')),
  evMatch(s, -0.109, 0.037, f('', 'day', 'down', '-5')),
  evMatch(s, -0.109, 0.037, f('', 'day', 'up', '5')),
  evMatch(s, -0.109, 0.037, f('', 'month', 'any', '5')),
  evMatch(s, -0.109, undefined, f('', 'month', 'up', '')),
  evOn(f('', 'day', 'any', '')), evOn(f('', 'day', 'up', ''))]));"""
    out = subprocess.run([node, '-e', js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [True, False, True, False, False, False, False, True]


def test_gold_and_bonds_moves_use_one_source_per_window():
    cal = [f'2004-11-{d:02d}' for d in range(1, 29)] + [f'2004-12-{d:02d}' for d in range(1, 29)]
    k = cal.index('2004-11-19')
    fut = [100.0 + i for i in range(len(cal))]
    etf = [None] * k + [40.0 + i * 0.4 for i in range(len(cal) - k)]       # starts on the switch day, another price level
    evs = [dict(d='2004-11-10', what='before'), dict(d='2004-11-22', what='after'), dict(d='2004-12-20', what='recent')]
    ev.side_moves(evs, cal, dict(gold=[(0, fut), (k, etf)], bonds=[(0, [None] * len(cal))]))
    assert evs[0]['gold'] == dict(day=round(109 / 108 - 1, 4), month=round(130 / 108 - 1, 4))   # futures at both ends
    assert evs[1]['gold']['day'] == round(41.2 / 40.8 - 1, 4)                                 # the ETF once it exists
    assert evs[2]['gold']['month'] is None                                                    # not a month yet
    assert 'bonds' not in evs[0]                                                              # no prices: left as saved
    evs[0]['bonds'] = dict(day=0.01, month=0.02)
    ev.side_moves(evs, cal, dict(bonds=[(0, fut), (k, [])]))                                  # one source failed tonight
    assert evs[0]['bonds'] == dict(day=0.01, month=0.02)


def test_macro_signals_join_from_signal_since_once_each_and_can_share_a_day():
    from datetime import date, timedelta
    d, cal = date(2024, 7, 1), []
    while len(cal) < 460:
        if d.weekday() < 5:
            cal.append(d.isoformat())
        d += timedelta(days=1)
    spy = [100.0] * len(cal)
    k = next(i for i, x in enumerate(cal) if x >= '2026-02-02')
    oil = dict(zip(cal, [60.0] * k + [95.0] * (len(cal) - k)))            # up 58% in a year from Feb 2, 2026
    evs = []
    ev.auto(evs, cal, spy, {}, [], since=ev.AUTO_SINCE, macro=dict(oil=oil))
    assert [(e['d'], e['src'], e['type']) for e in evs] == [(cal[k], ev.SIGNAL_SRC, 'Oil up 50% in a year')]
    ev.auto(evs, cal, spy, {}, [], since=ev.AUTO_SINCE, macro=dict(oil=oil))
    assert len(evs) == 1                                                   # re-running adds nothing
    assert ev.add(evs, cal[k], 'Dollar down 10% in a year: down 11%', ev.SIGNAL_SRC)   # a second signal that day
    assert not ev.add(evs, cal[k], 'Oil up 50% in a year: again', ev.SIGNAL_SRC)

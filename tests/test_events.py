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
    assert [e['what'] for e in evs] == ['S&P 500 −3.1% in a day: Bank fails']
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

"""Friday alert text from the scan data."""
import importlib.util
import os

spec = importlib.util.spec_from_file_location('weekly_alert', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'weekly_alert.py'))
alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alert)


def scan(**kw):
    base = dict(signalDay=True, asOf='2026-10-02', tradeDate='2026-10-05', changes={'sell': [], 'buy': []},
                holdings=[{'t': 'AAA', 'rank': 1}, {'t': 'BBB', 'rank': 2}],
                sleeve={'held': 'DBC', 'prevHeld': 'DBC', 'n': 'Commodities'},
                plan={'auto': {'split': '100/0', 'prevSplit': '100/0', 'down': [],
                               'steps': {'split': '100/0', 'prevSplit': '100/0'},
                               'guard': {'bear': False, 'prevBear': False, 'share': 0.5, 'weights': [1, 0, 0], 'prevWeights': [1, 0, 0]}}})
    base.update(kw)
    return base


def test_quiet_weeks_and_weekdays_send_nothing():
    assert alert.build(scan()) is None
    assert alert.build(scan(signalDay=False, changes={'sell': ['X'], 'buy': ['Y']})) is None


def test_swaps_and_guard_flip_make_one_alert():
    s = scan(changes={'sell': ['MRVL'], 'buy': ['MU']})
    s['plan']['auto']['guard'].update(bear=True, spyNow=500.0, spyYearAgo=550.0, weights=[0.5, 0, 0.5])
    title, body = alert.build(s, 'someone')
    assert title.startswith('Trade Mon Oct 5') and 'sell MRVL' in title and 'bear guard ON' in title
    assert '@someone' in body and '| Guard | 50% | 0% | 50% |' in body and 'MU' in body


def test_boost_list_changes_are_listed_when_they_differ():
    s = scan(changes={'sell': ['MRVL'], 'buy': ['MU']})
    s['plan']['auto']['boost'] = dict(split='100/0', prevSplit='100/0', sell=['MRVL'], buy=['NBIS'],
                                      holdings=['AAA', 'BBB', 'NBIS'])
    title, body = alert.build(s)
    assert 'boost: sell MRVL, buy NBIS' in title and 'Boost list:** AAA, BBB, NBIS' in body and '| Boost | 100% |' in body
    assert 'If you follow Boost (news boost list)' in body and '| Boost 100% | 100% | 0% | 0% |' in body
    # same trades as the plain model -> no separate boost line
    s['plan']['auto']['boost'].update(buy=['MU'], holdings=['AAA', 'BBB'])
    title, body = alert.build(s)
    assert 'boost' not in title


def test_cushion_switch_is_an_action():
    from scripts.weekly_alert import build
    s = scan()
    s['plan']['auto']['cushion'] = dict(share=0.75, split='75/25', prevSplit='100/0', ma=150, spyGap=-0.031)
    title, body = build(s, None)
    assert 'cushion 75/25' in title and 'Boost + cushion:** 100/0 → **75/25**' in body
    assert 'move 25% of the stocks into the sleeve' in body and '| Boost + cushion | 75% | 25% | 0% |' in body


def test_blowoff_list_trades_are_listed():
    s = scan()
    s['plan']['auto']['boostx'] = dict(holdings=['AAA', 'CCC'], prev=['AAA', 'BBB'], sell=['BBB'], buy=['CCC'], blown=['BBB'])
    title, body = alert.build(s, None)
    assert 'If you follow Boost 100% or Boost + cushion' in body and 'sell BBB (blow-off exit)' in body and 'buy CCC' in body
    assert 'boost 100%: sell BBB, buy CCC' in title and 'Boost 100% / cushion list:** AAA, CCC' in body


def test_blowoff_exit_switching_on_or_off_is_announced():
    s = scan()
    s['plan']['auto']['boostx'] = dict(mult=2.0, ma=150, armedAt=True, prevArmed=False, sell=[], buy=[])
    title, body = alert.build(s, None)
    assert 'blow-off exit on' in title and '**Blow-off exit ON**' in body
    s['plan']['auto']['boostx'].update(armedAt=False, prevArmed=True)
    title, body = alert.build(s, None)
    assert 'blow-off exit off' in title and 'kept through blow-offs again' in body and '150-day average' in body
    s['plan']['auto']['boostx'].update(armedAt=True, prevArmed=True)
    assert alert.build(s, None) is None


def test_midweek_blowoff_sale_sends_its_own_alert():
    s = scan(signalDay=False, asOf='2026-10-06')
    s['plan']['auto']['boostx'] = dict(mult=2.0, ma=150, midweek=dict(date='2026-10-07', sell=['BBB'], buy=['CCC'], blown=['BBB']))
    title, body = alert.build(s, 'someone')
    assert title == 'Trade Wed Oct 7: Boost 100% / cushion blow-off exit: sell BBB (blow-off exit), buy CCC'
    assert 'fired at today\'s close (Tue Oct 6)' in body and '@someone' in body
    s['plan']['auto']['boostx']['midweek'] = None
    assert alert.build(s, None) is None

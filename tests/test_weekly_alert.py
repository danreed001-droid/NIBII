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
    # same trades as the plain model -> no separate boost line
    s['plan']['auto']['boost'].update(buy=['MU'], holdings=['AAA', 'BBB'])
    title, body = alert.build(s)
    assert 'boost' not in title

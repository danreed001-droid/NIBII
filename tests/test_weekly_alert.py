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


def test_call_sleeve_line_lists_best_case_limits():
    s = scan()
    s['plan']['auto']['boostx'] = dict(holdings=['AAA', 'CCC'], prev=['AAA', 'BBB'], sell=['BBB'], buy=['CCC'], blown=[],
                                       callSpread=0.04, calls={'CCC': dict(price=100.0, rv=0.6, maxIv=0.48, strike=120,
                                                                         expiry='2027-04-16', maxPrice=8.25)})
    title, body = alert.build(s, None)
    assert 'Call sleeve (20% OTM, best-case pricing only, ~10% of the account' in body and 'buy CCC $120 call exp Fri Apr 16 2027' in body
    assert 'pay at most $8.25 ($825/contract), only if IV <= 48% and bid/ask <= 4% of mid' in body and 'sell your BBB call' in body


def test_friday_table_has_calls_column_and_call_sleeve_table():
    s = scan(changes={'sell': ['MRVL'], 'buy': ['MU']})
    s['plan']['auto']['boost'] = dict(split='100/0', prevSplit='100/0', holdings=['AAA'])
    s['plan']['auto']['boostx'] = dict(holdings=['AAA'], callSleeve=0.2, callBudget=0.1, callSpread=0.04,
                                       calls={'AAA': dict(price=100.0, rv=0.6, maxIv=0.48, strike=120, expiry='2027-04-16',
                                                          maxPrice=8.25, quote=dict(ok=None))})
    title, body = alert.build(s, None)
    assert '| Mix | Top 5 | Sleeve | SPY | Calls |' in body and '| Auto | 100% | 0% | 0% | 0% |' in body
    assert '| Boost 100% + calls | 80% | 0% | 0% | 20% (about 10% in calls, rest T-bills) |' in body
    assert '| AAA | $120 | Fri Apr 16 2027 | $8.25 | $825 | 48% | check at the open |' in body


def test_cushion_check_line_shows_both_signals():
    from scripts.weekly_alert import build, cushion_check
    s = scan()
    s['plan']['auto']['cushion'] = dict(share=0.75, split='75/25', prevSplit='100/0', ma=150, spyGap=-0.031, credit=-0.012, creditLook=21)
    title, body = build(s, None)
    assert 'junk vs quality bonds -1.2% over 21 sessions' in body and 'both say weak' in body
    assert '**Cushion check:** SPY -3.1% vs its 150-day average' in body and '→ **on** (both weak)' in body
    calm = cushion_check(dict(split='100/0', ma=150, spyGap=-0.02, credit=0.004, creditLook=21))
    assert '→ **off**' in calm and 'credit calm' in calm


def rot(**kw):
    base = dict(mode='boost', held='boost', trade=None, log=[])
    base.update(kw)
    return base


def test_rotation_switch_midweek_sends_its_own_alert():
    s = scan(signalDay=False, asOf='2026-10-07')
    s['plan']['auto']['rotation'] = rot(mode='GLD', held='boost', trade='2026-10-08', log=[['2026-10-07', 'boost', 'GLD', 'rotate']])
    title, body = alert.build(s, 'someone')
    assert title.startswith('Trade Thu Oct 8: Boost + rotation → GLD')
    assert 'buy **GLD**' in body and 'steepest gradient' in body and '@someone' in body


def test_rotation_back_to_stocks_on_friday_and_out_of_stocks_note():
    s = scan()
    s['plan']['auto']['rotation'] = rot(mode='boost', held='TLT', trade='2026-10-05', log=[['2026-10-02', 'TLT', 'boost', 'above']])
    title, body = alert.build(s)
    assert 'rotation → stocks' in title and 'sell TLT' in body and '150-day average' in body
    assert '| Boost + rotation | 100% |' in body
    s = scan(changes={'sell': ['MRVL'], 'buy': ['MU']})
    s['plan']['auto']['rotation'] = rot(mode='GLD', held='GLD')
    title, body = alert.build(s)
    assert "out of stocks (GLD): the stock changes below don't apply" in body and '100% in GLD' in body
    s = scan()
    s['plan']['auto']['rotation'] = rot(mode='GLD', held='GLD')
    assert alert.build(s) is None     # holding GLD, nothing else to do: no alert


def test_downtrend_warning_is_info_only():
    s = scan(signalDay=False, asOf='2026-10-07')
    s['plan']['auto']['rotation'] = rot(warn='TLT', prevWarn=None, ma=150, confirm=15)
    title, body = alert.build(s)
    assert title.startswith('Warning Wed Oct 7') and 'TLT is rising most steeply' in body and 'not a signal' in body
    s['plan']['auto']['rotation'] = rot(warn='TLT', prevWarn='TLT')
    assert alert.build(s) is None          # already on yesterday: no repeat
    s = scan()
    s['plan']['auto']['rotation'] = rot(warn='GLD', prevWarn=None)
    title, body = alert.build(s)
    assert 'downtrend warning (GLD)' in title


def test_rsi_warning_alert_on_its_first_day():
    s = scan(signalDay=False, asOf='2026-10-07')
    s['plan']['auto']['rotation'] = rot(rsiWarn=dict(on=True, prevOn=False, date='2026-10-06', line=44.0, rsi=38.5, gap=-0.01))
    title, body = alert.build(s)
    assert title == 'Warning Wed Oct 7: SPY RSI broke its support line' and 'line 44.0' in body and '-1.0%' in body
    s['plan']['auto']['rotation']['rsiWarn']['prevOn'] = True
    assert alert.build(s) is None


def test_midweek_surge_sale_names_the_surge_exit():
    s = scan(signalDay=False, asOf='2026-10-06')
    s['plan']['auto']['boostx'] = dict(mult=2.0, ma=150, surge=dict(up=0.05, vol=4.0, delay=5),
                                       midweek=dict(date='2026-10-07', sell=['BBB'], buy=['CCC'], blown=[], surged=['BBB']))
    title, body = alert.build(s, None)
    assert title == 'Trade Wed Oct 7: Boost 100% / cushion surge exit: sell BBB (surge exit), buy CCC'
    assert 'The surge exit fired' in body and '4x its 50-day average volume 5 trading days ago' in body and 'blow-off exit fired' not in body


def test_scheduled_surge_sale_is_a_heads_up():
    s = scan()
    s['plan']['auto']['boostx'] = dict(sell=[], buy=[], surge=dict(up=0.05, vol=4.0, delay=5, pending=[
        dict(t='DELL', d='2026-10-05', up=0.08, x=4.6, sell='2026-10-12')]))
    title, body = alert.build(s, None)
    assert '**Surge exit scheduled**' in body and 'DELL closed +8% on 4.6x its normal volume on Mon Oct 5' in body and 'Mon Oct 12' in body


def whip(**kw):
    w = dict(on=True, half='GLD', held=None, trade='2026-10-05', look=126, loss=0.65, n=9, lost=7, share=0.78,
             chg={'TLT': -0.02, 'GLD': 0.06, 'SPY': 0.01})
    w.update(kw)
    return w


def test_whipsaw_half_switch_on_friday():
    s = scan()
    s['plan']['auto']['rotation'] = rot(whip=whip())
    title, body = alert.build(s)
    assert 'whipsaw half → GLD' in title
    assert 'sell half the Boost list, buy **GLD**' in body and '7 of the Boost list' in body
    assert '50% the Boost 100% stock list, 50% GLD' in body and '| Boost + rotation | 50% (+50% GLD, whipsaw half) |' in body


def test_whipsaw_half_moving_midweek_sends_its_own_alert():
    s = scan(signalDay=False)
    s['plan']['auto']['rotation'] = rot(whip=whip(held='GLD', half='SPY'))
    title, body = alert.build(s)
    assert title == 'Trade Mon Oct 5: Boost + rotation whipsaw half → SPY'
    assert 'sell GLD, buy **SPY** with that half' in body

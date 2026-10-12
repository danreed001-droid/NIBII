"""scripts/ignition_alert.py - the issue that pings the owner when an Ignition flags."""
import importlib.util
import os
from datetime import date

spec = importlib.util.spec_from_file_location(
    'ignition_alert', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'ignition_alert.py'))
ignition_alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ignition_alert)

TODAY = date(2026, 10, 9)
ROW = dict(t='CRDO', n='Credo', ind='Semiconductors', kind='ignition', score=7.0, chg=0.48, gap=0.30, vr=6.8, rs=97,
           offHigh=0.0, repeats=2, group=True)
REC = dict(d='2026-10-09', t='CRDO', n='Credo', kind='ignition', days=0, since=0.0, close=10.0, low=9.0, sma20=8.0)
SCAN = dict(generatedAt='2026-10-09T21:40:00+00:00', asOf='2026-10-09', statsFrom='2023-10-04',
            today=[dict(ROW, t='SNOW', kind='breakout'), ROW],
            recent=[REC], market=dict(spy=600, sma50=590, sma200=550),
            stats={'ignition': dict(up50=0.23, ex60=-0.07), 'all': dict(up50=0.15)})


def test_alerts_on_an_ignition_and_mentions_the_owner():
    title, body = ignition_alert.build(SCAN, 'someone', TODAY)
    assert title == 'Ignition alert: CRDO (Fri Oct 9 close)'
    assert body.startswith('@someone ') and '| **CRDO** |' in body and '6.8x' in body and 'group move' in body
    assert 'SNOW' not in body                   # breakouts don't alert
    assert 'ignitions 23%' in body and 'any liquid stock 15%' in body
    assert '**CRDO**: Repeat gap' in body and 'flag-day low 9.00' in body and '**Market:**' in body


def test_turnarounds_alert_too():
    scan = dict(SCAN, today=[dict(ROW, t='CVNA', kind='turnaround')], recent=[dict(REC, t='CVNA', kind='turnaround')])
    title, body = ignition_alert.build(scan, None, TODAY)
    assert title.startswith('Ignition alert: CVNA') and '| Turnaround |' in body


def test_no_alert_without_ignitions_or_from_a_stale_scan():
    assert ignition_alert.build(dict(SCAN, today=[dict(ROW, kind='breakout')]), 'x', TODAY) is None
    assert ignition_alert.build(SCAN, 'x', date(2026, 10, 12)) is None   # scan step failed: yesterday's file


def test_main_writes_nothing_when_there_is_no_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(ignition_alert, 'SCAN', str(tmp_path / 'missing.json'))
    monkeypatch.setattr('sys.argv', ['x', str(tmp_path)])
    ignition_alert.main()
    assert not (tmp_path / 'alert_title.txt').exists()


def test_a_new_hot_industry_alerts_even_without_flags():
    th = dict(ind='Marine Shipping', heat=95, up=0.8, dUp=0.3, leaders=['FRO', 'DAC'], emerging=True, newTop=True)
    title, body = ignition_alert.build(dict(SCAN, today=[], themes=[th]), 'x', TODAY)
    assert title == 'Theme alert: Marine Shipping heating up (Fri Oct 9 close)' and 'FRO, DAC' in body
    assert ignition_alert.build(dict(SCAN, today=[], themes=[dict(th, newTop=False)]), 'x', TODAY) is None

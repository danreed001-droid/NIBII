"""mtl/ignition.py - the ignition / turnaround / breakout flags and their hit rates."""
import importlib.util
import os
from datetime import date

import numpy as np
import pandas as pd

from mtl import ignition as ig

spec = importlib.util.spec_from_file_location(
    'render_scanner', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'render_scanner.py'))
render_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_scanner)

N = 400


def frames(paths, gaps=(), vol=1e6):
    """Wide OHLCV from close paths {ticker: [close...]}; gaps = [(ticker, row, gap, vol_mult)]."""
    idx = pd.bdate_range('2024-01-01', periods=N)
    C = pd.DataFrame(paths, index=idx)
    O = C.shift(1).fillna(C)
    H, L = C * 1.005, O.where(O < C, C) * 0.995
    V = pd.DataFrame(vol, index=idx, columns=C.columns)
    for t, r, g, m in gaps:
        O.iloc[r, C.columns.get_loc(t)] = C[t].iat[r - 1] * (1 + g)
        C.iloc[r, C.columns.get_loc(t)] = C[t].iat[r - 1] * (1 + g) * 1.03
        H.iloc[r, C.columns.get_loc(t)] = C[t].iat[r] * 1.002
        L.iloc[r, C.columns.get_loc(t)] = O[t].iat[r] * 0.99
        V.iloc[r, C.columns.get_loc(t)] = vol * m
    return O, H, L, C, V


def test_gap_on_heavy_volume_in_an_uptrend_is_an_ignition():
    up = list(20 * np.exp(np.linspace(0, 1.0, N)))
    flat = [20.0] * N
    O, H, L, C, V = frames({'UP': up, 'FLAT': flat, 'UP2': up}, gaps=[('UP', 350, 0.10, 5)])
    res = ig.compute(O, H, L, C, V)
    assert res['flags']['ignition']['UP'].iat[350]
    assert not res['flags']['ignition']['UP'].iat[349]
    assert not res['flags']['ignition']['FLAT'].any()
    assert res['repeats']['UP'].iat[351] == 1


def test_small_gap_or_light_volume_is_not_an_ignition():
    up = list(20 * np.exp(np.linspace(0, 1.0, N)))
    O, H, L, C, V = frames({'A': up, 'B': up}, gaps=[('A', 350, 0.04, 5), ('B', 350, 0.10, 1.5)])
    f = ig.compute(O, H, L, C, V)['flags']['ignition']
    assert not f['A'].iat[350] and not f['B'].iat[350]


def test_illiquid_or_penny_stocks_never_flag():
    up = list(2 * np.exp(np.linspace(0, 1.0, N)))   # under $5
    O, H, L, C, V = frames({'P': up, 'Q': up}, gaps=[('P', 350, 0.10, 5)])
    assert not ig.compute(O, H, L, C, V)['flags']['ignition']['P'].any()


def test_options_expiry_and_russell_days_are_mechanical():
    idx = pd.bdate_range('2025-06-01', '2025-07-31')
    m = ig.mechanical_days(idx)
    assert m[pd.Timestamp('2025-06-20')] and m[pd.Timestamp('2025-06-27')] and m[pd.Timestamp('2025-07-18')]
    assert not m[pd.Timestamp('2025-06-23')]


def test_hit_stats_measure_forward_returns():
    up = list(20 * np.exp(np.linspace(0, 1.0, N)))
    O, H, L, C, V = frames({'UP': up, 'X': up}, gaps=[('UP', 260, 0.10, 5)])
    res = ig.compute(O, H, L, C, V)
    evs = ig.events(res['flags'], start_row=252)
    assert (260, 'UP', 'ignition') in evs
    st = ig.hit_stats(C, C['X'], evs)['ignition']
    # the synthetic gap day sits above the path, so the stock falls back: a negative forward return
    assert st['n'] == st['n20'] == 1 and st['ret20'] < 0 and st['mae60'] < 0 and st['beat60'] == 0


def test_score_prefers_setups_repeats_and_nearness_to_high():
    assert ig.score('ignition', 90, 2, 0.0) > ig.score('ignition', 90, 1, 0.0) > ig.score('breakout', 90, 1, 0.0)
    assert ig.score('ignition', 90, 1, -0.02) > ig.score('ignition', 90, 1, -0.3)


SCAN = dict(asOf='2026-10-09', liquid=2500, mechanical=False, statsFrom='2023-10-04', rules=dict(recent=20),
            today=[dict(t='EVIL', n='<script>x</script>', ind='Semis', kind='ignition', score=7.1, chg=0.12, gap=0.09,
                        vr=4.2, rs=95, offHigh=0.0, repeats=2, group=True)],
            recent=[dict(d='2026-10-01', t='ABC', n='Abc', ind='', kind='breakout', days=6, since=0.05, ex=0.03, held=True)],
            groups=[['Semis', ['EVIL', 'XYZ']]],
            stats={'ignition': dict(n=10, ret20=0.01, ex20=0.0, ret60=0.02, ex60=-0.01, ret120=0.05, ex120=0.01,
                                    beat60=0.4, up50=0.3, mae60=-0.12)})


def test_watch_section_renders_and_escapes_names():
    out = render_scanner.ignition_html(SCAN)
    assert 'id="watch"' in out and 'Next big thing watch' in out and 'EVIL' in out
    assert '<script>x' not in out and '&lt;script&gt;' in out
    assert 'Hit rates' in out and '4.2x' in out


def test_watch_section_is_empty_without_a_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(render_scanner, 'IGNITION_PATH', str(tmp_path / 'missing.json'))
    assert render_scanner.ignition_html() == ''


def test_baseline_covers_every_liquid_stock_day():
    up = list(20 * np.exp(np.linspace(0, 1.0, N)))
    O, H, L, C, V = frames({'A': up, 'B': up})
    res = ig.compute(O, H, L, C, V)
    st = ig.baseline(C, C['A'], res['liquid'], 252)
    assert st['n'] == 2 * (N - 252) and st['ex60'] == 0 and 0 < st['ret60'] < 0.2 and st['up50'] == 0


def test_plan_turns_flags_into_actions():
    rec = lambda t, **k: dict(dict(d='2026-10-01', t=t, n=t, kind='ignition', days=5, since=0.05, close=10.5, low=10.0,
                                   sma20=10.2, repeats=1), **k)
    scan = dict(today=[], recent=[rec('NEW', days=0, since=0.0), rec('STOP', close=9.5, since=-0.1),
                                  rec('WIN', since=0.25, close=12.5, sma20=11.0), rec('FADE', since=0.05, close=10.1, sma20=10.3),
                                  rec('OK'), rec('OK', d='2026-09-20'), rec('BRK', kind='breakout')])
    acts = {a['t']: a['act'] for a in ig.plan(scan)}
    assert acts == {'NEW': 'new', 'STOP': 'exit', 'WIN': 'profit', 'FADE': 'trail', 'OK': 'hold'}   # old breakouts skipped
    assert [a['t'] for a in ig.plan(scan)][0] == 'NEW'


def test_market_note_cuts_size_below_the_200_day():
    assert ig.market_note(dict(spy=500, sma50=520, sma200=540))[0] == 'bad'
    assert ig.market_note(dict(spy=530, sma50=535, sma200=500))[0] == 'warn'
    assert ig.market_note(dict(spy=560, sma50=540, sma200=500))[0] == 'ok'


def test_themes_rank_the_industry_that_is_heating_up_first():
    up = list(20 * np.exp(np.linspace(0, 1.0, N)))
    flat = list(20 + np.sin(np.linspace(0, 20, N)))
    paths = {f'H{i}': up for i in range(8)}
    paths.update({f'C{i}': flat for i in range(8)})
    O, H, L, C, V = frames(paths)
    res = ig.compute(O, H, L, C, V)
    industry = {**{f'H{i}': 'Hot' for i in range(8)}, **{f'C{i}': 'Cold' for i in range(8)}}
    rows = ig.themes(C, res, industry, {'H1', 'H2'}, C['C0'])
    assert [r['ind'] for r in rows] == ['Hot', 'Cold']
    assert rows[0]['flags'] == 2 and rows[0]['up'] == 1.0 and rows[0]['heat'] > rows[1]['heat']


def test_new_leaders_are_industries_that_just_entered_the_top():
    hist = [['d1', ['A', 'B']], ['d2', ['A', 'B']]]
    assert ig.new_leaders(['C', 'A'], hist, top=2) == ['C']
    assert ig.new_leaders(['C'], []) == []

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

"""mtl/you2.py - You-2: the viewer's own stocks on the default plan's timing; and its intake."""
import importlib.util
import os

import pandas as pd

from mtl import you2

CAL = [d.date().isoformat() for d in pd.bdate_range('2026-10-12', periods=8)]
PX = {'AAA': {d: 10.0 * (1.1 ** i) for i, d in enumerate(CAL)}, 'BBB': {d: 20.0 for d in CAL}}
GLD = {'GLD': {d: 100.0 * (1.05 ** i) for i, d in enumerate(CAL)}}
DOC = {'you2': {CAL[1]: {'stocks': ['AAA', 'BBB'], 'at': 'x'}}}


def test_list_is_bought_at_the_close_after_its_day_and_then_drifts():
    c = dict(you2.picks_curve(you2.entries_of(DOC), PX, CAL, CAL[0]))
    assert c[CAL[1]] == 1.0 and c[CAL[2]] == 1.0          # decided at CAL[1]'s close, bought at CAL[2]'s
    assert abs(c[CAL[3]] - (0.5 * 1.1 + 0.5)) < 1e-9       # half in AAA (+10%), half in BBB (flat)


def test_follows_the_plan_out_of_stocks_and_back():
    modes = {d: 'boost' for d in CAL}
    modes[CAL[3]] = 'GLD'                                  # the plan holds gold after CAL[4]'s close
    cv = dict(you2.you2_curve(you2.entries_of(DOC), PX, GLD, CAL, modes, {}, start=CAL[0]))
    stocks = dict(you2.picks_curve(you2.entries_of(DOC), PX, CAL, CAL[0]))
    g = GLD['GLD'][CAL[5]] / GLD['GLD'][CAL[4]]
    assert abs(cv[CAL[5]] / cv[CAL[4]] - g * (1 - you2.SWITCH_COST)) < 1e-9   # in gold, then back (0.1% a switch)
    assert abs(cv[CAL[6]] / cv[CAL[5]] - stocks[CAL[6]] / stocks[CAL[5]]) < 1e-9   # back in the stocks
    assert you2.holding(modes, {}, CAL, 4) == 'GLD' and you2.holding(modes, {CAL[5]: 'TLT'}, CAL, 6) == 'TLT'


def test_block_reports_the_list_holding_and_missing_tickers():
    doc = {'you2': {CAL[1]: {'stocks': ['AAA', 'ZZZ'], 'at': 'x'}}}
    b = you2.block(doc, PX, GLD, CAL, {d: 'boost' for d in CAL}, {}, [[d, 1.0] for d in CAL], {d: 1.0 for d in CAL}, 6, start=CAL[0])
    assert b['stocks'] == ['AAA', 'ZZZ'] and b['missing'] == ['ZZZ'] and b['holds'] == 'stocks' and b['curve']


def test_intake_reads_you2_lists_and_ignores_junk():
    spec = importlib.util.spec_from_file_location('intake', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'intake_calls.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    body = 'x\n```json\n{"you2": {"2026-10-15": {"stocks": ["dell", "MRNA", "bad ticker", "MRNA"], "at": "2026-10-15T14:00:00Z"}, "nope": {}}}\n```'
    assert m.parse_you2(body) == {'2026-10-15': {'stocks': ['DELL', 'MRNA'], 'note': '', 'at': '2026-10-15T14:00:00Z'}}


def test_fading_stock_waits_in_cash_until_a_week_end_check_clears_it():
    cal = [d.date().isoformat() for d in pd.bdate_range('2026-10-12', periods=10)]   # Mon Oct 12 .. Fri Oct 23
    px = {'AAA': {d: 10.0 for d in cal}, 'BBB': {d: 10.0 * 1.1 ** i for i, d in enumerate(cal)}}
    entries = {cal[0]: ['AAA', 'BBB']}
    skip = lambda t, k: t == 'BBB' and cal[k] < cal[4]               # BBB fades until Friday Oct 16's close
    c = dict(you2.picks_curve(entries, px, cal, cal[0], skip=skip))
    assert abs(c[cal[3]] - 1.0) < 1e-12                              # half in AAA (flat), half in cash: no gain yet
    assert abs(c[cal[5]] - 1.0) < 1e-12                              # cleared at Friday's check, bought at Monday's close
    assert abs(c[cal[6]] - (0.5 + 0.5 * 1.1)) < 1e-9                 # then its half rises with it
    plain = dict(you2.picks_curve(entries, px, cal, cal[0]))
    assert plain[cal[3]] > 1.0                                       # without the filter BBB's half rose


def _intake():
    spec = importlib.util.spec_from_file_location('intake', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'intake_calls.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_named_plans_get_their_own_record_and_notes():
    doc = {'you2': DOC['you2'],
           'plans': {'Tech rebound': {CAL[1]: {'stocks': ['AAA'], 'note': 'semis held their lows', 'at': 'x'},
                                      CAL[4]: {'stocks': ['BBB'], 'note': 'took profits', 'at': 'y'}},
                     'Empty': {CAL[2]: {'m': 'del', 'at': 'z'}}}}
    assert you2.plan_names(doc) == ['Tech rebound'] and you2.tickers_of(doc) == {'AAA', 'BBB'}
    mp = you2.plans_block(doc, PX, GLD, CAL, {d: 'boost' for d in CAL}, {}, [[d, 1.0] for d in CAL], {d: 1.0 for d in CAL}, 6)
    p = mp['Tech rebound']
    assert p['start'] == CAL[1] and p['stocks'] == ['BBB']
    (d1, s1, n1, r1, pr1), (d2, s2, n2, r2, pr2) = p['entries']
    assert (d1, s1, n1) == (CAL[1], ['AAA'], 'semis held their lows') and n2 == 'took profits'
    assert abs(r1 - (1.1 ** 3 - 1)) < 2e-3 and pr1 == 0.0      # AAA held from CAL[2]'s close to CAL[5]'s: +33%; the plan flat
    assert abs(r2) < 1e-9                                       # BBB (flat) from CAL[5]'s close
    # You-2's block carries its notes too
    assert you2.block(doc, PX, GLD, CAL, {d: 'boost' for d in CAL}, {}, [[d, 1.0] for d in CAL], {d: 1.0 for d in CAL}, 6, start=CAL[0])['entries'][0][2] == ''


def test_intake_reads_named_plans_and_rejects_bad_names():
    m = _intake()
    body = ('```json\n{"plans": {"Tech rebound": {"2026-10-15": {"stocks": ["nvda", "MU"], "note": "semis held", "at": "2026-10-15T14:00:00Z"}},'
            ' "<script>": {"2026-10-15": {"stocks": ["AAA"]}}, "Ok name": {"bad-date": {"stocks": ["AAA"]}}}}\n```')
    assert m.parse_plans(body) == {'Tech rebound': {'2026-10-15': {'stocks': ['NVDA', 'MU'], 'note': 'semis held', 'at': '2026-10-15T14:00:00Z'}}}


def test_intake_merges_plans_into_my_calls(tmp_path, monkeypatch):
    m = _intake()
    path = tmp_path / 'my_calls.json'
    path.write_text('{"app": "nibii-calls", "v": 1, "calls": {}, "you2": {"2026-10-14": {"stocks": ["DELL"], "note": "", "at": "a"}}}')
    monkeypatch.setattr(m, 'PATH', str(path))
    monkeypatch.setenv('ISSUE_BODY', '```json\n{"plans": {"Defensive": {"2026-11-16": {"stocks": ["KO", "PG"], "note": "rates rising", "at": "2026-11-16T15:00:00Z"}}}}\n```')
    m.main()
    import json as _j
    doc = _j.loads(path.read_text())
    assert doc['plans'] == {'Defensive': {'2026-11-16': {'stocks': ['KO', 'PG'], 'note': 'rates rising', 'at': '2026-11-16T15:00:00Z'}}}
    assert doc['you2']['2026-10-14']['stocks'] == ['DELL']


def test_actual_moves_follow_you2_until_the_first_move_then_what_was_moved_into():
    modes = {d: 'boost' for d in CAL}
    y2 = you2.you2_curve(you2.entries_of(DOC), PX, GLD, CAL, modes, {}, start=CAL[0])
    pk = you2.picks_curve(you2.entries_of(DOC), PX, CAL, CAL[0])
    mv = {CAL[3]: ('cash', 'took profits'), CAL[5]: ('GLD', ''), '2026-10-24': ('plan', '')}   # a Saturday after CAL's end
    mc, y, c = dict(you2.mine_curve(y2, pk, GLD, CAL, mv)), dict(y2), 1 - you2.SWITCH_COST
    assert all(abs(mc[d] - y[d]) < 1e-12 for d in CAL[:3])                     # with You-2 before the first move
    assert abs(mc[CAL[3]] - y[CAL[3]] * c) < 1e-12                              # out at the move's own close
    assert abs(mc[CAL[4]] - mc[CAL[3]]) < 1e-12 and abs(mc[CAL[5]] - mc[CAL[3]] * c) < 1e-12   # flat in cash, then into gold
    g = lambda a, b: GLD['GLD'][b] / GLD['GLD'][a]
    assert abs(mc[CAL[6]] / mc[CAL[5]] - g(CAL[5], CAL[6])) < 1e-12              # gold after CAL[5]'s close
    assert abs(mc[CAL[7]] / mc[CAL[6]] - g(CAL[6], CAL[7]) * c) < 1e-12          # the Saturday move counts at the last close


def test_block_carries_the_actual_line_and_what_you_hold():
    doc = dict(DOC, moves={CAL[3]: {'to': 'cash', 'note': 'nervous', 'at': 'x'}, CAL[4]: {'m': 'del', 'at': 'y'}})
    b = you2.block(doc, PX, GLD, CAL, {d: 'boost' for d in CAL}, {}, [[d, 1.0] for d in CAL], {d: 1.0 for d in CAL}, 6, start=CAL[0])
    assert b['moves'] == [[CAL[3], 'cash', 'nervous']] and b['mineHolds'] == 'CASH' and b['holds'] == 'stocks'
    mine = dict(b['mine'])
    assert mine[CAL[6]] == mine[CAL[4]] and len(b['mine']) == len(b['curve'])
    nb = you2.block(DOC, PX, GLD, CAL, {d: 'boost' for d in CAL}, {}, [[d, 1.0] for d in CAL], {d: 1.0 for d in CAL}, 6, start=CAL[0])
    assert 'mine' not in nb


def test_intake_reads_moves_and_merges_them(tmp_path, monkeypatch):
    m = _intake()
    body = '```json\n{"moves": {"2026-11-13": {"to": "cash", "note": "sold Friday", "at": "2026-11-17T01:00:00Z"}, "2026-11-14": {"to": "yolo"}, "bad": {"to": "cash"}}}\n```'
    assert m.parse_moves(body) == {'2026-11-13': {'to': 'cash', 'note': 'sold Friday', 'at': '2026-11-17T01:00:00Z'}}
    path = tmp_path / 'my_calls.json'
    path.write_text('{"app": "nibii-calls", "v": 1, "calls": {}, "you2": {"2026-10-14": {"stocks": ["DELL"], "note": "", "at": "a"}}}')
    monkeypatch.setattr(m, 'PATH', str(path))
    monkeypatch.setenv('ISSUE_BODY', body)
    m.main()
    import json as _j
    doc = _j.loads(path.read_text())
    assert doc['moves'] == {'2026-11-13': {'to': 'cash', 'note': 'sold Friday', 'at': '2026-11-17T01:00:00Z'}} and doc['you2']['2026-10-14']


def test_a_mix_is_bought_at_the_move_close_and_drifts():
    modes = {d: 'boost' for d in CAL}
    y2 = you2.you2_curve(you2.entries_of(DOC), PX, GLD, CAL, modes, {}, start=CAL[0])
    pk = you2.picks_curve(you2.entries_of(DOC), PX, CAL, CAL[0])
    t = sorted(PX)[0]
    mix = {'GLD': 0.5, t: 0.5}
    mv = {CAL[3]: (mix, 'half and half')}
    mc, y, c = dict(you2.mine_curve(y2, pk, GLD, CAL, mv, prices=PX)), dict(y2), 1 - you2.SWITCH_COST
    assert abs(mc[CAL[3]] - y[CAL[3]] * c) < 1e-12                              # switch cost at the move's close
    v3 = mc[CAL[3]]
    want = v3 * (0.5 * GLD['GLD'][CAL[6]] / GLD['GLD'][CAL[3]] + 0.5 * PX[t][CAL[6]] / PX[t][CAL[3]])
    assert abs(mc[CAL[6]] - want) < 1e-9                                        # buy-and-hold from that close


def test_moves_of_reads_mixes_and_tickers_of_includes_them():
    doc = dict(DOC, moves={'2026-11-23': {'to': 'mix', 'mix': {'TLT': 1, 'MRNA': 1}, 'note': '', 'at': 'x'},
                           '2026-11-24': {'to': 'mix', 'mix': {}, 'note': '', 'at': 'x'}})
    mv = you2.moves_of(doc)
    assert mv == {'2026-11-23': ({'TLT': 0.5, 'MRNA': 0.5}, '')}
    assert {'TLT', 'MRNA'} <= you2.tickers_of(doc)
    assert you2.mix_label({'TLT': 0.5, 'MRNA': 0.5}) in ('50% TLT + 50% MRNA', '50% MRNA + 50% TLT')

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

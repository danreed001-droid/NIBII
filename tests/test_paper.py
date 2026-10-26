"""mtl/paper.py - the default plan's paper record: append-only log, next-close fills, replay check, status."""
from datetime import datetime, timezone

import pandas as pd

from mtl import paper

CAL = [d.date().isoformat() for d in pd.bdate_range('2026-10-12', periods=10)]   # Mon Oct 12 ...
PX = {'AAA': {d: 10.0 * (1.1 ** i) for i, d in enumerate(CAL)}, 'BBB': {d: 20.0 for d in CAL},
      'GLD': {d: 100.0 * (1.02 ** i) for i, d in enumerate(CAL)}, 'SPY': {d: 500.0 * (1.01 ** i) for i, d in enumerate(CAL)}}


def ledger(*decs):
    L = paper.new_ledger('fp1', {})
    L['start'] = CAL[0]
    for i, d in enumerate(decs):
        assert paper.record(L, d, f'{d["d"]}T21:30:00+00:00', 'fp1')
    return L


def test_weights_follow_mode_half_and_list(monkeypatch):
    five = ['A1', 'A2', 'A3', 'A4', 'A5']
    assert paper.weights('boost', None, five) == {t: 0.2 for t in five}
    w = paper.weights('boost', None, ['AAA', 'BBB'])            # empty slots (fading filter) are cash
    assert w['AAA'] == w['BBB'] == 0.2 and abs(w['CASH'] - 0.6) < 1e-12
    assert paper.weights('boost', 'GLD', five[:4]) == {'GLD': 1.0}   # the whipsaw switch moves the whole account
    monkeypatch.setattr(paper, 'WHIP_SHARE', 0.5)                    # the half-switch it replaced (until Oct 16, 2026)
    w = paper.weights('boost', 'GLD', five[:4])
    assert all(abs(w[t] - 0.1) < 1e-12 for t in five[:4]) and abs(w['CASH'] - 0.1) < 1e-12 and w['GLD'] == 0.5
    assert paper.weights('TLT', 'GLD', ['AAA']) == {'TLT': 1.0}
    assert paper.weights('CASH', None, []) == {'CASH': 1.0}
    assert paper.decision(CAL[0], 'GLD', 'TLT', ['AAA'])['half'] is None      # no half outside the stocks


def test_record_is_append_only_and_one_entry_per_day():
    L = ledger(paper.decision(CAL[1], 'boost', None, ['AAA']))
    first = dict(L['entries'][0])
    assert not paper.record(L, paper.decision(CAL[1], 'CASH', None, []), 'later', 'fp1')    # the day is logged
    assert not paper.record(L, paper.decision(CAL[0], 'CASH', None, []), 'later', 'fp1')    # nothing back-dated
    assert L['entries'][0] == first and len(L['entries']) == 1
    assert paper.record(L, paper.decision(CAL[2], 'CASH', None, []), 'x', 'fp2')
    assert [e['fp'] for e in L['entries']] == ['fp1', 'fp2']


def test_decisions_fill_at_the_next_close_with_costs(monkeypatch):
    monkeypatch.setattr(paper, 'SLOTS', 2)                         # a two-stock list fills the account
    L = ledger(paper.decision(CAL[1], 'boost', None, ['AAA', 'BBB']),
               paper.decision(CAL[2], 'boost', None, ['AAA', 'BBB']),
               paper.decision(CAL[3], 'GLD', None, ['AAA', 'BBB']))
    c = dict(paper.account(L['entries'], PX, CAL))
    assert min(c) == CAL[2]                                            # the first fill is CAL[2]'s close
    assert abs(c[CAL[2]] - (1 - paper.SLIP)) < 1e-12                   # buying 100% costs 0.15%
    v2 = 1 - paper.SLIP
    v3 = v2 * (0.5 * 1.1 + 0.5)                                        # AAA +10%, BBB flat; no trade (same holdings)
    assert abs(c[CAL[3]] - v3) < 1e-9
    v4 = v2 * (0.5 * 1.21 + 0.5) * (1 - paper.SLIP * 2)                # marked at CAL[4]'s close, then all sold for gold
    assert abs(c[CAL[4]] - v4) < 1e-9
    assert abs(c[CAL[5]] - v4 * 1.02) < 1e-9                           # then gold's move


def test_cash_is_flat_and_nothing_before_the_first_fill():
    L = ledger(paper.decision(CAL[4], 'CASH', None, ['AAA']))
    c = paper.account(L['entries'], PX, CAL)
    assert c[0][0] == CAL[5] and all(abs(v - 1.0) < 1e-12 for _, v in c)


def test_replay_check_only_compares_entries_under_todays_rules():
    L = ledger(paper.decision(CAL[1], 'boost', None, ['AAA']))
    paper.record(L, paper.decision(CAL[2], 'boost', None, ['AAA']), 'x', 'fp-new')
    replay = lambda d: paper.decision(d, 'CASH', None, [])         # today's code would decide differently
    n, diffs = paper.replay_check(L['entries'], replay, CAL[3], 'fp-new')
    assert n == 1 and [x['d'] for x in diffs] == [CAL[2]]          # the entry under the old rules isn't compared


def test_listed_rule_update_is_not_flagged():
    L = ledger(paper.decision(CAL[1], 'boost', None, ['AAA']))
    paper.record(L, paper.decision(CAL[2], 'boost', None, ['AAA']), 'x', 'fp-new')
    L['updates'] = [dict(since=CAL[2], fingerprint='fp-new', files={}, what='a new filter')]
    b = paper.block(L, PX, CAL, len(CAL) - 1, PX['SPY'], lambda d: None, 'fp-new')
    assert b['rulesChanged'] == [] and b['updates'][0]['what'] == 'a new filter'


def test_replay_check_lists_differences_and_skips_today():
    L = ledger(paper.decision(CAL[1], 'boost', None, ['AAA', 'BBB']), paper.decision(CAL[2], 'CASH', None, []),
               paper.decision(CAL[3], 'boost', None, ['AAA']))
    replay = {CAL[1]: paper.decision(CAL[1], 'boost', None, ['BBB', 'AAA']), CAL[2]: paper.decision(CAL[2], 'GLD', None, [])}
    n, diffs = paper.replay_check(L['entries'], replay.get, CAL[3])
    assert n == 2 and len(diffs) == 1 and diffs[0]['d'] == CAL[2] and 'CASH logged, GLD' in diffs[0]['what']


def test_status_flags_only_against_the_ranges():
    flat = [[d, 1.0] for d in CAL]
    s = paper.status(flat, PX['SPY'])
    assert s['band'] is None and s['flags'] == [] and s['sessions'] == len(CAL) - 1
    crash = [[d, 1.0 if i < 5 else 0.5] for i, d in enumerate(CAL)]
    assert any('deeper than' in f for f in paper.status(crash, PX['SPY'])['flags'])


def test_after_close_uses_new_york_time():
    assert not paper.after_close('2026-10-15', datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc))     # 3pm ET
    assert paper.after_close('2026-10-15', datetime(2026, 10, 15, 21, 20, tzinfo=timezone.utc))        # 5:20pm ET
    assert paper.after_close('2026-10-15', datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc))


def test_block_reports_frozen_rules_and_changes():
    L = ledger(paper.decision(CAL[1], 'boost', None, ['AAA']))
    paper.record(L, paper.decision(CAL[2], 'boost', None, ['AAA']), 'x', 'fp-new')
    b = paper.block(L, PX, CAL, len(CAL) - 1, PX['SPY'], lambda d: None, 'fp-new')
    assert b['frozen']['fingerprint'] == 'fp1' and b['rulesChanged'] == [CAL[2]] and b['entries'] == 2 and b['curve']


def test_corrupt_ledger_raises_and_missing_is_none(tmp_path):
    import pytest
    assert paper.load(str(tmp_path / 'none.json')) is None
    p = tmp_path / 'bad.json'
    p.write_text('{"entries": [')
    with pytest.raises(ValueError):
        paper.load(str(p))


def test_problems_report_gaps_reruns_and_replay_differences():
    cal = ['2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-16']
    ent = [dict(d='2026-10-12', mode='boost', half=None, list=['A']), dict(d='2026-10-14', mode='boost', half=None, list=['A']),
           dict(d='2026-10-16', mode='CASH', half=None, list=[])]
    blk = dict(diffs=[dict(d='2026-10-14', what='mode boost logged, GLD in the replay')], rulesChanged=[], status=dict(flags=[]))
    out = ' '.join(paper.problems(dict(entries=ent), blk, dict(d='2026-10-16', mode='boost', half=None, list=['A']), '2026-10-16', cal))
    assert 'no decision for 2026-10-13, 2026-10-15' in out
    assert 'reads 2026-10-16 differently' in out and 'no longer replays the same' in out
    # logged under earlier rules (a listed update since): a different reading tonight is expected, no warning
    ent[-1]['fp'] = 'old'
    out = ' '.join(paper.problems(dict(entries=ent), dict(blk, fpNow='new'), dict(d='2026-10-16', mode='GLD', half=None, list=[]), '2026-10-16', cal))
    assert 'reads 2026-10-16 differently' not in out and 'no longer replays the same' in out
    out = ' '.join(paper.problems(dict(entries=ent), dict(blk, fpNow='old'), dict(d='2026-10-16', mode='GLD', half=None, list=[]), '2026-10-16', cal))
    assert 'reads 2026-10-16 differently' in out


def test_status_checks_every_horizon_reached():
    n = 300
    cal = [f'd{i:04d}' for i in range(n + 1)]
    # flat for most of the year, then a steep fall in the last 3 months: the 3-month floor must still fire
    curve = [[d, 1.0 if i < n - 63 else 1.0 * (0.997 ** (i - (n - 63)))] for i, d in enumerate(cal)]
    flags = ' '.join(paper.status(curve, {})['flags'])
    assert 'last 3 months' in flags and 'last 12 months' in flags

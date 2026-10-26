import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('membership', os.path.join(ROOT, 'research', 'backtest', 'membership.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def bars(t0, t1):
    return [(d, 1.0, 1.0, 1.0, 1.0) for d in (t0, t1)]


def test_intervals_from_daily_lists_and_later_changes():
    lists = [('2000-01-03', {'AAA', 'BBB'}), ('2001-05-01', {'AAA', 'CCC'}), ('2002-01-02', {'CCC', 'BBB'})]
    iv = M.intervals(lists, changes=[('2003-03-03', 'DDD', 'CCC'), ('1999-01-01', 'OLD', None)])
    assert iv['AAA'] == [['2000-01-03', '2002-01-02']]
    assert iv['BBB'] == [['2000-01-03', '2001-05-01'], ['2002-01-02', None]]
    assert iv['CCC'] == [['2001-05-01', '2003-03-03']]
    assert iv['DDD'] == [['2003-03-03', None]]
    assert 'OLD' not in iv       # changes before the lists' last date are already in them


def test_apply_maps_renames_reused_tickers_and_leaves_unpriced_out():
    lists = [('1998-06-01', {'BLL', 'XYZ', 'GONE'}), ('2005-01-03', {'BLL', 'NEW'})]
    D = dict(bars={'BALL': bars('1998-01-02', '2026-10-01'),        # BLL is Ball, now under BALL
                   'XYZ': bars('2010-01-04', '2026-10-01')},        # XYZ's ticker was reused by a later company
             bench={'SPY': bars('1998-01-02', '2026-10-01')}, names=['BALL'], changes=[])
    delisted = {'XYZ_T': {'bars': bars('1998-01-02', '2005-01-10'), 'vol': {'1998-01-02': 100}},
                'NEW': {'bars': bars('2004-01-02', '2026-10-01')}}
    D2, priced, missing = M.apply(D, lists, {'BLL': 'BALL'}, delisted)
    assert D2['iv']['BALL'] == [[None, None]]
    assert D2['iv']['XYZ_T'] == [[None, '2005-01-03']]
    assert D2['iv']['NEW'] == [['2005-01-03', None]]
    assert 'XYZ' not in D2['iv']            # the later company never gets the old one's membership
    assert missing == [('GONE', '1998-06-01', '2005-01-03')]
    assert priced == 3 and D2['added'] == {} and D2['extra_vol']['XYZ_T'] == {'1998-01-02': 100}


def test_renamed_company_priced_from_its_series_start():
    lists = [('1998-06-01', {'OLD', 'AAA'}), ('2010-01-04', {'AAA'})]
    D = dict(bars={'NEW': bars('2005-12-05', '2026-10-01'), 'AAA': bars('1998-01-02', '2026-10-01'),
                   'OTHER': bars('2003-01-02', '2026-10-01')},
             bench={'SPY': bars('1998-01-02', '2026-10-01')}, names=[], changes=[])
    D2, priced, missing = M.apply(D, lists, {'OLD': 'NEW'}, {})
    assert D2['iv']['NEW'] == [['2005-12-05', '2010-01-04']]   # the renamed series covers the rest of the stretch
    D3, _, missing3 = M.apply(D, [('1998-06-01', {'OTHER', 'AAA'})], {}, {})
    assert 'OTHER' not in D3['iv'] and missing3 == [('OTHER', '1998-06-01', None)]   # never a later company's series


def test_repo_lists_load():
    lists = M.member_lists()
    assert lists[0][0] == '1996-01-02' and all(450 < len(s) < 520 for _, s in lists[::200])

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtl import pickchart  # noqa: E402


def test_build_aligns_tickers_on_shared_dates_and_keeps_the_last_n():
    bars = {'AAA': [('2026-11-1%d' % i, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i) for i in range(0, 5)],
            'BBB': [('2026-11-1%d' % i, 0.5, 0.6, 0.4, 0.55556) for i in range(2, 5)], 'CCC': []}
    d = pickchart.build(bars, {'AAA': 'Alpha'}, n=4, volumes={'AAA': {'2026-11-11': 1500.0}})
    assert d['dates'] == ['2026-11-11', '2026-11-12', '2026-11-13', '2026-11-14']
    assert d['t']['AAA'][0] == [11.0, 12.0, 10.0, 11.5, 1500] and d['t']['AAA'][1][4] is None
    assert d['t']['BBB'][0] is None and d['t']['BBB'][1] == [0.5, 0.6, 0.4, 0.5556, None]
    assert 'CCC' not in d['t'] and d['n'] == {'AAA': 'Alpha'}


def test_load_names_reads_both_index_lists():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nm = pickchart.load_names(root)
    assert nm.get('AAPL') and len(nm) > 400 and nm['TLT'].startswith('Long') and nm['DBMF'] == 'Managed futures'

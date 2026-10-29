import gzip
import json

import pytest

from mtl import backup_prices as bp


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.delenv('PRICE_CACHE', raising=False)
    monkeypatch.delenv('TIINGO_KEY', raising=False)
    bp.reset()
    yield
    bp.reset()


def rows(*closes, start=26):
    return [(f'2026-10-{start + i:02d}', c, c + 1, c - 1, c) for i, c in enumerate(closes)]


def test_text_round_trip():
    r = rows(10.5, 11.25)
    t = bp.to_text(r, {'2026-10-26': 1200})
    assert bp.from_text(t) == (r, {'2026-10-26': 1200})


def test_merge_keeps_older_saved_rows_rescaled_to_join():
    old = bp.to_text(rows(10, 20, 30, start=21), {})        # 21, 22, 23
    new = rows(15, 16, start=22)                              # Yahoo's history now starts on the 22nd, rebased
    got, _ = bp.from_text(bp.merge(old, new, {}))
    assert [r[0] for r in got] == ['2026-10-21', '2026-10-22', '2026-10-23']
    assert got[0][4] == pytest.approx(7.5) and got[1][4] == 15


def test_quote_appends_the_missing_close():
    r, v = bp.append('AAA', rows(10, 11), {}, False, '2026-10-28',
                     quote=('2026-10-28', 11, 13, 10.5, 12.5, 900, 11))
    assert r[-1] == ('2026-10-28', 11.0, 13.0, 10.5, 12.5) and v == {'2026-10-28': 900}
    assert r[:2] == rows(10, 11)


def test_split_between_rescales_the_history():
    r, v = bp.append('AAA', rows(100, 110), {'2026-10-27': 50}, False, '2026-10-28',
                     quote=('2026-10-28', 56, 57, 54, 56, 200, 55))   # 2-for-1: yesterday's close is now 55
    assert [x[4] for x in r] == [50, 55, 56] and v['2026-10-27'] == 100


def test_dividend_rescales_only_the_adjusted_series():
    q = ('2026-10-28', 10, 10, 10, 10, None, 9.9)
    assert bp.append('AAA', rows(9, 10), {}, True, '2026-10-28', quote=q)[0][0][4] == pytest.approx(9 * 0.99)
    assert bp.append('AAA', rows(9, 10), {}, False, '2026-10-28', quote=q)[0][0][4] == 9


def test_no_append_from_an_old_or_early_quote():
    assert bp.append('AAA', rows(10, 11), {}, False, '2026-10-28', quote=('2026-10-27', 1, 1, 1, 1, 1, 1)) is None
    assert bp.append('AAA', rows(10, 11, 12), {}, False, '2026-10-27', quote=('2026-10-28', 1, 1, 1, 1, 1, 1)) is None
    assert bp.append('AAA', rows(10, 11), {}, False, '2026-10-28', quote=None) is None


def test_fred_fills_only_when_it_agrees_on_the_last_day():
    ser = {'2026-10-27': 4.0, '2026-10-28': 4.1}
    r, _ = bp.append('^TNX', rows(3.9, 4.0), {}, False, '2026-10-28', fred_ser=ser)
    assert r[-1] == ('2026-10-28', 4.1, 4.1, 4.1, 4.1)
    assert bp.append('^TNX', rows(39, 40), {}, False, '2026-10-28', fred_ser=ser) is None   # other scale


def test_fill_does_nothing_unless_switched_on():
    out = {'AAA': rows(10)}
    bp.fill(out, ['AAA', 'BBB'], target='2026-10-28')
    assert out == {'AAA': rows(10)} and bp._cache is None


def test_fill_from_saved_copy_and_quotes_then_saves(tmp_path, monkeypatch):
    path = tmp_path / 'p.json.gz'
    with gzip.open(path, 'wt') as f:
        json.dump({'raw': {'BBB': bp.to_text(rows(20, 21), {'2026-10-27': 5})}, 'adj': {}}, f)
    monkeypatch.setenv('PRICE_CACHE', str(path))
    monkeypatch.setenv('TIINGO_KEY', 'x')
    monkeypatch.setattr(bp, '_quotes', {'AAA': ('2026-10-28', 12, 12, 12, 12, 7, 11),
                                        'BBB': ('2026-10-28', 22, 22, 22, 22, 8, 21)})
    out, vol = {'AAA': rows(10, 11)}, {}
    bp.fill(out, ['AAA', 'BBB', 'CCC'], volumes=vol, target='2026-10-28')
    assert out['AAA'][-1][4] == 12 and out['BBB'][-1][4] == 22 and 'CCC' not in out
    assert vol['BBB'] == {'2026-10-27': 5, '2026-10-28': 8}
    u = bp.used()
    assert u['tiingo'] == ['AAA', 'BBB'] and u['cache'] == [] and not u['yahoo_down']
    bp.save()
    with gzip.open(path, 'rt') as f:
        saved = json.load(f)['raw']
    assert bp.from_text(saved['BBB'])[0][-1][0] == '2026-10-28' and 'CCC' not in saved


def test_saved_copy_without_a_quote_is_reported_as_early():
    bp._cache = {'raw': {'BBB': bp.to_text(rows(20, 21), {})}, 'adj': {}}
    bp._quotes = {}
    import os
    os.environ['PRICE_CACHE'] = '/nonexistent/p.json.gz'
    try:
        out = {}
        bp.fill(out, ['BBB'], target='2026-10-28')
    finally:
        del os.environ['PRICE_CACHE']
    assert out['BBB'] == rows(20, 21)
    lines = bp.problems(bp.used(), '2026-10-28')
    assert len(lines) == 1 and 'saved copy' in lines[0] and 'BBB' in lines[0]


def test_yahoo_down_when_most_of_a_large_request_was_missing(monkeypatch):
    monkeypatch.setenv('TIINGO_KEY', 'x')
    tick = [f'T{i}' for i in range(30)]
    bp._quotes = {t: ('2026-10-28', 2, 2, 2, 2, 1, 1) for t in tick}
    out = {t: rows(1, 1) for t in tick[:10]}                   # 10 a day short, 20 up to date
    out.update({t: rows(1, 1, 1) for t in tick[10:]})
    bp.fill(out, tick, target='2026-10-28')
    assert bp.used()['tiingo'] == sorted(tick[:10]) and not bp.used()['yahoo_down']
    out = {t: rows(1, 1) for t in tick}                        # now 40 of 60 asked were short
    bp.fill(out, tick, target='2026-10-28')
    u = bp.used()
    assert u['yahoo_down'] and all(out[t][-1][0] == '2026-10-28' for t in tick)
    lines = bp.problems(u, '2026-10-28')
    assert len(lines) == 1 and 'backup source' in lines[0]


def test_a_skipped_session_is_reported(monkeypatch):
    monkeypatch.setenv('TIINGO_KEY', 'x')
    bp._quotes = {'AAA': ('2026-10-28', 2, 2, 2, 2, 1, 1)}
    out = {'AAA': rows(1)}                                      # stops on the 26th: the 27th is missing
    bp.fill(out, ['AAA'], target='2026-10-28')
    assert [r[0] for r in out['AAA']] == ['2026-10-26', '2026-10-28']
    assert bp.used()['gap'] == ['AAA']
    assert any('skip a session' in x for x in bp.problems(bp.used(), '2026-10-28'))


def test_a_few_filled_closes_stay_off_the_page():
    assert bp.problems({'tiingo': ['IWM'], 'cache': [], 'fred': [], 'gap': []}, '2026-10-28') == []
    many = [f'T{i}' for i in range(12)]
    assert len(bp.problems({'tiingo': many, 'cache': [], 'fred': [], 'gap': []}, '2026-10-28')) == 1

"""The scanner's default universe: fixed ETFs + the S&P 500 csv."""
from mtl.universe import ETFS, default_universe, load_sp500


def test_sp500_csv_is_complete_and_in_yahoo_form():
    sp = load_sp500()
    assert 490 <= len(sp) <= 510
    assert 'AAPL' in sp and 'BRK-B' in sp
    assert not any('.' in s for s in sp)


def test_default_universe_puts_the_etfs_first():
    u = default_universe()
    assert list(u)[:len(ETFS)] == ['XLF', 'XLU', 'XLY', 'EEM', 'GLD', 'SLV']
    assert len(u) == len(ETFS) + len(load_sp500())


from datetime import date

from mtl.universe import ensure_fresh

FAKE = {f"S{i:03d}": (f"Co {i}", 'Tech') for i in range(500)}


def _fetch_ok():
    return FAKE


def _fetch_fails():
    raise OSError("network down")


def _setup(tmp_path, asof):
    path, asof_path = tmp_path / 'sp.csv', tmp_path / 'sp.asof'
    path.write_text("symbol,name,sector\nOLD,Old Co,Tech\nS000,Co 0,Tech\n")
    if asof:
        asof_path.write_text(asof + "\n")
    return str(path), str(asof_path)


def test_fresh_list_is_left_alone(tmp_path):
    path, asof = _setup(tmp_path, '2026-10-01')
    assert not ensure_fresh(path, asof, today=date(2026, 10, 5), fetch=_fetch_fails, log=lambda m: None)
    assert list(load_sp500(path)) == ['OLD', 'S000']


def test_stale_list_is_refreshed_and_changes_are_reported(tmp_path):
    path, asof = _setup(tmp_path, '2026-09-01')
    logs = []
    assert ensure_fresh(path, asof, today=date(2026, 10, 5), fetch=_fetch_ok, log=logs.append)
    assert len(load_sp500(path)) == 500
    assert open(asof).read().strip() == '2026-10-05'
    assert 'removed OLD' in logs[0] and 'added S001' in logs[0]


def test_missing_refresh_date_counts_as_stale(tmp_path):
    path, asof = _setup(tmp_path, None)
    assert ensure_fresh(path, asof, today=date(2026, 10, 5), fetch=_fetch_ok, log=lambda m: None)


def test_failed_or_short_download_keeps_the_saved_list(tmp_path):
    path, asof = _setup(tmp_path, '2026-09-01')
    for bad in (_fetch_fails, lambda: dict(list(FAKE.items())[:10])):
        logs = []
        assert not ensure_fresh(path, asof, today=date(2026, 10, 5), fetch=bad, log=logs.append)
        assert list(load_sp500(path)) == ['OLD', 'S000'] and 'failed' in logs[0]


from mtl.universe import ensure_fresh_ndx, load_ndx, momentum_universe


def test_momentum_universe_is_sp500_plus_nasdaq_only_members():
    u = momentum_universe(refresh=False)
    assert 'AAPL' in u and 'ASML' in u and 'XLF' not in u
    assert len(u) == len(set(load_sp500()) | set(load_ndx()))


def test_ndx_refresh_keeps_the_saved_list_when_the_download_is_short(tmp_path):
    path, asof = tmp_path / 'ndx.csv', tmp_path / 'ndx.asof'
    path.write_text("symbol,name,industry\nAAA,Aaa,Tech\n")
    logs = []
    assert not ensure_fresh_ndx(str(path), str(asof), today=date(2026, 10, 5),
                                fetch=lambda: {'X': ('x', 'y')}, log=logs.append)
    assert list(load_ndx(str(path))) == ['AAA'] and 'failed' in logs[0]

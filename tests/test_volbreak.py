from mtl import volbreak as VB
from mtl.sector_rsi import FUNDS


def _cal(n):
    return [f'2026-{1 + i // 28:02d}-{1 + i % 28:02d}' for i in range(n)]


def _line(cal, start, step):
    return {d: start * (1 + step) ** i for i, d in enumerate(cal)}


def _funds(cal, falling):
    """the 11 sector funds: those in `falling` drift down, the rest up"""
    return {f: _line(cal, 100, -0.002 if f in falling else 0.002) for f in FUNDS}


def _vol(cal, last):
    v = {d: 1_000_000 for d in cal}
    v[cal[-1]] = last
    return v


def test_break_when_sector_falls_alone_on_heavy_volume():
    cal = _cal(80)
    px = {'AAA': _line(cal, 50, -0.003)}
    out = VB.check([('AAA', 'Technology')], px, {'AAA': _vol(cal, 2_000_000)}, _funds(cal, {'XLK', 'XLE'}), cal)
    assert out['AAA']['kind'] == 'break' and out['AAA']['fund'] == 'XLK'
    assert out['AAA']['vr'] == 2.0 and out['AAA']['down'] == 2 and out['AAA']['chg'] < 0


def test_quiet_volume_or_rising_stock_is_not_flagged():
    cal = _cal(80)
    funds = _funds(cal, {'XLK'})
    px = {'AAA': _line(cal, 50, -0.003), 'BBB': _line(cal, 50, 0.003)}
    vols = {'AAA': _vol(cal, 1_200_000), 'BBB': _vol(cal, 3_000_000)}
    assert VB.check([('AAA', 'Technology'), ('BBB', 'Technology')], px, vols, funds, cal) == {}


def test_sector_up_is_not_a_break():
    cal = _cal(80)
    px = {'AAA': _line(cal, 50, -0.003)}
    out = VB.check([('AAA', 'Energy')], px, {'AAA': _vol(cal, 2_000_000)}, _funds(cal, {'XLK'}), cal)
    assert out == {}


def test_market_wide_dip_on_heavy_volume_is_panic():
    cal = _cal(80)
    falling = set(list(FUNDS)[:8])
    px = {'AAA': _line(cal, 50, -0.003)}
    out = VB.check([('AAA', 'Technology')], px, {'AAA': _vol(cal, 2_000_000)}, _funds(cal, falling), cal)
    assert out['AAA']['kind'] == 'panic' and out['AAA']['down'] == 8


def test_four_to_six_sectors_down_is_neither():
    cal = _cal(80)
    px = {'AAA': _line(cal, 50, -0.003)}
    out = VB.check([('AAA', 'Technology')], px, {'AAA': _vol(cal, 2_000_000)}, _funds(cal, {'XLK', 'XLE', 'XLF', 'XLB', 'XLU'}), cal)
    assert out == {}


def test_missing_data_is_skipped():
    cal = _cal(80)
    px = {'AAA': _line(cal, 50, -0.003)}
    assert VB.check([('AAA', 'Technology')], px, {}, _funds(cal, {'XLK'}), cal) == {}
    assert VB.check([('AAA', 'Technology')], px, {'AAA': _vol(cal, 2_000_000)}, {'XLK': _line(cal, 100, -0.002)}, cal) == {}
    assert VB.vol_ratio({cal[-1]: 5}, cal) is None

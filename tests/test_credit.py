"""Credit watch: banks and junk bonds under their 1-year highs, with an early read while SPY is near its high."""
from mtl.credit import LOOK, watch


def days(n):
    return [f"d{i:05d}" for i in range(n)]


def series(ds, path):
    """{date: close}: flat at 100 for a year, then the given path of closes."""
    vals = [100.0] * LOOK + list(path)
    return dict(zip(ds, vals))


def test_needs_a_year_of_shared_history():
    ds = days(LOOK)
    flat = dict.fromkeys(ds, 100.0)
    assert watch(flat, flat, flat) is None


def test_on_when_both_crack_and_off_when_one_recovers():
    tail = 40
    ds = days(LOOK + tail)
    banks = series(ds, [100 - 0.4 * i for i in range(30)] + [96.0] * 10)        # down 11.6% by day 29, back to -4%
    junk = series(ds, [100 - 0.12 * i for i in range(30)] + [96.4] * 10)        # down 3.5% by day 29
    spy = series(ds, [100 - 0.5 * i for i in range(30)] + [90.0] * 10)
    w = watch(banks, junk, spy)
    assert not w['on'] and w['banks'] == -0.04            # banks back within 5% of the high: off
    assert w['spells'] and w['spells'][-1][1] is not None  # it was on, and the spell ended
    on_from, on_to = w['spells'][-1]
    assert ds.index(on_from) > LOOK and ds.index(on_to) < LOOK + 30
    assert w['tickers'] == ['XLF', 'VWEHX'] and w['main'] == dict(banks=0.10, junk=0.03)


def test_early_read_needs_spy_near_its_high():
    tail = 30
    ds = days(LOOK + tail)
    banks = series(ds, [100 - 0.3 * i for i in range(tail)])       # -8.7% at the end
    junk = series(ds, [100 - 0.1 * i for i in range(tail)])        # -2.9%
    spy_high = series(ds, [100.0] * tail)                          # SPY at its high: they crack first
    spy_low = series(ds, [100 - 0.4 * i for i in range(tail)])     # SPY already 11.6% down
    w = watch(banks, junk, spy_high)
    assert w['early'] and not w['on'] and w['earlySince'] is not None
    w = watch(banks, junk, spy_low)
    assert not w['early'] and not w['on']

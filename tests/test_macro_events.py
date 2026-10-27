"""Macro signals for the events list (mtl/macro_events.py): oil, the dollar, credit, the yield curve, inflation, jobs."""
from datetime import date, timedelta

from mtl import macro_events as M


def sessions(start='2020-01-01', n=900):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def path(cal, values):
    return dict(zip(cal, values))


def test_oil_up_half_in_a_year_fires_once_a_year():
    cal = sessions()
    oil = [50.0] * 300 + [80.0] * 20 + [70.0] * 20 + [80.0] * 560     # crosses +50%, dips back, crosses again
    got = M.find(cal, dict(oil=path(cal, oil)), cal[0])
    assert [d for d, w in got] == [cal[300]]
    assert got[0][1] == 'Oil up 50% in a year: $80 against $50 a year earlier'


def test_credit_cracking_needs_banks_and_junk_bonds_both():
    cal = sessions()
    flat = [100.0] * 300
    banks = flat + [88.0] * 600
    alone = M.find(cal, dict(banks=path(cal, banks), junk=path(cal, [100.0] * 900)), cal[0])
    both = M.find(cal, dict(banks=path(cal, banks), junk=path(cal, flat + [96.5] * 600)), cal[0])
    assert alone == []
    assert both == [(cal[300], 'Credit cracking: banks 12% and junk bonds 4% under their 1-year highs')]


def test_inflation_counts_from_the_day_it_is_published():
    cal = sessions('2019-01-01', 1000)
    cpi, x = {}, 100.0
    for y in range(2018, 2023):
        for m in range(1, 13):
            rate = 0.05 if (y, m) >= (2021, 5) else 0.02                    # 5% a year from May 2021
            x *= (1 + rate) ** (1 / 12)
            cpi[f'{y}-{m:02d}-01'] = x
    first = min(m for m in cpi if m in M.yoy_monthly(cpi) and M.yoy_monthly(cpi)[m] >= 0.04)   # the month it crossed
    got = [(d, w) for d, w in M.find(cal, dict(cpi=cpi), cal[0]) if w.startswith('Inflation tops')]
    out = M.pub_date(first, M.CPI_LAG)
    assert got == [(next(c for c in cal if c >= out),
                     f"Inflation tops 4%: {M.yoy_monthly(cpi)[first] * 100:.1f}% in {date.fromisoformat(first):%B %Y}")]
    assert out[:7] > first[:7]                                            # out the month after it describes


def test_yield_curve_inverts_then_back_to_normal():
    cal = sessions()
    curve = [1.0] * 300 + [-0.3] * 150 + [0.4] * 450
    got = M.find(cal, dict(curve=path(cal, curve)), cal[0])
    assert [w.split(':')[0] for d, w in got] == ['Yield curve inverts', 'Yield curve un-inverts']
    assert got[0][0] == cal[300] and got[1][0] == cal[454]                # back above for 5 sessions


def test_dollar_and_recession_signal_and_missing_series():
    cal = sessions()
    usd = [100.0] * 300 + [89.0] * 600
    sahm = {f'{y}-{m:02d}-01': (0.6 if (y, m) >= (2021, 6) else 0.1) for y in range(2019, 2024) for m in range(1, 13)}
    got = M.find(cal, dict(dollar=path(cal, usd), sahm=sahm), cal[0])
    kinds = [w.split(':')[0] for d, w in got]
    assert kinds.count('Dollar down 10% in a year') == 1 and kinds.count('Recession signal') == 1
    jobs = next(d for d, w in got if w.startswith('Recession'))
    assert jobs == next(c for c in cal if c >= '2021-07-07')              # June's figure, out the first week of July
    assert M.find(cal, {}, cal[0]) == [] and M.find(cal, dict(oil={}), cal[0]) == []


def test_since_keeps_only_later_signals():
    cal = sessions()
    oil = [50.0] * 300 + [80.0] * 600
    assert M.find(cal, dict(oil=path(cal, oil)), cal[301]) == []

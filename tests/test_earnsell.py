"""The near-high earnings sell (mtl/earnsell.py, rule 23): a 3%+ drop on the report from within 5% of the 52-week high,
then a 3%+ down day or a new low within 10 sessions, sells the holding."""
from datetime import date, timedelta

from mtl import earnsell as E


def _cal(n):
    d, out = date(2024, 1, 1), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _px(cal, closes):
    return {'X': dict(zip(cal, closes))}


R = 300   # the reaction day


def _closes(top=100.0, drop=-0.05, after=(0.0,) * 15):
    c = [80 + (top - 80) * i / (R - 1) for i in range(R)]       # rising to its high the day before the report
    c.append(c[-1] * (1 + drop))
    for a in after:
        c.append(c[-1] * (1 + a))
    return c


def test_sells_on_a_second_down_day():
    c = _closes(after=(0.01, -0.035, 0.0))
    cal = _cal(len(c))
    es = E.EarnSell(_px(cal, c), {'X': [[cal[R], 'bmo']]}, cal)
    assert es.reactions('X') and es.reactions('X')[0][0] == R
    assert not es.sell('X', R + 1, entry_k=10)
    assert es.sell('X', R + 2, entry_k=10)


def test_sells_on_a_new_low():
    c = _closes(after=(0.01, -0.02, 0.0))          # the second day closes under the report day's close
    cal = _cal(len(c))
    es = E.EarnSell(_px(cal, c), {'X': [[cal[R], 'bmo']]}, cal)
    assert es.sell('X', R + 2, entry_k=10)


def test_after_the_close_reacts_next_session():
    c = _closes(after=(-0.035,) + (0.0,) * 14)
    cal = _cal(len(c))
    es = E.EarnSell(_px(cal, c), {'X': [[cal[R - 1], 'amc']]}, cal)
    assert es.reactions('X')[0][0] == R


def test_not_far_from_the_high():
    c = _closes(after=(0.01, -0.04, 0.0))
    c[100] = 200.0                                   # a much higher close in the last year: not near the high
    cal = _cal(len(c))
    es = E.EarnSell(_px(cal, c), {'X': [[cal[R], 'bmo']]}, cal)
    assert not es.reactions('X') and not es.sell('X', R + 2, entry_k=10)


def test_not_a_small_drop_or_after_the_window_or_before_the_buy():
    cal = _cal(R + 16)
    small = E.EarnSell(_px(cal, _closes(drop=-0.02, after=(0.01, -0.04) + (0.0,) * 13)), {'X': [[cal[R], 'bmo']]}, cal)
    assert not small.sell('X', R + 2, entry_k=10)
    late = E.EarnSell(_px(cal, _closes(after=(0.01,) * 11 + (-0.04,) + (0.0,) * 3)), {'X': [[cal[R], 'bmo']]}, cal)
    assert not late.sell('X', R + 12, entry_k=10)
    c = _closes(after=(0.01, -0.035, 0.0))
    held_after = E.EarnSell(_px(cal, c + [c[-1]] * 13), {'X': [[cal[R], 'bmo']]}, cal)
    assert not held_after.sell('X', R + 2, entry_k=R + 1)      # bought after the report: it doesn't count


def test_info_for_the_page():
    c = _closes(after=(0.01, -0.035) + (0.0,) * 12)
    cal = _cal(len(c))
    es = E.EarnSell(_px(cal, c), {'X': [[cal[R], 'bmo']]}, cal)
    i = es.info('X', R + 1)
    assert i['date'] == cal[R] and i['chg'] < -0.03 and not i['sell'] and i['until'] == cal[R + 10]
    assert es.info('X', R + 2)['sell']

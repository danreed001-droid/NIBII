from mtl import sector_rsi as SR


def _cal(n):
    return [f'2026-{1 + i // 28:02d}-{1 + i % 28:02d}' for i in range(n)]


def test_rising_series_is_overbought_and_falling_oversold():
    cal = _cal(80)
    up = {d: 100 * 1.01 ** i for i, d in enumerate(cal)}
    dn = {d: 100 * 0.99 ** i for i, d in enumerate(cal)}
    out = SR.build({'XLK': up, 'XLE': dn}, {}, {}, cal)
    s = {r['t']: r for r in out['sectors']}
    assert s['XLK']['rsi'] > 70 and s['XLE']['rsi'] < 30
    assert out['sectors'][0]['t'] == 'XLK'          # sorted high to low
    assert out['back'] == SR.BACK and out['asOf'] == cal[-1]


def test_theme_needs_enough_members_and_uses_the_universe():
    cal = _cal(80)
    px = {f'S{i}': {d: 50 * 0.995 ** j for j, d in enumerate(cal)} for i in range(5)}
    ind = {f'S{i}': 'Widgets' for i in range(5)}
    ind.update(X1='Tiny', X2='Tiny')
    px.update(X1=px['S0'], X2=px['S0'])
    out = SR.build({}, px, ind, cal)
    names = [t['name'] for t in out['themes']]
    assert 'Widgets' in names and 'Tiny' not in names
    w = next(t for t in out['themes'] if t['name'] == 'Widgets')
    assert w['n'] == 5 and w['rsi'] < 30
    assert SR.build({}, px, ind, cal, universe=['S0', 'S1'])['themes'] == []


def test_short_history_is_skipped():
    cal = _cal(10)
    out = SR.build({'XLK': {d: 1.0 + i for i, d in enumerate(cal)}}, {}, {}, cal)
    assert out['sectors'] == [] and out['themes'] == []


def test_index_ignores_huge_moves():
    cal = _cal(5)
    px = {t: {d: v for d, v in zip(cal, vals)} for t, vals in
          {'A': [10, 10, 30, 30, 30], 'B': [10, 11, 11, 11, 11], 'C': [10, 11, 11, 11, 11], 'D': [10, 11, 11, 11, 11]}.items()}
    ix = SR.industry_index(px, ['A', 'B', 'C', 'D'], cal)
    assert abs(ix[1] - 1.075) < 1e-9    # day 1: A flat, B/C/D +10%: average of 4
    assert abs(ix[2] / ix[1] - 1) < 1e-9   # day 2: A +200% left out, the rest flat


def test_daily_history_for_the_date_picker():
    cal = _cal(120)
    up = {d: 100 * 1.01 ** i for i, d in enumerate(cal)}
    dn = {d: 100 * 0.99 ** i for i, d in enumerate(cal)}
    px = {f'S{i}': dn for i in range(4)}
    h = SR.build({'XLK': up, 'XLE': dn}, px, {f'S{i}': 'Widgets' for i in range(4)}, cal)['hist']
    assert h['dates'] == cal[-SR.DAYS:] and h['dates'][-1] == cal[-1]
    assert len(h['sectors']['XLK']) == len(h['dates']) and h['sectors']['XLK'][-1] > 70 > 30 > h['sectors']['XLE'][-1]
    assert h['themes']['Widgets'][-1] < 30 and h['n']['Widgets'] == 4
    assert h['sectors']['XLK'][0] is None          # too early for a 14-day RSI


def test_six_month_return_for_the_circles():
    cal = _cal(300)
    up = {d: 100 * 1.001 ** i for i, d in enumerate(cal)}
    h = SR.build({'XLK': up}, {}, {}, cal)['hist']
    assert abs(h['r6s']['XLK'][-1] - (1.001 ** 126 - 1)) < 1e-3


def test_tickers_map_to_their_theme():
    cal = _cal(80)
    px = {f'S{i}': {d: 50 * 0.995 ** j for j, d in enumerate(cal)} for i in range(5)}
    out = SR.build({}, px, {f'S{i}': 'Widgets' for i in range(5)}, cal)
    assert out['tickers'] == {f'S{i}': 'Widgets' for i in range(5)}

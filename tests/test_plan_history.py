"""Where the plan was on each market event (mtl/plan_history.py, research/backtest/build_plan_history.py, the events page)."""
from mtl import plan_history as ph
from research.backtest import build_plan_history as bph

HIST = dict(end='2026-10-16', held=[
    ['2026-01-02', 1.0, 0.0, 0.0, 0.0],
    ['2026-03-10', 0.0, 1.0, 0.0, 0.0],      # into gold at the Mar 10 close
    ['2026-04-15', 0.8, 0.0, 0.0, 0.2],      # back to stocks, a fifth in cash
    ['2026-09-30', 0.0, 0.0, 0.0, 1.0]])


def test_backtest_dump_keeps_only_the_changes():
    sched = [['2026-01-02', {'AMD': 0.2, 'MU': 0.2, 'HPE': 0.2, 'DELL': 0.2, 'CRWD': 0.2}],
             ['2026-01-09', {'AMD': 0.2, 'MU': 0.2, 'HPE': 0.2, 'DELL': 0.2, 'NVDA': 0.2}],   # new stock, same shares
             ['2026-01-12', {'GLDX': 1.0}], ['2026-01-20', {'TLTX': 1.0}],
             ['2026-01-27', {'AMD': 0.2, 'MU': 0.2, 'HPE': 0.2, 'CASH0': 0.4}]]
    out = bph.build(sched, '2026-01-30')
    assert out['held'] == [['2026-01-02', 1.0, 0.0, 0.0, 0.0], ['2026-01-12', 0.0, 1.0, 0.0, 0.0],
                           ['2026-01-20', 0.0, 0.0, 1.0, 0.0], ['2026-01-27', 0.6, 0.0, 0.0, 0.4]]
    assert out['start'] == '2026-01-02' and out['end'] == '2026-01-30'


def test_live_decisions_take_over_from_the_first_fill_and_fill_at_the_next_close():
    hist = dict(HIST, held=HIST['held'] + [['2026-10-16', 1.0, 0.0, 0.0, 0.0]])   # a rerun that disagrees with the live plan
    ledger = dict(entries=[dict(d='2026-10-14', w={'CASH': 1.0}),            # fills Oct 15: live from here on
                           dict(d='2026-10-16', w={'GLD': 1.0}),             # a Friday: fills Monday
                           dict(d='2026-10-19', w={'GLD': 1.0}),             # no change
                           dict(d='2026-10-20', w={'TLT': 0.5, 'SPY': 0.5})])
    tl = ph.timeline(hist, ledger)
    assert tl[-3:] == [('2026-09-30', (0.0, 0.0, 0.0, 1.0)), ('2026-10-19', (0.0, 1.0, 0.0, 0.0)),
                       ('2026-10-21', (0.5, 0.0, 0.5, 0.0))]
    assert ph.during(tl, '2026-10-19') == (0.0, 0.0, 0.0, 1.0)       # what the live plan held, not the rerun's stocks
    assert ph.timeline(None, None) == []
    assert ph.timeline(None, ledger)[0] == ('2026-10-15', (0.0, 0.0, 0.0, 1.0))


def test_where_the_plan_was_through_a_day_and_its_next_move():
    tl = ph.timeline(HIST, None)
    assert ph.during(tl, '2026-01-02') is None                       # bought at that close: nothing held through it
    assert ph.during(tl, '2026-03-10') == (1.0, 0.0, 0.0, 0.0)       # the switch is at that day's close
    assert ph.during(tl, '2026-03-11') == (0.0, 1.0, 0.0, 0.0)
    assert ph.switch(tl, '2026-03-10') == ('2026-03-10', 'gold')     # moved at the event day's own close
    assert ph.switch(tl, '2026-02-20') == ('2026-03-10', 'gold')     # 13 sessions later
    assert ph.switch(tl, '2026-02-01') is None                       # more than a month later
    assert ph.switch(tl, '2026-04-20') is None                       # stocks 80% to stocks 80%: no move
    assert ph.now(tl, '2026-10-16') == ((0.0, 0.0, 0.0, 1.0), '2026-09-30', None)
    tl = ph.timeline(HIST, dict(entries=[dict(d='2026-10-16', w={'AMD': 0.2, 'MU': 0.2})]))
    assert ph.now(tl, '2026-10-16') == ((0.0, 0.0, 0.0, 1.0), '2026-09-30', ('2026-10-19', 'stocks'))
    assert ph.now(tl, '2025-12-31') is None


def test_events_page_shows_the_plan_under_each_event():
    from scripts.major_events import render
    tl = ph.timeline(HIST, None)
    doc = dict(updated='2026-10-16T23:30:00+00:00', events=[
        dict(d='2026-02-20', what='Bank fails', src='curated', type='Bank / credit failure', day=-0.03, month=-0.05),
        dict(d='2026-05-01', what='Rescue deal', src='curated', type='Rescue / fiscal', day=0.02, month=0.04),
        dict(d='2025-06-01', what='Before the history', src='curated', type='Other', day=0.01)])
    page = render(doc, pats={}, log={}, plan=tl)
    assert 'Plan: stocks <span class="nw">→ <i class="dot k-gold"></i>gold Mar 10</span></div>' in page
    assert 'title="stocks 80%, cash 20%"><i class="dot k-stocks"></i>Plan: stocks 80%</div>' in page
    assert page.count('class="pl"') == 2                              # none before the history starts
    assert 'The plan now: <b>cash</b>, since the Sep 30 close.' in page

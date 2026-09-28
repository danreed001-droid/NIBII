"""settle_document tests - pure logic, no network (a fake close_fn stands in)."""
import copy
import json
import os

from datetime import datetime

from mtl.verify import verify_document
from scripts.settle import ET, settle_document

# After every golden maturity (latest 2026-10-08) has closed, so grades are final.
AFTER_ALL = datetime(2026, 10, 9, 9, 0, tzinfo=ET)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = json.load(open(os.path.join(ROOT, 'golden/2026-09-24.published.json')))


LEGACY = {'^GSPC': 'equities', 'TLT': 'bonds', 'GC=F': 'gold', 'DX-Y.NYB': 'dollar',
          'IWM': 'iwm', 'QQQ': 'qqq'}


def fake_close_fn(ticker, date):
    key = LEGACY.get(ticker)
    if ticker == 'GC=F' and date == '2026-09-24':
        return 4300.0  # proxy base: GC=F's own print on the document date
    closes = {
        ('equities', '2026-09-25'): 7690.0, ('equities', '2026-10-01'): 7750.0,
        ('equities', '2026-10-08'): 7600.0,
        ('bonds', '2026-09-25'): 79.10, ('bonds', '2026-10-01'): 78.50,
        ('bonds', '2026-10-08'): 79.00,
        ('gold', '2026-09-25'): 4300.0, ('gold', '2026-10-01'): 4250.0,
        ('gold', '2026-10-08'): 4400.0,
        ('dollar', '2026-09-25'): 101.20, ('dollar', '2026-10-01'): 101.50,
        ('dollar', '2026-10-08'): 100.90,
        ('iwm', '2026-09-25'): 280.0, ('iwm', '2026-10-01'): 275.0,
        ('iwm', '2026-10-08'): 285.0,
        ('qqq', '2026-09-25'): 600.0, ('qqq', '2026-10-01'): 610.0,
        ('qqq', '2026-10-08'): 590.0,
    }
    return closes.get((key, date))


def test_settle_marks_every_horizon_and_stays_verifiable():
    doc = copy.deepcopy(PUB)
    changed, before = settle_document(doc, close_fn=fake_close_fn, now=AFTER_ALL)
    assert changed
    for a in doc['assets']:
        for h in a['horizons']:
            assert h['maturityClose'] is not None
            assert h['correct'] in (True, False, None)
            for v in h['votes']:
                assert len(v) == 3
    assert doc['scored'] is True
    assert verify_document(doc) == []


def test_settle_is_a_noop_when_nothing_has_matured():
    doc = copy.deepcopy(PUB)
    changed, _ = settle_document(doc, close_fn=lambda key, date: None)
    assert not changed
    assert doc == PUB


def test_settle_never_touches_vote_side_or_reason():
    doc = copy.deepcopy(PUB)
    before_votes = [[list(v[:2]) for v in h['votes']] for a in doc['assets'] for h in a['horizons']]
    settle_document(doc, close_fn=fake_close_fn, now=AFTER_ALL)
    after_votes = [[list(v[:2]) for v in h['votes']] for a in doc['assets'] for h in a['horizons']]
    assert before_votes == after_votes


def test_settles_each_document_against_its_own_instrument():
    # A legacy document (no per-asset 'ticker') is graded on its own
    # instrument (SPX index via ^GSPC, TLT, ...), never on today's futures.
    seen = []
    def spy(ticker, date):
        seen.append(ticker)
        return fake_close_fn(ticker, date)
    settle_document(copy.deepcopy(PUB), close_fn=spy, now=AFTER_ALL)
    assert {'^GSPC', 'TLT', 'IWM', 'QQQ', 'DX-Y.NYB'} <= set(seen)
    assert not {'ES=F', 'ZN=F', 'RTY=F', 'NQ=F'} & set(seen)


def test_gold_without_a_spot_source_is_graded_on_the_futures_return():
    doc = copy.deepcopy(PUB)
    settle_document(doc, close_fn=fake_close_fn, now=AFTER_ALL)
    gold = next(a for a in doc['assets'] if a['key'] == 'gold')
    h = gold['horizons'][0]
    # 4300 -> 4300 on GC=F is a 0% move, whatever the spot close was
    assert h['ret'] == 0.0
    assert 'GC=F' in h['settlementNote']
    assert verify_document(doc) == []


# --- provisional grades: a maturity session still trading is graded, but
# re-graded every run until it closes, and never counted until then.

def test_intraday_grade_is_provisional_and_regraded_until_the_close():
    from mtl.record import settled_cells
    doc = copy.deepcopy(PUB)
    morning = datetime(2026, 9, 25, 9, 50, tzinfo=ET)
    changed, _ = settle_document(doc, close_fn=fake_close_fn, now=morning)
    assert changed
    one_d = [h for a in doc['assets'] for h in a['horizons'] if h['h'] == 1]
    assert all(h['provisional'] and h['maturityClose'] is not None for h in one_d)
    assert doc['scored'] is False
    assert settled_cells({doc['date']: doc}) == []  # nothing provisional is counted
    assert verify_document(doc) == []

    # later print moves: the provisional grade is replaced, marks recomputed
    moved = lambda t, d: (fake_close_fn(t, d) * 1.05) if fake_close_fn(t, d) else None
    settle_document(doc, close_fn=moved, now=datetime(2026, 9, 25, 15, 0, tzinfo=ET))
    eq = doc['assets'][0]['horizons'][0]
    assert eq['provisional'] and eq['maturityClose'] == fake_close_fn('^GSPC', '2026-09-25') * 1.05
    assert all(len(v) == 3 for v in eq['votes'])  # re-marked, not double-marked
    assert verify_document(doc) == []

    # after 5pm ET on the maturity date the grade is final and counted
    settle_document(doc, close_fn=fake_close_fn, now=datetime(2026, 9, 25, 17, 5, tzinfo=ET))
    assert not any(h.get('provisional') for h in one_d)
    assert len(settled_cells({doc['date']: doc})) == len(one_d)
    assert verify_document(doc) == []

    # a final grade is never touched again
    changed, _ = settle_document(doc, close_fn=moved, now=AFTER_ALL)
    assert eq['maturityClose'] == fake_close_fn('^GSPC', '2026-09-25')


def test_rerun_with_the_same_print_is_not_a_change():
    doc = copy.deepcopy(PUB)
    noon = datetime(2026, 9, 25, 12, 0, tzinfo=ET)
    settle_document(doc, close_fn=fake_close_fn, now=noon)
    changed, _ = settle_document(doc, close_fn=fake_close_fn, now=noon)
    assert not changed

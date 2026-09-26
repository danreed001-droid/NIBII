"""settle_document tests - pure logic, no network (a fake close_fn stands in)."""
import copy
import json
import os

from mtl.verify import verify_document
from scripts.settle import settle_document

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
    changed, before = settle_document(doc, close_fn=fake_close_fn)
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
    settle_document(doc, close_fn=fake_close_fn)
    after_votes = [[list(v[:2]) for v in h['votes']] for a in doc['assets'] for h in a['horizons']]
    assert before_votes == after_votes


def test_settles_each_document_against_its_own_instrument():
    # A legacy document (no per-asset 'ticker') is graded on its own
    # instrument (SPX index via ^GSPC, TLT, ...), never on today's futures.
    seen = []
    def spy(ticker, date):
        seen.append(ticker)
        return fake_close_fn(ticker, date)
    settle_document(copy.deepcopy(PUB), close_fn=spy)
    assert {'^GSPC', 'TLT', 'IWM', 'QQQ', 'DX-Y.NYB'} <= set(seen)
    assert not {'ES=F', 'ZN=F', 'RTY=F', 'NQ=F'} & set(seen)


def test_gold_without_a_spot_source_is_graded_on_the_futures_return():
    doc = copy.deepcopy(PUB)
    settle_document(doc, close_fn=fake_close_fn)
    gold = next(a for a in doc['assets'] if a['key'] == 'gold')
    h = gold['horizons'][0]
    # 4300 -> 4300 on GC=F is a 0% move, whatever the spot close was
    assert h['ret'] == 0.0
    assert 'GC=F' in h['settlementNote']
    assert verify_document(doc) == []

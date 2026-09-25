"""The 13th category (Market structure, weight 3): tally weighting, the
mechanical vote it gets instead of judgment, and a real build+verify
round-trip proving the wiring holds together end to end."""
import copy
import json
import os

from mtl.build import build_document
from mtl.resolve import FAMILY, resolve, tally, weight
from mtl.structure import CATEGORY_NAME, vote_from_signal
from mtl.verify import verify_document
from scripts.prepare_daily import draft_votes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INP = json.load(open(os.path.join(ROOT, 'contracts/inputs.2026-09-24.json')))
VOT = json.load(open(os.path.join(ROOT, 'contracts/votes.2026-09-24.json')))


def test_weight_defaults_to_one_everywhere_except_13():
    assert weight(1) == 1
    assert weight(12) == 1
    assert weight(13) == 3


def test_category_13_has_its_own_family():
    assert FAMILY[13] == 'F'
    assert FAMILY[13] not in (FAMILY[1], FAMILY[12])  # not folded into an existing cluster


def test_tally_counts_the_13th_vote_triple():
    votes_12 = [["neu", "x"]] * 12
    votes_13_bull = votes_12 + [["bull", "structure"]]
    bull, bear, neutral = tally(votes_13_bull)
    assert bull == 3  # weight 3, not 1
    assert bull + bear + neutral == 15  # 12*1 + 1*3


def test_13th_vote_alone_can_tip_a_call_12_votes_could_not():
    # 4 bull, 3 bear, 5 neu among the 12 judgment categories: margin 1,
    # short of DIRECTIONAL_THRESHOLD (4) either way.
    votes_12 = ([["bull", "x"]] * 4 + [["bear", "x"]] * 3 + [["neu", "x"]] * 5)
    without_13 = resolve(votes_12 + [["neu", "structure"]])
    assert without_13['call'] == 'flat'

    # at weight 3, the 13th vote by itself is enough: (4+3) - 3 = 4, exactly
    # DIRECTIONAL_THRESHOLD - a single category deciding the call alone is
    # the tradeoff of weight 3, flagged in resolve.py's own docstring.
    with_13_bull = resolve(votes_12 + [["bull", "structure"]])
    assert with_13_bull['margin'] == 4
    assert with_13_bull['call'] == 'bullish'


def test_vote_from_signal_is_mechanical_not_judged():
    up = dict(state='uptrend', swings=[dict(label='HH')], lookback=1, lastBreak=None)
    down = dict(state='downtrend', swings=[dict(label='LL')], lookback=1, lastBreak=None)
    choppy = dict(state='choppy', swings=[], lookback=1, lastBreak=None)
    none_sig = dict(state=None, note='too few bars', swings=[], lookback=1, lastBreak=None)

    assert vote_from_signal(up, '1H')[0] == 'bull'
    assert vote_from_signal(down, 'Weekly')[0] == 'bear'
    assert vote_from_signal(choppy, '1H')[0] == 'neu'
    assert vote_from_signal(none_sig, 'Weekly')[0] == 'neu'
    assert 'too few bars' in vote_from_signal(none_sig, 'Weekly')[1]


def test_draft_votes_fills_13th_mechanically_leaves_12_as_todo():
    assets = {
        'equities': {'structure': {
            'hourly': dict(state='uptrend', swings=[dict(label='HH')], lookback=1, lastBreak=None),
            'weekly': dict(state='downtrend', swings=[dict(label='LL')], lookback=1, lastBreak=None),
        }},
    }
    # draft_votes iterates mtl.build.ASSET_ORDER, so give every key the same shape
    from mtl.build import ASSET_ORDER
    for k in ASSET_ORDER:
        assets.setdefault(k, assets['equities'])

    votes = draft_votes(assets)
    h1 = votes['equities']['1']
    h5 = votes['equities']['5']
    assert len(h1) == 13 and len(h5) == 13
    assert h1[12][0] == 'bull'    # hourly structure -> uptrend -> bull
    assert h5[12][0] == 'bear'    # weekly structure -> downtrend -> bear
    assert all(v[0] == 'neu' and 'TODO' in v[1] for v in h1[:12])  # untouched, still judgment stubs


def test_build_and_verify_round_trip_with_a_13th_category():
    inp = copy.deepcopy(INP)
    vot = copy.deepcopy(VOT)

    a = inp['assets']['equities']
    a['categories'] = a['categories'] + [CATEGORY_NAME]
    for h in ('1', '5', '10'):
        vot['equities'][h] = vot['equities'][h] + [["bull", "structure: uptrend"]]

    doc = build_document(inp, vot)
    errs = verify_document(doc)
    assert errs == [], errs

    eq = next(a for a in doc['assets'] if a['key'] == 'equities')
    assert len(eq['categories']) == 13
    for h in eq['horizons']:
        assert len(h['votes']) == 13

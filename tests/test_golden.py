"""Golden test: the engine must reproduce the published 2026-09-24 board exactly.

This is the proof that extracting the logic out of the model was faithful and
not approximately right. If any threshold, tier table or overlay rule drifts,
this fails.

INP/VOT are frozen copies under golden/, not the live contracts/ files - the
live ledger is meant to keep evolving (e.g. 2026-09-24 itself was later
backfilled with a real, weighted 13th vote once the market-structure feature
existed - see mtl/structure.py), but this regression anchor must never move
out from under it.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl.build import build_document
from mtl.verify import verify_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = json.load(open(os.path.join(ROOT, 'golden/2026-09-24.published.json')))
INP = json.load(open(os.path.join(ROOT, 'golden/2026-09-24.inputs.json')))
VOT = json.load(open(os.path.join(ROOT, 'golden/2026-09-24.votes.json')))

COMPARE = ('h', 'maturity', 'band', 'flatLo', 'flatHi', 'bull', 'bear', 'neutral',
           'margin', 'call', 'confidence', 'shadowCall', 'shadowConfidence',
           'families', 'clusterDowngrade', 'preReversionCall',
           'preReversionConfidence', 'reversionAligned', 'reversionFlag')


def test_rebuild_matches_published():
    built = build_document(INP, VOT)
    assert [a['key'] for a in built['assets']] == [a['key'] for a in PUB['assets']]
    assert built['overlay']['cellsChanged'] == PUB['overlay']['cellsChanged']

    fails = []
    for ab, ap in zip(built['assets'], PUB['assets']):
        for f in ('score', 'label', 'components'):
            if ab['stretch'][f] != ap['stretch'][f]:
                fails.append(f"{ab['key']}.stretch.{f}: {ab['stretch'][f]} != {ap['stretch'][f]}")
        for hb, hp in zip(ab['horizons'], ap['horizons']):
            for f in COMPARE:
                if hb[f] != hp[f]:
                    fails.append(f"{ab['key']}/h{hp['h']}.{f}: {hb[f]!r} != {hp[f]!r}")
            if [v[:2] for v in hb['votes']] != [v[:2] for v in hp['votes']]:
                fails.append(f"{ab['key']}/h{hp['h']}: votes differ")
    assert not fails, "rebuild diverged from published document:\n  " + "\n  ".join(fails)


def test_published_document_passes_verifier():
    assert verify_document(PUB) == []


def test_overlay_never_flips_direction():
    for a in PUB['assets']:
        for h in a['horizons']:
            pre, post = h.get('preReversionCall'), h['call']
            if pre in ('bullish', 'bearish') and post in ('bullish', 'bearish'):
                assert pre == post, f"{a['key']}/h{h['h']} flipped {pre}->{post}"


def test_every_horizon_has_twelve_votes():
    for a in PUB['assets']:
        for h in a['horizons']:
            assert len(h['votes']) == 12, f"{a['key']}/h{h['h']}"

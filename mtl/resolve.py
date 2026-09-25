"""Vote tally -> call and confidence. Cluster downgrade. Shadow threshold.

Votes are weighted, not one-point-each: WEIGHT gives each category's
point value, defaulting to 1 for any index not listed. Category 13
(Market structure, HH/HL/LH/LL) is worth 3 - see mtl/structure.py and
scripts/prepare_daily.py, which fills that one vote in mechanically from
the computed swing read rather than leaving it for judgment, since it's
reporting a computed fact rather than asking for one. Every existing
12-category document (weight 1 throughout, since WEIGHT has no entry
below 13) tallies identically to before this existed - this is additive,
not a change to how any prior document is read.

LIVE_GATE/DIRECTIONAL_THRESHOLD/SHADOW_THRESHOLD/tier()'s margin cutoffs
are UNCHANGED absolute point values, carried over from the 12-category,
12-point system rather than re-derived for the new ~15-point maximum.
That's a real assumption, not a verified recalibration - there's no
backtested data yet to say whether these cutoffs should move now that a
single category can swing the tally by 3 points instead of 1 - at weight
3 this one category alone can already clear DIRECTIONAL_THRESHOLD's
margin of 4 almost by itself (3 points from one vote vs. needing a 4-vote
margin among the other 12), which is a materially bigger lever than
weight 2 was. Worth watching once real data exists.
"""

# Family positions are fixed for every asset. 13 (Market structure) gets
# its own family rather than joining an existing one, so it can't quietly
# change the cluster-downgrade math for categories 1-12.
FAMILY = {1: 'A', 2: 'A', 3: 'B', 4: 'B', 5: 'C', 6: 'C',
          7: 'D', 8: 'D', 9: 'E', 10: 'E', 11: 'E', 12: 'A',
          13: 'F'}

WEIGHT = {13: 3}  # every other category defaults to weight 1 - see weight()

LIVE_GATE = 7
DIRECTIONAL_THRESHOLD = 4
SHADOW_THRESHOLD = 3


def weight(category_index: int) -> int:
    """category_index is 1-based, matching FAMILY's keys."""
    return WEIGHT.get(category_index, 1)

_NOTCH = {'strong': 'solid', 'solid': 'lean', 'lean': 'lean',
          'flat-solid': 'flat-lean', 'flat-lean': 'flat-lean'}


def notch(conf: str) -> str:
    """Drop one confidence notch. Idempotent at the bottom of each ladder."""
    return _NOTCH[conf]


def tier(margin: int, flat: bool) -> str:
    if flat:
        return 'flat-solid' if margin <= 1 else 'flat-lean'
    if margin >= 7:
        return 'strong'
    if margin >= 5:
        return 'solid'
    return 'lean'


def tally(votes):
    """Weighted tally: each vote contributes weight(its 1-based position),
    not a flat 1. neutral is the weighted total minus bull minus bear, so
    a heavier neu vote still counts toward the denominator correctly."""
    bull = sum(weight(i + 1) for i, v in enumerate(votes) if v[0] == 'bull')
    bear = sum(weight(i + 1) for i, v in enumerate(votes) if v[0] == 'bear')
    total = sum(weight(i + 1) for i in range(len(votes)))
    return bull, bear, total - bull - bear


def resolve(votes, threshold: int = DIRECTIONAL_THRESHOLD) -> dict:
    """Resolve 12 or 13 weighted votes into a call. Votes are [side, reason]
    or [side, reason, mark]."""
    if len(votes) not in (12, 13):
        raise ValueError(f"expected 12 or 13 votes, got {len(votes)}")
    bull, bear, neutral = tally(votes)
    live, margin = bull + bear, abs(bull - bear)

    if live < LIVE_GATE:
        return dict(bull=bull, bear=bear, neutral=neutral, live=live, margin=margin,
                    call='no-call', confidence='thin-evidence',
                    families=[], clusterDowngrade=False)

    if margin >= threshold:
        call = 'bullish' if bull > bear else 'bearish'
        conf = tier(margin, flat=False)
    else:
        call, conf = 'flat', tier(margin, flat=True)

    if margin == 0:
        # No winning side: families are those across all live votes.
        families = sorted({FAMILY[i + 1] for i, v in enumerate(votes) if v[0] != 'neu'})
        downgrade = False
    else:
        win = 'bull' if bull > bear else 'bear'
        families = sorted({FAMILY[i + 1] for i, v in enumerate(votes) if v[0] == win})
        downgrade = len(families) == 1

    if downgrade:
        conf = notch(conf)

    return dict(bull=bull, bear=bear, neutral=neutral, live=live, margin=margin,
                call=call, confidence=conf, families=families,
                clusterDowngrade=downgrade)

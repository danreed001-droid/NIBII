"""Vote tally -> call and confidence. Cluster downgrade. Shadow threshold."""

# Family positions are fixed for every asset.
FAMILY = {1: 'A', 2: 'A', 3: 'B', 4: 'B', 5: 'C', 6: 'C',
          7: 'D', 8: 'D', 9: 'E', 10: 'E', 11: 'E', 12: 'A'}

LIVE_GATE = 7
DIRECTIONAL_THRESHOLD = 4
SHADOW_THRESHOLD = 3

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
    bull = sum(1 for v in votes if v[0] == 'bull')
    bear = sum(1 for v in votes if v[0] == 'bear')
    return bull, bear, len(votes) - bull - bear


def resolve(votes, threshold: int = DIRECTIONAL_THRESHOLD) -> dict:
    """Resolve 12 votes into a call. Votes are [side, reason] or [side, reason, mark]."""
    if len(votes) != 12:
        raise ValueError(f"expected 12 votes, got {len(votes)}")
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

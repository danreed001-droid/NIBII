"""stretch-v1 mean-reversion overlay.

Never flips a call's direction. It only dampens or vetoes a call that bets on
CONTINUATION of an already-stretched move, and never rewards one that opposes
a stretch (the vote model's contrarian categories already found that).
"""
from .bands import daily_sigma
from .resolve import notch

METHOD = "stretch-v1"
COMPONENT_ORDER = ("oscillator", "extension50", "extension200", "range", "volRegime", "crowd")


def c_oscillator(rsi14):
    if rsi14 is None:
        return 0
    if rsi14 >= 80: return 2
    if rsi14 >= 70: return 1
    if rsi14 <= 20: return -2
    if rsi14 <= 30: return -1
    return 0


def c_extension50(close, ma50, ds):
    if ma50 is None:
        return 0, None
    z = (close / ma50 - 1) / ds
    if z >= 4:   return 2, z
    if z >= 2:   return 1, z
    if z <= -4:  return -2, z
    if z <= -2:  return -1, z
    return 0, z


def c_extension200(close, ma200, ds):
    if ma200 is None:
        return 0, None
    z = (close / ma200 - 1) / ds
    if z >= 6:  return 1, z
    if z <= -6: return -1, z
    return 0, z


def c_range(close, high52w, low52w):
    if high52w is not None and (high52w - close) / high52w <= 0.02:
        return 1
    if low52w is not None and (close - low52w) / low52w <= 0.02:
        return -1
    return 0


def label_for(score):
    if score >= 3:  return 'extreme-up'
    if score <= -3: return 'extreme-down'
    if score == 2:  return 'stretched-up'
    if score == -2: return 'stretched-down'
    return 'neutral'


def score_stretch(close, sigma, inputs, vol_regime=0, crowd=0, as_of=None,
                  drivers=None, null_inputs=None):
    """Build the per-asset stretch object.

    vol_regime and crowd are JUDGMENT inputs: they may only be non-zero when a
    source itself names a percentile, a record, or a multi-year extreme. The
    engine cannot verify that, so it accepts them and records them verbatim.
    """
    ds = daily_sigma(sigma)
    osc = c_oscillator(inputs.get('rsi14'))
    e50, z50 = c_extension50(close, inputs.get('ma50'), ds)
    e200, z200 = c_extension200(close, inputs.get('ma200'), ds)
    rng = c_range(close, inputs.get('high52w'), inputs.get('low52w'))
    comps = dict(oscillator=osc, extension50=e50, extension200=e200,
                 range=rng, volRegime=int(vol_regime), crowd=int(crowd))
    score = sum(comps.values())
    if not -2 <= comps['crowd'] <= 2:
        raise ValueError("crowd component is capped at +/-2")
    return dict(score=score, label=label_for(score), components=comps,
                drivers=list(drivers or []), nullInputs=list(null_inputs or []),
                asOf=as_of, method=METHOD,
                z50=None if z50 is None else round(z50, 3),
                z200=None if z200 is None else round(z200, 3),
                dailySigma=round(ds, 6))


def alignment(call, score):
    """'rides' = continuation bet into a stretch. 'opposes' = points against it."""
    if (call == 'bullish' and score >= 2) or (call == 'bearish' and score <= -2):
        return 'rides'
    if (call == 'bullish' and score <= -2) or (call == 'bearish' and score >= 2):
        return 'opposes'
    return 'none'


def apply_overlay(call, confidence, score, label, margin):
    """Returns (call, confidence, aligned, flag, note). Direction never changes."""
    pre_call, pre_conf = call, confidence
    aligned = alignment(pre_call, score)
    rides = aligned == 'rides'

    if rides and abs(score) >= 3 and margin == 4:
        call, confidence = 'flat', 'flat-lean'
        note = (f"Stretch score {score} ({label}) and a marginal continuation call: "
                f"the +4 threshold {pre_call} call rode an extreme reading, so it was vetoed to flat.")
    elif rides and abs(score) >= 3:
        confidence = notch(confidence)
        note = (f"Stretch score {score} ({label}): the {pre_call} call rides an extreme reading "
                f"with margin {margin}, so confidence was dropped from {pre_conf} to {confidence}.")
    elif rides and abs(score) == 2:
        confidence = notch(confidence)
        note = (f"Stretch score {score} ({label}): the {pre_call} call rides a stretched reading, "
                f"so confidence was dropped from {pre_conf} to {confidence}.")
    elif aligned == 'opposes':
        note = (f"Stretch score {score} ({label}): the {call} call points against the stretch, so the "
                f"overlay left it untouched rather than rewarding the vote model twice.")
    elif call in ('flat', 'no-call'):
        note = (f"Stretch score {score} ({label}): the cell is {call}, not a directional "
                f"continuation bet, so the overlay took no action.")
    else:
        note = f"Stretch score {score} ({label}) is short of the +/-2 trigger, so the {call} call was left untouched."

    flag = (call != pre_call) or (confidence != pre_conf)
    if pre_call in ('bullish', 'bearish') and call in ('bullish', 'bearish') and call != pre_call:
        raise AssertionError("overlay must never flip a call's direction")
    return call, confidence, aligned, flag, note

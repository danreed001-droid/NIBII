"""Settlement: realized return -> outcome -> correctness flags and vote marks."""


def outcome(ret, band):
    if ret > band:
        return 'bullish'
    if ret < -band:
        return 'bearish'
    return 'flat'


def _mark(call, oc):
    if call is None or call == 'no-call':
        return None
    return call == oc


def settle_horizon(horizon, basis_close, maturity_close, settlement_note=None):
    """Settle one horizon in place. Returns the outcome string."""
    h = horizon
    h['maturityClose'] = maturity_close
    ret = round(maturity_close / basis_close - 1, 6)
    h['ret'] = ret
    oc = outcome(ret, h['band'])
    h['correct'] = _mark(h.get('call'), oc)
    h['shadowCorrect'] = _mark(h.get('shadowCall'), oc)
    if 'preReversionCall' in h:
        h['preReversionCorrect'] = _mark(h.get('preReversionCall'), oc)
    for v in h['votes']:
        if len(v) == 2:
            if v[0] == 'bull':
                v.append(oc == 'bullish')
            elif v[0] == 'bear':
                v.append(oc == 'bearish')
            else:
                v.append(None)
    if settlement_note:
        h['settlementNote'] = settlement_note
    return oc


def document_fully_settled(doc):
    return all(h['maturityClose'] is not None
               for a in doc['assets'] for h in a['horizons'])

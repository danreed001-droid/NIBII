"""Independent audit of a ledger document. Recomputes every derived field."""
import math
from .bands import band as calc_band
from .resolve import resolve, FAMILY, DIRECTIONAL_THRESHOLD, SHADOW_THRESHOLD
from .stretch import (c_oscillator, c_extension50, c_extension200, c_range,
                      label_for, alignment)
from .bands import daily_sigma
from .score import outcome

ROUND_TOL = 0.006  # documents have rounded flat zones to 2dp historically


def verify_document(doc, stretch_inputs=None) -> list:
    errs = []
    E = errs.append
    date = doc.get('date')
    si = stretch_inputs or (doc.get('context') or {}).get('stretchInputs') or {}

    for a in doc['assets']:
        key = a['key']
        if len(a.get('categories', [])) != 12:
            E(f"{key}: {len(a.get('categories', []))} categories, expected 12")

        st = a.get('stretch')
        if st:
            if sum(st['components'].values()) != st['score']:
                E(f"{key}: stretch components sum {sum(st['components'].values())} != score {st['score']}")
            if st['label'] != label_for(st['score']):
                E(f"{key}: label {st['label']} != {label_for(st['score'])}")
            if not -2 <= st['components']['crowd'] <= 2:
                E(f"{key}: crowd component outside +/-2")
            if key in si:
                inp, ds = si[key], daily_sigma(a['sigma'])
                c = st['components']
                for name, got, exp in (
                    ('oscillator', c['oscillator'], c_oscillator(inp.get('rsi14'))),
                    ('extension50', c['extension50'], c_extension50(a['close'], inp.get('ma50'), ds)[0]),
                    ('extension200', c['extension200'], c_extension200(a['close'], inp.get('ma200'), ds)[0]),
                    ('range', c['range'], c_range(a['close'], inp.get('high52w'), inp.get('low52w'))),
                ):
                    if got != exp:
                        E(f"{key}: stretch {name} {got} != {exp} recomputed from recorded input")

        for h in a['horizons']:
            tag = f"{date}/{key}/h{h['h']}"
            votes = h['votes']
            if len(votes) != 12:
                E(f"{tag}: {len(votes)} votes, expected 12")
                continue

            r = resolve(votes, DIRECTIONAL_THRESHOLD)
            sh = resolve(votes, SHADOW_THRESHOLD)
            for f in ('bull', 'bear', 'neutral', 'margin', 'families', 'clusterDowngrade'):
                if h[f] != r[f]:
                    E(f"{tag}: {f} {h[f]} != {r[f]}")
            if h['shadowCall'] != sh['call']:
                E(f"{tag}: shadowCall {h['shadowCall']} != {sh['call']}")
            if h['shadowConfidence'] != sh['confidence']:
                E(f"{tag}: shadowConfidence {h['shadowConfidence']} != {sh['confidence']}")

            eb = calc_band(a['sigma'], h['h'])
            if abs(h['band'] - eb) > 1e-9:
                E(f"{tag}: band {h['band']} != {eb}")
            for f, exp in (('flatLo', a['close'] * (1 - h['band'])),
                           ('flatHi', a['close'] * (1 + h['band']))):
                if abs(h[f] - exp) > ROUND_TOL:
                    E(f"{tag}: {f} {h[f]} != {exp}")

            pre, prec = h.get('preReversionCall'), h.get('preReversionConfidence')
            if pre is not None and st:
                if (pre, prec) != (r['call'], r['confidence']):
                    E(f"{tag}: preReversion {pre}/{prec} != vote model {r['call']}/{r['confidence']}")
                from .stretch import apply_overlay
                xc, xk, ea, ef, _ = apply_overlay(pre, prec, st['score'], st['label'], r['margin'])
                if (h['call'], h['confidence']) != (xc, xk):
                    E(f"{tag}: post-overlay {h['call']}/{h['confidence']} != {xc}/{xk}")
                if h.get('reversionAligned') not in (None, ea):
                    E(f"{tag}: reversionAligned {h['reversionAligned']} != {ea}")
                if h.get('reversionFlag') != ef:
                    E(f"{tag}: reversionFlag {h.get('reversionFlag')} != {ef}")
                if not h.get('reversionNote'):
                    E(f"{tag}: missing reversionNote")
                if pre in ('bullish', 'bearish') and h['call'] in ('bullish', 'bearish') and pre != h['call']:
                    E(f"{tag}: OVERLAY FLIPPED DIRECTION {pre} -> {h['call']}")
            elif (h['call'], h['confidence']) != (r['call'], r['confidence']):
                E(f"{tag}: call {h['call']}/{h['confidence']} != {r['call']}/{r['confidence']}")

            mc = h.get('maturityClose')
            if mc is None:
                for f in ('ret', 'correct', 'shadowCorrect'):
                    if h.get(f) is not None:
                        E(f"{tag}: {f} set without maturityClose")
            else:
                er = round(mc / a['close'] - 1, 6)
                if h['ret'] != er:
                    E(f"{tag}: ret {h['ret']} != {er}")
                oc = outcome(er, h['band'])
                for fld, cf in (('correct', 'call'), ('shadowCorrect', 'shadowCall'),
                                ('preReversionCorrect', 'preReversionCall')):
                    if cf not in h:
                        continue
                    cv = h[cf]
                    exp = None if (cv is None or cv == 'no-call') else (cv == oc)
                    if h.get(fld, 'MISSING') != exp:
                        E(f"{tag}: {fld} {h.get(fld)} != {exp} (outcome {oc}, call {cv})")
                for i, v in enumerate(votes):
                    if len(v) != 3:
                        E(f"{tag}: vote {i+1} unmarked on a settled horizon")
                    else:
                        exp = None if v[0] == 'neu' else (oc == ('bullish' if v[0] == 'bull' else 'bearish'))
                        if v[2] != exp:
                            E(f"{tag}: vote {i+1} mark {v[2]} != {exp}")

    from .score import document_fully_settled
    if doc['scored'] != document_fully_settled(doc):
        E(f"{date}: scored={doc['scored']} but fullySettled={document_fully_settled(doc)}")
    return errs


def assert_no_reason_drift(before: dict, after: dict) -> list:
    """Scoring must never change a vote's side or reason string."""
    errs = []
    for ao, an in zip(before['assets'], after['assets']):
        for ho, hn in zip(ao['horizons'], an['horizons']):
            for i, (vo, vn) in enumerate(zip(ho['votes'], hn['votes'])):
                if vo[0] != vn[0] or vo[1] != vn[1]:
                    errs.append(f"{ao['key']}/h{ho['h']} vote {i+1}: side or reason drifted")
            for k in ('band', 'call', 'confidence', 'shadowCall', 'shadowConfidence',
                      'margin', 'bull', 'bear', 'neutral', 'families', 'clusterDowngrade',
                      'preReversionCall', 'preReversionConfidence', 'flatLo', 'flatHi'):
                if ho.get(k) != hn.get(k):
                    errs.append(f"{ao['key']}/h{ho['h']}: {k} changed {ho.get(k)} -> {hn.get(k)}")
    return errs

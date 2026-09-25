"""Assemble a ledger document from researched inputs + authored votes.

inputs.json carries every NUMBER and its provenance. votes.json carries the
234 (side, reason) pairs (216 judgment + 18 mechanical - see
mtl.structure.vote_from_signal). Everything else in the document is
derived here.
"""
from .bands import band, flat_zone
from .resolve import resolve, SHADOW_THRESHOLD, DIRECTIONAL_THRESHOLD
from .stretch import score_stretch, apply_overlay
from .calendar_nyse import maturities

SCHEMA = "multi-asset-v4"  # v4: adds the weighted, mechanical 13th category (Market structure)
ASSET_ORDER = ("equities", "bonds", "gold", "dollar", "iwm", "qqq")
HORIZONS = (1, 5, 10)


def build_document(inputs: dict, votes: dict, generated_at=None, generation_lag=None) -> dict:
    s = inputs['date']
    mats = maturities(s, HORIZONS)
    assets, cells_changed = [], 0

    for key in inputs['assetOrder']:
        a = inputs['assets'][key]
        st = score_stretch(
            close=a['close'], sigma=a['sigma'], inputs=a['stretchInputs'],
            vol_regime=a.get('volRegime', 0), crowd=a.get('crowd', 0),
            as_of=s, drivers=a.get('stretchDrivers'), null_inputs=a.get('nullInputs'),
        )
        z50, z200, ds = st.pop('z50'), st.pop('z200'), st.pop('dailySigma')

        horizons = []
        for h in HORIZONS:
            vs = [list(v) for v in votes[key][str(h)]]
            r = resolve(vs, DIRECTIONAL_THRESHOLD)
            sh = resolve(vs, SHADOW_THRESHOLD)
            b = band(a['sigma'], h)
            lo, hi = flat_zone(a['close'], b)

            pre_call, pre_conf = r['call'], r['confidence']
            call, conf, aligned, flag, note = apply_overlay(
                pre_call, pre_conf, st['score'], st['label'], r['margin'])
            if flag:
                cells_changed += 1

            horizons.append(dict(
                h=h, maturity=mats[h], band=b, flatLo=lo, flatHi=hi,
                bull=r['bull'], bear=r['bear'], neutral=r['neutral'], margin=r['margin'],
                call=call, confidence=conf,
                shadowCall=sh['call'], shadowConfidence=sh['confidence'],
                families=r['families'], clusterDowngrade=r['clusterDowngrade'],
                preReversionCall=pre_call, preReversionConfidence=pre_conf,
                reversionAligned=aligned, reversionFlag=flag, reversionNote=note,
                votes=vs, maturityClose=None, ret=None,
                correct=None, shadowCorrect=None, preReversionCorrect=None,
            ))

        assets.append(dict(
            key=key, name=a['name'], instrument=a['instrument'], direction=a['direction'],
            close=a['close'], sigma=a['sigma'], sigmaSource=a['sigmaSource'],
            driverNote=a.get('driverNote', ''), stretch=st,
            categories=a['categories'], horizons=horizons,
            structure=a.get('structure'),
        ))

    ctx = dict(inputs.get('context') or {})
    ctx['stretchInputs'] = {k: inputs['assets'][k]['stretchInputs'] for k in inputs['assetOrder']}

    return dict(
        date=s, basisDate=s, scored=False,
        generatedAt=generated_at, generationLag=generation_lag,
        schema=SCHEMA,
        overlay=dict(name="stretch-v1", mode="dampen-and-veto",
                     appliedRetroactively=False, cellsChanged=cells_changed),
        context=ctx, assets=assets,
    )

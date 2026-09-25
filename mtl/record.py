"""Record aggregation: hit rate, edge units, and the two experiments."""
from collections import defaultdict

EDGE = {'strong': 3, 'solid': 2, 'lean': 1, 'flat-solid': 2, 'flat-lean': 1}
ASSET_ORDER = ("equities", "bonds", "gold", "dollar", "iwm", "qqq")


def settled_cells(docs: dict) -> list:
    rows = []
    for date, d in sorted(docs.items()):
        retro = bool((d.get('overlay') or {}).get('appliedRetroactively'))
        for a in d['assets']:
            for h in a['horizons']:
                if h['maturityClose'] is None:
                    continue
                oc = ('bullish' if h['ret'] > h['band']
                      else 'bearish' if h['ret'] < -h['band'] else 'flat')
                rows.append(dict(
                    date=date, asset=a['key'], h=h['h'],
                    call=h['call'], conf=h['confidence'], correct=h['correct'],
                    shadowCall=h['shadowCall'], shadowCorrect=h['shadowCorrect'],
                    preCall=h.get('preReversionCall'), preConf=h.get('preReversionConfidence'),
                    preCorrect=h.get('preReversionCorrect'),
                    reversionFlag=h.get('reversionFlag'), retroactive=retro,
                    ret=h['ret'], band=h['band'], outcome=oc,
                    categories=a['categories'], votes=h['votes'],
                ))
    return rows


def _rate(rows, field='correct'):
    v = [r for r in rows if r.get(field) is not None]
    if not v:
        return dict(hits=0, n=0, pct=None)
    hits = sum(1 for r in v if r[field])
    return dict(hits=hits, n=len(v), pct=round(100 * hits / len(v), 1))


def _edge(rows, field='correct', conf='conf'):
    t = 0
    for r in rows:
        if r.get(field) is None:
            continue
        e = EDGE.get(r.get(conf), 0)
        t += e if r[field] else -e
    return t


def aggregate(docs: dict) -> dict:
    rows = settled_cells(docs)
    out = dict(settledCells=len(rows), overall=_rate(rows), overallEdge=_edge(rows))

    out['byAsset'] = {k: dict(**_rate([r for r in rows if r['asset'] == k]),
                              edge=_edge([r for r in rows if r['asset'] == k]),
                              settled=len([r for r in rows if r['asset'] == k]))
                      for k in ASSET_ORDER}
    out['byHorizon'] = {h: dict(**_rate([r for r in rows if r['h'] == h]),
                                edge=_edge([r for r in rows if r['h'] == h]))
                        for h in (1, 5, 10)}
    tiers = sorted({r['conf'] for r in rows})
    out['byConfidence'] = {t: dict(**_rate([r for r in rows if r['conf'] == t]),
                                   edge=_edge([r for r in rows if r['conf'] == t]))
                           for t in tiers}
    out['byCallType'] = {t: _rate([r for r in rows if r['call'] == t])
                         for t in ('bullish', 'bearish', 'flat', 'no-call')}

    # +4 vs +3
    diff = [r for r in rows if r['call'] != r['shadowCall']]
    out['shadow'] = dict(
        actual=_rate(rows), actualEdge=_edge(rows),
        shadow=_rate(rows, 'shadowCorrect'), shadowEdge=_edge(rows, 'shadowCorrect'),
        divergentCells=len(diff),
        divergences=[dict(date=r['date'], asset=r['asset'], h=r['h'], actual=r['call'],
                          actualCorrect=r['correct'], shadow=r['shadowCall'],
                          shadowCorrect=r['shadowCorrect'], outcome=r['outcome']) for r in diff],
    )

    # Overlay: ONLY cells the overlay changed, retroactive segregated.
    changed = [r for r in rows if r['reversionFlag']]
    native = [r for r in changed if not r['retroactive']]
    out['overlay'] = dict(
        changedAndSettled=len(changed), native=len(native),
        retroactiveExcluded=len(changed) - len(native),
        post=_rate(native), postEdge=_edge(native),
        pre=_rate(native, 'preCorrect'), preEdge=_edge(native, 'preCorrect', 'preConf'),
        caveat=("Reported only over cells the overlay actually changed. "
                f"n={len(native)} native changed cells." +
                (" Documents with overlay.appliedRetroactively=true are excluded."
                 if len(changed) != len(native) else "")),
    )

    cat = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        for i, v in enumerate(r['votes']):
            if len(v) < 3 or v[2] is None:
                continue
            c = cat[r['asset']][r['categories'][i]]
            c[1] += 1
            c[0] += 1 if v[2] else 0
    out['byCategory'] = {
        k: dict(maxN=max((v[1] for v in cats.values()), default=0),
                rows=sorted(({'category': n, 'hits': v[0], 'n': v[1],
                              'pct': round(100 * v[0] / v[1], 1)} for n, v in cats.items()),
                            key=lambda x: (-x['pct'], -x['n'])))
        for k, cats in cat.items()}
    out['byCategoryWarning'] = (
        "Category denominators vary with how often each category voted directionally. "
        "Below roughly 20 marked votes per category these rankings invert on the next "
        "settlement and should be reported as not yet meaningful.")
    return out

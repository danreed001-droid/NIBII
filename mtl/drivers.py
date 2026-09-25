"""Driver regime: what is actually moving each market, measured not assumed."""
import math

DOMINANCE = 0.40
BIG_DAY_BP = 5.0


def pct_changes(series):
    return [(series[i] / series[i - 1] - 1) * 100 for i in range(1, len(series))]


def bp_changes(series):
    return [(series[i] - series[i - 1]) * 100 for i in range(1, len(series))]


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da * db else float('nan')


def beta(a, b):
    """Slope of a (% move) on b (bp change)."""
    mb, ma = sum(b) / len(b), sum(a) / len(a)
    den = sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else float('nan')


def driver_regime(asset_returns: dict, d2y, d10y, doil, window_label="", dates=None):
    """asset_returns: {key: [daily % changes]}. d2y/d10y in bp, doil in %."""
    per_asset = {}
    for k, r in asset_returns.items():
        c2, c10, co = corr(r, d2y), corr(r, d10y), corr(r, doil)
        cands = {'2Y': abs(c2), '10Y': abs(c10), 'oil': abs(co)}
        top = max(cands, key=cands.get)
        per_asset[k] = dict(
            corr2Y=round(c2, 3), beta2Y=round(beta(r, d2y), 4),
            corr10Y=round(c10, 3), corrOil=round(co, 3),
            dominantDriver=top if cands[top] >= DOMINANCE else 'none',
            allDominant=[kk for kk, vv in cands.items() if vv >= DOMINANCE],
        )
    out = dict(window=window_label, n=len(d2y), perAsset=per_asset,
               method=("daily % change of each asset regressed on the daily change in the US 2-year "
                       "and 10-year yields (basis points) and on the daily % change in WTI; a driver "
                       f"is dominant when |corr| >= {DOMINANCE}"))

    if 'gold' in asset_returns and 'bonds' in asset_returns:
        g, t = asset_returns['gold'], asset_returns['bonds']
        same = sum(1 for x, y in zip(g, t) if x * y > 0)
        c = corr(g, t)
        out['goldVsTlt'] = dict(corr=round(c, 3), sameDirection=f"{same}/{len(g)}",
                                sharedDriverPair=bool(c >= DOMINANCE))

    idx = [i for i, v in enumerate(d2y) if abs(v) >= BIG_DAY_BP]
    if idx:
        out['bigDays'] = dict(
            n=len(idx),
            definition=f"|change in 2Y| >= {BIG_DAY_BP:g}bp",
            dates=[dates[i + 1] for i in idx] if dates else None,
            corrs={k: round(corr([r[i] for i in idx], [d2y[i] for i in idx]), 3)
                   for k, r in asset_returns.items()},
        )
    return out


def check_vote_signs(doc):
    """Every vote whose reason runs through oil must carry the measured sign."""
    problems = []
    per = doc['context']['driverRegime']['perAsset']
    for a in doc['assets']:
        co = per[a['key']]['corrOil']
        for h in a['horizons']:
            for i, v in enumerate(h['votes']):
                t = v[1].lower()
                if any(w in t for w in ('wti', 'oil', 'brent', 'crude')):
                    if v[0] == 'bull' and co <= 0:
                        problems.append(f"{a['key']}/h{h['h']} vote {i+1}: bull via oil but corrOil {co}")
                    if v[0] == 'bear' and co > 0:
                        problems.append(f"{a['key']}/h{h['h']} vote {i+1}: bear via oil but corrOil {co}")
    return problems

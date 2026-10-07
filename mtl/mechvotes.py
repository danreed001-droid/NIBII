"""Mechanical votes for categories 2 (Breadth), 3 (Volatility regime) and
4 (Credit).

Until now only category 13 (Market structure) was computed; every other
category was left to a judgment pass that, when it could not find a dated,
sourced figure, voted neutral. Breadth, volatility regime and credit were
neutral on 72-86% of cells in the first nine sessions, which is the main
reason ~70% of calls came out "no-call" (see mtl/resolve.py LIVE_GATE).

These three can be read straight from price series Yahoo serves, so they are
computed here with fixed, symmetric rules instead of being left to chance:

  Breadth  - RSP/SPY (equal-weight vs cap-weight S&P 500) ratio.
  Credit   - HYG/IEF (high-yield vs Treasury) ratio, a risk-appetite read.
  Vol      - the asset's own vol gauge (VIX, VXN, RVX) vs its 20-day mean.

Ratios use one trend rule: above their 50-day mean AND up over 20 sessions
-> bull; below AND down -> bear; anything else -> neu.  Vol is inverted
(falling and below its 20-day mean is calm = bull).

IMPORTANT - these rules are NOT backtested or calibrated.  They are standard,
symmetric reads chosen so the votes carry information, not tuned to history
(this environment cannot reach Yahoo, so no history was available).  Each
vote is graded at settlement like any other, so the track record will show
per-category hit rates; judge them on that, and drop or reweight a category
that does not earn its place.

Pure functions only - no network.  scripts/prepare_daily.py does the fetching.
"""
from __future__ import annotations

CATEGORY_NAMES = {2: 'Breadth', 3: 'Volatility regime', 4: 'Credit'}

MA_N = 50
CHG_N = 20
VOL_MA_N = 20
VOL_CHG_N = 5
VOL_BAND = 0.05      # must sit >5% above/below its 20-day mean to count

# Which assets each category speaks to.  Anything not listed votes neutral:
# a breadth or credit read has no clean direction for gold, the dollar or
# Treasuries, and vol has no matching gauge for bonds/dollar.
BREADTH_ASSETS = ('equities', 'iwm')
CREDIT_ASSETS = ('equities', 'qqq', 'iwm')
VOL_ASSETS = ('equities', 'qqq', 'iwm')

PREFIX = "Mechanical: "


def ratio_series(num_rows, den_rows, through):
    """Join two dated close series [(iso, close)] on date, keep dates <= through,
    return [(iso, num/den)] oldest first.  The blindness rule is enforced here:
    nothing dated after `through` is ever used."""
    den = {d: c for d, c in den_rows if d <= through and c}
    out = []
    for d, c in num_rows:
        if d <= through and d in den:
            out.append((d, c / den[d]))
    return out


def _mean(xs):
    return sum(xs) / len(xs)


def trend_read(values):
    """('bull'|'bear'|'neu', detail) for a ratio series (plain floats)."""
    need = max(MA_N, CHG_N + 1)
    if values is None or len(values) < need:
        return 'neu', f"only {0 if values is None else len(values)} sessions of history (need {need})"
    last = values[-1]
    ma = _mean(values[-MA_N:])
    chg = last / values[-1 - CHG_N] - 1
    detail = (f"ratio {last:.4f} vs 50-day mean {ma:.4f}, {chg * 100:+.2f}% over {CHG_N} sessions")
    if last > ma and chg > 0:
        return 'bull', detail
    if last < ma and chg < 0:
        return 'bear', detail
    return 'neu', detail + " - mixed, no clean read"


def vol_read(values):
    """Vol gauge closes (plain floats).  Calm and falling = bull, stressed and
    rising = bear, else neu."""
    need = max(VOL_MA_N, VOL_CHG_N + 1)
    if values is None or len(values) < need:
        return 'neu', f"only {0 if values is None else len(values)} sessions of history (need {need})"
    last = values[-1]
    ma = _mean(values[-VOL_MA_N:])
    chg = last / values[-1 - VOL_CHG_N] - 1
    detail = (f"gauge {last:.2f} vs 20-day mean {ma:.2f} ({(last / ma - 1) * 100:+.1f}%), "
              f"{chg * 100:+.1f}% over {VOL_CHG_N} sessions")
    if last < ma * (1 - VOL_BAND) and chg < 0:
        return 'bull', detail
    if last > ma * (1 + VOL_BAND) and chg > 0:
        return 'bear', detail
    return 'neu', detail + " - inside the band or not trending, no clean read"


def _vote(side, label, detail):
    return [side, f"{PREFIX}{label}: {detail}."]


def breadth_vote(asset_key, rsp_spy_values):
    if asset_key not in BREADTH_ASSETS:
        return _vote('neu', 'RSP/SPY breadth', f"not applicable to {asset_key}, so no vote")
    side, detail = trend_read(rsp_spy_values)
    return _vote(side, 'RSP/SPY equal-weight vs cap-weight breadth', detail)


def credit_vote(asset_key, hyg_ief_values):
    if asset_key not in CREDIT_ASSETS:
        return _vote('neu', 'HYG/IEF credit', f"no clean direction for {asset_key}, so no vote")
    side, detail = trend_read(hyg_ief_values)
    return _vote(side, 'HYG/IEF high-yield vs Treasury credit appetite', detail)


def vol_vote(asset_key, vol_values, gauge_name):
    if asset_key not in VOL_ASSETS:
        return _vote('neu', 'volatility regime', f"no matching vol gauge for {asset_key}, so no vote")
    side, detail = vol_read(vol_values)
    return _vote(side, f'{gauge_name} volatility regime', detail)


def unavailable(label, why):
    """Neutral vote for a feed that could not be fetched.  Never raises, so one
    dead ticker cannot stop the daily draft."""
    return _vote('neu', label, f"data unavailable ({why}), so no vote")

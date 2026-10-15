"""Run the default plan (NBup) with the dashboard's 15 Nasdaq-100 members outside the S&P 500 added.
Run from the engine folder (research/backtest/refresh.sh sets it up). env: NDX_JOIN (ndx_join_dates.json here:
{ticker: [[start, end|null], ...]}, each the first session in the Nasdaq-100 per Nasdaq's announcements), plus the
engine's usual env, e.g.

  env HARNESS_SIDE=<side folder> NIBII_REPO=<repo> NDX_JOIN=<repo>/research/validation/ndx_join_dates.json \
      FROM=1998-06-01 START=2000-01-03 EXCLUDE=EP,CPWR BOOST_ONLY=1 ONLY=NBup,NDXa,NDXh TAG=_ndx \
      DUMP_SCHED=NDXa_boost python <repo>/research/validation/ndx_universe.py

Jobs (same rules; only the stocks it may pick differ):
  NBup  point-in-time S&P 500 (the audit)
  NDXa  NBup plus the 15, each only while it was in the Nasdaq-100 (from its join date)
  NDXh  NBup plus the 15 from their first price (hindsight, like the dashboard's own replay)
"""
import json
import os
import sys

ENG = os.getcwd()
sys.path[:0] = [os.path.join(ENG, 'scripts'), ENG]
import robustness as R  # noqa: E402
import improve as I  # noqa: E402
from momentum_scan import blocked_dates  # noqa: E402

JOIN = json.load(open(os.environ['NDX_JOIN']))
_prep, _run = R.prepare, I.run_one


def prepare(D):
    P = _prep(D)
    pit = P['elig_pit']
    blocked = {t: blocked_dates(D['bars'][t]) for t in JOIN if D['bars'].get(t)}
    first = {t: D['bars'][t][0][0] for t in JOIN if D['bars'].get(t)}

    def member(t, d):
        return any(s <= d and (e is None or d < e) for s, e in JOIN[t])
    P['elig_ndxa'] = lambda t, d: pit(t, d) or (t in first and d not in blocked[t] and member(t, d))
    P['elig_ndxh'] = lambda t, d: pit(t, d) or (t in first and d not in blocked[t] and d >= first[t])
    R.log('Nasdaq-100 additions: ' + ', '.join(f'{t} {JOIN[t][0][0]}' for t in sorted(JOIN)))
    return P


def run_one(args):
    key, kw, boost, exclude = args
    u = kw.get('univ')
    if not u:
        return _run(args)
    kw = dict(kw)
    kw.pop('univ')
    P = I.G['P']
    keep = P['elig_pit']
    P['elig_pit'] = P['elig_' + u]
    try:
        return _run((key, kw, boost, exclude))
    finally:
        P['elig_pit'] = keep


R.prepare, I.run_one = prepare, run_one
base = I.VARIANTS['NBup']
I.VARIANTS['NDXa'] = (dict(base[0], univ='ndxa'), None)
I.VARIANTS['NDXh'] = (dict(base[0], univ='ndxh'), None)

if __name__ == '__main__':
    I.main()

"""Nightly: the dominoes card's data (data/dominoes.json, mtl/dominoes.py). Information only: the plan doesn't use it.

Fetches the long histories the eight dominoes need (back to 1985: the S&P 500, Nasdaq, Russell 2000, the banking,
transport and high-yield funds, the Fed funds rate, the yield curve, oil, inflation) plus long Treasuries and gold for
what followed, and the macro signals' inputs for the "what was happening then" lines. If any domino's data is
missing, the last file stays and the problem goes in the issues log.

    python scripts/dominoes.py"""
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mtl import dominoes as dm, events as ev, health, macro_events  # noqa: E402
from scripts import event_patterns as ep  # noqa: E402

OUT = os.path.join(ROOT, 'data', 'dominoes.json')
YF = {'spx': '^GSPC', 'tech': '^IXIC', 'small': '^RUT', 'banks': 'FSRBX', 'transport': 'FSRFX', 'junk': 'VWEHX',
      'bonds': 'VUSTX', 'gold': 'GC=F'}
FRED = {'fed': 'DFF', 'curve': 'T10Y3M', 'oil': 'DCOILWTICO', 'cpi': 'CPIAUCSL'}
NEED = ('spx', 'tech', 'small', 'banks', 'transport', 'junk', 'fed', 'curve', 'oil', 'cpi')
MIN_LEN = dict(cpi=400)          # monthly since 1947; the daily ones need 8,000+ sessions (back to the late 1980s)


def fetch():
    """({key: {date: value}}, the macro signals' inputs, [inputs that came back short])."""
    import yfinance as yf
    ser = {}
    for k, t in {**YF, **{f'm:{v}': v for v in ep.MACRO_YF.values() if v not in YF.values()}}.items():
        try:
            df = yf.download(t, start='1985-01-01', auto_adjust=True, progress=False)
            c = df['Close']
            c = c[t] if hasattr(c, 'columns') else c
            ser[k] = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
        except Exception:   # noqa: BLE001 - checked below
            ser[k] = {}
    got, _ = ep.fetch_fred(tuple(FRED.values()) + tuple(v for v in ep.MACRO_FRED.values() if v not in FRED.values()))
    for k, sid in FRED.items():
        ser[k] = got[f'FRED:{sid}']
    short = [k for k in NEED if len(ser.get(k) or {}) < MIN_LEN.get(k, 8000)]
    px = {t: ser[k] for k, t in YF.items()}
    px.update({t: ser.get(f'm:{t}', {}) for t in ep.MACRO_YF.values() if t not in YF.values()})
    px.update(got)
    return ser, ep.macro_inputs(px), short


def context(cal, macro):
    """[(date, text)]: the macro signals over the whole history and the hand-picked events, for "what was happening
    then" under each past match."""
    out = [(d, w.split(':', 1)[0]) for d, w in macro_events.find(cal, macro, cal[0])]
    try:
        out += [(e['d'], e['what'] if len(e['what']) <= 70 else e['what'][:67].rstrip() + '…')
                for e in ev.load()['events'] if e['src'] == 'curated' and e.get('type') != 'Turning point']
    except (OSError, ValueError):
        pass
    return out


def main():
    today = datetime.now(timezone.utc).date().isoformat()
    ser, macro, short = fetch()
    if short:
        log = health.load()
        health.add(log, today, 'dominoes', f"No full history for {', '.join(short)} tonight, so the dominoes card shows the "
                   'last good reading (it never affects the plan).')
        health.save(log)
        print(f"dominoes: short data for {', '.join(short)}; keeping {OUT}")
        return
    cal = sorted(ser['spx'])
    doc = dm.build(cal, ser, context(cal, macro))
    if not doc:
        raise SystemExit('dominoes: not enough history to build the card')
    doc = dict(about='The dominoes card (mtl/dominoes.py, scripts/dominoes.py). Information only.',
               updated=datetime.now(timezone.utc).isoformat(timespec='seconds'), **doc)
    with open(OUT, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    print(f"wrote {OUT}: {doc['count']} of 8 dominoes down, {len(doc['matches'])} past matches")


if __name__ == '__main__':
    main()

"""Nightly: add new major market events by the automatic rules (mtl/events.py), fill in SPY's moves, and draw
docs/events.html. Information only; the plan doesn't read it.

    python scripts/major_events.py            # fetch SPY and the VIX, update data/major_events.json, render
    python scripts/major_events.py --render   # just redraw the page from the saved list"""
import html
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import events as ev  # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'events.html')


def fetch():
    import yfinance as yf
    out = {}
    for t in ('SPY', '^VIX'):
        df = yf.download(t, start='1999-06-01', auto_adjust=True, progress=False)
        c = df['Close']
        c = c[t] if hasattr(c, 'columns') else c
        out[t] = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
    if len(out['SPY']) < 5000:
        raise SystemExit(f"SPY history came back short ({len(out['SPY'])} closes)")
    return out


def pct(x):
    if x is None:
        return '<span class="muted">–</span>'
    s = f"{x * 100:+.1f}%".replace('-', '−')
    return f'<span class="{"pos" if x > 0 else "neg" if x < 0 else ""}">{s}</span>'


def render(doc):
    evs = sorted(doc['events'], key=lambda e: e['d'], reverse=True)
    years = {}
    for e in evs:
        years.setdefault(e['d'][:4], []).append(e)
    parts = []
    for y, es in years.items():
        rows = []
        for e in es:
            d = date.fromisoformat(e['d'])
            tag = '' if e['src'] == 'curated' else f' <span class="tag">{html.escape(e["src"].replace("auto: ", "auto · "))}</span>'
            rows.append(f'<tr><td class="d">{d.strftime("%b")} {d.day}</td><td>{html.escape(e["what"])}{tag}</td>'
                        f'<td class="n">{pct(e.get("day"))}</td><td class="n">{pct(e.get("month"))}</td></tr>')
        parts.append(f'<h2>{y}</h2><table><thead><tr><th>Date</th><th>Event</th><th class="n">Day</th>'
                     f'<th class="n">1 month</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')
    upd = doc.get('updated') or ''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Market Events</title>
<style>
:root {{ --bg: #fbfaf7; --ink: #1d1c1a; --muted: #6f6d67; --line: #e1e0d9; --pos: #0a8f0a; --neg: #c43232; --tag: #eeece6; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #161615; --ink: #ecebe6; --muted: #98968f; --line: #2c2c2a; --pos: #3fbf5f; --neg: #e5605a; --tag: #262624; }} }}
:root[data-theme="dark"] {{ --bg: #161615; --ink: #ecebe6; --muted: #98968f; --line: #2c2c2a; --pos: #3fbf5f; --neg: #e5605a; --tag: #262624; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.45 -apple-system, system-ui, "Segoe UI", sans-serif; }}
.wrap {{ max-width: 920px; margin: 0 auto; padding: 18px 16px 48px; }}
.nav a {{ color: var(--muted); text-decoration: none; font-size: 0.85rem; }}
h1 {{ font-size: 1.6rem; margin: 10px 0 6px; }} h2 {{ font-size: 1.05rem; margin: 26px 0 6px; }}
p.note {{ color: var(--muted); font-size: 0.86rem; margin: 6px 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
th {{ text-align: left; color: var(--muted); font-weight: 600; font-size: 0.75rem; border-bottom: 1px solid var(--line); padding: 4px 6px; }}
td {{ border-bottom: 1px solid var(--line); padding: 6px; vertical-align: top; }}
td.d {{ white-space: nowrap; color: var(--muted); width: 3.6em; }} .n {{ text-align: right; white-space: nowrap; width: 5.5em; }}
.pos {{ color: var(--pos); }} .neg {{ color: var(--neg); }} .muted {{ color: var(--muted); }}
@media (max-width: 520px) {{ table {{ font-size: 0.84rem; }} td, th {{ padding: 6px 3px; }} .n {{ width: 3.9em; }} td.d {{ width: 3.2em; }} }}
.tag {{ font-size: 0.68rem; background: var(--tag); color: var(--muted); border-radius: 6px; padding: 1px 6px; white-space: nowrap; }}
</style></head><body><div class="wrap">
<div class="nav"><a href="scanner.html">← Top 5 Strongest</a></div>
<h1>Market events since 2000</h1>
<p class="note">Major events and how the S&amp;P 500 (SPY) moved: on the first day it could react, and over the next month
(21 trading days), shown as Day and 1 month. New ones are added each night when SPY moves 2.5% or more in a day (with the day's headline from the news log),
the Fed changes rates, the VIX closes above 30 for the first time in three months, or the market enters a correction, a bear market or
a new bull run; those carry an <span class="tag">auto</span> tag. The next-month figure fills in a month later. Information only:
the plan doesn't use it.</p>
<p class="note">Updated {html.escape(upd[:10])} · {len(evs)} events</p>
{"".join(parts)}
</div></body></html>
'''


def main(argv):
    doc = ev.load()
    if '--render' not in argv:
        px = fetch()
        cal = sorted(px['SPY'])
        spy = [px['SPY'][d] for d in cal]
        try:
            with open(ev.NEWS) as fh:
                news = [x['data'] for x in json.load(fh)]
        except FileNotFoundError:
            news = []
        new = ev.auto(doc['events'], cal, spy, px['^VIX'], news)
        ev.reactions(doc['events'], cal, spy)
        doc['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        ev.save(doc)
        print(f"events: {len(doc['events'])}, added tonight: {', '.join(new) or 'none'}")
    with open(OUT, 'w') as fh:
        fh.write(render(doc))
    print(f"wrote {OUT}")


if __name__ == '__main__':
    main(sys.argv[1:])

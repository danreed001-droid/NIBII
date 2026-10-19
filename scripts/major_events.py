"""Nightly: save the day's headlines from the free feeds (mtl/news_feeds.py), read any new FOMC statement, add new
major market events by the automatic rules (mtl/events.py), fill in SPY's moves, and draw docs/events.html. Information
only; the plan doesn't read it. A feed that hasn't worked for three days goes in the scanner page's issues list.

    python scripts/major_events.py            # fetch SPY, the VIX and the feeds, update data/major_events.json, render
    python scripts/major_events.py --moves    # after the "Add news" form: your items and SPY's moves, no feeds
    python scripts/major_events.py --render   # just redraw the page from the saved list"""
import html
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import events as ev, health, news_feeds as nf  # noqa: E402

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


def update_fed(doc, heads, today, get=nf.fetch):
    """Read each FOMC statement since AUTO_SINCE that isn't saved yet into doc['fed']. Returns an error or None."""
    fed = doc.setdefault('fed', [])
    try:
        for d, link in nf.fed_statements(get(nf.FED_FEED)):
            if d >= ev.AUTO_SINCE and link and not any(f['link'] == link for f in fed):
                got = nf.decision(get(link))
                if got:
                    fed.append(dict(d=d, action=got[0], lo=got[1], hi=got[2], link=link))
        heads['feeds']['Fed'] = today
    except Exception as e:   # noqa: BLE001 - the other sources still run
        return f'{type(e).__name__}: {e}'[:200]
    fed.sort(key=lambda f: f['d'])
    return None


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
            label = ev.tag(e)
            tag = f' <span class="tag">{html.escape(label)}</span>' if label else ''
            what = html.escape(e['what'])
            if (e.get('link') or '').startswith(('http://', 'https://')):
                what = f'<a href="{html.escape(e["link"])}" target="_blank" rel="noopener">{what}</a>'
            find = ev.search_text(e)
            mv = ''.join(f' data-{k}="{e[k]}"' for k in ('day', 'month') if e.get(k) is not None)
            rows.append(f'<tr data-s="{html.escape(find)}"{mv}><td class="d">{d.strftime("%b")} {d.day}</td><td>{what}{tag}</td>'
                        f'<td class="n">{pct(e.get("day"))}</td><td class="n">{pct(e.get("month"))}</td></tr>')
        parts.append(f'<section class="yr"><h2>{y}</h2><table><thead><tr><th>Date</th><th>Event</th><th class="n">Day</th>'
                     f'<th class="n">1 month</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')
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
td a {{ color: inherit; text-decoration-color: var(--muted); text-underline-offset: 2px; }}
a.add {{ display: inline-block; margin: 8px 0 2px; padding: 7px 14px; border-radius: 8px; background: var(--ink); color: var(--bg);
  font-weight: 600; font-size: 0.88rem; text-decoration: none; }}
.find {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; align-items: center; }}
.find input, .find select {{ font: inherit; font-size: 16px; color: var(--ink); background: var(--bg); border: 1px solid var(--line);
  border-radius: 8px; padding: 7px 10px; }}
.find input[type=search] {{ flex: 1 1 100%; }}
.find .mv {{ display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; }}
@media (max-width: 350px) {{ .find .mv {{ flex-wrap: wrap; }} }}
.find select {{ padding: 7px 4px; }}
.find input[type=number] {{ width: 3.4em; padding: 7px 6px; }}
p.acts {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; margin: 10px 0; }}
p.acts .note {{ margin: 0; flex: 1 1 260px; color: var(--muted); font-size: 0.86rem; }}
.nw {{ white-space: nowrap; }}
a.add {{ margin: 0; }}
details.how {{ margin: 28px 0 0; }} details.how summary {{ color: var(--muted); font-size: 0.86rem; cursor: pointer; }}
.find .lbl {{ color: var(--muted); font-size: 0.86rem; }}
.find button {{ font: inherit; font-size: 0.86rem; color: var(--muted); background: none; border: 0; padding: 7px 4px; cursor: pointer;
  text-decoration: underline; text-underline-offset: 2px; }}
p.count {{ color: var(--muted); font-size: 0.86rem; margin: 6px 0 0; }}
.tag {{ font-size: 0.68rem; background: var(--tag); color: var(--muted); border-radius: 6px; padding: 1px 6px; white-space: nowrap; }}
</style></head><body><div class="wrap">
<div class="nav"><a href="scanner.html">← Top 5 Strongest</a></div>
<h1>Market events since 2000</h1>
<p class="note">Major events and how the S&amp;P 500 (SPY) moved on the first day it could react (Day) and over the next month
(1 month, 21 trading days). <span class="nw">Updated {html.escape(upd[:10])}</span> · {len(evs)} events.</p>
<p class="acts"><a class="add" href="{ev.ADD_URL}" target="_blank" rel="noopener">＋ Add news</a>
<span class="note">Opens a short form in the repo. Press Submit and it shows here in a few minutes, tagged
<span class="tag">added by you</span>. To remove one, send it again with Remove.</span></p>
<div class="find" role="search">
  <input id="q" type="search" placeholder="Search events (Fed, COVID, 2008…)" aria-label="Search events or headlines" autocomplete="off">
  <span class="mv"><select id="per" aria-label="Which move"><option value="day">Day</option><option value="month">1 month</option></select>
  <select id="dir" aria-label="Direction"><option value="any">up/down</option><option value="up">up</option><option value="down">down</option></select>
  <span class="lbl" aria-hidden="true">≥</span><input id="min" type="number" inputmode="decimal" min="0" step="0.5" placeholder="0" aria-label="Moved at least this many percent"><span class="lbl">%</span></span>
  <button id="clear" type="button" hidden>Clear</button>
</div>
<p class="count" id="count" aria-live="polite"></p>
{"".join(parts)}
<p class="note" id="none" hidden>No events match. Try fewer words or a smaller move.</p>
<details class="how"><summary>How this list works</summary>
<p class="note">New events are added each night when SPY moves 2.5% or more in a day (with the day's headline), the Fed changes
rates, the VIX closes above 30 for the first time in three months, or the market enters a correction, a bear market or a new bull
run; those carry an <span class="tag">auto</span> tag. A big day's headline comes from the daily news log when it has one for that
day, else from MarketWatch or Google News (named in brackets); Fed rate changes are read from the Fed's own FOMC statements. The
1-month figure fills in a month later. Search matches the event text, its date or year, and its tag; the move filter uses the Day
or 1 month column, and events without that figure yet drop out while it's on. Information only: the plan doesn't use it.</p>
</details>
<script>
{ev.MATCH_JS}
(function () {{
  var q = document.getElementById('q'), per = document.getElementById('per'), dir = document.getElementById('dir'),
      min = document.getElementById('min'), clear = document.getElementById('clear'), count = document.getElementById('count'),
      none = document.getElementById('none'), secs = document.querySelectorAll('section.yr'), total = {len(evs)};
  // a link from the scanner page's events search arrives as #q=...&per=...&dir=...&min=...
  try {{
    var h = new URLSearchParams(location.hash.slice(1));
    if (h.get('q')) q.value = h.get('q');
    if (h.get('per') === 'month') per.value = 'month';
    if (['up', 'down'].indexOf(h.get('dir')) >= 0) dir.value = h.get('dir');
    if (h.get('min')) min.value = h.get('min');
  }} catch (e) {{}}
  function apply() {{
    var f = evFilter(q, per, dir, min), shown = 0;
    secs.forEach(function (sec) {{
      var n = 0;
      sec.querySelectorAll('tbody tr').forEach(function (tr) {{
        var ok = evMatch(tr.dataset.s, tr.dataset.day, tr.dataset.month, f);
        tr.hidden = !ok; n += ok ? 1 : 0;
      }});
      sec.hidden = !n; shown += n;
    }});
    var on = evOn(f);
    clear.hidden = !on; none.hidden = shown > 0;
    count.textContent = on ? 'Showing ' + shown + ' of ' + total + ' events' : '';
  }}
  [q, min].forEach(function (el) {{ el.addEventListener('input', apply); }});
  [per, dir].forEach(function (el) {{ el.addEventListener('change', apply); }});
  clear.addEventListener('click', function () {{ q.value = ''; min.value = ''; dir.value = 'any'; per.value = 'day'; apply(); q.focus(); }});
  apply();
}})();
</script>
</div></body></html>
'''


def moves(doc):
    px = fetch()
    cal = sorted(px['SPY'])
    ev.reactions(doc['events'], cal, [px['SPY'][d] for d in cal])


def main(argv):
    doc = ev.load()
    ev.sync_mine(doc['events'], ev.load_mine())
    if '--moves' in argv:
        moves(doc)
        doc['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    elif '--render' not in argv:
        px = fetch()
        cal = sorted(px['SPY'])
        spy = [px['SPY'][d] for d in cal]
        try:
            with open(ev.NEWS) as fh:
                news = [x['data'] for x in json.load(fh)]
        except FileNotFoundError:
            news = []
        today = datetime.now(nf.NY).date().isoformat()
        heads = nf.load_log()
        bad = nf.collect(heads, today)
        err = update_fed(doc, heads, today)
        if err:
            bad.append(('Fed', err))
        for name, e in bad:
            print(f"news feed {name} failed: {e}")
        nf.save_log(heads, today)
        dead = nf.stale(heads, today, list(nf.FEEDS) + ['Fed'])
        if dead:
            log = health.load()
            health.add(log, today, 'events', f"News feed not working for {nf.STALE_DAYS}+ days: {', '.join(dead)}. "
                       "The events page still runs; big-move days may lack a headline.")
            health.save(log)
        new = ev.auto(doc['events'], cal, spy, px['^VIX'], news, headlines=heads['items'], fed=doc['fed'])
        ev.reactions(doc['events'], cal, spy)
        doc['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        print(f"events: {len(doc['events'])}, added tonight: {', '.join(new) or 'none'}")
    ev.save(doc)
    with open(OUT, 'w') as fh:
        fh.write(render(doc))
    print(f"wrote {OUT}")


if __name__ == '__main__':
    main(sys.argv[1:])

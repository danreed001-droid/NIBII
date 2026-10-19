"""Nightly: save the day's headlines from the free feeds (mtl/news_feeds.py), read any new FOMC statement, add new
major market events by the automatic rules (mtl/events.py), fill in SPY's moves, and draw docs/events.html with where
the plan was on each event (mtl/plan_history.py). Information only; the plan doesn't read it. A feed that hasn't worked for three days goes in the scanner page's issues list.

    python scripts/major_events.py            # fetch SPY, the VIX and the feeds, update data/major_events.json, render
    python scripts/major_events.py --moves    # after the "Add news" form: your items and SPY's moves, no feeds
    python scripts/major_events.py --render   # just redraw the page from the saved list
    python scripts/major_events.py --patterns # also rebuild what usually followed each type (otherwise weekly)"""
import html
import json
import os
import sys
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mtl import events as ev, event_types as et, health, news_feeds as nf, plan_history as ph  # noqa: E402
from scripts import event_patterns as ep  # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'events.html')


SIDE_TICKERS = ('GLD', 'GC=F', 'TLT', 'VUSTX')   # the plan's gold and bond funds, and what stands in before they started
TLT_FROM = '2002-07-30'                          # long Treasuries: TLT from here, Vanguard's long-term Treasury fund before


def fetch():
    """SPY and the VIX (the page can't run without SPY), plus gold and long Treasuries for their moves under each event:
    one of those failing leaves its figures as they were and is listed in '_missing'."""
    import yfinance as yf
    out, missing = {}, []
    for t in ('SPY', '^VIX') + SIDE_TICKERS:
        try:
            df = yf.download(t, start='1999-06-01', auto_adjust=True, progress=False)
            c = df['Close']
            c = c[t] if hasattr(c, 'columns') else c
            out[t] = {d.date().isoformat(): float(v) for d, v in c.dropna().items()}
        except Exception:   # noqa: BLE001 - checked below
            out[t] = {}
        if t in SIDE_TICKERS and len(out[t]) < 250:
            missing.append(t)
    if len(out['SPY']) < 5000:
        raise SystemExit(f"SPY history came back short ({len(out['SPY'])} closes)")
    out['_missing'] = missing
    return out


def side_closes(px, cal):
    """Gold and long Treasuries on SPY's calendar as ev.side_moves takes them: the funds the plan holds (GLD, TLT) and,
    for windows starting before those existed, gold futures (before Nov 19, 2004) and the long-term Treasury fund
    (before Jul 30, 2002)."""
    al = lambda t: [None if np.isnan(x) else float(x) for x in ep.align(px.get(t, {}), cal)]
    return dict(gold=[(0, al('GC=F')), (bisect_left(cal, ep.GOLD_ETF_FROM), al('GLD'))],
                bonds=[(0, al('VUSTX')), (bisect_left(cal, TLT_FROM), al('TLT'))])


def all_moves(doc, px, cal, today=None):
    """SPY's, gold's and bonds' moves for every event; a missing gold or bond feed goes in the issues list."""
    ev.reactions(doc['events'], cal, [px['SPY'][d] for d in cal])
    ev.side_moves(doc['events'], cal, side_closes(px, cal))
    ev.plan_moves(doc['events'], cal, ph.load_values())
    if px.get('_missing'):
        print(f"no prices for {', '.join(px['_missing'])}: those moves stay as they were")
        log = health.load()
        health.add(log, today or datetime.now(nf.NY).date().isoformat(), 'events',
                   f"No prices for {', '.join(px['_missing'])} tonight, so new events' gold or bond moves fill in later "
                   '(it never affects the plan).')
        health.save(log)


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


def share(x):
    return f"{round(x * 100)}%"


def signed(x):
    return f"{x * 100:+.1f}%".replace('-', '−')


SIDE_NAME = {'gold': 'Gold', 'bonds': 'Bonds', 'plan': 'The plan'}


def nums(e, h):
    """An event's 'day' or 'month' cell: the S&P's move, then gold's, bonds' and the plan's under it, each with its dot."""
    sub = ''.join(f'<span class="sd" title="{SIDE_NAME[a]}"><i class="dot k-{a}"></i>{pct(x)}</span>'
                  for a in ev.SIDE + ('plan',) for x in [(e.get(a) or {}).get(h)] if x is not None)
    return ('<i class="dot k-stocks"></i>' if sub else '') + pct(e.get(h)) + sub


HELD = '<span class="held" title="held in both halves of the history">✓</span>'


def odds(c):
    """'31%', or '4 of 4' for a small sample so it doesn't read as more certain than it is."""
    return f"{round(c['up'] * c['n'])} of {c['n']}" if c['n'] < 10 else share(c['up'])


def follow(e, pats):
    """The "what usually followed" line under a recent event: its type's history (or its group's, when the type has
    too few complete 3-month windows), and the group's split by the S&P's trend at the time."""
    t = e.get('type')
    pats = pats or {}
    T = pats.get('types', {}).get(t)
    g = et.group(t) if t else None
    G = pats.get('groups', {}).get(g)
    src, who = T, f"{html.escape(t)}, {T['n']} before" if T else ''
    if not (T and T['assets']['S&P 500']['quarter']) and G:
        src, who = G, f"{et.GROUP_SHORT[g][0].upper() + et.GROUP_SHORT[g][1:]}, {G['n']} before"
    if not src or not src['assets']['S&P 500']['quarter']:
        return ''
    q, bd, gd = (src['assets'][a][h] for a, h in (('S&P 500', 'quarter'), ('Bonds', 'day'), ('Gold', 'day')))
    norm = pats['baseline']['S&P 500']['63']['up']
    out = f"{who}: S&amp;P higher 3 months later in {odds(q)} (avg {signed(q['avg'])}{HELD if q['held'] else ''}, normally {share(norm)})"
    if bd and gd:
        out += f" · on the day bonds rose in {odds(bd)}{HELD if bd['held'] else ''}, gold in {odds(gd)}{HELD if gd['held'] else ''}"
    trend = e.get('trend')
    if G and trend:
        c = G.get(f'{trend}200', {}).get('quarter')
        if c and c['n'] >= 5:
            out += f" · with the S&amp;P {trend} its 200-day average, all {et.GROUP_SHORT[g]}: {odds(c)} higher ({signed(c['avg'])})"
    return f'<div class="pat">{out}. <a href="#t-{et.slug(t)}">More</a></div>'


def _md(d):
    d = date.fromisoformat(d)
    return f"{d.strftime('%b')} {d.day}"


def where(sh):
    """'gold', or 'stocks 80%' when the rest is elsewhere."""
    k = ph.main(sh)
    x = sh[ph.ORDER.index(k)]
    return k + (f' {share(x)}' if x < 0.99 else '')


def plan_line(tl, d):
    """Under an event: what the plan held through that day, and its first move in the month after, if any."""
    sh = ph.during(tl, d)
    if sh is None:
        return ''
    k = ph.main(sh)
    full = ', '.join(f'{w} {share(x)}' for w, x in zip(ph.ORDER, sh) if x >= 0.01)
    out = f'<div class="pl" title="{full}"><i class="dot k-{k}"></i>Plan: {where(sh)}'
    sw = ph.switch(tl, d)
    if sw:
        out += f' <span class="nw">→ <i class="dot k-{sw[1]}"></i>{sw[1]} {_md(sw[0])}</span>'
    return out + '</div>'


def plan_now(tl, asof):
    """The line at the top: where the plan is after the latest close, and its next decided move."""
    got = ph.now(tl, asof)
    if not got:
        return ''
    sh, start, nxt = got
    k = ph.main(sh)
    out = (f'<p class="now"><i class="dot k-{k}"></i>The plan now: <b>{where(sh)}</b>, since the {_md(start)} close')
    if nxt:
        out += f'; it moves to <i class="dot k-{nxt[1]}"></i>{nxt[1]} at the {_md(nxt[0])} close'
    return out + '.</p>'


def record_card(log, pats):
    """The live scorecard: each new event's odds as shown the day it appeared, checked 3 months later."""
    r = ep.record(log)
    since = date.fromisoformat((log or {}).get('since', ev.AUTO_SINCE))
    head = f'<div class="tcard" id="t-live"><h3>Live record since {since.strftime("%b")} {since.day}, {since.year}</h3>'
    intro = ('<p class="note">Each new event\'s odds are saved the day it appears and checked 3 months later, so you can see '
             'whether these patterns keep working on events they haven\'t seen.')
    if not r['n']:
        due = ''
        pend = [x for x in (log or {}).get('entries', []) if x.get('spy_q') is None]
        if pend:
            first = date.fromisoformat(min(x['d'] for x in pend)) + timedelta(days=92)
            due = f" {len(pend)} waiting; the first check is due around {first.strftime('%b')} {first.day}, {first.year}."
        return head + intro + f' Nothing scored yet.{due}</p></div>'
    norm = share(pats['baseline']['S&P 500']['63']['up']) if pats else 'the any-day'
    out = (head + intro + f" {r['n']} scored ({r['pending']} waiting): the more likely side came true in <b>{r['right']} of "
           f"{r['calls']}</b>; always going with the any-day odds (higher {norm} of the time) would have got {r['normal_right']} "
           f"of {r['n']}. Average miss (0 = perfect, 0.25 = a coin toss): {r['brier']:.2f} vs {r['brier_normal']:.2f}.</p>")
    rows = []
    for x in sorted((x for x in log['entries'] if x.get('spy_q') is not None), key=lambda x: x['d'], reverse=True)[:10]:
        d = date.fromisoformat(x['d'])
        ok = (x['spy_q'] > 0) == (x['up'] > 0.5) if x['up'] != 0.5 else None
        mark = '' if ok is None else ('<span class="held">✓</span>' if ok else '<span class="neg">✗</span>')
        rows.append(f'<tr><td class="d">{d.strftime("%b")} {d.day} {d.year}</td><td>{html.escape(x["what"])}</td>'
                    f'<td class="n">{share(x["up"])}</td><td class="n">{pct(x["spy_q"])} {mark}</td></tr>')
    return out + ('<table class="pt"><thead><tr><th>Date</th><th>Event</th><th class="n">Said higher</th><th class="n">S&amp;P 3 months</th>'
                  f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def type_cards(pats, log=None):
    """The fold with every type's table: how often each asset was higher after it, and the average move."""
    if not pats:
        return ''
    labels = (('day', 'Day'), ('month', '1 month'), ('quarter', '3 months'))
    def table(assets):
        rows = []
        for a, cells in assets.items():
            tds = []
            for lab, _ in labels:
                c = cells.get(lab) if isinstance(cells, dict) else None
                if c and 'up' in c:
                    tds.append(f'<td><b>{share(c["up"])}</b> <span class="muted">{signed(c["avg"])}</span>{HELD if c.get("held") else ""}</td>')
                else:
                    tds.append('<td class="muted">–</td>')
            rows.append(f'<tr><th>{html.escape(a)}</th>{"".join(tds)}</tr>')
        return (f'<table class="pt"><thead><tr><th></th>{"".join(f"<th>{x}</th>" for _, x in labels)}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>')
    base = {a: {lab: v[str(h)] for lab, h in ep.H.items()} for a, v in pats['baseline'].items()}
    cards = [record_card(log, pats), f'<div class="tcard"><h3>Any day (for comparison)</h3>{table(base)}</div>']
    for t, (g, desc) in et.TYPES.items():
        T = pats['types'].get(t)
        if not T:
            continue
        sect = T.get('sectors') or []
        good = [x for x in sect if x['beat'] >= 0.6][:2]
        bad = [x for x in sect[::-1] if x['beat'] <= 0.4][:2]
        sline = ''
        if good or bad:
            f = lambda x: f"{x['name']} ({share(x['beat'])}{HELD if x['held'] else ''})"
            sline = ('<p class="note">Next 3 months vs the S&amp;P 500: ' +
                     (f"usually beat it: {', '.join(f(x) for x in good)}" if good else '') + ('; ' if good and bad else '') +
                     (f"usually lagged: {', '.join(f(x) for x in bad)}" if bad else '') + '.</p>')
        gline = ''
        G = pats['groups'].get(g)
        if G and g in et.GROUP_NAME:
            parts = []
            for lab, word in (('above200', 'above'), ('below200', 'below')):
                c = G[lab]['quarter']
                if c:
                    parts.append(f"{word} its 200-day average {share(c['up'])} ({signed(c['avg'])}, {c['n']})")
            q = G['assets']['S&P 500']['quarter']
            gline = (f'<p class="note">All {et.GROUP_NAME[g]}, {G["n"]} events: higher 3 months later {share(q["up"])} '
                     f'(avg {signed(q["avg"])}); with the S&amp;P {"; ".join(parts)}.</p>')
        cards.append(f'<div class="tcard" id="t-{et.slug(t)}"><h3>{html.escape(t)}</h3><p class="note">{html.escape(desc)} · '
                     f'{T["n"]} events ({T["clusters"]} separate episodes), {T["first"][:4]}–{T["last"][:4]}</p>'
                     f'{table(T["assets"])}{sline}{gline}</div>')
    return ('<details class="types" id="types"><summary>What usually followed each type of event</summary>'
            '<p class="note">How often each was higher on the event day, a month and 3 months later (bold), with the average '
            f'move. ✓ = it held in both halves of the history (before and after {html.escape(pats.get("split", "")[:4])}), so it '
            'keeps working as the years add up. Bonds = long Treasuries, gold = gold ETF (futures before 2005), '
            'oil = US crude. Small samples swing a lot: treat these as history, not forecasts. Big days, VIX spikes and market '
            'phases count every time the rule would have fired since 2000; the news types come from the list above. '
            f'It is a running calculation: rebuilt every week from every event so far, so new events join their type once '
            f'their 3 months have passed. Updated {html.escape(pats["updated"][:10])}.</p>' + ''.join(cards) + '</details>')


def render(doc, pats=None, log=None, plan=None):
    if pats is None:
        pats = ep.load()
    if log is None:
        log = ep.load_forecasts()
    if plan is None:
        plan = ph.load()
    evs = sorted(doc['events'], key=lambda e: e['d'], reverse=True)
    upd0 = (doc.get('updated') or datetime.now(timezone.utc).isoformat())[:10]
    recent = (date.fromisoformat(upd0) - timedelta(days=92)).isoformat()   # outcomes still to come
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
            t = e.get('type')
            if t and t != 'Other':
                tag += f' <a class="tag ty" href="#t-{et.slug(t)}">{html.escape(t)}</a>'
            pat = follow(e, pats) if (e['d'] >= recent or e['src'] == ev.MINE_SRC) else ''
            what = html.escape(e['what'])
            if (e.get('link') or '').startswith(('http://', 'https://')):
                what = f'<a href="{html.escape(e["link"])}" target="_blank" rel="noopener">{what}</a>'
            find = ev.search_text(e)
            mv = ''.join(f' data-{k}="{e[k]}"' for k in ('day', 'month') if e.get(k) is not None)
            cls = ' class="haspat"' if pat else ''
            rows.append(f'<tr data-s="{html.escape(find)}"{mv}{cls}><td class="d">{d.strftime("%b")} {d.day}</td><td>{what}{tag}{plan_line(plan, e["d"])}</td>'
                        f'<td class="n">{nums(e, "day")}</td><td class="n">{nums(e, "month")}</td></tr>')
            if pat:   # its own full-width row, so it isn't squeezed into the event column on a phone
                rows.append(f'<tr class="pr"><td></td><td colspan="3">{pat}</td></tr>')
        parts.append(f'<section class="yr"><h2>{y}</h2><table><thead><tr><th>Date</th><th>Event</th><th class="n">Day</th>'
                     f'<th class="n">1 month</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')
    upd = doc.get('updated') or ''
    try:
        asof = datetime.fromisoformat(upd).astimezone(nf.NY).date().isoformat()
    except ValueError:
        asof = upd0
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Market Events</title>
<style>
:root {{ --bg: #fbfaf7; --ink: #1d1c1a; --muted: #6f6d67; --line: #e1e0d9; --pos: #0a8f0a; --neg: #c43232; --tag: #eeece6;
  --k-stocks: #2a6fdb; --k-gold: #c08a00; --k-bonds: #12968a; --k-cash: #9a978f; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg: #161615; --ink: #ecebe6; --muted: #98968f; --line: #2c2c2a; --pos: #3fbf5f; --neg: #e5605a; --tag: #262624;
  --k-stocks: #5b95ee; --k-gold: #e0ac2e; --k-bonds: #35bfb1; --k-cash: #8d8b84; }} }}
:root[data-theme="dark"] {{ --bg: #161615; --ink: #ecebe6; --muted: #98968f; --line: #2c2c2a; --pos: #3fbf5f; --neg: #e5605a; --tag: #262624;
  --k-stocks: #5b95ee; --k-gold: #e0ac2e; --k-bonds: #35bfb1; --k-cash: #8d8b84; }}
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
a.ty {{ text-decoration: none; }}
.pat {{ font-size: 0.78rem; color: var(--muted); line-height: 1.4; }} tr.haspat td {{ border-bottom: 0; padding-bottom: 2px; }}
tr.pr td {{ padding-top: 0; }} .pat a {{ color: var(--muted); }}
.held {{ color: var(--pos); font-weight: 600; margin-left: 2px; }}
details.types {{ margin: 12px 0 0; }} details.types > summary {{ font-weight: 600; font-size: 0.92rem; cursor: pointer; }}
.tcard {{ border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; margin: 10px 0; scroll-margin-top: 12px; }}
.tcard h3 {{ font-size: 0.95rem; margin: 0 0 2px; }}
table.pt {{ font-size: 0.8rem; margin-top: 6px; }} table.pt th, table.pt td {{ padding: 4px; white-space: nowrap; }}
@media (max-width: 520px) {{ table.pt td .muted {{ display: block; font-size: 0.74rem; }} table.pt td {{ width: 27%; }} }}
table.pt tbody th {{ color: var(--ink); font-weight: 500; }}
.sd {{ display: block; font-size: 0.78rem; margin-top: 1px; }}
@media (max-width: 380px) {{ td .tag {{ white-space: normal; }} td.n {{ font-size: 0.8rem; }} td.n .dot {{ width: 6px; height: 6px; margin-right: 2px; }}
  td, th {{ padding: 6px 2px; }} }}
.pl {{ font-size: 0.76rem; color: var(--muted); margin-top: 2px; }}
.dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 4px 1px 0; vertical-align: middle; }}
.k-stocks {{ background: var(--k-stocks); }} .k-gold {{ background: var(--k-gold); }} .k-bonds {{ background: var(--k-bonds); }}
.k-cash {{ background: var(--k-cash); }} .k-plan {{ background: transparent; border: 1.5px solid var(--ink); box-sizing: border-box; }}
p.now {{ font-size: 0.9rem; margin: 8px 0; }}
.tag {{ font-size: 0.68rem; background: var(--tag); color: var(--muted); border-radius: 6px; padding: 1px 6px; white-space: nowrap; }}
</style></head><body><div class="wrap">
<div class="nav"><a href="scanner.html">← Top 5 Strongest</a></div>
<h1>Market events since 2000</h1>
<p class="note">Major events and how the <i class="dot k-stocks"></i>S&amp;P 500, <i class="dot k-gold"></i>gold,
<i class="dot k-bonds"></i>long-term Treasury bonds and <i class="dot k-plan"></i>the plan did on the first day the market could
react (Day) and over the next month (1 month, 21 trading days). <span class="nw">Updated {html.escape(upd[:10])}</span> · {len(evs)} events.</p>
{plan_now(plan, asof)}<p class="acts"><a class="add" href="{ev.ADD_URL}" target="_blank" rel="noopener">＋ Add news</a>
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
{type_cards(pats, log)}
{"".join(parts)}
<p class="note" id="none" hidden>No events match. Try fewer words or a smaller move.</p>
<details class="how"><summary>How this list works</summary>
<p class="note">New events are added each night when SPY moves 2.5% or more in a day (with the day's headline), the Fed changes
rates, the VIX closes above 30 for the first time in three months, or the market enters a correction, a bear market or a new bull
run; those carry an <span class="tag">auto</span> tag. A big day's headline comes from the daily news log when it has one for that
day, else from MarketWatch or Google News (named in brackets); Fed rate changes are read from the Fed's own FOMC statements. The
1-month figure fills in a month later. Each event has a type (tap it for that type's history), and events from the last 3 months,
plus your own, show what usually followed past events of the same type. The Plan line under each event is where today's plan
was through that day (stocks, gold, bonds or cash; a share when part of it sat elsewhere) and, after an arrow, its first move in the
month after. Before Oct 2026 it is the backtest of today's rules on the stocks in the S&amp;P 500 at the time (rerun with the
track record, so it shifts if the rules change); from then on it is the plan's live paper record, logged each night and never
rewritten, so new events get their line automatically and the move fills in as the month goes by. Search matches the event text, its date or year, its tag and
type; the move filter uses the S&amp;P's Day or 1 month figure, and events without that figure yet drop out while it's on.
Under each S&amp;P figure are gold's and long-term Treasury bonds' over the same days, as the plan holds them (the GLD and TLT
funds; before those started, gold futures until Nov 2004 and a long-term Treasury mutual fund until Jul 2002). The plan's figure
(the open circle) is what it made over the same days on whatever it held (its stock picks, gold, bonds or cash), before tax and after
0.15% a trade: the backtest of today's rules until Oct 15, 2026, then the live paper account. Information only:
the plan doesn't use it.</p>
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
      var last = true;
      sec.querySelectorAll('tbody tr').forEach(function (tr) {{
        if (tr.classList.contains('pr')) {{ tr.hidden = !last; return; }}   // an event's pattern row goes with it
        var ok = evMatch(tr.dataset.s, tr.dataset.day, tr.dataset.month, f);
        tr.hidden = !ok; last = ok; n += ok ? 1 : 0;
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
  // a type tag (#t-...) opens the patterns fold at that type's card
  function openType() {{
    var id = location.hash.slice(1), el = id.indexOf('t-') === 0 && document.getElementById(id);
    if (el) {{ document.getElementById('types').open = true; el.scrollIntoView(); }}
  }}
  window.addEventListener('hashchange', openType);
  openType();
}})();
</script>
</div></body></html>
'''


def moves(doc):
    px = fetch()
    all_moves(doc, px, sorted(px['SPY']))


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
        all_moves(doc, px, cal, today)
        if '--patterns' in argv or ep.stale():
            try:
                epx = ep.fetch()
                ep.save(ep.compute(doc, epx))
                print('event patterns rebuilt')
                if epx['_missing']:
                    log = health.load()
                    health.add(log, today, 'events', f"No prices for {', '.join(epx['_missing'])} in this week's event-patterns "
                               'refresh, so those columns are blank (it never affects the plan).')
                    health.save(log)
            except Exception as e:   # noqa: BLE001 - the page still renders with last week's patterns
                print(f"event patterns failed: {type(e).__name__}: {e}")
                log = health.load()
                health.add(log, today, 'events', 'The weekly event-patterns refresh failed, so the events page shows last '
                           "week's figures (it never affects the plan).")
                health.save(log)
        pats_now = ep.load()
        if pats_now:
            ep.update_forecasts(doc, pats_now, cal, spy, today)   # the live scorecard: save new odds, score old ones
        doc['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        print(f"events: {len(doc['events'])}, added tonight: {', '.join(new) or 'none'}")
    ev.save(doc)
    with open(OUT, 'w') as fh:
        fh.write(render(doc))
    print(f"wrote {OUT}")


if __name__ == '__main__':
    main(sys.argv[1:])

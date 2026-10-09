#!/usr/bin/env python3
"""Render a published ledger document as a self-contained HTML report.

Pure server-side rendering - no client JS required for the page to work; the
vote breakdown uses native <details> disclosure so it degrades to plain HTML.

Usage:
    python scripts/render_html.py 2026-09-24
    # -> documents/latest.html (overwritten each run - see main()'s docstring)
"""
import html
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtl import growth_rank
from mtl.documents import iter_document_paths
from mtl.record import aggregate
from mtl.calendar_nyse import is_trading_day, most_recent_completed_session, next_trading_day
from mtl.live_read import latest_note
from mtl.structure import CATEGORY_NAME as STRUCTURE_CATEGORY
from mtl.score import live_tilt, outcome, real_result

CALL_STATUS = {
    'bullish': ('good', '#0ca30c', '▲'),
    'bearish': ('critical', '#d03b3b', '▼'),
    'flat': ('flat', '#898781', '▬'),
    'no-call': ('warning', '#fab219', '?'),
}
VOTE_MARK = {'bull': ('good', '#0ca30c'), 'bear': ('critical', '#d03b3b'), 'neu': ('flat', '#898781')}
STRETCH_TONE = {
    'extreme-down': '#d03b3b', 'stretched-down': '#ec835a', 'neutral': '#898781',
    'stretched-up': '#ec835a', 'extreme-up': '#d03b3b',
}
TICKER = {
    # Fallback ONLY - use display_ticker(a) wherever an asset dict is in
    # scope, which prefers the document's own recorded a['ticker'] (see
    # mtl.build.build_document). TICKERS in mtl/fetch.py has already
    # changed once (ETFs -> futures) and will again; a static label here
    # would drift out of sync with whichever ticker actually backed a
    # given document's close - this map only fires for documents drafted
    # before the ticker field existed (e.g. 2026-09-24).
    'equities': 'SPX', 'bonds': 'TLT', 'gold': 'XAU',
    'dollar': 'DXY', 'iwm': 'IWM', 'qqq': 'QQQ',
}


def display_ticker(a):
    return a.get('ticker') or TICKER.get(a['key'], a['key'].upper())


# What each Yahoo symbol actually is, in plain words, and the familiar ETF
# it moves with - shown under the symbol in the price strip.
INSTRUMENT_NOTE = {
    'ES=F': 'E-mini S&P 500 futures · tracks SPY',
    'NQ=F': 'E-mini Nasdaq-100 futures · tracks QQQ',
    'RTY=F': 'E-mini Russell 2000 futures · tracks IWM',
    'ZN=F': '10-Yr T-Note futures · inverse of 10Y yield',
    'GC=F': 'Gold futures (COMEX) · tracks GLD',
    'DX-Y.NYB': 'US Dollar Index (ICE) · tracks UUP',
    '^GSPC': 'S&P 500 index · tracks SPY',
    'TLT': '20+ Year Treasury bond ETF',
    'IWM': 'Russell 2000 ETF',
    'QQQ': 'Nasdaq-100 ETF',
}


def instrument_note(a):
    """Plain-words name for the asset's symbol, or '' for an unknown one."""
    return INSTRUMENT_NOTE.get(display_ticker(a), '')
STRETCH_MIN, STRETCH_MAX = -6, 6
E = html.escape


def fmt_price(v):
    return f"{v:,.2f}"


def fmt_pct(v):
    return f"{v * 100:+.2f}%"


def call_chip(call, confidence):
    role, hexval, arrow = CALL_STATUS.get(call, ('flat', '#898781', '▬'))
    return (f'<span class="chip" style="--dot:{hexval}">'
            f'<span class="chip-arrow">{arrow}</span>'
            f'<span class="chip-label">{E(call)}</span>'
            f'<span class="chip-conf">{E(confidence)}</span></span>')


def note_stamp(stamp):
    """Small 'when was this written' line under a note. stamp is a
    NoteStamp-style dict: {'written': 'Thu Sep 24, 8:30 PM ET', 'iso': ...,
    'basis': 'Thu Sep 24'} (see board_stamp)."""
    if not stamp:
        return ''
    return (f'<span class="note-stamp" title="{E(stamp.get("iso", ""))}">'
            f'written {E(stamp["written"])} · data through {E(stamp["basis"])} close</span>')


def vote_row(v, category=None, stamp=None, mechanical=False, provisional=False):
    side = v[0]
    reason = v[1]
    mark = v[2] if len(v) > 2 else None
    role, hexval = VOTE_MARK.get(side, ('flat', '#898787'))
    mark_html = ''
    if mark is not None:
        word = "correct" if mark else "wrong"
        if provisional:
            mark_html = (f'<span class="vote-mark provisional {"hit" if mark else "miss"}" '
                         f'title="provisional - graded on an intraday print; final after the session closes">'
                         f'{word} so far</span>')
        else:
            mark_html = f'<span class="vote-mark {"hit" if mark else "miss"}">{word}</span>'
    meta = ''
    if category or stamp:
        when = ''
        if stamp:
            verb = 'computed' if mechanical else 'written'
            when = f' · <span title="{verb} {E(stamp["written"])}">{E(stamp["short"])}</span>'
        meta = f'<span class="vote-meta">{E(category or "")}{when}</span>'
    return (f'<li class="vote" style="--dot:{hexval}">'
            f'<span class="dot" aria-hidden="true"></span>'
            f'<span class="vote-body">{meta}<span class="vote-text">{E(reason)}</span></span>{mark_html}</li>')


STRUCTURE_TONE = {
    'uptrend': '#0ca30c', 'downtrend': '#d03b3b', 'choppy': '#898781',
}
STRUCTURE_ARROW = {'uptrend': '▲', 'downtrend': '▼', 'choppy': '↔'}


def structure_badge(sig, timeframe_label, prefix='', title=''):
    """sig is a mtl.structure.structure_signal() dict, or None if this
    document predates the structure field (older published documents).
    prefix/title label the latest-read variant ('now') apart from the
    board's own read."""
    if not sig or sig.get('state') is None:
        note = (sig or {}).get('note') or 'not enough bars yet'
        return (f'<span class="struct-badge muted" title="{E(note)}">'
                f'{E(prefix)}{E(timeframe_label)} structure: n/a</span>')
    hexval = STRUCTURE_TONE.get(sig['state'], '#898781')
    arrow = STRUCTURE_ARROW.get(sig['state'], '↔')
    brk = ' · break' if sig.get('lastBreak') else ''
    title_attr = f' title="{E(title)}"' if title else ''
    return (f'<span class="struct-badge" style="--dot:{hexval}"{title_attr}>'
            f'<span class="dot" aria-hidden="true"></span>'
            f'{E(prefix)}{E(timeframe_label)}: {arrow} {E(sig["state"])}{brk}</span>')


def live_read_for(key, live):
    """This asset's latest read from live.json, or None (no snapshot, an
    older live.json without reads, or that asset's read failed)."""
    return ((live or {}).get('reads') or {}).get(key)


def live_stamp(live):
    dt = _parse_utc((live or {}).get('fetchedAt'))
    return fmt_et(dt) if dt else None


def latest_read_html(a, live):
    """The asset's trend numbers recomputed through the latest bar on every
    refresh run - next to, never replacing, the board's frozen notes."""
    read = live_read_for(a['key'], live)
    note = latest_note(read)
    if not note:
        return ''
    when = live_stamp(live)
    when_html = (f'<span class="note-stamp">computed {E(when)} · through the latest bar'
                 f' · unscored, not the call basis</span>') if when else ''
    return (f'<p class="latest-read"><span class="latest-label">Latest read</span>'
            f'{E(note)}{when_html}</p>')


def horizon_block(a, h, stamp=None, live=None):
    cats = a.get('categories') or []
    votes_html = "".join(
        vote_row(v, cats[i] if i < len(cats) else None, stamp,
                 mechanical=(i < len(cats) and cats[i] == STRUCTURE_CATEGORY),
                 provisional=bool(h.get('provisional')))
        for i, v in enumerate(h['votes']))
    reversion = ""
    if h.get('reversionFlag'):
        reversion = f'<p class="reversion">⚠ overlay applied — {E(h["reversionNote"])}{note_stamp(stamp)}</p>'
    elif h.get('reversionNote'):
        reversion = f'<p class="reversion muted">{E(h["reversionNote"])}{note_stamp(stamp)}</p>'

    votes_when = ''
    if stamp:
        votes_when = (f' <span class="votes-when">· written {E(stamp["written"])}'
                      f' · data through {E(stamp["basis"])} close</span>')

    structure = a.get('structure') or {}
    field, tf = ('hourly', '1H') if h['h'] == 1 else ('weekly', 'Weekly')
    struct_html = structure_badge(structure.get(field), tf)
    read = live_read_for(a['key'], live)
    if read:
        when = live_stamp(live)
        struct_html += structure_badge(
            read.get(field), tf, prefix='now ',
            title=f'latest read{" as of " + when if when else ""} - unscored, not the call basis')

    return f'''
    <div class="horizon">
      <div class="horizon-head">
        <span class="horizon-h">{h['h']}D</span>
        <span class="horizon-maturity">matures {E(h['maturity'])}</span>
      </div>
      {call_chip(h['call'], h['confidence'])}
      <div class="horizon-stats">
        <span>{h['bull']} bull / {h['bear']} bear / {h['neutral']} neu · margin {h['margin']}</span>
        <span>flat zone {fmt_price(h['flatLo'])}–{fmt_price(h['flatHi'])}</span>
      </div>
      <div class="struct-row">{struct_html}</div>
      {reversion}
      <details class="votes">
        <summary>{len(h['votes'])} votes{votes_when}</summary>
        <ul>{votes_html}</ul>
      </details>
    </div>'''


CATALYST_DOT = {'Bullish': '#0ca30c', 'Bearish': '#d03b3b', 'Mixed': '#eda100', 'Neutral': '#898781'}


def catalyst_item(c):
    hexval = CATALYST_DOT.get(c.get('direction'), '#898781')
    impact = c.get('impact', '')
    when = ''
    if c.get('date'):
        try:
            when = datetime.fromisoformat(c['date']).strftime('%a %b %-d')
        except ValueError:
            when = c['date']
        if c.get('time'):
            when += f", {c['time']}"
        when = f' · {E(when)}'
    return (f'<li class="catalyst" style="--dot:{hexval}">'
            f'<span class="dot" aria-hidden="true"></span>'
            f'<span class="catalyst-body">'
            f'<span class="catalyst-meta">{E(c.get("category", ""))} · {E(impact)} impact{when}</span>'
            f'<span class="catalyst-event">{E(c.get("event", ""))}</span>'
            f'</span></li>')


def stretch_gauge(score, label):
    tone = STRETCH_TONE.get(label, '#898781')
    clamped = max(STRETCH_MIN, min(STRETCH_MAX, score))
    pct = (clamped - STRETCH_MIN) / (STRETCH_MAX - STRETCH_MIN) * 100
    return f'''
        <div class="gauge" style="--tone:{tone}" role="img"
             aria-label="stretch score {score}, {E(label)}">
          <div class="gauge-track">
            <span class="gauge-mid"></span>
            <span class="gauge-marker" style="left:{pct:.1f}%"></span>
          </div>
          <div class="gauge-foot">
            <span class="gauge-score">{score:+d}</span>
            <span class="gauge-label">{E(label)}</span>
          </div>
        </div>'''


def since_board_block(items, board_date):
    """News logged after the board's session - it never fed these calls
    (the blindness rule), but it's what has moved since, so show it apart."""
    if not items:
        return ''
    basis = datetime.fromisoformat(board_date).strftime('%a %b %-d')
    lis = "".join(catalyst_item(c) for c in items)
    return f'''
      <details class="catalysts since-board" open>
        <summary>since the board ({len(items)}) · news after {E(basis)} - not in these calls</summary>
        <ul>{lis}</ul>
      </details>'''


CANDLE_UP, CANDLE_DOWN = '#0ca30c', '#d03b3b'  # the page's bull/bear colours


def _nice_step(span, target=4):
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def _et(ts):
    try:
        return datetime.fromisoformat(ts).astimezone(ET)
    except (TypeError, ValueError):
        return None


SESSION_ROLL_ET = 9  # a chart "day" starts at 9:00 AM New York time


CHART_INSET_L, CHART_INSET_R = 0.6, 2.4  # % of plot width kept clear of candles


def session_days(bars):
    """[(first_index, last_index, 'Mon 28'), ...] grouping candles into
    9 AM-to-9 AM ET days. Label = the weekday the day starts on.

    A new day only ever starts at a weekday's first candle from 9 AM on,
    so every band begins at the 9 AM open of trading: overnight hours
    belong to the day that started the previous morning, and hours with no
    weekday daytime of their own - the Sunday-evening reopen, a holiday
    like Labor Day - join the band before them instead of starting a short
    or oddly-timed one."""
    out = []
    for i, b in enumerate(bars):
        dt = _et(b[0])
        if dt is None:
            continue
        day = (dt - timedelta(hours=SESSION_ROLL_ET)).date()
        starts_day = dt.weekday() < 5 and dt.hour >= SESSION_ROLL_ET and dt.date() == day
        if out and (out[-1][3] == day or not starts_day):
            out[-1][1] = i
        else:
            if day.weekday() >= 5:  # chart opens mid-weekend: that's Friday's day
                day -= timedelta(days=day.weekday() - 4)
            out.append([i, i, day.strftime('%a %-d'), day])
    return [(i0, i1, lab) for i0, i1, lab, _ in out]


def start_at_session_open(bars):
    """Drop the partial day at the far left so the chart begins at a 9 AM
    ET candle, the start of its first full 9am-9am day band. The window is
    a fixed number of hourly candles counted back from now, so otherwise
    its first candle lands at whatever hour that count reaches (4 AM, 5 AM
    ...). Returns the bars unchanged if there's no second day to start at."""
    days = session_days(bars)
    first = _et(bars[0][0]) if bars else None
    if len(days) > 1 and not (first and first.hour == SESSION_ROLL_ET and first.weekday() < 5):
        return bars[days[1][0]:]
    return bars


def hourly_chart_html(a, live, compact=False):
    """The last ~100 hourly candles for this asset's instrument (from the
    refresh run's live.json read), with the board's 1D flat zone shaded so
    the price can be read against the call. Display only - never the call
    basis. The plot is an SVG stretched to the card width; price and time
    labels are HTML so they stay legible at any width. compact=True is the
    price-strip tile version: no axis gutters, a short caption."""
    read = live_read_for(a['key'], live)
    bars = start_at_session_open((read or {}).get('bars') or [])
    if len(bars) < 2:
        return ''
    h1 = next((h for h in a['horizons'] if h['h'] == 1), None)
    lows, highs = [b[3] for b in bars], [b[2] for b in bars]
    lo, hi = min(lows), max(highs)
    if h1:
        lo, hi = min(lo, h1['flatLo']), max(hi, h1['flatHi'])
    pad = (hi - lo) * 0.06 or abs(hi) * 0.001 or 1
    lo, hi = lo - pad, hi + pad
    n = len(bars)
    y = lambda p: (hi - p) / (hi - lo) * 100
    # candles sit inset from the plot's borders (X0 left, 100 - X0 - SPAN
    # right) so the newest ones never disappear into the right edge
    x0, span = CHART_INSET_L, 100 - CHART_INSET_L - CHART_INSET_R
    slot = span / n
    body_w = slot * 0.64

    # Session days run 9:00 AM ET to 9:00 AM ET: every other one gets a
    # lighter band behind the candles so a day's candles read as a group.
    parts, day_labels = [], []
    for k, (i0, i1, label) in enumerate(session_days(bars)):
        if k % 2 == 1:
            parts.append(f'<rect class="hc-day" x="{x0 + i0 * slot:.3f}" width="{(i1 - i0 + 1) * slot:.3f}" y="0" height="100"/>')
        if k > 0:  # a line at every 9 AM day start, shaded band or not
            xx = x0 + i0 * slot
            parts.append(f'<line class="hc-day-start" x1="{xx:.3f}" x2="{xx:.3f}" y1="0" y2="100"/>')
        if (i1 - i0 + 1) * slot >= 1.5:  # Friday's short day (to the 5 PM close) still fits one letter
            # weekday initial, centred in its band - full names collide at 400 candles
            day_labels.append(f'<span class="hc-day-label" style="left:{x0 + (i0 + i1 + 1) / 2 * slot:.2f}%" '
                              f'title="{E(label)}">{E(label[0])}</span>')
    step = _nice_step(hi - lo)
    tick = math.ceil(lo / step) * step
    ylabels = []
    while tick <= hi:
        yy = y(tick)
        parts.append(f'<line class="hc-grid" x1="0" x2="100" y1="{yy:.3f}" y2="{yy:.3f}"/>')
        ylabels.append(f'<span style="top:{yy:.2f}%">{fmt_price(tick)}</span>')
        tick += step
    if h1:
        top, bot = y(h1['flatHi']), y(h1['flatLo'])
        parts.append(f'<rect class="hc-zone" x="0" width="100" y="{top:.3f}" height="{max(bot - top, 0.2):.3f}"/>')
        for yy in (top, bot):
            parts.append(f'<line class="hc-zone-edge" x1="0" x2="100" y1="{yy:.3f}" y2="{yy:.3f}"/>')
    for i, (ts, o, h, l, c) in enumerate(bars):
        cx = x0 + (i + 0.5) * slot
        col = CANDLE_UP if c >= o else CANDLE_DOWN
        top, bot = y(max(o, c)), y(min(o, c))
        parts.append(f'<line x1="{cx:.3f}" x2="{cx:.3f}" y1="{y(h):.3f}" y2="{y(l):.3f}" stroke="{col}" class="hc-wick"/>')
        parts.append(f'<rect x="{cx - body_w / 2:.3f}" width="{body_w:.3f}" y="{top:.3f}" '
                     f'height="{max(bot - top, 0.35):.3f}" fill="{col}"/>')
    last = bars[-1][4]
    parts.append(f'<line class="hc-last" x1="0" x2="100" y1="{y(last):.3f}" y2="{y(last):.3f}"/>')

    # a time label at the first candle of each New York day, thinned to fit
    xlabels, prev = [], None
    for i, b in enumerate(bars):
        dt = _et(b[0])
        if dt and dt.date() != prev:
            prev = dt.date()
            xlabels.append((i, dt.strftime('%a %-d')))
    # when two labels would sit within 12% of the width, keep the later one
    # (e.g. Sunday's few evening candles right before Monday's session)
    kept = []
    for i, t in xlabels:
        if kept and (i - kept[-1][0]) * slot < 12:
            kept[-1] = (i, t)
        else:
            kept.append((i, t))
    xl_html = "".join(f'<span style="left:{x0 + (i + 0.5) * slot:.2f}%">{E(t)}</span>' for i, t in kept)

    tip_rows = [[(_et(b[0]).strftime('%a %b %-d, %-I:%M %p ET') if _et(b[0]) else b[0]),
                 fmt_price(b[1]), fmt_price(b[2]), fmt_price(b[3]), fmt_price(b[4]),
                 fmt_pct(b[4] / b[1] - 1) if b[1] else ''] for b in bars]
    if compact:
        zone_c = (f' · shaded: 1D flat zone') if h1 else ''
        return f"""
        <figure class="hchart compact" data-x0="{x0}" data-span="{span}" data-bars='{E(json.dumps(tip_rows))}'>
          <div class="hc-plot">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img"
                 aria-label="Hourly candles for {E(read['ticker'])}, last {n}, latest {fmt_price(last)}">{''.join(parts)}</svg>
            {''.join(day_labels)}
            <div class="hc-cross" hidden></div>
            <div class="hc-tip" hidden></div>
          </div>
          <figcaption>1H · {n} candles · last {fmt_price(last)} (dotted){zone_c} · bands: 9am–9am ET days</figcaption>
        </figure>"""
    zone = (f' · shaded: board\'s 1D flat zone {fmt_price(h1["flatLo"])}–{fmt_price(h1["flatHi"])}'
            f' (call: {E(h1["call"])})') if h1 else ''
    when = live_stamp(live)
    return f"""
      <figure class="hchart" data-x0="{x0}" data-span="{span}" data-bars='{E(json.dumps(tip_rows))}'>
        <div class="hc-plot">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img"
               aria-label="Hourly candles for {E(read['ticker'])}, last {n}, latest {fmt_price(last)}">{''.join(parts)}</svg>
          <div class="hc-cross" hidden></div>
          <div class="hc-tip" hidden></div>
          <span class="hc-last-tag" style="top:{y(last):.2f}%">{fmt_price(last)}</span>
        </div>
        <div class="hc-y">{''.join(ylabels)}</div>
        <div class="hc-x">{xl_html}</div>
        <figcaption>Hourly {E(read['ticker'])} · last {n} candles{zone}{' · as of ' + E(when) if when else ''} · not the call basis</figcaption>
      </figure>"""


def is_call(h):
    """False for a no-call abstention: there's nothing to grade, so it's
    left out of the cards, the price strip and the call log."""
    return h['call'] != 'no-call'


def asset_card(a, catalysts, stamp=None, live=None, since=None, board_date=None):
    st = a['stretch']
    horizons_html = "".join(horizon_block(a, h, stamp, live) for h in a['horizons'] if is_call(h))
    drivers_html = "".join(f'<li>{E(d)}</li>' for d in st.get('drivers', []))
    drivers_block = (f'<ul class="drivers">{drivers_html}</ul>{note_stamp(stamp)}'
                     if drivers_html else '')

    catalysts_block = ''
    if catalysts:
        items = "".join(catalyst_item(c) for c in catalysts)
        catalysts_block = f'''
      <details class="catalysts" open>
        <summary>what's been moving this ({len(catalysts)})</summary>
        <ul>{items}</ul>
      </details>'''

    return f'''
    <section class="asset">
      <header class="asset-head">
        <div>
          <span class="asset-ticker">{E(display_ticker(a))}</span>
          <h2>{E(a['name'])}</h2>
          <p class="instrument">{E(a['instrument'])} · close {fmt_price(a['close'])}</p>
        </div>
        {stretch_gauge(st['score'], st['label'])}
      </header>
      <p class="driver-note">{E(a['driverNote'])}{note_stamp(stamp)}</p>
      {latest_read_html(a, live)}
      {f'<details class="stretch-drivers"><summary>why this stretch score</summary>{drivers_block}</details>' if drivers_block else ''}
      {catalysts_block}
      {since_board_block(since, board_date) if board_date else ''}
      <div class="horizons">{horizons_html}</div>
    </section>'''


def live_price_html(key, live):
    """Small secondary line showing what the instrument is trading at right
    now, from documents/live.json - a pure display overlay, never the basis
    a call was actually made against (that's always a['close'], untouched).
    None if no live snapshot exists or this key isn't in it."""
    if not live:
        return ''
    row = (live.get('prices') or {}).get(key)
    if not row or row.get('price') is None:
        return ''
    return (f'<span class="tape-live" title="live snapshot, not the call basis">'
            f'live {E(row["ticker"])} {fmt_price(row["price"])}</span>')


def ticker_strip(doc, live=None):
    items = []
    for a in doc['assets']:
        by_h = {h['h']: h for h in a['horizons']}
        h1 = by_h[1]
        role, hexval, arrow = CALL_STATUS.get(h1['call'], ('flat', '#898781', '▬'))
        horizons_html = "".join(tape_horizon_badge(by_h[h]) for h in (1, 5, 10) if is_call(by_h[h]))
        items.append(f'''
      <div class="tape-item" style="--dot:{hexval}">
        <div class="tape-head">
          <span class="tape-ticker">{E(display_ticker(a))}</span>
          <span class="tape-price">{fmt_price(a['close'])}</span>
        </div>
        {f'<span class="tape-name">{E(instrument_note(a))}</span>' if instrument_note(a) else ''}
        {live_price_html(a['key'], live)}
        <div class="tape-horizons">{horizons_html}</div>
        {live_tilt_row_html(a, live)}
        {hourly_chart_html(a, live, compact=True)}
      </div>''')
    return "".join(items)


def tape_horizon_badge(h):
    role, hexval, arrow = CALL_STATUS.get(h['call'], ('flat', '#898781', '▬'))
    return (f'<span class="tape-badge" style="--dot:{hexval}">'
            f'<span class="tape-badge-h">{h["h"]}D</span>'
            f'<span class="tape-badge-arrow">{arrow}</span></span>')


def live_tilt_badge(h, live_price):
    """Unscored: where the live price sits against this horizon's own
    flat-zone bounds, right now - never written back to the horizon,
    never graded, just refreshed with whatever the last run's live.json
    snapshot (scheduled or workflow_dispatch) happened to see."""
    tilt = live_tilt(live_price, h['flatLo'], h['flatHi'])
    if tilt is None:
        return ''
    role, hexval, arrow = CALL_STATUS.get(tilt, ('flat', '#898781', '▬'))
    return (f'<span class="tape-tilt-badge" style="--dot:{hexval}" '
            f'title="unscored - where the live price sits vs this horizon\'s flat zone right now">'
            f'<span class="tape-badge-h">{h["h"]}D</span>'
            f'<span class="tape-badge-arrow">{arrow}</span></span>')


def live_tilt_row_html(a, live):
    if not live:
        return ''
    row = (live.get('prices') or {}).get(a['key'])
    if not row or row.get('price') is None:
        return ''
    by_h = {h['h']: h for h in a['horizons']}
    badges = "".join(live_tilt_badge(by_h[h], row['price']) for h in (1, 5, 10))
    if not badges:
        return ''
    return f'<div class="tape-tilt-row"><span class="tape-tilt-label">live tilt</span>{badges}</div>'


def stat_tiles(doc):
    calls = [h['call'] for a in doc['assets'] for h in a['horizons']]
    n_bull, n_bear = calls.count('bullish'), calls.count('bearish')
    n_flat, n_nocall = calls.count('flat'), calls.count('no-call')

    extreme = max(doc['assets'], key=lambda a: abs(a['stretch']['score']))
    ex_tone = STRETCH_TONE.get(extreme['stretch']['label'], '#898781')

    def tile(label, value, sub='', tone=None):
        style = f' style="--tone:{tone}"' if tone else ''
        cls = 'stat-tile toned' if tone else 'stat-tile'
        return (f'<div class="{cls}"{style}><span class="stat-label">{E(label)}</span>'
                f'<span class="stat-value">{value}</span>'
                f'{f"<span class=stat-sub>{E(sub)}</span>" if sub else ""}</div>')

    return (
        tile('Bullish calls', n_bull, f'of 18') +
        tile('Bearish calls', n_bear, f'of 18') +
        tile('Flat / no-call', n_flat + n_nocall, f'of 18') +
        tile('Overlay reweighted', doc['overlay']['cellsChanged'], 'of 18 cells') +
        tile('Most stretched', f"{display_ticker(extreme)} {extreme['stretch']['score']:+d}",
             extreme['stretch']['label'], tone=ex_tone)
    )


def summary_chips(doc):
    calls = [h['call'] for a in doc['assets'] for h in a['horizons']]
    counts = {k: calls.count(k) for k in ('bullish', 'bearish', 'flat', 'no-call')}
    parts = []
    for call, n in counts.items():
        if n:
            role, hexval, arrow = CALL_STATUS[call]
            parts.append(f'<span class="summary-chip" style="--dot:{hexval}">'
                        f'<span class="dot" aria-hidden="true"></span>{n} {E(call)}</span>')
    return "".join(parts)


PAGE = '''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<!-- GitHub Pages serves this file as-is: without the viewport tag phones lay
     it out at desktop width (~980px) and shrink it, instead of using the
     narrow-screen layout the CSS below defines. -->
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Tape Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Space+Grotesk:wght@500;600&display=swap" rel="stylesheet">
<style>
/* Dark is the default look, unconditionally - not keyed off OS preference
   or the viewer's own Claude account theme, since [data-mtl-theme] below
   is this page's own attribute, never the host's shared [data-theme]. Only
   this page's own toggle button can switch it to light. */
:root {{
  --bg: #0d0d0d; --surface: #17181a; --ink: #ffffff; --ink-2: #c3c2b7;
  --muted: #8b8a85; --hairline: #2c2c2a; --accent: #3987e5; --gold: #d9b46a;
  --masthead-bg: #17181a; --masthead-ink: #ffffff; --masthead-ink-2: #a9adba;
  color-scheme: dark;
}}
/* A page-private attribute, not the host's shared [data-theme] - so this
   page's default can't be overridden by the viewer's own Claude account
   theme setting. Only this page's own toggle ever sets it. */
:root[data-mtl-theme="light"] {{
  --bg: #f4f3ef; --surface: #fdfdfc; --ink: #0b0c0e; --ink-2: #52514e;
  --muted: #898781; --hairline: #e1e0d9; --accent: #2a78d6; --gold: #93701f;
  --masthead-bg: #10141c; --masthead-ink: #f4f3ef; --masthead-ink-2: #a9adba;
  color-scheme: light;
}}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--ink); margin: 0;
  font: 15px/1.55 "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.wrap {{ max-width: 920px; margin-inline: auto; padding-inline: 16px; padding-block: 0 64px; }}
h1, h2 {{ font-family: "Fraunces", Georgia, serif; text-wrap: balance; margin: 0; }}
code {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}

/* masthead */
.masthead {{ background: var(--masthead-bg); color: var(--masthead-ink); }}
.masthead-inner {{
  max-width: 920px; margin-inline: auto; padding: 28px 16px 22px;
  border-bottom: 2px solid var(--gold);
}}
.eyebrow {{
  font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--gold); font-weight: 600; margin: 0 0 6px;
}}
.masthead-top {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; justify-content: space-between; }}
.masthead-right {{ display: flex; align-items: center; gap: 10px; }}
h1 {{ font-size: 2.1rem; font-weight: 600; color: var(--masthead-ink); }}
.date {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; color: var(--masthead-ink-2); font-size: 0.95rem; }}
.subtitle {{ color: var(--masthead-ink-2); margin: 8px 0 0; font-size: 0.92rem; }}
.updated {{
  color: var(--masthead-ink-2); margin: 6px 0 0; font-size: 0.75rem;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; opacity: 0.85;
}}

/* freshness panel: when each part of the page was last updated */
.refresh-cta {{ margin: 28px 0 8px; display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; font-size: 0.8rem; color: var(--muted); }}
.refresh-btn {{ display: inline-block; padding: 9px 16px; border-radius: 999px; border: 1px solid var(--accent);
  color: var(--accent); font-weight: 600; text-decoration: none; white-space: nowrap; }}
.refresh-btn:hover {{ background: color-mix(in srgb, var(--accent) 14%, transparent); }}
.submit-news {{ margin: 10px 0 0; font-size: 0.8rem; color: var(--masthead-ink-2); }}
.submit-news a {{ font-weight: 600; margin-right: 8px; }}
.fresh {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px;
  margin-top: 14px;
}}
.fresh-item {{
  border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; padding: 8px 10px;
  display: grid; grid-template-columns: auto 1fr; column-gap: 8px; align-items: baseline;
}}
.fresh-dot {{ width: 8px; height: 8px; border-radius: 999px; background: var(--masthead-ink-2); align-self: center; }}
.fresh-item[data-state="fresh"] .fresh-dot {{ background: #5fb87a; }}
.fresh-item[data-state="aging"] .fresh-dot {{ background: #d9b46a; }}
.fresh-item[data-state="stale"] .fresh-dot {{ background: #e5705f; }}
.fresh-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--masthead-ink-2); }}
.fresh-value {{
  grid-column: 2; color: var(--masthead-ink); font-size: 0.82rem;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums;
}}
.fresh-note {{ grid-column: 2; color: var(--masthead-ink-2); font-size: 0.72rem; }}
.fresh-age {{ font-weight: 600; }}
.fresh-item[data-state="stale"] .fresh-age {{ color: #e5705f; }}
.fresh-item[data-state="aging"] .fresh-age {{ color: #d9b46a; }}

/* ticker strip */
.tape {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(min(250px, 100%), 1fr)); gap: 1px;
  margin-top: 20px; background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.12); border-radius: 10px; overflow: hidden;
}}
.tape-item {{
  min-width: 0; display: flex; flex-direction: column; gap: 8px; background: var(--masthead-bg);
  padding: 10px 14px;
  border-top: 3px solid var(--dot);
}}
.tape-head {{ display: flex; align-items: baseline; gap: 8px; }}
.tape-ticker {{ font-family: ui-monospace, monospace; font-weight: 600; font-size: 0.8rem; letter-spacing: 0.04em; color: var(--masthead-ink-2); }}
.tape-price {{ font-family: ui-monospace, monospace; font-size: 1.05rem; font-variant-numeric: tabular-nums; color: var(--masthead-ink); }}
.tape-name {{ font-size: 0.7rem; color: var(--masthead-ink-2); margin-top: -4px; }}
.tape-live {{ font-family: ui-monospace, monospace; font-size: 0.68rem; font-variant-numeric: tabular-nums; color: var(--masthead-ink-2); opacity: 0.85; }}
.tape-horizons {{ display: flex; gap: 6px; }}
.tape-badge {{
  display: inline-flex; align-items: center; gap: 4px; font-size: 0.72rem;
  padding: 2px 7px; border-radius: 6px; background: color-mix(in srgb, var(--dot) 16%, transparent);
  color: var(--dot); font-weight: 600;
}}
.tape-badge-h {{ font-family: ui-monospace, monospace; letter-spacing: 0.02em; }}
.tape-tilt-row {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: -2px; }}
.tape-tilt-label {{ font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--masthead-ink-2); opacity: 0.75; }}
.tape-tilt-badge {{
  display: inline-flex; align-items: center; gap: 4px; font-size: 0.7rem;
  padding: 1px 6px; border-radius: 6px; border: 1px dashed var(--dot);
  background: transparent; color: var(--dot); font-weight: 600; opacity: 0.9;
}}

/* stat tiles */
.stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--hairline);
  border: 1px solid var(--hairline); border-radius: 12px; overflow: hidden; margin-top: -1px; }}
@media (max-width: 720px) {{ .stats {{ grid-template-columns: repeat(2, 1fr); }} .stats > :last-child:nth-child(odd) {{ grid-column: 1 / -1; }} }}
.stat-tile {{ background: var(--surface); padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }}
.stat-tile.toned {{ border-top: 3px solid var(--tone); }}
.stat-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
.stat-value {{ font-family: ui-monospace, monospace; font-size: 1.4rem; font-weight: 600; font-variant-numeric: tabular-nums; }}
.stat-sub {{ font-size: 0.72rem; color: var(--ink-2); text-transform: capitalize; }}

.section-label {{
  font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted);
  font-weight: 600; margin: 36px 0 12px;
}}

/* asset cards */
.hchart {{ margin: 14px 0 0; display: grid; grid-template-columns: 1fr auto; grid-template-rows: auto auto auto; column-gap: 8px; }}
.hc-plot {{ position: relative; height: 230px; border: 1px solid var(--hairline); border-radius: 8px; overflow: hidden; cursor: crosshair; }}
.hc-plot svg {{ display: block; width: 100%; height: 100%; }}
.hc-grid {{ stroke: var(--hairline); stroke-width: 1; vector-effect: non-scaling-stroke; }}
.hc-zone {{ fill: var(--accent); opacity: 0.10; }}
.hc-zone-edge {{ stroke: var(--accent); stroke-width: 1; stroke-dasharray: 4 3; opacity: 0.6; vector-effect: non-scaling-stroke; }}
.hc-wick {{ stroke-width: 1; vector-effect: non-scaling-stroke; }}
.hc-last {{ stroke: var(--ink-2); stroke-width: 1; stroke-dasharray: 2 3; vector-effect: non-scaling-stroke; }}
.hc-last-tag {{ position: absolute; right: 4px; transform: translateY(-50%); font: 600 0.68rem ui-monospace, monospace;
  background: var(--surface); color: var(--ink); border: 1px solid var(--hairline); border-radius: 4px; padding: 0 4px; }}
.hc-y {{ position: relative; min-width: 62px; font: 0.68rem ui-monospace, monospace; color: var(--muted); font-variant-numeric: tabular-nums; }}
.hc-y span {{ position: absolute; left: 0; transform: translateY(-50%); white-space: nowrap; }}
.hc-x {{ position: relative; height: 18px; font-size: 0.68rem; color: var(--muted); }}
.hc-x span {{ position: absolute; top: 3px; transform: translateX(-50%); white-space: nowrap; }}
.hchart figcaption {{ grid-column: 1 / -1; font-size: 0.72rem; color: var(--muted); margin-top: 2px; }}
.hc-cross {{ position: absolute; top: 0; bottom: 0; width: 1px; background: var(--ink-2); opacity: 0.5; pointer-events: none; }}
.hc-tip {{ position: absolute; top: 6px; pointer-events: none; background: var(--surface); color: var(--ink);
  border: 1px solid var(--hairline); border-radius: 6px; padding: 5px 8px; font: 0.72rem ui-monospace, monospace;
  white-space: nowrap; box-shadow: 0 4px 12px rgba(0,0,0,0.18); z-index: 2; }}
.hc-tip b {{ font-family: inherit; }}
@media (max-width: 560px) {{ .hc-plot {{ height: 180px; }} }}
.hchart.compact {{ margin: 2px 0 0; grid-template-columns: 1fr; }}
.hc-day {{ fill: #ffffff; opacity: 0.055; }}
.hc-day-start {{ stroke: #ffffff; stroke-width: 1; opacity: 0.22; stroke-dasharray: 2 2; vector-effect: non-scaling-stroke; }}
.hc-day-label {{ position: absolute; top: 2px; transform: translateX(-50%); font: 0.56rem ui-monospace, monospace;
  color: var(--masthead-ink-2); opacity: 0.75; pointer-events: none; white-space: nowrap; }}
.hchart.compact .hc-plot {{ height: 110px; border-color: rgba(255,255,255,0.12); }}
.hchart.compact figcaption {{ font-size: 0.62rem; color: var(--masthead-ink-2); opacity: 0.8; }}
.hchart.compact .hc-tip {{ font-size: 0.62rem; padding: 3px 6px; }}
@media (max-width: 560px) {{ .hchart.compact .hc-plot {{ height: 140px; }} }}
.asset {{
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px;
  padding: 22px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(11,12,14,0.04), 0 8px 20px -12px rgba(11,12,14,0.12);
}}
.asset-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap; }}
.asset-ticker {{
  display: inline-block; font-family: ui-monospace, monospace; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.06em; color: var(--gold); background: color-mix(in srgb, var(--gold) 14%, transparent);
  padding: 2px 7px; border-radius: 5px; margin-bottom: 6px;
}}
.instrument {{ margin: 3px 0 0; color: var(--ink-2); font-size: 0.88rem; font-variant-numeric: tabular-nums; }}

/* stretch gauge */
.gauge {{ min-width: 190px; }}
.gauge-track {{ position: relative; height: 6px; border-radius: 999px; background: var(--hairline); margin-bottom: 8px; }}
.gauge-mid {{ position: absolute; left: 50%; top: -3px; width: 1px; height: 12px; background: var(--muted); }}
.gauge-marker {{
  position: absolute; top: 50%; width: 14px; height: 14px; border-radius: 50%;
  background: var(--tone); border: 2px solid var(--surface); box-shadow: 0 0 0 1px var(--tone);
  transform: translate(-50%, -50%);
}}
.gauge-foot {{ display: flex; align-items: baseline; gap: 8px; justify-content: flex-end; }}
.gauge-score {{ font-family: ui-monospace, monospace; font-size: 1.15rem; font-weight: 600; color: var(--tone); }}
.gauge-label {{ color: var(--ink-2); font-size: 0.85rem; }}

.driver-note {{ color: var(--ink-2); font-size: 0.92rem; margin: 14px 0 0; }}
.stretch-drivers {{ margin-top: 8px; }}
.stretch-drivers summary {{ cursor: pointer; color: var(--accent); font-size: 0.85rem; }}
.stretch-drivers ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--ink-2); font-size: 0.85rem; }}
.horizons {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }}
@media (max-width: 620px) {{ .horizons {{ grid-template-columns: 1fr; }} }}
.horizon {{ border: 1px solid var(--hairline); border-radius: 10px; padding: 12px; }}
.horizon-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }}
.horizon-h {{ font-weight: 700; font-family: ui-monospace, monospace; letter-spacing: 0.02em; }}
.horizon-maturity {{ font-size: 0.72rem; color: var(--muted); }}
.chip {{
  display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--hairline);
  border-radius: 999px; padding: 4px 10px 4px 8px; font-size: 0.85rem;
}}
.chip-arrow {{ color: var(--dot); font-size: 0.7rem; }}
.chip-label {{ text-transform: capitalize; font-weight: 600; }}
.chip-conf {{ color: var(--muted); font-size: 0.78rem; }}
.struct-row {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
.latest-read {{ color: var(--ink-2); font-size: 0.88rem; margin: 10px 0 0; padding: 8px 10px; border-left: 3px solid var(--muted); background: color-mix(in srgb, var(--muted) 8%, transparent); border-radius: 4px; }}
.latest-label {{ font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.04em; margin-right: 8px; }}
.struct-badge {{
  display: inline-flex; align-items: center; gap: 5px; font-size: 0.74rem;
  color: var(--dot); font-weight: 600; text-transform: capitalize;
}}
.struct-badge.muted {{ color: var(--muted); font-weight: 400; text-transform: none; }}
.struct-badge .dot {{ width: 6px; height: 6px; }}
.horizon-stats {{
  display: flex; flex-direction: column; gap: 2px; margin-top: 10px;
  font-size: 0.78rem; color: var(--ink-2); font-variant-numeric: tabular-nums;
}}
.reversion {{ font-size: 0.78rem; margin: 8px 0 0; color: var(--ink); }}
.reversion.muted {{ color: var(--muted); }}
.votes {{ margin-top: 10px; }}
.votes summary {{ cursor: pointer; color: var(--accent); font-size: 0.82rem; }}
.votes ul {{ list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 7px; }}
.vote {{ display: flex; align-items: flex-start; gap: 7px; font-size: 0.82rem; color: var(--ink-2); }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--dot); flex-shrink: 0; }}
.vote .dot {{ margin-top: 6px; }}
.vote-body {{ flex: 1; display: flex; flex-direction: column; gap: 1px; }}
.vote-meta, .note-stamp {{
  font-size: 0.68rem; color: var(--muted); letter-spacing: 0.02em;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums;
}}
.note-stamp {{ display: block; margin-top: 4px; }}
.votes-when {{ font-size: 0.68rem; color: var(--muted); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}
.vote-mark {{ font-size: 0.7rem; white-space: nowrap; padding: 1px 6px; border-radius: 999px; }}
.vote-mark.hit {{ color: #0ca30c; border: 1px solid #0ca30c; }}
.vote-mark.miss {{ color: #d03b3b; border: 1px solid #d03b3b; }}
.vote-mark.provisional {{ border-style: dashed; opacity: 0.8; }}
.log-prov {{ margin-left: 6px; font-size: 0.7rem; color: var(--muted); border: 1px dashed var(--muted); border-radius: 999px; padding: 0 5px; }}
.catalysts {{ margin-top: 16px; border-top: 1px solid var(--hairline); padding-top: 12px; }}
.catalysts summary {{ cursor: pointer; color: var(--accent); font-size: 0.85rem; }}
.catalysts ul {{ list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }}
.catalyst {{ display: flex; align-items: flex-start; gap: 8px; }}
.catalyst .dot {{ margin-top: 6px; }}
.catalyst-body {{ display: flex; flex-direction: column; gap: 2px; }}
.catalyst-meta {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
.catalyst-event {{ font-size: 0.85rem; color: var(--ink-2); }}
footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--hairline); color: var(--muted); font-size: 0.8rem; }}
footer a {{ color: var(--accent); }}

/* track record */
.record {{
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px;
  padding: 22px; margin-top: 8px;
}}
.record-empty {{ color: var(--ink-2); font-size: 0.9rem; }}
.record-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 20px; margin-bottom: 18px; }}
.record-pct {{ font-family: ui-monospace, monospace; font-size: 2rem; font-weight: 600; }}
.record-pct.good {{ color: #0ca30c; }}
.record-pct.critical {{ color: #d03b3b; }}
.record-pct.flat {{ color: var(--ink-2); }}
.record-n {{ color: var(--muted); font-size: 0.85rem; }}
.record-edge {{ font-size: 0.85rem; color: var(--ink-2); }}
.record-head-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; margin: 0 0 6px; }}
.record-row-real {{ color: var(--muted); font-size: 0.72rem; font-weight: 400; margin-left: 8px; }}
.record-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 18px; }}
@media (max-width: 620px) {{ .record-grid {{ grid-template-columns: 1fr 1fr; }} }}
.record-block h3 {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 0 0 8px; font-family: inherit; font-weight: 600; }}
.record-row {{
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 5px 0; border-bottom: 1px solid var(--hairline); font-size: 0.85rem;
}}
.record-row:last-child {{ border-bottom: none; }}
.record-row-label {{ color: var(--ink-2); }}
.record-row-val {{ font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; font-weight: 600; }}
.record-row-n {{ color: var(--muted); font-size: 0.75rem; font-weight: 400; }}
.record-caveat {{ font-size: 0.78rem; color: var(--muted); border-top: 1px solid var(--hairline); padding-top: 12px; margin-top: 4px; }}

/* call log */
.log-wrap {{ overflow-x: auto; border: 1px solid var(--hairline); border-radius: 14px; }}
table.log {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; background: var(--surface); }}
table.log th {{
  text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--muted); font-weight: 600; padding: 10px 14px; border-bottom: 1px solid var(--hairline);
  white-space: nowrap; position: sticky; top: 0; background: var(--surface);
}}
table.log td {{ padding: 9px 14px; border-bottom: 1px solid var(--hairline); white-space: nowrap; vertical-align: middle; }}
table.log tbody tr:last-child td {{ border-bottom: none; }}
table.log tbody tr:hover {{ background: color-mix(in srgb, var(--accent) 6%, transparent); }}
.log-date, .log-matures {{ font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; color: var(--ink-2); font-size: 0.8rem; }}
.log-price {{ font-family: ui-monospace, monospace; font-variant-numeric: tabular-nums; color: var(--ink-2); font-size: 0.8rem; text-align: right; }}
.log-ticker {{ font-family: ui-monospace, monospace; font-weight: 600; }}
.log-call {{ display: inline-flex; align-items: center; gap: 5px; text-transform: capitalize; font-weight: 500; }}
.log-call .dot {{ width: 7px; height: 7px; }}
.log-conf {{ color: var(--muted); font-size: 0.78rem; }}
.log-pending {{ color: var(--muted); font-size: 0.78rem; }}
.log-noscore {{ color: var(--muted); font-size: 0.78rem; }}
.log-correct {{ color: #0ca30c; font-weight: 600; }}
.log-wrong {{ color: #d03b3b; font-weight: 600; }}
.log-nocall {{ color: var(--gold); font-weight: 600; }}
.log-caption {{ font-size: 0.78rem; color: var(--muted); margin: 10px 2px 0; }}

.scanner-link {{ margin: 14px 0 0; }}
.scanner-link a {{
  display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px;
  border: 1px solid var(--gold); color: var(--masthead-ink); text-decoration: none; font-size: 0.85rem; font-weight: 600;
}}
.scanner-link a:hover {{ background: color-mix(in srgb, var(--gold) 16%, transparent); }}
.scanner-link span {{ color: var(--masthead-ink-2); font-weight: 500; }}

.theme-toggle {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.18);
  background: transparent; color: var(--masthead-ink-2); cursor: pointer; flex-shrink: 0;
}}
.theme-toggle:hover {{ color: var(--gold); border-color: var(--gold); }}
.theme-toggle svg {{ width: 15px; height: 15px; }}
</style>

<div class="masthead">
  <div class="masthead-inner">
    <p class="eyebrow">Daily Briefing</p>
    <div class="masthead-top">
      <h1>Market Tape Ledger</h1>
      <span class="masthead-right">
        <span class="date">{date}</span>
        <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle dark/light theme">
          <svg id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4"></circle>
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>
          </svg>
          <svg id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" hidden>
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"></path>
          </svg>
        </button>
      </span>
    </div>
    <p class="subtitle">6 markets × 3 horizons (1D / 5D / 10D) — 18 calls from a thirteen-category vote model, with a stretch/mean-reversion overlay.</p>
    <p class="scanner-link"><a href="scanner.html">◆ Top 5 Strongest <span>S&amp;P 500 + Nasdaq-100 momentum picks</span> →</a></p>
    {freshness}
    <p class="submit-news"><a href="{submit_url}" target="_blank" rel="noopener">＋ Submit a news event</a>
      <span>adds it to the news log the research reads; the page updates in about a minute</span></p>
    <div class="tape">{tape}</div>
  </div>
</div>

<div class="wrap">
<div class="stats">{stats}</div>

<p class="section-label">The board</p>
{assets}

{growth}
<p class="section-label">Track record</p>
{record}

<p class="section-label">Call log</p>
{log}

<p class="refresh-cta"><a class="refresh-btn" href="{refresh_url}" target="_blank" rel="noopener">↻ Refresh market data</a>
  <span>Opens the refresh job on GitHub - tap <b>Run workflow</b> (signed in as the repo owner). The page updates about two minutes later; it also refreshes itself every hour.</span></p>
<footer>
  Generated by <code>scripts/render_html.py</code> from <code>documents/{date}.json</code> in
  <a href="https://github.com/danreed001-droid/NIBII">danreed001-droid/NIBII</a>.
  Every call here is reproducible: <code>mtl.build.build_document</code> derives it from
  <code>contracts/inputs.{date}.json</code> and <code>contracts/votes.{date}.json</code>, and
  <code>mtl.verify.verify_document</code> recomputes it independently. Unsettled cells show no
  correctness mark until their maturity date passes; marks tagged "so far" are provisional -
  graded on an intraday print, final once that session closes, and not in the track record.
</footer>
</div>

<script>
(function () {{
  // Hourly chart hover: nearest candle's time and O/H/L/C in a tooltip.
  document.querySelectorAll('.hchart').forEach(function (fig) {{
    var rows; try {{ rows = JSON.parse(fig.getAttribute('data-bars')); }} catch (e) {{ return; }}
    var plot = fig.querySelector('.hc-plot'), tip = fig.querySelector('.hc-tip'),
        cross = fig.querySelector('.hc-cross'), n = rows.length,
        x0 = (parseFloat(fig.getAttribute('data-x0')) || 0) / 100,
        span = (parseFloat(fig.getAttribute('data-span')) || 100) / 100;
    function show(clientX) {{
      var r = plot.getBoundingClientRect();
      var plotW = r.width * span, plotL = r.width * x0;
      var i = Math.max(0, Math.min(n - 1, Math.floor((clientX - r.left - plotL) / plotW * n)));
      var x = plotL + (i + 0.5) / n * plotW, row = rows[i];
      cross.style.left = x + 'px'; cross.hidden = false;
      tip.innerHTML = '<b>' + row[0] + '</b><br>O ' + row[1] + '  H ' + row[2] +
        '<br>L ' + row[3] + '  C ' + row[4] + (row[5] ? '  (' + row[5] + ')' : '');
      tip.hidden = false;
      var w = tip.offsetWidth, left = x + 10;
      if (left + w > r.width - 4) left = x - w - 10;
      tip.style.left = Math.max(4, left) + 'px';
    }}
    plot.addEventListener('mousemove', function (e) {{ show(e.clientX); }});
    plot.addEventListener('touchmove', function (e) {{ if (e.touches[0]) show(e.touches[0].clientX); }}, {{ passive: true }});
    plot.addEventListener('mouseleave', function () {{ tip.hidden = true; cross.hidden = true; }});
  }});
}})();
</script>
<script>
(function () {{
  // Freshness panel: turn each stamp's ISO time into "x min ago" and a
  // fresh/aging/stale dot, recomputed every minute against the viewer's clock.
  function ago(ms) {{
    var m = Math.floor(ms / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + ' min ago';
    var h = Math.floor(m / 60);
    if (h < 48) return h + 'h ' + (m % 60) + 'm ago';
    return Math.floor(h / 24) + ' days ago';
  }}
  function tick() {{
    var items = document.querySelectorAll('.fresh-item[data-ts]');
    for (var i = 0; i < items.length; i++) {{
      var el = items[i];
      var t = Date.parse(el.getAttribute('data-ts'));
      if (isNaN(t)) continue;
      var age = Date.now() - t;
      var out = el.querySelector('.fresh-age');
      if (out) out.textContent = ago(age);
      if (el.getAttribute('data-fixed-state')) continue;
      var freshH = parseFloat(el.getAttribute('data-fresh-h'));
      var staleH = parseFloat(el.getAttribute('data-stale-h'));
      var h = age / 3600000;
      el.setAttribute('data-state', h < freshH ? 'fresh' : (h < staleH ? 'aging' : 'stale'));
    }}
  }}
  tick();
  setInterval(tick, 60000);
}})();
(function () {{
  var root = document.documentElement;
  var sun = document.getElementById('icon-sun');
  var moon = document.getElementById('icon-moon');
  var btn = document.getElementById('theme-toggle');
  var STORAGE_KEY = 'mtl-theme';

  function isDark(theme) {{
    return theme !== 'light'; // dark is the unconditional default; only an explicit "light" opts out
  }}
  function apply(theme) {{
    if (theme) {{ root.setAttribute('data-mtl-theme', theme); }} else {{ root.removeAttribute('data-mtl-theme'); }}
    var dark = isDark(theme);
    if (sun) sun.hidden = dark;
    if (moon) moon.hidden = !dark;
  }}

  var saved = null;
  try {{ saved = localStorage.getItem(STORAGE_KEY); }} catch (e) {{}}
  apply(saved);

  if (btn) {{
    btn.addEventListener('click', function () {{
      var next = isDark(root.getAttribute('data-mtl-theme')) ? 'light' : 'dark';
      apply(next);
      try {{ localStorage.setItem(STORAGE_KEY, next); }} catch (e) {{}}
    }});
  }}
}})();
</script>
'''


ASSET_MATCH = {
    'equities': ['spy', 'dia', '^gspc', 's&p 500', 's&p'],
    'bonds': ['tlt', 'shy', 'us30y', '10y', '30y', '2y', 'yield', 'treasury'],
    'gold': ['gld', 'gold', 'xau'],
    'dollar': ['dxy', 'dx-y', 'usd', 'dollar'],
    'iwm': ['iwm', 'russell'],
    'qqq': ['qqq', 'nasdaq', 'smh'],
}


def matches_asset(asset_key, c):
    """Keyword must start a word (endings allowed - 'yield' hits 'yields'),
    so 'usd' no longer matches inside a pair like BTC-USD."""
    haystack = ' '.join((c.get('tickers', ''), c.get('event', ''), c.get('numbers', ''))).lower()
    return any(re.search(r'(?<![\w-])' + re.escape(k), haystack) for k in ASSET_MATCH.get(asset_key, []))


def matching_catalysts(asset_key, news_log, date):
    return [c for c in news_log if c.get('date') == date and matches_asset(asset_key, c)]


HORIZON_LABEL = {1: '1D', 5: '5D', 10: '10D'}


def pct_tone(pct):
    if pct is None:
        return 'flat'
    return 'good' if pct >= 55 else ('critical' if pct < 45 else 'flat')


def fmt_pct_or_dash(rate):
    return f"{rate['pct']:.1f}%" if rate['pct'] is not None else '—'


def record_row(label, rate, edge=None, real=None):
    n_txt = f"{rate['hits']}/{rate['n']}" if rate['n'] else '0/0'
    edge_txt = f" · edge {edge:+d}" if edge is not None and rate['n'] else ''
    real_txt = ''
    if real is not None and real['n']:
        real_edge_txt = f" · edge {real['edge']:+d}" if real.get('edge') is not None else ''
        real_txt = (f'<span class="record-row-real">real {fmt_pct_or_dash(real)} '
                    f'({real["hits"]}/{real["n"]}{real_edge_txt})</span>')
    return (f'<div class="record-row"><span class="record-row-label">{E(label)}</span>'
            f'<span class="record-row-val">{fmt_pct_or_dash(rate)} '
            f'<span class="record-row-n">({n_txt}{edge_txt})</span>{real_txt}</span></div>')


def track_record_section(all_docs: dict) -> str:
    agg = aggregate(all_docs)
    if agg['settledCells'] == 0:
        return ('<div class="record"><p class="record-empty">No calls have matured and settled '
                'yet - the earliest published document is too recent for any 1-day horizon to '
                'have closed. Come back after the next session close.</p></div>')

    overall = agg['overall']
    overall_real = agg['overallReal']
    tone = pct_tone(overall['pct'])
    tone_real = pct_tone(overall_real['pct'])
    by_horizon = "".join(record_row(HORIZON_LABEL[h], agg['byHorizon'][h], agg['byHorizon'][h]['edge'],
                                     agg['byHorizon'][h]['real'])
                         for h in (1, 5, 10))
    by_asset = "".join(record_row(TICKER.get(k, k.upper()), agg['byAsset'][k], agg['byAsset'][k]['edge'],
                                   agg['byAsset'][k]['real'])
                       for k in ('equities', 'bonds', 'gold', 'dollar', 'iwm', 'qqq'))
    by_call = "".join(record_row(t.capitalize(), agg['byCallType'][t], agg['byCallType'][t]['edge'],
                                  agg['byCallType'][t]['real'])
                      for t in ('bullish', 'bearish', 'flat', 'no-call') if agg['byCallType'][t]['n'])

    overlay = agg['overlay']
    overlay_html = ''
    if overlay['native']:
        overlay_html = f'''
      <div class="record-block">
        <h3>Overlay effect (cells it actually changed)</h3>
        {record_row('Post-overlay', overlay['post'], overlay['postEdge'])}
        {record_row('Pre-overlay (shadow)', overlay['pre'], overlay['preEdge'])}
      </div>'''

    return f'''
    <div class="record">
      <p class="record-head-label">Result</p>
      <div class="record-head">
        <span class="record-pct {tone}">{fmt_pct_or_dash(overall)}</span>
        <span class="record-n">{overall['hits']}/{overall['n']} settled calls correct</span>
        <span class="record-edge">edge {agg['overallEdge']:+d} units</span>
      </div>
      <p class="record-head-label">Real Result <span class="record-row-real">({agg['noCallCells']} directional
        call{'s' if agg['noCallCells'] != 1 else ''} that landed flat excluded as no-call push{'es' if agg['noCallCells'] != 1 else ''}, not misses)</span></p>
      <div class="record-head">
        <span class="record-pct {tone_real}">{fmt_pct_or_dash(overall_real)}</span>
        <span class="record-n">{overall_real['hits']}/{overall_real['n']} real-result calls correct</span>
        <span class="record-edge">edge {agg['overallRealEdge']:+d} units</span>
      </div>
      <div class="record-grid">
        <div class="record-block"><h3>By horizon</h3>{by_horizon}</div>
        <div class="record-block"><h3>By asset</h3>{by_asset}</div>
        <div class="record-block"><h3>By call type</h3>{by_call}</div>
      </div>
      {overlay_html}
      <p class="record-caveat">{E(agg['byCategoryWarning'])}</p>
    </div>'''


LOG_MAX_SESSIONS = 14  # cap the rendered log so the page doesn't grow unbounded over months


PROVISIONAL_TAG = ('<span class="log-prov" title="graded on an intraday print - '
                   'final after the maturity session closes; not in the track record">so far</span>')


def result_badge(settled, correct, provisional=False):
    if not settled:
        return '<span class="log-pending">pending</span>'
    if correct is None:
        return '<span class="log-noscore">not scored</span>'
    badge = ('<span class="log-correct">✓ correct</span>' if correct
             else '<span class="log-wrong">✗ incorrect</span>')
    return badge + (PROVISIONAL_TAG if provisional else '')


def actual_badge(oc, ret, settled):
    """What really happened, independent of what was called - the same
    outcome() classification settle_horizon graded the call against, so
    this is never a second opinion, just the raw fact being shown."""
    if not settled:
        return '<span class="log-pending">pending</span>'
    role, hexval, arrow = CALL_STATUS.get(oc, ('flat', '#898781', '▬'))
    return (f'<span class="log-call"><span class="dot" style="--dot:{hexval}"></span>{arrow} {E(oc)}</span>'
            f'<span class="log-conf">{fmt_pct(ret)}</span>')


def real_result_badge(settled, call, oc, provisional=False):
    if not settled:
        return '<span class="log-pending">pending</span>'
    rr = real_result(call, oc)
    if rr is None:
        return '<span class="log-noscore">not scored</span>'
    tag = PROVISIONAL_TAG if provisional else ''
    if rr == 'correct':
        return '<span class="log-correct">✓ correct</span>' + tag
    if rr == 'no-call':
        return '<span class="log-nocall">– no call</span>' + tag
    return '<span class="log-wrong">✗ incorrect</span>' + tag


def log_row(date, a, h):
    role, hexval, arrow = CALL_STATUS.get(h['call'], ('flat', '#898781', '▬'))
    settled = h.get('maturityClose') is not None
    end_price = fmt_price(h['maturityClose']) if settled else '—'
    oc = outcome(h['ret'], h['band']) if settled else None
    return f'''<tr>
      <td class="log-date">{E(date)}</td>
      <td class="log-ticker">{E(display_ticker(a))}</td>
      <td>{h['h']}D</td>
      <td><span class="log-call"><span class="dot" style="--dot:{hexval}"></span>{arrow} {E(h['call'])}</span>
          <span class="log-conf">{E(h['confidence'])}</span></td>
      <td class="log-matures">{E(h['maturity'])}</td>
      <td class="log-price">{fmt_price(a['close'])}</td>
      <td class="log-price">{end_price}</td>
      <td>{actual_badge(oc, h.get('ret'), settled)}</td>
      <td>{result_badge(settled, h.get('correct'), bool(h.get('provisional')))}</td>
      <td>{real_result_badge(settled, h['call'], oc, bool(h.get('provisional')))}</td>
    </tr>'''


def call_log_section(all_docs: dict) -> str:
    dates = sorted(all_docs, reverse=True)
    shown_dates = dates[:LOG_MAX_SESSIONS]
    rows = []
    for date in shown_dates:
        doc = all_docs[date]
        for a in doc['assets']:
            for h in sorted(a['horizons'], key=lambda h: h['h']):
                if is_call(h):
                    rows.append(log_row(date, a, h))

    caption = f"showing the {len(shown_dates)} most recent session(s) ({len(rows)} calls)"
    if len(dates) > len(shown_dates):
        caption += f" of {len(dates)} published total - see documents/ in the repo for the full history"

    return f'''
    <div class="log-wrap">
      <table class="log">
        <thead><tr><th>Date</th><th>Asset</th><th>Horizon</th><th>Predicted</th><th>Matures</th><th>Start</th><th>End</th><th>Actual</th><th>Result</th><th>Real Result</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    <p class="log-caption">{E(caption)}</p>'''


ET = ZoneInfo("America/New_York")


def _parse_utc(ts):
    """ISO-8601 UTC stamp ('...Z' or '+00:00') -> aware datetime, or None."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        return None


def fmt_et(dt):
    """'Sat Sep 26, 2:27 PM ET' - the page's readers think in New York time."""
    local = dt.astimezone(ET)
    return local.strftime('%a %b %-d, %-I:%M %p ET')


def fresh_item(label, dt, note='', fresh_h=None, stale_h=None, fixed_state=None, css=''):
    """One tile of the freshness panel. The age ("3h 5m ago") and the
    fresh/aging/stale dot are filled in client-side from data-ts, so they
    stay right however long after rendering the page is viewed."""
    if dt is None:
        return (f'<div class="fresh-item {css}" data-state="stale"><span class="fresh-dot"></span>'
                f'<span class="fresh-label">{E(label)}</span>'
                f'<span class="fresh-value">unknown</span></div>')
    iso = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    attrs = f'data-ts="{iso}"'
    if fixed_state:
        attrs += f' data-state="{fixed_state}" data-fixed-state="1"'
    else:
        attrs += f' data-fresh-h="{fresh_h}" data-stale-h="{stale_h}"'
    note_html = f'<span class="fresh-note">{note}</span>' if note else ''
    return (f'<div class="fresh-item {css}" {attrs}><span class="fresh-dot"></span>'
            f'<span class="fresh-label">{E(label)}</span>'
            f'<span class="fresh-value" title="{iso}">{E(fmt_et(dt))} · <span class="fresh-age"></span></span>'
            f'{note_html}</div>')


def calls_fresh_html(doc, now=None):
    """When the calls were written, and whether a newer session's board is
    due: a session counts as closed from 4 PM ET that day, and its board is
    written by the 9:20 AM daily-cycle Routine the next trading morning -
    so between the close and ~10 AM the next board is 'due', not late."""
    now_et = (now or datetime.now(ET)).astimezone(ET)
    today = now_et.date()
    closed = (today.isoformat() if is_trading_day(today) and now_et.hour >= 16
              else most_recent_completed_session(today))
    session = datetime.fromisoformat(doc['date']).strftime('%a %b %-d')
    if doc['date'] >= closed:
        note, state = f'Calls for session {E(session)} - the latest completed session', 'fresh'
    else:
        exp = datetime.fromisoformat(closed).strftime('%a %b %-d')
        due_day = next_trading_day(closed)
        due = datetime.combine(due_day, datetime.min.time(), ET).replace(hour=10)
        if now_et < due:
            note = (f'Calls for session {E(session)} - the {E(exp)} board is written '
                    f'{E(due_day.strftime("%a"))} ~9:45 AM ET')
            state = 'aging'
        else:
            note, state = f'Calls for session {E(session)} - the {E(exp)} board is not published yet', 'stale'
    return fresh_item('Calls written', _parse_utc(doc.get('generatedAt')), note, fixed_state=state)


def live_note_html(live):
    if not live or not live.get('prices'):
        return ''
    note = 'Overlay only - never the basis a call was made against'
    return fresh_item('Live prices', _parse_utc(live.get('fetchedAt')), note,
                      fresh_h=1, stale_h=4, css='live-note')


def board_stamp(doc):
    """Every note on a board - driver notes, all 13 category votes per
    horizon, stretch drivers, overlay notes - is written in one pass for one
    session, so they all share the document's generatedAt and basis date."""
    dt = _parse_utc(doc.get('generatedAt'))
    if dt is None:
        return None
    basis = doc.get('basisDate') or doc['date']
    return dict(written=fmt_et(dt), iso=dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
                short=dt.astimezone(ET).strftime('%b %-d %-I:%M%p').replace('AM', 'am').replace('PM', 'pm'),
                basis=datetime.fromisoformat(basis).strftime('%a %b %-d'))


def freshness_html(doc, live, generated_at):
    page = fresh_item('Page rebuilt', _parse_utc(generated_at),
                      'Grades and the track record are recomputed on every rebuild',
                      fresh_h=4, stale_h=24)
    return f'<div class="fresh">{calls_fresh_html(doc)}{live_note_html(live)}{page}</div>'


def news_after(news_log, date):
    """Entries from data/news_log.json (stored as {id, data} rows) dated
    after `date`, newest first, flattened to the shape catalyst_item reads."""
    rows = [r.get('data', r) for r in (news_log or [])]
    rows = [r for r in rows if (r.get('date') or '') > date]
    return sorted(rows, key=lambda r: (r['date'], -(r.get('order') or 0)), reverse=True)


# Opens the News event issue form; .github/workflows/news-from-issue.yml turns
# the owner's submissions into data/news_log.json entries.
SUBMIT_NEWS_URL = "https://github.com/danreed001-droid/NIBII/issues/new?template=news-event.yml"
# The Daily Market Data Fetch workflow's page, where its "Run workflow"
# button lives - a static page can't start a run itself without shipping a
# token, so the button takes the owner there instead.
REFRESH_URL = "https://github.com/danreed001-droid/NIBII/actions/workflows/daily-fetch.yml"


# --- Growth ranking grid (data: documents/growth_rank.json, written by
# scripts/fetch_growth_rank.py; logic in mtl/growth_rank.py) ---------------

GROWTH_UP, GROWTH_DOWN = '#0ca30c', '#d03b3b'  # the page's bull/bear colours

GROWTH_CSS = """
<style>
.gr {
  background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px;
  padding: 18px 18px 14px; margin-bottom: 28px;
}
.gr-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 6px; font-size: 0.8rem; color: var(--ink-2); }
.gr-controls-label { min-width: 62px; }
.gr-btn { border: 1px solid var(--hairline); background: transparent; color: var(--ink-2); border-radius: 999px;
  padding: 5px 12px; font: inherit; font-size: 0.8rem; cursor: pointer; }
.gr-btn:hover { border-color: var(--muted); color: var(--ink); }
.gr-btn[aria-pressed="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.gr-note, .gr-sub { margin: 4px 0 10px; font-size: 0.8rem; color: var(--muted); line-height: 1.5; }
.gr-sub { color: var(--ink-2); }
.gr[data-mode="range"] .gr-note[data-for="sigma"], .gr[data-mode="sigma"] .gr-note[data-for="range"], .gr[data-mode="price"] .gr-note[data-for="sigma"] { display: none; }
.gr[data-view="weekly"] .gr-view[data-view="daily"], .gr[data-view="daily"] .gr-view[data-view="weekly"] { display: none; }
.gr[data-mode="range"] .gr-z, .gr[data-mode="price"] .gr-z { display: none; }
.gr[data-mode="price"] table.gr-table tbody td:not(.gr-na) { background: var(--gr-bg-price); color: var(--gr-fg-price); }
.gr .gr-px { display: none; }
.gr[data-show="price"] .gr-px { display: block; font-size: 0.82rem; font-weight: 700; }
.gr[data-show="price"] .gr-rank { display: none; }
.gr[data-mode="range"] .gr-note[data-for="price"], .gr[data-mode="sigma"] .gr-note[data-for="price"], .gr[data-mode="price"] .gr-note[data-for="range"] { display: none; }
.gr-scroll { overflow-x: auto; }
.gr-date { border: 1px solid var(--hairline); background: transparent; color: var(--ink); border-radius: 999px;
  padding: 4px 10px; font: inherit; font-size: 0.8rem; color-scheme: light dark; }
.gr-status { color: var(--muted); }
table.gr-table { width: 100%; min-width: 560px; border-collapse: separate; border-spacing: 3px; table-layout: fixed;
  font-size: 0.75rem; font-variant-numeric: tabular-nums; }
table.gr-table col.gr-label-col { width: 112px; }
table.gr-table th { font-weight: 600; color: var(--muted); font-size: 0.68rem; text-align: center; padding: 4px 2px; }
table.gr-table th.gr-label { text-align: left; white-space: nowrap; color: var(--ink-2); padding-right: 8px; }
table.gr-table th.gr-label em { font-weight: 400; color: var(--muted); }
.gr-name { display: block; color: var(--ink); }
.gr-tk { display: block; font-weight: 400; font-size: 0.62rem; }
table.gr-table td { text-align: center; padding: 5px 2px; border-radius: 6px; line-height: 1.2; }
table.gr-table tbody td:not(.gr-na) { background: var(--gr-bg-range); color: var(--gr-fg-range); }
.gr[data-mode="sigma"] table.gr-table tbody td:not(.gr-na) { background: var(--gr-bg-sigma); color: var(--gr-fg-sigma); }
.gr-rank { display: block; font-size: 0.95rem; font-weight: 700; }
.gr-detail { display: block; font-size: 0.62rem; opacity: 0.85; }
td.gr-na { color: var(--muted); }
table.gr-table tfoot td { color: var(--ink); font-weight: 600; }
table.gr-table tr.gr-sum td { font-size: 0.92rem; border-top: 1px solid var(--hairline); }
td.gr-up { color: #0ca30c; } td.gr-down { color: #d03b3b; }
</style>
"""

GROWTH_JS = """
<script>
(function () {
  var gr = document.getElementById('growthRank');
  if (!gr) return;
  // Two independent toggles: weekly/daily (data-view) and shading (data-mode).
  function toggle(selector, attr, key, values) {
    var buttons = gr.querySelectorAll(selector);
    function set(value) {
      gr.setAttribute('data-' + attr, value);
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].setAttribute('aria-pressed', String(buttons[i].getAttribute('data-' + attr) === value));
      }
      try { localStorage.setItem(key, value); } catch (e) {}
    }
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function () { set(this.getAttribute('data-' + attr)); });
    }
    var saved = null;
    try { saved = localStorage.getItem(key); } catch (e) {}
    if (values.indexOf(saved) >= 0) set(saved);
  }
  toggle('.gr-view-btn', 'view', 'mtl-gr-view', ['weekly', 'daily']);
  toggle('.gr-mode-btn', 'mode', 'mtl-gr-mode', ['range', 'sigma', 'price']);
  toggle('.gr-show-btn', 'show', 'mtl-gr-show', ['rank', 'price']);
  gr.querySelectorAll('.gr-show-btn').forEach(function (b) {   // showing prices colors by price level; back to ranks restores move size
    b.addEventListener('click', function () {
      var m = b.getAttribute('data-show') === 'price' ? 'price' : 'range', mb = gr.querySelector('.gr-mode-btn[data-mode="' + m + '"]');
      if (mb && (m === 'price' || gr.getAttribute('data-mode') === 'price')) mb.click();
    });
  });

  // "Ending on" date picker: rebuild both grids from docs/growth_history.json with the same
  // rules as mtl/growth_rank.py (rank_grid / build), loaded only when a date is picked.
  var C = JSON.parse(gr.getAttribute('data-cfg') || '{}');
  var input = gr.querySelector('.gr-date'), latest = gr.querySelector('.gr-latest'), status = gr.querySelector('.gr-status');
  if (!input) return;
  var views = {}, original = {}, H = null, loading = null;
  gr.querySelectorAll('.gr-view').forEach(function (v) { views[v.getAttribute('data-view')] = v; original[v.getAttribute('data-view')] = v.innerHTML; });
  function load() {
    if (H) return Promise.resolve(H);
    if (!loading) loading = fetch(C.src + '?v=' + (C.v || '')).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { H = j; if (j.days && j.days.length) { input.min = j.days[31] || j.days[0]; } return j; });
    return loading;
  }
  function iso(d) { return d.toISOString().slice(0, 10); }
  function addDays(s, n) { var d = new Date(s + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return iso(d); }
  function friday(s) { var d = new Date(s + 'T12:00:00Z'), wd = (d.getUTCDay() + 6) % 7; return addDays(s, 4 - wd); }
  function rankGrid(by, periods, partialAfter, baseline, assets) {
    if (periods.length < 2) return null;
    var start = periods[0], shown = periods.slice(1), tickers = assets.map(function (a) { return a[0]; }).filter(function (t) { return by[t]; });
    function pct(t, p, c) { var m = by[t]; return (p in m && c in m && m[p]) ? (m[c] - m[p]) / m[p] * 100 : null; }
    var rows = shown.map(function (cur, i) {
      var prev = periods[i], cells = {};
      tickers.forEach(function (t) { var p = pct(t, prev, cur); if (p !== null) cells[t] = { pct: p, close: by[t][cur] }; });
      Object.keys(cells).sort(function (a, b) { return cells[b].pct - cells[a].pct; }).forEach(function (t, k) { cells[t].rank = k + 1; });
      return { period: cur, partial: cur > partialAfter, n: Object.keys(cells).length, cells: cells };
    });
    tickers.forEach(function (t) {
      var keys = Object.keys(by[t]).sort(), hist = [];
      for (var i = 1; i < keys.length; i++) { var c = pct(t, keys[i - 1], keys[i]); if (c !== null) hist.push([keys[i], c]); }
      rows.forEach(function (row) {
        var cell = row.cells[t]; if (!cell) return;
        var prior = [];
        for (var i = 0; i < hist.length && hist[i][0] < row.period; i++) prior.push(hist[i][1]);
        prior = prior.slice(-baseline);
        if (prior.length < C.minBase) return;
        var mean = prior.reduce(function (a, b) { return a + b; }, 0) / prior.length;
        var sd = Math.sqrt(prior.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / (prior.length - 1));
        if (sd > 0) { cell.sigma = sd; cell.z = cell.pct / sd; }
      });
    });
    var rankSum = {}, growth = {};
    tickers.forEach(function (t) {
      rankSum[t] = rows.reduce(function (a, r) { return a + (r.cells[t] ? r.cells[t].rank : tickers.length); }, 0);
      growth[t] = pct(t, start, shown[shown.length - 1]);
    });
    rows.reverse();
    return { assets: assets.filter(function (a) { return by[a[0]]; }), start: start, rows: rows, rankSum: rankSum, growth: growth };
  }
  function build(end) {
    var days = H.days, by = {}, weekly = {}, n = 0;
    while (n < days.length && days[n] <= end) n++;
    H.assets.forEach(function (a) {
      var cl = H.closes[a[0]], m = {}, w = {};
      for (var i = 0; i < n; i++) if (cl[i]) { m[days[i]] = cl[i]; w[friday(days[i])] = cl[i]; }
      if (Object.keys(m).length) { by[a[0]] = m; weekly[a[0]] = w; }
    });
    var allWeeks = {}; Object.keys(weekly).forEach(function (t) { Object.keys(weekly[t]).forEach(function (k) { allWeeks[k] = 1; }); });
    var weeks = Object.keys(allWeeks).sort(), common = [];
    for (var i = 0; i < n; i++) { var ok = true; for (var t in by) if (!(days[i] in by[t])) { ok = false; break; } if (ok) common.push(days[i]); }
    return { weekly: rankGrid(weekly, weeks.slice(-(C.weeks + 1)), end, C.baseW, H.assets),
             daily: rankGrid(by, common.slice(-(C.days + 1)), '9999-12-31', C.baseD, H.assets) };
  }
  function shade(p, frac, mode) {
    var st = 15 + 70 * Math.max(0, Math.min(frac, 1)), col = p >= 0 ? C.up : C.down;
    return '--gr-bg-' + mode + ': color-mix(in srgb, ' + col + ' ' + st.toFixed(0) + '%, var(--surface)); --gr-fg-' + mode + ': ' + (st > 55 ? '#ffffff' : 'var(--ink)') + ';';
  }
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  function fmt(s, long) { var d = new Date(s + 'T12:00:00Z'); return long ? MON[d.getUTCMonth()] + ' ' + d.getUTCDate() + ', ' + d.getUTCFullYear() : WD[d.getUTCDay()] + ' ' + MON[d.getUTCMonth()] + ' ' + d.getUTCDate(); }
  function table(g, view) {
    var weekly = view === 'weekly', unit = weekly ? 'week' : 'day', units = weekly ? 'weeks' : 'days', adj = weekly ? 'weekly' : 'daily';
    if (!g) return '<p class="gr-sub">Not enough data before this date.</p>';
    var maxAbs = {}, lo = {}, hi = {};
    g.assets.forEach(function (a) {
      maxAbs[a[0]] = g.rows.reduce(function (m, r) { return r.cells[a[0]] ? Math.max(m, Math.abs(r.cells[a[0]].pct)) : m; }, 0);
      g.rows.forEach(function (r) { var c = r.cells[a[0]]; if (c && c.close != null) { lo[a[0]] = Math.min(lo[a[0]] == null ? Infinity : lo[a[0]], c.close); hi[a[0]] = Math.max(hi[a[0]] == null ? -Infinity : hi[a[0]], c.close); } });
    });
    function px(x) { return x == null ? '–' : x >= 1000 ? Math.round(x).toLocaleString('en-US') : x >= 100 ? x.toFixed(1) : x >= 10 ? x.toFixed(2) : x.toFixed(3); }
    var head = g.assets.map(function (a) { return '<th><span class="gr-name">' + a[1] + '</span><span class="gr-tk">' + a[0] + '</span></th>'; }).join('');
    var body = g.rows.map(function (row) {
      var label = weekly ? fmt(row.period, true) : fmt(row.period, false);
      if (row.partial) label += weekly ? ' <em>(to date)</em>' : ' <em>(live)</em>';
      var when = weekly ? 'week ending ' + fmt(row.period, true) : fmt(row.period, false);
      return '<tr><th class="gr-label">' + label + '</th>' + g.assets.map(function (a) {
        var c = row.cells[a[0]];
        if (!c) return '<td class="gr-na">–</td>';
        var z = c.z, normal = z != null ? ' vs. normal ±' + c.sigma.toFixed(2) + '% (' + Math.abs(z).toFixed(1) + '× normal)' : '';
        var tip = a[1] + ', ' + when + ': ' + (c.pct >= 0 ? '+' : '') + c.pct.toFixed(2) + '%' + normal + ' — rank ' + c.rank + ' of ' + row.n;
        var q = c.close != null && hi[a[0]] > lo[a[0]] ? (c.close - lo[a[0]]) / (hi[a[0]] - lo[a[0]]) : 0.5;
        if (c.close != null) tip += ' — close ' + px(c.close) + ' (' + Math.round(q * 100) + '% of its low–high range here)';
        var style = shade(c.pct, maxAbs[a[0]] ? Math.abs(c.pct) / maxAbs[a[0]] : 0, 'range') + shade(c.pct, z != null ? Math.abs(z) / C.cap : 0, 'sigma') + shade(q - 0.5, Math.abs(q - 0.5) * 2, 'price');
        return '<td style="' + style + '" title="' + tip + '"><span class="gr-rank">' + c.rank + '</span><span class="gr-px">' + px(c.close) + '</span><span class="gr-detail">' + (c.pct >= 0 ? '+' : '') + c.pct.toFixed(1) + '%' +
          (z != null ? '<span class="gr-z"> · ' + Math.abs(z).toFixed(1) + 'σ</span>' : '') + '</span></td>';
      }).join('') + '</tr>';
    }).join('');
    var sums = g.assets.map(function (a) { return '<td>' + g.rankSum[a[0]] + '</td>'; }).join('');
    var grow = g.assets.map(function (a) { var v = g.growth[a[0]]; return v == null ? '<td class="gr-na">–</td>' : '<td class="' + (v >= 0 ? 'gr-up' : 'gr-down') + '">' + (v >= 0 ? '+' : '') + v.toFixed(1) + '%</td>'; }).join('');
    var n = g.rows.length;
    return '<p class="gr-sub">Each ' + unit + ' (' + (weekly ? 'Friday close to Friday close' : 'close to close, trading days every asset traded') + '), the assets are ranked by their % change: <strong>1</strong> = best gain that ' + unit +
      '. The <strong>sum of ' + adj + ' ranks</strong> over the ' + n + ' ' + units + ' (since ' + fmt(g.start, true) + ') is at the bottom — lowest sum = best. Green = up, red = down. Hover a cell for details.</p>' +
      '<div class="gr-scroll"><table class="gr-table"><colgroup><col class="gr-label-col">' + g.assets.map(function () { return '<col>'; }).join('') + '</colgroup>' +
      '<thead><tr><th class="gr-label">' + (weekly ? 'Week ending' : 'Day') + '</th>' + head + '</tr></thead><tbody>' + body + '</tbody>' +
      '<tfoot><tr class="gr-sum"><th class="gr-label">Sum of ranks</th>' + sums + '</tr><tr><th class="gr-label">' + n + '-' + unit + ' growth</th>' + grow + '</tr></tfoot></table></div>';
  }
  function show(end) {
    if (!end) { Object.keys(views).forEach(function (k) { views[k].innerHTML = original[k]; }); latest.setAttribute('aria-pressed', 'true'); status.textContent = ''; return; }
    status.textContent = 'loading…';
    load().then(function () {
      var g = build(end);
      views.weekly.innerHTML = table(g.weekly, 'weekly');
      views.daily.innerHTML = table(g.daily, 'daily');
      latest.setAttribute('aria-pressed', 'false');
      status.textContent = 'showing the ' + C.weeks + ' weeks / ' + C.days + ' trading days ending ' + fmt(end, true);
    }).catch(function () { status.textContent = 'history file unavailable'; });
  }
  input.addEventListener('change', function () { show(input.value); });
  latest.addEventListener('click', function () { input.value = ''; show(''); });
})();
</script>
"""


def _growth_shade(pct, frac, mode):
    """CSS custom properties for one shading mode: hue = direction (the
    page's bull green / bear red), strength = frac in [0, 1]."""
    strength = 15 + 70 * max(0.0, min(frac, 1.0))
    colour = GROWTH_UP if pct >= 0 else GROWTH_DOWN
    text = '#ffffff' if strength > 55 else 'var(--ink)'
    return (f'--gr-bg-{mode}: color-mix(in srgb, {colour} {strength:.0f}%, var(--surface)); '
            f'--gr-fg-{mode}: {text};')


def _price(x):
    if x is None:
        return '–'
    return f"{x:,.0f}" if x >= 1000 else f"{x:.1f}" if x >= 100 else f"{x:.2f}" if x >= 10 else f"{x:.3f}"


def _growth_table(grid, view):
    weekly = view == 'weekly'
    unit, units, adj = ('week', 'weeks', 'weekly') if weekly else ('day', 'days', 'daily')
    if not grid:
        return f'<div class="gr-view" data-view="{view}"><p class="gr-sub">{adj.capitalize()} data unavailable this run.</p></div>'
    assets = grid['assets']
    head = ''.join(f'<th><span class="gr-name">{E(name)}</span><span class="gr-tk">{E(t)}</span></th>'
                   for t, name in assets)
    max_abs = {t: max((abs(r['cells'][t]['pct']) for r in grid['rows'] if t in r['cells']), default=0)
               for t, _ in assets}
    closes = {t: [r['cells'][t]['close'] for r in grid['rows'] if t in r['cells'] and r['cells'][t].get('close') is not None]
              for t, _ in assets}
    lo = {t: min(v) if v else None for t, v in closes.items()}
    hi = {t: max(v) if v else None for t, v in closes.items()}
    body = []
    for row in grid['rows']:
        d = date.fromisoformat(row['period'])
        label = f"{d:%b} {d.day}, {d.year}" if weekly else f"{d:%a %b} {d.day}"
        if row['partial']:
            label += ' <em>(to date)</em>' if weekly else ' <em>(live)</em>'
        when = f"week ending {d:%b} {d.day}" if weekly else f"{d:%a %b} {d.day}"
        tds = []
        for t, name in assets:
            c = row['cells'].get(t)
            if not c:
                tds.append('<td class="gr-na">–</td>')
                continue
            z = c.get('z')
            normal = f" vs. normal ±{c['sigma']:.2f}% ({abs(z):.1f}× normal)" if z is not None else ''
            tip = f"{name}, {when}: {c['pct']:+.2f}%{normal} — rank {c['rank']} of {row['n']}"
            px = c.get('close')
            q = (px - lo[t]) / (hi[t] - lo[t]) if px is not None and hi[t] is not None and hi[t] > lo[t] else 0.5
            if px is not None:
                tip += f" — close {_price(px)} ({q * 100:.0f}% of its low–high range here)"
            style = (_growth_shade(c['pct'], abs(c['pct']) / max_abs[t] if max_abs[t] else 0, 'range')
                     + _growth_shade(c['pct'], abs(z) / growth_rank.SIGMA_CAP if z is not None else 0, 'sigma')
                     + _growth_shade(q - 0.5, abs(q - 0.5) * 2, 'price'))
            z_html = f'<span class="gr-z"> · {abs(z):.1f}σ</span>' if z is not None else ''
            tds.append(f'<td style="{style}" title="{E(tip)}"><span class="gr-rank">{c["rank"]}</span><span class="gr-px">{_price(px)}</span>'
                       f'<span class="gr-detail">{c["pct"]:+.1f}%{z_html}</span></td>')
        body.append(f'<tr><th class="gr-label">{label}</th>{"".join(tds)}</tr>')
    sums = ''.join(f'<td>{grid["rankSum"][t]}</td>' for t, _ in assets)
    growth = ''.join(
        f'<td class="{"gr-up" if g >= 0 else "gr-down"}">{g:+.1f}%</td>' if g is not None else '<td class="gr-na">–</td>'
        for g in (grid['growth'].get(t) for t, _ in assets))
    n = len(grid['rows'])
    start = date.fromisoformat(grid['start'])
    period_desc = 'Friday close to Friday close' if weekly else 'close to close, trading days every asset traded'
    return f"""<div class="gr-view" data-view="{view}">
  <p class="gr-sub">Each {unit} ({period_desc}), the assets are ranked by their % change: <strong>1</strong> = best gain that {unit}. The <strong>sum of {adj} ranks</strong> over the last {n} {units} (since {start:%b} {start.day}, {start.year}) is at the bottom — lowest sum = best. Green = up, red = down. Hover a cell for details.</p>
  <div class="gr-scroll"><table class="gr-table">
    <colgroup><col class="gr-label-col">{'<col>' * len(assets)}</colgroup>
    <thead><tr><th class="gr-label">{'Week ending' if weekly else 'Day'}</th>{head}</tr></thead>
    <tbody>{''.join(body)}</tbody>
    <tfoot><tr class="gr-sum"><th class="gr-label">Sum of ranks</th>{sums}</tr>
      <tr><th class="gr-label">{n}-{unit} growth</th>{growth}</tr></tfoot>
  </table></div>
</div>"""


def growth_rank_section(data):
    """The Growth ranking card, or '' when there's no documents/growth_rank.json yet."""
    if not data or not (data.get('weekly') or data.get('daily')):
        return ''
    end = (data.get('fetchedAt') or '')[:10]
    cfg = json.dumps(dict(src='growth_history.json', v=data.get('fetchedAt', ''), weeks=growth_rank.WEEKS, days=growth_rank.DAYS,
                          baseW=growth_rank.BASELINE_WEEKS, baseD=growth_rank.BASELINE_DAYS, minBase=growth_rank.MIN_BASELINE,
                          cap=growth_rank.SIGMA_CAP, up=GROWTH_UP, down=GROWTH_DOWN), separators=(',', ':'))
    return f"""<p class="section-label">Growth ranking</p>
{GROWTH_CSS}<div class="gr" id="growthRank" data-view="weekly" data-mode="range" data-show="rank" data-cfg="{E(cfg)}">
  <div class="gr-controls" role="group" aria-label="View"><span class="gr-controls-label">View:</span>
    <button type="button" class="gr-btn gr-view-btn" data-view="weekly" aria-pressed="true">Weekly · {growth_rank.WEEKS} weeks</button>
    <button type="button" class="gr-btn gr-view-btn" data-view="daily" aria-pressed="false">Daily · {growth_rank.DAYS} days</button></div>
  <div class="gr-controls" role="group" aria-label="Shading"><span class="gr-controls-label">Shade by:</span>
    <button type="button" class="gr-btn gr-mode-btn" data-mode="range" aria-pressed="true">Own range</button>
    <button type="button" class="gr-btn gr-mode-btn" data-mode="sigma" aria-pressed="false">vs. normal move (σ)</button>
    <button type="button" class="gr-btn gr-mode-btn" data-mode="price" aria-pressed="false">Price level</button></div>
  <div class="gr-controls" role="group" aria-label="Show"><span class="gr-controls-label">Show:</span>
    <button type="button" class="gr-btn gr-show-btn" data-show="rank" aria-pressed="true">Rank</button>
    <button type="button" class="gr-btn gr-show-btn" data-show="price" aria-pressed="false">Price</button></div>
  <div class="gr-controls" role="group" aria-label="End date"><span class="gr-controls-label">Ending on:</span>
    <input type="date" class="gr-date" aria-label="End date" max="{end}">
    <button type="button" class="gr-btn gr-latest" aria-pressed="true">Latest</button>
    <span class="gr-status" aria-live="polite"></span></div>
  <p class="gr-note" data-for="range">Darker = a bigger move <em>for that asset</em> — each column's largest move in the window is darkest.</p>
  <p class="gr-note" data-for="price">Price level: each asset's own closes in the window — red = its lowest close, full green = its highest, pale = the middle of its range.</p>
  <p class="gr-note" data-for="sigma">Darker = further off that asset's <em>normal</em> move (σ = std dev of its prior {growth_rank.BASELINE_WEEKS} weekly / {growth_rank.BASELINE_DAYS} daily changes) — pale = a normal move, darkest = {growth_rank.SIGMA_CAP:g}σ or more.</p>
{_growth_table(data.get('weekly'), 'weekly')}
{_growth_table(data.get('daily'), 'daily')}
</div>{GROWTH_JS}"""


def render(doc: dict, all_docs: dict = None, generated_at: str = None, live: dict = None,
           news_log: list = None, growth: dict = None) -> str:
    board_news = doc.get('context', {}).get('newsLog', [])
    later = news_after(news_log, doc['date'])
    stamp = board_stamp(doc)
    assets_html = "".join(
        asset_card(a, matching_catalysts(a['key'], board_news, doc['date']), stamp, live,
                   since=[c for c in later if matches_asset(a['key'], c)], board_date=doc['date'])
        for a in doc['assets']
    )
    docs = all_docs or {doc['date']: doc}
    rebuilt = generated_at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return PAGE.format(
        date=doc['date'], tape=ticker_strip(doc, live), stats=stat_tiles(doc),
        assets=assets_html, record=track_record_section(docs), log=call_log_section(docs),
        freshness=freshness_html(doc, live, rebuilt), submit_url=SUBMIT_NEWS_URL,
        refresh_url=REFRESH_URL, growth=growth_rank_section(growth),
    )


def load_all_documents(documents_dir):
    docs = {}
    for path in iter_document_paths(documents_dir):
        doc = json.load(open(path))
        docs[doc['date']] = doc
    return docs


def load_growth_rank(documents_dir):
    path = os.path.join(documents_dir, "growth_rank.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def load_live(documents_dir):
    path = os.path.join(documents_dir, "live.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def main(s: str):
    """Renders the board for session date `s`, always to the same files
    (documents/latest.html and docs/index.html) - overwritten each run
    rather than accumulating one HTML file per day. The underlying
    documents/<date>.json ledger is NOT touched by this script and stays
    one file per day; that's the real scored history the Track record /
    Call log sections are computed from, and it has to persist. Only these
    rendered display copies are disposable.

    docs/index.html exists because this repo's GitHub Pages is configured
    to serve from the /docs folder on main - that's the file Pages
    actually publishes at https://danreed001-droid.github.io/NIBII/.
    documents/latest.html stays too, for the artifact-publish workflow and
    anyone browsing the repo directly.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    documents_dir = os.path.join(root, "documents")
    doc = json.load(open(os.path.join(documents_dir, f"{s}.json")))
    all_docs = load_all_documents(documents_dir)
    live = load_live(documents_dir)
    news_path = os.path.join(root, "data", "news_log.json")
    news_log = json.load(open(news_path)) if os.path.exists(news_path) else None
    page = render(doc, all_docs, live=live, news_log=news_log,
                  growth=load_growth_rank(documents_dir))

    out_path = os.path.join(documents_dir, "latest.html")
    with open(out_path, "w") as f:
        f.write(page)
    print(f"wrote {out_path}")

    docs_dir = os.path.join(root, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    pages_path = os.path.join(docs_dir, "index.html")
    with open(pages_path, "w") as f:
        f.write(page)
    print(f"wrote {pages_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} YYYY-MM-DD")
    main(sys.argv[1])

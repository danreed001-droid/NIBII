#!/usr/bin/env python3
"""Friday alert: writes a GitHub issue title/body when Monday's trade has
anything to do - stock swaps (also the News boost list's), a sleeve switch, or a change in the Auto,
Boost, Guard or Steps mix (including the bear guard turning on or off). Midweek, an alert goes
out when Boost + rotation (the default plan) switches or the blow-off exit sells a stock: both
trade at the next session's close.

Reads data/momentum_scan.json (written by scripts/momentum_scan.py). Only on a
signal day (Friday's close); on other days, or when nothing changes, it writes
nothing and the workflow skips the issue.

Usage:
    python scripts/weekly_alert.py OUT_DIR [owner]     # writes OUT_DIR/alert_title.txt + alert_body.md
"""
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = 'https://danreed001-droid.github.io/NIBII/scanner.html'


def fmt(d):
    x = date.fromisoformat(d)
    return x.strftime('%a %b ') + str(x.day)


def pctw(w):
    return f"{round(w * 100)}%"


def pct1(w):
    return f"{w * 100:+.1f}%"


ROT_WHY = {'rotate': 'SPY in a daily downtrend while {to} makes higher highs and lows with the steepest gradient (led for the confirmation period)',
           'rotate-end': "{frm}'s daily uptrend broke", 'exit': "SPY's weekly downtrend: last lower high below the 150-day average, SPY below it, lower lows falling slowly",
           'switch': 'still out of stocks; {to} is now the steepest rising asset', 'above': 'SPY closed back above its 150-day average',
           'steeper': "SPY's daily higher lows are steeper than TLT's and GLD's"}


def rot_name(m):
    return 'the Boost 100% stock list' if m == 'boost' else m


def rotation_line(rt, as_of):
    """The Boost + rotation switch decided at the last close (None when it holds)."""
    if not rt or not rt.get('trade'):
        return None
    frm, to = rt.get('held'), rt.get('mode')
    log = rt.get('log') or []
    why = log[0][3] if log and log[0][0] == as_of else None
    reason = ROT_WHY.get(why, '').format(frm=frm, to=to)
    return (f"**Boost + rotation (the default plan):** sell {rot_name(frm)}, buy **{rot_name(to)}** with the whole account"
            + (f" ({reason})" if reason else ''))


def warn_line(rt):
    """Information only: SPY in a daily downtrend below its 150-day average while TLT or GLD rises."""
    if not rt or not rt.get('warn'):
        return None
    return (f"**Downtrend warning (information only):** SPY's daily chart is in a downtrend and SPY is below its "
            f"{rt.get('ma', 150)}-day average, while {rt['warn']} is rising most steeply. Boost + rotation keeps the stocks until its "
            f"{rt.get('confirm', 15)}-session confirmation; stepping into {rt['warn']} earlier is your call (as an automatic rule it fixed "
            f"late 2018 but cost about 2 points a year over 2000-2026).")


def rsi_line(rt):
    """Information only: SPY's RSI(14) broke its support line with SPY near or below its 150-day average."""
    w = (rt or {}).get('rsiWarn') or {}
    if not w.get('on'):
        return None
    return (f"**RSI support-line warning (information only):** SPY's 14-day RSI closed below a support line through its swing lows "
            f"on {fmt(w['date'])} (line {w.get('line')}, RSI now {w.get('rsi')}), and SPY is {pct1(w.get('gap') or 0)} vs its 150-day average. "
            "It fired before the August 2015 and October 2018 drops but also on dips that reversed; as an automatic exit it made "
            "about 2 points a year less than Boost + rotation over 2000-2026.")


def rotation_now(rt):
    if not rt:
        return None
    m = rt.get('mode')
    return ("- **Boost + rotation:** " + ("in the Boost 100% stock list" if m == 'boost' else f"out of stocks, 100% in {m}"))


def build(scan, owner=None):
    """(title, body) or None when there's nothing to do Monday (or, midweek, no rotation switch or blow-off sale)."""
    if not scan.get('signalDay'):
        return midweek(scan, owner)
    ch = scan.get('changes') or {}
    sells, buys = ch.get('sell') or [], ch.get('buy') or []
    sl = scan.get('sleeve') or {}
    auto = (scan.get('plan') or {}).get('auto') or {}
    steps = auto.get('steps') or {}
    guard = auto.get('guard') or {}
    items, tags = [], []
    rt = auto.get('rotation') or {}
    rl = rotation_line(rt, scan['asOf'])
    if rl:
        items.append(rl)
        tags.append(f"rotation → {rot_name(rt['mode']) if rt['mode'] != 'boost' else 'stocks'}")
    if rt.get('mode') and rt['mode'] != 'boost':
        items.append(f"Boost + rotation is out of stocks ({rt['mode']}): the stock changes below don't apply to it")
    wl = warn_line(rt)
    if wl and not rt.get('prevWarn'):
        items.append(wl)
        tags.append(f"downtrend warning ({rt['warn']})")
    rl_ = rsi_line(rt)
    if rl_ and not ((rt.get('rsiWarn') or {}).get('prevOn')):
        items.append(rl_)
        tags.append("RSI support-line warning")
    if sells or buys:
        items.append('**Stocks:** ' + ', '.join([f"sell {t}" for t in sells] + [f"buy {t}" for t in buys]))
        tags.append(', '.join([f"sell {t}" for t in sells] + [f"buy {t}" for t in buys]))
    if sl.get('held') and sl.get('prevHeld') and sl['held'] != sl['prevHeld']:
        items.append(f"**Sleeve pick:** switch {sl['prevHeld']} → {sl['held']} (matters whenever your mix holds the sleeve)")
        tags.append(f"sleeve {sl['prevHeld']}→{sl['held']}")
    if auto.get('split') and auto.get('prevSplit') and auto['split'] != auto['prevSplit']:
        items.append(f"**Auto mix:** {auto['prevSplit']} → **{auto['split']}** (top 5 / sleeve; {len(auto.get('down') or [])} holdings in a lower-low downtrend: {', '.join(auto.get('down') or []) or 'none'})")
        tags.append(f"auto {auto['split']}")
    if guard and guard.get('bear') != guard.get('prevBear'):
        on = guard.get('bear')
        items.append(f"**Bear guard {'ON' if on else 'OFF'}:** SPY {guard.get('spyNow')} vs {guard.get('spyYearAgo')} a year ago → "
                     + (f"move {pctw(guard.get('share', 0.5))} of the stock part into SPY (Guard mix)" if on else "move the SPY part back into the top 5 (Guard mix)"))
        tags.append(f"bear guard {'ON' if on else 'OFF'}")
    elif guard and guard.get('weights') != guard.get('prevWeights') and guard.get('bear'):
        items.append("**Guard mix:** weights changed with the Auto mix (see below)")
    if steps.get('split') and steps.get('prevSplit') and steps['split'] != steps['prevSplit']:
        items.append(f"**Steps mix:** {steps['prevSplit']} → **{steps['split']}**")
        tags.append(f"steps {steps['split']}")
    boost = auto.get('boost') or {}
    if boost.get('sell') or boost.get('buy'):
        bs, bb = boost.get('sell') or [], boost.get('buy') or []
        if (bs, bb) != (sells, buys):
            items.append('**If you follow Boost (news boost list):** ' + ', '.join([f"sell {t}" for t in bs] + [f"buy {t}" for t in bb]))
            tags.append('boost: ' + ', '.join([f"sell {t}" for t in bs] + [f"buy {t}" for t in bb]))
    bx = auto.get('boostx') or {}
    if bx.get('sell') or bx.get('buy'):
        xs, xb = bx.get('sell') or [], bx.get('buy') or []
        if (xs, xb) != (sells, buys):
            blown, surged = set(bx.get('blown') or []), set(bx.get('surged') or [])
            items.append('**If you follow Boost 100% or Boost + cushion (boost list + blow-off and surge exits):** '
                         + ', '.join([f"sell {t}" + (" (blow-off exit)" if t in blown else " (surge exit)" if t in surged else "") for t in xs] + [f"buy {t}" for t in xb]))
            tags.append('boost 100%: ' + ', '.join([f"sell {t}" for t in xs] + [f"buy {t}" for t in xb]))
        cl = call_line(bx, xb, xs)
        if cl:
            items.append(cl)
    sgl = surge_line(bx)
    if sgl:
        items.append(sgl)
    if bx and 'armedAt' in bx and bx.get('armedAt') != bx.get('prevArmed'):
        on = bx['armedAt']
        items.append(f"**Blow-off exit {'ON' if on else 'OFF'}** (Boost 100% and Boost + cushion): "
                     + (f"SPY closed below its {bx.get('ma', 150)}-day average, so from now on a holding whose last month's gain is more than "
                        f"{bx.get('mult', 2):g}x its prior 5 months' is sold - an alert goes out the evening it happens"
                        if on else f"SPY is back above its {bx.get('ma', 150)}-day average, so holdings are kept through blow-offs again"))
        tags.append(f"blow-off exit {'on' if on else 'off'}")
    if boost.get('split') and boost.get('prevSplit') and boost['split'] != boost['prevSplit']:
        items.append(f"**Boost mix:** {boost['prevSplit']} → **{boost['split']}** (Boost 100% stays fully in the stocks: nothing to change)")
    cush = auto.get('cushion') or {}
    if cush.get('split') and cush.get('prevSplit') and cush['split'] != cush['prevSplit']:
        to_sleeve = cush['split'] != '100/0'
        cr = cush.get('credit')
        items.append(f"**Boost + cushion:** {cush['prevSplit']} → **{cush['split']}** (SPY {pct1(cush.get('spyGap') or 0)} vs its {cush.get('ma', 150)}-day average"
                     + (f", junk vs quality bonds {pct1(cr)} over {cush.get('creditLook', 21)} sessions" if cr is not None else '') + '; '
                     + ("both say weak: move 25% of the stocks into the sleeve" if to_sleeve else "move the sleeve part back into the Boost list") + ")")
        tags.append(f"cushion {cush['split']}")
    if not items or items == [f"Boost + rotation is out of stocks ({rt.get('mode')}): the stock changes below don't apply to it"]:
        return None
    hold = [h['t'] for h in sorted(scan.get('holdings') or [], key=lambda h: h.get('rank') or 99)]
    gw = guard.get('weights') or [1, 0, 0]
    a_s = int((auto.get('split') or '100/0').split('/')[0]) / 100
    lines = [f"Signal from {fmt(scan['asOf'])}'s close. **Trade {fmt(scan['tradeDate'])}, 3:30–4:00 pm ET.**", '',
             '### What to do Monday', *[f"- {x}" for x in items], '',
             '### After the trades', f"- **Top 5:** {', '.join(hold)} (equal amounts)",
             *([f"- **Boost list:** {', '.join(boost['holdings'])}"] if boost.get('holdings') and set(boost['holdings']) != set(hold) else []),
             *([f"- **Boost 100% / cushion list:** {', '.join(bx['holdings'])}"] if bx.get('holdings') and set(bx['holdings']) != set(boost.get('holdings') or hold) else []),
             *([rotation_now(rt)] if rt else []),
             *([f"- {wl}"] if wl and rt.get('prevWarn') else []),
             *([f"- {rl_}"] if rl_ and (rt.get('rsiWarn') or {}).get('prevOn') else []),
             f"- **Sleeve pick:** {sl.get('held')}" + (f" ({sl.get('n')})" if sl.get('n') else ''),
             *([cushion_check(cush)] if cush.get('split') else []), '',
             '| Mix | Top 5 | Sleeve | SPY | Calls |', '|---|---|---|---|---|',
             f"| Auto | {pctw(a_s)} | {pctw(1 - a_s)} | 0% | 0% |",
             f"| Guard | {pctw(gw[0])} | {pctw(gw[1])} | {pctw(gw[2])} | 0% |"]
    if rt.get('mode'):
        lines.append("| Boost + rotation | 100% | 0% | 0% | 0% |" if rt['mode'] == 'boost' else f"| Boost + rotation | 0% (100% {rt['mode']}) | 0% | 0% | 0% |")
    if boost.get('split'):
        b_s = int(boost['split'].split('/')[0]) / 100
        lines.append(f"| Boost | {pctw(b_s)} | {pctw(1 - b_s)} | 0% | 0% |")
        lines.append("| Boost 100% | 100% | 0% | 0% | 0% |")
        if bx.get('calls'):
            lines.append(f"| Boost 100% + calls | {pctw(1 - (bx.get('callSleeve') or 0.2))} | 0% | 0% | {pctw(bx.get('callSleeve') or 0.2)} (about {pctw(bx.get('callBudget') or 0.1)} in calls, rest T-bills) |")
    if cush.get('split'):
        c_s = int(cush['split'].split('/')[0]) / 100
        lines.append(f"| Boost + cushion | {pctw(c_s)} | {pctw(1 - c_s)} | 0% | 0% |")
        if bx.get('calls'):
            cs_ = 1 - (bx.get('callSleeve') or 0.2)
            lines.append(f"| Boost + cushion + calls | {pctw(c_s * cs_)} | {pctw((1 - c_s) * cs_)} | 0% | {pctw(bx.get('callSleeve') or 0.2)} (about {pctw(bx.get('callBudget') or 0.1)} in calls, rest T-bills) |")
    if steps.get('split'):
        s_s = int(steps['split'].split('/')[0]) / 100
        lines.append(f"| Steps | {pctw(s_s)} | {pctw(1 - s_s)} | 0% | 0% |")
    lines += calls_table(bx)
    lines += ['', f"Exact dollars and shares for your account: {PAGE} (type your amount in the Account box).", '',
              (f"@{owner} " if owner else '') + "— sent automatically by the Top 5 Strongest update. Close this issue once you've traded."]
    title = f"Trade {fmt(scan['tradeDate'])}: " + '; '.join(tags)
    return title[:240], '\n'.join(lines) + '\n'


def calls_table(bx):
    """The call sleeve's calls for the Boost 100% list after the trades, with the best-case limits."""
    calls = bx.get('calls') or {}
    rows = [t for t in (bx.get('holdings') or []) if calls.get(t)]
    if not rows:
        return []
    out = ['', f"### Call sleeve - best-case pricing only (bid/ask <= {round((bx.get('callSpread') or 0.04) * 100)}% of mid)",
           '| Stock | Call | Expiry | Pay at most | Per contract | Max IV | Live check |', '|---|---|---|---|---|---|---|']
    for t in rows:
        c, q = calls[t], calls[t].get('quote') or {}
        live = 'best case' if q.get('ok') else 'skip' if q.get('ok') is False else 'check at the open'
        out.append(f"| {t} | ${c['strike']:g} | {fmt(c['expiry'])} {c['expiry'][:4]} | ${c['maxPrice']:.2f} | "
                   f"${c['maxPrice'] * 100:,.0f} | {round(c['maxIv'] * 100)}% | {live} |")
    return out


def cushion_check(cush):
    """One line with both cushion checks: SPY vs its average and junk vs quality bonds."""
    g, cr = cush.get('spyGap'), cush.get('credit')
    weak, stress = g is not None and g < 0, cr is None or cr < 0
    why = ('both weak' if weak and stress else 'SPY weak but credit calm - likely a false alarm, no cushion' if weak
           else 'SPY above its average')
    return (f"- **Cushion check:** SPY {pct1(g or 0)} vs its {cush.get('ma', 150)}-day average, junk vs quality bonds "
            + (f"{pct1(cr)} over {cush.get('creditLook', 21)} sessions" if cr is not None else 'no data')
            + f" → **{'on' if cush.get('split') != '100/0' else 'off'}** ({why})")


def call_line(bx, buys, sells):
    """The call sleeve: on each new stock, a best-case-priced 6-month call 20% out of the money; sell it with the stock."""
    calls, parts = bx.get('calls') or {}, []
    bud = round((bx.get('callBudget') or 0.10) * 100)
    for t in buys:
        c = calls.get(t)
        if not c:
            continue
        q = c.get('quote') or {}
        live = (' - live check: best case' if q.get('ok') else ' - live check: NOT best case, skip unless it improves'
                if q.get('ok') is False else '')
        parts.append(f"buy {t} ${c['strike']:g} call exp {fmt(c['expiry'])} {c['expiry'][:4]} - pay at most ${c['maxPrice']:.2f} "
                     f"(${c['maxPrice'] * 100:,.0f}/contract), only if IV <= {round(c['maxIv'] * 100)}% and bid/ask <= "
                     f"{round((bx.get('callSpread') or 0.04) * 100)}% of mid; otherwise skip{live}")
    parts += [f"sell your {t} call" for t in sells]
    if not parts:
        return None
    return (f"**Call sleeve (20% OTM, best-case pricing only, ~{bud}% of the account split across the calls held):** "
            + '; '.join(parts))


def surge_line(bx):
    """Heads-up for surge-exit sales already scheduled (a 5%+ up day on 4x+ volume -> sold a week later)."""
    g = (bx or {}).get('surge') or {}
    pend = g.get('pending') or []
    if not pend:
        return None
    return ('**Surge exit scheduled** (Boost 100%, cushion, and Boost + rotation while in stocks): '
            + '; '.join(f"{p['t']} closed {p['up'] * 100:+.0f}% on {p['x']:.1f}x its normal volume on {fmt(p['d'])}, so it is sold at the close on {fmt(p['sell'])}"
                        for p in pend)
            + " unless another rule sells it first. An alert goes out the evening before.")


def midweek(scan, owner=None):
    """A Boost + rotation switch or a blow-off exit sale decided at a weekday close other than
    Friday's: it fills at the next close."""
    auto = (scan.get('plan') or {}).get('auto') or {}
    bx = auto.get('boostx') or {}
    rt = auto.get('rotation') or {}
    mw = bx.get('midweek')
    rl = rotation_line(rt, scan['asOf'])
    if rl:
        lines = [f"**Trade at the close on {fmt(rt['trade'])}:** {rl}.", '',
                 "Decided at today's close; the rest of the plans (Auto, Boost, Steps, Boost 100%, cushion) have nothing to do"
                 + (" except the blow-off sale below." if mw and (mw.get('sell') or mw.get('buy')) else "."), '',
                 rotation_now(rt)]
        if mw and (mw.get('sell') or mw.get('buy')):
            lines += ['', f"**Boost 100% / cushion exit, same close:** "
                      + ', '.join([f"sell {t}" for t in mw.get('sell') or []] + [f"buy {t}" for t in mw.get('buy') or []])]
        lines += ['', f"Details: {PAGE}", '',
                  (f"@{owner} " if owner else '') + "- sent automatically by the Top 5 Strongest update. Close this issue once you've traded."]
        title = f"Trade {fmt(rt['trade'])}: Boost + rotation → {rot_name(rt['mode']) if rt['mode'] != 'boost' else 'back into stocks'}"
        return title[:240], '\n'.join(lines) + '\n'
    if not mw or not (mw.get('sell') or mw.get('buy')):
        wl = warn_line(rt) if not rt.get('prevWarn') else None
        rl_ = rsi_line(rt) if not ((rt.get('rsiWarn') or {}).get('prevOn')) else None
        if wl or rl_:
            lines = [x for x in (wl, rl_) if x] + ['', "Nothing to trade under any plan: this is a heads-up, not a signal.", '', f"Details: {PAGE}", '',
                     (f"@{owner} " if owner else '') + "- sent automatically by the Top 5 Strongest update."]
            what = f"SPY downtrend below its 150-day, {rt['warn']} rising" if wl else "SPY RSI broke its support line"
            return f"Warning {fmt(scan['asOf'])}: {what}"[:240], '\n'.join(lines) + '\n'
        return None
    blown, surged = set(mw.get('blown') or []), set(mw.get('surged') or [])
    acts = [f"sell {t}" + (" (blow-off exit)" if t in blown else " (surge exit)" if t in surged else "") for t in mw.get('sell') or []] + [f"buy {t}" for t in mw.get('buy') or []]
    g = bx.get('surge') or {}
    why = []
    if blown:
        why.append(f"The blow-off exit fired at today's close ({fmt(scan['asOf'])}): the sold stock's last month's gain is more than "
                   f"{bx.get('mult', 2):g}x its gain over the 5 months before. The exit is on because SPY is below its "
                   f"{bx.get('ma', 150)}-day average.")
    if surged:
        why.append(f"The surge exit fired at today's close ({fmt(scan['asOf'])}): {', '.join(sorted(surged))} closed "
                   f"{g.get('up', 0.05) * 100:.0f}%+ up on at least {g.get('vol', 4):g}x its 50-day average volume {g.get('delay', 5)} trading days ago.")
    if not why:
        why.append(f"A Boost 100% exit fired at today's close ({fmt(scan['asOf'])}).")
    lines = [f"**Trade at the close on {fmt(mw['date'])}:** Boost 100%, Boost + cushion, and Boost + rotation while it holds stocks: " + ', '.join(acts), '',
             ' '.join(why) + " Swap the same dollar amount; the rest of the account stays as it is.",
             *(['', call_line(bx, mw.get('buy') or [], mw.get('sell') or [])] if call_line(bx, mw.get('buy') or [], mw.get('sell') or []) else []),
             '', "Auto, Boost and Steps: nothing to do." + (f" Boost + rotation is out of stocks ({rt['mode']}): nothing to do." if rt.get('mode') and rt['mode'] != 'boost' else " Boost + rotation (in the Boost list): make the same swap."), '',
             f"Details: {PAGE}", '',
             (f"@{owner} " if owner else '') + "- sent automatically by the Top 5 Strongest update. Close this issue once you've traded."]
    title = f"Trade {fmt(mw['date'])}: Boost 100% / cushion {'surge' if surged and not blown else 'blow-off'} exit: " + ', '.join(acts)
    return title[:240], '\n'.join(lines) + '\n'


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    owner = sys.argv[2] if len(sys.argv) > 2 else None
    scan = json.load(open(os.path.join(ROOT, 'data', 'momentum_scan.json')))
    res = build(scan, owner)
    if not res:
        print("no Monday actions - no alert", file=sys.stderr)
        return
    title, body = res
    with open(os.path.join(out, 'alert_title.txt'), 'w') as f:
        f.write(title)
    with open(os.path.join(out, 'alert_body.md'), 'w') as f:
        f.write(body)
    print(title, file=sys.stderr)


if __name__ == '__main__':
    main()

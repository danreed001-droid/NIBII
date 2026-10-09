"""RSI support-line breaks on SPY, for the dashboard's downtrend warning (information only).

The line is drawn the way a chartist would: through two of RSI(14)'s swing lows (each the
lowest RSI within 3 sessions on both sides, so it is confirmed 3 sessions later), with at
least 4 swing lows touching it (within 2.5 RSI points) and none of them clearly below it.
A break is the first close of RSI more than 1 point under the line.

Tested as an automatic exit (a break, then SPY closing below its 150-day average within 20
sessions -> out of stocks) it made 28.9% a year from 2000 against 31.0% for Boost + rotation:
2018 -7% instead of -15%, but 2015 -15% instead of -6% (it sold the August 2015 drop and
missed the rebound), so it is shown as a warning, not traded.
"""

PIV, PTS, TOL, MARGIN, LOOK, RECENT, MIN_SPAN = 3, 4, 2.5, 1.0, 200, 8, 30
WINDOW = 20      # sessions a break stays relevant
NEAR = 0.02      # warn when SPY is below, or within 2% above, its 150-day average


def rsi(closes, n=14):
    """Wilder's RSI; None until n + 1 closes."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0.0)
        l += max(-d, 0.0)
    g, l = g / n, l / n
    out[n] = 100 - 100 / (1 + g / l) if l else 100.0
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (n - 1) + max(d, 0.0)) / n
        l = (l * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100 - 100 / (1 + g / l) if l else 100.0
    return out


def support_breaks(r, piv=PIV, pts=PTS, tol=TOL, margin=MARGIN, look=LOOK, recent=RECENT, min_span=MIN_SPAN):
    """{index: (line value, index of the line's first low)} for each session where RSI breaks
    its support line; each line can break once."""
    out, lows, used = {}, [], set()
    for k in range(len(r)):
        j = k - piv
        if j - piv >= 0 and all(r[x] is not None for x in range(j - piv, k + 1)) and r[j] == min(r[j - piv:k + 1]):
            lows.append((j, r[j]))
        if k == 0 or r[k] is None or r[k - 1] is None:
            continue
        cand = [p for p in lows[-recent:] if p[0] >= k - look]
        best = None
        for a in range(len(cand)):
            for b in range(a + 1, len(cand)):
                (x1, y1), (x2, y2) = cand[a], cand[b]
                if x2 - x1 < 5:
                    continue
                s = (y2 - y1) / (x2 - x1)
                after = [p for p in cand if p[0] >= x1]
                if any(p[1] < y1 + s * (p[0] - x1) - tol for p in after):
                    continue
                touch = [p for p in after if abs(p[1] - (y1 + s * (p[0] - x1))) <= tol]
                if len(touch) < pts or touch[-1][0] - touch[0][0] < min_span:
                    continue
                if best is None or x1 > best[0]:
                    best = (x1, y1, s)
        if best and best[0] not in used:
            x1, y1, s = best
            line, prev = y1 + s * (k - x1), y1 + s * (k - 1 - x1)
            if r[k] < line - margin and r[k - 1] >= prev - margin:
                out[k] = (round(line, 1), x1)
                used.add(x1)
    return out


def rsi_warning(closes, calendar, k, ma=150, window=WINDOW, near=NEAR, brk=None):
    """The RSI-break warning at session k: {on, date, line, rsi, gap} from the latest break in
    the last `window` sessions while SPY is below or within `near` of its `ma`-day average."""
    r = rsi(closes)
    brk = support_breaks(r) if brk is None else brk
    last = max((i for i in brk if i <= k), default=None)
    if last is None or k < ma - 1:
        return dict(on=False, date=calendar[last] if last is not None else None)
    gap = closes[k] / (sum(closes[k - ma + 1:k + 1]) / ma) - 1
    on = k - last <= window and gap < near
    return dict(on=on, date=calendar[last], line=brk[last][0], rsi=round(r[k], 1), gap=round(gap, 4),
                ago=k - last)

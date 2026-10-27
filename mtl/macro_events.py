"""Macro signals for the market events list: oil, the dollar, credit, the yield curve, inflation and jobs crossing the
lines that marked past turns. Information only: no trading rule reads this.

Each signal is an event on the first session it could be known, at most once a year (credit: once in six months):
  Oil up 50% in a year         oil (WTI) 50%+ above its level a year earlier
  Oil 40% under its high       oil 40%+ under its highest close of the last year
  Dollar up / down 10%         the dollar index 10%+ above / below its level a year earlier
  Credit cracking              banks (XLF) 10%+ and junk bonds (Vanguard high-yield fund) 3%+ under their 1-year
                               highs: the credit watch's line (mtl/credit.py)
  Yield curve inverts          the 10-year yield under the 3-month rate, the first time in six months
  Yield curve un-inverts       back above for 5 sessions after 3+ months of the last six inverted
  Inflation tops 4%            CPI 4%+ above a year earlier, the first time in a year
  Inflation turns down         CPI a full point under its peak of the last year, after a peak of 4%+
  Recession signal             the Sahm rule (unemployment's 3-month average 0.5 point above its low of the last
                               year) reaching 0.5
CPI and the Sahm rule count from the day they are published (about the 14th, and the jobs report's first Friday, of
the next month), not the month they describe. The lines were set before testing, from the 1990, 2000, 2008, 2020 and
2022 sequences (research, Oct 2026); they were not fitted.

Pure and network-free: series in, events out."""
from bisect import bisect_left
from datetime import date, timedelta

YEAR, HALF = 252, 126
CPI_LAG, SAHM_LAG = 14, 7           # days after the month ends: when each monthly figure is out

TYPES = {
    'Oil up 50% in a year': 'oil 50% or more above its level a year earlier',
    'Oil 40% under its high': 'oil 40% or more under its highest close of the last year',
    'Dollar up 10% in a year': 'the dollar index 10% or more above its level a year earlier',
    'Dollar down 10% in a year': 'the dollar index 10% or more below its level a year earlier',
    'Credit cracking': 'banks 10% and junk bonds 3% under their 1-year highs (the credit watch)',
    'Yield curve inverts': 'the 10-year yield under the 3-month rate, the first time in six months',
    'Yield curve un-inverts': 'the yield curve back to normal after three months or more inverted',
    'Inflation tops 4%': 'consumer prices 4% or more above a year earlier, the first time in a year',
    'Inflation turns down': 'inflation a full point under its peak of the last year, after a peak of 4% or more',
    'Recession signal': 'unemployment rising: the Sahm rule reaching 0.5',
}


def on_cal(cal, series, stale=5):
    """{date: value} on cal: the last value on or before each session, at most `stale` sessions old (else None)."""
    ks = sorted(series)
    out, j = [], -1
    for i, d in enumerate(cal):
        while j + 1 < len(ks) and ks[j + 1] <= d:
            j += 1
        out.append(series[ks[j]] if j >= 0 and bisect_left(cal, ks[j]) >= i - stale else None)
    return out


def pub_date(month, lag):
    """The day a monthly figure for `month` (YYYY-MM-01) is out: `lag` days into the next month."""
    y, m = int(month[:4]), int(month[5:7])
    return (date(y + (m == 12), m % 12 + 1, 1) + timedelta(days=lag - 1)).isoformat()


def published(monthly, lag):
    """{YYYY-MM-01: value} -> {date it was published: value}."""
    return {pub_date(d, lag): v for d, v in monthly.items()}


def yoy_monthly(monthly):
    out = {}
    for d, v in monthly.items():
        prev = f"{int(d[:4]) - 1}{d[4:]}"
        if prev in monthly and monthly[prev]:
            out[d] = v / monthly[prev] - 1
    return out


def _off_high(a, i, look=YEAR):
    w = [x for x in a[max(0, i - look + 1):i + 1] if x is not None]
    return a[i] / max(w) - 1 if a[i] is not None and len(w) >= look // 2 else None


def _ago(a, i, n=YEAR):
    return a[i] / a[i - n] - 1 if i >= n and a[i] is not None and a[i - n] else None


def _firsts(cond, cool):
    """Sessions where cond turns on, at most once per `cool` sessions."""
    out, last = [], -10 ** 9
    for i in range(1, len(cond)):
        if cond[i] and not cond[i - 1] and i - last >= cool:
            out.append(i)
            last = i
    return out


def _pct(x):
    return f"{x * 100:.0f}%"


def find(cal, ser, since):
    """[(date, 'Type: detail')] for every signal from `since` on, oldest first. ser: any of 'oil', 'dollar', 'banks',
    'junk', 'curve' ({date: value}, daily) and 'cpi' (index), 'sahm' ({YYYY-MM-01: value}, monthly). A series that is
    missing or short just yields no signals of its kind."""
    n = len(cal)
    if n < 2:
        return []
    got = []

    oil = on_cal(cal, ser.get('oil') or {})
    yo = [_ago(oil, i) for i in range(n)]
    for i in _firsts([x is not None and x >= 0.5 for x in yo], YEAR):
        got.append((i, f"Oil up 50% in a year: ${oil[i]:.0f} against ${oil[i - YEAR]:.0f} a year earlier"))
    oh = [_off_high(oil, i) for i in range(n)]
    for i in _firsts([x is not None and x <= -0.4 for x in oh], YEAR):
        got.append((i, f"Oil 40% under its high: ${oil[i]:.0f}, {_pct(-oh[i])} under its 1-year high"))

    usd = on_cal(cal, ser.get('dollar') or {})
    yd = [_ago(usd, i) for i in range(n)]
    for i in _firsts([x is not None and x >= 0.10 for x in yd], YEAR):
        got.append((i, f"Dollar up 10% in a year: up {_pct(yd[i])}"))
    for i in _firsts([x is not None and x <= -0.10 for x in yd], YEAR):
        got.append((i, f"Dollar down 10% in a year: down {_pct(-yd[i])}"))

    banks, junk = on_cal(cal, ser.get('banks') or {}), on_cal(cal, ser.get('junk') or {})
    bo, jo = [_off_high(banks, i) for i in range(n)], [_off_high(junk, i) for i in range(n)]
    crack = [b is not None and j is not None and b <= -0.10 and j <= -0.03 for b, j in zip(bo, jo)]
    for i in _firsts(crack, HALF):
        got.append((i, f"Credit cracking: banks {_pct(-bo[i])} and junk bonds {_pct(-jo[i])} under their 1-year highs"))

    curve = on_cal(cal, ser.get('curve') or {})
    inv = [c is not None and c < 0 for c in curve]
    for i in _firsts(inv, YEAR):
        if not any(inv[max(0, i - HALF):i]) and i >= HALF:
            got.append((i, f"Yield curve inverts: the 10-year yield {abs(curve[i]):.2f} points under the 3-month rate"))
    back = [i >= 5 and all(c is not None and c > 0 for c in curve[i - 4:i + 1]) and sum(inv[max(0, i - 5 - HALF):i - 5]) >= 63
            for i in range(n)]
    for i in _firsts(back, YEAR):
        got.append((i, f"Yield curve un-inverts: the 10-year yield back {curve[i]:.2f} points over the 3-month rate"))

    cpi_y = yoy_monthly(ser.get('cpi') or {})
    infl = on_cal(cal, published(cpi_y, CPI_LAG), stale=40)
    which = on_cal(cal, {pub_date(m, CPI_LAG): m for m in cpi_y}, stale=40)    # the month each reading describes
    hi = [x is not None and x >= 0.04 for x in infl]
    for i in _firsts(hi, YEAR):
        if not any(hi[max(0, i - YEAR):i]) and i >= YEAR:
            got.append((i, f"Inflation tops 4%: {infl[i] * 100:.1f}% in {date.fromisoformat(which[i]).strftime('%B %Y')}"))
    peak = [max((x for x in infl[max(0, i - YEAR):i + 1] if x is not None), default=None) for i in range(n)]
    turn = [x is not None and p is not None and p >= 0.04 and x <= p - 0.01 for x, p in zip(infl, peak)]
    for i in _firsts(turn, YEAR):
        got.append((i, f"Inflation turns down: {infl[i] * 100:.1f}% from a peak of {peak[i] * 100:.1f}%"))

    sahm = on_cal(cal, published(ser.get('sahm') or {}, SAHM_LAG), stale=40)
    for i in _firsts([x is not None and x >= 0.5 for x in sahm], YEAR):
        got.append((i, f"Recession signal: unemployment rising (the Sahm rule at {sahm[i]:.2f})"))

    k0 = bisect_left(cal, since)
    return sorted((cal[i], w) for i, w in got if i >= k0)

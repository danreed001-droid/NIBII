"""Credit watch (information only): banks and junk bonds cracking before the S&P 500.

In 2007 banks (XLF) and junk bonds (VWEHX, Vanguard's high-yield bond fund) topped in June, four months before the
S&P 500's October peak; in 2000-2002 they also fell before the market's second leg down. The watch reads both against
their highest close of the last year. It is on when banks are 10%+ under that high and junk bonds 3%+ under theirs,
and goes off when either recovers to within half of that (5% / 1.5%). The early read is the same at 7% / 2% (off at
3.5% / 1%) but can only switch on while SPY is still within 5% of its own high: the case where they crack first.

It changes nothing the plan does. Tested as rules on the default plan (Oct 26, 2026, the plan's own schedule replayed:
45.8% a year from 2000, worst drop -29%): out of stocks into the haven while the watch is on made 32.0% (worst drop
-42%); 33.5% at 15% / 5%; 32.5% when a new 1- or 3-month SPY high also ends it; the early read alone 41.5%. The early
read came on Jul 24, 2007, but the plan's energy and materials stocks kept rising into mid-2008, credit heals slowly
(the watch stayed on through the 2009 and 2020 rebounds) and it also fires in 2001, 2011, 2016 and 2022 (rate rises,
not a crisis).

Pure and network-free."""

BANKS, JUNK = 'XLF', 'VWEHX'
LOOK = 252                                   # sessions: the 1-year high
MAIN = dict(banks=0.10, junk=0.03)           # on at these falls from the high; off at half
EARLY = dict(banks=0.07, junk=0.02)
SPY_NEAR = 0.05                              # the early read starts only while SPY is this close to its high


def _off_high(px, i, look=LOOK):
    lo = max(0, i - look + 1)
    return px[i] / max(px[lo:i + 1]) - 1


def _spells(on, dates):
    out, start = [], None
    for j, v in enumerate(on):
        if v and start is None:
            start = j
        if not v and start is not None:
            out.append([dates[start], dates[j - 1]])
            start = None
    if start is not None:
        out.append([dates[start], None])
    return out


def _run(b_off, j_off, s_off, banks, junk, early):
    """The watch state at each date: on when both are far enough under their highs (and, early, SPY near its high),
    off when either recovers to within half."""
    on, state = [], False
    for ob, oj, os_ in zip(b_off, j_off, s_off):
        if ob is None:
            on.append(False)
            continue
        if not state:
            state = ob <= -banks and oj <= -junk and (not early or os_ >= -SPY_NEAR)
        elif ob > -banks / 2 or oj > -junk / 2:
            state = False
        on.append(state)
    return on


def watch(banks, junk, spy, look=LOOK):
    """The watch read at the last date the three share. banks, junk, spy: {date: close} (dividends in).
    Returns None without a year of common history."""
    dates = sorted(set(banks) & set(junk) & set(spy))
    if len(dates) <= look:
        return None
    B, J, S = ([px[d] for d in dates] for px in (banks, junk, spy))
    b_off = [None if i < look - 1 else _off_high(B, i, look) for i in range(len(dates))]
    j_off = [None if i < look - 1 else _off_high(J, i, look) for i in range(len(dates))]
    s_off = [None if i < look - 1 else _off_high(S, i, look) for i in range(len(dates))]
    main = _run(b_off, j_off, s_off, MAIN['banks'], MAIN['junk'], early=False)
    early = _run(b_off, j_off, s_off, EARLY['banks'], EARLY['junk'], early=True)
    sp_main, sp_early = _spells(main, dates), _spells(early, dates)
    r4 = lambda x: round(x, 4)
    counted = [v for v, o in zip(main, b_off) if o is not None]
    return dict(asOf=dates[-1], banks=r4(b_off[-1]), junk=r4(j_off[-1]), spy=r4(s_off[-1]),
                on=main[-1], prevOn=main[-2], early=early[-1], prevEarly=early[-2],
                since=sp_main[-1][0] if main[-1] else None, earlySince=sp_early[-1][0] if early[-1] else None,
                spells=sp_main[-8:], earlySpells=sp_early[-8:], daysOn=sum(counted), days=len(counted),
                main=MAIN, earlyAt=EARLY, spyNear=SPY_NEAR, tickers=[BANKS, JUNK])

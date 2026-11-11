# Human review picks

Your own year-by-year calls, made by reviewing each year's SPY, TLT, gold and DBMF charts (trend channels, swing highs and lows, money flow) in the Calls & Channels Lab. Saved here so they can be revisited, extended or re-tested later. Research only: nothing here changes the live plan.

`picks.json` holds:

- `calls`: every call, by date, with what to hold and why (106 calls over 26 years as of 2026-11-11).
- `meaning`: how the calls are read in a test. A stocks call hands control back to the plan from that date; TLT, gold, DBMF, cash or half DBMF takes you out of stocks into that holding until your next call. A year's calls run from its first call to that year's last trading day, and the plan decides everything outside them. Calls are decided at that day's close and traded at the next close. If a date has two entries, the later one wins (the three replaced entries are listed).
- `result`: the strict test (S&P members as of each date, 0.15% a trade) from 2000, before tax, against the plan, with every year's return side by side.

As of 2026-11-11: 63.7% a year (worst drop -24.9%, Sharpe 1.77) against the plan's 60.4% (-25.2%, 1.59). The calls were made looking back at charts, with hindsight, so treat the edge with care; the fair test is how the same kind of reading does on years not yet marked, or going forward.

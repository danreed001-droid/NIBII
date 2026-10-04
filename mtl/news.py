"""News-gap boost: a stock that gapped up big on news (usually earnings)
jumps the top-5 queue for a few weeks.

A news gap is a session that opened `th` or more above the previous close,
also CLOSED `th` or more up, and closed in the upper part of its range
(`min_where` of the way from low to high) - the move held all day. Found in
2000-2026 backtests (scripts/backtest_addons.py --robust): with th=12% and a
4-week window, letting such a stock replace the weakest holding added about
6%/yr over the plain top 5, and random fake flags made it worse. Pure and
network-free.
"""
NEWS_GAP, NEWS_WINDOW, NEWS_WHERE = 0.12, 21, 0.6


def news_gap_days(bars, th=NEWS_GAP, min_where=NEWS_WHERE):
    """bars: [(date, open, high, low, close)] oldest first -> [date, ...] of news gaps."""
    out = []
    for j in range(1, len(bars)):
        d, o, h, lo, c = bars[j][:5]
        pc = bars[j - 1][4]
        if not pc or h <= lo:
            continue
        if o / pc - 1 >= th and c / pc - 1 >= th and (c - lo) / (h - lo) >= min_where:
            out.append(d[:10])
    return out


def booster(gap_days, calendar, window=NEWS_WINDOW):
    """gap_days: {ticker: [date, ...]} -> prefer(ticker, k): True while a news gap is
    within the last `window` sessions up to calendar[k] (run_momentum's `prefer`)."""
    pos = {d: i for i, d in enumerate(calendar)}
    idx = {t: sorted(pos[d] for d in ds if d in pos) for t, ds in gap_days.items()}

    def prefer(t, k):
        return any(k - window < i <= k for i in idx.get(t, ()))
    return prefer


def recent_gaps(gap_days, calendar, k, window=NEWS_WINDOW):
    """{ticker: last news-gap date} for gaps within the last `window` sessions up to calendar[k]."""
    lo = calendar[max(0, k - window + 1)]
    hi = calendar[k]
    out = {}
    for t, ds in gap_days.items():
        hits = [d for d in ds if lo <= d <= hi]
        if hits:
            out[t] = max(hits)
    return out

"""Speculator crowding gauge (information only): how heavily hedge funds and other speculators lean one way in futures.

Source: the CFTC's weekly Commitments of Traders report (legacy, futures only), positions as of each Tuesday, published
the Friday after. For each market the gauge takes the speculators' ("non-commercial") net long position as a share of
all open contracts, then places this week's reading in its own range of the last 156 weeks (3 years): 100% = the most
crowded long in 3 years, 0% = the most crowded short. Top or bottom 10% of that range counts as crowded.

It changes nothing the plan does. Audit (Oct 27, 2026, every weekly reading since 1989, chance of a 10%+ fall within
2 months of the report): gold 6.8% when most crowded long against 5.1% normally, silver 21.6% vs 18.3%, copper 14.1%
vs 14.8%, crude oil 17.5% vs 28.4%, S&P 500 futures 25.9% vs 10.7% (58 weeks, few separate episodes), Nasdaq-100
futures 2.5% vs 12.9%. It missed the May-June 2006 metals crash (gold at 72% of its range, silver falling and copper
speculators net short: much of that money came through new metal ETFs and index funds, which this report does not count
as speculators) and the April 2013 gold and April 2011 silver crashes, but was high before gold's 2008 and 2020 tops.
A heads-up on positioning, not a timing signal.

Pure except fetch_years (network)."""
import csv
import io
import zipfile

MARKETS = {   # CFTC contract market code -> name shown
    '088691': 'Gold', '084691': 'Silver', '085692': 'Copper', '067651': 'Crude oil',
    '043602': '10-yr Treasury', '020601': '30-yr Treasury',
    '13874A': 'S&P 500 futures', '209742': 'Nasdaq-100 futures',
}
WINDOW = 156          # weeks: the 3-year range a reading is placed in
CROWDED = 0.9         # top 10% of the range = crowded long; bottom 10% = crowded short
HIST = 26             # weeks of history kept for the page's sparkline
URL = 'https://www.cftc.gov/files/dea/history/deacot{year}.zip'


def parse(zip_bytes, markets=MARKETS):
    """{name: {date: (net long share of open interest, open interest)}} from one CFTC legacy futures-only zip."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for n in zf.namelist():
            rd = csv.reader(io.StringIO(zf.read(n).decode('latin-1')))
            hdr = {h.strip(): i for i, h in enumerate(next(rd))}
            ic, idt = hdr['CFTC Contract Market Code'], hdr['As of Date in Form YYYY-MM-DD']
            ioi, il, ish = hdr['Open Interest (All)'], hdr['Noncommercial Positions-Long (All)'], hdr['Noncommercial Positions-Short (All)']
            for row in rd:
                name = markets.get(row[ic].strip())
                if not name:
                    continue
                oi = float(row[ioi].strip() or 0)
                if oi > 0:
                    out.setdefault(name, {})[row[idt].strip()] = ((float(row[il].strip() or 0) - float(row[ish].strip() or 0)) / oi, oi)
    return out


def merge(parts):
    """Merge several parse() results (one per year file)."""
    out = {}
    for p in parts:
        for k, v in p.items():
            out.setdefault(k, {}).update(v)
    return out


def reading(series, window=WINDOW, crowded=CROWDED, hist=HIST):
    """One market's gauge from {date: (net share, open interest)}, or None with under a full window of weeks:
    dict(date, net, pct (0-1 place in the 3-year range), prev (last week's pct), lo, hi, flag ('long'/'short'/None),
    hist=[[date, pct]...] for the last `hist` weeks)."""
    ds = sorted(series)
    if len(ds) <= window:
        return None
    nets = [series[d][0] for d in ds]

    def pct(i):
        w = nets[i - window:i + 1]
        lo, hi = min(w), max(w)
        return (nets[i] - lo) / (hi - lo) if hi > lo else 0.5
    i = len(ds) - 1
    p = pct(i)
    w = nets[i - window:i + 1]
    return dict(date=ds[i], net=round(nets[i], 4), pct=round(p, 3), prev=round(pct(i - 1), 3) if i - 1 >= window else None,
                lo=round(min(w), 4), hi=round(max(w), 4),
                flag='long' if p >= crowded else 'short' if p <= 1 - crowded else None,
                hist=[[ds[k], round(pct(k), 3)] for k in range(max(window, i - hist + 1), i + 1)])


def gauge(merged, markets=MARKETS):
    """The page block: rows in MARKETS order (markets without enough history left out), the report date."""
    rows = []
    for name in markets.values():
        r = reading(merged.get(name) or {})
        if r:
            rows.append(dict(name=name, **r))
    return dict(rows=rows, asOf=max((r['date'] for r in rows), default=None), window=WINDOW, crowded=CROWDED) if rows else None


def fetch_years(years, timeout=60):
    """Download and merge the CFTC yearly files (network). The current year's file is refreshed weekly by the CFTC."""
    import urllib.request
    parts = []
    for y in years:
        req = urllib.request.Request(URL.format(year=y), headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            parts.append(parse(resp.read()))
    return merge(parts)

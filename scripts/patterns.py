#!/usr/bin/env python3
"""Cross-reference dated news catalysts against the Ledger's own settled moves.

Reads data/news_log.json (a local cache of the "Daily market news log"
Artifact database - dated, ticker-tagged, sourced market-moving events) and
documents/*.json (the Ledger's own published boards). For every horizon that
has actually settled - a real, exactly-computed realized return from
scripts/settle.py, never a number parsed out of the news log's own free-text
"numbers" field - it looks at which catalyst categories were live in the
window between the call and its maturity, and tabulates how often each
category's tagged direction matched the realized outcome.

This deliberately does NOT parse percentages or prices out of the news log's
prose; that free text is for a human/model to read, not for this script to
scrape. The only numbers this script trusts are the Ledger's own exact
closes and returns.

Every asset/category cell is reported with its sample size, and any cell
below MIN_SAMPLES is marked too thin to mean anything - never hidden, since
"no reliable answer yet" is itself the honest answer while the Ledger and
the news log are both still young. The report renderer should not display a
rate from a cell below MIN_SAMPLES as a real finding.

Usage:
    python scripts/patterns.py
"""
import glob
import json
import os
import sys

MIN_SAMPLES = 15

ASSET_MATCH = {
    'equities': ['SPY', 'DIA', '^GSPC', 'S&P 500', 'S&P'],
    'bonds': ['TLT', 'SHY', 'US30Y', '10Y', '30Y', '2Y', 'yield', 'Treasury'],
    'gold': ['GLD', 'gold', 'XAU'],
    'dollar': ['DXY', 'DX-Y', 'USD', 'dollar'],
    'iwm': ['IWM', 'Russell'],
    'qqq': ['QQQ', 'Nasdaq', 'SMH'],
}

DIRECTION_TO_OUTCOME = {'Bullish': 'bullish', 'Bearish': 'bearish'}


def load_news_log(path):
    return json.load(open(path))


def load_settled_horizons(documents_dir):
    """[(asset_key, doc_date, maturity_date, realized_outcome), ...] for
    every horizon that has actually settled (maturityClose is not None)."""
    out = []
    for path in sorted(glob.glob(os.path.join(documents_dir, "*.json"))):
        doc = json.load(open(path))
        for a in doc['assets']:
            for h in a['horizons']:
                if h.get('maturityClose') is None:
                    continue
                ret = h['ret']
                outcome = 'bullish' if ret > h['band'] else ('bearish' if ret < -h['band'] else 'flat')
                out.append((a['key'], doc['date'], h['maturity'], outcome))
    return out


def catalysts_in_window(news_log, asset_key, start, end):
    keywords = [k.lower() for k in ASSET_MATCH[asset_key]]
    hits = []
    for entry in news_log:
        d = entry['data']
        if not (start <= d['date'] <= end):
            continue
        haystack = ' '.join((d.get('tickers', ''), d.get('event', ''), d.get('numbers', ''))).lower()
        if any(k in haystack for k in keywords):
            hits.append(d)
    return hits


def analyze(news_log, settled):
    """{asset_key: {category: {'n': int, 'agree': int, 'rate': float|None}}}"""
    table = {}
    for asset_key, doc_date, maturity, outcome in settled:
        for cat in catalysts_in_window(news_log, asset_key, doc_date, maturity):
            expected = DIRECTION_TO_OUTCOME.get(cat['direction'])
            if expected is None:  # Mixed/Neutral catalysts don't predict a side
                continue
            cell = table.setdefault(asset_key, {}).setdefault(
                cat['category'], {'n': 0, 'agree': 0})
            cell['n'] += 1
            cell['agree'] += int(expected == outcome)

    for asset in table.values():
        for cell in asset.values():
            cell['rate'] = round(cell['agree'] / cell['n'], 3) if cell['n'] >= MIN_SAMPLES else None
            cell['reliable'] = cell['n'] >= MIN_SAMPLES
    return table


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    news_log = load_news_log(os.path.join(root, "data", "news_log.json"))
    settled = load_settled_horizons(os.path.join(root, "documents"))

    if not settled:
        print("no settled horizons yet - the Ledger hasn't matured any calls, "
              "so there's nothing real to correlate against. Run scripts/settle.py "
              "once calls start maturing.")
        return

    table = analyze(news_log, settled)
    out_path = os.path.join(root, "data", "patterns.json")
    with open(out_path, "w") as f:
        json.dump({"minSamples": MIN_SAMPLES, "settledHorizons": len(settled),
                    "byAsset": table}, f, indent=1)
        f.write("\n")

    print(f"{len(settled)} settled horizons analyzed. wrote {out_path}")
    reliable = sum(1 for a in table.values() for c in a.values() if c['reliable'])
    print(f"{reliable} asset/category cells reached {MIN_SAMPLES}+ samples "
          f"({sum(len(a) for a in table.values()) - reliable} still too thin to report)")


if __name__ == "__main__":
    main()

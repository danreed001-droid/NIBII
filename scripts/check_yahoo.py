"""Does the Yahoo download library (yfinance) still work? A two-ticker download before the nightly scan.

    python scripts/check_yahoo.py      # exit 0 and print the version when it works, 1 when it doesn't

The scanner workflow runs it first: when tonight's newest yfinance can't download, it goes back to the last version
that did (saved next to the price copy) and checks again. If Yahoo itself is down, the scan still runs on the
backup prices (mtl/backup_prices.py).
"""
import sys


def main():
    try:
        import yfinance as yf
        df = yf.download(['SPY', 'AAPL'], period='1mo', interval='1d', group_by='ticker', progress=False, threads=False)
        n = min(int(df[t]['Close'].notna().sum()) for t in ('SPY', 'AAPL'))
    except Exception as e:   # noqa: BLE001
        print(f"yfinance check failed: {e}", file=sys.stderr)
        return 1
    if n < 5:
        print(f"yfinance check failed: only {n} closes for the last month", file=sys.stderr)
        return 1
    print(yf.__version__)
    return 0


if __name__ == '__main__':
    sys.exit(main())

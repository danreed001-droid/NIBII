"""Compare a rebuilt data/track_record.json with the published one; exit 1 when the default plan moved too much.

usage: python research/backtest/compare_track.py <published.json> <rebuilt.json>

A refresh adds a few months and redownloads every price, so a few tenths of a point of drift is normal. A move of more
than MAX_ANNUAL in the default plan's return a year, or MAX_DD in its worst drop, means the data or the engine changed:
look before publishing."""
import json
import sys

MAX_ANNUAL, MAX_DD = 0.03, 0.05


def main(old_path, new_path):
    old, new = json.load(open(old_path)), json.load(open(new_path))
    print(f"backtest through {old['end']} -> {new['end']}")
    for k, n in new['stats'].items():
        o = old['stats'].get(k, {})
        print(f"{k:9} {o.get('annual', 0) * 100:5.1f}% -> {n['annual'] * 100:5.1f}% a year, "
              f"worst drop {o.get('maxDD', 0) * 100:4.0f}% -> {n['maxDD'] * 100:4.0f}%")
    o, n = old['stats']['rotation'], new['stats']['rotation']
    bad = []
    if new['end'] < old['end']:
        bad.append('it ends earlier than the published one')
    if abs(n['annual'] - o['annual']) > MAX_ANNUAL:
        bad.append(f"the default's return a year moved {(n['annual'] - o['annual']) * 100:+.1f} points")
    if abs(n['maxDD'] - o['maxDD']) > MAX_DD:
        bad.append(f"the default's worst drop moved {(n['maxDD'] - o['maxDD']) * 100:+.1f} points")
    if bad:
        print('Not publishing: ' + '; '.join(bad) + '.')
        sys.exit(1)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

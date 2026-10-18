"""Is the backtest engine (overlay/) in step with the live rules? engine_sync.json holds the live rules' fingerprint
(mtl/paper.py) from the last time overlay/scripts/improve.py was matched to them. A different fingerprint now means
a live rule changed since, so the refreshed track record may not be the live plan's: this exits 1 and the
workflow opens an issue (it still publishes). After syncing the overlay, put the new fingerprint in the file:
    python research/backtest/check_sync.py --update"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from mtl import paper  # noqa: E402

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine_sync.json')


def main(argv):
    fp, _ = paper.fingerprint(ROOT)
    if '--update' in argv:
        with open(PATH, 'w') as fh:
            json.dump(dict(fingerprint=fp, note='live rules fingerprint the overlay engine was last synced to'), fh, indent=1)
            fh.write('\n')
        print(f"engine synced to {fp}")
        return 0
    with open(PATH) as fh:
        synced = json.load(fh)['fingerprint']
    if synced != fp:
        print(f"The live rules ({fp}) changed since the backtest engine was last synced ({synced}): update "
              f"research/backtest/overlay/scripts/improve.py to match, then run check_sync.py --update.")
        return 1
    print(f"ok: engine in step with the live rules ({fp})")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

"""Swap the "Today's story" card on docs/scanner.html for a fresh one from data/story_log.json, using the scan data
already embedded in the page, so a new story shows without re-running the scan (.github/workflows/story.yml).
Information only. On a page from before the card it is put under the banner; exits non-zero only when the page has no scan data."""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import render_scanner as rs  # noqa: E402

MARK = re.compile(r'<!--story-->.*?<!--/story-->', re.S)


def refresh(page):
    m = re.search(r'<script type="application/json" id="scan-data">(.*?)</script>', page, re.S)
    if not m:
        return None
    scan = json.loads(m.group(1).replace('<\\/', '</'))
    card = rs.story_html(scan)
    if MARK.search(page):
        return MARK.sub(lambda _: card, page, count=1)
    anchor = '<div class="banner" id="banner"></div>'   # a page from before the card: put it under the banner
    if anchor not in page:
        return None
    return page.replace(anchor, anchor + '\n' + card, 1)


def main():
    with open(rs.OUT_PATH) as f:
        page = f.read()
    new = refresh(page)
    if new is None:
        sys.exit('docs/scanner.html has no scan data to build the story card from')
    if new != page:
        with open(rs.OUT_PATH, 'w') as f:
            f.write(new)
        print('updated the story card on docs/scanner.html')
    else:
        print('story card unchanged')


if __name__ == '__main__':
    main()

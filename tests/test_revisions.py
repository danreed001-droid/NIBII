import json

import pandas as pd

from mtl.revisions import log_revisions, revision


def test_revision_reads_trend_and_counts():
    trend = pd.DataFrame({'current': [2.0, 3.0], '90daysAgo': [1.6, 3.3]}, index=['0y', '+1y'])
    revs = pd.DataFrame({'upLast30days': [5, 2], 'downLast30days': [1, 3]}, index=['0y', '+1y'])
    r = revision(trend, revs)
    assert r == {'eps': 2.0, 'eps90': 0.25, 'up30': 7, 'down30': 4}
    # a loss narrowing (-1.0 -> -0.5) reads as an upgrade
    assert revision(pd.DataFrame({'current': [-0.5], '90daysAgo': [-1.0]}, index=['0y']), None)['eps90'] == 0.5


def test_revision_missing_data_is_none():
    assert revision(pd.DataFrame(), pd.DataFrame()) is None


def test_log_keeps_one_entry_per_date(tmp_path):
    p = str(tmp_path / 'log.json')
    log_revisions(p, '2026-10-09', {'MU': {'eps90': 0.1}}, {'MU': 3})
    log_revisions(p, '2026-10-09', {'MU': {'eps90': 0.2}}, {'MU': 2})
    log_revisions(p, '2026-10-16', {'AMD': {'eps90': -0.05}}, {'AMD': 7})
    log = json.load(open(p))
    assert log['2026-10-09'] == {'MU': {'eps90': 0.2, 'rank': 2}} and log['2026-10-16']['AMD']['rank'] == 7

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_scanner_fresh as C  # noqa: E402

NY = ZoneInfo('America/New_York')


def _run(mode, now, last, tmp_path, monkeypatch):
    monkeypatch.setattr(C, 'last_logged', lambda: last)
    out = tmp_path / 'out'
    out.unlink(missing_ok=True)
    monkeypatch.setenv('GITHUB_OUTPUT', str(out))
    C.main(mode, now=now)
    return out.read_text().strip()


def test_kick_waits_for_6pm_then_starts_a_missing_run(tmp_path, monkeypatch):
    tue = '2026-11-03'
    assert _run('kick', datetime(2026, 11, 3, 17, 30, tzinfo=NY), '2026-11-02', tmp_path, monkeypatch) == 'run=false'
    assert _run('kick', datetime(2026, 11, 3, 18, 5, tzinfo=NY), '2026-11-02', tmp_path, monkeypatch) == 'run=true'
    assert _run('kick', datetime(2026, 11, 3, 18, 5, tzinfo=NY), tue, tmp_path, monkeypatch) == 'run=false'


def test_kick_after_midnight_still_starts_last_nights_missing_run(tmp_path, monkeypatch):
    assert _run('kick', datetime(2026, 11, 4, 1, 0, tzinfo=NY), '2026-11-02', tmp_path, monkeypatch) == 'run=true'
    assert _run('kick', datetime(2026, 11, 4, 1, 0, tzinfo=NY), '2026-11-03', tmp_path, monkeypatch) == 'run=false'

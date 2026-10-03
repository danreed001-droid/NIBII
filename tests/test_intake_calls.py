"""Calls intake from a GitHub issue body - validation and merge."""
import importlib.util
import os

spec = importlib.util.spec_from_file_location('intake_calls', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'intake_calls.py'))
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)

BODY = '''Calls submitted from the dashboard.

```json
{"calls": {"2026-10-02": {"m": "custom", "s": 90, "v": 30, "swaps": [["DELL", "HUM"], ["X", "bad ticker"]],
  "drops": ["AMD", "$(rm -rf)"], "note": "trim", "at": "2026-10-03T20:00:00.000Z"},
  "not-a-date": {"m": "auto"}, "2026-09-25": {"m": "hack"}, "2026-09-18": {"m": "del", "at": "2026-10-03T19:00:00Z"}}}
```
'''


def test_parse_keeps_only_valid_fields():
    calls = intake.parse(BODY)
    assert set(calls) == {'2026-10-02', '2026-09-18'}
    c = calls['2026-10-02']
    assert (c['s'], c['v'], c['c']) == (90, 10, 0)          # sleeve capped at what's left
    assert c['swaps'] == [['DELL', 'HUM']] and c['drops'] == ['AMD']
    assert intake.parse('no block here') == {} and intake.parse('```json\n{oops}\n```') == {}


def test_merge_newest_wins():
    cur = {'2026-10-02': {'m': 'auto', 'note': '', 'at': '2026-10-03T21:00:00Z'}}
    merged, changed = intake.merge(cur, intake.parse(BODY))
    assert merged['2026-10-02']['m'] == 'auto'               # the repo copy is newer
    assert changed == ['2026-09-18']

"""research/backtest/compare_track.py stops a refresh whose default plan moved too much."""
import importlib.util
import json
import os

import pytest

spec = importlib.util.spec_from_file_location(
    'compare_track', os.path.join(os.path.dirname(__file__), '..', 'research', 'backtest', 'compare_track.py'))
compare_track = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_track)


def track(tmp_path, name, end, annual, dd):
    p = tmp_path / name
    p.write_text(json.dumps(dict(end=end, stats=dict(rotation=dict(annual=annual, maxDD=dd), SPY=dict(annual=0.08, maxDD=-0.55)))))
    return str(p)


def test_small_drift_passes(tmp_path):
    compare_track.main(track(tmp_path, 'a', '2026-10-13', 0.369, -0.31), track(tmp_path, 'b', '2027-01-04', 0.372, -0.31))


@pytest.mark.parametrize('end,annual,dd', [('2027-01-04', 0.41, -0.31), ('2027-01-04', 0.369, -0.37), ('2026-09-30', 0.369, -0.31)])
def test_a_big_move_or_an_older_end_stops_it(tmp_path, end, annual, dd):
    with pytest.raises(SystemExit):
        compare_track.main(track(tmp_path, 'a', '2026-10-13', 0.369, -0.31), track(tmp_path, 'b', end, annual, dd))

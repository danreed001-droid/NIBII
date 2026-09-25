"""mtl.documents.iter_document_paths - the fix for a bug that hit three
scripts independently (settle.py, patterns.py, run_verify.py) before this
was centralized: documents/live.json (scripts/fetch_live.py's snapshot)
has no 'assets' key, so any bare glob.glob("documents/*.json") that reads
it as a ledger document crashes with KeyError('assets')."""
import json
import os

from mtl.documents import iter_document_paths


def test_excludes_live_json(tmp_path):
    (tmp_path / "2026-09-24.json").write_text(json.dumps({"date": "2026-09-24"}))
    (tmp_path / "2026-09-25.json").write_text(json.dumps({"date": "2026-09-25"}))
    (tmp_path / "live.json").write_text(json.dumps({"fetchedAt": "x", "prices": {}}))

    paths = iter_document_paths(str(tmp_path))

    assert len(paths) == 2
    assert all(os.path.basename(p) != "live.json" for p in paths)
    assert [os.path.basename(p) for p in paths] == ["2026-09-24.json", "2026-09-25.json"]


def test_empty_directory_returns_empty_list(tmp_path):
    assert iter_document_paths(str(tmp_path)) == []


def test_only_live_json_present_returns_empty_list(tmp_path):
    (tmp_path / "live.json").write_text(json.dumps({"fetchedAt": "x", "prices": {}}))
    assert iter_document_paths(str(tmp_path)) == []


def test_every_returned_path_is_actually_loadable_as_a_document(tmp_path):
    # the regression this exists for: every path this returns must be safe
    # to json.load() and index ['assets'] on without KeyError
    (tmp_path / "2026-09-24.json").write_text(json.dumps({"date": "2026-09-24", "assets": []}))
    (tmp_path / "live.json").write_text(json.dumps({"fetchedAt": "x", "prices": {}}))

    for p in iter_document_paths(str(tmp_path)):
        doc = json.load(open(p))
        assert "assets" in doc  # would KeyError downstream if live.json leaked through

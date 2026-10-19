"""Every inline script on the published pages must parse: one stray quote in a long sentence stops the whole page."""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..')
NODE = shutil.which('node')
SCRIPT = re.compile(r'<script(?![^>]*application/json)[^>]*>(.*?)</script>', re.S)


def _check(html):
    bad = []
    for i, body in enumerate(SCRIPT.findall(html)):
        if not body.strip():
            continue
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as fh:
            fh.write(body)
        r = subprocess.run([NODE, '--check', fh.name], capture_output=True, text=True)
        os.unlink(fh.name)
        if r.returncode:
            bad.append((i, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'error'))
    return bad


@pytest.mark.skipif(NODE is None, reason='node is not installed')
@pytest.mark.parametrize('page', ['scanner.html', 'backtest.html', 'index.html', 'events.html'])
def test_published_page_scripts_parse(page):
    path = os.path.join(ROOT, 'docs', page)
    if not os.path.exists(path):
        pytest.skip(f'{page} not built')
    assert _check(open(path).read()) == []


@pytest.mark.skipif(NODE is None, reason='node is not installed')
def test_rendered_scanner_scripts_parse():
    import importlib.util
    spec = importlib.util.spec_from_file_location('render_scanner', os.path.join(ROOT, 'scripts', 'render_scanner.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    scan = dict(generatedAt='2026-10-03T03:22:15+00:00', asOf='2026-10-02', holdings=[], table=[], trades=[], curves={}, years={}, stats={})
    assert _check(mod.render(scan)) == []

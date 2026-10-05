"""Prevent mismatched Android, Python, macOS and release tag versions."""
import json
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def check():
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'\d+\.\d+\.\d+', version), 'VERSION must contain a semantic version'
    assert (ROOT / 'desktop/gpx2elev/assets/version.txt').read_text().strip() == version
    gradle = (ROOT / 'app/build.gradle.kts').read_text()
    assert 'versionName = rootProject.file("VERSION").readText().trim()' in gradle
    assert 'applicationId = "com.nico.gpx2elev"' in gradle
    metadata = tomllib.loads((ROOT / 'desktop/pyproject.toml').read_text())
    assert metadata['tool']['setuptools']['dynamic']['version']['attr'] == 'gpx2elev.__version__'
    spec = (ROOT / 'desktop/bundle.spec').read_text()
    assert 'version=(root.parent / "VERSION").read_text().strip()' in spec
    ref = os.environ.get('GITHUB_REF', '')
    if ref.startswith('refs/tags/'):
        assert ref.removeprefix('refs/tags/') == 'v' + version, 'Tag and VERSION differ'
    print(json.dumps({'version': version, 'android': version, 'desktop': version, 'macos': version}))
    return version


if __name__ == '__main__':
    check()

"""Shared path anchors for the test suite.

Tests previously hardcoded directory depth (parent.parent, .parents[2]),
which breaks the moment a test moves a level deeper - and the scanners
package does exactly that. Anchor on a marker file instead.
"""
from pathlib import Path
import pytest


def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".claude-plugin" / "plugin.json").is_file():
            return p
    raise RuntimeError("plugin root not found above %s" % start)


@pytest.fixture(scope="session")
def plugin_root() -> Path:
    return _find_root(Path(__file__).resolve())


@pytest.fixture(scope="session")
def scripts_dir(plugin_root: Path) -> Path:
    return plugin_root / "scripts"


@pytest.fixture(scope="session")
def fixture():
    base = Path(__file__).resolve().parent / "fixtures"
    def _get(name: str) -> Path:
        return base / name
    return _get

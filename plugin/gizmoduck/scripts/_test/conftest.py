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
    raise RuntimeError(f"plugin root not found above {start}")


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


@pytest.fixture
def scratch_nuclei_home(tmp_path, monkeypatch):
    """Point every place Nuclei looks for a config.yaml at a scratch tree, so
    the operator's own ~/.config/nuclei/config.yaml never decides a result.
    Returns the HOME used; nothing is created under it."""
    home = tmp_path / "scratch-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("NUCLEI_CONFIG_DIR", raising=False)
    return home


@pytest.fixture(autouse=True)
def _isolate_tool_lookup(tmp_path_factory, monkeypatch):
    """No test reads the operator's real tool home or lookup overrides
    (L-0684). scanners.base.which looks in the tool home's bin ahead of PATH,
    so a developer with a populated ~/.local/share/gizmoduck would otherwise
    see real tools from inside a test. GIZMODUCK_HOME points at an empty
    directory; the per-tool overrides and XDG_DATA_HOME are removed."""
    monkeypatch.setenv("GIZMODUCK_HOME", str(tmp_path_factory.mktemp("empty-tool-home")))
    for var in ("GIZMODUCK_ZAP_HOME", "GIZMODUCK_NIKTO_PL", "GIZMODUCK_TESTSSL_SH",
                "XDG_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)

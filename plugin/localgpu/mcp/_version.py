"""Single source of truth for localgpu's version: pyproject.toml.

Both mcp/server.py and cli/localgpu_cli.py need a version string, and
hardcoding it in each of them is exactly the drift that shipped: two
Python literals that nothing kept in sync with plugin.json or
marketplace.json, so `localgpu --version` reported 0.1.0 while the
manifests had moved on to 0.1.4. Read pyproject.toml instead of
duplicating the literal.

Deliberately NOT ``importlib.metadata.version("localgpu")``: this package
is installed editable, and an editable install's dist-info is a snapshot
written at `pip install -e` time. Editing pyproject.toml does not refresh
it - confirmed on this machine, where the installed dist-info still says
0.1.0 while pyproject.toml already says 0.1.4. Metadata lookup would just
relocate the drift bug, not close it. Reading the file directly means a
source edit takes effect immediately, same as every other module here
under the editable install - no reinstall required.

Lives in mcp/ (not the plugin root) because both callers already put
mcp/ on sys.path to reach their other flat siblings (config, ollama,
indexer for the server; those same modules again for the CLI, via its
own sys.path.insert onto this directory) - so `from _version import
VERSION` resolves for both without a new sys.path entry.
"""

from __future__ import annotations

import re
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


def read_version() -> str:
    text = _PYPROJECT.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if not match:
        raise RuntimeError(f"no version field found in {_PYPROJECT}")
    return match.group(1)


VERSION = read_version()

"""Makes the repo root importable regardless of how pytest is invoked.

tests/ has no __init__.py, so pytest's default "prepend" import mode only
puts tests/ on sys.path, not the repo root where installer.py and
config_loader.py live.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PLUGIN = REPO_ROOT


@pytest.fixture(scope="session")
def venv(tmp_path_factory):
    """A venv without pip whose site-packages point at this interpreter's: deps import, nothing installs."""
    path = tmp_path_factory.mktemp("deploy-venv") / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(path)], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    python = next(p for p in (path / "Scripts" / "python.exe", path / "bin" / "python") if p.is_file())
    purelib = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                             check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
    dirs = [p for p in sys.path if p and os.path.isdir(p) and Path(p).resolve() != PLUGIN.resolve()]
    Path(purelib, "outer.pth").write_text("\n".join(dirs) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def box(tmp_path, venv):  # pylint: disable=redefined-outer-name
    """One fake machine of this host's own OS flavour (tests/deploy_box.py)."""
    from deploy_box import NATIVE, Box  # pylint: disable=import-outside-toplevel
    return Box(tmp_path, venv, NATIVE)

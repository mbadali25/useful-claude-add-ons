"""Makes the repo root importable regardless of how pytest is invoked.

tests/ has no __init__.py, so pytest's default "prepend" import mode only
puts tests/ on sys.path, not the repo root where installer.py and
config_loader.py live.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PLUGIN = REPO_ROOT
sys.path.insert(0, str(Path(__file__).resolve().parent / "netguard"))
import netguard  # noqa: E402  pylint: disable=wrong-import-position,import-error


@pytest.fixture(scope="session", autouse=True)
def network_guard(tmp_path_factory):
    netguard.guard(tmp_path_factory.getbasetemp() / "netguard-opened")


@pytest.fixture(autouse=True)
def no_network(network_guard):  # pylint: disable=redefined-outer-name,unused-argument
    """No test may open a socket that leaves this machine, itself or in a Python it starts (tests/netguard):
    the guard refuses the socket and notes it, and the test that opened it fails."""
    netguard.take()
    yield
    opened = netguard.take()
    assert not opened, f"this test opened a non-loopback socket: {opened!r}"


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
    # What deploy writes after its pip install: these requirements are in, so it installs nothing
    digest = hashlib.sha256((PLUGIN / "requirements.txt").read_bytes()).hexdigest()
    (path / ".ai-connect-requirements.sha256").write_text(digest + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_real_tailscale(tmp_path_factory, monkeypatch):
    """No test may reach a Tailscale installed on this machine (two once ran `tailscale down` on it).

    The install directories tsadmin also looks in point at nothing, and a tripwire named
    tailscale is first on PATH: it does nothing but leave a mark, and the test that made
    it run fails. A test that needs the command puts its own fake in front of it.
    """
    guard = tmp_path_factory.getbasetemp() / "tailscale-guard"
    mark = guard / "called"
    if not guard.exists():
        (guard / "bin").mkdir(parents=True)
        if os.name == "nt":
            (guard / "bin" / "tailscale.cmd").write_text(f'@echo %*>>"{mark}"\r\n@exit /b 97\r\n', encoding="utf-8")
        else:
            shim = guard / "bin" / "tailscale"
            shim.write_text(f'#!/bin/sh\necho "$@" >> "{mark}"\nexit 97\n', encoding="utf-8", newline="\n")
            shim.chmod(0o755)
    monkeypatch.setenv("AI_CONNECT_TAILSCALE_DIRS", str(guard / "no-such-dir"))
    monkeypatch.setenv("PATH", str(guard / "bin") + os.pathsep + os.environ.get("PATH", ""))
    yield
    called = mark.read_text(encoding="utf-8") if mark.exists() else ""
    mark.unlink(missing_ok=True)
    assert not called, f"this test ran the tailscale command on PATH instead of a fake: {called!r}"

@pytest.fixture
def box(tmp_path, venv):  # pylint: disable=redefined-outer-name
    """One fake machine of this host's own OS flavour (tests/deploy_box.py)."""
    from deploy_box import NATIVE, Box  # pylint: disable=import-outside-toplevel
    return Box(tmp_path, venv, NATIVE)

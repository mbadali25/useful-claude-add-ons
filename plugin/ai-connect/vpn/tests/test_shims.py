"""The .sh/.ps1 shims: syntax, LF endings, and exit codes passed through from tsadmin.py."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

VPN = Path(__file__).resolve().parent.parent
NAMES = ("mint-key", "vpn-up", "vpn-down", "revoke")
SH = sorted(VPN.glob("*.sh"))
PS1 = sorted(VPN.glob("*.ps1"))

PWSH_CANDIDATES = [r"C:\Program Files\PowerShell\7\pwsh.exe", "/usr/bin/pwsh", "/usr/local/bin/pwsh",
                   "/opt/homebrew/bin/pwsh"]
PWSH = next((p for p in PWSH_CANDIDATES if os.path.isfile(p)), None)
GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"
BASH = GIT_BASH if os.name == "nt" and os.path.isfile(GIT_BASH) else shutil.which("bash")


def test_every_shim_pair_exists():
    for name in NAMES:
        assert (VPN / f"{name}.sh").is_file()
        assert (VPN / f"{name}.ps1").is_file()


@pytest.mark.parametrize("path", SH + PS1 + [VPN / "tsadmin.py"], ids=lambda p: p.name)
def test_lf_only(path):
    assert b"\r" not in path.read_bytes()


@pytest.mark.skipif(not BASH, reason="bash not found")
@pytest.mark.parametrize("path", SH, ids=lambda p: p.name)
def test_bash_syntax(path):
    res = subprocess.run([BASH, "-n", str(path)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(not PWSH, reason="pwsh not found at an absolute path")
@pytest.mark.parametrize("path", PS1, ids=lambda p: p.name)
def test_ps1_parses(path, tmp_path):
    script = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
              f"'{path}', [ref]$null, [ref]$e); if ($e.Count) {{ $e | ForEach-Object {{ $_.Message }}; exit 1 }}")
    # pwsh's startup profile cache goes in this test's own dir, never the shared ~/.cache (L-0557)
    res = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                         text=True, check=False, env=dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))
    assert res.returncode == 0, res.stdout + res.stderr


def _env_without_tailscale(tmp_path):
    """PATH holding only the directory of a real python, so `tailscale` is not found."""
    import sys
    env = dict(os.environ)
    pydir = str(Path(sys.executable).parent)
    sysdirs = [r"C:\Windows\System32", r"C:\Windows"] if os.name == "nt" else ["/usr/bin", "/bin"]
    env["PATH"] = os.pathsep.join([pydir] + sysdirs)
    env["AI_CONNECT_TS_STATE_DIR"] = str(tmp_path / "state")
    # Nor in the directory a real install uses: these tests run vpn-down, which must never reach a real tailscale
    env["AI_CONNECT_TAILSCALE_DIRS"] = str(tmp_path / "no-tailscale")
    env["XDG_CACHE_HOME"] = str(tmp_path / "xdg-cache")  # pwsh's profile cache, per test (L-0557)
    return env


@pytest.mark.skipif(not BASH, reason="bash not found")
def test_sh_shim_passes_exit_code_through(tmp_path):
    if shutil.which("tailscale", path=_env_without_tailscale(tmp_path)["PATH"]):
        pytest.skip("tailscale on the minimal PATH")
    env = _env_without_tailscale(tmp_path)
    if os.name == "nt":  # Git Bash needs its own coreutils (dirname) on PATH
        env["PATH"] = os.pathsep.join([r"C:\Program Files\Git\usr\bin", env["PATH"]])
    res = subprocess.run([BASH, str(VPN / "vpn-down.sh")], capture_output=True, text=True, env=env, check=False)
    assert res.returncode == 3, res.stdout + res.stderr
    assert "not installed" in res.stderr


@pytest.mark.skipif(not PWSH, reason="pwsh not found at an absolute path")
def test_ps1_shim_passes_exit_code_through(tmp_path):
    env = _env_without_tailscale(tmp_path)
    if shutil.which("tailscale", path=env["PATH"]):
        pytest.skip("tailscale on the minimal PATH")
    res = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(VPN / "vpn-down.ps1")],
                         capture_output=True, text=True, env=env, check=False)
    assert res.returncode == 3, res.stdout + res.stderr
    assert "not installed" in res.stderr


@pytest.mark.skipif(not PWSH, reason="pwsh not found at an absolute path")
@pytest.mark.parametrize("name", NAMES)
def test_ps1_shim_passes_the_repo_powershell_static_check(name, tmp_path):
    """scripts/check-powershell.ps1 cannot follow a dot-source, so each shim carries its own helper."""
    checker = VPN.parents[2] / "scripts" / "check-powershell.ps1"
    res = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(checker),
                          "-Path", str(VPN / f"{name}.ps1")], capture_output=True, text=True, check=False,
                         env=dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))
    assert res.returncode == 0, res.stdout + res.stderr

"""Tests for verify-gate.ps1's bash resolver (ANEWINF-756).

On Windows with WSL installed, an unqualified `bash` on PATH commonly
resolves to C:\\Windows\\System32\\bash.exe (the WSL launcher) or the
WindowsApps App Execution Alias shim, ahead of Git for Windows' own bash --
confirmed via `Get-Command bash -All` on a real reporting machine. Inside
WSL none of a Windows repo's tools exist (terraform, tflint, rustup, ...),
so the Stop hook printed a false "SMOKE: 0/9 passed" on a tree that was
actually green under Git Bash.

This bug is inherently Windows-only: there is no WSL launcher or
WindowsApps shim to shadow bash on POSIX, and verify-gate.ps1 is itself
documented as "the PowerShell end-of-turn gate for native Windows". These
tests are skipped everywhere else, including the pytest-crew.yml CI job
(ubuntu-latest), which never exercises this file for that reason.

verify-gate.ps1's `-PrintBash` switch exists solely so the resolution can
be probed without touching stdin, .crew/, or running any real check -- it
prints the path Resolve-CrewBash would use and exits 0.
"""
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")

_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="WSL/WindowsApps bash-shadowing only happens on native Windows with pwsh",
)


def _touch(path):
    """Create a file Get-Command can resolve as a command.

    -PrintBash never executes the resolved path (only Test-Path /
    Get-Command see it), so the content is irrelevant -- it just has to
    exist with a .exe extension for PATHEXT-based resolution.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as f:
        f.write("rem stub, never executed by -PrintBash\n")
    return path


def _print_bash(path_entries):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(path_entries)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-PrintBash"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, "stderr: %s" % result.stderr
    return result.stdout.strip()


def test_prefers_gitbash_over_a_wsl_style_bash_earlier_on_path(tmp_path):
    """The exact shape of the real bug: a WSL-launcher-style bash sits ahead
    of Git for Windows' own bash on PATH -- `where.exe bash` on the
    reporting machine showed System32's bash.exe first, Git's nowhere in
    the list. Resolve-CrewBash must walk up from git.exe's own directory
    and use ITS bash, ignoring PATH order entirely."""
    wsl_dir = tmp_path / "Windows" / "System32"
    _touch(str(wsl_dir / "bash.exe"))

    git_root = tmp_path / "Git"
    git_cmd_dir = git_root / "cmd"
    real_bash = git_root / "bin" / "bash.exe"
    _touch(str(git_cmd_dir / "git.exe"))
    _touch(str(real_bash))

    # WSL-style bash listed first on PATH, exactly as observed -- if PATH
    # order won instead of the git-relative walk-up, this resolves wrong.
    resolved = _print_bash([str(wsl_dir), str(git_cmd_dir)])

    assert resolved == str(real_bash)
    assert "System32" not in resolved


def test_walks_up_from_a_mingw64_style_git_exe_too(tmp_path):
    """git.exe's Source varies by install shape: `...\\Git\\cmd\\git.exe`
    or `...\\Git\\mingw64\\bin\\git.exe` on this very machine (`Get-Command
    git -All` returned both). bash.exe sits two directories up from either
    -- the resolver must walk up rather than assume one fixed depth."""
    git_root = tmp_path / "Git"
    git_bin_dir = git_root / "mingw64" / "bin"
    real_bash = git_root / "usr" / "bin" / "bash.exe"
    _touch(str(git_bin_dir / "git.exe"))
    _touch(str(real_bash))

    resolved = _print_bash([str(git_bin_dir)])

    assert resolved == str(real_bash)


def test_falls_through_when_git_is_a_powershell_function(tmp_path):
    """A git wrapper defined as a PowerShell function (real in corporate
    profiles that shim git) has no .exe -- Get-Command still returns it
    ahead of any git.exe on PATH, but its .Source is an empty string, not a
    path. Resolve-CrewBash must not call Split-Path on that empty .Source
    (that throws a terminating error which escapes the whole hook -- a
    crash where the old unconditional `& bash` at least attempted
    something); it must fall through to the PATH-based fallback (tier b)
    instead, and must not throw."""
    wsl_dir = tmp_path / "Windows" / "System32"
    _touch(str(wsl_dir / "bash.exe"))

    real_dir = tmp_path / "Git" / "bin"
    real_bash = real_dir / "bash.exe"
    _touch(str(real_bash))

    env = os.environ.copy()
    # A System32-style bash sits first on PATH, exactly like the real-bug
    # shape in the other tests -- the real bash.exe comes later on PATH,
    # reachable only through the tier-b fallback since `git` here is a
    # function with nothing for the tier-a walk-up to use. Tier b's
    # System32 filter compares against $env:SystemRoot, not path text, so
    # SystemRoot has to point at this fake tree for the filter to apply.
    env["SystemRoot"] = str(tmp_path / "Windows")
    env["PATH"] = os.pathsep.join([str(wsl_dir), str(real_dir)])
    command = "function git { }\n& '%s' -PrintBash" % _PS1
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False,
    )

    assert result.returncode == 0, "stderr: %s" % result.stderr
    resolved = result.stdout.strip()
    assert resolved == str(real_bash)
    assert "System32" not in resolved
    # Without the CommandType/Source guard, Split-Path on the function's
    # empty .Source still resolves correctly by accident (the parameter-
    # binding error is non-terminating under this script's default
    # $ErrorActionPreference, so execution falls through to tier b anyway)
    # -- but it does so noisily. A clean run must not touch Split-Path at
    # all for a non-Application git, so stderr must be empty.
    assert result.stderr == "", "unexpected stderr: %s" % result.stderr


def test_falls_back_to_path_excluding_windowsapps_when_no_git_found(tmp_path):
    """No git resolvable at all (tier b of the resolver): filter
    `Get-Command bash -All`, dropping the WindowsApps App Execution Alias
    shim -- the second WSL-adjacent shadow `Get-Command bash -All` showed
    on the reporting machine, alongside the System32 launcher."""
    windows_apps = tmp_path / "AppData" / "Local" / "Microsoft" / "WindowsApps"
    _touch(str(windows_apps / "bash.exe"))

    real_dir = tmp_path / "usr" / "local" / "bin"
    real_bash = real_dir / "bash.exe"
    _touch(str(real_bash))

    # No git anywhere on PATH: forces the PATH-filtering fallback branch.
    resolved = _print_bash([str(windows_apps), str(real_dir)])

    assert resolved == str(real_bash)
    assert "WindowsApps" not in resolved

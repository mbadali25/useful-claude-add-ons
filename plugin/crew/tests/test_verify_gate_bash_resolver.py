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
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

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
    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-PrintBash"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
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
    env["PATH"] = os.pathsep.join([str(wsl_dir), str(real_dir)])
    # SystemRoot is faked INSIDE -Command, not in the process env. pwsh
    # reads it during startup (InitialSessionState -> GetSaferPolicy),
    # and a tree with no real System32 kills the interpreter with
    # Win32Exception (126) before the script runs at all. Setting it
    # here lets pwsh boot against the real System32 while the script
    # under test still sees the fake tree, which is all tier b's
    # filter compares against.
    command = ("$env:SystemRoot = '%s'\n"
               "function git { }\n& '%s' -PrintBash"
               % (tmp_path / "Windows", _PS1))
    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    resolved = result.stdout.strip()
    assert resolved == str(real_bash)
    assert "System32" not in resolved
    # Without the CommandType/Source guard, Split-Path on the function's
    # empty .Source still resolves correctly by accident (the parameter-
    # binding error is non-terminating under this script's default
    # $ErrorActionPreference, so execution falls through to tier b anyway)
    # -- but it does so noisily. A clean run must not touch Split-Path at
    # all for a non-Application git, so stderr must be empty.
    assert result.stderr == "", f"unexpected stderr: {result.stderr}"


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


def test_tier_b_skips_a_bash_defined_as_a_powershell_function(tmp_path):
    """The mirror image of the git-as-a-function case, in tier b. `Get-Command
    bash -All` returns a profile-defined `bash` function first, and its .Source
    is an empty string -- calling .StartsWith() on that throws, and returning
    it hands `& $bashExe` an empty interpreter, so the gate blocks the turn
    with a smoke failure that is really a resolution failure. Only Application
    entries are candidates, so the real bash.exe later on PATH must win and
    nothing may reach stderr."""
    wsl_dir = tmp_path / "Windows" / "System32"
    _touch(str(wsl_dir / "bash.exe"))

    real_dir = tmp_path / "Git" / "bin"
    real_bash = real_dir / "bash.exe"
    _touch(str(real_bash))

    env = os.environ.copy()
    # No git on PATH at all, so tier a cannot resolve and tier b runs.
    env["PATH"] = os.pathsep.join([str(wsl_dir), str(real_dir)])
    # Same reason as the git-function case above: faked in -Command so
    # pwsh can still start.
    command = ("$env:SystemRoot = '%s'\n"
               "function bash { }\n& '%s' -PrintBash"
               % (tmp_path / "Windows", _PS1))
    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == str(real_bash)
    assert result.stderr == "", f"unexpected stderr: {result.stderr}"


def _touch_extensionless(path):
    """A `bash` candidate CreateProcess cannot launch directly -- no
    recognised extension. Confirmed by direct probe on this host that
    `Get-Command bash -All` (Resolve-CrewBash's tier-b call, which unlike
    Resolve-CrewPython's carries no `-CommandType Application` filter) DOES
    return this as CommandType Application with a real, non-WindowsApps
    .Source: it reaches the native-extension gate and is rejected there, not
    silently invisible to Get-Command the way Resolve-CrewPython's fixtures
    are."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as f:
        f.write("#!/bin/sh\nwhile true; do sleep 1; done\n")
    return path


def test_prints_nothing_not_the_bare_name_when_every_candidate_is_rejected(tmp_path):
    """The defect this module exists to catch (B2): every PATH candidate is
    an extensionless shim the native-extension gate rejects, and no git is
    resolvable either (tier a never runs). The old fallback returned the
    bare string 'bash' here -- which `& $bashExe` then re-resolves through
    PowerShell's OWN command lookup, landing back on the exact shim this
    loop just rejected, and hangs (this fixture's body would spin forever if
    it were ever actually invoked). Resolve-CrewBash must return an empty
    string instead, so every caller can tell "nothing usable" apart from "an
    actual path" and refuse by name rather than invoke."""
    only_dir = tmp_path / "only"
    _touch_extensionless(str(only_dir / "bash"))

    # No git anywhere on this PATH -- forces tier a's git-relative walk-up
    # to find nothing and fall through to tier b, exactly like
    # test_falls_back_to_path_excluding_windowsapps_when_no_git_found above.
    resolved = _print_bash([str(only_dir)])

    assert resolved == "", (
        f"Resolve-CrewBash returned {resolved!r} instead of '' when every "
        "candidate was rejected -- a non-empty, non-path value here is "
        "exactly the bare-'bash' regression this test exists to catch")


def test_gate_refuses_by_name_instead_of_hanging_on_an_all_rejected_path(tmp_path):
    """The full gate (not just -PrintBash) exercising the actual defect:
    every rule's bash invocation must refuse by name, never invoke a
    bare-name re-resolution of the shim this module's sibling test above
    proves gets rejected.

    This needs a WORKING git (the gate's own `git diff`/`ls-files` calls,
    made before the rule loop is ever reached, would otherwise fail and
    take a different code path than a real Stop hook run) while still
    forcing Resolve-CrewBash's tier a to fall through -- and a real Git for
    Windows install always has a real bash.exe two directories from
    git.exe, which would rescue tier a and defeat the fixture. Wrapping
    `git` as a PowerShell FUNCTION closes that gap exactly the way
    test_falls_through_when_git_is_a_powershell_function proves above:
    `Get-Command git` then returns CommandType Function, not Application,
    so tier a's `.Source`-Application check never matches and falls
    straight to tier b -- while the function itself still runs the real
    git.exe by absolute path, so the gate's OWN git calls keep working."""
    git_exe = shutil.which("git")
    assert git_exe, "need a real git on PATH to build this fixture"

    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=root, check=True, timeout=30,
                       capture_output=True, text=True)
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, timeout=30,
                   capture_output=True, text=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True,
                   timeout=30, capture_output=True, text=True)

    vmap = {"version": 1,
            "rules": [{"paths": ["a.py"], "reach": "local", "run": ["echo ok"]}],
            "default": [], "unmapped": "ignore"}
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(json.dumps(vmap), encoding="utf-8")
    (root / "a.py").write_text("x", encoding="utf-8")  # untracked, matches the rule

    only_dir = tmp_path / "only"
    # Spins forever if ever actually invoked -- proves the gate never
    # reached it rather than merely returning fast by luck.
    _touch_extensionless(str(only_dir / "bash"))

    command = ("$env:PATH = '%s'\n"
               "$env:CLAUDE_PROJECT_DIR = '%s'\n"
               "function git { & '%s' @args }\n"
               "& '%s'\n"
               "exit $LASTEXITCODE\n"
               % (only_dir, root, git_exe, _PS1))

    started = time.time()
    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
        input="{}", capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    elapsed = time.time() - started

    assert elapsed < 15, (
        f"the gate took {elapsed:.1f}s to return -- it may have invoked "
        f"the rejected shim through a re-resolved bare name instead of "
        f"refusing. stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.returncode != 0, (
        "a rule refused for lack of a usable bash must not read as "
        f"verified. stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "no usable bash resolved" in result.stderr, (
        "the gate did not name the refusal reason. stderr: " + result.stderr)

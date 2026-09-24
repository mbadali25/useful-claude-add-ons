"""verify-gate.ps1's python resolver, and the scope script's own precondition.

Twin of test_verify_gate_bash_resolver.py, and it exists because this file
already CONTAINED the hardened resolver it needed. `Resolve-CrewBash` filters
on `CommandType -eq 'Application'` and excludes the WindowsApps App Execution
Alias; the scope report's interpreter was resolved four lines of
`Get-Command python3, python | Select-Object -First 1` away from it, with
neither guard. One file, two resolvers, one of them hardened.

Both vectors are live rather than theoretical:

* **A profile function wins.** `hooks.json` registers this hook with no
  `-NoProfile`, so a `function python { ... }` in a user profile is loaded and
  `Get-Command` returns it AHEAD of any `python.exe`. Its `.Source` is empty,
  so the old code fell through to "no python; scope not checked" on a machine
  with python installed -- the unknown collapsing into a safe-looking value
  that this repository's CLAUDE.md names as its recurring defect.

* **The Store stub resolves and is invoked.** `WindowsApps\\python.exe` is a
  real Application with a real `.Source`, so it passed the old test and was
  executed; it opens the Microsoft Store rather than running the script.

The third case here is the scope script's own existence. verify-gate.sh tests
`-n "$SCOPE_PY"` AND `-f "$SCOPE_DIR/scope_report.py"`; the .ps1 tested only
the interpreter, so a missing scope_report.py reached python and the gate
printed a raw "can't open file" line as its scope report.

`-PrintPython` is the probe seam, exactly as `-PrintBash` is for the other
resolver: it prints what Resolve-CrewPython would use and exits 0 without
touching stdin, .crew/, or running any check.
"""
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

_PWSH = shutil.which("pwsh")
_BASH = crew_fixtures.resolve_bash()

# MARKED PER TEST, not with a module-level pytestmark. The scope-precondition
# split landed in BOTH flavours, and the .sh half runs everywhere -- a module
# mark reading "needs Windows + pwsh" would have skipped it on the Linux CI
# runner, which is the one place the bash flavour is the only one that runs.
_WINDOWS_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="verify-gate.ps1 is the native-Windows flavour; needs Windows + pwsh",
)
_NEEDS_BASH = pytest.mark.skipif(_BASH is None, reason="needs bash")


def _stub(path):
    """A file Get-Command resolves as an Application. -PrintPython never runs
    it, so the contents are irrelevant -- only the .exe extension matters."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as fh:
        fh.write("rem stub, never executed by -PrintPython" + chr(10))
    return path


def _launchable(path):
    """A stub that RUNS and answers like an interpreter: it prints the JSON
    proof object Resolve-CrewPython requires -- {"v": [major, minor],
    "exe": sys.executable, "impl": sys.implementation.name} -- rather than a
    bare path. Since crew 1.0 every candidate is executed and its answer is
    parsed as that JSON, so a plain `echo <path>`, as `print(sys.executable)`
    would produce, no longer stands in for a real python."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    proof = '{"v": [3, 9], "exe": "' + path.replace("\\", "\\\\") + '", "impl": "cpython"}'
    with open(path, "w", encoding="ascii") as fh:
        fh.write("@echo off" + chr(13) + chr(10) + "echo " + proof + chr(13) + chr(10))
    return path


def _print_python(path_entries):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(path_entries)
    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-PrintPython"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert result.returncode == 0, (
        "the probe must exit 0. stderr: " + result.stderr
    )
    return result.stdout.strip()


# ------------------------------------------------------- the WindowsApps stub

@_WINDOWS_ONLY
def test_the_windowsapps_stub_is_never_returned(tmp_path):
    """Must-block. The App Execution Alias is a real Application with a real
    .Source, so it passed the old `Select-Object -First 1` test and would have
    been INVOKED -- it opens the Store instead of running scope_report.py."""
    apps = tmp_path / "WindowsApps"
    _stub(str(apps / "python3.exe"))
    _stub(str(apps / "python.exe"))

    resolved = _print_python([str(apps)])
    assert "WindowsApps" not in resolved, (
        "the WindowsApps App Execution Alias was returned as the interpreter: "
        + resolved
    )
    assert resolved == "", (
        "with only the WindowsApps stubs on PATH there is no usable python, "
        "and the resolver must say so with an empty answer rather than "
        "handing back a stub. got: " + resolved
    )


@_WINDOWS_ONLY
def test_a_real_python_beside_a_stub_still_resolves(tmp_path):
    """Must-allow, and the half that stops the fix above becoming "never find
    python". A genuine python3.exe must still be returned even when a
    WindowsApps stub is on PATH ahead of it."""
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    _stub(str(apps / "python3.exe"))
    _launchable(str(real / "python3.cmd"))

    resolved = _print_python([str(apps), str(real)])
    assert resolved.lower().startswith(str(real).lower()), (
        "the real python3.exe must win over the WindowsApps stub. got: "
        + resolved
    )


# --------------------------------------------------- the profile function

def _resolver_source():
    """Resolve-CrewPython lifted out of the script, so this case tests the
    shipped function rather than a restatement of it."""
    src = pathlib.Path(_PS1).read_text(encoding="utf-8")
    start = src.find("function Resolve-CrewPython {")
    assert start != -1, (
        "Resolve-CrewPython is gone from verify-gate.ps1. If it was renamed, "
        "re-point this test rather than deleting it -- a resolver guard that "
        "silently stops checking is the defect it exists to catch."
    )
    end = src.find(chr(10) + "}" + chr(10), start)
    assert end != -1, "could not find the end of Resolve-CrewPython"
    return src[start:end + 3]


@_WINDOWS_ONLY
def test_a_profile_function_named_python_does_not_shadow_the_interpreter(tmp_path):
    """Must-block for the CommandType guard.

    hooks.json passes no -NoProfile, so a `function python` in a user profile
    is loaded and Get-Command returns it first with an empty .Source. Driven
    in-process because that is the only way to have such a function defined:
    writing a real profile would touch the user's own configuration, which no
    test here may do.
    """
    real = tmp_path / "tools"
    _launchable(str(real / "python3.cmd"))

    script = (
        _resolver_source() + chr(10) +
        "function python { 'shadow' }" + chr(10) +
        "function python3 { 'shadow' }" + chr(10) +
        "Write-Output (Resolve-CrewPython)" + chr(10)
    )
    script_path = tmp_path / "probe.ps1"
    script_path.write_text(script, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = str(real)
    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script_path)],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert result.returncode == 0, result.stderr
    resolved = result.stdout.strip()
    assert resolved.lower().startswith(str(real).lower()), (
        "a PowerShell function named python/python3 shadowed the real "
        "interpreter. Get-Command returns it first and its .Source is empty, "
        "so the gate reports 'no python' on a machine that has python. got: "
        + repr(resolved)
    )


# ------------------------------------------------------ the CALL SITE uses it

def _fixture_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=repo, check=True,
                       capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (repo / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=repo, check=True,
                   capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=repo,
                   check=True, capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (repo / "unverified.py").write_text("x = 1", encoding="utf-8")
    return repo


@_WINDOWS_ONLY
def test_the_scope_report_call_site_actually_uses_the_hardened_resolver(tmp_path):
    """A hardened resolver nothing calls is not a fix.

    Found by sabotage: reverting the call site to
    `Get-Command python3, python | Select-Object -First 1` left every other
    case in this file GREEN, because they all probe Resolve-CrewPython through
    -PrintPython and none of them proved the scope report goes through it.
    That is the shape this repo keeps hitting -- a guard that is correct and
    unreached.

    So drive the REAL gate with a PATH whose only python is a WindowsApps
    stub. The hardened resolver skips it, finds nothing, and prints the
    "no python" sentence. The old code hands back the stub's .Source, invokes
    it, and lands in the catch with a different sentence.
    """
    apps = tmp_path / "WindowsApps"
    _stub(str(apps / "python3.exe"))
    _stub(str(apps / "python.exe"))
    repo = _fixture_repo(tmp_path)

    env = os.environ.copy()
    # git must stay reachable (the gate needs it to find changed files and to
    # locate bash); no real python may be.
    env["PATH"] = os.pathsep.join(
        [str(apps), os.path.dirname(shutil.which("git"))])
    env["CLAUDE_PROJECT_DIR"] = str(repo)

    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1],
        input="{}", cwd=str(repo), env=env,
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert "(no python; scope not checked)" in result.stderr, (
        "the scope report did not go through Resolve-CrewPython: with only a "
        "WindowsApps stub on PATH the gate must report no usable python, not "
        "invoke the stub. stderr: " + result.stderr
    )


# ------------------------------------------- the scope script's own existence

def _scripts_without_scope_report(tmp_path):
    """A copy of the whole hooks/scripts directory with scope_report.py
    removed.

    Copying the gate ALONE is not enough and the difference is not cosmetic:
    verify-gate.sh dot-sources _common.sh from its own directory, so a lone
    copy dies with "crew_incident_active: command not found" and never
    reaches the scope block at all -- while still printing a plausible
    "(no python; scope not checked)" line, because crew_py went missing with
    the rest. That would have been a test passing for entirely the wrong
    reason on a gate that never ran.
    """
    dst = tmp_path / "scripts"
    shutil.copytree(os.path.join(_ROOT, "hooks", "scripts"), dst)
    (dst / "scope_report.py").unlink()
    return dst



@_WINDOWS_ONLY
def test_a_missing_scope_report_says_so_instead_of_a_python_error(tmp_path):
    """Must-allow for the Test-Path parity fix.

    The gate is copied somewhere scope_report.py is NOT beside it, which is
    what $PSScriptRoot keys on. Before the fix python was invoked anyway and
    printed its own "can't open file" line as the scope report; the uniform
    fallback sentence is what a reader can actually act on. The scope layer is
    report-only, so this must not change the exit code either.
    """
    lonely = _scripts_without_scope_report(tmp_path)
    copied = lonely / "verify-gate.ps1"

    # A real git repo with an untracked file: the gate exits before the scope
    # report when its changed-file set is empty, so a bare directory would
    # pass this test without the scope block ever running.
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=repo, check=True,
                       capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (repo / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=repo, check=True,
                   capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=repo,
                   check=True, capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    (repo / "unverified.py").write_text("x = 1", encoding="utf-8")

    result = crew_fixtures.run_gate(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(copied)],
        input="{}", cwd=str(repo),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(repo)),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert "scope_report.py not found" in result.stderr, (
        "a missing scope_report.py must produce the uniform fallback line, "
        "not a raw python error. stderr: " + result.stderr
    )
    assert "can't open file" not in result.stderr, (
        "python was invoked on a script that is not there. stderr: "
        + result.stderr
    )


@_NEEDS_BASH
def test_the_bash_flavour_also_names_a_missing_scope_report(tmp_path):
    """The .sh twin, and it runs on POSIX where the .ps1 cannot.

    Both flavours used to answer "(no python; scope not checked)" for a
    missing scope_report.py -- a different cause with a different fix,
    wearing the other one's sentence. Found by sabotage: collapsing the two
    branches in verify-gate.sh again left every .ps1 case above green,
    because none of them execute the bash flavour at all.
    """
    lonely = _scripts_without_scope_report(tmp_path)
    copied = lonely / "verify-gate.sh"

    repo = _fixture_repo(tmp_path)
    result = crew_fixtures.run_gate(
        [_BASH, str(copied)], input="{}", cwd=str(repo),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(repo)),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    assert "scope_report.py not found" in result.stderr, (
        "verify-gate.sh must name the missing scope script rather than "
        "reporting it as an absent interpreter. stderr: " + result.stderr
    )

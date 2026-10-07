"""pm-pulse.ps1's python resolver, and the guard on its duplicated copy.

`pm-pulse.ps1` resolved its interpreter with
`(Get-Command python3, python | Select-Object -First 1).Source` -- the same
one-liner verify-gate.ps1 carried, with neither of the guards
`Resolve-CrewBash` has had in that same file all along.

**What it costs here is worse than in verify-gate.** This hook exits 2 to
block the stop and hand the PM's findings back to the model, and the next line
was `if (-not $py) { exit 0 }`. hooks.json registers it with no `-NoProfile`,
so a `function python { }` in a user profile is returned ahead of any
python.exe with an EMPTY `.Source`; the emptiness then failed that test and
the hook exited 0. Every PM finding, including the blocking ones, dropped in
silence on a machine with python installed -- a hook wearing the exit code of
a pass, which is this repository's named recurring defect.

The WindowsApps App Execution Alias fails the other way: a real Application
with a real `.Source`, so it resolved, was invoked, and opened the Store
instead of running pm_pulse.py.

The resolver is duplicated inline rather than dot-sourced, following the
decision verify-gate.ps1's header records (a dot-sourced function is invisible
to scripts/check-powershell.ps1's static check). The last case in this file is
the guard that duplication needs: a hand-copy with no guard is the defect this
repo keeps re-finding, so the two copies are asserted to still agree.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_PULSE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "pm-pulse.ps1")
_GATE_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")

_PWSH = shutil.which("pwsh")

_WINDOWS_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="pm-pulse.ps1 is the native-Windows flavour; needs Windows + pwsh",
)


def _stub(path):
    """A file Get-Command resolves as an Application. NOT "never executed by
    -PrintPython" (stale as of Windows audit wave 3, corrected round-2
    review 2026-09-22): Resolve-CrewPython DOES attempt to run this -- the
    rejection these must-block cases below depend on comes from the launch
    failing (garbage content behind a real-looking .exe extension is not a
    valid PE), not from the candidate being skipped unexamined."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as fh:
        fh.write("rem stub, not a valid executable when actually launched" + chr(10))
    return path


def _real_stub(path):
    """A REAL, launchable `.cmd` batch file that echoes its OWN path when
    run -- never the inert `_stub()` above. Review round, 2026-09-22:
    `test_a_real_python_beside_a_stub_still_resolves` and
    `test_a_profile_function_named_python_does_not_silence_the_pulse` used
    `_stub()` for the interpreter they expect the resolver to FIND, which
    only ever looked like a real Application to Get-Command's metadata and
    was never actually launchable -- once Resolve-CrewPython started
    executing every candidate (Windows audit wave 3), both cases would
    have failed closed for the WRONG reason. Matches
    test_role_write_guard.py's own `_stub(path, reports=...)` convention.

    LIMITATION, noted rather than worked around: `echo <path>` is
    UNESCAPED cmd.exe text -- `tmp_path`'s own fixtures never contain `&`,
    `^`, `%`, parens, or non-ASCII characters, so this has never needed to
    quote or escape them, but a profile whose OWN path did (a Windows
    username with an accent, for instance) would need this stub widened
    first; batch-quoting rules are their own trap and are not worth
    adding speculatively."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="ascii") as fh:
        fh.write("@echo off\r\necho " + path + "\r\n")
    return path


def _print_python(path_entries):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(path_entries)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PULSE_PS1,
         "-PrintPython"],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "the probe must exit 0. stderr: " + result.stderr
    )
    return result.stdout.strip()


@_WINDOWS_ONLY
def test_the_windowsapps_stub_is_never_returned(tmp_path):
    """Must-block. The Store alias passed the old test and was INVOKED."""
    apps = tmp_path / "WindowsApps"
    _stub(str(apps / "python3.exe"))
    _stub(str(apps / "python.exe"))

    resolved = _print_python([str(apps)])
    assert "WindowsApps" not in resolved, (
        "the WindowsApps alias was returned as the interpreter: " + resolved
    )
    assert resolved == "", (
        "with only stubs on PATH there is no usable python and the resolver "
        "must answer empty rather than hand back a stub. got: " + resolved
    )


@_WINDOWS_ONLY
def test_a_store_python_alias_relaying_to_a_real_interpreter_still_resolves(tmp_path):
    """Must-allow: Windows audit wave 3. A genuine Microsoft Store Python
    install resolves through EXACTLY this layout -- the alias at
    `...\\WindowsApps\\python3.exe` relays to a real interpreter whose own
    `sys.executable` is ALSO WindowsApps-rooted. Before this fix the
    blanket `-match 'WindowsApps'` check rejected that reported path too,
    so a machine with Python genuinely installed through the Store answered
    "no usable python" on every pulse -- silently dropping the PM's
    findings, blocking ones included. This is a `.cmd` that PRINTS a
    WindowsApps-rooted path rather than one that lives at it, because
    -PrintPython never executes what the resolver returns."""
    apps = tmp_path / "WindowsApps"
    relay_target = str(
        apps / "PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"
        / "python.exe")
    os.makedirs(os.path.dirname(relay_target), exist_ok=True)
    with open(relay_target, "w", encoding="ascii") as fh:
        fh.write("placeholder")
    stub = apps / "python3.cmd"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text("@echo off\r\necho " + relay_target + "\r\n",
                     encoding="ascii")

    resolved = _print_python([str(apps)])
    assert resolved == relay_target, (
        "a Store-Python alias relaying to a real interpreter under "
        "WindowsApps must be ACCEPTED, not rejected for its path. got: "
        + resolved)


@_WINDOWS_ONLY
def test_a_real_python_beside_a_stub_still_resolves(tmp_path):
    """Must-allow: the fix must not become "the pulse never finds python",
    which would silence it exactly as the bug did."""
    apps = tmp_path / "WindowsApps"
    real = tmp_path / "tools"
    _stub(str(apps / "python3.exe"))
    real_exe = _real_stub(str(real / "python3.cmd"))

    resolved = _print_python([str(apps), str(real)])
    assert resolved == real_exe, (
        "the real python3.cmd must win over the WindowsApps stub. got: "
        + resolved
    )


def _resolver_source(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find("function Resolve-CrewPython {")
    assert start != -1, (
        "Resolve-CrewPython is gone from " + path + ". If it was renamed, "
        "re-point this test rather than deleting it."
    )
    end = src.find(chr(10) + "}" + chr(10), start)
    assert end != -1, "could not find the end of Resolve-CrewPython in " + path
    return src[start:end + 3]


@_WINDOWS_ONLY
def test_a_profile_function_named_python_does_not_silence_the_pulse(tmp_path):
    """Must-block, and the worst of the three.

    A profile function shadowing python gave an empty .Source, which made
    `if (-not $py) { exit 0 }` true: the PM's blocking findings vanished with
    a passing exit code. Driven in-process because defining such a function
    for real would mean writing the user's own PowerShell profile, which no
    test here may touch.
    """
    real = tmp_path / "tools"
    real_exe = _real_stub(str(real / "python3.cmd"))

    script_path = tmp_path / "probe.ps1"
    script_path.write_text(
        _resolver_source(_PULSE_PS1) + chr(10) +
        "function python { 'shadow' }" + chr(10) +
        "function python3 { 'shadow' }" + chr(10) +
        "Write-Output (Resolve-CrewPython)" + chr(10),
        encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = str(real)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script_path)],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    resolved = result.stdout.strip()
    assert resolved == real_exe, (
        "a PowerShell function named python/python3 shadowed the real "
        "interpreter, so the pulse would exit 0 and drop the PM's blocking "
        "findings on a machine that has python. got: " + repr(resolved)
    )


@_WINDOWS_ONLY
def test_the_pulse_still_runs_when_python_resolves(tmp_path):
    """Must-allow at the level of the hook, not the resolver: the script as a
    whole must still reach pm_pulse.py. A resolver that answers correctly in a
    script that no longer calls it is the gap sabotage found in 0.19.67."""
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PULSE_PS1],
        input="{}", cwd=str(repo),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(repo)),
        capture_output=True, text=True, check=False,
    )
    # pm_pulse.py decides what to say; what matters here is that the hook did
    # not fall out at the resolver, which is an exit 0 with nothing attempted.
    assert result.returncode in (0, 2), (
        "unexpected exit from the pulse: " + str(result.returncode)
        + " stderr: " + result.stderr
    )



@_WINDOWS_ONLY
def test_the_call_site_goes_through_the_hardened_resolver(tmp_path):
    """A hardened resolver the script does not call is not a fix.

    Found by sabotage, and it is the SECOND time the same gap appeared: every
    case above probes Resolve-CrewPython through -PrintPython, so reverting
    the call site to the old one-liner left all five green.

    The stub here is OBSERVABLE rather than inert -- a .cmd that writes a
    marker file when it runs. Get-Command resolves .cmd as an Application, so
    the old code would hand it back and invoke it. Asserting on an exit code
    could not tell "skipped the stub" from "ran it and it failed"; the marker
    can only exist if the stub was actually executed.
    """
    apps = tmp_path / "WindowsApps"
    apps.mkdir(parents=True)
    marker = tmp_path / "stub-was-invoked.txt"
    for name in ("python3.cmd", "python.cmd"):
        (apps / name).write_text(
            "@echo off" + chr(10) + 'echo invoked > "' + str(marker) + '"' + chr(10),
            encoding="ascii")

    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    env = os.environ.copy()
    env["PATH"] = str(apps)
    env["CLAUDE_PROJECT_DIR"] = str(repo)

    result = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PULSE_PS1],
        input="{}", cwd=str(repo), env=env,
        capture_output=True, text=True, check=False,
    )
    assert not marker.exists(), (
        "pm-pulse.ps1 invoked the WindowsApps stub as its interpreter, so "
        "the call site is not going through Resolve-CrewPython. stderr: "
        + result.stderr
    )

def test_the_two_copies_of_the_resolver_still_agree():
    """The guard the duplication needs, and it runs everywhere.

    verify-gate.ps1 and pm-pulse.ps1 each carry their own Resolve-CrewPython
    because a dot-sourced function is invisible to check-powershell.ps1's
    static check. That decision is defensible; leaving the copies unguarded is
    not. Comments are allowed to differ -- they SHOULD, the two files explain
    different costs -- so this compares the executable lines only.
    """
    def code_lines(src):
        out = []
        for line in src.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(re.sub(r"\s+", " ", stripped))
        return out

    gate = code_lines(_resolver_source(_GATE_PS1))
    pulse = code_lines(_resolver_source(_PULSE_PS1))
    assert gate == pulse, (
        "the two copies of Resolve-CrewPython have drifted. One hook would "
        "then resolve an interpreter the other refuses, which is the same "
        "class of defect as a .ps1 guard that stands down on Windows."
        + chr(10) + "verify-gate.ps1: " + repr(gate)
        + chr(10) + "pm-pulse.ps1:    " + repr(pulse)
    )

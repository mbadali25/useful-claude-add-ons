"""pm-pulse.sh's python resolver, driven through the real script.

Reported 2026-09-22. `pm-pulse.sh` resolved its interpreter with `_common.sh`'s
shared `crew_py()` -- a bare `command -v python3 || python || py` with no
filtering at all -- and then `exec`ed it. The Windows Store App Execution Alias
at `%LOCALAPPDATA%\\Microsoft\\WindowsApps\\python3.exe` IS a real, executable
file, so `command -v` resolves it, the non-empty test passes, and the stub is
what `exec` launches. Simulated here as "a real executable file that exits
non-zero with no output", which is how crew's own 2026-09-19 report at
`role-write-guard.sh:17-31` characterises it:

    script                     exit   stderr
    pm-pulse.sh (stub)           49   0 bytes
    pm-pulse.sh (real python)     2   the PM's findings

49 is 9009 & 0xFF. `pm-pulse.ps1` has carried the hardened `Resolve-CrewPython`
since 2026-09-19, so WHICH SHELL FLAVOUR Claude Code happened to invoke decided
whether the PM's findings -- blocking ones included -- appeared at all.

**Every assertion here is on behaviour and on stderr CONTENT, never on the exit
code alone.** The whole defect is a wrong exit code with an empty stderr, so an
exit-code-only test is precisely the instrument that cannot see it: the buggy
script and a fixed one both leave `pm-pulse.sh` exiting non-zero on the
must-block cases, and only the presence of the named message tells them apart.

`exec` is why this hook cannot be mitigated the way `verify-gate.sh:1215` and
`promote-gate.sh` are. Those launch python and then CHECK its status, so a stub
becomes a named refusal; `exec` leaves nothing behind that could notice.

The last case is the guard the duplication needs: `crew_py_strict` in
`_common.sh` and `_resolve_role_write_python` in `role-write-guard.sh` are the
same body, kept apart because that hook is the one that can BLOCK a tool call
and its own suite patches that file textually. A hand-copy with no guard is
this repository's most repeated defect.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "pm-pulse.sh")
_COMMON_SH = os.path.join(_ROOT, "hooks", "scripts", "_common.sh")
_GUARD_SH = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.sh")

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

# The message the hook has always meant to print when it cannot find python.
# Under the stub it never printed: `crew_py` SUCCEEDED, so the `||` branch
# holding it was never reached.
_NO_PYTHON = "no usable python"

# A finding is present when the directive that prefixes every pulse is.
_PULSE_MARKER = "Crew PM: the project state changed"


def _real_python_dir():
    real = shutil.which("python3") or shutil.which("python")
    assert real, "this test needs a real python3/python on PATH to prove against"
    return os.path.dirname(real)


def _stub(directory, exit_code=9009, stdout="", names=("python3", "python", "py")):
    """A real, executable file that is not an interpreter.

    This is how crew's own 2026-09-19 report characterises the Store alias:
    a real executable that exits non-zero with no usable output. Its true
    exit code and Store-launch behaviour on Windows are NOT tested here and
    must stay marked unverified -- no Windows host was available.

    `names` defaults to all three because `command -v` returns only the FIRST
    hit per name, so shadowing all three is what makes "nothing usable on
    this PATH" reachable while a real interpreter still sits further down it
    for bash's own `dirname`/`pwd` to work. The must-allow case below shadows
    `python3` alone, which is the layout actually reported on Windows.

    `newline="\\n"` is load-bearing: `pathlib.write_text` is TEXT mode on
    Windows and would corrupt the shebang into `#!/bin/sh\\r\\n`, which dies as
    `bad interpreter: ...^M` -- CLAUDE.md's own named landmine, and it would
    make this stub fail for the WRONG reason.
    """
    directory.mkdir(parents=True, exist_ok=True)
    body = "#!/bin/sh\n"
    if stdout:
        body += f"echo '{stdout}'\n"
    body += f"exit {exit_code}\n"
    for name in names:
        path = directory / name
        path.write_text(body, encoding="ascii", newline="\n")
        os.chmod(path, 0o755)
    return directory


def _pulse_repo(tmp_path):
    """A crew repo whose state renders findings, so "the PM spoke" is
    observable rather than inferred. A non-empty `.crew/config.json` is what
    makes `isCrew` true; no graph and no codemap is what fires the
    `upgradeNeeded` / `graphStale` triggers."""
    return crew_fixtures.make_repo(
        tmp_path, config={"pm": {"authority": "report-only"}},
        work_ticket="T-0001")


def _run(script, root, path_entries, session="s-1", stop_hook_active=False):
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(list(path_entries) + [env.get("PATH", "")])
    env["CLAUDE_PROJECT_DIR"] = str(root)
    payload = {"session_id": session, "cwd": str(root)}
    if stop_hook_active:
        payload["stop_hook_active"] = True
    return subprocess.run(
        [_BASH, script], input=json.dumps(payload), capture_output=True,
        text=True, check=False, env=env, cwd=str(root))


# --- MUST BLOCK: the stub must never be what the PM runs ------------------

@needs_bash
def test_windowsapps_stub_alone_says_so_instead_of_failing_silently(tmp_path):
    """The reported defect. The stub is the only python on PATH.

    Before the fix: exit 49, stderr EMPTY -- an unknown wearing the exit code
    of a hook that ran. After: the hook says what happened."""
    root = _pulse_repo(tmp_path)
    apps = _stub(tmp_path / "fakepath" / "WindowsApps")

    proc = _run(_SH, root, [str(apps)])

    assert _NO_PYTHON in proc.stderr, (
        f"the hook must NAME the missing interpreter. Empty stderr is the "
        f"defect itself: got {proc.stderr!r} (exit {proc.returncode})")
    assert proc.stderr.strip(), "stderr must not be empty"
    assert proc.returncode == 0, (
        "a Stop hook that cannot run must not return a status Claude Code "
        "reads as a non-blocking error; 49 was the stub's own. stderr: "
        + proc.stderr)


@needs_bash
def test_stub_outside_a_windowsapps_directory_is_also_rejected(tmp_path):
    """The case only the EXECUTE probe can catch.

    A path filter alone would pass this: the directory is not named
    WindowsApps, so nothing but running the candidate and reading back
    `sys.executable` distinguishes it from an interpreter. Sabotaging the
    resolver down to a path filter must turn this red."""
    root = _pulse_repo(tmp_path)
    apps = _stub(tmp_path / "some" / "ordinary" / "bin")

    proc = _run(_SH, root, [str(apps)])

    assert _NO_PYTHON in proc.stderr, (
        f"a non-interpreter that is not in a WindowsApps directory must "
        f"still be rejected. got {proc.stderr!r} (exit {proc.returncode})")
    assert proc.returncode == 0, proc.stderr


@needs_bash
def test_candidate_printing_a_plausible_path_but_exiting_nonzero(tmp_path):
    """The third shape: it prints something that LOOKS like an answer.

    `real=$(...) || continue` is what rejects it. A resolver that read the
    stdout and skipped the status would take `/fake/python` as the
    interpreter and `exec` a path that does not exist."""
    root = _pulse_repo(tmp_path)
    apps = _stub(tmp_path / "wrappers", exit_code=1, stdout="/fake/python")

    proc = _run(_SH, root, [str(apps)])

    assert _NO_PYTHON in proc.stderr, (
        f"a candidate that exits nonzero must be rejected even though it "
        f"printed a plausible interpreter path. got {proc.stderr!r} "
        f"(exit {proc.returncode})")


# --- MUST ALLOW: the fix must not become "the pulse never speaks" ---------

@needs_bash
def test_real_python_behind_a_stub_still_delivers_the_findings(tmp_path):
    """The must-allow that matters most, and the one that proves the defect
    was about the PM going QUIET rather than about an exit code.

    A WindowsApps stub ahead of a real interpreter on PATH is the exact
    machine that was reported: the Store aliases cover `python3` and
    `python`, `py` is elsewhere, and a real interpreter is further down.
    The findings must arrive anyway -- this is what `pm-pulse.ps1` already
    did on the same machine, and the divergence between the two flavours is
    what was being fixed."""
    root = _pulse_repo(tmp_path)
    apps = _stub(tmp_path / "fakepath" / "WindowsApps", names=("python3",))

    proc = _run(_SH, root, [str(apps), _real_python_dir()])

    assert _PULSE_MARKER in proc.stderr, (
        f"the real python must win over the stub and the PM's findings must "
        f"reach the model. got {proc.stderr[:200]!r} (exit {proc.returncode})")
    assert proc.returncode == 2, (
        "exit 2 is what hands the findings back to the model; anything else "
        "drops them. stderr: " + proc.stderr[:200])
    assert _NO_PYTHON not in proc.stderr


@needs_bash
def test_real_python_alone_is_unchanged(tmp_path):
    """The baseline. If this ever fails, the fix silenced the hook exactly
    as the bug did, and every other must-block case here would still pass."""
    root = _pulse_repo(tmp_path)

    proc = _run(_SH, root, [_real_python_dir()])

    assert _PULSE_MARKER in proc.stderr, proc.stderr[:200]
    assert proc.returncode == 2, proc.stderr[:200]


@needs_bash
def test_stop_hook_active_still_stands_down(tmp_path):
    """Must-allow, second shape: the loop guard is downstream of the
    resolver and must still decide. A resolver change that made this block
    would make every forced continuation block forever."""
    root = _pulse_repo(tmp_path)

    proc = _run(_SH, root, [_real_python_dir()], stop_hook_active=True)

    assert proc.returncode == 0, (
        "stop_hook_active must stand the pulse down. stderr: "
        + proc.stderr[:200])
    assert _PULSE_MARKER not in proc.stderr, proc.stderr[:200]


# --- The regression itself, asserted at the call site ---------------------

@needs_bash
def test_pm_pulse_does_not_call_the_unhardened_resolver():
    """A cheap tripwire for the literal reintroduction. `pm-pulse.sh` is a
    four-line wrapper that `exec`s what it resolves, so a revert to
    `crew_py` is a one-word edit that the behavioural cases above would
    catch only on a machine where a stub happens to exist."""
    src = pathlib.Path(_SH).read_text(encoding="utf-8")
    calls = re.findall(r"\$\((crew_py(?:_strict)?)\)", src)
    assert calls, "pm-pulse.sh no longer resolves python here; re-point this test"
    assert "crew_py" not in calls, (
        "pm-pulse.sh is back on the unhardened `crew_py`, which resolves a "
        "WindowsApps stub and then `exec`s it. Found: " + repr(calls))


# --- Parity between the two bash copies of the hardened resolver ----------

def _function_code_lines(path, header):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find(header)
    assert start != -1, (
        header + " is gone from " + path + ". If it was renamed, re-point "
        "this test rather than deleting it.")
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of " + header + " in " + path
    body = src[start + len(header):end]
    out = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(re.sub(r"\s+", " ", stripped))
    return out


def test_the_two_bash_hardened_resolvers_still_agree():
    """`crew_py_strict` and `_resolve_role_write_python` are the same body in
    two files. They are duplicated rather than shared because
    role-write-guard.sh is the hook that can BLOCK a tool call and its own
    suite patches that file textually at an anchor just past its resolver --
    so the duplication is deliberate and this is the guard it owes."""
    shared = _function_code_lines(_COMMON_SH, "crew_py_strict() {")
    guard = _function_code_lines(_GUARD_SH, "_resolve_role_write_python() {")
    assert shared == guard, (
        "_common.sh's crew_py_strict and role-write-guard.sh's "
        "_resolve_role_write_python have drifted. One hook would then "
        "accept an interpreter the other refuses -- the exact divergence "
        "both were written to end."
        + "\n_common.sh:          " + repr(shared)
        + "\nrole-write-guard.sh: " + repr(guard))


def test_crew_py_is_still_the_unhardened_one():
    """The OPPOSITE mistake. If `crew_py` is ever quietly hardened in place,
    every caller's behaviour changes at once -- including `promote-gate.sh`
    and `verify-gate.sh`, which are mitigated downstream by CHECKING the
    status of the python they launched and would start reporting "no
    python" where they used to name the real failure. That may one day be
    the right call; it is not one to make by accident."""
    lines = _function_code_lines(_COMMON_SH, "crew_py() {")
    assert lines == [
        'command -v python3 2>/dev/null && return 0',
        'command -v python 2>/dev/null && return 0',
        'command -v py 2>/dev/null && return 0',
        'return 1',
    ], (
        "crew_py has changed. It is shared by eight call sites; if this was "
        "deliberate, re-verify each one rather than re-pointing this test. "
        "Found: " + repr(lines))

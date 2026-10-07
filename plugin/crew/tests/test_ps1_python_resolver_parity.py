"""Cross-flavour python-resolver parity, run on LINUX -- review round on
Windows audit wave 3's `.ps1` WindowsApps-parity fix.

Confirmed directly, on this host: Linux `pwsh` classifies a `chmod +x`
POSIX-shebang file as `Get-Command`'s `Application`, so every one of these
five `.ps1` resolvers can be dot-sourced (its `Resolve-CrewPython` function
extracted, not the whole script -- the flavour guard at the top of each file
would otherwise stand it down here) and driven end-to-end with `#!/bin/sh`
stubs on PATH, the same way `test_context_watch_python_resolver.py` already
drives `_common.sh`'s `crew_py_strict` and `role-write-guard.sh`'s
`_resolve_role_write_python`. That means the regressions a review round found
in the `.ps1` twins do not have to wait for a Windows host to be caught again.

**Why `-All`, not `-First 1`, on all five.** `Select-Object -First 1` after
`Get-Command $name` briefly replaced `-All` here (Windows audit wave 3's own
follow-up). Confirmed directly (`test_get_command_returns_function_before_
application_for_the_same_name` below): a PowerShell FUNCTION of the same name
ALWAYS outranks the real Application in `Get-Command`'s own result order, so
`-First 1` can never see a real interpreter sitting behind a same-named
profile function -- and hooks.json registers every one of these hooks with no
`-NoProfile`, so a profile-defined `function python { }` is a live vector, not
a theoretical one. The identical shape costs a WindowsApps stub ahead of a
real interpreter under the SAME name further down PATH: `-First 1` tries only
the stub, the stub fails the execute-probe, and the loop moves to the NEXT
NAME rather than trying a further match for the one it just rejected. `-All`,
walking and PROBING every match for a name before giving up on it, fixes both
-- every candidate is still proved by execution before being trusted, so this
costs nothing in safety. PowerShell can enumerate every PATH match for a name;
bash's `command -v` structurally cannot (confirmed in
`test_bash_crew_py_strict_cannot_see_past_a_profile_function_shadow` below),
so the `.ps1` twins are not obligated to imitate that specific limitation --
matching `crew_py_strict`'s OUTCOME (a proved, safe interpreter or nothing)
does not require matching its exact mechanism everywhere it cannot.

Every case here that bash's `crew_py_strict` CAN also reach is cross-checked
against it on the identical PATH layout, via `_run_bash_crew_py_strict`.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_COMMON_SH = os.path.join(_SCRIPTS, "_common.sh")

_PS1_FILES = [
    "role-write-guard.ps1",
    "pm-pulse.ps1",
    "verify-gate.ps1",
    "platform-sync.ps1",
    "pm-brief.ps1",
]

_PWSH = shutil.which("pwsh")
_BASH = crew_fixtures.resolve_bash()

_needs_pwsh = pytest.mark.skipif(_PWSH is None, reason="no pwsh on PATH")
_needs_bash = pytest.mark.skipif(_BASH is None, reason="no bash on PATH")


# --------------------------------------------------------------- extraction

def _resolver_source(ps1_name):
    path = os.path.join(_SCRIPTS, ps1_name)
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find("function Resolve-CrewPython {")
    assert start != -1, "Resolve-CrewPython is gone from " + ps1_name
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of Resolve-CrewPython in " + ps1_name
    return src[start:end + 2]


def _crew_py_strict_source():
    src = pathlib.Path(_COMMON_SH).read_text(encoding="utf-8")
    start = src.find("crew_py_strict() {")
    assert start != -1, "crew_py_strict is gone from _common.sh"
    end = src.find("\n}\n", start)
    return src[start:end + 2]


# ---------------------------------------------------------------- fixtures

def _mkstub(path, body, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="ascii", newline="\n")
    os.chmod(path, mode)
    return path


def _make_tools_dir(base):
    """`tr`/`cut` only, symlinked in -- never the real system PATH. Appending
    the real PATH so bash has `tr` would also leak this host's OWN real
    python3/python into a fixture meant to have none, silently making a
    must-block case pass for the wrong reason. Mirrors
    test_verify_gate_python3_shim.py's `_NEEDED_TOOLS` convention."""
    tools = base / "_tools"
    tools.mkdir(exist_ok=True)
    for name in ("tr", "cut"):
        real = shutil.which(name)
        if real and not (tools / name).exists():
            os.symlink(real, tools / name)
    return tools


def _run_ps1(resolver_src, tmp_path, path_entries, extra_functions="", extra_env=None):
    script = tmp_path / "probe.ps1"
    script.write_text(
        resolver_src + "\n" + extra_functions + "\nWrite-Output (Resolve-CrewPython)\n",
        encoding="utf-8")
    env = {"PATH": os.pathsep.join(str(p) for p in path_entries)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)],
        env=env, capture_output=True, text=True)


def _run_bash_crew_py_strict(tools_dir, path_entries, extra_prelude=""):
    driver_src = extra_prelude + _crew_py_strict_source() + "\ncrew_py_strict\nexit $?\n"
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, newline="\n") as fh:
        fh.write(driver_src)
        driver = fh.name
    env = {"PATH": os.pathsep.join([str(p) for p in path_entries] + [str(tools_dir)])}
    try:
        return subprocess.run([_BASH, driver], capture_output=True, text=True, env=env)
    finally:
        os.unlink(driver)


# --------------------------------------------------- the mechanism proofs

@_needs_pwsh
def test_get_command_returns_function_before_application_for_the_same_name(tmp_path):
    """The proof `-All` (not `-First 1`) depends on. A PowerShell function
    named `python3` and a REAL `python3` executable coexist on PATH; Get-
    Command's own default order is asserted directly, not assumed."""
    real = _mkstub(tmp_path / "tools" / "python3", "#!/bin/sh\nexit 0\n")
    script = tmp_path / "probe.ps1"
    script.write_text(
        "function python3 { 'shadow' }\n"
        "$all = Get-Command python3 -All -ErrorAction SilentlyContinue\n"
        "Write-Output (($all | ForEach-Object { $_.CommandType }) -join ',')\n",
        encoding="utf-8")
    env = {"PATH": str(tmp_path / "tools")}
    result = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)],
                             env=env, capture_output=True, text=True)
    assert result.stdout.strip() == "Function,Application", (
        "Get-Command's own ranking changed -- re-derive whether -All is "
        "still required. stdout=" + repr(result.stdout) + " stderr=" + result.stderr)


@_needs_bash
def test_bash_crew_py_strict_cannot_see_past_a_profile_function_shadow(tmp_path):
    """The reason the `.ps1` twins are NOT obligated to match bash's exact
    mechanism for the profile-function-shadow case: bash's `command -v`
    reports only ONE match, the function, and crew_py_strict has no way to
    ask for a second. This is recorded as a fact about bash, not asserted as
    a defect -- `_run_bash_crew_py_strict`'s own docstring covers why."""
    tools = _make_tools_dir(tmp_path)
    _mkstub(tmp_path / "case" / "python3", "#!/bin/sh\nprintf '%s\\n' \"$0\"\nexit 0\n")
    result = _run_bash_crew_py_strict(
        tools, [tmp_path / "case"], extra_prelude="python3() { echo shadow; }\n")
    assert result.stdout.strip() == "" and result.returncode == 1, (
        "if this ever finds the real interpreter, bash grew a way to walk "
        "past a function shadow and the .ps1-vs-bash comparison in "
        "test_profile_function_shadow below should start asserting equality "
        "instead of just recording ps1's answer. stdout=" + repr(result.stdout))


# -------------------------------------------------------- the seven cases

@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_9009_exit_stub_is_rejected(ps1_name, tmp_path):
    """Must-block. The WindowsApps App Execution Alias's real reported exit
    status (crew's own 2026-09-19 report) with no usable output."""
    d = tmp_path / "case"
    _mkstub(d / "python3", "#!/bin/sh\nexit 9009\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    assert resolved == "", (ps1_name, resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_exit_0_empty_output_stub_is_rejected(ps1_name, tmp_path):
    """Must-block: `command -v`-style resolution alone would have accepted
    this -- it is a real, executable file that exits 0."""
    d = tmp_path / "case"
    _mkstub(d / "python3", "#!/bin/sh\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    assert resolved == "", (ps1_name, resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_store_relay_is_accepted(ps1_name, tmp_path):
    """Must-allow: the whole point of dropping the blanket WindowsApps
    match. Alias AND the real interpreter it relays to are both
    WindowsApps-rooted."""
    apps = tmp_path / "WindowsApps"
    pkg = apps / "PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"
    target = _mkstub(pkg / "python.exe", "#!/bin/sh\nexit 0\n")
    _mkstub(apps / "python3", "#!/bin/sh\nprintf '%s\\n' '" + str(target) + "'\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [apps]).stdout.strip()
    assert resolved == str(target), (ps1_name, resolved)


@_needs_pwsh
@_needs_bash
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_store_relay_matches_crew_py_strict(ps1_name, tmp_path):
    apps = tmp_path / "WindowsApps"
    pkg = apps / "PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"
    target = _mkstub(pkg / "python.exe", "#!/bin/sh\nexit 0\n")
    _mkstub(apps / "python3", "#!/bin/sh\nprintf '%s\\n' '" + str(target) + "'\nexit 0\n")
    ps1_resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [apps]).stdout.strip()
    tools = _make_tools_dir(tmp_path)
    bash_resolved = _run_bash_crew_py_strict(tools, [apps]).stdout.strip()
    assert ps1_resolved == bash_resolved == str(target), (ps1_name, ps1_resolved, bash_resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_crlf_output_is_accepted_cr_stripped(ps1_name, tmp_path):
    """Must-allow: a real native Windows interpreter run under Git Bash can
    leave a trailing \\r on its stdout."""
    d = tmp_path / "case"
    target = _mkstub(d / "realtarget", "#!/bin/sh\nexit 0\n")
    _mkstub(d / "python3", "#!/bin/sh\nprintf '" + str(target) + "\\r\\n'\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    assert resolved == str(target), (ps1_name, resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_non_executable_target_is_rejected(ps1_name, tmp_path):
    """Must-block: a real, EXISTING file that is not chmod +x. Existence
    alone (Test-Path) is not proof on a POSIX host -- matching bash's `-x`,
    which this repeats via UnixMode when $env:OS is not 'Windows_NT'."""
    d = tmp_path / "case"
    noexe = d / "data_only"
    noexe.parent.mkdir(parents=True, exist_ok=True)
    noexe.write_text("not executable", encoding="ascii")
    os.chmod(noexe, 0o644)
    _mkstub(d / "python3", "#!/bin/sh\nprintf '%s\\n' '" + str(noexe) + "'\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    assert resolved == "", (ps1_name, resolved)


@_needs_pwsh
@_needs_bash
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_non_executable_target_matches_crew_py_strict(ps1_name, tmp_path):
    d = tmp_path / "case"
    noexe = d / "data_only"
    noexe.parent.mkdir(parents=True, exist_ok=True)
    noexe.write_text("not executable", encoding="ascii")
    os.chmod(noexe, 0o644)
    _mkstub(d / "python3", "#!/bin/sh\nprintf '%s\\n' '" + str(noexe) + "'\nexit 0\n")
    ps1_resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    tools = _make_tools_dir(tmp_path)
    bash_resolved = _run_bash_crew_py_strict(tools, [d]).stdout.strip()
    assert ps1_resolved == "" and bash_resolved == "", (ps1_name, ps1_resolved, bash_resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_nonexistent_target_is_rejected_on_native_windows(ps1_name, tmp_path):
    """Must-block, and the tripwire for `Test-Path` itself being load-bearing
    on the ONE platform where it is the SOLE existence check.

    Round-2 review, 2026-09-22: on this Linux test host, `$env:OS` is never
    'Windows_NT', so the UnixMode branch always runs too and independently
    rejects a nonexistent target via its own `Get-Item` failing -- deleting
    `Test-Path` here leaves every other case in this file green, because
    nothing else exercises the ONE code path (native Windows, where
    UnixMode is skipped and Test-Path is the only check left) where that
    deletion has any effect. This test forces that path directly by
    setting `OS=Windows_NT` in the probe's own environment -- the same
    override test_context_watch.py already uses to reach Windows-only
    branches on non-Windows CI -- with a candidate that proves itself but
    reports a path that does not exist."""
    d = tmp_path / "case"
    _mkstub(d / "python3", "#!/bin/sh\nprintf '/nonexistent/python.exe\\n'\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d],
                         extra_env={"OS": "Windows_NT"}).stdout.strip()
    assert resolved == "", (ps1_name, resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_profile_function_shadow_still_resolves_the_real_interpreter(ps1_name, tmp_path):
    """Must-allow, the regression this whole review round is about: a
    PowerShell FUNCTION named python3/python (hooks.json passes no
    -NoProfile, so a profile-defined wrapper is live) must not hide a real
    interpreter under the SAME name. bash's crew_py_strict CANNOT do this
    (see test_bash_crew_py_strict_cannot_see_past_a_profile_function_shadow
    above) -- ps1's answer is recorded and asserted on its own terms, not
    cross-checked against bash for this one case."""
    d = tmp_path / "case"
    target = _mkstub(d / "python3", "#!/bin/sh\nprintf '%s\\n' \"$0\"\nexit 0\n")
    resolved = _run_ps1(
        _resolver_source(ps1_name), tmp_path, [d],
        extra_functions="function python3 { 'shadow' }\nfunction python { 'shadow' }\n"
    ).stdout.strip()
    assert resolved == str(target), (ps1_name, resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_stub_before_real_python_same_name_still_resolves(ps1_name, tmp_path):
    """Must-allow: a WindowsApps stub for `python3` ahead of a REAL `python3`
    further down PATH, with no `python`/`py` anywhere. `-First 1` rejects the
    stub and gives up on the NAME entirely; `-All` keeps walking."""
    stub_dir = tmp_path / "WindowsApps"
    real_dir = tmp_path / "tools"
    _mkstub(stub_dir / "python3", "#!/bin/sh\nexit 9009\n")
    target = _mkstub(real_dir / "python3", "#!/bin/sh\nprintf '%s\\n' \"$0\"\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [stub_dir, real_dir]).stdout.strip()
    assert resolved == str(target), (ps1_name, resolved)


@_needs_pwsh
@_needs_bash
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_stub_before_real_python_bash_rejects_but_ps1_accepts(ps1_name, tmp_path):
    """Recorded as an INTENTIONAL divergence, not a bug -- and NOT described
    as bash "failing closed" here, corrected 2026-09-22 review round:
    `crew_py_strict` itself returns nothing on this PATH (bash's `command
    -v` sees only the first match for a name and cannot retry it), but what
    that means downstream is NOT uniformly safe. `role-write-guard.sh:
    115-117` is the sharp case: `PY=$(_resolve_role_write_python) || {
    echo "...allowing it unjudged." >&2; exit 0; }` -- no python resolving
    means the write is ALLOWED, not blocked, so under `guards.roleWrites:
    block` an out-of-scope PM write on exactly this PATH shape goes through
    UNJUDGED. That is bash FAILING OPEN, the opposite of safe. `pm-pulse.sh`
    and `pm-brief.sh`/`platform-sync.sh` fail open the same way (silently
    skip). `verify-gate.sh`'s own top-level `PY=$(crew_py_strict)` is the
    one exception -- it fails CLOSED (exit 2), per its own 2026-09-22 "PM
    ruling" comment -- so "bash fails safe here" was never a blanket claim
    to begin with; role-write-guard.sh is the file where it is furthest
    from true. ps1's `-All` finding the real interpreter here is what lets
    role-write-guard.ps1 actually JUDGE the write instead of allowing it
    unjudged -- ps1 is the SAFE direction specifically because bash's
    behaviour on this exact layout is not."""
    stub_dir = tmp_path / "WindowsApps"
    real_dir = tmp_path / "tools"
    _mkstub(stub_dir / "python3", "#!/bin/sh\nexit 9009\n")
    target = _mkstub(real_dir / "python3", "#!/bin/sh\nprintf '%s\\n' \"$0\"\nexit 0\n")
    ps1_resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [stub_dir, real_dir]).stdout.strip()
    tools = _make_tools_dir(tmp_path)
    bash_resolved = _run_bash_crew_py_strict(tools, [stub_dir, real_dir]).stdout.strip()
    assert ps1_resolved == str(target), (ps1_name, ps1_resolved)
    assert bash_resolved == "", (ps1_name, bash_resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_multiline_stdout_is_rejected(ps1_name, tmp_path):
    """Must-block: crew_py_strict parity. bash's `$(...)` captures the WHOLE
    stdout as one string; an embedded newline can never equal a real file's
    path so `-x` fails structurally. PowerShell splits multi-line native
    output into an array, so this must be checked explicitly.

    Round-2 review, 2026-09-22: the FIRST line here must be a REAL,
    existing, executable file -- not `line1`, which is not a path at all
    and gets rejected by `Test-Path` regardless of whether the
    `$lines.Count -ne 1` check exists. That made this case unable to fail:
    deleting the Count check from all five resolvers still left it green
    (`$lines[0]` = `line1`, `Test-Path` on a nonexistent `line1` still
    rejects it). With a real target as the first line, deleting the Count
    check ACCEPTS it (`$lines[0]` alone passes Test-Path/UnixMode); the
    intact check rejects the whole multi-line output first, before
    `$lines[0]` is ever looked at alone."""
    d = tmp_path / "case"
    target = _mkstub(d / "realtarget", "#!/bin/sh\nexit 0\n")
    _mkstub(d / "python3", "#!/bin/sh\nprintf '" + str(target) + "\\nline2\\n'\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    assert resolved == "", (ps1_name, resolved)


@_needs_pwsh
@_needs_bash
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_multiline_stdout_matches_crew_py_strict(ps1_name, tmp_path):
    d = tmp_path / "case"
    target = _mkstub(d / "realtarget", "#!/bin/sh\nexit 0\n")
    _mkstub(d / "python3", "#!/bin/sh\nprintf '" + str(target) + "\\nline2\\n'\nexit 0\n")
    ps1_resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    tools = _make_tools_dir(tmp_path)
    bash_resolved = _run_bash_crew_py_strict(tools, [d]).stdout.strip()
    assert ps1_resolved == "" and bash_resolved == "", (ps1_name, ps1_resolved, bash_resolved)


@_needs_pwsh
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_leading_whitespace_is_rejected(ps1_name, tmp_path):
    """Must-block: crew_py_strict parity. bash never trims leading
    whitespace either -- a leading space prepended to an otherwise-real path
    fails the existence check exactly as it fails bash's `-x`, which is why
    this is not trimmed away before the existence check runs."""
    d = tmp_path / "case"
    target = _mkstub(d / "realtarget", "#!/bin/sh\nexit 0\n")
    _mkstub(d / "python3", "#!/bin/sh\nprintf '   %s\\n' '" + str(target) + "'\nexit 0\n")
    resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    assert resolved == "", (ps1_name, resolved)


@_needs_pwsh
@_needs_bash
@pytest.mark.parametrize("ps1_name", _PS1_FILES)
def test_leading_whitespace_matches_crew_py_strict(ps1_name, tmp_path):
    d = tmp_path / "case"
    target = _mkstub(d / "realtarget", "#!/bin/sh\nexit 0\n")
    _mkstub(d / "python3", "#!/bin/sh\nprintf '   %s\\n' '" + str(target) + "'\nexit 0\n")
    ps1_resolved = _run_ps1(_resolver_source(ps1_name), tmp_path, [d]).stdout.strip()
    tools = _make_tools_dir(tmp_path)
    bash_resolved = _run_bash_crew_py_strict(tools, [d]).stdout.strip()
    assert ps1_resolved == "" and bash_resolved == "", (ps1_name, ps1_resolved, bash_resolved)

"""context-watch.sh's python resolver -- the BLOCKING half of Windows audit
wave 3, re-reviewed 2026-09-22.

Reported: `context-watch.sh` resolved its interpreter with `_common.sh`'s
shared `crew_py()` -- a bare `command -v python3 || python || py` with no
filtering at all. The Windows Store App Execution Alias at
`%LOCALAPPDATA%\\Microsoft\\WindowsApps\\python3.exe` IS a real, executable
file, so `command -v` resolves it and the non-empty test passed. Every later
`"$PY" -c ...` then produced empty output -- including the config-reading
heredoc, so `CFG` came back empty -- and the old `[ -z "$CFG" ] && exit 0`
treated that identically to a repository that legitimately has no
`.crew/config.json`. The blocking Stop hook -- the one whose whole job is to
demand a handoff before the context window fills -- silently never fired.

**Every assertion here is on stderr CONTENT, never on the exit code alone**,
following `test_pm_pulse_bash_resolver.py`'s own rule: a wrong exit code with
EMPTY stderr is exactly what an exit-code-only test cannot see.

PM ruling 2026-09-22 (re-review): the first version of this fix FAILED OPEN
on a resolver failure (exit 0, loud stderr). That was REJECTED. A stderr
line on exit 0 is invisible in practice -- `auto-clear.sh:26` says so of this
exact hook's own stderr -- and "blocks forever" was never true, because
`.crew/.handoff-requested` already makes every nag this hook raises a
ONE-TIME event per session, cleared by `handoff-read.sh` at the next
SessionStart. The required shape, asserted below: resolver failure exits 2
ONCE (same severity as a real over-budget turn) and claims the marker, so the
SECOND Stop event in the same session -- resolver still broken or not --
exits 0 because the marker is already there.
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
_SH = (_ROOT + "/hooks/scripts/context-watch.sh").replace("\\", "/")
_COMMON_SH = os.path.join(_ROOT, "hooks", "scripts", "_common.sh")
_GUARD_SH = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.sh")

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

# The message the hook prints when the interpreter itself is the problem.
_NO_PYTHON = "no usable python"

# What a real, over-threshold (or interpreter-failure) run says on stderr --
# both now write the handoff instruction and claim the same marker.
_HANDOFF_MARKER = "write the handoff note to"

_MARKER_REL = os.path.join(".crew", ".handoff-requested")


def _real_python_dir():
    real = shutil.which("python3") or shutil.which("python")
    assert real, "this test needs a real python3/python on PATH to prove against"
    return os.path.dirname(real)


def _stub(directory, exit_code=9009, stdout="", names=("python3", "python", "py")):
    """A real, executable file that is not an interpreter -- the shape crew's
    own 2026-09-19 report gives the Store alias: a real executable that exits
    non-zero with no usable output.

    `newline="\\n"` is load-bearing (CLAUDE.md's CRLF-shebang landmine)."""
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


def _config(budget=100, warn_at=0.8, reserve=0):
    cfg = {"warnAt": warn_at, "budgetTokens": budget,
           "handoffPath": ".work/HANDOFF.md", "reserveTokens": reserve,
           "autoWrapUp": False}
    return {"context": cfg}


def _repo(tmp_path, **cfg_kwargs):
    return crew_fixtures.make_repo(
        tmp_path, config=_config(**cfg_kwargs), git=False)


def _run(root, path_entries, transcript_bytes, isolate_path=False):
    """`isolate_path` does NOT append the real environment's PATH behind the
    given entries. The default (append) is what every other stub case here
    wants -- the stub is on PATH ahead of a real interpreter that later
    entries would otherwise find, exactly like a live machine -- but "no
    python anywhere" needs the real system python genuinely absent, not
    merely shadowed, or this test's own PATH would silently supply one."""
    transcript = root / "transcript.jsonl"
    transcript.write_bytes(b"x" * transcript_bytes)
    payload = json.dumps({
        "transcript_path": str(transcript), "cwd": str(root),
    })
    env = os.environ.copy()
    entries = list(path_entries)
    if not isolate_path:
        entries.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(entries)
    return subprocess.run(
        [_BASH, _SH], input=payload, cwd=str(root), env=env,
        capture_output=True, text=True, check=False)


def _coreutils_only(tmp_path):
    """A PATH entry carrying ONLY the external binaries
    context-watch.sh/`_common.sh` shell out to before/without python --
    `dirname`, `cat`, `grep`, `sed` (the bash-only "cwd" and
    `context.enabled` extraction, both added so the config-existence check
    and the enabled switch work without an interpreter) and `awk` (the
    "context" block isolator) -- as symlinks to the real ones, with nothing
    named python3/python/py at all. `isolate_path=True` means this is the
    WHOLE PATH the script sees, so the script's own external-command needs
    must be satisfied here or the run fails for the wrong reason (a missing
    `grep`, not the resolver)."""
    names = ("dirname", "cat", "grep", "sed", "awk")
    reals = {name: shutil.which(name) for name in names}
    missing = [name for name, path in reals.items() if not path]
    assert not missing, f"need {missing} on PATH to build this fixture"
    bindir = tmp_path / "coreutils-only"
    bindir.mkdir()
    for name, real in reals.items():
        (bindir / name).symlink_to(real)
    return bindir


# --- MUST BLOCK: over threshold, real python, config present --------------

@needs_bash
def test_must_block_over_threshold_with_real_python(tmp_path):
    root = _repo(tmp_path, budget=100)
    # ~500 bytes clears the 80-token threshold on the size-fallback estimate.
    proc = _run(root, [_real_python_dir()], transcript_bytes=500)
    assert proc.returncode == 2, proc.stderr
    assert _HANDOFF_MARKER in proc.stderr, proc.stderr
    assert (root / _MARKER_REL).exists()


# --- MUST ALLOW: under threshold, real python -------------------------------

@needs_bash
def test_must_allow_under_threshold_with_real_python(tmp_path):
    root = _repo(tmp_path, budget=100)
    proc = _run(root, [_real_python_dir()], transcript_bytes=100)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == "", proc.stderr


# --- MUST BLOCK ONCE, MUST ALLOW AFTER: a broken interpreter ---------------
#
# PM ruling: fail CLOSED once, not open. Each stub case below is a must-block
# on the FIRST Stop event of the session and a must-allow on the second --
# the marker is what turns "once" into "not a permanent block".

@needs_bash
def test_stub_python_blocks_once_then_stands_down(tmp_path):
    """The reported defect, re-shaped by the PM ruling. The stub is the only
    python on PATH."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "fakepath" / "WindowsApps")

    first = _run(root, [str(apps)], transcript_bytes=500)
    assert first.returncode == 2, (
        "a broken interpreter must block ONCE, not fail open: " + first.stderr)
    assert _NO_PYTHON in first.stderr, (
        f"the hook must NAME the missing interpreter. got {first.stderr!r}")
    assert _HANDOFF_MARKER in first.stderr, first.stderr
    assert (root / _MARKER_REL).exists()

    second = _run(root, [str(apps)], transcript_bytes=500)
    assert second.returncode == 0, (
        "the marker must suppress the SECOND Stop event in the same "
        "session, interpreter still broken or not: " + second.stderr)


@needs_bash
def test_stub_outside_a_windowsapps_directory_also_blocks_once(tmp_path):
    """Only the EXECUTE probe catches this: the directory name gives no clue,
    so nothing but running the candidate and reading back `sys.executable`
    distinguishes it from a real interpreter."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "some" / "ordinary" / "bin")

    proc = _run(root, [str(apps)], transcript_bytes=500)

    assert proc.returncode == 2, proc.stderr
    assert _NO_PYTHON in proc.stderr, proc.stderr


@needs_bash
def test_candidate_printing_a_plausible_path_but_exiting_nonzero_blocks_once(tmp_path):
    """A wrapper that LOOKS like an answer: prints a plausible interpreter
    path and then exits non-zero. The exit-status check rejects it even
    though a path was printed."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "wrappers", exit_code=1, stdout="/fake/python")

    proc = _run(root, [str(apps)], transcript_bytes=500)

    assert proc.returncode == 2, proc.stderr
    assert _NO_PYTHON in proc.stderr, proc.stderr


@needs_bash
def test_no_python_at_all_blocks_once(tmp_path):
    """The plainer case: PATH genuinely has nothing named python3/python/py
    anywhere -- not shadowed, absent."""
    root = _repo(tmp_path, budget=100)
    bindir = _coreutils_only(tmp_path)

    proc = _run(root, [str(bindir)], transcript_bytes=500, isolate_path=True)

    assert proc.returncode == 2, proc.stderr
    assert _NO_PYTHON in proc.stderr, proc.stderr


@needs_bash
def test_real_python_behind_a_stub_still_delivers_the_warning(tmp_path):
    """Must-allow that matters most: the fix must not become "context-watch
    never fires again". A WindowsApps stub ahead of a real interpreter is the
    exact machine layout reported. Resolution SUCCEEDS here, so this is the
    normal over-threshold path, not the interpreter-failure one."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "fakepath" / "WindowsApps", names=("python3",))

    proc = _run(root, [str(apps), _real_python_dir()], transcript_bytes=500)

    assert proc.returncode == 2, proc.stderr
    assert _HANDOFF_MARKER in proc.stderr, proc.stderr
    assert _NO_PYTHON not in proc.stderr


# --- NIT: the config-existence check must run before ANY python attempt ---

@needs_bash
def test_non_crew_repo_never_attempts_python_at_all(tmp_path):
    """No `.crew/config.json` and NO python anywhere on PATH. If the config
    check ran first (as required), the hook exits 0 with EMPTY stderr -- it
    never reaches the resolver, so it never has a reason to print
    `_NO_PYTHON`. If python were still resolved first, this would either
    crash resolving `dirname`/`cat` (wrong fixture) or -- the actual old bug
    shape -- print the interpreter-failure message despite there being
    nothing here for crew to check in the first place.

    `.crew/` DOES exist here, deliberately, with no `config.json` inside it
    -- only that specific file's absence is under test. Without a `.crew/`
    directory at all, a sabotaged (python-resolved-first) run would ALSO
    exit 0 with empty stderr, but for an unrelated reason: the marker-claim
    redirect (`: > .crew/.handoff-requested`) fails when `.crew/` itself is
    missing, and that failure is silenced by its own `2>/dev/null`, before
    the interpreter-failure message is ever printed. That would make this
    test pass whether or not the real ordering fix was in place, which is
    exactly the false-confirmation shape CLAUDE.md warns about."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    bindir = _coreutils_only(tmp_path)

    proc = _run(root, [str(bindir)], transcript_bytes=500, isolate_path=True)

    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == "", (
        "a non-crew repo must exit 0 with NOTHING on stderr -- any message "
        "here means python was attempted before .crew/config.json was "
        "checked. got: " + repr(proc.stderr))


# --- FIX: a malformed "context" value must not be blamed on the interpreter

@needs_bash
def test_context_null_is_reported_as_malformed_not_interpreter(tmp_path):
    """`"context": null` used to reach `c.get(...)` on `c = None` --
    AttributeError, uncaught (the old `try: ... except Exception` wrapped
    only the line that PRODUCED `c`, not the lines that USED it) -- so the
    heredoc crashed, CFG came back empty, and the message blamed the
    interpreter for a config problem."""
    root = crew_fixtures.make_repo(
        tmp_path, config={"context": None}, git=False)
    proc = _run(root, [_real_python_dir()], transcript_bytes=500)
    assert proc.returncode == 0, proc.stderr
    assert "context" in proc.stderr and "malformed" in proc.stderr, (
        "must name the config as malformed: " + proc.stderr)
    assert "interpreter" not in proc.stderr, (
        "must NOT blame the interpreter for a config problem: " + proc.stderr)


@needs_bash
def test_context_wrong_type_is_also_reported_as_malformed(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"context": "off"}, git=False)
    proc = _run(root, [_real_python_dir()], transcript_bytes=500)
    assert proc.returncode == 0, proc.stderr
    assert "malformed" in proc.stderr, proc.stderr
    assert "interpreter" not in proc.stderr, proc.stderr


# --- The regression itself, asserted at the call site ----------------------

def _resolver_calls(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    return re.findall(r"\$\((crew_py(?:_strict)?)\)", src)


@needs_bash
def test_context_watch_does_not_call_the_unhardened_resolver():
    calls = _resolver_calls(_SH)
    assert calls, "context-watch.sh no longer resolves python here; re-point this test"
    assert "crew_py" not in calls, (
        "context-watch.sh is back on the unhardened `crew_py`, which resolves "
        "a WindowsApps stub. Found: " + repr(calls))


@pytest.mark.parametrize("script", ["pm-brief.sh", "platform-sync.sh"])
def test_thin_wrapper_hooks_do_not_call_the_unhardened_resolver(script):
    """Same tripwire, the two other scripts converted alongside
    context-watch.sh in the same pass. Both `exec` what they resolve, so a
    revert to `crew_py` is a one-word edit this static check catches on any
    machine, not only one where a stub happens to exist."""
    path = os.path.join(_ROOT, "hooks", "scripts", script)
    calls = _resolver_calls(path)
    assert calls, script + " no longer resolves python here; re-point this test"
    assert "crew_py" not in calls, (
        script + " is back on the unhardened `crew_py`. Found: " + repr(calls))


# --- Parity: crew_py_strict's tightened probe stays in sync with
#     role-write-guard.sh's own copy ----------------------------------------

def _function_code_lines(path, header):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find(header)
    assert start != -1, header + " is gone from " + path
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


def _function_raw_source(path, header):
    """UNSTRIPPED text of the function body (comments included -- harmless in
    bash, and stripping them is not needed to actually RUN the function),
    for driving it directly rather than just comparing its text."""
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find(header)
    assert start != -1, header + " is gone from " + path
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of " + header + " in " + path
    return src[start:end + 3]


def test_crew_py_strict_and_role_write_guard_still_agree_after_tightening():
    shared = _function_code_lines(_COMMON_SH, "crew_py_strict() {")
    guard = _function_code_lines(_GUARD_SH, "_resolve_role_write_python() {")
    assert shared == guard, (
        "_common.sh's crew_py_strict and role-write-guard.sh's "
        "_resolve_role_write_python have drifted after the `-x` tightening."
        + "\n_common.sh:          " + repr(shared)
        + "\nrole-write-guard.sh: " + repr(guard))


# --- BLOCK item: the `-x` check needs a BEHAVIOURAL test, not just a
#     textual one. A static "is this string present anywhere in the
#     function" check (the previous version of this test) still passes even
#     if `[ -x "$real" ] || continue` is moved to AFTER `return 0`, where it
#     can never execute -- the check has no runtime effect there. These run
#     the real function, in a real bash subprocess, against a candidate that
#     prints a REAL, EXISTING, but NON-EXECUTABLE file. That must be rejected
#     only if the `-x` test actually runs before the return.
#
#     Verified by sabotage as part of this change (not asserted by any test,
#     since asserting "the function's own text is in a particular physical
#     order" is exactly the trap being fixed): moving the `[ -x ... ]` line to
#     immediately before `return 1` at the end of the loop body -- past
#     `return 0` -- turns both cases below red.

@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_rejects_a_real_but_non_executable_target(tmp_path, path, header, fn):
    """The candidate on PATH prints a path to a file that genuinely EXISTS
    (so a check that only tests `-n`, or that never runs at all, would
    accept it) but is NOT executable (chmod 644). Must be rejected."""
    target = tmp_path / "not-actually-runnable"
    target.write_text("not a real interpreter\n", encoding="utf-8")
    os.chmod(target, 0o644)
    assert not os.access(target, os.X_OK), "fixture must not be executable"

    # ALL THREE names, matching `_stub()`'s own default -- if only "python3"
    # pointed at the broken target, `crew_py_strict`'s own for-loop would
    # correctly fall through to a real "python"/"py" further down PATH and
    # this test would prove nothing about the `-x` check specifically.
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    body = "#!/bin/sh\n" f"printf '%s\\n' '{target}'\n" "exit 0\n"
    for name in ("python3", "python", "py"):
        stub = stub_dir / name
        stub.write_text(body, encoding="ascii", newline="\n")
        os.chmod(stub, 0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    # The real PATH stays behind the stubs -- `tr` (used unconditionally by
    # the CR-strip step) must resolve, and the stubs still win as the first
    # match for every name either way.
    env["PATH"] = os.pathsep.join([str(stub_dir), env.get("PATH", "")])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env)
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:1", (
        f"a non-executable target must be REJECTED (return 1). "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert not printed, (
        "must print nothing when rejecting: " + repr(printed))


# --- FIX: the probe's output must be CR-stripped before the `-x` test ------

@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_accepts_a_crlf_terminated_real_interpreter(tmp_path, path, header, fn):
    """A real interpreter whose stdout keeps a trailing \\r (Git Bash on a
    native Windows python.exe) must still be ACCEPTED. Before the fix,
    `-x "$real"` tested a path with a stray \\r appended, which never
    matches an actual file, and every real Windows interpreter behind this
    combination was rejected."""
    real = shutil.which("python3") or shutil.which("python")
    assert real, "need a real python3/python for this fixture"

    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    stub = stub_dir / "python3"
    # A literal CR before the newline -- printf '%s\r\n' does exactly what a
    # CRLF-terminated write would look like once it reaches bash's $().
    stub.write_text(
        "#!/bin/sh\n" f"printf '%s\\r\\n' '{real}'\n" "exit 0\n",
        encoding="ascii", newline="\n")
    os.chmod(stub, 0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(stub_dir), env.get("PATH", "")])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env)
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l.rstrip("\r") for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:0", (
        f"a real interpreter behind a CRLF-terminated probe result must be "
        f"ACCEPTED. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert printed == [real], (
        f"must return the interpreter path with the CR stripped. "
        f"got {printed!r}")


# --- FIX (round-3 review, integration): a native Windows `sys.executable`
#     (e.g. `C:\fakepy\python.exe`) must be normalised into a form THIS
#     shell can stat before `-x` runs on it. `cygpath` is absent on a plain
#     Linux test host, so the resolver's fallback path (backslash ->
#     forward-slash) is what these fixtures exercise -- the same shape a
#     merging lane's own fixture uses (a real file at a RELATIVE path
#     literally named `C:/fakepy/python.exe` under the driver's cwd).

_HAS_CYGPATH = shutil.which("cygpath") is not None
_cygpath_absent = pytest.mark.skipif(
    _HAS_CYGPATH, reason="cygpath present -- these fixtures assume the tr fallback")


@needs_bash
@_cygpath_absent
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_accepts_a_native_windows_drive_letter_path(tmp_path, path, header, fn):
    """Must-allow. Without `cygpath`, `-x` cannot see an ABSOLUTE Windows
    drive as a real path on Linux at all -- so this fabricates the only
    thing that CAN prove the normalisation ran: a directory literally named
    `C:`, holding `fakepy/python.exe`, resolved as a path RELATIVE to the
    driver's cwd once backslashes become forward slashes."""
    target_dir = tmp_path / "C:" / "fakepy"
    target_dir.mkdir(parents=True)
    target = target_dir / "python.exe"
    target.write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")
    os.chmod(target, 0o755)

    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    body = "#!/bin/sh\nprintf '%s\\n' 'C:\\fakepy\\python.exe'\nexit 0\n"
    for name in ("python3", "python", "py"):
        stub = stub_dir / name
        stub.write_text(body, encoding="ascii", newline="\n")
        os.chmod(stub, 0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(stub_dir), env.get("PATH", "")])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env, cwd=str(tmp_path))
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:0", (
        f"a native Windows drive-letter path to a real, executable target "
        f"must be ACCEPTED. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert printed == ["C:/fakepy/python.exe"], (
        f"must return the backslash-normalised path. got {printed!r}")


@needs_bash
@_cygpath_absent
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_rejects_a_native_windows_drive_letter_path_to_a_non_executable_target(
        tmp_path, path, header, fn):
    """Must-block: normalisation is not a bypass of the executability check
    -- a native-Windows-shaped path to a real but non-executable file must
    still be rejected."""
    target_dir = tmp_path / "C:" / "fakepy"
    target_dir.mkdir(parents=True)
    target = target_dir / "python.exe"
    target.write_text("not a real interpreter\n", encoding="utf-8")
    os.chmod(target, 0o644)

    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    body = "#!/bin/sh\nprintf '%s\\n' 'C:\\fakepy\\python.exe'\nexit 0\n"
    for name in ("python3", "python", "py"):
        stub = stub_dir / name
        stub.write_text(body, encoding="ascii", newline="\n")
        os.chmod(stub, 0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(stub_dir), env.get("PATH", "")])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env, cwd=str(tmp_path))
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:1", (
        f"a non-executable target must still be REJECTED after drive-letter "
        f"normalisation. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert not printed, "must print nothing when rejecting: " + repr(printed)


# --- FIX (round-3 review): context.enabled must be honoured even when
#     python is unusable -- fail-closed-once is for an UNKNOWN state, and an
#     explicitly disabled hook is a KNOWN one. Before this fix the
#     fail-closed branch ran before context.enabled was ever read.

@needs_bash
def test_context_disabled_with_broken_python_stands_down_silently(tmp_path):
    root = crew_fixtures.make_repo(
        tmp_path, config={"context": {"enabled": False}}, git=False)
    # `_coreutils_only` now carries every external binary this fallback path
    # itself depends on (grep/sed for cwd, awk+grep for the enabled check) --
    # not "only dirname and cat", which stopped being the true dependency
    # set once the cwd-extraction and enabled-check fixes below were added.
    bindir = _coreutils_only(tmp_path)
    proc = _run(root, [str(bindir)], transcript_bytes=500, isolate_path=True)
    assert proc.returncode == 0, proc.stderr


# --- FIX (round-3 review): the JSON payload's "cwd" must win over
#     $CLAUDE_PROJECT_DIR again, restoring the ORIGINAL priority order --
#     the config-existence-before-python reordering must not silently start
#     ignoring a crew repo nested under the project root.

@needs_bash
def test_nested_repo_cwd_from_json_wins_over_claude_project_dir(tmp_path):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    (inner / ".crew").mkdir(parents=True)
    (inner / ".crew" / "config.json").write_text(
        json.dumps(_config(budget=100)), encoding="utf-8")
    transcript = inner / "transcript.jsonl"
    transcript.write_bytes(b"x" * 500)  # clears the threshold, as elsewhere
    payload = json.dumps({"transcript_path": str(transcript), "cwd": str(inner)})
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([_real_python_dir(), env.get("PATH", "")])
    env["CLAUDE_PROJECT_DIR"] = str(outer)
    proc = subprocess.run(
        [_BASH, _SH], input=payload, cwd=str(outer), env=env,
        capture_output=True, text=True, check=False)
    assert proc.returncode == 2, (
        "the nested repo at input cwd=outer/inner must still be checked and "
        "nagged, not silently missed by looking only at "
        "$CLAUDE_PROJECT_DIR=outer: " + proc.stderr)
    assert _HANDOFF_MARKER in proc.stderr, proc.stderr
    assert (inner / _MARKER_REL).exists()

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
import uuid

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


def _run(root, path_entries, transcript_bytes, isolate_path=False,
         stop_hook_active=False):
    """`isolate_path` does NOT append the real environment's PATH behind the
    given entries. The default (append) is what every other stub case here
    wants -- the stub is on PATH ahead of a real interpreter that later
    entries would otherwise find, exactly like a live machine -- but "no
    python anywhere" needs the real system python genuinely absent, not
    merely shadowed, or this test's own PATH would silently supply one.

    `stop_hook_active` mirrors what Claude Code sets to `true` on the
    FORCED-CONTINUATION retry it fires automatically after an exit-2 block --
    round-4 review: this must now be honoured BEFORE any resolver work, so a
    broken interpreter's retry stands down instead of blocking (and
    marker-claiming) a second time."""
    transcript = root / "transcript.jsonl"
    transcript.write_bytes(b"x" * transcript_bytes)
    payload = json.dumps({
        "transcript_path": str(transcript), "cwd": str(root),
        "stop_hook_active": stop_hook_active,
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


# --- MUST BLOCK on a real Stop, MUST ALLOW on the forced-continuation retry,
#     NEVER claim $MARKER: a broken interpreter ----------------------------
#
# PM ruling: fail CLOSED, not open. Round-4 review (merged-branch,
# BLOCK-adjacent): the marker-based "must-allow on the SECOND same-session
# call" shape these tests had was itself the bug -- this branch is no longer
# allowed to touch `.crew/.handoff-requested` at all, in either direction
# (see context-watch.sh's own header comment on that branch for the full
# reasoning: a zero-byte marker claimed here, with nothing measured, is what
# let context-watch.ps1 and auto-clear.ps1 stand down and /clear a session
# at low context on Windows). What now bounds the repeat is
# `stop_hook_active`, checked FIRST, before any resolver work -- so every
# case below is must-block on a REAL Stop event and must-allow on the
# FORCED-CONTINUATION retry Claude Code fires after that block, and every
# must-block case also asserts the marker was never written.

@needs_bash
def test_stub_python_blocks_on_a_real_stop_without_claiming_the_marker(tmp_path):
    """The reported defect, re-shaped by the round-4 review. The stub is the
    only python on PATH."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "fakepath" / "WindowsApps")

    proc = _run(root, [str(apps)], transcript_bytes=500)
    assert proc.returncode == 2, (
        "a broken interpreter must block on a real Stop event: " + proc.stderr)
    assert _NO_PYTHON in proc.stderr, (
        f"the hook must NAME the missing interpreter. got {proc.stderr!r}")
    assert not (root / _MARKER_REL).exists(), (
        "an interpreter error must NEVER claim .crew/.handoff-requested -- "
        "that marker means 'the context window was measured and is over "
        "budget', which did not happen here")


@needs_bash
def test_stub_python_stands_down_on_the_forced_continuation_retry(tmp_path):
    """Must-allow: the SAME broken stub, but `stop_hook_active: true` --
    Claude Code's own retry after the block above. Checked FIRST, before the
    resolver ever runs, so this must be silent (exit 0, no message) even
    though the interpreter is exactly as broken as the must-block case."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "fakepath" / "WindowsApps")

    proc = _run(root, [str(apps)], transcript_bytes=500, stop_hook_active=True)
    assert proc.returncode == 0, (
        "stop_hook_active must stand this down before the resolver runs: "
        + proc.stderr)
    assert proc.stderr.strip() == "", proc.stderr
    assert not (root / _MARKER_REL).exists()


@needs_bash
def test_stub_outside_a_windowsapps_directory_also_blocks_without_a_marker(tmp_path):
    """Only the EXECUTE probe catches this: the directory name gives no clue,
    so nothing but running the candidate and reading back `sys.executable`
    distinguishes it from a real interpreter."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "some" / "ordinary" / "bin")

    proc = _run(root, [str(apps)], transcript_bytes=500)

    assert proc.returncode == 2, proc.stderr
    assert _NO_PYTHON in proc.stderr, proc.stderr
    assert not (root / _MARKER_REL).exists()


@needs_bash
def test_candidate_printing_a_plausible_path_but_exiting_nonzero_blocks_without_a_marker(tmp_path):
    """A wrapper that LOOKS like an answer: prints a plausible interpreter
    path and then exits non-zero. The exit-status check rejects it even
    though a path was printed."""
    root = _repo(tmp_path, budget=100)
    apps = _stub(tmp_path / "wrappers", exit_code=1, stdout="/fake/python")

    proc = _run(root, [str(apps)], transcript_bytes=500)

    assert proc.returncode == 2, proc.stderr
    assert _NO_PYTHON in proc.stderr, proc.stderr
    assert not (root / _MARKER_REL).exists()


@needs_bash
def test_no_python_at_all_blocks_without_a_marker(tmp_path):
    """The plainer case: PATH genuinely has nothing named python3/python/py
    anywhere -- not shadowed, absent."""
    root = _repo(tmp_path, budget=100)
    bindir = _coreutils_only(tmp_path)

    proc = _run(root, [str(bindir)], transcript_bytes=500, isolate_path=True)

    assert proc.returncode == 2, proc.stderr
    assert _NO_PYTHON in proc.stderr, proc.stderr
    assert not (root / _MARKER_REL).exists()


@needs_bash
def test_no_python_at_all_stands_down_on_the_forced_continuation_retry(tmp_path):
    root = _repo(tmp_path, budget=100)
    bindir = _coreutils_only(tmp_path)

    proc = _run(root, [str(bindir)], transcript_bytes=500, isolate_path=True,
                stop_hook_active=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.strip() == "", proc.stderr
    assert not (root / _MARKER_REL).exists()


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


# --- FIX (round-6 review): crew_py_strict must not reject any path
#     containing "WindowsApps" -- a genuine Microsoft Store Python install
#     runs from EXACTLY that shape (the alias itself, AND the real
#     interpreter it relays to, both live under a WindowsApps-rooted
#     directory), so the old blanket substring check rejected a machine
#     where python plainly works, on every turn, forever. The stub check
#     must reject the ALIAS STUB specifically (no output / non-zero exit),
#     not the path.

@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_accepts_a_store_python_alias_relaying_to_a_real_interpreter(
        tmp_path, path, header, fn):
    """Must-allow: the reviewer's reported shape. `command -v python3`
    resolves the alias under `.../Microsoft/WindowsApps/python3`; the alias
    `exec`s a real interpreter one level further down, itself ALSO under a
    WindowsApps-rooted path (`.../WindowsApps/PythonSoftwareFoundation.
    Python.3.x_<hash>/python.exe`, the real shape a Store install uses).
    Both paths contain "WindowsApps" -- proving this is no longer rejected
    on that substring alone."""
    apps_dir = tmp_path / "Microsoft" / "WindowsApps"
    apps_dir.mkdir(parents=True)
    pkg_dir = apps_dir / "PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0"
    pkg_dir.mkdir()
    target = pkg_dir / "python.exe"
    # Prints its OWN invocation path (`$0`) rather than a value hard-coded in
    # the test -- what `exec` from the alias hands it is the real proof this
    # relay actually ran, not an assumption about path formatting.
    target.write_text("#!/bin/sh\nprintf '%s\\n' \"$0\"\nexit 0\n",
                       encoding="ascii", newline="\n")
    os.chmod(target, 0o755)

    alias = apps_dir / "python3"
    alias.write_text(
        '#!/bin/sh\nexec "$(dirname "$0")/'
        'PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe" "$@"\n',
        encoding="ascii", newline="\n")
    os.chmod(alias, 0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(apps_dir), env.get("PATH", "")])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env)
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:0", (
        f"a Store-Python alias relaying to a real interpreter under "
        f"WindowsApps must be ACCEPTED. stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}")
    assert printed == [str(target)], (
        f"must return the real interpreter's own path. got {printed!r}")


@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_rejects_a_windowsapps_alias_stub_with_no_real_python(
        tmp_path, path, header, fn):
    """Must-block: the SAME WindowsApps-rooted location, but no real
    interpreter behind it -- the placeholder alias, which produces no usable
    output and exits non-zero (9009, matching crew's own 2026-09-19 report of
    the real Store alias's behaviour) rather than relaying anywhere. What
    must reject this is the exec-and-probe, NOT a path check -- there is no
    WindowsApps substring check left to reject it on location alone."""
    apps_dir = tmp_path / "Microsoft" / "WindowsApps"
    apps_dir.mkdir(parents=True)
    for name in ("python3", "python", "py"):
        stub = apps_dir / name
        stub.write_text("#!/bin/sh\nexit 9009\n", encoding="ascii", newline="\n")
        os.chmod(stub, 0o755)

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(apps_dir), env.get("PATH", "")])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env)
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:1", (
        f"a WindowsApps alias stub with no real interpreter behind it must "
        f"be REJECTED. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert not printed, "must print nothing when rejecting: " + repr(printed)


# --- FIX (round-3 review, integration; round-4 NIT on the fallback shape):
#     a native Windows `sys.executable` (e.g. `C:\fakepy\python.exe`) must be
#     normalised into a form THIS shell can stat before `-x` runs on it.
#     `cygpath` is absent on a plain Linux test host, so the resolver's
#     fallback path is what these fixtures exercise. That fallback was
#     ROUND-4-FIXED to produce an ABSOLUTE path (`/c/fakepy/python.exe`, the
#     same shape `cygpath -u` would give), not the earlier relative
#     `C:/fakepy/python.exe` -- a relative result depends on the RESOLVER'S
#     OWN cwd at the moment `-x` runs, and any `cd` between here and the
#     caller (there are several, in both context-watch.sh and
#     role-write-guard.sh) silently breaks it.
#
#     That absoluteness is also why these fixtures changed shape entirely:
#     the OLD tests proved the transform by fabricating a directory literally
#     named `C:` UNDER `tmp_path` and relying on the RELATIVE interpretation
#     to land there. The NEW output is absolute (`/c/...`), so nothing under
#     `tmp_path` can ever satisfy it -- and creating a real `/c/fakepy/...`
#     at the actual filesystem root to make `-x` succeed would touch the
#     real machine outside any throwaway fixture, which CLAUDE.md's test
#     suites are never allowed to do. Split into three narrower claims
#     instead, none of which needs that: the STRING the transform produces
#     (`test_drive_letter_fallback_produces_an_absolute_path`, no filesystem
#     involved at all), that the full resolver genuinely evaluates `-x`
#     against that absolute string rather than skipping it
#     (`test_resolver_rejects_a_native_windows_path_with_no_real_target`,
#     must-block against a target that provably does not exist on ANY
#     non-Windows host), and a real must-allow behavioural case gated on a
#     `/c` mount already existing (true on WSL and on Git Bash's own view of
#     the filesystem, false and therefore skipped everywhere else, including
#     in this container).

_HAS_CYGPATH = shutil.which("cygpath") is not None
_cygpath_absent = pytest.mark.skipif(
    _HAS_CYGPATH, reason="cygpath present -- these fixtures assume the tr fallback")

# True on a real Windows/WSL host where /c IS the C: drive; false (and
# therefore these specific must-allow cases skip) everywhere else, including
# this container. Never created if absent -- see the header comment above.
_HAS_C_MOUNT = os.path.isdir("/c") and os.access("/c", os.W_OK)


def _drive_letter_normaliser_source(path):
    """Just the `case "$real" in [A-Za-z]:...) ... esac` block, NOT the whole
    resolver function -- lets the transform's OUTPUT STRING be asserted on
    directly, without also needing `-x` to pass against a real file."""
    src = pathlib.Path(path).read_text(encoding="utf-8")
    marker = 'case "$real" in\n      [A-Za-z]:\\\\*|[A-Za-z]:/*)'
    start = src.find(marker)
    assert start != -1, "drive-letter case block not found in " + path
    end = src.find("\n    esac\n", start)
    assert end != -1, "could not find the end of the drive-letter case block in " + path
    return src[start:end + len("\n    esac")]


@needs_bash
@_cygpath_absent
@pytest.mark.parametrize("path", [_COMMON_SH, _GUARD_SH])
def test_drive_letter_fallback_produces_an_absolute_path(tmp_path, path):
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "real='C:\\fakepy\\python.exe'\n"
        + _drive_letter_normaliser_source(path) + "\n"
        'printf \'%s\\n\' "$real"\n',
        encoding="utf-8", newline="\n")
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True, check=False)
    assert proc.stdout.strip() == "/c/fakepy/python.exe", (
        f"the no-cygpath fallback must yield an ABSOLUTE /c/... path, not a "
        f"relative C:/... one that depends on the caller's cwd. "
        f"got {proc.stdout!r} stderr={proc.stderr!r}")


@needs_bash
@_cygpath_absent
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_rejects_a_native_windows_path_with_no_real_target(tmp_path, path, header, fn):
    """Must-block: proves the FULL resolver actually runs `-x` against the
    normalised absolute path rather than skipping the check once a drive
    letter is seen. `/c/<unique token>/python.exe` cannot exist on any
    non-Windows host -- the token is derived from `tmp_path` PLUS a uuid
    suffix, not `tmp_path` alone: `tmp_path`'s own basename repeats
    identically across separate pytest runs (it is numbered relative to a
    per-session parent directory, which the basename strips off), so a
    leftover `/c/<token>` from a run of the must-allow test below that was
    killed before its `finally: shutil.rmtree` ran would otherwise make
    THIS test's "must not exist" assumption false on the very next run."""
    token = os.path.basename(str(tmp_path)) + "-" + uuid.uuid4().hex[:8]
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    body = f"#!/bin/sh\nprintf '%s\\n' 'C:\\{token}\\python.exe'\nexit 0\n"
    for name in ("python3", "python", "py"):
        stub = stub_dir / name
        stub.write_text(body, encoding="ascii", newline="\n")
        os.chmod(stub, 0o755)

    assert not os.path.exists(f"/c/{token}/python.exe"), (
        "fixture assumption violated: this path must not exist")

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
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:1", (
        f"a native Windows path with no corresponding real file must be "
        f"REJECTED. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert not printed, "must print nothing when rejecting: " + repr(printed)


@needs_bash
@_cygpath_absent
@pytest.mark.skipif(not _HAS_C_MOUNT, reason="no /c mount on this host (expected off Windows/WSL)")
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_accepts_a_native_windows_path_to_a_real_target_under_c(tmp_path, path, header, fn):
    """Must-allow, real end-to-end: only runs where `/c` is ALREADY a real
    mount (WSL, or Git Bash's own view of the C: drive) -- never created,
    only used, and only a throwaway subdirectory under it, cleaned up after
    like any other tmp fixture.

    The token carries a uuid suffix, not just `tmp_path`'s own basename:
    that basename repeats identically across separate pytest runs (pytest
    numbers it relative to a per-session parent directory, which the
    basename strips off), so a run killed before the `finally:
    shutil.rmtree` below could run left this exact directory behind, and
    the next run's bare `mkdir(parents=True)` (deliberately with no
    `exist_ok` -- see below) then raised FileExistsError on its own
    leftover rather than on a genuine collision. The guarantee that this
    never touches a pre-existing directory of the REAL user's stays: a
    uuid-suffixed name cannot collide with one the user already had."""
    token = os.path.basename(str(tmp_path)) + "-" + uuid.uuid4().hex[:8]
    target_dir = pathlib.Path(f"/c/{token}")
    # NO exist_ok - see the docstring above: a genuine collision (now
    # vanishingly unlikely, with the uuid suffix) must still be loud rather
    # than silently reused and then deleted in the `finally` block below.
    target_dir.mkdir(parents=True)
    try:
        target = target_dir / "python.exe"
        target.write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")
        os.chmod(target, 0o755)

        stub_dir = tmp_path / "stubs"
        stub_dir.mkdir()
        body = "#!/bin/sh\n" f"printf '%s\\n' 'C:\\{token}\\python.exe'\n" "exit 0\n"
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
            check=False, env=env)
        lines = proc.stdout.splitlines()
        exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
        printed = [l for l in lines if not l.startswith("EXIT:")]
        assert exit_line == "EXIT:0", (
            f"a native Windows path to a real, executable target under a "
            f"real /c mount must be ACCEPTED. stdout={proc.stdout!r} "
            f"stderr={proc.stderr!r}")
        assert printed == [f"/c/{token}/python.exe"], (
            f"must return the normalised absolute path. got {printed!r}")
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


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
    assert not (root / _MARKER_REL).exists()


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

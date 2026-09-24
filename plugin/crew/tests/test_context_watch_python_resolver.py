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
import time

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

# Keyed on the session since the auto-cycle fix; these payloads carry no
# session_id, so this is the documented fallback key.
_MARKER_REL = os.path.join(".crew", ".handoff-requested-nosession")


def _python_free_path(base):
    """The host's /usr/bin and /bin as symlinks, MINUS anything named
    python*/py*. The resolvers walk EVERY PATH match of every name since the
    burn-in FAIL 3 fix, so a stub fixture can no longer shadow the host's
    real interpreter by merely sitting ahead of it on PATH -- the walk would
    carry on past the stub and find it. Cases that mean "no working python"
    append this instead of the real PATH."""
    tools = pathlib.Path(base) / "python-free-bin"
    if tools.is_dir():
        return str(tools)
    tools.mkdir(parents=True)
    for source in ("/usr/bin", "/bin"):
        if not os.path.isdir(source):
            continue
        for name in os.listdir(source):
            if name.startswith(("python", "py")) or (tools / name).exists():
                continue
            os.symlink(os.path.join(source, name), tools / name)
    return str(tools)


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
    env = dict(os.environ, HOME=str(root), CREW_AUTOCLEAR_INHIBIT="1")
    entries = list(path_entries)
    if not isolate_path:
        entries.append(_python_free_path(root.parent))
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


@pytest.mark.parametrize("script", ["platform-sync.sh", "crew-context.sh"])
def test_thin_wrapper_hooks_do_not_call_the_unhardened_resolver(script):
    """Same tripwire, for the thin wrappers converted alongside
    context-watch.sh (pm-brief.sh was the other one until crew 1.0 deleted
    it; crew-context.sh took its SessionStart slot). Both hand off what they resolve, so a
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


def _bash_has_cygpath():
    """Whether `_BASH` ITSELF can find `cygpath` -- asked by running
    `command -v cygpath` inside that bash, never by `shutil.which` in this
    python process. Burn-in FAIL 3/4: those two answers can genuinely
    differ under Git Bash on native Windows. `bash.exe` is an MSYS program
    and prepends its own compiled-in `/usr/bin`-equivalent to whatever PATH
    it inherits before resolving any command, so it finds `cygpath.exe`
    there even when the PARENT process's PATH (what a native `python.exe`
    running pytest sees, and all `shutil.which` can ever consult) does not
    list that directory at all -- Git for Windows' installer adds `<git>\\
    cmd` and `<git>\\bin` to the system PATH, not `<git>\\usr\\bin`, on
    purpose, specifically so it does not expose the full unix toolchain to
    native Windows programs. Asking bash directly is what keeps this
    process's notion of "cygpath exists" in sync with the resolver's own."""
    if _BASH is None:
        return False
    proc = subprocess.run([_BASH, "-c", "command -v cygpath"],
                           capture_output=True, text=True, check=False)
    return proc.returncode == 0 and proc.stdout.strip() != ""


_HAS_CYGPATH = _bash_has_cygpath()


def _posix_form(path_str):
    """The path string the resolver's OWN shell would see, mirroring
    MSYS/Cygwin's path translation (mount table included) instead of
    guessing at a manual backslash swap. On native Windows Python, a
    subprocess's PATH and argv are translated by the MSYS runtime through
    its compiled-in mount table before bash ever sees them -- e.g. this
    machine's `/tmp` is mounted to the same directory pytest's `tmp_path`
    resolves under (`D:\\temp`), so `D:\\temp\\...` and `/tmp/...` name the
    SAME file, and a bare string comparison between a Windows-style path and
    what a bash subprocess prints back is comparing two spellings of one
    path, not two different paths. `cygpath -u` (shipped next to Git Bash)
    performs the exact same translation, so it is used here rather than a
    hand-rolled one that would not know about that mount. On a platform
    where the string is already POSIX-shaped (no drive letter -- Linux,
    macOS, or when `_BASH` is not a Windows Git Bash), there is no
    translation layer to account for and the string is returned unchanged.

    Two things burn-in FAIL 3/4 got wrong about the previous version of this
    function, both now fixed:

    1. It asked `shutil.which("cygpath")`, this process's own view of PATH,
       rather than `_bash_has_cygpath()` -- see that function's docstring
       for why those two can disagree on the exact host this test exists
       to cover.
    2. When cygpath was NOT found, it gave up and returned the path
       UNCHANGED (native-shaped) -- but the resolver's own fallback, run
       through `_BASH` here via `cygpath`, DOES NOT give up: `_common.sh`'s
       `crew_py_strict` and `role-write-guard.sh`'s
       `_resolve_role_write_python` both hand-roll the identical conversion
       (lower-case the drive letter, drop the colon, backslash to forward
       slash, leading `/`) when `command -v cygpath` fails, and STILL
       return a POSIX-shaped path. An expectation that quietly reverts to
       "no conversion" in that branch is exactly backwards from what the
       resolver under test actually does, and the mismatch this produced
       (resolver: POSIX; test expectation: native) is FAIL 3/4 verbatim.
    """
    if not (len(path_str) >= 2 and path_str[1] == ":"):
        return path_str
    if _bash_has_cygpath():
        out = subprocess.run([_BASH, "-c", 'cygpath -u "$1"', "_", path_str],
                              capture_output=True, text=True,
                              check=False).stdout.strip()
        return out or path_str
    # Mirror the resolver's own no-cygpath fallback exactly (see the case
    # statement in `_common.sh:crew_py_strict` / `role-write-guard.sh:
    # _resolve_role_write_python`): "C:\\fakepy\\python.exe" -> "/c/fakepy/python.exe".
    drive = path_str[0].lower()
    rest = path_str[2:].replace("\\", "/")
    return "/" + drive + rest


def _is_executable_via_shell(path):
    """`os.access(path, os.X_OK)` is not reliable evidence on native Windows
    Python: Windows has no POSIX execute bit, `os.chmod` there only ever
    toggles the read-only DOS attribute, and an existing file reads back as
    X_OK regardless of the mode requested. The fixtures below need to know
    whether the SAME bash that runs the resolver under test would reject the
    file with `[ -x ... ]` -- which it reliably does even when Python's own
    `os.access` cannot tell the difference -- so ask that bash directly
    instead of trusting the Windows-side `os.access` result."""
    if _BASH is None:
        return os.access(path, os.X_OK)
    proc = subprocess.run([_BASH, "-c", '[ -x "$1" ]', "_", str(path)],
                           capture_output=True, check=False)
    return proc.returncode == 0


def test_crew_py_strict_and_role_write_guard_still_agree_after_tightening():
    shared = _function_code_lines(_COMMON_SH, "crew_py_strict() {")
    guard = _function_code_lines(_GUARD_SH, "_resolve_role_write_python() {")
    assert shared == guard, (
        "_common.sh's crew_py_strict and role-write-guard.sh's "
        "_resolve_role_write_python have drifted after the `-x` tightening."
        + "\n_common.sh:          " + repr(shared)
        + "\nrole-write-guard.sh: " + repr(guard))


# --- FIX (Codex review of crew-1.0, item 1): the "memoized within this
#     process" caching crew 1.0 r3 added never survives a caller -- every
#     call site resolves these functions as `PY=$(crew_py...)`, and a
#     `$(...)` command substitution runs the function in a SUBSHELL, so
#     whatever cache variable it set is discarded the instant that subshell
#     exits. Reproduced by hand: `source _common.sh; p=$(crew_py_strict);
#     [ -n "$_CREW_PY_STRICT_MEMO_DONE" ]` is FALSE in the caller's own
#     shell -- the cache never once did anything. Removed rather than made
#     real: doing that would mean rewriting every `$(crew_py...)` call site
#     in this directory (and role-write-guard.sh's own single subshelled
#     call) to avoid a subshell, for a saving that never actually happened.
#     STATIC, not behavioural: there is nothing a caching optimisation that
#     never fires can be proven to do at runtime -- the claim itself is
#     what must be gone.

def test_crew_py_no_longer_claims_a_dead_memo():
    body = _function_raw_source(_COMMON_SH, "crew_py() {")
    assert "MEMO" not in body, (
        "crew_py() still carries memoization variables that cannot survive "
        "its own call site (`PY=$(crew_py)`, a subshell): " + body)


@pytest.mark.parametrize("path,header", [
    (_COMMON_SH, "crew_py_strict() {"),
    (_GUARD_SH, "_resolve_role_write_python() {"),
])
def test_crew_py_strict_and_its_byte_copy_no_longer_claim_a_dead_memo(path, header):
    body = _function_raw_source(path, header)
    assert "MEMO" not in body, (
        f"{path} still carries a memoization for `{header}` that cannot "
        f"survive its own call site (a `$(...)` subshell): {body!r}")


# --- FIX (Codex review of crew-1.0, item 2): the overall 8s deadline was
#     only checked before LAUNCHING a candidate; the probe itself then
#     waited a flat 3s regardless of how much budget was left, so several
#     candidates that each fail just under that per-candidate bound --
#     summing to just under the 8s deadline -- followed by one that hangs
#     could still overrun both the 8s deadline and the 10s hook timeout
#     that calls this (bridge-status.ps1's twin). The fix caps each probe's
#     wait to whatever budget remains, not a flat 3s, and gives up outright
#     once nothing remains.

def _slow_failing_stub(directory, delay_seconds):
    """A real, executable `python3` that ignores whatever it is asked and
    just sleeps `delay_seconds` before exiting 1 -- modelling a PATH entry
    that answers, eventually, but never as a usable interpreter."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "python3"
    path.write_text(f"#!/bin/sh\nsleep {delay_seconds}\nexit 1\n",
                     encoding="ascii", newline="\n")
    os.chmod(path, 0o755)
    return path


def _hung_stub(directory):
    """Never exits on its own -- only the resolver's own 3s watchdog (or,
    with the fix, a shorter one bounded by the remaining deadline) kills
    it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "python3"
    path.write_text("#!/bin/sh\nsleep 60\n", encoding="ascii", newline="\n")
    os.chmod(path, 0o755)
    return path


@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_the_final_probes_wait_is_capped_to_the_remaining_deadline(tmp_path, path, header, fn):
    """The review's own reproduction, sized for a fast test: four
    candidates that each fail after 1.8s (7.2s total, comfortably under the
    8s deadline) followed by one that hangs. Before the fix the hung
    candidate's wait was a flat 3s regardless, pushing the total past
    10s -- past the 10s hook timeout this deadline exists to stay inside.
    With the fix the hung candidate's wait is capped to whatever remains of
    the 8s budget, so the whole run finishes well under 10s. (Three
    candidates at 2.5s -- closer to the 8s boundary -- was tried first and
    is measurably flakier: bash's own per-candidate overhead can tip the
    deadline check before the final candidate is even launched, passing
    either way regardless of whether the fix is present.)"""
    slow_dirs = [_slow_failing_stub(tmp_path / f"slow{i}", 1.8) for i in range(4)]
    hang_dir = _hung_stub(tmp_path / "hang")

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        [str(d.parent) for d in slow_dirs] + [str(hang_dir.parent),
                                               _python_free_path(tmp_path)])
    began = time.monotonic()
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env, timeout=30)
    elapsed = time.monotonic() - began
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    assert exit_line == "EXIT:1", (
        "none of these candidates is a usable interpreter; must report "
        f"failure. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert elapsed < 10, (
        f"the run took {elapsed:.1f}s -- the final (hung) candidate's wait "
        "must be capped to what remains of the 8s deadline, not a flat 3s, "
        "or the total overruns the 10s hook timeout this bounds against")


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
    assert not _is_executable_via_shell(target), "fixture must not be executable"

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
    env["PATH"] = os.pathsep.join([str(stub_dir), _python_free_path(tmp_path)])
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
    assert printed == [_posix_form(real)], (
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
    assert printed == [_posix_form(str(target))], (
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
    env["PATH"] = os.pathsep.join([str(apps_dir), _python_free_path(tmp_path)])
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
    non-Windows host -- the token is derived from `tmp_path` so two
    parallel test workers can never collide on the same absolute path."""
    token = os.path.basename(str(tmp_path))
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
    env["PATH"] = os.pathsep.join([str(stub_dir), _python_free_path(tmp_path)])
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
    like any other tmp fixture."""
    token = os.path.basename(str(tmp_path))
    target_dir = pathlib.Path(f"/c/{token}")
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


# --- FIX (Codex r1 finding 3): the version floor bash was missing --------
#     bash's crew_py_strict/`_resolve_role_write_python` used to accept ANY
#     candidate that printed a real, executable sys.executable, regardless
#     of its actual version, while the PowerShell Resolve-CrewPython already
#     required >= 3.8. A real Python 3.7 (or older) is what this looks like
#     -- monkeypatching sys.version_info before running the probe's own code
#     is the only way to prove this without an actual old CPython installed.

def _spoofed_version_stub(directory, version_tuple, names=("python3", "python", "py")):
    real = shutil.which("python3") or shutil.which("python")
    assert real, "need a real python3/python for this fixture"
    # DOUBLE-quoted release level ("final", not 'final'): repr()'s default
    # single quotes would close the shell's own single-quoted `-c` argument
    # early, corrupting the embedded code -- caught by hand running this
    # exact stub before trusting the test.
    major, minor, micro, level, serial = version_tuple
    tuple_text = f'({major}, {minor}, {micro}, "{level}", {serial})'
    directory.mkdir(parents=True, exist_ok=True)
    body = (
        "#!/bin/sh\n"
        'if [ "$1" = "-c" ]; then\n'
        f'  exec "{real}" -c \'import sys; sys.version_info={tuple_text}; '
        "exec(sys.argv[1])' \"$2\"\n"
        "fi\n"
        f'exec "{real}" "$@"\n'
    )
    for name in names:
        path = directory / name
        path.write_text(body, encoding="ascii", newline="\n")
        os.chmod(path, 0o755)


@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_rejects_a_proven_python_37(tmp_path, path, header, fn):
    """Codex r1 finding 3's own reproduction: only CPython 3.7 on PATH."""
    stub_dir = tmp_path / "stubs"
    _spoofed_version_stub(stub_dir, (3, 7, 9, "final", 0))

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(stub_dir), _python_free_path(tmp_path)])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env)
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:1", (
        f"a proven Python 3.7 must be REJECTED (return 1) -- the version "
        f"floor must match the PowerShell probe's >= 3.8. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert not printed, "must print nothing when rejecting: " + repr(printed)


@needs_bash
@pytest.mark.parametrize("path,header,fn", [
    (_COMMON_SH, "crew_py_strict() {", "crew_py_strict"),
    (_GUARD_SH, "_resolve_role_write_python() {", "_resolve_role_write_python"),
])
def test_resolver_accepts_a_proven_python_38(tmp_path, path, header, fn):
    """Must-allow companion: the same spoofing machinery at exactly the
    floor must still be ACCEPTED, proving the rejection above is about the
    version and not an accidental side effect of the spoofing stub itself."""
    real = shutil.which("python3") or shutil.which("python")
    assert real, "need a real python3/python for this fixture"
    stub_dir = tmp_path / "stubs"
    _spoofed_version_stub(stub_dir, (3, 8, 0, "final", 0))

    driver = tmp_path / "driver.sh"
    driver.write_text(
        _function_raw_source(path, header) + "\n"
        f"{fn}\n"
        'printf "EXIT:%s\\n" "$?"\n',
        encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(stub_dir), _python_free_path(tmp_path)])
    proc = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True,
        check=False, env=env)
    lines = proc.stdout.splitlines()
    exit_line = next((l for l in lines if l.startswith("EXIT:")), "EXIT:?")
    printed = [l for l in lines if not l.startswith("EXIT:")]
    assert exit_line == "EXIT:0", (
        f"a proven Python 3.8 must be ACCEPTED. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert printed == [_posix_form(real)], f"must return the real interpreter's path. got {printed!r}"


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

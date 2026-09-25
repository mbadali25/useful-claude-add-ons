"""Builds synthetic crew repositories for tests.

A fixture is a real git repository with a real commit, because the code under
test asks git for HEAD and comparing against a mocked sha would test the mock.
"""
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile

import pytest

# Sentinel exit code for the bash probe. Any value a failing-to-launch bash
# would not produce on its own: 127 is "command not found", 126 is "found but
# not executable", 1 and 2 are ordinary script failures.
_PROBE_EXIT = 37
_BASH = "unprobed"

# Bounds every gate spawn across the verify-gate suite: a hung sh/pwsh child
# (a stuck interpreter probe, a lock holder that never releases, a shell
# association dialog under -NonInteractive) turns into a red test with a
# name attached, instead of a suite that never returns. 120s is comfortably
# above the longest sleep any fixture here uses (10s) with headroom for a
# slow CI host, never a value a passing run is expected to approach.
GATE_SUBPROCESS_TIMEOUT_S = 120

# Set only while a `gate_processes` fixture instance is active (see below);
# `None` outside one, which is also the default state a test file that never
# requests it -- or drives the fixture's raw generator by hand, as
# test_gate_processes_kills_a_still_running_child_at_teardown does -- runs
# under, and `popen_gate` treats `None` as "nothing to auto-register with".
_AMBIENT_GATE_TRACKER = None

# Whether /proc exists on this host at all (Linux; not macOS/BSD). Read
# once at import time and treated as a constant everywhere below: a host
# that has no /proc can never verify a pgid by start time, so the
# verification in `kill_process_group` is skipped there and the old
# best-effort signal-by-number behaviour is unchanged. On a host that DOES
# have it, a `None` result from `_proc_start_ticks` always means "this
# specific read failed" (pid gone, or gone-and-reused), never "no /proc".
_PROC_SUPPORTED = os.path.isdir("/proc")


def _proc_start_ticks(pid):
    """The kernel's process-start-time field for `pid`, as a string, or
    `None` if it cannot be read (no /proc, pid does not exist, or the stat
    line does not parse).

    This is `/proc/<pid>/stat` field 22 (starttime, in clock ticks since
    boot) -- monotonic, assigned once at fork, and never reused for a
    DIFFERENT process while THIS pid is: a fresh process reusing a
    recycled pid always gets a fresh, later starttime. Comparing it is how
    `kill_process_group` tells "the process I recorded at spawn" from "some
    unrelated process that now happens to hold the same numeric pid",
    which a bare pid alone cannot do once the original has been reaped.

    `comm` (field 2) is parenthesised and may itself contain spaces or a
    literal `)`, so this splits on the LAST `)` rather than by field
    position, matching how `ps`/`procps` parse the same file.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as handle:
            raw = handle.read()
    except OSError:
        return None
    try:
        after_comm = raw.rsplit(")", 1)[1].split()
        return after_comm[19]  # field 22; state (field 3) is after_comm[0]
    except (IndexError, ValueError):
        return None


def _pgid_has_live_member_since(pgid, min_start_ticks):
    """Is there a process ALIVE RIGHT NOW whose process group is `pgid` and
    whose own start time is at or after `min_start_ticks` (the leader's own
    start ticks, recorded at spawn)?

    Exists for the case `_proc_start_ticks(pgid)` cannot answer at all: the
    group LEADER has already been reaped (`/proc/<pgid>/stat` no longer
    exists, so that helper returns `None`), but a grandchild the leader
    backgrounded and never waited on can still be alive in the SAME group
    -- a process group survives its leader's exit for as long as any member
    does. Treating a bare `None` as "this pgid was reused, do not signal"
    (what the mismatch check below used to do for every non-matching
    read, `None` included) skipped `killpg` on exactly the leak this
    function exists to still catch.

    A live member's own start time can never be EARLIER than the group
    leader's -- every member was forked into this group after the leader
    already existed to make the group in the first place -- so scanning
    for one at or after `min_start_ticks` distinguishes a genuine surviving
    grandchild from an unrelated process that merely happens to sit in a
    group numbered the same as ours after full reuse (whose own members,
    if the number really was handed to a brand new session, could not have
    started before the reuse, which is itself after our own leader's
    recorded start -- the same bound, from the other direction).
    """
    if not _PROC_SUPPORTED:
        return False
    try:
        floor = int(min_start_ticks)
    except (TypeError, ValueError):
        return False
    try:
        entries = os.listdir("/proc")
    except OSError:
        return False
    target = str(pgid)
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="ascii") as handle:
                raw = handle.read()
            after_comm = raw.rsplit(")", 1)[1].split()
            member_pgrp = after_comm[2]  # field 5
            member_start = after_comm[19]  # field 22
        except (OSError, IndexError, ValueError):
            continue
        if member_pgrp != target:
            continue
        try:
            if int(member_start) >= floor:
                return True
        except ValueError:
            continue
    return False


def pid_alive(pid):
    """Is `pid` still alive, in the sense every caller here actually means
    -- "would a fresh signal still land", not "does the kernel still have
    a task struct for it".

    A killed child that has not yet been WAITed on is a ZOMBIE: it cannot
    be signalled again and holds no real resources, but its pid is not
    freed until something reaps it, so a bare `os.kill(pid, 0)` keeps
    succeeding for it exactly as it would for a genuinely running process.
    On a host whose PID 1 is not a real init (common in containers,
    nothing reaps orphans), a killed and reparented grandchild can sit in
    that state forever -- a liveness loop built on `os.kill(pid, 0)` alone
    never converges even though the kill already landed. Checking
    `/proc/<pid>/stat`'s state field first (Linux-only) catches this: state
    `Z` reads as dead here.

    Falls back to a bare `os.kill(pid, 0)` when /proc is unavailable (any
    non-Linux POSIX host) or the read fails for some other reason -- the
    zombie-forever case this exists for is Linux/container-specific, not
    general, and a bare kill(0) is still correct everywhere else.
    """
    if os.name == "nt":
        done = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
            text=True, check=False, timeout=30)
        return str(pid) in done.stdout
    if _PROC_SUPPORTED:
        try:
            with open(f"/proc/{pid}/stat", encoding="ascii") as handle:
                state = handle.read().rsplit(")", 1)[1].split()[0]
            if state == "Z":
                return False
        except (OSError, IndexError):
            pass
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def popen_gate(cmd, **kwargs):
    """`subprocess.Popen`, but the child is made killable as a whole GROUP.

    A gate spawn (verify-gate.sh/.ps1, running commands read out of
    `.crew/verify.json`) can leave a GRANDCHILD alive after the direct child
    exits or is killed -- a rule that backgrounds something, or a Git Bash /
    MSYS helper process the platform's own fork emulation leaves behind. If
    that grandchild still holds the direct child's stdout/stderr pipe open,
    `communicate()` blocks forever reading it, because a pipe's read side
    only ever sees EOF once every process holding its write side has exited.
    Killing only the direct child (what a plain `subprocess.Popen`/`.kill()`
    does) does nothing about that grandchild.

    POSIX: `start_new_session=True` makes the child its own session leader,
    so `os.killpg` (`kill_process_group`, below) reaches everything it forked
    or backgrounded, not just itself. Windows: `CREATE_NEW_PROCESS_GROUP`
    is the flag `taskkill /T` needs to walk the same tree -- Windows has no
    signal-based `killpg` to mirror.

    Use `run_gate` for the ordinary spawn-wait-collect-output case; use this
    directly only when a test drives more than one gate concurrently by hand
    (see test_verify_gate_lock_concurrent.py) and pair it with
    `kill_process_group` on any timeout from a hand-rolled `wait`/
    `communicate`.
    """
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kwargs.setdefault("start_new_session", True)
    proc = subprocess.Popen(cmd, **kwargs)  # pylint: disable=consider-using-with
    if os.name != "nt":
        # Recorded HERE, once, from a pid that has not had a chance to be
        # reaped yet -- never re-derived later via `os.getpgid(proc.pid)`
        # at kill time. `start_new_session=True` runs `setsid()` in the
        # child before exec, which POSIX guarantees makes the new process
        # GROUP's id equal the child's own pid -- so this is not a
        # measurement that could race, it is the id `Popen` already fixed
        # the moment it forked. `kill_process_group` used to call
        # `os.getpgid(proc.pid)` at the point of killing instead: if the
        # leader had ALREADY exited and been reaped by then (a `.poll()`/
        # `.wait()` elsewhere between spawn and cleanup), the OS is free to
        # hand that exact pid to a brand new, unrelated process, and
        # `getpgid` on THAT pid returns THAT process' group -- `killpg`
        # would then signal something this test never started. Storing the
        # id at spawn removes the reuse window entirely: it is correct for
        # as long as `proc` exists, reaped or not.
        proc.pgid = proc.pid
        # Recorded in the same breath, for the same reason: a `None` here
        # (process already gone, or no /proc) means kill-time verification
        # is not possible either, and `kill_process_group` falls back to
        # the old unverified signal rather than refusing to clean up at
        # all.
        proc.pgid_start_ticks = (
            _proc_start_ticks(proc.pid) if _PROC_SUPPORTED else None)
    # Auto-tracked by whichever test's `gate_processes` fixture is
    # currently active (autouse, see below) -- a caller that ALSO does its
    # own explicit `gate_processes(proc)` registration (the pre-existing
    # usage this repo's tests already wrote) just double-registers into the
    # same list, which `gate_processes`'s teardown already tolerates (a
    # `poll()` check before each kill, not an assumption every entry is
    # still alive and untouched). This is what closes the gap the previous
    # design left: a test that drives `popen_gate` directly and then fails
    # an assertion before reaching its own manual `finally:` cleanup used to
    # leak that child past the test's own end; now it does not, whether or
    # not that test remembers to register anything itself.
    if _AMBIENT_GATE_TRACKER is not None:
        _AMBIENT_GATE_TRACKER(proc)
    return proc


def kill_process_group(proc):
    """Kill `proc` and everything it started (see `popen_gate`). Best-effort:
    a process that already exited, or one this user cannot signal, is not an
    error here -- the caller is about to give up on it either way.

    Uses `proc.pgid` -- recorded by `popen_gate` at spawn time -- in
    preference to a fresh `os.getpgid(proc.pid)` here. A caller that built
    `proc` some other way (bypassing `popen_gate`) has no such attribute, so
    the live lookup remains as a fallback for that case only; see
    `popen_gate`'s comment on `proc.pgid` for why the fresh lookup is the
    one with the reuse race and should not be reached for anything spawned
    through here.

    A recorded `proc.pgid` is not itself immune to reuse: once the whole
    group this pgid names has exited (the ordinary case for a short-lived
    gate command -- `run_gate` reaps the direct child via `communicate()`
    on every non-timeout call, and a command with no lingering grandchild
    takes the rest of the group with it), the kernel is free to hand that
    exact number to a brand new, unrelated `setsid` leader, and this
    function can be called on the stale `proc` well after that -- teardown
    iterates every tracked proc regardless of whether it already exited.
    So when `proc.pgid_start_ticks` was recorded (non-`None`, meaning
    `_PROC_SUPPORTED` and the read succeeded at spawn), this re-reads the
    SAME field for the pgid now and refuses to signal on a mismatch --
    that pgid no longer names the process this call is trying to clean up,
    and guessing would kill whatever unrelated thing holds it now. No
    recorded start time (no /proc, or the `getpgid` fallback path, which
    never had one to record) falls back to the old, unverified signal --
    the only thing possible there, and no worse than before this check
    existed.

    A REAPED leader is not the same thing as a REUSED pgid, and used to be
    treated identically: `_proc_start_ticks(pgid)` reads `None` once the
    leader itself has been waited on (its `/proc` entry is gone entirely,
    not merely stale), and `None != start_ticks` is true exactly the same
    way a genuine mismatch is -- so a rule that backgrounded a grandchild
    and exited itself (the ordinary shape `run_gate`'s own `communicate()`
    already reaps) fell into the "may have been reused" branch and skipped
    `killpg`, leaking that grandchild. `None` now falls to
    `_pgid_has_live_member_since` instead of an immediate skip: only when
    NO member of this exact pgid is still alive with a start time at or
    after the leader's recorded one does this refuse to signal.
    """
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        capture_output=True, timeout=30, check=False)
    else:
        pgid = getattr(proc, "pgid", None)
        start_ticks = getattr(proc, "pgid_start_ticks", None)
        try:
            if pgid is None:
                pgid = os.getpgid(proc.pid)
            elif _PROC_SUPPORTED and start_ticks is not None:
                current = _proc_start_ticks(pgid)
                if current is None:
                    if not _pgid_has_live_member_since(pgid, start_ticks):
                        print(
                            f"crew_fixtures: skipping killpg({pgid}) - its "
                            "leader has been reaped and no process group "
                            "member with a start time at or after the "
                            "recorded leader start remains",
                            file=sys.stderr)
                        pgid = None
                elif current != start_ticks:
                    print(
                        f"crew_fixtures: skipping killpg({pgid}) - its "
                        "process start time no longer matches what was "
                        "recorded at spawn, so this pgid may have been "
                        "reused by an unrelated process", file=sys.stderr)
                    pgid = None
            if pgid is not None:
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def run_gate(cmd, *, timeout=GATE_SUBPROCESS_TIMEOUT_S, input=None,  # pylint: disable=redefined-builtin
             check=False, capture_output=False, text=None, stdin=None,
             stdout=None, stderr=None, cwd=None, env=None):
    """`subprocess.run`, but a timeout kills the child's whole process GROUP
    before the retry-drain, not just the one pid `subprocess.run` started.

    `subprocess.run`'s own `timeout` handling -- see cpython's `subprocess.py`
    -- kills only the direct child, then calls `communicate()` a SECOND time,
    with no timeout at all, to collect whatever output is left. That second
    call is the hang: see `popen_gate`'s docstring for why a grandchild can
    keep the pipe open past the direct child's own death. Every verify-gate
    spawn in this suite must go through here (or `popen_gate` for the one
    hand-rolled concurrent case) instead of raw `subprocess.run`/`Popen`, so a
    hung gate fails as a named `TimeoutExpired` within `timeout` seconds
    instead of wedging the whole session -- see
    test_verify_gate_stop_gate_record.py's account of test_34 for the run
    that first exposed this.
    """
    if input is not None:
        if stdin is not None:
            raise ValueError("input and stdin are mutually exclusive")
        stdin = subprocess.PIPE
    if capture_output:
        if stdout is not None or stderr is not None:
            raise ValueError(
                "capture_output and stdout/stderr are mutually exclusive")
        stdout = subprocess.PIPE
        stderr = subprocess.PIPE

    popen_kwargs = {"cwd": cwd, "env": env, "stdin": stdin, "stdout": stdout,
                    "stderr": stderr}
    if text is not None:
        popen_kwargs["text"] = text

    proc = popen_gate(cmd, **popen_kwargs)
    try:
        out, err = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_process_group(proc)
        # Bounded drain: every holder of the pipe is now dead, so this
        # returns fast -- but "fast" is not trusted blindly, hence the bound.
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out, err = None, None
        raise subprocess.TimeoutExpired(
            cmd, timeout, output=out, stderr=err) from None
    result = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
    if check and proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, out, err)
    return result


@pytest.fixture(autouse=True)
def gate_processes():
    """Hygiene, not a check: kills every tracked gate's whole process GROUP
    at test teardown, regardless of whether the test passed, failed, or
    raised partway through -- and makes no assertion of its own about what
    it finds still running.

    `run_gate` already cleans up its OWN spawn on a `TimeoutExpired`, but a
    test that drives `popen_gate` directly (concurrent-lock tests, the
    stdin-bound tests that hold a pipe open on purpose) owns its process for
    the whole test body, and an assertion failing partway through skips
    whatever manual `finally:` cleanup that test wrote. A gate left running
    past its own test can still be holding `.crew/.verify-gate.lock`, which
    then fails the NEXT test to spawn one for a reason that has nothing to
    do with what that next test is actually checking.

    AUTOUSE, and every `popen_gate` call registers itself here automatically
    (see `_AMBIENT_GATE_TRACKER`) -- this used to require a test to request
    the fixture BY NAME and then call it explicitly on every `Popen`, and
    nothing in the verify-gate test modules actually did, which made the
    whole mechanism dead weight everywhere it mattered. Explicit
    `gate_processes(proc)` registration (still exported, still exercised by
    test_crew_fixtures.py's own meta-test of this fixture) is now redundant
    with the automatic path rather than required by it -- calling it anyway
    just double-registers into the same list, which the teardown loop below
    already tolerates via its `poll()` check. Cheap where it does nothing:
    a test file that never calls `popen_gate` leaves `procs` empty and this
    loop a no-op, so making it autouse suite-wide costs nothing there.
    """
    # pylint: disable=global-statement  # save/restore of the ambient
    # tracker for the duration of this fixture's yield, not a persistent
    # mutation - see the previous_tracker restore in the finally below.
    global _AMBIENT_GATE_TRACKER
    procs = []
    previous_tracker = _AMBIENT_GATE_TRACKER
    _AMBIENT_GATE_TRACKER = procs.append
    try:
        yield procs.append
    finally:
        _AMBIENT_GATE_TRACKER = previous_tracker
    for proc in procs:
        if os.name == "nt":
            # Unchanged: Windows' equivalent of the POSIX gap below is a
            # separate question (taskkill against an already-exited PID
            # behaves differently again) and is win-repo's call per the
            # OWNER RULE, not decided here - see TODO.md.
            if proc.poll() is None:
                kill_process_group(proc)
            else:
                continue
        else:
            # POSIX: killpg REGARDLESS of whether the direct child (the
            # process GROUP LEADER) has already exited. Gating on
            # `proc.poll() is None` skipped exactly the case this fixture
            # exists for - a rule that backgrounds a grandchild and returns
            # immediately leaves the leader's own poll() non-None almost
            # instantly, while the grandchild it forked keeps running in
            # the SAME process group for as long as it likes (test_34b's
            # leaked `sleep 20`, before that test grew its own explicit
            # pid-based cleanup). A process group survives its leader's
            # exit as long as any member is still alive, so `os.killpg` via
            # `kill_process_group` still reaches it; `kill_process_group`
            # already treats a `ProcessLookupError` (the group is gone too,
            # or the leader's now-reused pid resolves to an unrelated
            # process' group) as nothing left to do, which is the
            # unavoidable, accepted cost of signalling by a possibly-
            # recycled pid in a best-effort test-teardown path, not
            # production code.
            kill_process_group(proc)
        # SIGKILL/taskkill only ends execution -- the pid stays a zombie,
        # still answering `os.kill(pid, 0)`, until something reaps it.
        # `kill_process_group`'s OWN callers (`run_gate`'s timeout path)
        # get that for free from the `communicate()` retry right after
        # it; this fixture has no such second call, so it does the
        # `wait()` itself.
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


def _usable(candidate):
    """Does this bash actually run a script living at a Windows path?

    This is the whole point of the module-level probe. `shutil.which("bash")`
    answers "is there a file called bash", which is not the question. Under
    PowerShell on Windows it returns `C:\\WINDOWS\\system32\\bash.EXE` -- WSL's
    -- which cannot open a Windows path at all: handed one it exits 127 with
    "No such file or directory" for a file that demonstrably exists.
    """
    tmp = tempfile.mkdtemp()
    try:
        script = os.path.join(tmp, "probe.sh")
        # newline="\n": a CRLF script dies on its shebang as `bad interpreter`.
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"exit {_PROBE_EXIT}\n")
        try:
            done = subprocess.run(
                [candidate, script.replace("\\", "/")],
                capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == _PROBE_EXIT
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve_bash():
    """A bash that can run a script at a Windows path, or None.

    Returns None rather than a path that will not work, so a caller can SKIP the
    `sh` flavour instead of parametrizing it in and collecting failures. The
    previous version of this logic lived copied in six test modules and treated
    "a bash was found" as "a working bash was found"; under PowerShell that made
    `_HAS_BASH` True against WSL's bash and 52 tests failed with `assert 127 ==
    2`. Two agents independently reported that as pre-existing breakage on main
    -- a harness assumption wearing the label of a regression.

    Every candidate is PROVED by running one, because the failure mode here is
    precisely that a plausible-looking path does not work.
    """
    global _BASH  # pylint: disable=global-statement
    if _BASH != "unprobed":
        return _BASH

    candidates = []
    found = shutil.which("bash")
    if found:
        parts = pathlib.Path(found).parts
        lower = [p.lower() for p in parts]
        # Git for Windows ships two bashes. usr/bin/bash.exe is the raw MSYS
        # binary and cannot resolve its own mount table when launched from
        # python.exe; bin/bash.exe is the shim that bootstraps MSYS first.
        if "usr" in lower and "bin" in lower:
            shim = pathlib.Path(*parts[:lower.index("usr")]) / "bin" / "bash.exe"
            if shim.exists():
                candidates.append(str(shim))
        candidates.append(found)
    # Named last, never by editing PATH. Prepending Git's bin/ to PATH is what
    # makes `check-marketplace.py` hang -- it moves `git` to a build that never
    # returns for that script -- so the two gates would want opposite
    # environments. Resolving the interpreter here leaves PATH alone.
    for guess in (r"C:\Program Files\Git\bin\bash.exe",
                  r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if guess not in candidates and os.path.isfile(guess):
            candidates.append(guess)

    for candidate in candidates:
        if _usable(candidate):
            _BASH = candidate
            return _BASH

    print(
        "crew tests: no usable bash - the 'sh' flavour is SKIPPED, not failed. "
        + (f"Found {found!r} but it cannot run a script at a Windows path."
           if found else "No bash on PATH.")
        + " Install Git for Windows, or run the suite from Git Bash.",
        file=sys.stderr,
    )
    _BASH = None
    return _BASH


_PWSH = "unprobed"


def resolve_pwsh():
    """PowerShell 7, or None when this machine has none.

    `shutil.which("pwsh")` alone is not enough here, and the reason is the
    mirror image of `resolve_bash`'s: pwsh is NOT on Git Bash's PATH on this
    repo's own development machine, so a suite launched from Git Bash skipped
    every `.ps1` case while reporting a pass. The install location is named as
    a fallback rather than assumed, so a machine that really has no pwsh still
    SKIPS instead of failing -- `which` first, because a pwsh somewhere else on
    PATH is the one the user means.

    Deliberately not `powershell.exe`: the `.ps1` hooks are registered for
    PowerShell 7 (`shell: "powershell"` -> pwsh) and Windows PowerShell 5.1
    differs in ways these scripts rely on, `ConvertFrom-Json` included.
    """
    global _PWSH  # pylint: disable=global-statement
    if _PWSH != "unprobed":
        return _PWSH

    found = shutil.which("pwsh")
    candidates = [found] if found else []
    for guess in (r"C:\Program Files\PowerShell\7\pwsh.exe",
                  r"C:\Program Files (x86)\PowerShell\7\pwsh.exe"):
        if guess not in candidates and os.path.isfile(guess):
            candidates.append(guess)
    _PWSH = candidates[0] if candidates else None
    if _PWSH is None:
        print("crew tests: no pwsh - the '.ps1' flavour is SKIPPED, not "
              "failed.", file=sys.stderr)
    return _PWSH


# The full per-shell matrix. `conftest.py` registers the marker and deselects
# it from a default run; `pytest -m slow` or `--run-slow` runs it. Only the
# bash and pwsh drivers of a decision case carry it: the python driver runs
# every case by default, and the wrappers only pass stdin, the exit code and
# stdout through to that same module. On Windows each shell case costs one
# process creation plus a python start inside it (0.8-1.4 s a case measured
# by docs/review/06-windows-burn-in.md), which is what made the default run
# unfinishable there.
SLOW = pytest.mark.slow


def parity_sample(cases, ids, keep, marks=()):
    """`cases` as pytest params for a bash or pwsh driver: the ids in `keep`
    run by default -- the parity sample -- and every other case is `slow`.

    `keep` naming an id the table lacks raises at collection, so renaming a
    case cannot quietly empty the sample."""
    missing = set(keep) - set(ids)
    assert not missing, f"parity sample names unknown case(s): {sorted(missing)}"
    return [pytest.param(case, id=case_id,
                         marks=tuple(marks) + (() if case_id in keep else (SLOW,)))
            for case, case_id in zip(cases, ids)]


def sample_params(params, keep):
    """`parity_sample` for a list that is already `pytest.param`s: those
    whose id is in `keep` keep their marks, every other one gains `slow`."""
    missing = set(keep) - {p.id for p in params}
    assert not missing, f"parity sample names unknown case(s): {sorted(missing)}"
    return [pytest.param(*p.values, id=p.id,
                         marks=tuple(p.marks) + (() if p.id in keep else (SLOW,)))
            for p in params]


# --- PATH shims, per flavour -------------------------------------------------
#
# A fake tool on PATH has to be findable by THREE different searchers, and on
# Windows they disagree about what "findable" means:
#
#   * bash (`command -v`) runs an extensionless file with a shebang, and wants
#     a `:`-separated POSIX PATH (`/c/...`);
#   * pwsh wants a `;`-separated native PATH;
#   * the native-Windows python a hook script starts (`crew_autocycle.py`)
#     asks `shutil.which`, which with the default X_OK mode only ever matches
#     `name + <a PATHEXT extension>` -- an extensionless shim is invisible to
#     it however PATH is joined. That, more than the separator, is what the
#     Windows burn-in's "method xdotool but xdotool is not on PATH" points at.
#
# So a shim is written twice on Windows (extensionless for bash, `.cmd` for
# everything native), and PATH is built for the flavour that will read it.
# chmod is a no-op on NTFS and is skipped there; on POSIX it is load-bearing.

_DRIVE_RE = re.compile(r"^([A-Za-z]):(?:[\\/]+(.*))?$")


def windows_to_posix(path):
    """`C:\\x\\y` -> `/c/x/y`, the shape `cygpath -u` gives. Pure, so the
    Windows conversion is covered on a Linux runner. A path with no drive
    letter keeps its shape, with backslashes turned into slashes."""
    text = str(path)
    match = _DRIVE_RE.match(text)
    if not match:
        return text.replace("\\", "/")
    rest = (match.group(2) or "").replace("\\", "/").strip("/")
    drive = "/" + match.group(1).lower()
    return f"{drive}/{rest}" if rest else drive


def _cygpath_list(entries, cygpath):
    """`cygpath -u -p` over the whole list in one process, or None."""
    try:
        done = subprocess.run([cygpath, "-u", "-p", ";".join(entries)],
                              capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    out = done.stdout.strip()
    return out.split(":") if done.returncode == 0 and out else None


def shell_path(flavor, dirs, base=None, windows=None, cygpath=None):
    """The PATH value `flavor` ("sh" or "ps1") should be handed, with `dirs`
    first and `base` (default: this process's PATH) behind them.

    `windows` and `cygpath` exist so a Linux test can drive the Windows
    branch: `windows=True` treats `base` as a `;`-list of native paths, and
    `cygpath=False` forces the manual `C:\\x` -> `/c/x` conversion."""
    windows = os.name == "nt" if windows is None else windows
    base = os.environ.get("PATH", "") if base is None else base
    native_sep = ";" if windows else ":"
    entries = [str(d) for d in dirs] + [e for e in base.split(native_sep) if e]
    if not (windows and flavor == "sh"):
        return native_sep.join(entries)
    if cygpath is None:
        cygpath = shutil.which("cygpath") if os.name == "nt" else None
    converted = _cygpath_list(entries, cygpath) if cygpath else None
    if converted is None or len(converted) != len(entries):
        converted = [windows_to_posix(e) for e in entries]
    return ":".join(converted)


def write_shim(directory, name, sh_body="#!/bin/sh\nexit 0\n",
               cmd_body="@echo off\r\nexit /b 0\r\n", windows=None):
    """A fake executable called `name` in `directory`; returns its path.

    POSIX: one extensionless file, chmod 755. Windows: the extensionless file
    (bash runs it by its shebang) plus `name.cmd`, the only form a native
    `shutil.which` or pwsh will find. No chmod there -- NTFS ignores it."""
    windows = os.name == "nt" if windows is None else windows
    os.makedirs(str(directory), exist_ok=True)
    path = os.path.join(str(directory), name)
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        handle.write(sh_body)
    if windows:
        with open(path + ".cmd", "w", encoding="ascii", newline="") as handle:
            handle.write(cmd_body)
    else:
        os.chmod(path, 0o755)
    return path


def shim_env(flavor, bindir, **extra):
    """`{"PATH": ...}` with `bindir` first, built for `flavor`, plus `extra`."""
    env = {"PATH": shell_path(flavor, [bindir])}
    env.update(extra)
    return env


def _git(root, *args):
    subprocess.run(
        ("git",) + args, cwd=root, check=True,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30,
    )


def make_repo(tmp_path, config=None, metrics=None, codemap=None,
              work_ticket=None, handoff=False, graph=False, git=True,
              graph_sha="head"):
    """Write a synthetic crew repo under tmp_path and return its root."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir(parents=True)

    if git:
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "test@example.invalid")
        _git(root, "config", "user.name", "Test")
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        _git(root, "add", "README.md")
        _git(root, "commit", "-q", "-m", "fixture")

    if config is not None:
        (root / ".crew" / "config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    if metrics is not None:
        lines = ["date | ticket | reviewer | BLOCK | FIX",
                 "--- | --- | --- | --- | ---"]
        for ticket, block, fix in metrics:
            lines.append(f"2026-08-01 | {ticket} | codex | {block} | {fix}")
        (root / ".crew" / "metrics.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    if codemap is not None:
        mapdir = root / ".crew" / "codemap"
        mapdir.mkdir()
        for name, body in codemap.items():
            (mapdir / f"{name}.md").write_text(body, encoding="utf-8")

    if work_ticket:
        (root / ".work" / "INDEX.md").write_text(
            f"# Work\n\n- {work_ticket} — in progress\n", encoding="utf-8"
        )

    if handoff:
        (root / ".work" / "HANDOFF.md").write_text(
            "# Handoff\n\n## Next action\nSomething.\n", encoding="utf-8"
        )

    if graph:
        out = root / "graphify-out"
        out.mkdir()
        # graph_sha: "head" stamps built_at_commit with the real, full HEAD
        # sha (a fresh graph) -- graphify records the full sha, not a short
        # one. A literal sha stamps that verbatim (a stale graph). None omits
        # the field entirely (a graph built outside crew, unknown provenance).
        body = {"nodes": [], "links": []}
        if graph_sha == "head" and git:
            body["built_at_commit"] = head_sha(root, length=40)
        elif graph_sha and graph_sha != "head":
            body["built_at_commit"] = graph_sha
        (out / "graph.json").write_text(json.dumps(body), encoding="utf-8")

    return root


def head_sha(root, length=7):
    """Short HEAD sha of a fixture repo."""
    done = subprocess.run(
        ("git", "rev-parse", f"--short={length}", "HEAD"),
        cwd=root, check=True, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=30,
    )
    return done.stdout.strip()


def commit_file(root, path, message=None):
    """Stage and commit one path at the current time. The ordinary case.

    commit_with_date() exists for the backdated-pull regression; this is the
    plain one, used by the tests that ask which PATHS a commit touched rather
    than when it happened.
    """
    _git(root, "add", path)
    _git(root, "commit", "-q", "-m", message or ("add " + path))


def commit_with_date(root, path, iso_date):
    """Commit one file with both dates forced, simulating a pulled commit.

    A pull lands commits authored earlier than now, which is what breaks any
    freshness check based on timestamps rather than a recorded sha.
    """
    env = dict(os.environ,
               GIT_AUTHOR_DATE=iso_date, GIT_COMMITTER_DATE=iso_date)
    subprocess.run(("git", "add", path), cwd=root, check=True,
                   capture_output=True, text=True,
                   stdin=subprocess.DEVNULL, timeout=30)
    subprocess.run(("git", "commit", "-q", "-m", f"backdated {path}"),
                   cwd=root, check=True, capture_output=True, text=True,
                   env=env, stdin=subprocess.DEVNULL, timeout=30)

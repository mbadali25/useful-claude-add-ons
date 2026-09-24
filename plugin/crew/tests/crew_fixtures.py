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
    error here -- the caller is about to give up on it either way."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        capture_output=True, timeout=30, check=False)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
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

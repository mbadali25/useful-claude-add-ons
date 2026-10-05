"""L-1512: the python probe signals nothing live when its candidate exits.

Windows CI killed cloud-guard.sh's own bash.exe with SIGKILL, twice, on PRs
that never touched the guard: exit 2304 with empty stderr, 0.8s into a run
bounded at 120s (job 111538994343, `test_must_block_bash[aws-s3-rm-recursive]`).
2304 is `9 << 8`: msys2-runtime's `pinfo::exit` byte-swaps the wait status of
a process no Cygwin parent started, so it means "ended by signal 9" and
nothing else. Cygwin raises no SIGKILL of its own, the other xdist workers
were running pwsh-only cases at that second, and the hook's process tree has
exactly one sender: the probe in `crew_py_strict`, which on EVERY call, after
the candidate had already exited, ran `kill -9 -- "-$watchdog" "-$pid"`
against a watchdog that was still alive (asleep, or mid-fork of its `sleep`).
Cygwin delivers a signal by reading the target's Windows pid and signal-pipe
handle out of shared memory (`sig_send`), and how that one landed on the
hook's own bash.exe is MODELLED, not observed on a Windows host.

The fix makes no kill call on the normal path: the watchdog is a process
substitution blocked in the builtin `read -t` on a pipe the probe holds, and
the probe writes `done` there once its candidate has exited. That line is the
only thing that stands the watchdog down; a timeout, EOF without it, or an
error kills -- the same on bash 3.2 (whose timed-out `read -t` returns 1) and
on 4.x/5.x. These cases drive each copy of the probe -- `crew_py_strict`, its
byte copy in role-write-guard.sh, and `crew_py` -- with `kill` shadowed by a
function that records every call, and every target still alive.
"""
import os
import pathlib
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_COMMON_SH = os.path.join(_ROOT, "hooks", "scripts", "_common.sh")
_GUARD_SH = os.path.join(_ROOT, "hooks", "scripts", "role-write-guard.sh")

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

PROBES = [
    pytest.param(_COMMON_SH, "crew_py_strict() {", "crew_py_strict", id="crew_py_strict"),
    pytest.param(_GUARD_SH, "_resolve_role_write_python() {",
                 "_resolve_role_write_python", id="role-write-guard-copy"),
    pytest.param(_COMMON_SH, "crew_py() {", "crew_py", id="crew_py"),
]

# `kill` as a function: the probe's subshells inherit it. EVERY call is
# logged (CALL), and each target after the signal (and an optional `--`)
# that `kill -0` still reaches is logged LIVE, before the real builtin runs.
KILL_SPY = r'''
kill() {
  local a first=1
  printf 'CALL %s\n' "$*" >> "$PROBE_LOG"
  for a in "$@"; do
    if [ "$first" = 1 ]; then first=0; continue; fi
    [ "$a" = "--" ] && continue
    builtin kill -0 -- "$a" 2>/dev/null && printf 'LIVE %s\n' "$a" >> "$PROBE_LOG"
  done
  builtin kill "$@"
}
'''

# bash 3.2 (macOS) returns 1 from a timed-out `read -t`, the same status as
# EOF; 4.0 and later return above 128. This makes any bash answer the 3.2 way.
READ_AS_BASH_32 = r'''
read() {
  builtin read "$@"
  local s=$?
  [ "$s" -gt 128 ] && return 1
  return "$s"
}
'''


def _function_raw_source(path, header):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find(header)
    assert start != -1, header + " is gone from " + path
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of " + header + " in " + path
    return src[start:end + 3]


def _drive(tmp_path, path, header, fn, candidate_body, prelude=""):
    """Run `fn` with ONE candidate on PATH, a `python3` whose body is
    `candidate_body`; return (stdout, log text)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python3"
    stub.write_text("#!/bin/sh\n" + candidate_body, encoding="ascii", newline="\n")
    os.chmod(stub, 0o755)
    log = tmp_path / "probe.log"
    log.write_text("", encoding="utf-8")
    driver = tmp_path / "driver.sh"
    driver.write_text(
        KILL_SPY + prelude + _function_raw_source(path, header) + "\n"
        f'r=$({fn}); printf "RESULT:%s\\n" "$r"\n',
        encoding="utf-8", newline="\n")
    base = None
    if os.name != "nt":
        # Without the host's interpreters, so the stub is the ONLY candidate
        # and the result says what the probe made of it.
        tools = tmp_path / "python-free-bin"
        tools.mkdir()
        crew_fixtures.link_path_dirs(
            tools, skip=lambda name: name.startswith(("python", "py")))
        base = str(tools)
    env = dict(os.environ, PROBE_LOG=log.as_posix(),
               PATH=crew_fixtures.shell_path("sh", [bindir], base=base))
    proc = subprocess.run([_BASH, str(driver)], capture_output=True, text=True,
                          env=env, timeout=60, check=False)
    return proc.stdout + proc.stderr, log.read_text(encoding="utf-8")


@needs_bash
@pytest.mark.parametrize("path,header,fn", PROBES)
def test_a_candidate_that_answers_at_once_makes_no_kill_call(
        tmp_path, path, header, fn):
    """The path every hook takes: the candidate answers and exits. The probe
    calls kill not once -- the old cleanup SIGKILLed its still-sleeping
    watchdog's group here, on every call, and the first fix still signalled
    the reaped candidate's (usually empty) group."""
    out, log = _drive(tmp_path, path, header, fn,
                      'echo "$0"\n')
    assert "RESULT:" in out and "RESULT:\n" not in out, out
    assert log == "", (
        f"{fn} called kill although its candidate had already exited:\n{log}")


@needs_bash
@pytest.mark.parametrize("path,header,fn", PROBES)
def test_a_candidate_that_fails_at_once_makes_no_kill_call_either(
        tmp_path, path, header, fn):
    """A broken candidate (the WindowsApps stub's shape: no output, exit 9009)
    is the other common case, and the same: no kill call at all."""
    _out, log = _drive(tmp_path, path, header, fn, "exit 9\n")
    assert log == "", log


_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason=(
    "needs a PATH with no interpreter behind the stub, built from /usr/bin "
    "symlinks; the two cases above run on Windows"))


def _assert_hung_candidate_killed(out, log, fn):
    assert "LIVE" in log, (
        f"{fn}'s watchdog never killed the hung candidate; the probe only "
        f"returned because its deadline ran out:\n{log}")
    if fn != "crew_py":
        # crew_py falls back to the first PATH match when nothing runs.
        assert "RESULT:\n" in out, out


@needs_bash
@_POSIX_ONLY
@pytest.mark.parametrize("path,header,fn", PROBES)
def test_a_hung_candidate_is_still_killed_and_reported_as_no_python(
        tmp_path, path, header, fn):
    """Must-block half: the timeout path keeps its kill. A candidate that
    never answers is SIGKILLed by the watchdog -- the one live target the
    log may name -- and the strict probe reports no python, never the stub."""
    out, log = _drive(tmp_path, path, header, fn, "exec sleep 60\n")
    _assert_hung_candidate_killed(out, log, fn)


@needs_bash
@_POSIX_ONLY
@pytest.mark.parametrize("path,header,fn", PROBES)
def test_a_hung_candidate_is_killed_where_read_t_times_out_with_status_1(
        tmp_path, path, header, fn):
    """bash 3.2, macOS's /bin/bash, answers a timed-out `read -t` with 1 --
    the status EOF also gives. A watchdog that read "above 128" as the only
    timeout never killed there, and the probe hung until the hook's own
    timeout: the non-blocking fail-open L-1512 removes. The clean exit is a
    line the probe writes, so anything else -- timeout, EOF, error -- kills."""
    out, log = _drive(tmp_path, path, header, fn, "exec sleep 60\n",
                      prelude=READ_AS_BASH_32)
    _assert_hung_candidate_killed(out, log, fn)


def _leftover_stub(directory, prints, seconds=20):
    """A `python3` that answers and exits 0 at once but leaves a background
    child running `seconds`, with the stub's own stdout, behind it. Its pid
    goes to `child.pid` so the test can end it."""
    directory.mkdir(parents=True, exist_ok=True)
    pidfile = directory / "child.pid"
    stub = directory / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        f"( sleep {seconds} ) &\n"
        f"echo $! > '{pidfile.as_posix()}'\n"
        f"echo '{prints}'\n"
        "exit 0\n", encoding="ascii", newline="\n")
    os.chmod(stub, 0o755)
    return pidfile


def _end_child(pidfile):
    try:
        os.kill(int(pidfile.read_text(encoding="ascii").strip()), 9)
    except (OSError, ValueError):
        pass


@needs_bash
@_POSIX_ONLY
@pytest.mark.wallclock
@pytest.mark.parametrize("path,header,fn", PROBES[:2])
def test_a_child_left_holding_the_candidates_stdout_does_not_hold_the_probe(
        tmp_path, path, header, fn):
    """Review round 2: the strict probe read the candidate's answer from a
    `$(...)` pipe, so a candidate that exited 0 but left a child holding
    stdout kept the probe waiting for EOF until that child ended -- 40s
    against role-write-guard's 10s hook timeout, a non-blocking fail-open.
    The candidate's stdout is now a process substitution that reads one
    line (bounded by the probe's `read -t`) and prints it to the `$()`; the
    child holds that pipe, is not killed (no kill on the clean path), and
    cannot hold the probe. Bounded at 5s against the child's 20s."""
    bindir = tmp_path / "bin"
    pidfile = _leftover_stub(bindir, "/the/stub/answer")
    tools = tmp_path / "python-free-bin"
    tools.mkdir()
    crew_fixtures.link_path_dirs(
        tools, skip=lambda name: name.startswith(("python", "py")))
    driver = tmp_path / "driver.sh"
    driver.write_text(
        KILL_SPY + _function_raw_source(path, header) + "\n"
        f'r=$({fn}); printf "RESULT:%s\\n" "$r"\n',
        encoding="utf-8", newline="\n")
    log = tmp_path / "probe.log"
    log.write_text("", encoding="utf-8")
    env = dict(os.environ, PROBE_LOG=log.as_posix(),
               PATH=crew_fixtures.shell_path("sh", [bindir], base=str(tools)))
    try:
        proc = subprocess.run([_BASH, str(driver)], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, env=env, timeout=5, check=False)
    finally:
        _end_child(pidfile)
    # The answer names no file, so the strict probe rejects it: what
    # matters is that the probe returned, promptly.
    assert "RESULT:" in proc.stdout, proc.stdout
    assert log.read_text(encoding="utf-8") == "", "a kill on the clean path"

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

The fix takes every signal off the normal path: the watchdog is a process
substitution blocked in the builtin `read -t` on a pipe the probe holds, so
the probe's exit closes it and the watchdog returns on EOF and exits by
itself. Only a timeout (read's status above 128) still kills. These cases
drive each copy of the probe -- `crew_py_strict`, its byte copy in
role-write-guard.sh, and `crew_py` -- with `kill` shadowed by a function that
records every target still alive when it is signalled.
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

# `kill` as a function: the probe's subshells inherit it. Every target after
# the signal (and an optional `--`) that `kill -0` still reaches is logged
# LIVE before the real builtin runs, so the probe behaves exactly as before.
KILL_SPY = r'''
kill() {
  local a first=1
  for a in "$@"; do
    if [ "$first" = 1 ]; then first=0; continue; fi
    [ "$a" = "--" ] && continue
    builtin kill -0 -- "$a" 2>/dev/null && printf 'LIVE %s\n' "$a" >> "$PROBE_LOG"
  done
  builtin kill "$@"
}
'''


def _function_raw_source(path, header):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.find(header)
    assert start != -1, header + " is gone from " + path
    end = src.find("\n}\n", start)
    assert end != -1, "could not find the end of " + header + " in " + path
    return src[start:end + 3]


def _drive(tmp_path, path, header, fn, candidate_body):
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
        KILL_SPY + _function_raw_source(path, header) + "\n"
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
def test_a_candidate_that_answers_at_once_draws_no_signal_to_anything_live(
        tmp_path, path, header, fn):
    """The path every hook takes: the candidate answers and exits. Nothing
    the probe started is signalled while alive -- the old cleanup SIGKILLed
    its still-sleeping watchdog's group here, on every call."""
    out, log = _drive(tmp_path, path, header, fn,
                      'echo "$0"\n')
    assert "RESULT:" in out and "RESULT:\n" not in out, out
    assert "LIVE" not in log, (
        f"{fn} signalled a live process although its candidate had already "
        f"exited:\n{log}")


@needs_bash
@pytest.mark.parametrize("path,header,fn", PROBES)
def test_a_candidate_that_fails_at_once_draws_no_signal_either(
        tmp_path, path, header, fn):
    """A broken candidate (the WindowsApps stub's shape: no output, exit 9009)
    is the other common case, and the same: no signal to anything live."""
    _out, log = _drive(tmp_path, path, header, fn, "exit 9\n")
    assert "LIVE" not in log, log


@needs_bash
@pytest.mark.skipif(os.name == "nt", reason=(
    "needs a PATH with no interpreter behind the stub, built from /usr/bin "
    "symlinks; the two cases above run on Windows"))
@pytest.mark.parametrize("path,header,fn", PROBES[:2])
def test_a_hung_candidate_is_still_killed_and_reported_as_no_python(
        tmp_path, path, header, fn):
    """Must-block half: the timeout path keeps its kill. A candidate that
    never answers is SIGKILLed by the watchdog -- the one live target the
    log may name -- and the strict probe reports no python, never the stub."""
    out, log = _drive(tmp_path, path, header, fn, "exec sleep 60\n")
    assert "RESULT:\n" in out, out
    assert "LIVE" in log, (
        "the watchdog never killed the hung candidate; the probe only "
        f"returned because its deadline ran out:\n{log}")

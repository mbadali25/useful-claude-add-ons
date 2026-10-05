"""`review_run.launch`'s kill-then-communicate sequence, unit-tested against
a fake `Popen` so the pid-reuse race itself (which the OS's real allocator
would need to be provoked to reproduce) never has to happen for the guard
around it to be checked.

BLOCK (Codex, review_run.py `launch`): the timeout-cleanup path used to call
`os.killpg(proc.pid, signal.SIGKILL)` unconditionally on a `communicate()`
timeout, with no check that the leader was still alive. Once the leader has
exited and been reaped, its pid (and any process group numbered the same)
is free for the OS to hand to an unrelated process, so an unconditional
`killpg` by that bare number can reach whatever the OS gave it to next
instead of anything this script started. The fix: `proc.poll()` decides
whether `killpg`/`taskkill` runs at all -- only while the leader is still
alive and unreaped, so the pid cannot yet have been recycled.

BLOCK (Codex, same function): the follow-up `communicate()` after a kill
carried no timeout of its own, so a descendant that escaped the kill and
kept holding the pipe open blocked that call indefinitely -- unbounded by
`--timeout` and unbounded by anything else. The fix: that second call is
now bounded by `POST_KILL_TIMEOUT`; on a second `TimeoutExpired`, `launch`
keeps and decodes whatever partial output CPython's own exception already
carries (`exc.output`/`exc.stderr`, raw bytes since the text-mode
translation never runs on this path) rather than waiting on a descendant
that is not coming back. An earlier version of this fix discarded that
partial output and closed the process's own stdout/stderr streams instead
-- reverted (crew 1.0.21): on Windows, closing a pipe still being read by
CPython's own reader thread for that stream can itself block, trading one
hang for another, and the discard threw away a diagnosis a caller may
actually need.

See test_review_ledger.py::
test_run_timeout_survives_an_escaped_descendant_holding_the_pipe for the
real-subprocess, real-timing version of the second half of this; this
module is the deterministic half; both are named because a mutation
striking either code path should trip at least one of them.
"""
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_checks
import review_run

_POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="review_run.launch's POSIX killpg branch only")


class _FakeProc:
    """Stands in for `subprocess.Popen`. The first `communicate()` call
    always times out (that is what puts `launch` on the kill path at all);
    `poll_result` controls whether the leader reads as still alive
    (`None`) or already exited (anything else); `second_raises` controls
    whether the bounded follow-up `communicate()` also times out."""

    def __init__(self, poll_result, second_raises):
        self.pid = 987654
        self.poll_result = poll_result
        self.second_raises = second_raises
        self.communicate_calls = 0
        self.kills = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        # An unbounded second call is the pre-fix shape being guarded
        # against: a real escaped descendant would block this forever, so
        # this fake refuses to model it as anything but a failure rather
        # than silently returning as though it were bounded too.
        if timeout is None:
            raise AssertionError(
                "communicate() called with no timeout bound on the "
                "post-kill path - a real escaped descendant would block "
                "this call forever")
        if self.second_raises:
            # Real CPython raises TimeoutExpired with whatever it already
            # read attached as raw BYTES, even on a text-mode Popen (the
            # text-mode translation never runs on this path) - see
            # review_run._decode_partial's own docstring for why launch()
            # must decode this rather than trust it as already-str.
            raise subprocess.TimeoutExpired(
                cmd="fake", timeout=timeout,
                output=b"partial stdout bytes", stderr=b"partial stderr bytes")
        return "partial stdout", "partial stderr"

    def poll(self):
        return self.poll_result

    def kill(self):
        self.kills += 1


def _patch_popen(monkeypatch, fake):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: fake)


@_POSIX_ONLY
def test_killpg_runs_when_the_leader_is_still_alive(monkeypatch):
    fake = _FakeProc(poll_result=None, second_raises=False)
    _patch_popen(monkeypatch, fake)
    calls = []
    monkeypatch.setattr(review_run.os, "killpg", lambda pid, sig: calls.append((pid, sig)))

    stdout, stderr, code, timed_out = review_run.launch(["fake"], ".", 1)

    assert calls == [(fake.pid, review_run.signal.SIGKILL)]
    assert (code, timed_out) == (None, True)
    assert (stdout, stderr) == ("partial stdout", "partial stderr")


@_POSIX_ONLY
def test_killpg_is_skipped_once_the_leader_has_already_exited(monkeypatch):
    """Must-refuse: once `poll()` shows the leader gone, its pid is free
    for reuse and must not be signalled by bare number."""
    fake = _FakeProc(poll_result=0, second_raises=False)
    _patch_popen(monkeypatch, fake)
    calls = []
    monkeypatch.setattr(review_run.os, "killpg", lambda pid, sig: calls.append((pid, sig)))

    stdout, stderr, code, timed_out = review_run.launch(["fake"], ".", 1)

    assert calls == [], "killpg must not run once the leader has already exited"
    assert (code, timed_out) == (None, True)
    assert stdout == "partial stdout"
    assert "escaped" in stderr


@_POSIX_ONLY
def test_post_kill_communicate_is_bounded_and_keeps_the_partial_output(monkeypatch):
    """A descendant that escaped the kill keeps holding the pipe open, so
    the bounded follow-up `communicate()` also times out -- `launch` must
    still return (not hang), keep and decode whatever partial output
    CPython's own TimeoutExpired already captured, and say the run
    escaped. FIX (crew 1.0.21): an earlier version of this discarded that
    partial output and closed the process's own stdout/stderr streams
    instead -- reverted, since closing a pipe still being read by
    CPython's own reader thread for that stream can itself block on
    Windows, trading one hang for another."""
    fake = _FakeProc(poll_result=None, second_raises=True)
    _patch_popen(monkeypatch, fake)
    monkeypatch.setattr(review_run.os, "killpg", lambda pid, sig: None)

    stdout, stderr, code, timed_out = review_run.launch(["fake"], ".", 1)

    assert (code, timed_out) == (None, True)
    assert stdout == "partial stdout bytes"
    assert "partial stderr bytes" in stderr
    assert "escaped" in stderr


class _FakeJob:
    """A job object that records what was asked of it; `fail` makes
    `terminate()` raise as a real TerminateJobObject failure does."""

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def adopt(self, proc):
        self.calls.append("adopt")

    def terminate(self):
        self.calls.append("terminate")
        if self.fail:
            raise OSError(5, "TerminateJobObject failed")

    def close(self):
        self.calls.append("close")


def _windows(monkeypatch, job, killer):
    """Drive launch's Windows branch on any host, with no os.killpg at all."""
    monkeypatch.setattr(review_checks, "_WINDOWS", True)
    monkeypatch.setattr(review_checks, "taskkill", lambda: killer)
    if job is None:
        def no_job(kill_on_close):
            raise OSError(1, "no job here")
        monkeypatch.setattr(review_checks, "new_job", no_job)
    else:
        monkeypatch.setattr(review_checks, "new_job", lambda kill_on_close: job)
    monkeypatch.setattr(review_run, "_launch_flags", lambda j: {})
    monkeypatch.delattr(review_run.os, "killpg", raising=False)
    fake = _FakeProc(poll_result=None, second_raises=False)
    _patch_popen(monkeypatch, fake)
    return fake


@pytest.mark.parametrize("with_job", [False, True])
def test_windows_timeout_without_taskkill_never_calls_killpg(monkeypatch, with_job):
    """L-0605, review round 10 FIX review_run.py:400: with no taskkill the
    old code fell to os.killpg, which Windows does not have."""
    job = _FakeJob() if with_job else None
    fake = _windows(monkeypatch, job, None)

    _, stderr, code, timed_out = review_run.launch(["fake"], ".", 1)

    assert ((code, timed_out), fake.kills, "escaped" in stderr, "no taskkill.exe" in stderr) == (
        (None, True), 1, not with_job, not with_job), stderr


def test_windows_timeout_with_taskkill_uses_it(monkeypatch):
    """taskkill /T walks parent pids, so even its exit 0 never establishes
    that a child whose parent already exited was ended: no job, escaped."""
    fake = _windows(monkeypatch, None, r"C:\Windows\System32\taskkill.exe")
    seen = []
    monkeypatch.setattr(review_run.subprocess, "run", lambda argv, **k: seen.append(argv) or
                        subprocess.CompletedProcess(argv, 0, b"", b""))

    _, stderr, _, timed_out = review_run.launch(["fake"], ".", 1)

    assert (seen, timed_out, "escaped" in stderr,
            "taskkill /T cannot reach a child whose parent already exited" in stderr) == (
        [[r"C:\Windows\System32\taskkill.exe", "/T", "/F", "/PID", str(fake.pid)]], True,
        True, True), stderr


@pytest.mark.parametrize("with_job", [False, True])
@pytest.mark.parametrize("outcome, text", [
    ("oserror", "taskkill failed"), ("timeout", "taskkill failed"), ("exit1", "taskkill exited 1")])
def test_windows_timeout_when_taskkill_fails_kills_the_leader(monkeypatch, outcome, text, with_job):
    """A taskkill that raises or exits nonzero is not a kill: the held
    leader is ended by handle and the run says what may have escaped. With
    a job, its terminate() fails so that taskkill is reached at all."""
    job = _FakeJob(fail=True) if with_job else None
    fake = _windows(monkeypatch, job, r"C:\Windows\System32\taskkill.exe")

    def run(argv, **kwargs):
        if outcome == "oserror":
            raise OSError(2, "boom")
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("taskkill", 30)
        return subprocess.CompletedProcess(argv, 1, b"", b"")
    monkeypatch.setattr(review_run.subprocess, "run", run)

    _, stderr, _, timed_out = review_run.launch(["fake"], ".", 1)

    assert (timed_out, fake.kills, text in stderr, "escaped" in stderr) == (
        True, 1, True, True), stderr


def test_windows_timeout_when_the_job_cannot_end_says_escaped(monkeypatch):
    job = _FakeJob(fail=True)
    fake = _windows(monkeypatch, job, None)

    _, stderr, _, timed_out = review_run.launch(["fake"], ".", 1)

    assert (timed_out, fake.kills, "escaped" in stderr, "job termination failed" in stderr) == (
        True, 1, True, True), stderr


def test_review_run_exit_codes_are_distinct():
    """L-0528: one number never means two things. EXIT_UNVERIFIED was 5, the
    same as the probe's EXIT_PROBE_LIMITED, so a caller that did not know
    which mode ran could not tell "the verify gate has not passed" from "Codex
    hit a usage limit". Found by introspection, so a code added later is
    covered without editing this test."""
    codes = {name: value for name, value in vars(review_run).items()
             if name.startswith("EXIT_") and isinstance(value, int)}
    by_value = {}
    for name, value in sorted(codes.items()):
        by_value.setdefault(value, []).append(name)

    assert {"EXIT_UNVERIFIED", "EXIT_PROBE_LIMITED"} <= set(codes)
    assert {v: n for v, n in by_value.items() if len(n) > 1} == {}

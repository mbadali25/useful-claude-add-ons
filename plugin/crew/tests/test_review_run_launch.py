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
import review_run

pytestmark = pytest.mark.skipif(
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


def _patch_popen(monkeypatch, fake):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: fake)


def test_killpg_runs_when_the_leader_is_still_alive(monkeypatch):
    fake = _FakeProc(poll_result=None, second_raises=False)
    _patch_popen(monkeypatch, fake)
    calls = []
    monkeypatch.setattr(review_run.os, "killpg", lambda pid, sig: calls.append((pid, sig)))

    stdout, stderr, code, timed_out = review_run.launch(["fake"], ".", 1)

    assert calls == [(fake.pid, review_run.signal.SIGKILL)]
    assert (code, timed_out) == (None, True)
    assert (stdout, stderr) == ("partial stdout", "partial stderr")


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

"""Tests for poll_fixtures: the deadline poll that replaces a fixed sleep.

Each helper gets a must-pass case (the condition arrives late, later than the
fixed sleep it replaces) and a must-fail case (the condition never arrives, and
the helper hands back the last real probe value rather than a success). Every
case asserts the returned value, so a helper that returns early or invents a
success cannot pass vacuously (L-0516).
"""
import contextlib
import subprocess
import sys
import threading
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import poll_fixtures


def test_poll_until_keeps_probing_until_the_condition_holds():
    values = [[7], [7], []]
    calls = []

    def probe():
        calls.append(1)
        return values.pop(0)

    got = poll_fixtures.poll_until(probe, done=lambda v: not v, timeout=10, interval=0)

    assert (got, len(calls)) == ([], 3)


def test_poll_until_probes_at_least_once_with_a_zero_timeout():
    calls = []

    def probe():
        calls.append(1)
        return [7]

    got = poll_fixtures.poll_until(probe, done=lambda v: not v, timeout=0)

    assert (got, len(calls) >= 1) == ([7], True)


class _Clock:
    """A scripted clock: `sleep` advances `monotonic` and nothing waits."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.mark.parametrize("interval, expected", [(2.0, "pending"), (0.5, "done")],
                         ids=["done-after-deadline", "done-before-deadline"])
def test_poll_until_never_returns_a_value_first_seen_after_the_deadline(monkeypatch, interval,
                                                                        expected):
    clock = _Clock()
    monkeypatch.setattr(poll_fixtures, "time", clock)

    got = poll_fixtures.poll_until(lambda: "done" if clock.now >= 0.5 else "pending",
                                   done=lambda v: v == "done", timeout=1.0, interval=interval)

    assert got == expected


@contextlib.contextmanager
def _child(seconds):
    """Run a python child that sleeps `seconds`; kill it and reap it with a bounded wait.

    Not `with subprocess.Popen(...)`: `Popen.__exit__` reaps with `wait()` and
    no timeout, so a child that ignores the kill would hang the suite.
    """
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-c", f"import time; time.sleep({seconds})"])
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_poll_until_returns_once_a_late_child_has_died():
    began = time.monotonic()
    with _child(1.0) as proc:
        alive = poll_fixtures.poll_until(lambda: proc.poll() is None,
                                         done=lambda v: not v, timeout=10)
        waited = time.monotonic() - began

    assert (alive, waited >= 0.9) == (False, True)


def test_poll_until_reports_a_child_that_never_dies_at_the_deadline():
    began = time.monotonic()
    with _child(120) as proc:
        alive = poll_fixtures.poll_until(lambda: proc.poll() is None,
                                         done=lambda v: not v, timeout=1.0)
        waited = time.monotonic() - began

    assert (alive, waited >= 1.0) == (True, True)


@pytest.mark.parametrize("seconds", [0, 120], ids=["already-dead", "never-dies"])
def test_child_cleanup_reaps_with_a_bounded_wait(monkeypatch, seconds):
    real_wait = subprocess.Popen.wait
    timeouts = []

    def recording_wait(self, timeout=None):
        timeouts.append(timeout)
        return real_wait(self, timeout=10 if timeout is None else timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", recording_wait)

    with _child(seconds) as proc:
        if seconds == 0:
            real_wait(proc, timeout=10)

    assert (proc.returncode is not None, None in timeouts) == (True, False)


def test_wait_for_pidfile_waits_past_an_empty_file_for_the_pid(tmp_path):
    path = tmp_path / "g.pid"
    path.write_text("", encoding="utf-8")
    timer = threading.Timer(0.5, lambda: path.write_text("4242\n", encoding="utf-8"))
    timer.start()
    try:
        pid = poll_fixtures.wait_for_pidfile(path, timeout=10)
    finally:
        timer.join()

    assert pid == 4242


@pytest.mark.parametrize("create, timeout", [(True, 0.5), (False, 0.3)],
                         ids=["empty", "missing"])
def test_wait_for_pidfile_gives_none_when_the_pid_never_arrives(tmp_path, create, timeout):
    path = tmp_path / "g.pid"
    if create:
        path.write_text("", encoding="utf-8")

    pid = poll_fixtures.wait_for_pidfile(path, timeout=timeout)

    assert pid is None

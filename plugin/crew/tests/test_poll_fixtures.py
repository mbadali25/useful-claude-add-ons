"""Tests for poll_fixtures: the deadline poll that replaces a fixed sleep.

Each helper gets a must-pass case (the condition arrives late, later than the
fixed sleep it replaces) and a must-fail case (the condition never arrives, and
the helper hands back the last real probe value rather than a success). Every
case asserts the returned value, so a helper that returns early or invents a
success cannot pass vacuously (L-0516).
"""
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


def test_poll_until_returns_once_a_late_child_has_died():
    began = time.monotonic()
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.0)"]) as proc:
        alive = poll_fixtures.poll_until(lambda: proc.poll() is None,
                                         done=lambda v: not v, timeout=10)
        waited = time.monotonic() - began

    assert (alive, waited >= 0.9) == (False, True)


def test_poll_until_reports_a_child_that_never_dies_at_the_deadline():
    began = time.monotonic()
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"]) as proc:
        try:
            alive = poll_fixtures.poll_until(lambda: proc.poll() is None,
                                             done=lambda v: not v, timeout=1.0)
            waited = time.monotonic() - began
        finally:
            proc.kill()

    assert (alive, waited >= 1.0) == (True, True)


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

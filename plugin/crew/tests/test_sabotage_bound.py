"""T-0080: every sabotage entry runs under a memory cap and a wall-clock limit.

Two cloud guard mutations turn a bounded read into an unbounded one. Before
this, `sabotage.py` ran each entry's pytest as a bare `subprocess.run`, so an
uncapped full run grew one python3 past 19 GB and the host's OOM killer took
the orchestrating session with it. `sabotage_bound.run` is the harness's own
bound: the child starts in its own process group under `RLIMIT_AS` (Linux),
and a timeout stops the whole group and returns 124.

Every case here runs a throwaway python child, never a crew test, so the
suite stays seconds long and cannot be the thing that grows.
"""
import os
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import sabotage_bound

_LINUX = sys.platform.startswith("linux")
_CAP_MIB = 256
_OVER = f"bytearray({2 * _CAP_MIB} << 20)"


def _py(code):
    return [sys.executable, "-c", code]


def _run(argv, mem_mib=_CAP_MIB, timeout_s=60, cwd=None):
    return sabotage_bound.run(argv, cwd or os.getcwd(), dict(os.environ),
                              mem_mib, timeout_s)


def _gone(pid):
    """True when `pid` no longer runs. A zombie counts as gone: in a container
    whose PID 1 does not reap, a killed orphan stays a zombie forever."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:
        return True


# --- must block --------------------------------------------------------------

@pytest.mark.skipif(not _LINUX, reason="RLIMIT_AS is enforced on Linux only")
def test_a_child_over_the_memory_cap_fails_instead_of_growing():
    code, output = _run(_py(_OVER))

    assert code != 0, output
    assert "MemoryError" in output


@pytest.mark.skipif(not _LINUX, reason="RLIMIT_AS is enforced on Linux only")
def test_the_memory_cap_reaches_a_grandchild():
    """The guard a crew test drives is a subprocess of the test, so the cap has
    to be inherited by everything the child starts, not set on pytest alone."""
    grandchild = (
        "import resource, sys; print('AS', resource.getrlimit(resource.RLIMIT_AS)[0]); "
        + _OVER)
    child = ("import subprocess, sys; "
             f"sys.exit(subprocess.call([sys.executable, '-c', {grandchild!r}]))")

    code, output = _run(_py(child))

    assert code != 0, output
    assert f"AS {_CAP_MIB << 20}" in output
    assert "MemoryError" in output


def test_a_timeout_stops_the_whole_group_and_returns_124(tmp_path):
    """The grandchild is a `sleep` that ignores nothing and outlives its
    parent; stopping only the leader would leave it running."""
    pidfile = tmp_path / "grandchild.pid"
    child = ("import subprocess, sys, time; "
             "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)']); "
             f"open({str(pidfile)!r}, 'w').write(str(p.pid)); "
             "time.sleep(300)")

    started = time.monotonic()
    code, _ = _run(_py(child), timeout_s=3)

    assert code == sabotage_bound.TIMED_OUT == 124
    assert time.monotonic() - started < 60
    grandchild = int(pidfile.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10
    while not _gone(grandchild) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert _gone(grandchild), f"grandchild {grandchild} outlived the timeout"


@pytest.mark.parametrize("name, value", [
    ("CREW_SABOTAGE_MEM_MB", "abc"),
    ("CREW_SABOTAGE_MEM_MB", "-1"),
    ("CREW_SABOTAGE_MEM_MB", ""),
    ("CREW_SABOTAGE_MEM_MB", "1.5"),
    ("CREW_SABOTAGE_MEM_MB", " 4096"),
    ("CREW_SABOTAGE_TIMEOUT_S", "0"),
    ("CREW_SABOTAGE_TIMEOUT_S", "abc"),
    ("CREW_SABOTAGE_TIMEOUT_S", ""),
])
def test_an_unreadable_limit_refuses_and_never_means_no_cap(name, value):
    with pytest.raises(ValueError) as caught:
        sabotage_bound.limits({name: value})

    assert name in str(caught.value)


# --- must allow --------------------------------------------------------------

def test_a_child_under_the_cap_is_unaffected():
    code, output = _run(_py("b = bytearray(16 << 20); print('fine', len(b))"))

    assert code == 0, output
    assert "fine 16777216" in output


def test_the_defaults_and_a_readable_override():
    assert sabotage_bound.limits({}) == (4096, 600)
    assert sabotage_bound.limits({"CREW_SABOTAGE_MEM_MB": "8192",
                                  "CREW_SABOTAGE_TIMEOUT_S": "30"}) == (8192, 30)


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals")
def test_a_child_that_dies_of_a_signal_returns_the_negative_code():
    code, _ = _run(_py("import os, signal; os.kill(os.getpid(), signal.SIGTERM)"))

    assert code == -15


def test_zero_memory_is_no_cap_and_the_line_says_absent():
    assert sabotage_bound.limits({"CREW_SABOTAGE_MEM_MB": "0"}) == (0, 600)
    line = sabotage_bound.describe(0, 600)

    assert line.startswith("bound: memory cap absent (")
    assert "CREW_SABOTAGE_MEM_MB=0" in line
    assert line.endswith("600 s per entry")
    if _LINUX:
        code, output = _run(_py(
            "import resource; print('AS', resource.getrlimit(resource.RLIMIT_AS)[0])"),
            mem_mib=0)
        assert code == 0, output
        assert f"AS {_CAP_MIB << 20}" not in output


def test_the_bound_line_says_absent_where_no_cap_is_enforced(monkeypatch):
    if _LINUX:
        assert sabotage_bound.describe(4096, 600) == (
            "bound: memory 4096 MiB per process (RLIMIT_AS), 600 s per entry")
    monkeypatch.setattr(sabotage_bound.sys, "platform", "win32")

    line = sabotage_bound.describe(4096, 600)

    assert line.startswith("bound: memory cap absent (")
    assert "win32" in line
    assert "4096 MiB per process" not in line


def test_the_harness_dying_stops_a_running_child(tmp_path, monkeypatch):
    """No test process outlives the harness: a SystemExit raised inside the
    wait (what sabotage.py's signal handler does) stops the group first."""
    pidfile = tmp_path / "child.pid"
    child = (f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); "
             "time.sleep(300)")

    def _interrupted(self, *args, **kwargs):
        deadline = time.monotonic() + 30
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        raise SystemExit(143)

    monkeypatch.setattr(sabotage_bound.subprocess.Popen, "communicate", _interrupted)
    with pytest.raises(SystemExit):
        _run(_py(child))

    pid = int(pidfile.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10
    while not _gone(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert _gone(pid), f"child {pid} outlived the harness"

"""crew_holder.py: the one liveness proof crew runners share (T-0049).

The probe cases moved here with the functions they pin, from T-0030's
`test_crew_coord.py` (branch T-0030-coord a54117e8), re-pointed at
`crew_holder`. `processes_in` and `private_dir` are new in T-0049. No test
starts anything that outlives it: every child is killed and reaped.
"""
import builtins
import json
import os
import shutil
import stat
import subprocess
import sys
import time

import context  # noqa: F401  pylint: disable=unused-import
import crew_holder
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(crew_holder.__file__))


def _dead_pid():
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], check=True,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return int(proc.stdout.strip())


def _wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _linux_only():
    if not sys.platform.startswith("linux"):
        pytest.skip("the /proc probe is Linux-only; this platform was NOT tested")


@pytest.fixture(name="live_pid")
def _live_pid():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],  # pylint: disable=consider-using-with
                            stdin=subprocess.DEVNULL)
    yield proc.pid
    proc.kill()
    proc.wait()


# --- moved from T-0030 ------------------------------------------------------------

def test_linux_probe_reads_live_dead_and_zombie(live_pid):
    _linux_only()
    zombie = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL)  # pylint: disable=consider-using-with
    assert _wait_for(lambda: crew_holder.probe_pid(zombie.pid).state == "gone", timeout=10)
    zombie.wait()

    live = crew_holder.probe_pid(live_pid)
    dead = crew_holder.probe_pid(_dead_pid())

    assert (live.state, live.measured) == ("alive", True)
    assert live.start and live.start.isdigit()
    assert (dead.state, dead.measured) == ("gone", True)


def _hide_proc(monkeypatch):
    real_open = builtins.open

    def fake(path, *args, **kwargs):
        if str(path).startswith("/proc/"):
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", fake)


def test_linux_probe_live_pid_with_unreadable_proc_reads_alive(monkeypatch, live_pid):
    _linux_only()
    _hide_proc(monkeypatch)

    probe = crew_holder.probe_pid(live_pid)

    assert probe.state == "alive"


def test_linux_probe_another_users_pid_with_unreadable_proc_reads_alive(monkeypatch):
    _linux_only()
    pid = _dead_pid()

    def denied(_pid, _sig):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(crew_holder.os, "kill", denied)
    _hide_proc(monkeypatch)

    probe = crew_holder.probe_pid(pid)

    assert probe.state == "alive"


class _FakeKernel32:
    """A ctypes-level stand-in for kernel32: GetProcessTimes writes into the
    FILETIME structures it is handed by reference, as the real call does."""

    def __init__(self, handle=0x44, error=0, times_ok=True, created=0, exited=0):
        self.handle, self.error, self.times_ok = handle, error, times_ok
        self.created, self.exited = created, exited
        self.opened, self.closed = [], []

    def OpenProcess(self, access, inherit, pid):  # noqa: N802  pylint: disable=invalid-name
        self.opened.append((access, inherit, pid))
        return self.handle

    def GetProcessTimes(self, _handle, created, exited, _kernel, _user):  # noqa: N802  pylint: disable=invalid-name
        if not self.times_ok:
            return 0
        for ref, value in ((created, self.created), (exited, self.exited)):
            ref._obj.dwLowDateTime = value & 0xFFFFFFFF  # pylint: disable=protected-access
            ref._obj.dwHighDateTime = value >> 32  # pylint: disable=protected-access
        return 1

    def CloseHandle(self, handle):  # noqa: N802  pylint: disable=invalid-name
        self.closed.append(handle)
        return 1


CREATED = 133_700_000_000_000_123
EXITED = 133_700_000_600_000_000


@pytest.mark.parametrize("kernel, expected", [
    (_FakeKernel32(handle=0, error=87), crew_holder.PidProbe("gone", None, True)),
    (_FakeKernel32(handle=0, error=5), crew_holder.PidProbe("alive", None, True)),
    (_FakeKernel32(handle=0, error=6), crew_holder.PidProbe("alive", None, True)),
    (_FakeKernel32(handle=0, error=0), crew_holder.PidProbe("alive", None, True)),
    (_FakeKernel32(created=CREATED, exited=EXITED), crew_holder.PidProbe("gone", None, True)),
    (_FakeKernel32(created=CREATED, exited=0), crew_holder.PidProbe("alive", str(CREATED), True)),
    (_FakeKernel32(times_ok=False), crew_holder.PidProbe("alive", None, True)),
], ids=["err87-gone", "err5-alive", "err6-alive", "err0-alive", "exit-filetime-gone", "running-alive",
        "times-fail-alive"])
def test_windows_probe_reads_the_measured_answers(kernel, expected):
    probe = crew_holder._windows_probe(4242, kernel=kernel, last_error=lambda: kernel.error)  # pylint: disable=protected-access

    assert probe == expected


def test_windows_probe_opens_limited_and_closes_every_handle():
    kernel = _FakeKernel32(created=CREATED)

    crew_holder._windows_probe(4242, kernel=kernel, last_error=lambda: 0)  # pylint: disable=protected-access

    assert kernel.opened == [(0x1000, False, 4242)]
    assert kernel.closed == [kernel.handle]


def test_probe_from_inside_a_bwrap_pid_namespace_cannot_tell(live_pid):
    _linux_only()
    if not shutil.which("bwrap"):
        pytest.skip("bwrap is not installed; the sandbox's own namespace was NOT exercised")
    holder = {"pid": live_pid, "pidns": os.readlink("/proc/self/ns/pid")}
    code = ("import json, sys, crew_holder\n"
            "holder = json.loads(sys.argv[1])\n"
            "print(crew_holder.probe_pid(holder['pid']).state, crew_holder.probe_holder(holder).state)\n")
    env = dict(os.environ, PYTHONPATH=SCRIPT_DIR)
    done = subprocess.run(["bwrap", "--unshare-pid", "--dev-bind", "/", "/", "--proc", "/proc",
                           sys.executable, "-c", code, json.dumps(holder)],
                          capture_output=True, text=True, env=env, check=False, stdin=subprocess.DEVNULL)
    if done.returncode != 0 and "crew_holder" not in done.stderr:
        pytest.skip(f"bwrap could not start here ({done.stderr.strip()[:120]}); NOT exercised")

    assert done.stdout.split() == ["gone", "unknown"], done.stderr


# --- same_holder and owner_signal (the contract crew_inflight relies on) -----------

def _holder(**over):
    base = {"session": "s", "bridge_session": None, "pid": 10, "pid_start": "5", "pidns": None,
            "machine": "m", "worktree": "/w"}
    base.update(over)
    return base


@pytest.mark.parametrize("other, same", [
    ({}, True), ({"session": "t"}, False), ({"pid": 11}, False), ({"machine": "n"}, False),
    ({"worktree": "/x"}, False), ({"pid_start": "6"}, False), ({"pid_start": None}, True),
    ({"bridge_session": "b2"}, False),
], ids=["identical", "session", "pid", "machine", "worktree", "start", "start-missing", "bridge-session"])
def test_same_holder_compares_every_identity_field(other, same):
    assert crew_holder.same_holder(_holder(), _holder(**other)) is same


@pytest.mark.parametrize("env, owner", [((), True), (("CLAUDECODE",), False),
                                        (("CLAUDE_CODE_SESSION_ID",), False)],
                         ids=["terminal", "claudecode", "session-id"])
def test_owner_signal_needs_both_variables_absent(monkeypatch, env, owner):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    for name in env:
        monkeypatch.setenv(name, "1")

    assert crew_holder.owner_signal() is owner


# --- private_dir (the heartbeat_dir check, generalised) ----------------------------

def test_private_dir_is_created_0700(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(crew_holder.tempfile, "tempdir", None)

    path = crew_holder.private_dir("crew-inflight")

    assert os.path.dirname(path) == str(tmp_path)
    if hasattr(os, "getuid"):
        assert os.path.basename(path) == f"crew-inflight-{os.getuid()}"
        assert stat.S_IMODE(os.lstat(path).st_mode) == 0o700


def test_private_dir_refuses_a_group_readable_directory(monkeypatch, tmp_path):
    if not hasattr(os, "getuid"):
        pytest.skip("POSIX modes only; this platform was NOT tested")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(crew_holder.tempfile, "tempdir", None)
    target = tmp_path / f"crew-inflight-{os.getuid()}"
    target.mkdir()
    target.chmod(0o750)

    with pytest.raises(OSError):
        crew_holder.private_dir("crew-inflight")


def test_private_dir_refuses_a_symlink(monkeypatch, tmp_path):
    if not hasattr(os, "getuid"):
        pytest.skip("POSIX modes only; this platform was NOT tested")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(crew_holder.tempfile, "tempdir", None)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    os.symlink(elsewhere, tmp_path / f"crew-inflight-{os.getuid()}")

    with pytest.raises(OSError):
        crew_holder.private_dir("crew-inflight")


# --- processes_in (new in T-0049) ----------------------------------------------------

def test_processes_in_finds_a_child_whose_cwd_is_inside(monkeypatch, tmp_path, live_pid):
    _linux_only()
    inside = tmp_path / "wt" / "sub"
    inside.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PID", str(live_pid))
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],  # pylint: disable=consider-using-with
                             cwd=str(inside), stdin=subprocess.DEVNULL)
    try:
        state, pids = crew_holder.processes_in(str(tmp_path / "wt"))
    finally:
        child.kill()
        child.wait()

    assert state == "live"
    assert child.pid in pids


def test_processes_in_none_when_no_process_is_inside(monkeypatch, tmp_path, live_pid):
    _linux_only()
    (tmp_path / "wt").mkdir()
    monkeypatch.setenv("CLAUDE_PID", str(live_pid))

    assert crew_holder.processes_in(str(tmp_path / "wt")) == ("none", [])


def test_processes_in_unknown_when_own_pid_is_invisible(monkeypatch, tmp_path):
    _linux_only()
    (tmp_path / "wt").mkdir()
    monkeypatch.setenv("CLAUDE_PID", str(_dead_pid()))

    state, reason = crew_holder.processes_in(str(tmp_path / "wt"))

    assert state == "unknown"
    assert "CLAUDE_PID" in reason


def test_processes_in_unknown_without_claude_pid(monkeypatch, tmp_path):
    _linux_only()
    monkeypatch.delenv("CLAUDE_PID", raising=False)

    assert crew_holder.processes_in(str(tmp_path))[0] == "unknown"


def test_processes_in_unknown_off_linux(monkeypatch, tmp_path, live_pid):
    monkeypatch.setenv("CLAUDE_PID", str(live_pid))
    monkeypatch.setattr(crew_holder.sys, "platform", "darwin")

    state, reason = crew_holder.processes_in(str(tmp_path))

    assert state == "unknown"
    assert "Linux" in reason


def test_processes_in_unknown_when_proc_cannot_be_listed(monkeypatch, tmp_path, live_pid):
    _linux_only()
    monkeypatch.setenv("CLAUDE_PID", str(live_pid))

    def refuse(_path):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(crew_holder.os, "listdir", refuse)

    assert crew_holder.processes_in(str(tmp_path))[0] == "unknown"


def test_processes_in_unknown_when_a_cwd_cannot_be_read(monkeypatch, tmp_path, live_pid):
    _linux_only()
    (tmp_path / "wt").mkdir()
    monkeypatch.setenv("CLAUDE_PID", str(live_pid))
    real = crew_holder.os.readlink

    def refuse(path, *args, **kwargs):
        if path == f"/proc/{live_pid}/cwd":
            raise PermissionError(13, "Permission denied")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(crew_holder.os, "readlink", refuse)

    state, reason = crew_holder.processes_in(str(tmp_path / "wt"))

    assert state == "unknown"
    assert "cannot be read" in reason


def test_processes_in_skips_a_process_gone_mid_scan(monkeypatch, tmp_path, live_pid):
    _linux_only()
    (tmp_path / "wt").mkdir()
    monkeypatch.setenv("CLAUDE_PID", str(live_pid))
    real = crew_holder.os.readlink

    def vanish(path, *args, **kwargs):
        if path == f"/proc/{live_pid}/cwd":
            raise FileNotFoundError(2, "No such file or directory")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(crew_holder.os, "readlink", vanish)

    assert crew_holder.processes_in(str(tmp_path / "wt"))[0] in ("none", "live")


@pytest.mark.parametrize("left, right", [(None, None), (None, 10), (10, None)], ids=["both", "left", "right"])
def test_same_holder_is_false_when_a_pid_is_missing(left, right):
    assert crew_holder.same_holder(_holder(pid=left), _holder(pid=right)) is False

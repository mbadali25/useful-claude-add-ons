"""crew_inflight.py: in-flight markers, so no two runners drive one ticket (T-0049).

Every case builds a throwaway repository under tmp_path with a second
worktree. Sessions are environment variables set by monkeypatch; the detached
beat loop is never started by `begin` here (`_start_loop` is replaced), and
the loop itself runs in-process with a stubbed probe and sleep, or as a
foreground child that exits at once. TMPDIR points into tmp_path, so the loop's
log and lock never reach the real temp directory.
"""
import datetime
import json
import os
import shlex
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_holder
import crew_inflight
import crew_ticket
import pytest
import review_ledger
from review_fixtures import git, init_repo

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(crew_inflight.__file__)), "crew_inflight.py")
TICKET = "T-0005"
SENTINEL = "SENTINEL-MESSAGING-TOKEN-49aa"
T0 = crew_holder.parse_stamp("2026-09-30T10:00:00+00:00")
REAL_START_LOOP = crew_inflight._start_loop  # pylint: disable=protected-access


# --- fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _private_tmp(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(crew_holder.tempfile, "tempdir", None)


@pytest.fixture(autouse=True)
def _no_loop(monkeypatch):
    started = []
    monkeypatch.setattr(crew_inflight, "_start_loop", lambda *a, **k: started.append((a, k)))
    return started


@pytest.fixture(name="clock")
def _clock(monkeypatch):
    now = {"t": T0}
    monkeypatch.setattr(crew_inflight, "_now", lambda: now["t"])
    return now


@pytest.fixture(name="live_pid")
def _live_pid():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],  # pylint: disable=consider-using-with
                            stdin=subprocess.DEVNULL)
    yield proc.pid
    proc.kill()
    proc.wait()


@pytest.fixture(name="repo")
def _repo(tmp_path):
    main = init_repo(tmp_path / "main")
    git(main, "worktree", "add", "-q", "-b", f"{TICKET}-build", str(tmp_path / "wt2"))
    return {"main": os.path.realpath(main), "wt2": os.path.realpath(tmp_path / "wt2")}


def _session(monkeypatch, sid, pid):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)
    monkeypatch.setenv("CLAUDE_PID", str(pid))
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", SENTINEL)


def _owner_terminal(monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"):
        monkeypatch.delenv(name, raising=False)


def _dead_pid():
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], check=True,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return int(proc.stdout.strip())


def _run(capsys, root, *argv):
    code = crew_inflight.main([argv[0], "--root", root] + list(argv[1:]))
    out = capsys.readouterr()
    return code, out.out + out.err


def _begin(capsys, root, runner, *extra):
    return _run(capsys, root, "begin", "--ticket", TICKET, "--runner", runner, *extra)


def _marker_bytes(repo):
    path = crew_inflight.marker_path(repo["main"], TICKET)
    with open(path, "rb") as handle:
        return handle.read()


def _marker(repo):
    return json.loads(_marker_bytes(repo))


def _log(repo):
    path = os.path.join(crew_inflight.inflight_dir(repo["main"]), crew_inflight.LOG)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _held_by_b(capsys, monkeypatch, repo, pid, runner="workflow:lane-b"):
    _session(monkeypatch, "sess-b", pid)
    code, out = _begin(capsys, repo["main"], runner)
    assert code == 0, out


def _assert_refused(code, out, repo, before, expected_code, state):
    assert code == expected_code, out
    assert f"result={state}" in out.splitlines()[-1], out
    if before is None:
        assert not os.path.exists(crew_inflight.marker_path(repo["main"], TICKET))
    else:
        assert _marker_bytes(repo) == before


# --- begin: must block ---------------------------------------------------------

def test_begin_refuses_live_marker(capsys, monkeypatch, repo, clock, live_pid):
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before, logged = _marker_bytes(repo), len(_log(repo))
    _session(monkeypatch, "sess-a", live_pid)
    clock["t"] = T0 + datetime.timedelta(minutes=5)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 1, "live")
    assert "workflow:lane-b" in out
    assert len(_log(repo)) == logged


def test_begin_refuses_stale_marker_and_prints_clear_command(capsys, monkeypatch, repo, clock, live_pid):
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)
    clock["t"] = T0 + datetime.timedelta(minutes=crew_inflight.TTL_MINUTES + 1)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 1, "stale")
    assert f"crew_inflight.py clear --root {repo['main']} --ticket {TICKET} --by" in out


def test_begin_refuses_dead_pid_marker_as_stale(capsys, monkeypatch, repo, clock, live_pid):
    if not sys.platform.startswith("linux"):
        pytest.skip("a provably gone pid is measured on Linux here; this platform was NOT tested")
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],  # pylint: disable=consider-using-with
                              stdin=subprocess.DEVNULL)
    _held_by_b(capsys, monkeypatch, repo, victim.pid)
    victim.kill()
    victim.wait()
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)
    clock["t"] = T0 + datetime.timedelta(minutes=1)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 1, "stale")
    assert "gone" in out


@pytest.mark.parametrize("damage", ["bad-json", "json-list", "schema-2", "no-runner", "directory",
                                    "unlistable"])
def test_begin_refuses_unreadable_marker(capsys, monkeypatch, repo, clock, live_pid, damage):  # pylint: disable=unused-argument
    folder = crew_inflight.inflight_dir(repo["main"])
    os.makedirs(folder, exist_ok=True)
    path = crew_inflight.marker_path(repo["main"], TICKET)
    good = {"schema": 1, "ticket": TICKET, "state": "working", "runner": "workflow:x",
            "holder": {"session": "s", "pid": live_pid, "machine": "m", "worktree": "/w"},
            "began_at": crew_holder.stamp(T0), "heartbeat_at": crew_holder.stamp(T0)}
    if damage == "unlistable":
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root lists any directory: the unlistable inflight directory was NOT tested")
        os.chmod(folder, 0)
    elif damage == "directory":
        os.mkdir(path)
    else:
        text = {"bad-json": "{not json",
                "json-list": "[]",
                "schema-2": json.dumps(dict(good, schema=2)),
                "no-runner": json.dumps({k: v for k, v in good.items() if k != "runner"})}[damage]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    _session(monkeypatch, "sess-a", live_pid)
    try:
        code, out = _begin(capsys, repo["main"], "autopilot")
    finally:
        os.chmod(folder, 0o755)

    assert code == 3, out
    assert "result=unknown" in out.splitlines()[-1]
    assert os.path.isdir(path) if damage == "directory" else True


def test_begin_refuses_same_session_other_runner(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)
    code, out = _begin(capsys, repo["main"], "agent:priority-t0005")
    assert code == 0, out
    before = _marker_bytes(repo)

    code, out = _begin(capsys, repo["main"], "workflow:lane-7")

    _assert_refused(code, out, repo, before, 1, "live")


def test_begin_without_session_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    """begin refuses before it asks `holds`: `holds` has its own `me is None`
    guard with the same words, so asserting the text alone would pass with
    begin's refusal removed (an equivalent mutant). `holds` is never reached."""
    _session(monkeypatch, "sess-a", live_pid)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    asked = []
    monkeypatch.setattr(crew_inflight, "holds", lambda *a, **k: asked.append(a) or {})

    code, out = _begin(capsys, repo["main"], "workflow:lane-1")

    _assert_refused(code, out, repo, None, 3, "unknown")
    assert "cannot tell who is asking" in out
    assert not asked


# --- begin: must allow -----------------------------------------------------------

def test_begin_writes_marker_fields(capsys, monkeypatch, repo, clock, live_pid, _no_loop):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot", "--worktree", repo["wt2"])

    assert code == 0, out
    marker = _marker(repo)
    assert marker["schema"] == 1 and marker["ticket"] == TICKET and marker["state"] == "working"
    assert marker["runner"] == "autopilot:sess-a"
    assert marker["worktree"] == repo["wt2"] and marker["branch"] == f"{TICKET}-build"
    assert marker["head_at_begin"] == git(repo["wt2"], "rev-parse", "HEAD")
    assert marker["began_at"] == marker["heartbeat_at"] == crew_holder.stamp(T0)
    for field in ("session", "bridge_session", "pid", "pid_start", "pidns", "machine", "worktree"):
        assert field in marker["holder"]
    assert marker["holder"]["session"] == "sess-a" and marker["holder"]["pid"] == live_pid
    assert [e["event"] for e in _log(repo)] == ["begin"]
    assert len(_no_loop) == 1


def test_begin_upper_cases_the_ticket(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)

    code, _out = _run(capsys, repo["main"], "begin", "--ticket", "t-0005", "--runner", "autopilot")

    assert code == 0
    assert os.path.exists(crew_inflight.marker_path(repo["main"], TICKET))


def test_begin_again_by_same_runner_refreshes(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    clock["t"] = T0 + datetime.timedelta(minutes=10)

    code, out = _begin(capsys, repo["main"], "workflow:lane-1")

    assert code == 0, out
    assert "result=mine" in out.splitlines()[-1]
    marker = _marker(repo)
    assert marker["began_at"] == crew_holder.stamp(T0)
    assert marker["heartbeat_at"] == crew_holder.stamp(clock["t"])


def test_begin_after_end_from_this_checkout(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    _run(capsys, repo["main"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b", "--outcome", "done")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out
    assert _marker(repo)["runner"] == "autopilot:sess-a"


def test_begin_after_clear(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    _owner_terminal(monkeypatch)
    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Owner")
    assert code == 0, out
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out


def test_begin_is_atomic_under_a_raising_serialiser(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    before = _marker_bytes(repo)
    clock["t"] = T0 + datetime.timedelta(minutes=1)

    def boom(_record):
        raise ValueError("serialiser failed")
    monkeypatch.setattr(crew_inflight, "_serialise", boom)

    code, _out = _begin(capsys, repo["main"], "workflow:lane-1")

    assert code != 0
    assert _marker_bytes(repo) == before
    assert not [n for n in os.listdir(crew_inflight.inflight_dir(repo["main"])) if n.endswith(".tmp")]


def test_two_begins_race_one_wins(repo, live_pid):
    env = dict(os.environ, CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="sess-race", CLAUDE_PID=str(live_pid))
    procs = [subprocess.Popen([sys.executable, SCRIPT, "begin", "--root", repo["main"], "--ticket", TICKET,  # pylint: disable=consider-using-with
                               "--runner", f"workflow:lane-{n}", "--no-heartbeat"],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
             for n in (1, 2)]
    codes = [p.wait(timeout=60) for p in procs]
    for proc in procs:
        proc.stdout.close()

    assert sorted(codes) == [0, 1]


# --- beat, end, clear --------------------------------------------------------------

def test_beat_refreshes_only_the_holders_marker(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    clock["t"] = T0 + datetime.timedelta(minutes=3)

    code, out = _run(capsys, repo["main"], "beat", "--ticket", TICKET, "--runner", "workflow:lane-1",
                     "--phase", "implement")

    assert code == 0, out
    marker = _marker(repo)
    assert marker["heartbeat_at"] == marker["runner_beat_at"] == crew_holder.stamp(clock["t"])
    assert marker["phase"] == "implement"


def test_beat_by_non_holder_refused(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _run(capsys, repo["main"], "beat", "--ticket", TICKET, "--runner", "workflow:lane-b")

    _assert_refused(code, out, repo, before, 1, "refused")


def test_end_by_non_holder_refused(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _run(capsys, repo["main"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b")

    _assert_refused(code, out, repo, before, 1, "refused")


def test_end_writes_ended_record_with_head_and_branch(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1", "--worktree", repo["wt2"])
    clock["t"] = T0 + datetime.timedelta(minutes=7)

    code, out = _run(capsys, repo["main"], "end", "--ticket", TICKET, "--runner", "workflow:lane-1",
                     "--outcome", "review CLEAN")

    assert code == 0, out
    marker = _marker(repo)
    assert marker["state"] == "ended" and marker["outcome"] == "review CLEAN"
    assert marker["branch"] == f"{TICKET}-build" and marker["worktree"] == repo["wt2"]
    assert marker["head"] == git(repo["wt2"], "rev-parse", "HEAD")
    assert marker["ended_at"] == crew_holder.stamp(clock["t"])
    assert [e["event"] for e in _log(repo)] == ["begin", "end"]


def test_clear_writes_cleared_record_and_log(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    _owner_terminal(monkeypatch)

    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Matthew", "--reason", "lane died")

    assert code == 0, out
    marker = _marker(repo)
    assert (marker["state"], marker["cleared_by"], marker["reason"]) == ("cleared", "Matthew", "lane died")
    assert marker["released_round"] is None
    entry = _log(repo)[-1]
    assert (entry["event"], entry["by"], entry["runner"]) == ("clear", "Matthew", "workflow:lane-b")


def test_clear_refused_with_claudecode(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before = _marker_bytes(repo)
    _owner_terminal(monkeypatch)
    monkeypatch.setenv("CLAUDECODE", "1")

    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Matthew")

    _assert_refused(code, out, repo, before, 1, "refused")


def test_clear_refused_with_session_id(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before = _marker_bytes(repo)
    _owner_terminal(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-x")

    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Matthew")

    _assert_refused(code, out, repo, before, 1, "refused")


def test_clear_refused_without_by(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    before = _marker_bytes(repo)
    _owner_terminal(monkeypatch)

    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET)

    _assert_refused(code, out, repo, before, 1, "refused")


# --- status ------------------------------------------------------------------------

def _snapshot(root):
    found = {}
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                found[path] = handle.read()
        found[base] = sorted(dirs + files)
    return found


def test_status_is_read_only(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    reserve = review_ledger.reserve(repo["main"], TICKET, "claude")
    assert reserve[0]
    with open(os.path.join(repo["wt2"], "wip.txt"), "w", encoding="utf-8") as handle:
        handle.write("uncommitted\n")
    _session(monkeypatch, "sess-a", live_pid)
    index = os.path.join(repo["main"], ".git", "index")
    before_mtime = os.stat(index).st_mtime_ns
    before = _snapshot(repo["main"]), _snapshot(repo["wt2"])

    code, out = _run(capsys, repo["main"], "status", "--ticket", TICKET)

    assert code in (1, 3), out
    assert (_snapshot(repo["main"]), _snapshot(repo["wt2"])) == before
    assert os.stat(index).st_mtime_ns == before_mtime


def test_status_exit_codes(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    assert _run(capsys, repo["main"], "status", "--ticket", TICKET)[0] == 0
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    _session(monkeypatch, "sess-a", live_pid)
    live = _run(capsys, repo["main"], "status", "--ticket", TICKET)
    clock["t"] = T0 + datetime.timedelta(hours=2)
    stale = _run(capsys, repo["main"], "status", "--ticket", TICKET)
    with open(crew_inflight.marker_path(repo["main"], TICKET), "w", encoding="utf-8") as handle:
        handle.write("{")
    unknown = _run(capsys, repo["main"], "status", "--ticket", TICKET)

    assert (live[0], stale[0], unknown[0]) == (1, 1, 3)
    assert "workflow:lane-b" in live[1] and "heartbeat" in live[1]
    assert "clear --root" in stale[1]


def test_status_all_lists_every_marker(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _run(capsys, repo["main"], "status", "--all")

    assert code == 1
    assert TICKET in out and "live" in out


# --- the beat loop -----------------------------------------------------------------

class _Stop(Exception):
    pass


def _probe_seq(monkeypatch, answers):
    answers = list(answers)

    def probe(_pid):
        return answers.pop(0) if len(answers) > 1 else answers[0]
    monkeypatch.setattr(crew_holder, "probe_pid", probe)


def _loop(repo, pid, runner="workflow:lane-1", sleeps=3):
    calls = []

    def sleep(_seconds):
        calls.append(_seconds)
        if len(calls) >= sleeps:
            raise _Stop()
    try:
        code = crew_inflight.beat_loop(repo["main"], TICKET, runner, pid, 5, sleep=sleep)
    except _Stop:
        code = None
    return code, calls


def test_loop_refreshes_heartbeat_while_pid_alive(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    clock["t"] = T0 + datetime.timedelta(minutes=9)

    code, calls = _loop(repo, live_pid)

    assert code is None and len(calls) == 3
    assert _marker(repo)["heartbeat_at"] == crew_holder.stamp(clock["t"])


def test_loop_exits_when_pid_gone(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    before = _marker_bytes(repo)
    clock["t"] = T0 + datetime.timedelta(minutes=9)
    _probe_seq(monkeypatch, [crew_holder.PidProbe("gone", None, True)])

    code, calls = _loop(repo, live_pid)

    assert code == 0 and not calls
    assert _marker_bytes(repo) == before


def test_loop_exits_when_pid_reused(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    _probe_seq(monkeypatch, [crew_holder.PidProbe("alive", "100", True), crew_holder.PidProbe("alive", "100", True),
                             crew_holder.PidProbe("alive", "200", True)])

    code, calls = _loop(repo, live_pid)

    assert code == 0 and len(calls) == 1


def test_loop_exits_when_marker_names_another_runner(capsys, monkeypatch, repo, clock, live_pid):
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    _owner_terminal(monkeypatch)
    _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Owner")
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-2")
    before = _marker_bytes(repo)
    clock["t"] = T0 + datetime.timedelta(minutes=9)

    code, calls = _loop(repo, live_pid)

    assert code == 0 and not calls
    assert _marker_bytes(repo) == before


def test_second_loop_for_same_holder_exits(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    lock = crew_inflight.loop_lock_path(TICKET, "workflow:lane-1", live_pid)
    fd = crew_holder._open_private(lock, os.O_RDWR)  # pylint: disable=protected-access
    crew_holder._lock_fd(fd, wait=False)  # pylint: disable=protected-access
    try:
        code, calls = _loop(repo, live_pid)
    finally:
        os.close(fd)

    assert code == 0 and not calls
    assert "already runs" in capsys.readouterr().out


def test_loop_log_never_prints_messaging_token(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "workflow:lane-1")
    env = dict(os.environ, CLAUDE_CODE_MESSAGING_TOKEN=SENTINEL)

    done = subprocess.run([sys.executable, SCRIPT, "beat-loop", "--root", repo["main"], "--ticket", TICKET,
                           "--runner", "workflow:lane-1", "--pid", str(_dead_pid()), "--interval", "1"],
                          env=env, capture_output=True, text=True, timeout=60, check=False,
                          stdin=subprocess.DEVNULL)

    assert done.returncode == 0, done.stdout + done.stderr
    assert SENTINEL not in done.stdout + done.stderr


def test_begin_starts_the_loop_detached_without_the_token(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    monkeypatch.setattr(crew_inflight, "_start_loop", REAL_START_LOOP)
    _session(monkeypatch, "sess-a", live_pid)
    spawned = []

    real_popen = subprocess.Popen

    def popen(argv, **kwargs):
        if "beat-loop" not in argv:
            return real_popen(argv, **kwargs)
        spawned.append((argv, kwargs))
        return None
    monkeypatch.setattr(crew_inflight.subprocess, "Popen", popen)

    code, out = _begin(capsys, repo["main"], "workflow:lane-1")

    assert code == 0, out
    argv, kwargs = spawned[0]
    assert argv[2] == "beat-loop" and "--pid" in argv and str(live_pid) in argv
    assert SENTINEL not in kwargs["env"].values()
    assert "CLAUDE_CODE_MESSAGING_TOKEN" not in kwargs["env"]
    assert kwargs.get("start_new_session") or kwargs.get("creationflags")


# --- secondary signals: the review ledger ----------------------------------------

def test_reserved_round_without_marker_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    assert review_ledger.reserve(repo["main"], TICKET, "claude")[0]
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 3, "unknown")
    assert "round 1 reserved with no result" in out
    assert "--round 1" in out


def test_reserved_round_under_ended_marker_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    assert review_ledger.reserve(repo["main"], TICKET, "claude")[0]
    _run(capsys, repo["main"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b")
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 3, "unknown")


def test_clear_round_releases_that_round(capsys, monkeypatch, repo, clock, live_pid):
    clock["t"] = crew_holder.utcnow() + datetime.timedelta(minutes=1)
    assert review_ledger.reserve(repo["main"], TICKET, "claude")[0]
    _owner_terminal(monkeypatch)
    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Owner", "--round", "1")
    assert code == 0, out
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")
    status = _run(capsys, repo["main"], "status", "--ticket", TICKET, "--runner", "autopilot")

    assert code == 0, out
    assert status[0] == 0, status[1]


def test_reserved_round_released_by_older_clear_is_still_unknown(capsys, monkeypatch, repo, clock, live_pid):
    clock["t"] = crew_holder.parse_stamp("2020-01-01T00:00:00+00:00")
    _owner_terminal(monkeypatch)
    code, out = _run(capsys, repo["main"], "clear", "--ticket", TICKET, "--by", "Owner", "--round", "1")
    assert code == 0, out
    assert review_ledger.reserve(repo["main"], TICKET, "claude")[0]
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 3, out
    assert "result=unknown" in out.splitlines()[-1]


def test_completed_round_is_no_signal(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    assert review_ledger.reserve(repo["main"], TICKET, "claude")[0]
    review_ledger.record(repo["main"], TICKET, 1, {"provider": "claude", "verdict": "FINDINGS",
                                                   "bundle_sha256": "x", "base": "y"})
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out


def test_unreadable_ledger_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    path = review_ledger.ledger_path(repo["main"], TICKET)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{broken")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 3, "unknown")
    assert "ledger" in out


# --- secondary signals: worktrees -------------------------------------------------

def _dirty(path, name="wip.txt", tracked=False):
    with open(os.path.join(path, name if not tracked else "seed.txt"), "a", encoding="utf-8") as handle:
        handle.write("uncommitted\n")


def test_dirty_worktree_live_pid_is_live(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    if not sys.platform.startswith("linux"):
        pytest.skip("process working directories are read on Linux only; NOT tested here")
    _dirty(repo["wt2"], tracked=True)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],  # pylint: disable=consider-using-with
                             cwd=repo["wt2"], stdin=subprocess.DEVNULL)
    _session(monkeypatch, "sess-a", live_pid)
    try:
        code, out = _begin(capsys, repo["main"], "autopilot")
    finally:
        child.kill()
        child.wait()

    _assert_refused(code, out, repo, None, 1, "live")
    assert repo["wt2"] in out


def test_dirty_worktree_no_process_is_stale(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _dirty(repo["wt2"], tracked=True)
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("none", []))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 1, "stale")
    assert "no live process seen" in out


def test_dirty_worktree_cannot_tell_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _dirty(repo["wt2"], tracked=True)
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("unknown", "not Linux"))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 3, "unknown")


def test_untracked_file_counts_as_dirty(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _dirty(repo["wt2"])
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("none", []))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 1, "stale")


def test_worktree_found_by_active_ticket_entry(capsys, monkeypatch, repo, tmp_path, clock, live_pid):  # pylint: disable=unused-argument
    other = tmp_path / "wt3"
    git(repo["main"], "worktree", "add", "-q", "-b", "unrelated", str(other))
    os.makedirs(os.path.join(other, ".work", "tickets", TICKET))
    crew_ticket.activate(str(other), TICKET)
    _dirty(str(other), tracked=True)
    seen = []
    monkeypatch.setattr(crew_holder, "processes_in", lambda path: (seen.append(path), ("none", []))[1])
    _session(monkeypatch, "sess-a", live_pid)
    git(repo["wt2"], "checkout", "-q", "--detach")

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 1, "stale")
    assert os.path.realpath(other) in [os.path.realpath(p) for p in seen]


def test_git_worktree_list_failure_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    real = crew_inflight._git  # pylint: disable=protected-access

    def failing(top, *args):
        return None if args[:2] == ("worktree", "list") else real(top, *args)
    monkeypatch.setattr(crew_inflight, "_git", failing)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 3, "unknown")


def test_own_dirty_worktree_is_ignored(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _dirty(repo["wt2"], tracked=True)
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("live", [1]))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["wt2"], "autopilot")

    assert code == 0, out


def test_clean_other_worktree_is_ignored(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("live", [1]))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out


def test_unrelated_branch_dirty_worktree_is_ignored(capsys, monkeypatch, repo, tmp_path, clock, live_pid):  # pylint: disable=unused-argument
    other = tmp_path / "wt4"
    git(repo["main"], "worktree", "add", "-q", "-b", "T-00050-x", str(other))
    _dirty(str(other), tracked=True)
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("live", [1]))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out


def test_ended_elsewhere_is_elsewhere(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-b", live_pid)
    _begin(capsys, repo["wt2"], "workflow:lane-b")
    _run(capsys, repo["wt2"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b", "--outcome", "implemented")
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 1, "elsewhere")
    assert f"cd {repo['wt2']}" in out


def test_begin_here_overrides_elsewhere(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-b", live_pid)
    _begin(capsys, repo["wt2"], "workflow:lane-b")
    _run(capsys, repo["wt2"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot", "--here")

    assert code == 0, out


def test_ended_here_is_free(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-b", live_pid)
    _begin(capsys, repo["wt2"], "workflow:lane-b")
    _run(capsys, repo["wt2"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _run(capsys, repo["wt2"], "status", "--ticket", TICKET)

    assert code == 0, out
    assert "result=free" in out.splitlines()[-1]


def test_holds_crash_is_unknown(monkeypatch, repo, live_pid):
    _session(monkeypatch, "sess-a", live_pid)

    def boom(*_a, **_k):
        raise RuntimeError("probe exploded")
    monkeypatch.setattr(crew_inflight, "_ledger_signal", boom)

    held = crew_inflight.holds(repo["main"], TICKET, crew_holder.current_holder(repo["main"]),
                               "autopilot:sess-a")

    assert held["state"] == "unknown" and "RuntimeError" in held["reason"]


# --- pick and lane-lines -----------------------------------------------------------

def _hold(capsys, monkeypatch, repo, ticket, runner, pid, session="sess-b"):
    _session(monkeypatch, session, pid)
    code, out = _run(capsys, repo["main"], "begin", "--ticket", ticket, "--runner", runner)
    assert code == 0, out


def _pick(capsys, repo, *tickets):
    return _run(capsys, repo["main"], "pick", "--runner", "autopilot", "--tickets", *tickets)


def test_pick_skips_live_and_takes_next(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _hold(capsys, monkeypatch, repo, "T-0001", "workflow:a", live_pid)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _pick(capsys, repo, "T-0001", "T-0002", "T-0003")

    assert code == 0, out
    assert "ticket=T-0002" in out
    assert "skipped T-0001 live workflow:a" in out


def test_pick_takes_mine(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _hold(capsys, monkeypatch, repo, "T-0001", "autopilot", live_pid, session="sess-a")

    code, out = _pick(capsys, repo, "T-0001", "T-0002")

    assert code == 0 and "ticket=T-0001" in out


def test_pick_never_takes_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _hold(capsys, monkeypatch, repo, "T-0001", "workflow:a", live_pid)
    _hold(capsys, monkeypatch, repo, "T-0003", "workflow:c", live_pid)
    assert review_ledger.reserve(repo["main"], "T-0002", "claude")[0]
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _pick(capsys, repo, "T-0001", "T-0002", "T-0003")

    assert code == 1, out
    assert "waiting=1" in out and "ticket=" not in out
    assert "skipped T-0002 unknown" in out


def test_pick_all_in_flight_waits_naming_each(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _hold(capsys, monkeypatch, repo, "T-0001", "workflow:a", live_pid)
    _hold(capsys, monkeypatch, repo, "T-0002", "wave:w1/2", live_pid)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _pick(capsys, repo, "T-0001", "T-0002")

    assert code == 1
    assert "waiting=1" in out
    for ticket, runner in (("T-0001", "workflow:a"), ("T-0002", "wave:w1/2")):
        assert f"skipped {ticket} live {runner} since {crew_holder.stamp(T0)}" in out


def test_pick_keeps_caller_order(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _pick(capsys, repo, "T-0009", "T-0001")

    assert code == 0 and "ticket=T-0009" in out


def test_pick_skips_elsewhere_naming_the_worktree(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-b", live_pid)
    _run(capsys, repo["wt2"], "begin", "--ticket", "T-0001", "--runner", "workflow:b")
    _run(capsys, repo["wt2"], "end", "--ticket", "T-0001", "--runner", "workflow:b")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _pick(capsys, repo, "T-0001", "T-0002")

    assert code == 0 and "ticket=T-0002" in out
    assert "skipped T-0001 elsewhere" in out and repo["wt2"] in out


def test_lane_lines_absolute_paths_and_order(capsys, repo):
    code, out = _run(capsys, repo["main"], "lane-lines", "--ticket", TICKET, "--runner", "workflow:lane-3",
                     "--worktree", repo["wt2"])

    assert code == 0, out
    lines = [line for line in out.splitlines() if "crew_inflight.py" in line]
    assert [line.split("crew_inflight.py ")[1].split()[0] for line in lines] == ["begin", "beat", "end"]
    for line in lines:
        assert os.path.abspath(SCRIPT) in line
        assert f"--root {repo['main']}" in line and "--runner workflow:lane-3" in line
    assert f"--worktree {repo['wt2']}" in lines[0]
    assert "every exit path" in out


def test_lane_lines_refuses_bad_runner(capsys, repo):
    code, _out = _run(capsys, repo["main"], "lane-lines", "--ticket", TICKET, "--runner", "lane 3; rm -rf /",
                      "--worktree", repo["wt2"])

    assert code == 2


def test_status_prints_marker_fields_through_safe(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _held_by_b(capsys, monkeypatch, repo, live_pid)
    path = crew_inflight.marker_path(repo["main"], TICKET)
    marker = _marker(repo)
    marker["holder"]["machine"] = "evil\x1b[2Jhost\u202e"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(marker, handle)
    _session(monkeypatch, "sess-a", live_pid)

    _code, out = _run(capsys, repo["main"], "status", "--ticket", TICKET)

    assert "\x1b" not in out and "\u202e" not in out


def test_time_constants_are_t0030s():
    assert crew_inflight.TTL_MINUTES == 30 and crew_inflight.BEAT_SECONDS == 600
    assert crew_inflight.LOOP_SECONDS == 600


# --- review round 1 (T-0049) ---------------------------------------------------------

def test_ended_on_the_same_branch_in_another_live_worktree_is_elsewhere(capsys, monkeypatch, repo, tmp_path,  # pylint: disable=unused-argument
                                                                         clock, live_pid):
    _session(monkeypatch, "sess-b", live_pid)
    _begin(capsys, repo["wt2"], "workflow:lane-b")
    _run(capsys, repo["wt2"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b")
    twin = tmp_path / "twin"
    git(repo["main"], "worktree", "add", "-q", "--force", str(twin), f"{TICKET}-build")
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, str(twin), "autopilot")

    _assert_refused(code, out, repo, before, 1, "elsewhere")
    assert f"cd {repo['wt2']}" in out


def test_ended_on_this_branch_whose_worktree_is_gone_is_free(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-b", live_pid)
    _begin(capsys, repo["wt2"], "workflow:lane-b")
    _run(capsys, repo["wt2"], "end", "--ticket", TICKET, "--runner", "workflow:lane-b")
    git(repo["main"], "worktree", "remove", "--force", repo["wt2"])
    git(repo["main"], "checkout", "-q", f"{TICKET}-build")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out


@pytest.mark.parametrize("content", ["{not json", "[\"T-0005\"]"], ids=["bad-json", "not-a-map"])
def test_unreadable_active_map_with_a_dirty_unrelated_worktree_is_unknown(capsys, monkeypatch, repo, tmp_path,  # pylint: disable=unused-argument
                                                                          clock, live_pid, content):
    other = tmp_path / "wt3"
    git(repo["main"], "worktree", "add", "-q", "-b", "unrelated", str(other))
    _dirty(str(other), tracked=True)
    path = os.path.join(crew_ticket.state_dir(repo["main"]), "active-ticket")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    monkeypatch.setattr(crew_holder, "processes_in", lambda _path: ("none", []))
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, None, 3, "unknown")
    assert "active-ticket" in out


def test_unreadable_active_map_with_only_clean_worktrees_is_free(capsys, monkeypatch, repo, tmp_path,  # pylint: disable=unused-argument
                                                                 clock, live_pid):
    git(repo["main"], "worktree", "add", "-q", "-b", "unrelated", str(tmp_path / "wt3"))
    path = os.path.join(crew_ticket.state_dir(repo["main"]), "active-ticket")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    assert code == 0, out


def test_marker_naming_another_ticket_is_unknown(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    os.makedirs(crew_inflight.inflight_dir(repo["main"]), exist_ok=True)
    record = {"schema": crew_inflight.SCHEMA, "ticket": "T-0006", "state": "cleared", "runner": "owner",
              "cleared_at": "2026-09-30T09:00:00+00:00", "cleared_by": "owner"}
    for field in crew_inflight._REQUIRED["cleared"]:  # pylint: disable=protected-access
        record.setdefault(field, "x")
    with open(crew_inflight.marker_path(repo["main"], TICKET), "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    before = _marker_bytes(repo)
    _session(monkeypatch, "sess-a", live_pid)

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 3, "unknown")
    assert "T-0006" in out


def test_marker_for_its_own_ticket_still_reads(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)
    _begin(capsys, repo["main"], "autopilot")

    record, status, why = crew_inflight.read_marker(repo["main"], TICKET.lower())

    assert (status, why) == ("ok", "") and record["ticket"] == TICKET


def test_lane_lines_quote_a_worktree_path_with_a_space(capsys, repo, tmp_path):
    spaced = tmp_path / "lane dir"
    git(repo["main"], "worktree", "add", "-q", "-b", "spaced", str(spaced))
    code, out = _run(capsys, repo["main"], "lane-lines", "--ticket", TICKET, "--runner", "workflow:lane-3",
                     "--worktree", str(spaced))

    assert code == 0, out
    begin = next(line for line in out.splitlines() if " begin " in line)
    argv = shlex.split(begin)
    assert argv[argv.index("--worktree") + 1] == str(spaced)
    assert argv[argv.index("--root") + 1] == repo["main"]


def test_another_bridge_session_is_not_mine(capsys, monkeypatch, repo, clock, live_pid):  # pylint: disable=unused-argument
    _session(monkeypatch, "sess-a", live_pid)
    monkeypatch.setenv("CLAUDE_CODE_BRIDGE_SESSION_ID", "bridge-1")
    code, out = _begin(capsys, repo["main"], "autopilot")
    assert code == 0, out
    before = _marker_bytes(repo)
    monkeypatch.setenv("CLAUDE_CODE_BRIDGE_SESSION_ID", "bridge-2")

    code, out = _begin(capsys, repo["main"], "autopilot")

    _assert_refused(code, out, repo, before, 1, "live")

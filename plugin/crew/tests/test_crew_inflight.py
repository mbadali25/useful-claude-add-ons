"""T-0049: in-flight markers -- one runner drives a ticket at a time.

    python3 -m pytest plugin/crew/tests/test_crew_inflight.py -q

`crew_inflight.holds()` answers free, mine, live, stale, elsewhere or unknown
and writes nothing; `claim`, `release`, `clear` and `beat-loop` are the only
writers, all under `<git-common-dir>/crew/inflight/`. Every repository is a
throwaway fixture under tmp_path; nothing touches the real one or ~/.claude.
The must-block rows assert the state is never free or mine; the must-allow
rows assert free and mine where they are owed.
"""
import datetime
import json
import os
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_inflight
import crew_ticket
from review_fixtures import git, init_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_inflight.py")
T = "T-1"
SESSION = "sess-1"
LINUX = os.path.isdir("/proc/self")


# --- fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """Short lock waits; the reader's holder pid is this test process."""
    monkeypatch.setattr(crew_inflight, "LOCK_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(crew_inflight, "_holder_pid", os.getpid)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return init_repo(tmp_path / "r")


def _folder(root):
    return crew_inflight.inflight_dir(str(root))


def _path(root, ticket=T):
    return os.path.join(_folder(root), f"{ticket}.json")


def _ago(seconds):
    return crew_inflight._iso(  # pylint: disable=protected-access
        crew_inflight._now() - datetime.timedelta(seconds=seconds))  # pylint: disable=protected-access


def _marker(root, **over):
    """A marker this test process holds, fresh, unless `over` says otherwise."""
    me = crew_inflight.identity(str(root), SESSION)
    marker = {"schema": 1, "ticket": T, "runner": "autopilot", "token": "tok-1",
              "session": me["session"], "pid": me["pid"], "pid_start": me["pid_start"],
              "pidns": me["pidns"], "boot_id": me["boot_id"], "host": me["host"],
              "worktree": me["worktree"], "branch": "main", "since": _ago(60),
              "heartbeat_at": _ago(5)}
    marker.update(over)
    return marker


def _put(root, marker=None, raw=None, ticket=T):
    os.makedirs(_folder(root), exist_ok=True)
    data = raw if raw is not None else json.dumps(marker).encode("utf-8")
    with open(_path(root, ticket), "wb") as handle:
        handle.write(data)


def _state(root, **kwargs):
    return crew_inflight.holds(str(root), T, **kwargs)


def _snapshot(root):
    found = {}
    common = crew_ticket.common_dir(str(root))
    for top in (str(root), common):
        for base, dirs, files in os.walk(top):
            for name in dirs + files:
                path = os.path.join(base, name)
                info = os.lstat(path)
                found[path] = (info.st_mtime_ns, info.st_size)
    return found


def _no_beat(*_args):
    return None


def _cli(root, *args, env=None):
    return subprocess.run([sys.executable, "-B", _SCRIPT, *args, "--root", str(root)],
                          capture_output=True, text=True, check=False, timeout=60,
                          stdin=subprocess.DEVNULL, env=env or os.environ.copy())


def _dead_pid():
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    return int(done.stdout)


# --- constants and the contract T-0060 reads ----------------------------------------

def test_contract_constants():
    assert (crew_inflight.TTL_SECONDS, crew_inflight.HEARTBEAT_SECONDS,
            crew_inflight.STATES, crew_inflight.RUNNERS) == (
        1800, 600, ("free", "mine", "live", "stale", "elsewhere", "unknown"),
        ("autopilot", "lane", "session"))


def test_beat_interval_is_min_600_ttl_third():
    assert crew_inflight.HEARTBEAT_SECONDS == min(600, crew_inflight.TTL_SECONDS // 3)


def test_holds_two_arg_call(repo):
    got = crew_inflight.holds(str(repo), T)
    assert set(got) == {"state", "ticket", "runner", "since", "heartbeat_at", "worktree",
                        "why", "clear"} and got["state"] == "free"


def test_holds_marker_dir_is_under_git_common_dir(repo):
    assert _folder(repo) == os.path.join(crew_ticket.common_dir(str(repo)), "crew", "inflight")


def test_holds_invalid_ticket_raises(repo):
    with pytest.raises(crew_ticket.TicketError):
        crew_inflight.holds(str(repo), "../x")


# --- must-allow ---------------------------------------------------------------------

def test_holds_absent_dir_is_free(repo):
    assert _state(repo)["state"] == "free"
    assert not os.path.exists(_folder(repo))


def test_holds_empty_dir_is_free(repo):
    os.makedirs(_folder(repo))
    got = _state(repo)
    assert (got["state"], got["clear"]) == ("free", "")


def test_holds_own_marker_is_mine(repo):
    _put(repo, _marker(repo))
    got = _state(repo, runner="autopilot")
    assert (got["state"], got["clear"], got["runner"]) == ("mine", "", "autopilot")


# --- must-block: another holder -----------------------------------------------------

def test_holds_other_holder_same_worktree_is_live(repo):
    """A live process that is not this one: pytest's parent, on every OS (pid 1
    exists only on POSIX, so on Windows it read as gone and the state stale)."""
    _put(repo, _marker(repo, session="other", pid=os.getppid(), pid_start=None))
    got = _state(repo)
    assert (got["state"], got["clear"]) == ("live", "")


def test_holds_session_alone_is_not_mine(repo):
    """T-0030 FIX: `claude --resume` keeps the session id with a new process."""
    _put(repo, _marker(repo, pid=os.getppid(), pid_start=None))
    assert _state(repo)["state"] == "live"


def test_holds_pid_start_differs_is_not_mine(repo):
    marker = _marker(repo)
    if marker["pid_start"] is None:
        pytest.skip("no /proc start time on this OS")
    _put(repo, dict(marker, pid_start=marker["pid_start"] + 1, pidns="other-ns"))
    assert _state(repo)["state"] == "live"


def test_holds_other_runner_named_is_not_mine(repo):
    _put(repo, _marker(repo, runner="lane"))
    assert _state(repo, runner="autopilot")["state"] == "live"


def test_holds_other_worktree_fresh_is_elsewhere(repo, tmp_path):
    other = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", str(other), "-b", "side")
    _put(repo, _marker(repo, worktree=os.path.realpath(str(other)), session="x"))
    got = _state(repo)
    assert (got["state"], got["worktree"]) == ("elsewhere", os.path.realpath(str(other)))
    # and the marker is shared: the other worktree reads the same marker.
    assert crew_inflight.holds(str(other), T, session="x")["state"] in ("mine", "live")


# --- must-block: stale ----------------------------------------------------------------

def test_holds_old_heartbeat_is_stale(repo):
    _put(repo, _marker(repo, heartbeat_at=_ago(crew_inflight.TTL_SECONDS + 5)))
    got = _state(repo)
    assert (got["state"], got["clear"]) == ("stale", crew_inflight.clear_command(T))
    assert "--by <you> --reason" in got["clear"]


def test_holds_heartbeat_just_inside_ttl_is_not_stale(repo):
    _put(repo, _marker(repo, heartbeat_at=_ago(crew_inflight.TTL_SECONDS - 30)))
    assert _state(repo)["state"] == "mine"


@pytest.mark.skipif(not LINUX, reason="the pid probe reads /proc")
def test_holds_dead_pid_same_ns_is_stale(repo):
    _put(repo, _marker(repo, pid=_dead_pid(), pid_start=None))
    got = _state(repo)
    assert (got["state"], "gone" in got["why"]) == ("stale", True)


@pytest.mark.skipif(not LINUX, reason="the pid probe reads /proc")
def test_holds_zombie_is_stale(repo):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])  # pylint: disable=consider-using-with
    try:
        child.kill()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = open(f"/proc/{child.pid}/stat", encoding="utf-8").read().rsplit(")", 1)[1].split()[0]  # pylint: disable=consider-using-with
            if state == "Z":
                break
            time.sleep(0.02)
        _put(repo, _marker(repo, pid=child.pid, pid_start=None))
        assert _state(repo)["state"] == "stale"
    finally:
        child.wait()


@pytest.mark.skipif(not LINUX, reason="the pid probe reads /proc")
def test_holds_pid_reused_is_stale(repo):
    marker = _marker(repo, session="other")
    _put(repo, dict(marker, pid_start=marker["pid_start"] + 7))
    assert _state(repo)["state"] == "stale"


@pytest.mark.skipif(not LINUX, reason="the pid probe reads /proc")
def test_holds_other_pidns_is_unmeasured_not_gone(repo):
    """T-0030 BLOCK: a pid from another namespace is never probed as gone."""
    _put(repo, _marker(repo, pid=_dead_pid(), pid_start=None, pidns="pid:[1]", session="o"))
    assert _state(repo)["state"] == "live"


@pytest.mark.parametrize("field", ["host", "boot_id"])
def test_holds_other_machine_is_unmeasured_not_gone(repo, field):
    _put(repo, _marker(repo, pid=_dead_pid(), pid_start=None, session="o", **{field: "x"}))
    assert _state(repo)["state"] == "live"


def test_probe_error_is_unmeasured(monkeypatch, repo):
    """Every platform's probe raises: /proc, `ps` and the Windows API (patching
    `_proc_stat` alone left Windows probing pid 12345 for real, which read gone)."""
    def boom(_pid):
        raise PermissionError("denied")
    for probe in ("_proc_stat", "_posix_process", "_win_process"):
        monkeypatch.setattr(crew_inflight, probe, boom)
    me = crew_inflight.identity(str(repo), SESSION)
    assert crew_inflight.probe(dict(me, pid=12345), me) == "unmeasured"


# --- must-block: unknown ---------------------------------------------------------------

def _unknown(root):
    got = _state(root)
    assert got["state"] == "unknown", got
    assert got["why"] and got["clear"] == crew_inflight.clear_command(T)
    return got


@pytest.mark.parametrize("raw,why", [
    (b"", "JSON"), (b"\xff\xfe{}", "UTF-8"), (b"{not json", "JSON"), (b"[1]", "object"),
    (b'{"schema": 1, "schema": 1}', "duplicate"), (b'{"pid": NaN}', "JSON"),
], ids=["empty", "not-utf8", "bad-json", "array", "duplicate-keys", "nan"])
def test_holds_unreadable_marker_is_unknown(repo, raw, why):
    _put(repo, raw=raw)
    assert why in _unknown(repo)["why"]


def test_holds_duplicate_keys_is_unknown(repo):
    text = json.dumps(_marker(repo))[:-1] + ', "runner": "lane"}'
    _put(repo, raw=text.encode())
    assert "duplicate" in _unknown(repo)["why"]


@pytest.mark.parametrize("over", [
    {"schema": 2}, {"schema": "1"}, {"runner": "robot"}, {"ticket": "T-2"}, {"pid": "12"},
    {"pid": True}, {"pid_start": 1.5}, {"token": ""}, {"worktree": ""}, {"session": None},
    {"since": "yesterday"}, {"heartbeat_at": "2026-10-04T10:00:00"}, {"heartbeat_at": 5},
], ids=lambda o: "-".join(f"{k}={v!r}" for k, v in o.items()))
def test_holds_wrong_shape_is_unknown(repo, over):
    _put(repo, _marker(repo, **over))
    _unknown(repo)


def test_holds_missing_field_is_unknown(repo):
    marker = _marker(repo)
    del marker["boot_id"]
    _put(repo, marker)
    assert "boot_id" in _unknown(repo)["why"]


def test_holds_future_heartbeat_is_unknown(repo):
    _put(repo, _marker(repo, heartbeat_at=_ago(-(crew_inflight.FUTURE_SKEW_SECONDS + 60))))
    assert "future" in _unknown(repo)["why"]


def test_holds_small_future_skew_is_fresh(repo):
    _put(repo, _marker(repo, heartbeat_at=_ago(-30)))
    assert _state(repo)["state"] == "mine"


def test_holds_marker_is_a_directory_is_unknown(repo):
    os.makedirs(_path(repo))
    assert "regular file" in _unknown(repo)["why"]


@pytest.mark.skipif(os.name == "nt", reason="symlinks and FIFOs need POSIX here")
def test_holds_marker_symlink_is_unknown(repo, tmp_path):
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps(_marker(repo)), encoding="utf-8")
    os.makedirs(_folder(repo))
    os.symlink(str(target), _path(repo))
    assert "regular file" in _unknown(repo)["why"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs here")
def test_holds_marker_fifo_is_unknown(repo):
    os.makedirs(_folder(repo))
    os.mkfifo(_path(repo))
    assert "regular file" in _unknown(repo)["why"]


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="root reads a mode-000 file")
def test_holds_marker_unreadable_permissions_is_unknown(repo):
    _put(repo, _marker(repo))
    os.chmod(_path(repo), 0)
    try:
        _unknown(repo)
    finally:
        os.chmod(_path(repo), 0o644)


def test_holds_inflight_path_is_a_file_is_unknown(repo):
    os.makedirs(os.path.dirname(_folder(repo)), exist_ok=True)
    with open(_folder(repo), "w", encoding="utf-8") as handle:
        handle.write("x")
    assert "not a directory" in _unknown(repo)["why"]


def test_holds_lock_held_past_wait_is_unknown(repo):
    _put(repo, _marker(repo))
    with open(_path(repo) + ".lock", "w", encoding="utf-8") as handle:
        handle.write("99999 dead")
    assert "lock" in _unknown(repo)["why"]


def test_holds_outside_git_is_unknown(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert "git" in _unknown(plain)["why"]


def test_holds_exception_is_unknown(monkeypatch, repo):
    def boom(*_args):
        raise RuntimeError("probe exploded")
    monkeypatch.setattr(crew_inflight, "_assess", boom)
    assert "probe exploded" in _unknown(repo)["why"]


@pytest.mark.parametrize("evil", ["auto pilot", "x\nstate=free", "a\x1b[2Jb", "t\tab"])
def test_holds_u2028_in_runner_is_single_line(repo, evil):
    _put(repo, _marker(repo, worktree="/w/" + evil, since=_ago(9), session="o"))
    got = _state(repo)
    for key in ("worktree", "why"):
        assert got[key].isprintable(), (key, got[key])
    line = crew_inflight._line(got)  # pylint: disable=protected-access
    assert len(line.splitlines()) == 1 and line.isprintable()


# --- holds writes nothing ------------------------------------------------------------

@pytest.mark.parametrize("arrange", [
    lambda r: None,
    lambda r: _put(r, _marker(r)),
    lambda r: _put(r, _marker(r, heartbeat_at=_ago(99999))),
    lambda r: _put(r, raw=b"{bad"),
    lambda r: _put(r, _marker(r, session="o")),
], ids=["free", "mine", "stale", "unknown", "live"])
def test_holds_writes_nothing(repo, arrange):
    arrange(repo)
    before = _snapshot(repo)
    crew_inflight.holds(str(repo), T)
    crew_inflight.survey(str(repo))
    assert _snapshot(repo) == before
    assert not any("__pycache__" in path for path in before)


def test_holds_cli_writes_no_bytecode(repo):
    before = _snapshot(repo)
    done = _cli(repo, "holds", "--ticket", T)
    assert done.returncode == 0 and _snapshot(repo) == before


# --- claim, release, clear --------------------------------------------------------------

def test_claim_publishes_with_link_and_refuses_a_second(repo, monkeypatch):
    code, text = crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    assert (code, text.split()[0]) == (0, "claimed")
    with open(_path(repo), encoding="utf-8") as handle:
        marker = json.load(handle)
    assert set(marker) == set(crew_inflight.FIELDS) and marker["runner"] == "autopilot"
    assert sorted(os.listdir(_folder(repo))) == ["T-1.json", "events.jsonl"]
    monkeypatch.setattr(crew_inflight, "_holder_pid", os.getppid)
    code, text = crew_inflight.claim(str(repo), T, "lane", session="other", spawn=_no_beat)
    assert (code, text.startswith("refused: live autopilot since")) == (3, True)


def test_claim_writes_nothing_outside_inflight(repo):
    before = _snapshot(repo)
    crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    after = _snapshot(repo)
    changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
    folder = _folder(repo)
    # The directories that gained an entry (.git, .git/crew) change mtime; no file does.
    parents = {os.path.dirname(folder), os.path.dirname(os.path.dirname(folder))}
    assert changed and all(p == folder or p.startswith(folder + os.sep) or p in parents
                           for p in changed), changed


def test_claim_shared_by_two_worktrees(repo, tmp_path, monkeypatch):
    other = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", str(other), "-b", "side")
    assert crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)[0] == 0
    monkeypatch.setattr(crew_inflight, "_holder_pid", os.getppid)
    code, text = crew_inflight.claim(str(other), T, "lane", session="o", spawn=_no_beat)
    assert (code, text.startswith("refused: elsewhere")) == (3, True)
    assert crew_inflight.inflight_dir(str(other)) == _folder(repo)


def test_claim_by_holder_refreshes(repo):
    crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    with open(_path(repo), encoding="utf-8") as handle:
        first = json.load(handle)
    code, text = crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    with open(_path(repo), encoding="utf-8") as handle:
        second = json.load(handle)
    assert (code, text.split()[0], second["since"]) == (0, "refreshed", first["since"])
    assert second["token"] != first["token"]


@pytest.mark.parametrize("arrange,state", [
    (lambda r: _put(r, _marker(r, heartbeat_at=_ago(99999))), "stale"),
    (lambda r: _put(r, raw=b"{bad"), "unknown"),
], ids=["stale", "unknown"])
def test_claim_refuses_stale_and_unknown_with_clear(repo, arrange, state):
    arrange(repo)
    code, text = crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    assert (code, text.startswith(f"refused: {state}"), "crew_inflight.py\" clear" in text) == (
        3, True, True)


def test_claim_race_two_processes_one_wins(repo):
    code = (f"import sys; sys.path.insert(0, {os.path.dirname(_SCRIPT)!r}); import crew_inflight;"
            f"c, t = crew_inflight.claim({str(repo)!r}, 'T-1', 'lane', session=sys.argv[1],"
            " spawn=lambda *a: None); print(t)")
    procs = [subprocess.Popen([sys.executable, "-B", "-c", code, f"s{i}"],  # pylint: disable=consider-using-with
                              stdout=subprocess.PIPE, text=True) for i in range(6)]
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    assert sum(o.startswith("claimed") for o in outs) == 1, outs
    assert all(o.startswith(("claimed", "refused:")) for o in outs), outs


def test_release_by_holder(repo):
    crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    assert crew_inflight.release(str(repo), T) == (0, f"released {T}")
    assert _state(repo)["state"] == "free"


def test_release_by_non_holder_refuses(repo, monkeypatch):
    crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    monkeypatch.setattr(crew_inflight, "_holder_pid", os.getppid)
    code, text = crew_inflight.release(str(repo), T, session="other")
    assert (code, text.startswith("refused: live")) == (3, True)
    assert os.path.exists(_path(repo))


def test_release_nothing_held_is_a_noop(repo):
    assert crew_inflight.release(str(repo), T)[0] == 0
    assert not os.path.exists(_folder(repo))


@pytest.mark.parametrize("arrange", [
    lambda r: crew_inflight.claim(str(r), T, "autopilot", spawn=_no_beat),
    lambda r: _put(r, _marker(r, session="other")),
    lambda r: None,
], ids=["mine", "live", "free"])
def test_clear_refuses_live_and_mine(repo, arrange):
    arrange(repo)
    code, text = crew_inflight.clear(str(repo), T, "owner", "testing")
    assert (code, text.startswith("refused:")) == (3, True)


@pytest.mark.parametrize("by,reason", [("", "x"), ("me", ""), ("  ", "x")])
def test_clear_needs_by_and_reason(repo, by, reason):
    _put(repo, _marker(repo, heartbeat_at=_ago(99999)))
    assert crew_inflight.clear(str(repo), T, by, reason)[0] == 2
    assert os.path.exists(_path(repo))


def test_clear_logs_event(repo):
    _put(repo, _marker(repo, heartbeat_at=_ago(99999), runner="lane"))
    code, text = crew_inflight.clear(str(repo), T, "owner", "lane died")
    assert (code, text) == (0, f"cleared {T} (stale) by owner")
    with open(os.path.join(_folder(repo), "events.jsonl"), encoding="utf-8") as handle:
        event = json.loads(handle.read().splitlines()[-1])
    assert (event["kind"], event["by"], event["reason"], event["state"], event["runner"]) == (
        "clear", "owner", "lane died", "stale", "lane")
    assert _state(repo)["state"] == "free"


def test_clear_unknown_marker(repo):
    _put(repo, raw=b"{bad")
    assert crew_inflight.clear(str(repo), T, "owner", "corrupt")[0] == 0
    assert not os.path.exists(_path(repo))


# --- the heartbeat ---------------------------------------------------------------------

def test_beat_once_rewrites_heartbeat(repo):
    _put(repo, _marker(repo, heartbeat_at=_ago(500)))
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "beat"
    with open(_path(repo), encoding="utf-8") as handle:
        marker = json.load(handle)
    beat = crew_inflight._parse_time(marker["heartbeat_at"])  # pylint: disable=protected-access
    assert (crew_inflight._now() - beat).total_seconds() < 5  # pylint: disable=protected-access


def test_beat_loop_exits_on_token_change(repo):
    _put(repo, _marker(repo, token="new"))
    sleeps = []
    reason = crew_inflight.beat_loop(str(repo), T, "old", sleep=sleeps.append)
    assert (reason, sleeps) == ("exit: superseded by another token",
                                [crew_inflight.HEARTBEAT_SECONDS])


def test_beat_loop_keyed_by_token(repo, monkeypatch):
    """An old holder's loop exits and never blocks the new holder's."""
    crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    with open(_path(repo), encoding="utf-8") as handle:
        old = json.load(handle)["token"]
    crew_inflight.release(str(repo), T)
    monkeypatch.setattr(crew_inflight, "_holder_pid", os.getppid)
    crew_inflight.claim(str(repo), T, "lane", session="new", spawn=_no_beat)
    with open(_path(repo), encoding="utf-8") as handle:
        new = json.load(handle)["token"]
    assert crew_inflight.beat_once(str(repo), T, old).startswith("exit")
    assert crew_inflight.beat_once(str(repo), T, new) == "beat"


def test_beat_loop_exits_when_marker_gone(repo):
    assert crew_inflight.beat_loop(str(repo), T, "tok", sleep=lambda s: None).startswith("exit")


@pytest.mark.skipif(not LINUX, reason="the pid probe reads /proc")
def test_beat_loop_exits_when_holder_gone(repo):
    _put(repo, _marker(repo, pid=_dead_pid(), pid_start=None))
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "exit: holder pid gone"


def test_beat_skips_a_busy_lock(repo, monkeypatch):
    monkeypatch.setattr(crew_inflight, "LOCK_WAIT_SECONDS", 0.05)
    _put(repo, _marker(repo))
    with open(_path(repo) + ".lock", "w", encoding="utf-8") as handle:
        handle.write("busy")
    real = crew_inflight._Lock  # pylint: disable=protected-access
    monkeypatch.setattr(crew_inflight, "_Lock", lambda path, wait=None: real(path, 0.05))
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "skipped"


# --- CLI ---------------------------------------------------------------------------------

def test_cli_claim_starts_one_beat_loop_then_release(repo):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID="cli")
    done = _cli(repo, "claim", "--ticket", T, "--runner", "autopilot", env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith(f"claimed {T} as autopilot (heartbeat pid ")
    pid = int(done.stdout.rsplit("pid ", 1)[1].rstrip(")\n"))
    try:
        time.sleep(0.5)
        if LINUX:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                args = handle.read().split(b"\0")
            with open(_path(repo), encoding="utf-8") as handle:
                token = json.load(handle)["token"]
            assert b"beat-loop" in args and token.encode() in args
        done = _cli(repo, "release", "--ticket", T, env=env)
        assert (done.returncode, done.stdout.strip()) == (0, f"released {T}")
    finally:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def test_cli_holds_unknown_exits_0(repo):
    _put(repo, raw=b"{bad")
    done = _cli(repo, "holds", "--ticket", T)
    assert done.returncode == 0 and done.stdout.startswith("state=unknown runner= ")
    assert "clear=python3" in done.stdout and len(done.stdout.splitlines()) == 1


def test_cli_holds_json(repo):
    done = _cli(repo, "holds", "--ticket", T, "--json")
    assert json.loads(done.stdout)["state"] == "free"


@pytest.mark.parametrize("args", [
    ("claim", "--ticket", T, "--runner", "robot"),
    ("claim", "--ticket", "../x", "--runner", "lane"),
    ("holds", "--ticket", T, "--runner", "robot"),
    ("clear", "--ticket", T, "--by", "me\nyou", "--reason", "x"),
    ("clear", "--ticket", T, "--by", "me", "--reason", "a b"),
    ("claim", "--ticket", T),
], ids=["runner", "ticket", "holds-runner", "newline", "u2028", "missing"])
def test_cli_values_reject_control_chars(repo, args):
    assert _cli(repo, *args).returncode == 2
    assert not os.path.exists(_folder(repo))


def test_cli_clear_refused_exit_3(repo):
    done = _cli(repo, "clear", "--ticket", T, "--by", "me", "--reason", "x")
    assert (done.returncode, done.stdout.startswith("refused: free")) == (3, True)


def test_scope_guard_refuses_write_edit_under_inflight(repo):
    """Acceptance 1: the guard's existing refusal under <git-common-dir>/crew/
    covers the marker directory; nothing new is registered for it."""
    import scope_guard  # pylint: disable=import-outside-toplevel
    top = crew_ticket.toplevel(str(repo))
    state = os.path.join(crew_ticket.common_dir(str(repo)), "crew")
    assert scope_guard.protected(top, state, _path(repo), top)
    assert scope_guard.shell_refusal(f"echo x > {_path(repo)}", crew_ticket.common_dir(str(repo)),
                                     top)


# --- review round 1: no /proc, the dead holder, transient errors, log first ----------

_SHIM = '''
import builtins, os, os.path
_isdir, _exists, _open, _readlink = os.path.isdir, os.path.exists, builtins.open, os.readlink
def _p(x):
    return str(x).startswith("/proc")
os.path.isdir = lambda p: False if _p(p) else _isdir(p)
os.path.exists = lambda p: False if _p(p) else _exists(p)
def _op(f, *a, **k):
    if _p(f):
        raise FileNotFoundError(2, "no /proc here", str(f))
    return _open(f, *a, **k)
builtins.open = _op
def _rl(p, *a, **k):
    if _p(p):
        raise FileNotFoundError(2, "no /proc here", str(p))
    return _readlink(p, *a, **k)
os.readlink = _rl
'''


@pytest.fixture(name="no_proc")
def _no_proc(monkeypatch):
    """In-process: this host has no /proc (macOS, BSD), as the shim does for a CLI."""
    namespace = {}
    real = {"isdir": os.path.isdir, "exists": os.path.exists, "readlink": os.readlink}
    import builtins  # pylint: disable=import-outside-toplevel
    real_open = builtins.open

    def proc(path):
        return str(path).startswith("/proc")

    def fake_open(path, *args, **kwargs):
        if proc(path):
            raise FileNotFoundError(2, "no /proc here", str(path))
        return real_open(path, *args, **kwargs)

    def fake_readlink(path, *args, **kwargs):
        if proc(path):
            raise FileNotFoundError(2, "no /proc here", str(path))
        return real["readlink"](path, *args, **kwargs)
    monkeypatch.setattr(os.path, "isdir", lambda p: False if proc(p) else real["isdir"](p))
    monkeypatch.setattr(os.path, "exists", lambda p: False if proc(p) else real["exists"](p))
    monkeypatch.setattr(os, "readlink", fake_readlink)
    monkeypatch.setattr(builtins, "open", fake_open)
    return namespace


_NO_PS = '''
import os.path, subprocess
_run = subprocess.run
def _no_ps(args, *a, **k):
    # By basename: crew_inflight runs the ps require_tool resolved (L-1508).
    if args and os.path.basename(str(args[0])) in ("ps", "ps.exe"):
        raise FileNotFoundError(2, "no ps here (a sandbox)", "ps")
    return _run(args, *a, **k)
subprocess.run = _no_ps
'''


def _shim_env(tmp_path, no_ps=False, **extra):
    """No /proc (and, with `no_ps`, no ps either: nothing can walk to the
    Claude Code process, so the session decides)."""
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "sitecustomize.py").write_text(_SHIM + (_NO_PS if no_ps else ""), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PID"}
    env.update(PYTHONPATH=str(shim), CLAUDE_CODE_SESSION_ID="sess-cli", **extra)
    return env


def _bash_cli(root, env, *args):
    """One `Bash tool call`: a fresh shell whose child runs the CLI."""
    # `; exit $?`: bash must fork, not exec, so each call has its own parent shell.
    line = " ".join([sys.executable, "-B", _SCRIPT, *args, "--root", str(root)]) + "; exit $?"
    return subprocess.run(["bash", "-c", line], capture_output=True, text=True, check=False,
                          timeout=60, stdin=subprocess.DEVNULL, env=env)


def _kill_beat(stdout):
    if "heartbeat pid " in stdout:
        try:
            os.kill(int(stdout.rsplit("pid ", 1)[1].split(")")[0]), 9)
        except (OSError, ValueError):
            pass


@pytest.mark.skipif(os.name == "nt", reason="bash -c stands in for the Bash tool")
@pytest.mark.parametrize("claude_pid,no_ps", [(False, False), (True, False), (False, True),
                                               (True, True)],
                         ids=["ps", "ps-CLAUDE_PID", "no-ps", "no-ps-CLAUDE_PID"])
def test_no_proc_later_call_in_same_session_is_mine(repo, tmp_path, claude_pid, no_ps):
    """BLOCK (a): without /proc, claim in one Bash call and holds in the next
    are the same holder, never `live` against itself."""
    env = _shim_env(tmp_path, no_ps=no_ps,
                    **({"CLAUDE_PID": str(os.getpid())} if claude_pid else {}))
    done = _bash_cli(repo, env, "claim", "--ticket", T, "--runner", "autopilot")
    try:
        assert done.returncode == 0, done.stdout + done.stderr
        got = _bash_cli(repo, env, "holds", "--ticket", T, "--runner", "autopilot")
        assert got.stdout.startswith("state=mine "), got.stdout + got.stderr
        with open(_path(repo), encoding="utf-8") as handle:
            pid = json.load(handle)["pid"]
        # Without ps nothing can walk the chain, so the hint is never trusted.
        assert pid == (None if no_ps else os.getpid() if claude_pid else pid)
    finally:
        _kill_beat(done.stdout)


@pytest.mark.skipif(os.name == "nt", reason="bash -c stands in for the Bash tool")
@pytest.mark.parametrize("no_ps", [False, True], ids=["ps", "no-ps"])
def test_no_proc_other_session_is_live(repo, tmp_path, no_ps):
    env = _shim_env(tmp_path, no_ps=no_ps)
    done = _bash_cli(repo, env, "claim", "--ticket", T, "--runner", "autopilot")
    try:
        got = _bash_cli(repo, dict(env, CLAUDE_CODE_SESSION_ID="other"), "holds", "--ticket", T)
        assert got.stdout.startswith("state=live "), got.stdout
    finally:
        _kill_beat(done.stdout)


def test_claude_pid_not_an_ancestor_is_not_the_holder(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("CLAUDE_PID", str(_dead_pid()))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "")
    assert crew_inflight._holder_pid() != int(os.environ["CLAUDE_PID"])  # pylint: disable=protected-access


def test_holder_names_are_claude_only():
    assert crew_inflight.HOLDER_NAMES == ("claude",)


@pytest.mark.skipif(os.name == "nt", reason="POSIX kill and ps")
def test_no_proc_dead_holder_is_stale(repo, no_proc):  # pylint: disable=unused-argument
    """BLOCK (b): without /proc a dead holder is still measured gone."""
    _put(repo, _marker(repo, pid=_dead_pid(), pid_start=None))
    got = _state(repo)
    assert (got["state"], "gone" in got["why"]) == ("stale", True)


@pytest.mark.skipif(os.name == "nt", reason="POSIX kill and ps")
def test_no_proc_live_holder_is_not_gone(repo, no_proc):  # pylint: disable=unused-argument
    _put(repo, _marker(repo, session="other"))
    assert _state(repo)["state"] == "live"


@pytest.mark.skipif(os.name == "nt", reason="POSIX kill and ps")
def test_no_proc_pid_reused_is_stale(repo, no_proc):  # pylint: disable=unused-argument
    marker = _marker(repo, session="other")
    assert marker["pid_start"] is not None, "ps gives a start time without /proc"
    _put(repo, dict(marker, pid_start=marker["pid_start"] + 7))
    assert _state(repo)["state"] == "stale"


@pytest.mark.skipif(os.name == "nt", reason="POSIX kill and ps")
def test_no_proc_zombie_is_stale(repo, no_proc):  # pylint: disable=unused-argument
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])  # pylint: disable=consider-using-with
    try:
        child.kill()
        time.sleep(0.3)
        _put(repo, _marker(repo, pid=child.pid, pid_start=None, session="o"))
        assert _state(repo)["state"] == "stale"
    finally:
        child.wait()


def test_windows_probe_reads_exit_code_and_creation_time(monkeypatch):
    """The Windows branch, driven through its one OS seam."""
    monkeypatch.setattr(crew_inflight, "_platform", lambda: "nt")
    me = {"host": "h", "boot_id": "", "pidns": ""}
    answers = {11: ("running", 500), 12: ("missing", None), 13: ("running", 999)}
    monkeypatch.setattr(crew_inflight, "_win_process", answers.__getitem__)
    marker = dict(me, pid=11, pid_start=500)
    assert [crew_inflight.probe(dict(marker, pid=p), me) for p in (11, 12, 13)] == [
        "alive", "gone", "gone"]


def test_windows_probe_error_is_unmeasured(monkeypatch):
    monkeypatch.setattr(crew_inflight, "_platform", lambda: "nt")

    def boom(_pid):
        raise OSError("access denied")
    monkeypatch.setattr(crew_inflight, "_win_process", boom)
    me = {"host": "h", "boot_id": "", "pidns": ""}
    assert crew_inflight.probe(dict(me, pid=11, pid_start=None), me) == "unmeasured"


class _Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = 0

    def sleep(self, seconds):
        self.sleeps += 1
        self.now += seconds
        assert self.sleeps < 50, "the beat loop never stopped"

    def __call__(self):
        return self.now


def test_beat_loop_stops_when_holder_unconfirmed_past_ttl(repo):
    """BLOCK (b): an unmeasurable holder is beaten for at most TTL, so the
    marker goes stale on its own when nobody can confirm the holder."""
    _put(repo, _marker(repo, pidns="pid:[other]"))
    clock = _Clock()
    reason = crew_inflight.beat_loop(str(repo), T, "tok-1", sleep=clock.sleep, clock=clock)
    assert "unconfirmed" in reason
    beats = crew_inflight.TTL_SECONDS // crew_inflight.HEARTBEAT_SECONDS
    assert beats <= clock.sleeps <= beats + 1


def test_beat_loop_keeps_beating_a_confirmed_holder(repo):
    _put(repo, _marker(repo))
    clock = _Clock()
    calls = []

    def sleep(seconds):
        clock.sleep(seconds)
        calls.append(seconds)
        if len(calls) == 10:
            os.remove(_path(repo))
    reason = crew_inflight.beat_loop(str(repo), T, "tok-1", sleep=sleep, clock=clock)
    assert (reason, len(calls)) == ("exit: marker gone", 10)


def test_beat_once_transient_oserror_skips(repo, monkeypatch):
    """FIX 1: os.replace refused while a reader holds the file (Windows) is a
    skipped beat, not the end of the heartbeat."""
    _put(repo, _marker(repo))
    real = os.replace
    fails = [PermissionError(13, "in use")]

    def flaky(src, dst):
        if fails:
            raise fails.pop()
        return real(src, dst)
    monkeypatch.setattr(os, "replace", flaky)
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "skipped"
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "beat"
    assert [n for n in os.listdir(_folder(repo)) if n.endswith(".tmp")] == []


def test_beat_loop_transient_errors_are_bounded_by_ttl(repo, monkeypatch):
    _put(repo, _marker(repo))

    def refuse(_src, _dst):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(os, "replace", refuse)
    clock = _Clock()
    reason = crew_inflight.beat_loop(str(repo), T, "tok-1", sleep=clock.sleep, clock=clock)
    assert reason.startswith("exit") and clock.sleeps <= (
        crew_inflight.TTL_SECONDS // crew_inflight.HEARTBEAT_SECONDS) + 1


def test_beat_once_leftover_lock_dead_holder_exits(repo):
    """FIX 2: a leftover lock never keeps a dead holder's loop alive."""
    pid = _dead_pid() if LINUX else 999999
    _put(repo, _marker(repo, pid=pid, pid_start=None))
    with open(_path(repo) + ".lock", "w", encoding="utf-8") as handle:
        handle.write("leftover")
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "exit: holder pid gone"


def test_beat_once_leftover_lock_marker_gone_exits(repo):
    os.makedirs(_folder(repo))
    with open(_path(repo) + ".lock", "w", encoding="utf-8") as handle:
        handle.write("leftover")
    assert crew_inflight.beat_once(str(repo), T, "tok-1") == "exit: marker gone"


def test_beat_once_leftover_lock_superseded_exits(repo):
    _put(repo, _marker(repo, token="new"))
    with open(_path(repo) + ".lock", "w", encoding="utf-8") as handle:
        handle.write("leftover")
    assert crew_inflight.beat_once(str(repo), T, "old").startswith("exit: superseded")


def _events(root):
    path = os.path.join(_folder(root), "events.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_claim_log_failure_claims_nothing(repo, monkeypatch):
    """FIX 3: the event is written before the effect; no log, no claim."""
    def broken(*_args, **_kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(crew_inflight, "_log", broken)
    code, text = crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    assert (code, text.startswith("refused: unknown"), os.path.exists(_path(repo))) == (
        3, True, False)


def test_claim_publish_failure_leaves_no_event(repo, monkeypatch):
    def broken(*_args, **_kwargs):
        raise OSError(1, "link refused")
    monkeypatch.setattr(os, "link", broken)
    code, _text = crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    assert (code, os.path.exists(_path(repo)), _events(repo)) == (3, False, [])


def test_clear_log_failure_keeps_marker(repo, monkeypatch):
    _put(repo, _marker(repo, heartbeat_at=_ago(99999)))

    def broken(*_args, **_kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(crew_inflight, "_log", broken)
    code, text = crew_inflight.clear(str(repo), T, "owner", "x")
    assert (code, text.startswith("refused: unknown"), os.path.exists(_path(repo))) == (
        3, True, True)


def test_clear_remove_failure_leaves_no_event(repo, monkeypatch):
    _put(repo, _marker(repo, heartbeat_at=_ago(99999)))
    real = os.remove

    def broken(path):
        if path == _path(repo):
            raise PermissionError(13, "in use")
        return real(path)
    monkeypatch.setattr(os, "remove", broken)
    code, _text = crew_inflight.clear(str(repo), T, "owner", "x")
    assert (code, os.path.exists(_path(repo)), _events(repo)) == (3, True, [])


def test_release_log_failure_keeps_marker(repo, monkeypatch):
    crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)

    def broken(*_args, **_kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(crew_inflight, "_log", broken)
    code, _text = crew_inflight.release(str(repo), T)
    assert (code, os.path.exists(_path(repo))) == (3, True)


# --- review round 2: Windows CLAUDE_PID, overflow, the log's recovery -------------------

def _windows(monkeypatch, chain, starts, session="sess-w"):
    """A Windows host: `_win_ancestors` answers `chain` (or None: the walk
    failed) and `_win_process` the creation times in `starts`."""
    monkeypatch.undo()
    monkeypatch.setattr(crew_inflight, "_platform", lambda: "nt")
    monkeypatch.setattr(crew_inflight, "_win_ancestors", lambda: chain)
    monkeypatch.setattr(crew_inflight, "_win_process",
                        lambda pid: ("running", starts.get(pid)))
    monkeypatch.setenv("CLAUDE_PID", "4242")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session)


def test_windows_claude_pid_ancestor_is_the_holder(monkeypatch):
    _windows(monkeypatch, [(os.getppid(), "bash.exe"), (4242, "claude.exe")],
             {4242: 100, os.getpid(): 900})
    assert crew_inflight._holder_pid() == 4242  # pylint: disable=protected-access


def test_windows_claude_pid_not_an_ancestor_is_refused(monkeypatch):
    """FIX: a CLAUDE_PID from project settings naming an unrelated process."""
    _windows(monkeypatch, [(os.getppid(), "bash.exe"), (77, "explorer.exe")],
             {4242: 100, os.getpid(): 900})
    assert crew_inflight._holder_pid() is None  # pylint: disable=protected-access


def test_windows_walk_failure_never_trusts_the_hint(monkeypatch):
    _windows(monkeypatch, None, {4242: 100, os.getpid(): 900})
    assert crew_inflight._holder_pid() is None  # pylint: disable=protected-access


def test_windows_walk_failure_lane_uses_its_parent(monkeypatch):
    _windows(monkeypatch, None, {4242: 100}, session="")
    assert crew_inflight._holder_pid() == os.getppid()  # pylint: disable=protected-access


def test_windows_hint_created_after_the_claimer_is_refused(monkeypatch):
    """A reused pid: the ancestor slot names a process born after this one."""
    _windows(monkeypatch, [(os.getppid(), "bash.exe"), (4242, "cmd.exe")],
             {4242: 950, os.getpid(): 900})
    assert crew_inflight._holder_pid() is None  # pylint: disable=protected-access


def test_windows_claude_exe_ancestor_without_hint(monkeypatch):
    _windows(monkeypatch, [(os.getppid(), "bash.exe"), (555, "Claude.exe")],
             {555: 100, os.getpid(): 900})
    monkeypatch.delenv("CLAUDE_PID")
    assert crew_inflight._holder_pid() == 555  # pylint: disable=protected-access


def test_marker_pid_out_of_range_is_unknown(repo):
    _put(repo, _marker(repo, pid=2 ** 70, pid_start=None))
    assert "range" in _unknown(repo)["why"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX kill")
def test_probe_overflowing_pid_is_unmeasured(repo, no_proc):  # pylint: disable=unused-argument
    me = crew_inflight.identity(str(repo), SESSION)
    assert crew_inflight.probe(dict(me, pid=2 ** 63, pid_start=None), me) == "unmeasured"


def test_broken_event_log_refusal_names_the_recovery(repo):
    """NIT: a log that cannot be written refuses, and says how to recover."""
    os.makedirs(os.path.join(_folder(repo), "events.jsonl"))
    code, text = crew_inflight.claim(str(repo), T, "autopilot", spawn=_no_beat)
    assert (code, "events.jsonl" in text, "then retry" in text,
            os.path.exists(_path(repo))) == (3, True, True, False)

"""The orphan reaper (crew_reaper.py) and the hook self-limit (crew_selflimit.py).

The reaper tests run REAL throwaway processes: an orphan is a child whose
parent really exited. Every run is restricted with `pids=` to the fixtures this
file spawned, so a test can never judge, let alone end, a real process on the
host. Every fixture is killed in teardown.
"""
# pylint: disable=consider-using-with
import json
import os
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_reaper
import crew_selflimit

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hooks", "scripts")
NOWIN = 0x08000000 if os.name == "nt" else 0
# Thresholds that make a fresh fixture eligible; a real config cannot say 0.
EAGER = {"enabled": True, "dryRun": True, "spinCpuPct": 50.0, "spinMinAgeMin": 0.0,
         "blockedMinAgeHours": 0.0, "protectedRegex": None, "intervalMin": 10, "onSessionStart": False}
SPIN = "while True:\n    pass\n"


def alive(pid):
    try:
        return pid in crew_reaper.snapshot()
    except OSError:
        return False


class Fleet:
    """Spawns orphans and live-parent children; kills everything at the end."""

    def __init__(self):
        self.pids = []
        self.handles = []

    def _read_pid(self, proc):
        line = proc.stdout.readline().strip()
        pid = int(line)
        self.pids.append(pid)
        return pid

    def orphan(self, child_code, hold_stdin=False):
        """pid of a child whose parent has really exited. With `hold_stdin` the
        child inherits a stdin pipe whose write end THIS process keeps open."""
        parent_code = (
            "import subprocess, sys\n"
            f"c = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
            f"creationflags={NOWIN})\n"
            "print(c.pid, flush=True)\n")
        parent = subprocess.Popen([sys.executable, "-c", parent_code], stdout=subprocess.PIPE,
                                  stdin=subprocess.PIPE if hold_stdin else subprocess.DEVNULL,
                                  text=True, creationflags=NOWIN)
        pid = self._read_pid(parent)
        parent.wait(timeout=30)
        if hold_stdin:
            self.handles.append(parent)  # keeps the write end of the child's stdin open
        time.sleep(0.5)
        return pid

    def live_child(self, child_code):
        """(parent handle, child pid): the parent stays alive."""
        parent_code = (
            "import subprocess, sys, time\n"
            f"c = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
            f"creationflags={NOWIN})\n"
            "print(c.pid, flush=True)\n"
            "time.sleep(600)\n")
        parent = subprocess.Popen([sys.executable, "-c", parent_code], stdout=subprocess.PIPE,
                                  stdin=subprocess.DEVNULL, text=True, creationflags=NOWIN)
        self.handles.append(parent)
        pid = self._read_pid(parent)
        time.sleep(0.5)
        return parent, pid

    def close(self):
        for handle in self.handles:
            try:
                handle.kill()
            except OSError:
                pass
            if handle.stdin:
                try:
                    handle.stdin.close()
                except OSError:
                    pass
        for pid in self.pids:
            crew_reaper.kill_pid(pid)
        for handle in self.handles:
            try:
                handle.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


@pytest.fixture(name="fleet")
def _fleet():
    fleet = Fleet()
    try:
        yield fleet
    finally:
        fleet.close()


def judge(pid, apply=False, cfg=None):
    records = crew_reaper.run(dict(cfg or EAGER), apply=apply, sample_s=1.5, pids={pid})
    return next((r for r in records if r["pid"] == pid), None)


def wait_gone(pid, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        if not alive(pid):
            return True
        time.sleep(0.3)
    return False


# ------------------------------------------------------------------ must kill

def test_a_spinning_orphan_is_ended(fleet):
    pid = fleet.orphan(SPIN)
    rec = judge(pid, apply=True)
    assert rec["decision"] == "kill" and rec["applied"] is True, rec
    assert rec["parent"] == "dead" and rec["cpuPct"] >= 50
    assert wait_gone(pid)


def test_a_blocked_orphan_reading_stdin_is_ended(fleet):
    pid = fleet.orphan("import sys\nsys.stdin.read()\n", hold_stdin=True)
    rec = judge(pid, apply=True)
    assert rec["decision"] == "kill" and "blocked" in rec["reason"], rec
    assert wait_gone(pid)


def test_a_self_matching_pgrep_watcher_is_detected_and_ended(fleet):
    code = "# until ! pgrep -f ZQ7731; do sleep 5; done\nimport time\ntime.sleep(600)\n"
    pid = fleet.orphan(code)
    rec = judge(pid, apply=True, cfg=dict(EAGER, blockedMinAgeHours=999))
    assert rec["selfMatchingWatcher"] is True
    assert rec["decision"] == "kill" and "pgrep" in rec["reason"], rec
    assert wait_gone(pid)


def test_the_watcher_pattern_is_recognised_only_when_it_matches_itself():
    assert crew_reaper.self_matching_watcher("bash -c 'until ! pgrep -f 2530; do sleep 5; done'")
    assert crew_reaper.self_matching_watcher('while pgrep -f "build.sh" >/dev/null; do sleep 1; done')
    assert not crew_reaper.self_matching_watcher("bash -c 'until ! pgrep -f [2]530; do sleep 5; done'")
    assert not crew_reaper.self_matching_watcher("pgrep -f 2530")
    assert not crew_reaper.self_matching_watcher("sleep 5")


# ---------------------------------------------------------------- must not kill

def test_dry_run_ends_nothing(fleet):
    pid = fleet.orphan(SPIN)
    rec = judge(pid, apply=False)
    assert rec["decision"] == "would-kill" and rec["applied"] is False and rec["dryRun"] is True, rec
    time.sleep(1)
    assert alive(pid)


def test_a_live_parent_is_reported_and_never_ended(fleet):
    parent, pid = fleet.live_child(SPIN)
    rec = judge(pid, apply=True)
    assert rec["decision"] == "report" and rec["parent"] == "live", rec
    assert rec["chain"] and rec["chain"][0].endswith(":live")
    assert rec["applied"] is False
    time.sleep(1)
    assert alive(pid) and parent.poll() is None


def test_a_protected_name_is_never_ended(fleet):
    pid = fleet.orphan("# tailscale\n" + SPIN)
    rec = judge(pid, apply=True)
    assert rec["decision"] == "skip" and rec["reason"] == "protected", rec
    time.sleep(1)
    assert alive(pid)


def test_the_configured_protected_regex_replaces_the_built_in_list(fleet):
    pid = fleet.orphan("# zzkeepme\n" + SPIN)
    rec = judge(pid, apply=True, cfg=dict(EAGER, protectedRegex="zzkeepme"))
    assert rec["decision"] == "skip" and rec["reason"] == "protected", rec
    time.sleep(1)
    assert alive(pid)


def test_a_process_with_a_protected_child_is_skipped_not_tree_killed(fleet):
    child = ("import subprocess, sys, time\n"
             "g = subprocess.Popen([sys.executable, '-c', '# tai' + 'lscale\\nimport time\\ntime.sleep(600)'])\n"
             "print(g.pid, flush=True)\n" + SPIN)
    pid = fleet.orphan(child)
    # the grandchild is the protected one; find it among the orphan's children
    snap = crew_reaper.snapshot()
    kids = crew_reaper.descendants(pid, snap)
    assert kids, "the fixture grandchild did not start"
    fleet.pids.extend(kids)
    rec = judge(pid, apply=True)
    assert rec["decision"] == "skip" and "child" in rec["reason"], rec
    time.sleep(1)
    assert alive(pid) and all(alive(k) for k in kids)


def test_a_young_or_quiet_orphan_is_left(fleet):
    pid = fleet.orphan("import time\ntime.sleep(600)\n")
    rec = judge(pid, apply=True, cfg=dict(EAGER, blockedMinAgeHours=2, spinMinAgeMin=15))
    assert rec["decision"] == "leave", rec
    assert alive(pid)


def test_an_image_off_the_allow_list_is_never_a_candidate():
    me = {"pid": 1, "name": "ms-teams", "cmd": "ms-teams.exe", "ppid": 0, "age_s": 9e5, "cpu_s": 1e6, "start": 1}
    assert not crew_reaper.image_allowed(me)
    assert crew_reaper.image_allowed(dict(me, name="python3"))
    assert crew_reaper.image_allowed(dict(me, name="python3.12"))
    assert crew_reaper.image_allowed(dict(me, name="weird", cmd="x /plugins/crew/hooks/scripts/cloud_guard.py"))


def test_a_hook_script_path_is_not_judged_by_its_directory_names():
    cmd = r'C:\Python314\python3.exe C:/Users/u/.claude/plugins/cache/obsidian-vault/1.0/vault_guard.py'
    rx = crew_reaper.protected_re(crew_reaper.DEFAULTS)
    proc = {"name": "python3", "cmd": cmd}
    assert not crew_reaper.is_protected(proc, rx)
    assert crew_reaper.is_protected({"name": "python3", "cmd": "python3 /opt/ai-connect/server.py"}, rx)
    assert crew_reaper.is_protected({"name": "claude", "cmd": "claude.exe --continue"}, rx)


def test_a_pid_reused_by_a_younger_process_is_not_the_parent():
    procs = {10: {"pid": 10, "ppid": 1, "name": "bash", "cmd": "", "start": 5000, "age_s": 0, "cpu_s": 0},
             20: {"pid": 20, "ppid": 10, "name": "python3", "cmd": "", "start": 1000, "age_s": 0, "cpu_s": 0}}
    assert not crew_reaper.parent_alive(procs[20], procs)
    procs[10]["start"] = 900
    assert crew_reaper.parent_alive(procs[20], procs)


# --------------------------------------------------------- config, log, tasks

def test_config_defaults_are_off_and_dry(tmp_path):
    cfg = crew_reaper.load_config(str(tmp_path / "missing.json"))
    assert cfg["enabled"] is False and cfg["dryRun"] is True and cfg["onSessionStart"] is False


def test_config_bad_values_read_as_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"reaper": {"enabled": "yes", "spinCpuPct": -4, "spinMinAgeMin": True,
                                           "blockedMinAgeHours": "2", "protectedRegex": "(",
                                           "intervalMin": 0, "dryRun": False}}), encoding="utf-8")
    cfg = crew_reaper.load_config(str(path))
    assert cfg["enabled"] is False and cfg["dryRun"] is False
    assert cfg["spinCpuPct"] == 50 and cfg["spinMinAgeMin"] == 15 and cfg["blockedMinAgeHours"] == 2
    assert cfg["protectedRegex"] is None and cfg["intervalMin"] == 10


def test_log_is_json_lines_and_rotates(tmp_path):
    path = str(tmp_path / "reaper.log")
    crew_reaper.write_log([{"pid": 1, "decision": "leave"}], path)
    assert json.loads(open(path, encoding="utf-8").read().strip())["pid"] == 1
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("x" * (crew_reaper.LOG_MAX_BYTES + 1))
    crew_reaper.write_log([{"pid": 2}], path)
    assert os.path.exists(path + ".1") and json.loads(open(path, encoding="utf-8").read())["pid"] == 2


def test_a_scheduled_pass_does_nothing_unless_enabled(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CREW_REAPER_CONFIG", str(cfg))
    monkeypatch.setenv("CREW_REAPER_LOG", str(tmp_path / "reaper.log"))
    assert crew_reaper.main(["--scheduled"]) == 0
    assert not (tmp_path / "reaper.log").exists()


def test_the_task_command_is_built_not_run():
    cmd = crew_reaper.task_command(script="/x/crew_reaper.py", python="/py/python")
    assert cmd[:2] == ["schtasks", "/Create"] and "--scheduled" in cmd[cmd.index("/TR") + 1]
    assert "/RU" not in cmd and "SYSTEM" not in " ".join(cmd)  # per user, no admin
    assert "crontab" in crew_reaper.schedule_text(script="/x/crew_reaper.py")


def test_session_start_option_is_off_by_default_and_rate_limited(tmp_path):
    spawned = []
    marker = str(tmp_path / "reaper.last")
    assert not crew_reaper.maybe_spawn_for_session(dict(EAGER, enabled=False, onSessionStart=True),
                                                   marker, popen=lambda *a, **k: spawned.append(a))
    assert not crew_reaper.maybe_spawn_for_session(dict(EAGER, enabled=True, onSessionStart=False),
                                                   marker, popen=lambda *a, **k: spawned.append(a))
    assert not spawned
    on = dict(EAGER, enabled=True, onSessionStart=True)
    assert crew_reaper.maybe_spawn_for_session(on, marker, popen=lambda *a, **k: spawned.append(a))
    assert not crew_reaper.maybe_spawn_for_session(on, marker, popen=lambda *a, **k: spawned.append(a))
    assert len(spawned) == 1


# ------------------------------------------------------------- hook self-limit

def test_selflimit_fires_and_exits_124():
    seen = []
    crew_selflimit.disarm()
    timer = crew_selflimit.arm(0.05, "t", exit_fn=seen.append)
    timer.join(5)
    crew_selflimit.disarm()
    assert seen == [124]


def test_selflimit_env_override_and_bad_values():
    assert crew_selflimit.limit_seconds(13, {"CREW_SELF_LIMIT_S": "2.5"}) == 2.5
    for bad in ("0", "-3", "abc", ""):
        assert crew_selflimit.limit_seconds(13, {"CREW_SELF_LIMIT_S": bad}) == 13.0


@pytest.mark.parametrize("script", ["cloud_guard.py", "env_guard.py", "role_write_guard.py"])
def test_a_guard_whose_stdin_never_closes_ends_itself(script):
    env = dict(os.environ, CREW_SELF_LIMIT_S="1")
    proc = subprocess.Popen([sys.executable, os.path.join(HOOKS, script)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, creationflags=NOWIN)
    try:
        code = proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()
    assert code == 124, (script, code)


def test_a_guard_that_decides_in_time_keeps_its_own_exit_code():
    env = dict(os.environ, CREW_SELF_LIMIT_S="30")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}, "cwd": os.getcwd()})
    res = subprocess.run([sys.executable, os.path.join(HOOKS, "cloud_guard.py")], input=payload,
                         capture_output=True, text=True, env=env, timeout=60, check=False,
                         creationflags=NOWIN)
    assert res.returncode == 0, res.stderr

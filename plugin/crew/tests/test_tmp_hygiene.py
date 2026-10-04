"""Crew's hooks and suites leave nothing in the temp directory (T-0065, item 7).

Measured on the host TSS shares: 2,999 `tmp.*` entries and 7,798
`crew-completion-audit.*` markers in `/tmp`, enough to exhaust its inodes and
fail the guard and the Stop verify-gate closed. They were crew's own: auto-clear
sender scripts, `run-tests.sh` fixtures, and completion-audit markers from
tests that inherited the real `TMPDIR`.

Every test here gives the hook a fresh `TMPDIR` and asserts it is EMPTY
afterwards -- not "no file matching a pattern", which a renamed leak passes.
"""
import json
import os
import signal
import subprocess
import tempfile
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_fixtures

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "hooks", "scripts")
BASH = crew_fixtures.resolve_bash()
POSIX = pytest.mark.skipif(os.name == "nt" or BASH is None,
                           reason="POSIX unlink-while-open and process groups")


def _under(path, base):
    path, base = os.path.realpath(str(path)), os.path.realpath(str(base))
    return os.path.commonpath([path, base]) == base


# --- every test gets its own TMPDIR (conftest) ---------------------------------


def test_every_test_gets_its_own_tmpdir(tmp_path):
    for name in ("TMPDIR", "TEMP", "TMP"):
        assert _under(os.environ[name], tmp_path), (name, os.environ[name])
    assert _under(tempfile.gettempdir(), tmp_path)
    assert _under(tempfile.mkdtemp(), tmp_path)


def test_subprocess_env_inherits_the_isolated_tmpdir(tmp_path):
    env = crew_fixtures.shim_env("sh", str(tmp_path / "bin"))

    for name in ("TMPDIR", "TEMP", "TMP"):
        assert env.get(name) == os.environ[name]
        assert _under(env[name], tmp_path)


# --- auto-clear.sh's detached sender --------------------------------------------


SESSION = "11111111-aaaa-4aaa-8aaa-000000000001"
HANDOFF = ("# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
           "## Done\n- a thing\n\n## Next action\nRun the next step.\n")


def _auto_clear(tmp_path, delay):
    """Run auto-clear.sh for real against a stub tmux, with its own TMPDIR.

    The same minimal setup as test_auto_cycle.py's `_sendable` (a tmux pane
    whose pid is this test process, an ancestor of the script), plus a log of
    every tmux call. Returns (tmpdir, tmux log, completed process)."""
    t = tmp_path / "t"
    t.mkdir()
    auto = {"method": "tmux", "delaySeconds": delay}
    context_cfg = {"warnAt": 0.8, "budgetTokens": None, "reserveTokens": 0, "autoWrapUp": True,
                   "handoffPath": ".work/HANDOFF.md", "autoClear": auto}
    root = crew_fixtures.make_repo(tmp_path, config={"context": context_cfg}, git=False)
    crew_dir = tmp_path / "home" / ".claude" / "crew"
    crew_dir.mkdir(parents=True)
    (crew_dir / "config.json").write_text(
        json.dumps({"context": {"autoClear": dict(auto, enabled=True)}}), encoding="utf-8")
    marker = root / ".crew" / (crew_autocycle.MARKER_PREFIX + crew_autocycle.session_key(SESSION))
    marker.write_text(json.dumps({"session_id": SESSION, "requested_at": time.time() - 30,
                                  "trusted": True, "why": "measured"}), encoding="utf-8")
    handoff = root / ".work" / "HANDOFF.md"
    handoff.write_text(HANDOFF, encoding="utf-8")
    stamp = time.time() + 5
    os.utime(str(handoff), (stamp, stamp))
    log = tmp_path / "tmux.log"
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "tmux", f'#!/bin/sh\necho "$*" >> "{log}"\necho {os.getpid()}\n')
    home = str(tmp_path / "home")
    env = dict(os.environ, HOME=home, USERPROFILE=home, CLAUDE_PROJECT_DIR=str(root),
               CREW_VAULT_OPS=str(tmp_path / "absent-vault-ops.py"),
               CREW_OBSIDIAN_CONFIG=str(tmp_path / "absent-obsidian.json"),
               **crew_fixtures.shim_env("sh", bindir, TMUX="/tmp/fake,1,0", TMUX_PANE="%7",
                                        TMPDIR=str(t)))
    env.pop("CREW_AUTOCLEAR_INHIBIT", None)
    done = subprocess.run([BASH, os.path.join(HOOKS, "auto-clear.sh"), "--session", SESSION],
                          cwd=str(root), env=env, capture_output=True, text=True, input="",
                          timeout=60, check=False)
    return t, log, done


def _wait(predicate, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def _sent(tmp_path):
    return "sent - method tmux" in _read(tmp_path / "repo" / ".crew" / ".autoclear.log")


def _read(path):
    try:
        with open(str(path), encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _sender_pids(t):
    done = subprocess.run(["pgrep", "-f", str(t)], capture_output=True, text=True, check=False)
    return [int(pid) for pid in done.stdout.split()]


@POSIX
def test_auto_clear_sender_leaves_nothing_after_sending(tmp_path):
    t, log, done = _auto_clear(tmp_path, 1)
    assert done.returncode == 0, done.stderr
    assert _sent(tmp_path), done.stdout + done.stderr

    assert _wait(lambda: "/clear" in _read(log), 10), _read(log)
    assert _wait(lambda: not os.listdir(str(t)), 5), os.listdir(str(t))


@POSIX
def test_auto_clear_sender_leaves_nothing_when_killed(tmp_path):
    t, log, done = _auto_clear(tmp_path, 5)
    assert done.returncode == 0, done.stderr
    assert _sent(tmp_path), done.stdout + done.stderr
    assert _wait(lambda: _sender_pids(t), 5), "the detached sender never started"
    time.sleep(0.5)  # into its `sleep 5`

    for pid in _sender_pids(t):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    assert _wait(lambda: not os.listdir(str(t)), 2), os.listdir(str(t))
    assert "/clear" not in _read(log)


# --- run-tests.sh ----------------------------------------------------------------

RUN_TESTS = os.path.join(HOOKS, "_test", "run-tests.sh")


@POSIX
def test_run_tests_sh_leaves_tmpdir_empty(tmp_path):
    """The shell suite removes every fixture it makes, on every exit path.

    Measured on origin/main f7ab26b9's run-tests.sh under a fresh TMPDIR: exit
    0, `RESULT: 121 passed, 0 failed`, and six entries left behind (the jq-less
    PATH mirror, the corrupt-verify.json, fakebin and argv-large repos, and the
    diagram block's two python mkdtemp dirs). The pass count is the suite's own
    and is not pinned here; a failing case shows up as exit 1."""
    t = tmp_path / "t"
    t.mkdir()
    env = dict(os.environ, TMPDIR=str(t))
    env.pop("CLAUDE_PROJECT_DIR", None)

    done = subprocess.run([BASH, RUN_TESTS], env=env, capture_output=True, text=True,
                          timeout=1200, check=False, stdin=subprocess.DEVNULL)

    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    assert ", 0 failed" in done.stdout
    assert not os.listdir(str(t)), sorted(os.listdir(str(t)))

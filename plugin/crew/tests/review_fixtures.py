"""Throwaway git repositories and a fake reviewer CLI for the review-adapter
tests. Everything is built under pytest's tmp_path: no test here touches the
real repository, its ledger directory, or ~/.claude."""
import os
import subprocess
import sys
import textwrap

# conftest.py imports `context` (which puts hooks/scripts on sys.path) before
# any test module in this directory is collected, so this resolves whether or
# not the caller of THIS module happened to import `context` itself first.
import review_run

# FIX (Codex): the escaped grandchild used to sleep a bare 4s, one second
# under review_run.POST_KILL_TIMEOUT (5s) -- so the pipe it held open always
# closed before the bounded follow-up `communicate()` in review_run.launch
# could time out a second time, and
# test_run_timeout_survives_an_escaped_descendant_holding_the_pipe never
# exercised that second-TimeoutExpired path at all.
#
# FIX (Codex): +3 was enough to REACH the second-TimeoutExpired path but not
# enough to PROVE it is actually bounded -- a test ceiling loose enough to
# tolerate normal process overhead (20s) could not tell a 5s-bounded
# `communicate()` from an 8s-unbounded one that just waits out this same
# lifetime; both finish comfortably inside 20s. Widened so the two are
# clearly different durations: long enough that an unbounded second
# `communicate()` (the regression) takes many seconds longer than the bounded
# one, so a tight elapsed-time assertion can actually distinguish them,
# not just long enough to still be running when the bound is checked.
ESCAPE_CHILD_LIFETIME_S = review_run.POST_KILL_TIMEOUT + 15


def git(root, *args, check=True):
    return subprocess.run(
        ("git",) + args, cwd=root, check=check, capture_output=True,
        text=True, stdin=subprocess.DEVNULL,
    ).stdout.strip()


def init_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    (root / "seed.txt").write_text("seed line one\nseed line two\nseed line three\n",
                                   encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    return root


# A fake `codex` for review_run.py. Behaviour is chosen by FAKE_REVIEWER_MODE:
#   clean     acknowledge every part named in the prompt, answer CLEAN
#   findings  acknowledge every part, report one FIX
#   fail      print nothing useful and exit 1
#   hang      sleep far past any test timeout
#   crash     kill the parent (review_run.py) -- an orchestrator crash
#   turnfail  a JSON stream whose turn failed, exit 0
#   escape    fork a detached `setsid` grandchild that inherits this
#             process's stdout/stderr and outlives it, then exit immediately
#             -- the leader-already-gone shape review_run.py's `launch` BLOCK
#             fix guards against: the grandchild keeps the pipe open long
#             after the leader (this process) has exited and been reaped, so
#             a bare `os.killpg(proc.pid, ...)` at that point would target a
#             pid the OS is free to have handed to something else, and an
#             unbounded follow-up `communicate()` would block on the pipe
#             for as long as the grandchild keeps running. Sleeps a bounded
#             few seconds, not the 60s an earlier version of this fixture
#             used -- that version left the grandchild running, detached
#             from the whole test's process tree, for up to a minute past
#             every test that exercised this mode, with nothing in the test
#             file reaping or even naming its pid. Bounded here -- sized
#             against review_run.POST_KILL_TIMEOUT (ESCAPE_CHILD_LIFETIME_S,
#             above) rather than a bare guess, so it actually outlives the
#             bounded follow-up `communicate()` it exists to hold open --
#             so a test that forgets to clean up still only leaks a handful
#             of seconds, and the pid is written to
#             FAKE_REVIEWER_ESCAPE_PIDFILE (when a caller sets it) so a test
#             that wants to confirm cleanup can watch it by identity.
_FAKE = r'''
import json, os, re, signal, subprocess, sys, time
prompt = sys.argv[-1]
sys.stdin.read()
mode = os.environ.get("FAKE_REVIEWER_MODE", "clean")
if mode == "hang":
    time.sleep(120)
if mode == "crash":
    os.kill(os.getppid(), getattr(signal, "SIGKILL", signal.SIGTERM))
    time.sleep(5)
    sys.exit(0)
if mode == "fail":
    sys.stderr.write("boom\n")
    sys.exit(1)
if mode == "escape":
    lifetime = os.environ["FAKE_REVIEWER_ESCAPE_LIFETIME"]
    grandchild = subprocess.Popen(["setsid", "sh", "-c", "sleep " + lifetime])
    pidfile = os.environ.get("FAKE_REVIEWER_ESCAPE_PIDFILE")
    if pidfile:
        with open(pidfile, "w", encoding="utf-8") as fh:
            fh.write(str(grandchild.pid))
    sys.exit(0)
parts = sorted(set(re.findall(r"part-\d{3}-of-\d{3}\.patch", prompt)))
body = "\n".join("READ|" + p for p in parts)
body += "\nFIX|seed.txt:1|breaks|repro" if mode == "findings" else "\nCLEAN"
events = [{"type": "thread.started"}, {"type": "turn.started"},
          {"type": "item.completed", "item": {"type": "agent_message", "text": body}}]
events.append({"type": "turn.failed", "error": {"message": "stream died"}}
              if mode == "turnfail" else {"type": "turn.completed"})
print("\n".join(json.dumps(e) for e in events))
'''


def fake_reviewer_bin(directory, name="codex"):
    """Write an executable fake reviewer called `name` into `directory` (plus
    a .cmd shim for Windows) and return the directory, for PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(_FAKE), encoding="utf-8",
                      newline="\n")
    script.chmod(0o755)
    (directory / f"{name}.cmd").write_text(
        f'@"{sys.executable}" "%~dp0{name}" %*\r\n', encoding="utf-8", newline="")
    return directory


def env_with_path(directory, **extra):
    env = dict(os.environ)
    env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")
    # Only read by the fake reviewer's `escape` mode; harmless for every
    # other mode. Forced from the derived value, not `setdefault` -- `env`
    # already carries a copy of THIS process's environment, so `setdefault`
    # would leave an ambient `FAKE_REVIEWER_ESCAPE_LIFETIME` (set outside
    # this test run, e.g. by a CI job or a previous manual run) in place
    # instead of the value sized against `review_run.POST_KILL_TIMEOUT`
    # above -- defeating the coverage that constant exists for, and
    # potentially leaving a grandchild sleeping far longer than intended. A
    # caller that deliberately wants a different lifetime can still get it,
    # by passing it via `extra` below, which is applied after and so still
    # wins.
    env["FAKE_REVIEWER_ESCAPE_LIFETIME"] = str(ESCAPE_CHILD_LIFETIME_S)
    env.update(extra)
    return env

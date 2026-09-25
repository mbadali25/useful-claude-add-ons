"""Throwaway git repositories and a fake reviewer CLI for the review-adapter
tests. Everything is built under pytest's tmp_path: no test here touches the
real repository, its ledger directory, or ~/.claude."""
import os
import subprocess
import sys
import textwrap


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
#             for as long as the grandchild keeps running.
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
    subprocess.Popen(["setsid", "sh", "-c", "sleep 60"])
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
    env.update(extra)
    return env

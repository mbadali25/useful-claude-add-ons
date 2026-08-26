"""verify-gate.ps1's lock against its own concurrent bash twin.

hooks.json registers both verify-gate.sh and verify-gate.ps1 for every Stop
so a single-shell machine always gets exactly one gate run -- the whole
reason both are registered. Most Windows dev boxes have both, since Git for
Windows ships bash.exe alongside native PowerShell, so both fire for the
same Stop event and ran the full smoke/verify gate twice: duplicate work up
to the 600s hook timeout, and two processes racing on the same scratch
files (the tf_validate JSON race fixed separately, crew-plugin FINDINGS
F12/F15).

A static "defer to whichever shell is available" was rejected: on any
Windows box with Git Bash (nearly all of them), Resolve-CrewBash always
finds a real bash.exe, which would make this script permanently
unreachable and its incident/config lane untestable. Instead each script
takes a short-lived lock right before the expensive part; whichever process
gets there first does the real work, the other backs off. These tests
exercise the PowerShell side of that lock directly, by pre-seeding
`.crew/.verify-gate.lock` the way a concurrently-running sibling would have
left it.

Windows + pwsh only: POSIX has no sibling .ps1 to race against, so the lock
is only reachable through this script there.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 gate is the native-Windows flavour; needs Windows + pwsh",
)


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _repo(tmp_path):
    """A repo whose verify.json is deliberately unparseable, so a real
    (non-deferred) run fails loudly and distinctly (exit 2, "could not be
    parsed" on stderr) -- a signal that cannot be confused with the
    lock-backoff exit 0, unlike an empty $changed set which also exits 0."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    # Untracked file so `git ls-files --others` reports a changed file --
    # otherwise $changed is empty and the gate exits 0 before ever reaching
    # the lock, which would collide with the backoff signal.
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text("{not valid json",
                                                encoding="utf-8")
    return root


def _seed_lock(root, holder_pid, age_seconds):
    lock = root / ".crew" / ".verify-gate.lock"
    lock.mkdir(parents=True)
    epoch = int(time.time()) - age_seconds
    (lock / "pid").write_text(f"{holder_pid} {epoch}", encoding="utf-8")


def _run_verify(root):
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
        input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
    )


def test_backs_off_when_a_live_holder_has_the_lock(tmp_path):
    """A fresh lock held by a PID that is actually alive right now (this
    test process's own PID -- guaranteed alive for the duration of the
    call) must make the gate back off immediately: exit 0, no output, and
    critically it must never touch the broken verify.json."""
    root = _repo(tmp_path)
    _seed_lock(root, os.getpid(), age_seconds=1)

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert result.stdout == ""
    assert result.stderr == ""


def test_reclaims_a_lock_whose_holder_pid_is_dead(tmp_path):
    """A lock recorded by a PID that no longer exists (the realistic case:
    every Stop invocation is a fresh process, so last turn's holder is
    always dead by the next one) must be reclaimed, not waited on forever
    -- the gate must run for real and hit the broken verify.json."""
    root = _repo(tmp_path)
    dead = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-Command", "$PID"],
        capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL,
    )
    dead_pid = dead.stdout.strip()
    _seed_lock(root, dead_pid, age_seconds=1)

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "could not be parsed" in result.stderr


def test_reclaims_a_stale_lock_even_with_a_live_pid(tmp_path):
    """A lock older than the 700s staleness window is reclaimed even if its
    recorded PID happens to still be alive (a long-dead lock from a crashed
    run whose PID got recycled by an unrelated process) -- age wins over a
    PID match, so a wedged lock cannot block every future turn forever."""
    root = _repo(tmp_path)
    _seed_lock(root, os.getpid(), age_seconds=800)

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "could not be parsed" in result.stderr


def test_plain_run_with_no_lock_present_runs_the_gate(tmp_path):
    """No prior lock at all (the common case: nothing else is racing this
    turn's gate) must run exactly as before the lock was added."""
    root = _repo(tmp_path)

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "could not be parsed" in result.stderr

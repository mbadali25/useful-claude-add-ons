"""verify-gate.sh's lock against its own concurrent PowerShell twin.

The bash twin of `test_verify_gate_lock.py`. Both scripts take the same
per-turn lock, and a hook that can block ships with a regression suite
covering both flavours -- the `.sh` is the one that runs on POSIX *and* on
every Windows box with Git for Windows, so leaving it uncovered would leave
the more-travelled path untested.

Two properties are load-bearing and each has a case here.

**The lock records no PID.** The first version of this lock stored one, and
that made it a no-op in the only situation it exists for: the two flavours do
not share a PID namespace on Windows, so `kill -0` on the PowerShell holder's
live Windows pid reports dead and the bash side reclaims a lock that is very
much held. It fails the other way too -- the id spaces overlap numerically, so
a coincidental match reads as a live holder and the gate is silently skipped.
Age now comes from the lock directory's own mtime, which `mkdir` stamps as it
creates it, so there is no half-written state and nothing to misread.

**The lock sits after the emergency lane and the empty-changed-set exit.** A
turn that does no work must not claim a lock, because the holder is what
removes it.
"""
import json
import os
import pathlib
import shutil
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

# Matches LOCK_TTL in verify-gate.sh.
_TTL = 700


def _resolve_bash():
    """Prefer Git for Windows' bin/bash.exe shim over the raw usr/bin MSYS
    binary, which cannot resolve its own mount table when launched from a
    non-MSYS parent. Same resolver as `test_context_watch.py`."""
    found = shutil.which("bash")
    if not found:
        return None
    parts = pathlib.Path(found).parts
    lower = [p.lower() for p in parts]
    if "usr" in lower and "bin" in lower:
        root = pathlib.Path(*parts[:lower.index("usr")])
        shim = root / "bin" / "bash.exe"
        if shim.exists():
            return str(shim)
    return found


_BASH = _resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _repo(tmp_path):
    """A repo whose verify.json is deliberately unparseable, so a real
    (non-deferred) run fails loudly and distinctly (exit 2, "could not be
    parsed" on stderr) -- a signal that cannot be confused with the
    lock-backoff exit 0, unlike an empty $CHANGED set which also exits 0."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    # Untracked file so `git ls-files --others` reports a changed file --
    # otherwise $CHANGED is empty and the gate exits 0 before ever reaching
    # the lock, which would collide with the backoff signal.
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text("{not valid json",
                                                encoding="utf-8")
    return root


def _lock(root):
    return root / ".crew" / ".verify-gate.lock"


def _seed_lock(root, age_seconds):
    """A lock as any other process would have left it: a bare directory,
    aged by its own mtime. No PID, by design -- see the module docstring."""
    lock = _lock(root)
    lock.mkdir(parents=True)
    stamp = time.time() - age_seconds
    os.utime(lock, (stamp, stamp))
    return lock


def _run_verify(root):
    return subprocess.run(
        [_BASH, _VERIFY_SH],
        input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
    )


def test_backs_off_when_a_fresh_lock_is_held(tmp_path):
    """A lock young enough that its holder is presumed still working must
    make the gate back off: exit 0, no output, and critically it must never
    touch the broken verify.json."""
    root = _repo(tmp_path)
    _seed_lock(root, age_seconds=1)

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert result.stdout == ""
    assert result.stderr == ""


def test_backs_off_for_a_lock_it_did_not_write_and_cannot_attribute(tmp_path):
    """The regression that the PID-based first draft failed. A lock left by
    the PowerShell twin carries nothing this shell can interrogate -- and it
    must not need to. Anything short of the age window is held, full stop."""
    root = _repo(tmp_path)
    lock = _seed_lock(root, age_seconds=_TTL - 60)
    (lock / "token").write_text("ps1-4242-1700000000-99\n", encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert result.stderr == ""


def test_reclaims_a_lock_older_than_the_ttl(tmp_path):
    """A holder that was hard-killed before its trap ran leaves the lock
    behind. Past the age window it is reclaimed, so a wedged lock cannot
    silently skip the gate on every future turn."""
    root = _repo(tmp_path)
    _seed_lock(root, age_seconds=_TTL + 100)

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


def test_the_holder_removes_its_own_lock_on_exit(tmp_path):
    """Cleanup is what keeps the age window from being the primary path. A
    gate that ran and exited must leave nothing behind, including on the
    blocking exit 2 -- the next turn has to be able to run."""
    root = _repo(tmp_path)

    result = _run_verify(root)

    assert result.returncode == 2
    assert not _lock(root).exists(), "the holder leaked its lock"


def test_the_lock_never_records_a_pid(tmp_path):
    """Guards the property directly rather than only its consequences: if a
    future change reintroduces a PID file, this fails even on a machine with
    one shell, where the cross-flavour cases cannot be exercised."""
    root = _repo(tmp_path)
    # Hold the lock open by pointing the gate at a slow smoke script, so the
    # lock's contents can be read while it is actually held.
    (root / ".crew" / "verify.json").unlink()
    (root / "_verify").mkdir()
    (root / "_verify" / "smoke.sh").write_text(
        "sleep 3\necho 'SMOKE: ok'\n", encoding="utf-8")

    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [_BASH, _VERIFY_SH], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
    )
    try:
        proc.stdin.write(json.dumps({}))
        proc.stdin.close()
        # Wait for the token, not just the directory: mkdir lands first and
        # sampling between the two would read an empty lock and pass for the
        # wrong reason.
        deadline = time.time() + 10
        while not (_lock(root) / "token").exists() and time.time() < deadline:
            time.sleep(0.05)
        assert (_lock(root) / "token").exists(), "the gate never took the lock"
        names = sorted(p.name for p in _lock(root).iterdir())
    finally:
        proc.kill()
        proc.wait(timeout=10)

    assert "pid" not in names, f"the lock records a PID again: {names}"
    assert names == ["token"], names


def test_an_open_incident_stands_down_without_claiming_the_lock(tmp_path):
    """The emergency lane sits BEFORE the lock on purpose. The holder is what
    removes the lock, so a turn that stands down without doing any work must
    not claim one -- it would sit there for the whole age window."""
    root = _repo(tmp_path)
    # `crew_incident_active` reads exactly one field: an unexpired
    # `expiresAtEpoch`. Anything else here would be decoration.
    (root / ".crew" / "incident.json").write_text(
        json.dumps({"id": "INC-1", "expiresAtEpoch": int(time.time()) + 3600}),
        encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert not _lock(root).exists()

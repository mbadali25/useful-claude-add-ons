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
unreachable and its incident/config lane untestable. Each script takes a
short-lived lock right before the expensive part instead.

**That lock records no PID**, and `test_the_lock_never_records_a_pid` guards
it directly. A PID-based first draft was a no-op across the pair it exists
for: `$PID` here is a Windows pid and `$$` in bash is an MSYS pid, and
`Get-Process -Id` on a live MSYS pid reports dead just as `kill -0` on a live
Windows pid does, so each side reclaimed the other's held lock and ran
anyway. The two id spaces also overlap numerically, so a coincidental match
read as a live holder and skipped the gate silently -- worse than the
double-run, by this script's own header. Age comes from the lock directory's
own creation stamp now, and the holder removes its own lock as the engine
exits.

**Backing off is not passing, so exit 0 needs an actual holder.** `New-Item
-ItemType Directory` fails for a path that is already a FILE, for an
unwritable `.crew` and for a read-only tree exactly as it fails for "already
there", and all of them read as "someone else is working". Measured on the
bash twin, where the same collapse was the same shape: with `.crew` present as
a file the gate exited 0 in 0.65s on every turn, for ever, with nothing on
stderr. The two cases at the bottom of this file are the must-block half of
that fix; the four backoff cases above them are the must-allow half and are
unchanged.

**What is still open, deliberately:** a lock directory left by a hard-killed
holder still backs later gates off for the rest of the age window. See the
bash twin's docstring for the measurement that rules out a pid-based
narrowing.

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
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PWSH = shutil.which("pwsh")

# Matches $lockTtl in verify-gate.ps1.
_TTL = 180

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="the .ps1 gate is the native-Windows flavour; needs Windows + pwsh",
)


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


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


def _lock(root):
    return root / ".crew" / ".verify-gate.lock"


def _seed_lock(root, age_seconds):
    """A lock as any other process would have left it: a bare directory,
    aged by its own stamp. No PID, by design -- see the module docstring."""
    lock = _lock(root)
    lock.mkdir(parents=True)
    stamp = time.time() - age_seconds
    os.utime(lock, (stamp, stamp))
    return lock


def _run_verify(root):
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
        input=json.dumps({}), cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
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
    # NOT `stderr == ""`. Until crew 0.19.65 the back-off path was silent, so a
    # gate that stood aside and a gate that ran everything and found nothing
    # were byte-identical: exit 0, no output. Measured against a real
    # abandoned lock on 2026-09-18: 474ms, rc=0, empty. Every reader -- a
    # person, .crew/metrics.md, the next session -- took that for a pass.
    # verify-gate.sh:189 had already recorded the symptom as a known unfixed
    # limitation; what was missing was saying it out loud.
    #
    # So the must-allow contract is no longer "silent", it is "says it did
    # nothing". Asserting silence here is what let the ambiguity stand.
    assert "backed off" in result.stderr, result.stderr
    assert "NOTHING WAS VERIFIED" in result.stderr, result.stderr


def test_backs_off_for_a_lock_it_did_not_write_and_cannot_attribute(tmp_path):
    """The regression that the PID-based first draft failed. A lock left by
    the bash twin carries nothing this shell can interrogate -- and it must
    not need to. Anything short of the age window is held, full stop."""
    root = _repo(tmp_path)
    lock = _seed_lock(root, age_seconds=_TTL - 60)
    (lock / "token").write_text("sh-4242-1700000000-99\n", encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    # NOT `stderr == ""`. Until crew 0.19.65 the back-off path was silent, so a
    # gate that stood aside and a gate that ran everything and found nothing
    # were byte-identical: exit 0, no output. Measured against a real
    # abandoned lock on 2026-09-18: 474ms, rc=0, empty. Every reader -- a
    # person, .crew/metrics.md, the next session -- took that for a pass.
    # verify-gate.sh:189 had already recorded the symptom as a known unfixed
    # limitation; what was missing was saying it out loud.
    #
    # So the must-allow contract is no longer "silent", it is "says it did
    # nothing". Asserting silence here is what let the ambiguity stand.
    assert "backed off" in result.stderr, result.stderr
    assert "NOTHING WAS VERIFIED" in result.stderr, result.stderr


def test_reclaims_a_lock_older_than_the_ttl(tmp_path):
    """A holder that was hard-killed before its exit handler ran leaves the
    lock behind. Past the age window it is reclaimed, so a wedged lock cannot
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
        "sleep 5\necho 'SMOKE: ok'\n", encoding="utf-8")

    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
    )
    try:
        proc.stdin.write(json.dumps({}))
        proc.stdin.close()
        # Wait for the token, not just the directory: New-Item lands first
        # and sampling between the two would read an empty lock and pass for
        # the wrong reason.
        deadline = time.time() + 20
        while not (_lock(root) / "token").exists() and time.time() < deadline:
            time.sleep(0.05)
        assert (_lock(root) / "token").exists(), "the gate never took the lock"
        names = sorted(p.name for p in _lock(root).iterdir())
    finally:
        proc.kill()
        proc.wait(timeout=10)

    assert "pid" not in names, f"the lock records a PID again: {names}"
    assert names == ["token"], names


def test_a_lock_path_that_is_a_file_does_not_stand_the_gate_down(tmp_path):
    """Nothing holds a regular file, so a lock path that is one leaves no
    holder to wait for. It used to read as held, and the gate exited 0 for
    the whole age window against a verify.json a running gate exits 2 on."""
    root = _repo(tmp_path)
    _lock(root).write_text("not a directory\n", encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "could not be parsed" in result.stderr, result.stderr
    assert "WITHOUT the lock" in result.stderr, result.stderr


def test_a_crew_directory_that_is_a_file_does_not_stand_the_gate_down(tmp_path):
    """The permanent version of the same collapse: with `.crew` itself a
    file the lock can never be created, so the gate exited 0 on EVERY turn
    with nothing on stderr. The checks have to run."""
    root = _repo(tmp_path)
    # No .crew means no verify.json, so the gate takes the smoke path -- which
    # sits after the lock and is what proves the lock was not what stopped it.
    shutil.rmtree(root / ".crew")
    (root / ".crew").write_text("not a directory\n", encoding="utf-8")
    (root / "_verify").mkdir()
    (root / "_verify" / "smoke.sh").write_text(
        "echo FAIL: deliberate\nexit 1\n", encoding="utf-8", newline="\n")

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "Smoke FAILED" in result.stderr, result.stderr
    assert "WITHOUT the lock" in result.stderr, result.stderr


def test_an_open_incident_stands_down_without_claiming_the_lock(tmp_path):
    """The emergency lane sits BEFORE the lock on purpose. The holder is what
    removes the lock, so a turn that stands down without doing any work must
    not claim one -- it would sit there for the whole age window."""
    root = _repo(tmp_path)
    # `Test-CrewIncidentActive` reads exactly one field: an unexpired
    # `expiresAtEpoch`. Anything else here would be decoration.
    (root / ".crew" / "incident.json").write_text(
        json.dumps({"id": "INC-1", "expiresAtEpoch": int(time.time()) + 3600}),
        encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert not _lock(root).exists()


def _age_path(path, seconds):
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def test_a_heartbeat_keeps_a_long_run_holding_its_lock(tmp_path):
    """PowerShell twin of the .sh case. Both flavours must date the lock by
    its TOKEN, or one reclaims a lock the other is still holding.

    This mirror exists because the .sh test alone left a measured blind spot:
    a sabotage run that pointed verify-gate.ps1 at the directory mtime stayed
    GREEN while the same mutation in the .sh went red. A pair where only one
    side is tested is a pair that drifts on the untested side -- which is the
    failure root CLAUDE.md records as crew shipping a guard that stood down on
    Windows and blocked nothing there.
    """
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    token = lock / "token"
    token.write_text("ps1-1-1-1", encoding="utf-8")
    _age_path(lock, 600)
    _age_path(token, 1)

    result = _run_verify(root)
    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "backed off" in result.stderr, (
        "verify-gate.ps1 reclaimed a lock whose heartbeat is 1s old, so it is "
        "dating by the directory. A directory mtime does not move when a file "
        "inside it is rewritten, so the heartbeat refreshes nothing. "
        f"stderr: {result.stderr}"
    )


def test_a_lock_whose_heartbeat_has_stopped_is_reclaimed(tmp_path):
    """And the lock must still be able to go stale, or a killed holder wedges
    the gate permanently instead of for a bounded window."""
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    token = lock / "token"
    token.write_text("ps1-1-1-1", encoding="utf-8")
    _age_path(lock, 600)
    _age_path(token, 600)

    result = _run_verify(root)
    assert "backed off" not in result.stderr, (
        "a lock with no heartbeat for 600s is abandoned and must be reclaimed. "
        f"stderr: {result.stderr}"
    )


def _repo_that_runs_rules(tmp_path, probe_rule):
    """A repo whose verify.json PARSES, so the gate reaches the rule loop.

    The twin of the fixture in test_verify_gate_lock_sh.py, and added for the
    same reason: every other fixture here forces the early exit on broken
    JSON, so no rule ever ran and the heartbeat WRITE was never exercised.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "unverified.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps({
        "version": 1,
        # reach: local - this probe is testing the lock heartbeat, not
        # reach classification; its `stat` command names no interpreter
        # but the lock token path it reads happens to exist once the gate
        # has acquired the lock, which the round-4 scanner would otherwise
        # treat as an existing-repo-file wrapper trigger.
        "rules": [{"paths": ["unverified.py"], "reach": "local", "run": probe_rule,
                   "why": "heartbeat probe"}],
        "default": [],
        "unmapped": "ignore",
    }), encoding="utf-8")
    return root


# verify-gate.ps1 runs each rule through bash (Resolve-CrewBash), so the probe
# is the same one the .sh flavour uses.
_HEARTBEAT_PROBE = [
    "stat -c %Y .crew/.verify-gate.lock/token > t0.txt",
    "sleep 3",
    "stat -c %Y .crew/.verify-gate.lock/token > t1.txt",
]


def test_the_heartbeat_actually_rewrites_the_token_during_a_run(tmp_path):
    """Must-allow for cutting $lockTtl to 180, and the case that was missing.

    The two heartbeat cases above pre-age the token and assert on the gate
    READING it. Neither runs a rule, so Update-CrewLock could be deleted and
    both stay green. This one runs the real gate and watches the token move
    while it holds the lock. Kept in lockstep with the .sh case of the same
    name: a .ps1 that drifts from its .sh is how this repo once shipped a
    guard that blocked nothing on Windows.
    """
    root = _repo_that_runs_rules(tmp_path, _HEARTBEAT_PROBE)

    result = _run_verify(root)
    assert result.returncode == 0, (
        f"the probe rule should pass. stdout: {result.stdout} "
        f"stderr: {result.stderr}"
    )

    t0 = (root / "t0.txt").read_text(encoding="utf-8").strip()
    t1 = (root / "t1.txt").read_text(encoding="utf-8").strip()
    assert t0 and t1, f"the probe did not record the token mtime: {t0!r} {t1!r}"
    drift = int(t1) - int(t0)
    assert drift >= 2, (
        "the lock token was not refreshed while the gate was running: its "
        f"mtime moved {drift}s across a 3s rule. Update-CrewLock is not "
        "writing, so the lock ages from the moment it was ACQUIRED and any "
        f"run longer than the TTL ({_TTL}s) loses it mid-run to the .sh "
        f"flavour. stderr: {result.stderr}"
    )

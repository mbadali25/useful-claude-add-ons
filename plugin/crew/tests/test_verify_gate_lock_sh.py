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

**Backing off is not passing, so exit 0 needs an actual holder.** `mkdir`
fails for ENOTDIR, EACCES and a read-only tree exactly as it fails for "the
directory is already there", and every one of those read as "someone else is
working". Measured: with `.crew` present as a FILE the gate exited 0 in 0.65s
on every turn, for ever, with nothing on stderr -- the gate silently off,
wearing the exit code of a pass. With the lock path itself a file it did the
same for the whole age window. The two cases at the bottom of this file are
the must-block half of that fix; the four backoff cases above them are the
must-allow half and are unchanged.

**What is still open, deliberately.** A lock DIRECTORY left behind by a
hard-killed holder still backs later gates off for the rest of the age window.
The obvious narrowing -- read the pid out of the token and ask whether that
process is alive, only for a token this flavour wrote -- was tried and
measured false on 2026-09-13: a hard-killed Git Bash's `$$` still answered
`kill -0` from a second bash as ALIVE at +0.5s, +5s and +15s, while a pid that
never existed correctly reported "No such process". So there is no reliable
liveness signal here and the age window remains the only answer for a lock
that can be dated. Recorded rather than left to be rediscovered.
"""
import json
import os
import pathlib
import shutil
import subprocess
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

# Matches LOCK_TTL in verify-gate.sh.
_TTL = 180

_BASH = crew_fixtures.resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


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
    return crew_fixtures.run_gate(
        [_BASH, _VERIFY_SH],
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
    the PowerShell twin carries nothing this shell can interrogate -- and it
    must not need to. Anything short of the age window is held, full stop."""
    root = _repo(tmp_path)
    lock = _seed_lock(root, age_seconds=_TTL - 60)
    (lock / "token").write_text("ps1-4242-1700000000-99\n", encoding="utf-8")

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
    # newline="\n": write_text is text mode, so on Windows the \n would become
    # \r\n and bash would fail on `sleep 3\r` instead of sleeping -- the lock
    # would be released before it could be read, and the failure would read as
    # a lock bug rather than a fixture one.
    (root / "_verify" / "smoke.sh").write_text(
        "sleep 3\necho 'SMOKE: ok'\n", encoding="utf-8", newline="\n")

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


def test_a_lock_path_that_is_a_file_does_not_stand_the_gate_down(tmp_path):
    """`mkdir` fails on a path that is already a regular file, and that
    failure used to read as "held": the gate exited 0 in under a second, for
    the whole age window, against a verify.json a running gate exits 2 on.
    Nothing holds a regular file, so there is no holder to wait for."""
    root = _repo(tmp_path)
    _lock(root).write_text("not a directory\n", encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 2, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "could not be parsed" in result.stderr, result.stderr
    assert "WITHOUT the lock" in result.stderr, result.stderr


def test_a_crew_directory_that_is_a_file_does_not_stand_the_gate_down(tmp_path):
    """The permanent version of the same collapse: with `.crew` itself a
    file, neither `mkdir -p .crew` nor the lock can ever succeed, so the gate
    exited 0 on EVERY turn with nothing on stderr. The checks have to run."""
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
    # `crew_incident_active` reads exactly one field: an unexpired
    # `expiresAtEpoch`. Anything else here would be decoration.
    (root / ".crew" / "incident.json").write_text(
        json.dumps({"id": "INC-1", "expiresAtEpoch": int(time.time()) + 3600}),
        encoding="utf-8")

    result = _run_verify(root)

    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert not _lock(root).exists()


def _age(path, seconds):
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def test_a_heartbeat_keeps_a_long_run_holding_its_lock(tmp_path):
    """Must-allow for cutting LOCK_TTL 700 -> 180.

    The TTL is also what stops the second flavour starting while the first is
    still going. Cut it without a working heartbeat and any run over 180s has
    its lock reclaimed mid-flight: two gates, two verdicts, one turn.

    This asserts the GATE's behaviour, not the filesystem's. The first version
    of this test recomputed the age in Python and passed against a sabotaged
    script -- it tested its own reimplementation, which is the "mocking that
    would test the mock" trap this suite's docstring already warns about. It
    reported ALL RED while three mutations went green.
    """
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    token = lock / "token"
    token.write_text("sh-1-1-1", encoding="utf-8")

    # Directory old enough to look abandoned; token fresh, as a live run's
    # heartbeat leaves it. Dating by the directory reclaims and runs the
    # checks; dating by the token backs off, which is correct.
    _age(lock, 600)
    _age(token, 1)

    result = _run_verify(root)
    assert result.returncode == 0, f"stdout: {result.stdout} stderr: {result.stderr}"
    assert "backed off" in result.stderr, (
        "the gate reclaimed a lock whose heartbeat is 1s old. It is dating the "
        "lock by the DIRECTORY, and a directory mtime does not move when a "
        "file inside it is rewritten -- so the heartbeat refreshes nothing and "
        "a long run loses its lock to the other flavour mid-run. "
        f"stderr: {result.stderr}"
    )


def test_a_lock_whose_heartbeat_has_stopped_is_reclaimed(tmp_path):
    """The other half, and what stops the fix above becoming a lock that can
    never go stale: token AND directory both old means abandoned, so the gate
    must take the lock and actually run rather than backing off forever."""
    root = _repo(tmp_path)
    lock = _lock(root)
    lock.mkdir(parents=True)
    token = lock / "token"
    token.write_text("sh-1-1-1", encoding="utf-8")
    _age(lock, 600)
    _age(token, 600)

    result = _run_verify(root)
    assert "backed off" not in result.stderr, (
        "a lock with no heartbeat for 600s is abandoned and must be reclaimed; "
        "backing off here is the twelve-minute silent stand-down 0.19.65 fixed. "
        f"stderr: {result.stderr}"
    )
    assert result.returncode == 2, (
        "having reclaimed the lock the gate must actually RUN -- this fixture's "
        "verify.json is deliberately broken, so a real run exits 2. "
        f"rc={result.returncode} stderr: {result.stderr}"
    )


def test_the_tests_ttl_matches_both_scripts():
    """_TTL is a hand-copied duplicate of the scripts' own constant, in two
    test files, and it silently went stale when 0.19.65 cut 700 to 180.

    The boundary cases build their fixtures from _TTL, so a stale copy does
    not fail -- it moves the boundary being tested away from the real one and
    keeps passing. That is the shape this repo keeps finding: not a wrong
    answer, an answer about the wrong question, wearing the label of a check
    that happened. Read both scripts rather than trusting either copy.
    """
    import re
    scripts = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
    sh = (scripts / "verify-gate.sh").read_text(encoding="utf-8")
    ps = (scripts / "verify-gate.ps1").read_text(encoding="utf-8")

    sh_ttl = re.search(r"^LOCK_TTL=(\d+)", sh, re.M)
    ps_ttl = re.search(r"^\$lockTtl = (\d+)", ps, re.M)
    assert sh_ttl and ps_ttl, "could not find the TTL in one of the flavours"
    assert int(sh_ttl.group(1)) == int(ps_ttl.group(1)), (
        f"the pair disagree: .sh={sh_ttl.group(1)} .ps1={ps_ttl.group(1)}. "
        "One flavour would reclaim a lock the other still holds."
    )
    assert _TTL == int(sh_ttl.group(1)), (
        f"this file's _TTL is {_TTL} but the scripts use {sh_ttl.group(1)}, so "
        "every boundary case here is testing a threshold that does not exist"
    )


def _repo_that_runs_rules(tmp_path, probe_rule):
    """A repo whose verify.json PARSES, so the gate reaches the rule loop.

    Every other fixture here writes deliberately-broken JSON to force the
    early exit, which is why nothing in this file ever executed a rule -- and
    therefore why the heartbeat WRITE went uncovered. The rule path is the
    literal filename rather than a glob, so this case does not also depend on
    whatever the matcher does with a leading star-star.
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
        # reach: local - the twin of the same note in test_verify_gate_lock.py.
        "rules": [{"paths": ["unverified.py"], "reach": "local", "run": probe_rule,
                   "why": "heartbeat probe"}],
        "default": [],
        "unmapped": "ignore",
    }), encoding="utf-8")
    return root


# The probe: read the token mtime, spend real time, read it again. The gate
# touches the lock after EVERY command, so a working heartbeat puts the second
# reading a full sleep later than the first. A no-op heartbeat leaves both at
# the moment the lock was acquired.
_HEARTBEAT_PROBE = [
    "stat -c %Y .crew/.verify-gate.lock/token > t0.txt",
    "sleep 3",
    "stat -c %Y .crew/.verify-gate.lock/token > t1.txt",
]


def test_the_heartbeat_actually_rewrites_the_token_during_a_run(tmp_path):
    """Must-allow for LOCK_TTL 700 -> 180, and the case that was missing.

    The two heartbeat cases above pre-age the token with os.utime and then
    assert on the gate READING it -- they prove the lock is dated by the token
    rather than by the directory, which is a different property. Neither ever
    runs a rule, so lock_touch could be deleted outright and both stay green.
    Measured 2026-09-18: making lock_touch a no-op left all 23 cases in the
    two lock files passing.

    That matters because the heartbeat is the whole justification for cutting
    the TTL. Without it a run longer than the TTL has its lock reclaimed by
    the other flavour mid-flight -- two gates, two verdicts, one turn -- which
    is precisely what the lock exists to prevent.

    This asserts the gate's own behaviour: the token mtime is read by the
    rules themselves, from inside the run, while the gate holds the lock.
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
        f"mtime moved {drift}s across a 3s rule. lock_touch is not writing, "
        "so the lock ages from the moment it was ACQUIRED and any run longer "
        f"than LOCK_TTL ({_TTL}s) loses it mid-run to the other flavour. "
        f"stderr: {result.stderr}"
    )

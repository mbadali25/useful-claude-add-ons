"""The one test that actually proves the verify-gate lock works.

Every other lock case pre-seeds a lock and asserts what one script does with
it. That is necessary but it is not the claim: the claim is that when two Stop
gates run at the same time, the expensive part runs ONCE.

WHAT CHANGED, and why this file was rewritten rather than deleted. The race it
used to model was `hooks.json` firing verify-gate.sh AND verify-gate.ps1 for
the same Stop event. L-0727 slice 2 ended that: the dispatcher picks ONE
flavour per row, and on Windows it runs the `.sh` through a strictly resolved
Git Bash. So from slice 2 until L-0869 this file could not fail - the second
process it launched was a flavour nothing fires any more, and
`test_only_one_flavour_runs_the_expensive_part` had been passing vacuously for
two slices. L-0869 deleted verify-gate.ps1 and this file now launches the race
that CAN still happen: two concurrent Stop events against the same repo.

That race is real. A Stop fires per turn, sessions overlap, and two checkouts
of one repo share `.crew/`. The lock is what stops the full rule set running
twice over the same tree, and - the failure the original header called worse
than the double-run - what must NOT leave a holder behind, because a leaked
lock means the next Stop is silently ungated.

Seeded-lock tests cannot catch this. The first version of the lock stored a
PID; each side's liveness check read the other's live holder as dead,
reclaimed the lock, and ran the gate anyway, while both scripts passed their
own seeded-lock suites the whole time because each seeded a lock in the shape
its own shell writes. So this runs two real gates, at the same time, against a
smoke script that appends one line per execution, and counts the lines.
Sabotaging the lock, or reintroducing a PID-based holder check, turns it red.

It is also no longer Windows-only: one flavour means one shell, so the race is
reachable on every host, and the Linux CI runner now exercises it too.
"""
import json
import os
import subprocess
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")

_BASH = crew_fixtures.resolve_bash()

pytestmark = pytest.mark.skipif(_BASH is None, reason="needs bash")


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path):
    """No verify.json, so the gate takes the smoke path -- which sits after
    the lock. The smoke script appends one line per run and then holds for
    long enough that a loser cannot simply arrive late and find the work
    already finished and the lock already cleaned up."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / "_verify").mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / "unverified.py").write_text("x = 1\n", encoding="utf-8")
    # newline="\n" is load-bearing, not tidiness: write_text is TEXT mode, so
    # on Windows every \n would become \r\n and bash would read `sleep 3\r` as
    # a command that does not exist. The overlap this test depends on would
    # vanish and the failure would look like a lock bug.
    (root / "_verify" / "smoke.sh").write_text(
        'echo "ran" >> "$(dirname "$0")/../runs.txt"\n'
        "sleep 3\n"
        "echo 'SMOKE: ok'\n",
        encoding="utf-8", newline="\n")
    return root


def _two_concurrent_stops(root):
    """Two Stop gates launched together against one repo.

    stdin is left open for the caller to feed, because the two ways of
    collecting a result are mutually exclusive: `communicate(input=...)` owns
    stdin itself and raises ValueError on a pipe the caller already closed.
    The previous version of this file closed stdin here and then called
    `communicate()`, which cannot work -- nothing noticed, because the whole
    module was skipped off a Windows host with both shells.
    """
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    return [
        crew_fixtures.popen_gate(
            [_BASH, _VERIFY_SH], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(root), env=env)
        for _ in range(2)
    ]


def test_only_one_of_two_concurrent_stops_runs_the_expensive_part(tmp_path):
    """Two Stop gates, launched together, must produce exactly one smoke run
    between them -- and neither may leave the lock behind."""
    root = _repo(tmp_path)

    procs = _two_concurrent_stops(root)
    for proc in procs:
        proc.stdin.write(json.dumps({}))
        proc.stdin.close()
    for proc in procs:
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            crew_fixtures.kill_process_group(proc)
            raise

    runs = root / "runs.txt"
    lines = (runs.read_text(encoding="utf-8").split()
             if runs.exists() else [])
    assert len(lines) == 1, (
        f"the smoke ran {len(lines)} time(s); both Stops got past the lock. "
        f"exit codes: {[p.returncode for p in procs]}")
    assert not (root / ".crew" / ".verify-gate.lock").exists(), \
        "the winner leaked its lock"


def test_the_loser_backs_off_silently_and_does_not_fail_the_turn(tmp_path):
    """The winner's exit code governs the turn. A loser that exited non-zero,
    or wrote FAIL to stderr, would turn a passing gate into a blocked turn
    whenever two Stops happened to overlap."""
    root = _repo(tmp_path)

    procs = _two_concurrent_stops(root)
    # Both payloads go in BEFORE either result is collected. Feeding one gate
    # and waiting for it would leave the other blocked on its own stdin, and
    # the overlap this test depends on would never happen -- the two gates
    # would simply run one after the other and both would win.
    for proc in procs:
        proc.stdin.write(json.dumps({}))
        proc.stdin.close()
    results = []
    for proc in procs:
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            crew_fixtures.kill_process_group(proc)
            raise
        results.append((proc.stdout.read(), proc.stderr.read()))

    for proc, (out, err) in zip(procs, results):
        assert proc.returncode == 0, f"stdout: {out} stderr: {err}"
        assert "FAIL" not in err


def test_a_second_pair_on_the_next_turn_still_runs(tmp_path):
    """The lock is per-turn, not per-session. Once the first pair is done the
    lock is gone, so the next Stop event gets a real gate run rather than a
    silent skip -- the failure mode the header calls worse than the
    double-run."""
    root = _repo(tmp_path)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))

    for _ in range(2):
        proc = crew_fixtures.run_gate(
            [_BASH, _VERIFY_SH], input=json.dumps({}), cwd=str(root),
            env=env, capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        time.sleep(0.2)

    runs = (root / "runs.txt").read_text(encoding="utf-8").split()
    assert len(runs) == 2, f"the second turn was silently skipped: {runs}"

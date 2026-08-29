"""The one test that actually proves the verify-gate lock works.

Every other lock case pre-seeds a lock and asserts what one script does with
it. That is necessary but it is not the claim: the claim is that when
`hooks.json` fires verify-gate.sh AND verify-gate.ps1 for the same Stop
event, the expensive part runs ONCE.

Seeded-lock tests cannot catch the failure this change exists to fix. The
first version of the lock stored a PID, and the two flavours do not share a
PID namespace on Windows -- so each side's liveness check reported the
other's live holder as dead, reclaimed the lock, and ran the gate anyway.
Both scripts passed their own seeded-lock suites the whole time, because
each seeded a lock in the shape its own shell writes.

So this runs the real pair, at the same time, against a smoke script that
appends one line per execution, and counts the lines. Sabotaging the lock in
either script turns it red; reintroducing a PID-based holder check turns it
red on any machine that has both shells, which is the machine the bug was
reported on.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_VERIFY_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_PWSH = shutil.which("pwsh")


def _resolve_bash():
    """Same resolver as `test_context_watch.py`: prefer Git for Windows'
    bin/bash.exe shim over the raw usr/bin MSYS binary."""
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

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None or _BASH is None,
    reason="the double-run only happens where BOTH flavours fire: Windows "
           "with Git Bash and pwsh",
)


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _repo(tmp_path):
    """No verify.json, so both scripts take the smoke path -- which sits
    after the lock in each. The smoke script appends one line per run and
    then holds for long enough that a loser cannot simply arrive late and
    find the work already finished and the lock already cleaned up."""
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
    (root / "_verify" / "smoke.sh").write_text(
        'echo "ran" >> "$(dirname "$0")/../runs.txt"\n'
        "sleep 3\n"
        "echo 'SMOKE: ok'\n",
        encoding="utf-8")
    return root


def test_only_one_flavour_runs_the_expensive_part(tmp_path):
    """Both Stop-hook flavours, launched together, must produce exactly one
    smoke run between them -- and neither may leave the lock behind."""
    root = _repo(tmp_path)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))

    procs = [
        subprocess.Popen(  # pylint: disable=consider-using-with
            [_BASH, _VERIFY_SH], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(root), env=env),
        subprocess.Popen(  # pylint: disable=consider-using-with
            [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=str(root), env=env),
    ]
    for proc in procs:
        proc.stdin.write(json.dumps({}))
        proc.stdin.close()
    for proc in procs:
        proc.wait(timeout=120)

    runs = root / "runs.txt"
    lines = (runs.read_text(encoding="utf-8").split()
             if runs.exists() else [])
    assert len(lines) == 1, (
        f"the smoke ran {len(lines)} time(s); both flavours got past the "
        f"lock. sh={procs[0].returncode} ps1={procs[1].returncode}")
    assert not (root / ".crew" / ".verify-gate.lock").exists(), \
        "the winner leaked its lock"


def test_the_loser_backs_off_silently_and_does_not_fail_the_turn(tmp_path):
    """The winner's exit code governs the turn. A loser that exited non-zero,
    or wrote to stderr, would turn a passing gate into a blocked turn on
    every machine that has both shells."""
    root = _repo(tmp_path)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))

    procs = [
        subprocess.Popen(  # pylint: disable=consider-using-with
            [_BASH, _VERIFY_SH], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(root), env=env),
        subprocess.Popen(  # pylint: disable=consider-using-with
            [_PWSH, "-NoProfile", "-NonInteractive", "-File", _VERIFY_PS1],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, cwd=str(root), env=env),
    ]
    for proc in procs:
        proc.stdin.write(json.dumps({}))
        proc.stdin.close()
    results = [proc.communicate(timeout=120) for proc in procs]

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
        proc = subprocess.run(
            [_BASH, _VERIFY_SH], input=json.dumps({}), cwd=str(root),
            env=env, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        time.sleep(0.2)

    runs = (root / "runs.txt").read_text(encoding="utf-8").split()
    assert len(runs) == 2, f"the second turn was silently skipped: {runs}"

"""The Stop gate's baseline: a commit must not be a way to pass it.

The gate used to diff the working tree against HEAD. That made `git commit` a
bypass -- the same change exited 2 while dirty and 0 once committed -- so a turn
could end "verified" having verified nothing. This suite is the must-block /
must-allow pair CLAUDE.md requires of anything that can block, and every case
runs the real script against a real git repository.

The cases are written around the BOUNDARY rather than the implementation: what
matters is which changes are in scope, not which sha the gate picked to get
there.
"""
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_BASH = crew_fixtures.resolve_bash()
_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = (_ROOT + "/hooks/scripts/verify-gate.sh").replace("\\", "/")

pytestmark = pytest.mark.skipif(
    _BASH is None, reason="no usable bash; see crew_fixtures.resolve_bash")

# A rule that maps every .py file to a command that always fails. Any file in
# scope therefore blocks, which makes "did the gate see this file" observable
# as an exit code instead of by reading its stdout.
#
# reach: local - this suite is testing baseline/marker behaviour, not reach
# classification; `python -c "..."` is an interpreter followed by inline
# code, a wrapper/inline-shell trigger on its own terms under the round-4
# scanner (the same shape as `bash -c '...'`, deliberately - see
# verify_record.py's module docstring).
_VERIFY = """{
  "unmapped": "ignore",
  "rules": [{"paths": ["**/*.py"], "reach": "local",
             "run": ["python -c \\"raise SystemExit(1)\\""]}]
}"""


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(_VERIFY, encoding="utf-8")
    (root / ".crew" / "config.json").write_text('{"schema": 1}', encoding="utf-8")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return root


def _branch(root, name="work"):
    """Work happens on a branch off the default one, which is where the
    merge-base baseline applies. The no-branch-point case has its own test."""
    _git(root, "checkout", "-q", "-b", name)
    return root


def _run(root):
    done = crew_fixtures.run_gate(
        [_BASH, _SH], cwd=root, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, check=False,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)}, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    return done.returncode


def _marker(root):
    p = root / ".crew" / ".verify-verified-at"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def _head(root):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
        text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S).stdout.strip()


# --- must block -----------------------------------------------------------

def test_a_dirty_file_blocks(tmp_path):
    """The case that always worked. Here as the control: if this ever passes,
    the suite is measuring nothing and every other case below is vacuous."""
    root = _repo(tmp_path)
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    assert _run(root) == 2


def test_committing_the_change_does_not_end_the_turn(tmp_path):
    """THE BUG. Same change, committed instead of left dirty.

    Under the old baseline this exited 0 -- `git commit` was a complete bypass
    of a gate whose whole job is to refuse to let a turn end unverified.
    """
    root = _branch(_repo(tmp_path))
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "sneak it past the gate")
    assert _run(root) == 2


def test_a_marker_naming_a_commit_this_repo_no_longer_has_is_not_trusted(tmp_path):
    """A squash merge or a rebase discards the sha the marker recorded.

    Trusting it would diff against nothing and report the branch clean, which
    is the same failure the marker exists to prevent -- so an unresolvable
    marker falls back to the merge-base rather than to silence.
    """
    root = _branch(_repo(tmp_path))
    (root / ".crew" / ".verify-verified-at").write_text(
        "0" * 40 + "\n", encoding="utf-8")
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed")
    assert _run(root) == 2


# --- must allow -----------------------------------------------------------

def test_a_clean_tree_with_nothing_new_since_the_last_pass_exits_zero(tmp_path):
    """The gate must not re-run on a turn that changed nothing.

    Without this the baseline would make every Stop re-verify the whole branch
    forever, which is the cost that gets a gate switched off.
    """
    root = _repo(tmp_path)
    (root / "note.md").write_text("no python here\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "docs only")
    assert _run(root) == 0
    # Marker now names HEAD, so a second run has nothing in scope at all.
    assert _marker(root) == _head(root)
    assert _run(root) == 0


def test_a_file_no_rule_matches_does_not_block(tmp_path):
    root = _repo(tmp_path)
    (root / "note.md").write_text("prose\n", encoding="utf-8")
    assert _run(root) == 0


def test_work_verified_in_an_earlier_turn_is_not_re_verified(tmp_path):
    """The marker's actual purpose: scope is what is NEW since the last pass.

    A commit that passed the gate must not keep blocking every later turn -- if
    it did, the only way to finish would be to switch the gate off.
    """
    root = _repo(tmp_path)
    (root / "ok.md").write_text("fine\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "clean turn")
    assert _run(root) == 0
    first = _marker(root)

    # A later commit that also matches no rule: still clean, marker advances.
    (root / "more.md").write_text("also fine\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second clean turn")
    assert _run(root) == 0
    assert _marker(root) != first


# --- the marker's own contract -------------------------------------------

def test_a_failing_turn_does_not_record_a_baseline(tmp_path):
    """A marker written before the checks ran would turn a FAILING turn into a
    verified baseline for the next one -- the gate would block once and then
    wave the same unverified code through forever. It is written only on the
    pass path."""
    root = _branch(_repo(tmp_path))
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "bad")
    assert _run(root) == 2
    assert _marker(root) is None


def test_the_marker_is_not_tracked_by_git(tmp_path):
    """"What has been verified here" is a fact about one checkout. Committing it
    would hand one machine's verification record to everyone who clones."""
    root = _repo(tmp_path)
    (root / "ok.md").write_text("fine\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "clean")
    assert _run(root) == 0
    assert _marker(root) is not None
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".crew/.verify-verified-at"],
        cwd=root, capture_output=True, text=True, check=True,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S).stdout.strip()
    assert tracked == ""


def test_on_the_default_branch_with_no_marker_a_commit_still_ends_the_turn(tmp_path):
    """The one narrowing that survives, asserted so it is a recorded decision
    rather than a surprise.

    On a feature branch the merge-base gives a real baseline. Sitting ON the
    default branch there is no branch point -- merge-base(HEAD, main) IS HEAD --
    so with no marker yet the old scope applies and a commit is invisible.

    It lasts one turn: the marker is written on every clean exit, so the first
    quiet turn establishes a baseline. Closing the window entirely needs a
    turn-start signal this hook does not receive, and the alternative -- a
    marker written by another hook, where absent means permissive -- fails in
    the direction this repo keeps paying for.

    If this test ever goes RED the window has been closed, which is an
    improvement: read the gate, delete this test, and say so.
    """
    root = _repo(tmp_path)          # on main, no marker, no origin
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed on main")
    assert _run(root) == 0

    # And the window really is one turn wide: that clean exit recorded a
    # baseline, so the NEXT commit is in scope.
    assert _marker(root) == _head(root)
    (root / "mod2.py").write_text("y = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the next one is caught")
    assert _run(root) == 2

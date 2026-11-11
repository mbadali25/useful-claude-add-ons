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

# The same map plus a rule that RUNS and PASSES for prose. L-0710: a turn in
# which zero rules ran no longer writes the verified marker, so the cases
# below that are about the marker advancing need something to actually run.
_VERIFY_MD_PASSES = """{
  "unmapped": "ignore",
  "rules": [{"paths": ["**/*.py"], "reach": "local",
             "run": ["python -c \\"raise SystemExit(1)\\""]},
            {"paths": ["**/*.md"], "reach": "local", "run": ["exit 0"]}]
}"""


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, stdin=subprocess.DEVNULL,
                   timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, verify=_VERIFY):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(verify, encoding="utf-8")
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


def _base_at(root):
    p = root / ".crew" / ".verify-gate.base-at"
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
    # On main with no marker the diff is empty and ZERO rules ran, so the
    # verified marker is NOT written (L-0710); the diff baseline is, at HEAD,
    # so a second run has nothing in scope at all.
    assert _marker(root) is None
    assert _base_at(root) == _head(root)
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
    root = _branch(_repo(tmp_path, _VERIFY_MD_PASSES))
    (root / "ok.md").write_text("fine\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "clean turn")
    assert _run(root) == 0
    first = _marker(root)
    assert first == _head(root)

    # A later commit whose rule also passes: still clean, marker advances.
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
    root = _branch(_repo(tmp_path, _VERIFY_MD_PASSES))
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

    It lasts one turn: the first quiet turn establishes a baseline. Since
    L-0710 that baseline is `.crew/.verify-gate.base-at`, not the verified
    marker - zero rules ran, so nothing is recorded as verified - but it
    closes the window the same way. Closing the window entirely needs a
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
    assert _marker(root) is None
    assert _base_at(root) == _head(root)
    (root / "mod2.py").write_text("y = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the next one is caught")
    assert _run(root) == 2


# --- a marker left on another branch ---------------------------------------

def _marker_on_a_sibling_branch(tmp_path, eol="\n"):
    """A repo where the verified marker names a commit on a SIBLING branch.

    `sibling` adds a .py file (which the always-failing rule matches) and
    passes there in some earlier turn; the checkout then moves to `work`, cut
    from the same seed, which has never had that file. The marker survives the
    checkout - it is machine-local and nothing clears it - and names a commit
    that exists in this repo but is NOT an ancestor of HEAD.
    """
    root = _repo(tmp_path, _VERIFY_MD_PASSES)
    _git(root, "checkout", "-q", "-b", "sibling")
    (root / "sib.py").write_text("s = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "sibling work")
    sibling = _head(root)
    _git(root, "checkout", "-q", "main")
    _git(root, "checkout", "-q", "-b", "work")
    # newline="\n" writes the bytes exactly: the gate writes the marker with
    # printf (LF), and `eol` is how a test asks for a CRLF one instead.
    (root / ".crew" / ".verify-verified-at").write_text(
        sibling + eol, encoding="utf-8", newline="\n")
    return root, sibling


def test_a_marker_on_a_sibling_branch_does_not_put_its_paths_in_scope(tmp_path):
    """Measured in a real checkout: a marker left by another branch made the
    gate diff against an unrelated commit, so every path that branch touched
    (about 1368 there) was reported as changed on a clean tree, and the turn
    could never end clean, so the marker never refreshed itself.

    The marker is used only when it is an ancestor of HEAD; otherwise its
    merge-base with HEAD is, which is an ancestor of both. `sib.py` never
    existed on `work`, so it must not be in scope.
    """
    root, sibling = _marker_on_a_sibling_branch(tmp_path)
    (root / "ok.md").write_text("fine\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "clean turn on work")
    assert _run(root) == 0
    # And it heals: the clean pass records HEAD, replacing the stale marker.
    assert _marker(root) == _head(root)
    assert _marker(root) != sibling


def test_a_marker_on_a_sibling_branch_does_not_hide_this_branch_s_work(tmp_path):
    """The other side of the boundary: ignoring the stale marker must widen
    nothing into silence. A committed .py on `work` is still in scope."""
    root, _ = _marker_on_a_sibling_branch(tmp_path)
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed on work")
    assert _run(root) == 2


def test_a_marker_sharing_no_history_with_head_is_refused(tmp_path):
    """A marker from an orphan branch has no merge-base with HEAD. Ignoring
    it would fall through, on the default branch, to merge-base = HEAD, and a
    committed change no rule ever checked would pass (review round 1). The
    gate refuses instead, as it does for an unshared `.verify-gate.base-at`."""
    root = _repo(tmp_path)          # on main, no origin
    _git(root, "checkout", "-q", "--orphan", "orphan")
    (root / "o.txt").write_text("unrelated\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "orphan root")
    orphan = _head(root)
    _git(root, "checkout", "-q", "main")
    (root / ".crew" / ".verify-verified-at").write_text(
        orphan + "\n", encoding="utf-8", newline="\n")
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed on main")
    assert _run(root) == 2


# --- a CRLF marker, and the quiet turn under a stale marker ------------------

def _said(root):
    """Run the gate; return (exit code, stderr plus the detail log). The
    diff-base note is detail: it reaches stderr, or the log when the quiet
    output holds it back."""
    done = crew_fixtures.run_gate(
        [_BASH, _SH], cwd=root, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, check=False,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)}, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )
    p = root / ".crew" / ".verify-gate.log"
    return done.returncode, done.stderr + (p.read_text(encoding="utf-8") if p.is_file() else "")


@pytest.mark.parametrize("eol", ["\r\n", " \r\n", "\t", ""],
                         ids=["crlf", "space-crlf", "tab", "no-newline"])
def test_an_orphan_branch_marker_written_with_crlf_is_still_refused(tmp_path, eol):
    """A marker written with CRLF (an editor, PowerShell, Python on Windows)
    kept its CR through `read -r`, so `git cat-file -e "<sha>\\r^{commit}"`
    failed and the gate ignored the marker. An orphan branch's marker then
    skipped the no-shared-history refusal and fell through, on the default
    branch, to merge-base = HEAD: the committed .py below passed unchecked
    (exit 0 before the fix). The line is trimmed, so it is refused as the LF
    marker is."""
    root = _repo(tmp_path)          # on main, no origin
    _git(root, "checkout", "-q", "--orphan", "orphan")
    (root / "o.txt").write_text("unrelated\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "orphan root")
    orphan = _head(root)
    _git(root, "checkout", "-q", "main")
    (root / ".crew" / ".verify-verified-at").write_text(
        orphan + eol, encoding="utf-8", newline="\n")
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed on main")
    assert _run(root) == 2


def test_a_crlf_marker_on_a_sibling_branch_behaves_like_the_lf_one(tmp_path):
    """MUST-ALLOW, and the same boundary as the LF case: the CRLF marker is
    read as the sibling commit, so the gate takes its merge-base with HEAD
    (and says so in the detail log, which an ignored marker never did), keeps
    `sib.py` out of scope, and the clean pass heals the marker."""
    root, sibling = _marker_on_a_sibling_branch(tmp_path, eol="\r\n")
    (root / "ok.md").write_text("fine\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "clean turn on work")
    code, said = _said(root)
    assert code == 0, said
    assert "the verified marker (" + sibling + ") is not an ancestor of HEAD" in said
    assert _marker(root) == _head(root)


def test_a_crlf_marker_on_a_sibling_branch_does_not_hide_this_branch_s_work(tmp_path):
    """MUST-BLOCK twin of the LF case: a committed .py on `work` is in scope."""
    root, _ = _marker_on_a_sibling_branch(tmp_path, eol="\r\n")
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed on work")
    assert _run(root) == 2


def test_a_quiet_turn_under_a_stale_marker_writes_no_diff_baseline(tmp_path):
    """On the merge-base fallback for a marker that is not an ancestor of
    HEAD, the base still came FROM the marker (BASE_FROM_MARKER stays 1). A
    quiet turn must then leave `.crew/.verify-gate.base-at` unwritten: the
    marker is read first while it remains, so a base-at written here is a
    second baseline nothing checked against, waiting to take over the moment
    the stale marker is removed. Red on a mutant that sets the flag to 0."""
    root, _ = _marker_on_a_sibling_branch(tmp_path)
    # Nothing committed on `work`: HEAD is the merge-base, so the turn is quiet.
    code, said = _said(root)
    assert code == 0, said
    assert "is not an ancestor of HEAD" in said      # the fallback was taken
    assert "0 rules ran" in said                     # and the turn was quiet
    assert _base_at(root) is None


# --- a CRLF deploy-in-flight marker -----------------------------------------

def _deploy_marker(root, body, row):
    (root / ".crew" / ".deploy-in-flight").write_bytes(body)
    if row is not None:
        (root / ".work").mkdir(exist_ok=True)
        (root / ".work" / "PROMOTIONS.md").write_text(
            "| env | sha | result |\n" + row, encoding="utf-8", newline="\n")


def test_a_crlf_deploy_marker_with_its_row_is_recorded(tmp_path):
    """MUST-ALLOW: `qa abc123` + CRLF names the deploy the row records.
    `read -r` kept the CR on the sha, the row grep never matched, and the
    turn was blocked as DEPLOY NOT RECORDED (exit 2 before the fix)."""
    root = _repo(tmp_path)
    _deploy_marker(root, b"qa abc123\r\n", "| qa | abc123 | ok |\n")
    assert _run(root) == 0
    assert not (root / ".crew" / ".deploy-in-flight").exists()


def test_a_crlf_deploy_marker_with_no_row_still_blocks(tmp_path):
    """MUST-BLOCK twin: trimming the line must not make a missing row pass."""
    root = _repo(tmp_path)
    _deploy_marker(root, b"qa abc123\r\n", None)
    assert _run(root) == 2
    assert (root / ".crew" / ".deploy-in-flight").exists()


def test_a_base_at_holding_a_nul_byte_is_refused(tmp_path):
    """MUST-BLOCK: `<sha>\\0\\r\\n` is not a clean baseline. Bash would drop
    the NUL and the trim the CR, so the reader treats any NUL-bearing file
    as unreadable, and an unreadable base-at is refused (exit 2), not used."""
    root = _repo(tmp_path)          # on main, no marker
    (root / ".crew" / ".verify-gate.base-at").write_bytes(
        _head(root).encode("ascii") + b"\0\r\n")
    assert _run(root) == 2


def test_an_orphan_branch_marker_holding_a_nul_byte_is_refused(tmp_path):
    """MUST-BLOCK: `<orphan sha>\\0\\n`. Read as empty it would be ignored, and
    on the default branch the fallback to merge-base = HEAD would pass the
    committed .py below; a NUL-bearing marker is refused instead (Codex
    review round 3)."""
    root = _repo(tmp_path)          # on main, no origin
    _git(root, "checkout", "-q", "--orphan", "orphan")
    (root / "o.txt").write_text("unrelated\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "orphan root")
    orphan = _head(root)
    _git(root, "checkout", "-q", "main")
    (root / ".crew" / ".verify-verified-at").write_bytes(
        orphan.encode("ascii") + b"\0\n")
    (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed on main")
    assert _run(root) == 2


@pytest.mark.parametrize("body", [b"\r\n", b"\0\r\n", b"qa\r\n"],
                         ids=["cr-only", "nul", "no-sha"])
def test_a_deploy_marker_with_an_empty_field_is_not_matched_to_blank_cells(tmp_path, body):
    """MUST-BLOCK: a marker whose env or sha is empty must not match a row
    with two adjacent blank cells and clear itself (Codex review round 3)."""
    root = _repo(tmp_path)
    _deploy_marker(root, body, "| prod | | | ok |\n")
    assert _run(root) == 2
    assert (root / ".crew" / ".deploy-in-flight").exists()


@pytest.mark.parametrize("body", [b"prod .*\r\n", b"pr.d abc\r\n", b"prod [0-9a-f]\r\n"],
                         ids=["dot-star-sha", "dot-env", "bracket-sha"])
def test_a_deploy_marker_is_matched_literally_not_as_a_pattern(tmp_path, body):
    """MUST-BLOCK: the marker's fields are text, not a regex. With the CR
    trimmed, `prod .*` would match the row for any prod sha and clear a
    marker no row records (Codex review round 4)."""
    root = _repo(tmp_path)
    _deploy_marker(root, body, "| prod | abc123 | ok |\n")
    assert _run(root) == 2
    assert (root / ".crew" / ".deploy-in-flight").exists()


def test_a_deploy_marker_with_a_comma_env_list_still_matches_its_row(tmp_path):
    """MUST-ALLOW: promote-gate writes a multi-environment deploy as `qa,prod`;
    escaping the fields must not stop that literal text matching its row."""
    root = _repo(tmp_path)
    _deploy_marker(root, b"qa,prod abc123\r\n", "| qa,prod | abc123def | ok |\n")
    assert _run(root) == 0
    assert not (root / ".crew" / ".deploy-in-flight").exists()

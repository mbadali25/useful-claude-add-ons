"""Gate first: a review round is never spent on a tree the verify gate has not
passed, and a re-review of an unchanged CLEAN bundle spends none at all.

`review_gate.gate_state` answers from what a full clean pass LEAVES BEHIND --
`.crew/.verify-verified-at` at HEAD and a fingerprint that still matches the
tree -- never from the gate's exit status, which is 0 for a stood-down gate, a
lock back-off and an empty changed set as well as for a pass.

The INVARIANT, asserted over a table of tree states by running the REAL gate:
after the gate passes on a tree, `gate_state` says VERIFIED for that tree; after
any edit, it does not. That is what keeps this module's re-derivation of the
gate's changed set from drifting away from the gate's own.

Must-block and must-allow cases for `review_run.py` follow, each through the
real CLI with the fake reviewer from review_fixtures.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import review_gate
import review_ledger as rl
import review_run
from review_fixtures import env_with_path, fake_reviewer_bin, git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_SH = os.path.join(_SCRIPTS, "verify-gate.sh")
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="runs the real verify-gate.sh")


def _map(run="echo RAN-ok"):
    return {"version": 1,
            "rules": [{"paths": ["**"], "seconds": 1, "run": [run], "why": "fixture"}],
            "default": [], "unmapped": "ignore"}


def _repo(tmp_path, verify_map=None, config=None):
    root = init_repo(tmp_path / "r")
    (root / ".crew").mkdir()
    if verify_map is not False:
        (root / ".crew" / "verify.json").write_text(json.dumps(verify_map or _map()),
                                                    encoding="utf-8")
    if config is not None:
        (root / ".crew" / "config.json").write_text(config, encoding="utf-8")
    (root / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    return root


def _gate(root):
    return crew_fixtures.run_gate(
        [_BASH, _SH], input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _state(root):
    return review_gate.gate_state(str(root))[0]


# --- gate_state, unit -----------------------------------------------------------

def test_no_verify_map_is_no_gate_and_says_nothing_was_checked(tmp_path):
    state, reason = review_gate.gate_state(str(_repo(tmp_path, verify_map=False)))
    assert state == review_gate.NO_GATE
    assert "nothing was checked" in reason


def test_a_stood_down_gate_is_no_gate(tmp_path):
    root = _repo(tmp_path, config='{"verifyGate": false}')
    assert _state(root) == review_gate.NO_GATE


def test_a_gate_that_never_passed_is_unverified(tmp_path):
    state, reason = review_gate.gate_state(str(_repo(tmp_path)))
    assert state == review_gate.UNVERIFIED
    assert "never recorded a clean pass" in reason


def test_a_marker_at_head_with_no_fingerprint_for_a_dirty_tree_is_unverified(tmp_path):
    root = _repo(tmp_path)
    (root / ".crew" / ".verify-verified-at").write_text(git(root, "rev-parse", "HEAD") + "\n",
                                                        encoding="utf-8")
    state, reason = review_gate.gate_state(str(root))
    assert state == review_gate.UNVERIFIED
    assert "fingerprint is absent" in reason


def test_a_marker_behind_head_is_unverified(tmp_path):
    root = _repo(tmp_path)
    old = git(root, "rev-parse", "HEAD")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "later")
    (root / ".crew" / ".verify-verified-at").write_text(old + "\n", encoding="utf-8")
    state, reason = review_gate.gate_state(str(root))
    assert state == review_gate.UNVERIFIED
    assert "have not been through the gate" in reason


# --- the invariant, against the real gate --------------------------------------

def _modify(root):
    (root / "seed.txt").write_text("edited\n", encoding="utf-8")


def _stage_new(root):
    (root / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(root, "add", "staged.txt")


def _delete(root):
    (root / "seed.txt").unlink()


def _commit_all(root):
    git(root, "add", "-A")
    git(root, "commit", "-qm", "everything")


@needs_bash
def test_a_gate_exit_0_on_a_clean_tree_where_zero_rules_ran_is_unverified(tmp_path):
    """L-0710: a clean tree on the default branch has nothing in scope, so
    the gate exits 0 having run no rule - and records nothing, so nothing
    here may read it as a pass. This was the `clean-tree` shape below until
    the gate stopped writing the marker on zero rules."""
    root = _repo(tmp_path)
    _commit_all(root)
    result = _gate(root)
    assert result.returncode == 0, result.stderr
    assert "0 rules ran" in result.stderr, result.stderr
    assert _state(root) == review_gate.UNVERIFIED


@needs_bash
@pytest.mark.parametrize("shape", [None, _modify, _stage_new, _delete],
                         ids=["untracked", "modified", "staged-new", "deleted"])
def test_after_the_real_gate_passes_the_tree_is_verified(tmp_path, shape):
    root = _repo(tmp_path)
    if shape:
        shape(root)
    result = _gate(root)
    assert result.returncode == 0, result.stderr
    state, reason = review_gate.gate_state(str(root))
    assert state == review_gate.VERIFIED, reason + "\n" + result.stderr


@needs_bash
@pytest.mark.parametrize("edit", ["content", "new-untracked", "stage", "commit"])
def test_any_change_after_the_pass_is_unverified(tmp_path, edit):
    root = _repo(tmp_path)
    assert _gate(root).returncode == 0
    assert _state(root) == review_gate.VERIFIED
    if edit == "content":
        (root / "feature.txt").write_text("feature v2\n", encoding="utf-8")
    elif edit == "new-untracked":
        (root / "later.txt").write_text("later\n", encoding="utf-8")
    elif edit == "stage":
        git(root, "add", "feature.txt")
    else:
        _commit_all(root)
    assert _state(root) == review_gate.UNVERIFIED


_PS1 = os.path.join(_SCRIPTS, "verify-gate.ps1")
_PWSH = crew_fixtures.resolve_pwsh()
_GATE_FLAVOURS = [
    pytest.param("sh", marks=needs_bash),
    pytest.param("ps1", marks=pytest.mark.skipif(
        _PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")),
]


def _gate_flavour(root, flavour, ci=False):
    cmd = ([_BASH, _SH] + (["--ci"] if ci else []) if flavour == "sh" else
           [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1] + (["-Ci"] if ci else []))
    return crew_fixtures.run_gate(
        cmd, input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT"),
        capture_output=True, text=True, check=False,
        timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _red_lane(tmp_path, own_config=None):
    """A main checkout with `"verifyGate": false` and a linked worktree whose
    own verify map has one red rule; its own config is `own_config` or none."""
    main = _repo(tmp_path, config='{"verifyGate": false}')
    lane = tmp_path / "lane"
    git(main, "worktree", "add", "-q", "-b", "lane", str(lane))
    (lane / ".crew").mkdir()
    (lane / ".crew" / "verify.json").write_text(json.dumps(_map(run="exit 1")),
                                                encoding="utf-8")
    if own_config is not None:
        (lane / ".crew" / "config.json").write_text(own_config, encoding="utf-8")
    (lane / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    return lane


@pytest.mark.parametrize("flavour", _GATE_FLAVOURS)
def test_a_lane_inherits_the_main_checkouts_stand_down(tmp_path, flavour):
    """L-0681 (flipped from T-0088's pin): the gate and gate_state read the
    same resolved file, so a lane with no config of its own is stood down by
    the main checkout's `"verifyGate": false` in both, and --ci still fails."""
    lane = _red_lane(tmp_path)
    assert _gate_flavour(lane, flavour).returncode == 0
    assert _state(lane) == review_gate.NO_GATE
    assert _gate_flavour(lane, flavour, ci=True).returncode == 2


@pytest.mark.parametrize("flavour", _GATE_FLAVOURS)
def test_a_lane_with_its_own_config_keeps_its_gate(tmp_path, flavour):
    """Must-block: an own config wins whole, so the main checkout's stand-down
    is not read and the red rule blocks."""
    lane = _red_lane(tmp_path, own_config="{}")
    assert _gate_flavour(lane, flavour).returncode == 2
    assert _state(lane) == review_gate.UNVERIFIED


@pytest.mark.skipif(os.name == "nt", reason="the failing-git shim is a POSIX sh script")
@pytest.mark.parametrize("flavour", _GATE_FLAVOURS)
def test_gate_is_not_stood_down_when_git_cannot_tell(tmp_path, flavour):
    """Must-block: when git cannot name the main checkout (a `git` that fails
    `rev-parse --git-common-dir`), the source is `unknown`, which inherits
    nothing, so the main checkout's stand-down is not read and the red rule
    blocks; gate_state is not stood down by a config either."""
    lane = _red_lane(tmp_path)
    shim = tmp_path / "shim"
    shim.mkdir()
    real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True,
                          check=True).stdout.strip()
    (shim / "git").write_text(
        "#!/bin/sh\ncase \"$*\" in *--git-common-dir*) exit 128 ;; esac\n"
        f'exec "{real}" "$@"\n', encoding="utf-8")
    os.chmod(shim / "git", 0o755)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(lane), OS="Windows_NT",
               PATH=str(shim) + os.pathsep + os.environ.get("PATH", ""))
    cmd = ([_BASH, _SH] if flavour == "sh" else
           [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1])
    proc = crew_fixtures.run_gate(cmd, input="{}", cwd=str(lane), env=env,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    assert proc.returncode == 2, proc.stderr


def test_gate_state_is_not_stood_down_when_git_cannot_tell(tmp_path, monkeypatch):
    lane = _red_lane(tmp_path)
    monkeypatch.setattr(review_gate.crew_common, "_main_checkout",
                        lambda _root: (None, "git could not tell (fixture)"))
    state, reason = review_gate.gate_state(str(lane))
    assert not (state == review_gate.NO_GATE and "verifyGate" in reason), reason


@needs_bash
def test_a_failing_gate_leaves_the_tree_unverified(tmp_path):
    root = _repo(tmp_path, verify_map=_map(run="exit 1"))
    assert _gate(root).returncode == 2
    assert _state(root) == review_gate.UNVERIFIED


@needs_bash
def test_a_skipped_check_is_unverified_and_the_reason_names_it(tmp_path):
    """A tool that is not installed exits 77, the gate exits 0, and the marker
    never advances -- so every review here is refused. The refusal has to say
    that a SKIP is why, or it reads as a gate that is broken."""
    root = _repo(tmp_path, verify_map=_map(run="exit 77"))
    assert _gate(root).returncode == 0
    state, reason = review_gate.gate_state(str(root))
    assert state == review_gate.UNVERIFIED
    assert "SKIP" in reason, reason


@needs_bash
def test_a_corrupt_record_cache_is_unknown_not_verified(tmp_path):
    root = _repo(tmp_path)
    assert _gate(root).returncode == 0
    (root / ".crew" / ".verify-gate.record.json").write_text("[]", encoding="utf-8")
    state, reason = review_gate.gate_state(str(root))
    assert state == review_gate.UNKNOWN, reason


def test_git_failing_is_unknown_not_verified(tmp_path):
    root = tmp_path / "not-a-repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "verify.json").write_text(json.dumps(_map()), encoding="utf-8")
    (root / ".crew" / ".verify-verified-at").write_text("0" * 40 + "\n", encoding="utf-8")
    state, _ = review_gate.gate_state(str(root))
    assert state == review_gate.UNKNOWN


# --- review_run: must-block / must-allow ---------------------------------------

def _bundle(repo, scratch):
    base = git(repo, "rev-parse", "HEAD")
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"),
                    "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    (scratch / "prompt.txt").write_text(
        "Review. " + " ".join(p["name"] for p in json.loads(
            (scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]),
        encoding="utf-8")


def _review(repo, tmp_path, *extra, mode="clean", provider="codex"):
    scratch, work = tmp_path / "scratch", tmp_path / "work"
    _bundle(repo, scratch)
    fakes = fake_reviewer_bin(tmp_path / "bin")
    result = subprocess.run(
        [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1", "--scratch", str(scratch),
         "--provider", provider, "--work-dir", str(work)] + list(extra),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
        env=env_with_path(fakes, FAKE_REVIEWER_MODE=mode), timeout=120)
    review_json = work / "review.json"
    review = json.loads(review_json.read_text(encoding="utf-8")) if review_json.exists() else None
    return result, review


def _rounds(repo):
    return rl.status(str(repo), "T1")["rounds"]


def test_an_unverified_tree_is_refused_with_exit_unverified_and_no_round_spent(tmp_path):
    repo = _repo(tmp_path)
    result, review = _review(repo, tmp_path)
    assert result.returncode == review_run.EXIT_UNVERIFIED, result.stdout + result.stderr
    assert "gate UNVERIFIED" in result.stderr and "No round reserved" in result.stderr
    assert _rounds(repo) == [] and review is None


def test_the_claude_reservation_is_refused_the_same_way(tmp_path):
    repo = _repo(tmp_path)
    result, _ = _review(repo, tmp_path, "--reserve-only", provider="claude")
    assert result.returncode == review_run.EXIT_UNVERIFIED
    assert "ROUND=" not in result.stdout
    assert _rounds(repo) == []


@needs_bash
def test_an_unknown_gate_state_is_refused_like_an_unverified_one(tmp_path):
    """The collapse this repo keeps paying for: "could not tell" must not
    review as though it were "passed"."""
    repo = _repo(tmp_path)
    assert _gate(repo).returncode == 0
    (repo / ".crew" / ".verify-gate.record.json").write_text("[]", encoding="utf-8")
    result, _ = _review(repo, tmp_path)
    assert result.returncode == review_run.EXIT_UNVERIFIED, result.stdout + result.stderr
    assert "gate UNKNOWN" in result.stderr
    assert _rounds(repo) == []


def test_allow_unverified_reviews_anyway_and_records_the_override(tmp_path):
    repo = _repo(tmp_path)
    result, review = _review(repo, tmp_path, "--allow-unverified")
    assert result.returncode == 0, result.stdout + result.stderr
    assert review["gate"]["state"] == review_gate.UNVERIFIED
    assert review["gate"]["overridden"] is True
    assert "gate=UNVERIFIED" in result.stdout


@needs_bash
def test_a_verified_tree_is_reviewed(tmp_path):
    repo = _repo(tmp_path)
    assert _gate(repo).returncode == 0
    result, review = _review(repo, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert review["gate"] == {"state": review_gate.VERIFIED,
                              "reason": review["gate"]["reason"], "overridden": False}


def test_no_gate_is_reviewed_and_says_so(tmp_path):
    repo = _repo(tmp_path, verify_map=False)
    result, review = _review(repo, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert review["gate"]["state"] == review_gate.NO_GATE
    assert "gate NO_GATE" in result.stderr


# --- the CLEAN-receipt short-circuit --------------------------------------------

def test_an_unchanged_clean_bundle_is_not_reviewed_twice(tmp_path):
    repo = _repo(tmp_path, verify_map=False)
    first, _ = _review(repo, tmp_path)
    assert first.returncode == 0

    again, _ = _review(repo, tmp_path)

    assert again.returncode == 0, again.stdout + again.stderr
    assert "CLEAN from the existing receipt" in again.stdout
    assert len(_rounds(repo)) == 1


def test_the_claude_path_reports_already_clean_instead_of_a_round(tmp_path):
    repo = _repo(tmp_path, verify_map=False)
    assert _review(repo, tmp_path)[0].returncode == 0

    again, _ = _review(repo, tmp_path, "--reserve-only", provider="claude")

    assert again.returncode == 0
    assert "ALREADY_CLEAN=1" in again.stdout and "ROUND=" not in again.stdout
    assert len(_rounds(repo)) == 1


def test_an_edit_after_the_clean_round_is_reviewed_again(tmp_path):
    repo = _repo(tmp_path, verify_map=False)
    assert _review(repo, tmp_path)[0].returncode == 0
    (repo / "feature.txt").write_text("feature v2\n", encoding="utf-8")

    again, _ = _review(repo, tmp_path)

    assert "existing receipt" not in again.stdout
    assert len(_rounds(repo)) == 2


def test_owner_accepted_findings_do_not_short_circuit(tmp_path):
    repo = _repo(tmp_path, verify_map=False)
    assert _review(repo, tmp_path, mode="findings")[0].returncode == 1
    rl.accept(str(repo), "T1", "owner")

    again, _ = _review(repo, tmp_path)

    assert "existing receipt" not in again.stdout
    assert len(_rounds(repo)) == 2


# --- round timing ---------------------------------------------------------------

def test_every_round_records_how_long_it_took(tmp_path):
    repo = _repo(tmp_path, verify_map=False)
    result, review = _review(repo, tmp_path)
    assert isinstance(review["elapsed_s"], int) and review["elapsed_s"] >= 0
    assert f"elapsed={review['elapsed_s']}s" in result.stdout

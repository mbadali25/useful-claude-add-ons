"""A FAILED turn must still sync the rules that passed - and must not
persist the FAILING rule's own outcome.

`plugin/crew/hooks/scripts/verify-gate.sh:1403` used to be
`[ "$FAILED" -eq 0 ] || exit 2`, sitting ABOVE the per-rule record sync -
whose own (then-accurate) comment said it was "only reached on a turn where
nothing FAILED". The intent (an unreliable run should not overwrite what a
previous clean run recorded) was right at the sha-marker/fingerprint
granularity; the exit was global while the evidence is per-rule, so ONE
failing rule among many discarded every OTHER rule's passing evidence too.
`.crew/verify.json:193` recorded the measured consequence in this repo: one
absent `node_modules` kept three unrelated rules UNVERIFIED and the sha
marker frozen 14 commits behind HEAD. See
`.crew/codemap/verification-harness.md`, "Two defects in the gate this map
feeds", item 1.

Fix: the sync now runs on EVERY turn, BEFORE `[ "$FAILED" -eq 0 ] || exit 2`
(and the PowerShell twin's `if ($failed) { exit 2 }`), which still runs
immediately after the sync and still exits the turn before either marker can
advance.

**First shape of this fix was itself reviewed BLOCK and reverted.** It added
a persisted "failed" status in verify_record.py, keyed on the failing rule's
content hash - and that hash changes the moment someone EDITS the rule to
fix it (`rule_key()` hashes `run`), so the OLD "failed" entry became an
ORPHAN the stale-obligation prune could never clear without `--all`,
freezing the marker behind a rule that was already fixed. The corrected
shape records ONLY the per-rule PASSES on a failed turn; the exit code (2)
already carries the failure, and nothing needs to survive to the next turn
because a FAILED turn never advances either marker in the first place - see
verify_record.py's `_sync`, the "fail" branch, for the full reasoning.
`test_editing_a_failing_rule_to_pass_does_not_orphan_the_marker` below
reproduces the reviewed-out bug and is the regression test for it.

Sabotage, done by hand in this ticket's own worktree and confirmed red before
this file was written green: reverting `verify-gate.sh` to the old ordering
(sync AFTER `exit 2`) turns `test_must_record_a_pass_alongside_a_fail` red -
the passing rule's cost is never cached, because the sync never runs on the
FAILED turn at all. Separately, reverting verify_record.py's "fail" branch
back to persisting a "failed" entry turns
`test_editing_a_failing_rule_to_pass_does_not_orphan_the_marker` red - the
fixed rule's Stop stays blocked behind the orphaned old entry. Restoring both
fixes and re-running turns everything green again; `git diff` against the
ticket's start commit was used to confirm each revert touched nothing else
before restoring it.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None,
                                                 reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        not sys.platform.startswith("win") or _PWSH is None,
        reason="the .ps1 gate is the native-Windows flavour")),
]


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True)


def _repo(tmp_path, verify_map):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("committed", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    (root / ".crew" / "verify.json").write_text(json.dumps(verify_map),
                                                encoding="utf-8")
    return root


def _run(flavour, root, *extra):
    if flavour == "sh":
        cmd = [_BASH, _SH, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[a.replace("--all", "-All") for a in extra]]
    return subprocess.run(
        cmd, input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
    )


def _baseline(root):
    marker = root / ".crew" / ".verify-verified-at"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def _record(root):
    p = root / ".crew" / ".verify-gate.record.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _timings(root):
    p = root / ".crew" / ".verify-gate.timings.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# One rule with NO declared `seconds` (so a clean pass caches its measured
# cost - the positive, hard-to-fake proof that the sync actually ran) and one
# rule that always fails.
_ONE_PASS_ONE_FAIL = {
    "version": 1,
    "rules": [
        {"paths": ["a.py"], "run": ["echo RAN-ok"], "why": "passes, unpriced"},
        {"paths": ["b.py"], "seconds": 1, "run": ["exit 1"], "why": "always fails"},
    ],
    "default": [], "unmapped": "ignore",
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_must_record_a_pass_alongside_a_fail(flavour, tmp_path):
    """MUST-RECORD. A turn with one passing rule and one failing rule must
    still persist the PASSING rule's evidence, and must still exit 2. The
    failing rule's own outcome is deliberately NOT persisted - see the
    module docstring and verify_record.py's `_sync` for why.

    Proof the sync actually ran on this FAILED turn: the passing rule has no
    declared `seconds`, so a sync that runs caches its measured wall time in
    `.crew/.verify-gate.timings.json` - a side effect the OLD ordering (sync
    only reached when FAILED was 0) could never produce on a turn where a
    different rule failed, because the whole sync call was skipped.
    """
    root = _repo(tmp_path, _ONE_PASS_ONE_FAIL)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")

    result = _run(flavour, root)
    assert result.returncode == 2, (
        "a real failure must still exit 2. " + result.stderr
    )
    assert "echo RAN-ok" in result.stderr, (
        "the passing rule did not even run. " + result.stderr
    )
    timings = _timings(root)
    assert timings.get("rules"), (
        "the passing rule's measured cost was never cached - its evidence "
        "was discarded because a DIFFERENT rule failed this turn. "
        + result.stderr
    )

    rec = _record(root)
    assert rec.get("rules", {}) == {}, (
        "the failing rule's outcome was persisted into the record - that is "
        "exactly the shape review found orphans the marker once the rule is "
        "edited to fix the failure (see "
        "test_editing_a_failing_rule_to_pass_does_not_orphan_the_marker). "
        + json.dumps(rec)
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_must_not_advance_either_marker_on_a_failed_turn(flavour, tmp_path):
    """MUST-NOT-ADVANCE. Recording per-rule evidence on a FAILED turn must
    never let the sha marker or the fingerprint advance - the exit-2 check
    still runs, unconditionally on FAILED, immediately after the sync and
    before either marker can be written."""
    green = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-ok"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, green)
    (root / "a.py").write_text("x", encoding="utf-8")
    settle = _run(flavour, root)
    assert settle.returncode == 0, settle.stderr
    before = _baseline(root)
    assert before, "the quiet first turn should establish a baseline"
    fp = root / ".crew" / ".verify-gate.fingerprint"
    assert fp.exists()
    fp_before = fp.read_text(encoding="utf-8")

    (root / ".crew" / "verify.json").write_text(
        json.dumps(_ONE_PASS_ONE_FAIL), encoding="utf-8")
    _git(root, "add", ".crew/verify.json")
    _git(root, "commit", "-q", "-m", "widen the map")
    (root / "a.py").write_text("x2", encoding="utf-8")
    (root / "b.py").write_text("y", encoding="utf-8")

    failed = _run(flavour, root)
    assert failed.returncode == 2, failed.stderr
    assert _baseline(root) == before, (
        "the sha marker advanced on a turn where a rule actually failed. "
        + failed.stderr
    )
    assert fp.exists() and fp.read_text(encoding="utf-8") == fp_before, (
        "the fingerprint advanced (or was deleted+rewritten) on a FAILED "
        "turn. " + failed.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_all_pass_turn_still_advances_the_baseline(flavour, tmp_path):
    """Existing behaviour, unchanged by the reorder: nothing failed, nothing
    was deferred or skipped, so both markers must still advance - the sync
    moving earlier must not become "never record a clean turn either"."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-ok"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    _run(flavour, root)
    before = _baseline(root)

    (root / "a.py").write_text("x", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "add a.py")
    after_run = _run(flavour, root)
    assert after_run.returncode == 0, after_run.stderr
    assert _baseline(root) != before, (
        "nothing was deferred and everything passed, so the baseline must "
        "advance. " + after_run.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_editing_a_failing_rule_to_pass_does_not_orphan_the_marker(flavour, tmp_path):
    """Regression test for the reviewed-out BLOCK: a rule fails, is then
    EDITED to fix the failure (a new `rule_key`, since it hashes `run`), and
    a later clean Stop must ADVANCE the marker rather than stay frozen
    behind a stale obligation recorded under the rule's OLD content hash.

    Reproduction, exactly as review described it: rule b `exit 1` -> Stop
    (rc 2) -> edit rule b's `run` to `echo fixed` -> Stop must exit 0 and
    advance the baseline.
    """
    failing = {
        "version": 1,
        "rules": [{"paths": ["b.py"], "seconds": 1, "run": ["exit 1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, failing)
    (root / "b.py").write_text("y", encoding="utf-8")  # left untracked deliberately

    first = _run(flavour, root)
    assert first.returncode == 2, first.stderr
    assert _baseline(root) is None, (
        "a failed turn must not have written a baseline in the first place. "
        + first.stderr
    )

    fixed = {
        "version": 1,
        "rules": [{"paths": ["b.py"], "seconds": 1, "run": ["echo fixed"]}],
        "default": [], "unmapped": "ignore",
    }
    (root / ".crew" / "verify.json").write_text(json.dumps(fixed), encoding="utf-8")

    second = _run(flavour, root)
    assert second.returncode == 0, (
        "fixing the rule (a NEW content hash) must let a clean turn "
        "advance the marker, not stay blocked behind a stale obligation "
        "recorded under the OLD rule's key. " + second.stderr
    )
    assert _baseline(root) is not None, (
        "the marker never advanced even after the rule was fixed. "
        + second.stderr
    )
    rec = _record(root)
    assert not any(v.get("orphaned") for v in rec.get("rules", {}).values()), (
        "an orphaned obligation is blocking the record. " + json.dumps(rec)
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_failed_turn_still_exits_2_when_the_sync_write_also_fails(flavour, tmp_path):
    """FIX 1 from review: the exit code must key off $FAILED/$failed alone,
    never off whether the record sync itself succeeded. Forces the sync to
    fail (a directory where the record file needs to go, exactly as
    test_7_a_save_failure_blocks_both_markers does elsewhere) ALONGSIDE a
    genuinely failing rule, so a mutation that returns 0 whenever
    SYNC_STATUS is nonzero - reported by review as passing all 351 existing
    tests - is caught here."""
    vmap = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 1, "run": ["exit 1"]}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, vmap)
    (root / "a.py").write_text("x", encoding="utf-8")
    (root / ".crew" / ".verify-gate.record.json").mkdir()

    result = _run(flavour, root)
    assert result.returncode == 2, (
        "a real rule failure must exit 2 even when the record sync ALSO "
        "fails to persist - the exit code must not be keyed off "
        "SYNC_STATUS. " + result.stderr
    )

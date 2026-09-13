"""The promote gate must fail closed when its own check cannot be evaluated.

`VERDICT` is produced by a command substitution, so a python that raises writes
its traceback to stderr and NOTHING to stdout. Every later test read that empty
string as "no unmet preconditions", so an error inside the check became
permission to deploy -- silently, with the in-flight marker written, and
byte-identical in behaviour to a valid, current rollback.

The trigger is not exotic: the regex accepts any `\\d{4}-\\d{2}-\\d{2}`, so
`last verified: 2026-99-99` is date-SHAPED, reaches `fromisoformat`, and
raises. Someone fat-fingering a month is enough.

Each case is paired with a control that must still behave as before, because a
test that only asserts the bad date blocks would also pass if the gate were
changed to block everything.
"""
import datetime
import json
import os
import pathlib
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_GATE = (pathlib.Path(__file__).resolve().parents[1]
         / "hooks" / "scripts" / "promote-gate.sh")

_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")

_PAYLOAD = json.dumps({"tool_input": {"command": "deploy-prod"}})


def _fixture(tmp_path, verified_line):
    """A clean, committed repo gated on one environment.

    Committing `.crew/verify.json` matters: leave it dirty and the gate's
    clean-tree check fires first and blocks for a different reason entirely,
    which reads as "the gate works" while proving nothing about this one.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir()
    for args in (["init", "-q"],
                 ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "T"]):
        subprocess.run(["git"] + args, cwd=root, check=False)
    (root / "README.md").write_text("x\n", encoding="utf-8")
    (root / "runbook.md").write_text(
        f"# Rollback\n{verified_line}\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps({
        "environments": {
            "prod": {"deploy": "deploy-prod", "rollback": "runbook.md"}}},
    ), encoding="utf-8")
    subprocess.run(["git", "add", "-A", "-f"], cwd=root, check=False)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"],
                   cwd=root, check=False)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                           capture_output=True, text=True, check=False).stdout
    assert dirty.strip() == "", f"fixture tree must be clean, got: {dirty!r}"
    return root


def _run(root):
    proc = subprocess.run(
        [_BASH, _GATE.as_posix()], input=_PAYLOAD,
        capture_output=True, text=True, check=False,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)), cwd=str(root),
    )
    return proc.returncode, proc.stderr


@needs_bash
def test_a_malformed_rollback_date_blocks_the_deploy(tmp_path):
    """The regression. `2026-99-99` used to exit 0 with an empty stderr."""
    root = _fixture(tmp_path, "last verified: 2026-99-99")
    code, err = _run(root)
    assert code == 2, f"a malformed date must block, got exit {code}"
    assert "2026-99-99" in err, "the message must name the offending value"
    assert not (root / ".crew" / ".deploy-in-flight").exists(), \
        "a blocked deploy must not leave an in-flight marker"


@needs_bash
def test_a_stale_but_valid_date_still_blocks_with_its_own_message(tmp_path):
    """Control: the ordinary blocking path is untouched, and says something
    different from the malformed-date path. Two findings, two messages."""
    root = _fixture(tmp_path, "last verified: 2020-01-01")
    code, err = _run(root)
    assert code == 2
    assert "days ago" in err
    assert "not a real date" not in err


@needs_bash
def test_a_fresh_valid_date_still_allows_the_deploy(tmp_path):
    """Control, and the one that matters most: the fix must not be "block
    everything". A gate that refuses every deploy is not a working gate, it is
    a broken one that happens to be safe."""
    fresh = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    root = _fixture(tmp_path, f"last verified: {fresh}")
    code, _ = _run(root)
    assert code == 0, "a current rollback must still deploy"
    assert (root / ".crew" / ".deploy-in-flight").exists()


@needs_bash
def test_the_gate_blocks_when_its_own_check_cannot_RUN(tmp_path):
    """The fail-closed path itself, exercised by an input that actually raises.

    This test exists because the sabotage suite proved the obvious one vacuous.
    `2026-99-99` is now handled GRACEFULLY -- it is reported as its own unmet
    precondition -- so it no longer reaches the exit-status check at all, and
    mutating that check to `-eq 999` left the malformed-date test green. The
    belt was being tested while the braces held.

    A `rollback` pointing at a DIRECTORY is the cheap way to make the check
    genuinely raise (`open()` on a directory), and it is not contrived: it is
    what you get by naming the folder the runbooks live in. The gate must then
    block *because it could not evaluate*, which is a different finding from
    any precondition being unmet, and must say so.
    """
    root = _fixture(tmp_path, "last verified: 2020-01-01")
    (root / "rollbacks").mkdir()
    (root / "rollbacks" / ".keep").write_text("x\n", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps({
        "environments": {
            "prod": {"deploy": "deploy-prod", "rollback": "rollbacks"}}},
    ), encoding="utf-8")
    subprocess.run(["git", "add", "-A", "-f"], cwd=root, check=False)
    subprocess.run(["git", "commit", "-q", "-m", "dir rollback"],
                   cwd=root, check=False)
    code, err = _run(root)
    assert code == 2, f"an unevaluatable check must block, got exit {code}"
    assert "could not be evaluated" in err
    assert "This is not a pass" in err
    assert not (root / ".crew" / ".deploy-in-flight").exists()


@needs_bash
def test_a_missing_verified_line_still_blocks(tmp_path):
    """Control for the branch next door -- no date at all is a separate
    finding from a date that will not parse, and both must block."""
    root = _fixture(tmp_path, "(nothing recorded)")
    code, err = _run(root)
    assert code == 2
    assert "no 'last verified" in err

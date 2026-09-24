"""What verify-gate may record as verified, and when it must not.

From the Codex review of the 0.19.65-0.19.70 branch (one BLOCK, four FIX).

The gate keeps TWO records of a clean run: `.crew/.verify-verified-at`, the
commit SHA later runs diff against, and `.crew/.verify-gate.fingerprint`, the
unchanged-turn skip. The fingerprint had a guard. **The SHA baseline had
none**, and it is the one that decides what lands in the changed set at all.

So a Stop that DEFERRED a rule still advanced the baseline, and the deferred
file dropped out of the changed set for every later run -- including `--all`,
which correctly ignores the fingerprint and was still diffing against the
advanced marker. Reproduced before the fix: commit a file mapped to a failing
90s rule, Stop (deferred, exit 0), then `--all` -> exit 0 with the failing
check never executed once. A committed change had left verification scope
permanently, and nothing said so.

It survived review because the guard a reader looks for is present and correct
on the twin, so its absence on the other reads as deliberate.

**These cases assert the FILE, not the exit code.** Exit 0 is correct on the
deferred path, so an exit-code-only assertion proves nothing about this bug --
which is exactly how it shipped.

The mirror defect is here too: the fingerprint's guard was `[ -z "$NOTICES" ]`,
a string-emptiness test doing a boolean's job. `NOTICES` is prose for a human
and is non-empty for two different facts -- "a rule was deferred" and "a rule
had no stated cost" -- and only the first means "not verified". So a rule that
ran and PASSED suppressed recording, disabling the skip for every map that is
not fully costed, which is most of them. Both records now share one predicate
driven by a machine-readable deferred COUNT.
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

# TWO rules on the same path, each fitting the 60s default ALONE but not
# together, so the second is ACUTELY deferred (budget contention this turn,
# not permanently over budget) -- the case that must still block the
# baseline. It FAILS when it finally runs, so a full run that reaches it is
# unmistakable.
# reach: local on the second rule of each map below - these fixtures test
# BUDGET deferral (acute/chronic), not reach classification; `sh -c '...'`
# is a wrapper/inline-shell trigger on its own terms under the round-4
# scanner, and an undeclared rule is excluded for REACH before budget logic
# is ever reached, which would test the wrong mechanism entirely.
_DEFERRING_AND_FAILING = {
    "version": 1,
    "rules": [
        {"paths": ["a.py"], "seconds": 50, "run": ["echo fits-alone"],
         "why": "fits alone, crowds out the second"},
        {"paths": ["a.py"], "seconds": 50, "reach": "local",
         "run": ["sh -c 'echo SHOULD-HAVE-RUN; exit 1'"],
         "why": "fits alone, but not alongside the first under a 60s budget"},
    ],
    "default": [], "unmapped": "ignore",
}

# A single rule priced ABOVE the whole budget on its own: chronic, never
# acute. This is the case the per-rule record feature exists for -- the
# baseline must advance PAST it while it stays named and reported.
_CHRONICALLY_OVER_BUDGET = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 900, "reach": "local",
               "run": ["sh -c 'echo SHOULD-HAVE-RUN; exit 1'"],
               "why": "permanently over the 60s budget alone"}],
    "default": [], "unmapped": "ignore",
}

_GREEN = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-ok"],
               "why": "cheap and green"}],
    "default": [], "unmapped": "ignore",
}


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True,
                   capture_output=True, text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


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
        capture_output=True, text=True, check=False, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S,
    )


def _baseline(root):
    marker = root / ".crew" / ".verify-verified-at"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def _commit_mapped_file(root):
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "add a.py")


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_deferred_rule_does_not_advance_the_verified_baseline(flavour, tmp_path):
    """MUST-BLOCK for the BLOCK. Advancing the baseline over a rule that was
    never checked removes the committed change from scope permanently, and it
    is self-perpetuating: every later run reads the advanced marker."""
    root = _repo(tmp_path, _DEFERRING_AND_FAILING)
    settle = _run(flavour, root)
    assert settle.returncode == 0, settle.stderr
    before = _baseline(root)
    assert before, "the quiet first turn should establish a baseline"

    _commit_mapped_file(root)
    deferred = _run(flavour, root)

    assert deferred.returncode == 0, (
        "a deferral is not a failure; exit 0 is correct here, which is why "
        "this case asserts the file instead. " + deferred.stderr
    )
    assert "deferred to /crew:verify" in deferred.stderr, deferred.stderr
    assert _baseline(root) == before, (
        "the verified baseline advanced over a rule that was never checked, "
        "so the committed file has left verification scope for good. "
        + deferred.stderr
    )
    assert "NOT advanced" in deferred.stderr, (
        "and it must SAY the baseline was held back -- a silent hold is as "
        "unreadable as a silent skip. " + deferred.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_full_run_still_sees_a_file_whose_check_was_deferred(flavour, tmp_path):
    """The reviewer's own reproduction, from the other end: after a deferring
    Stop, a full run must RUN the deferred rule and fail on it."""
    root = _repo(tmp_path, _DEFERRING_AND_FAILING)
    _run(flavour, root)
    _commit_mapped_file(root)
    _run(flavour, root)

    forced = _run(flavour, root, "--all")
    assert "SHOULD-HAVE-RUN" in forced.stderr, (
        "the full run never executed the deferred check -- the file had "
        "dropped out of the changed set. " + forced.stderr
    )
    assert forced.returncode == 2, (
        "the deferred rule fails, so a full run must block. rc="
        + str(forced.returncode) + " " + forced.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_chronic_rule_advances_the_baseline_but_all_still_finds_it(flavour, tmp_path):
    """The per-rule record feature's whole point: a rule permanently over
    budget on its own must not freeze the baseline forever -- but the
    baseline advancing must not put the file that triggered it out of
    --all's reach either, or "deferred" quietly becomes "never checked
    again", just moved one step over."""
    root = _repo(tmp_path, _CHRONICALLY_OVER_BUDGET)
    settle = _run(flavour, root)
    assert settle.returncode == 0, settle.stderr
    before = _baseline(root)
    assert before

    _commit_mapped_file(root)
    deferred = _run(flavour, root)
    assert deferred.returncode == 0, deferred.stderr
    assert "permanently over budget" in deferred.stderr, deferred.stderr
    assert _baseline(root) != before, (
        "a CHRONIC deferral must not block the baseline -- see "
        "verify_record.py. " + deferred.stderr
    )

    forced = _run(flavour, root, "--all")
    assert "SHOULD-HAVE-RUN" in forced.stderr, (
        "--all must still reach the file that triggered the chronic rule, "
        "even though the sha marker has advanced past the commit that "
        "added it. " + forced.stderr
    )
    assert forced.returncode == 2, forced.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_fully_checked_run_does_advance_the_baseline(flavour, tmp_path):
    """MUST-ALLOW, and what stops the fix becoming "never record again"."""
    root = _repo(tmp_path, _GREEN)
    _run(flavour, root)
    before = _baseline(root)

    _commit_mapped_file(root)
    after_run = _run(flavour, root)
    assert after_run.returncode == 0, after_run.stderr
    assert _baseline(root) != before, (
        "nothing was deferred and everything passed, so the baseline must "
        "advance. " + after_run.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_unstated_cost_that_passes_still_records(flavour, tmp_path):
    """The mirror of the BLOCK, and why both guards are ONE predicate.

    `deferred` and `unstated` are different facts and only the first means
    "not verified". Reading the notice TEXT conflated them, so a rule that ran
    and passed suppressed recording -- disabling the unchanged-turn skip for
    every map that is not fully costed.
    """
    unstated = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "run": ["echo RAN-ok"],
                   "why": "deliberately no seconds"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, unstated)
    (root / "a.py").write_text("x = 1", encoding="utf-8")

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    assert "UNSTATED" in first.stderr, (
        "the unstated cost must still be REPORTED -- it just must not "
        "suppress recording. " + first.stderr
    )

    second = _run(flavour, root)
    assert "SKIPPED, not re-run" in second.stderr, (
        "a rule that RAN and PASSED is verified, whatever its cost was not "
        "stated as; the skip must still work. " + second.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_mapped_crew_path_is_verified_not_excluded(flavour, tmp_path):
    """MUST-BLOCK for the blanket `.crew/` exclusion in the fingerprint.

    A repo may legitimately map a path under `.crew/` to a check. Excluding
    the whole directory let such a file change its contents, keep the passing
    digest and skip verification entirely.
    """
    mapped = {
        "version": 1,
        # reach: local - testing the .crew/ path-exclusion fingerprint bug,
        # not reach classification; `sh -c` plus an existing `.crew/check.txt`
        # argument are BOTH wrapper triggers under the round-4 scanner.
        "rules": [{"paths": [".crew/check.txt"], "seconds": 1, "reach": "local",
                   "run": ["sh -c 'grep -q GOOD .crew/check.txt'"],
                   "why": "a content check on a .crew path"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, mapped)
    (root / ".crew" / "check.txt").write_text("GOOD", encoding="utf-8")
    assert _run(flavour, root).returncode == 0

    (root / ".crew" / "check.txt").write_text("BAD", encoding="utf-8")
    broken = _run(flavour, root)
    assert "SKIPPED, not re-run" not in broken.stderr, (
        "a mapped .crew/ file changed and the gate skipped anyway. "
        + broken.stderr
    )
    assert broken.returncode == 2, (
        "the check must run and fail. rc=" + str(broken.returncode) + " "
        + broken.stderr
    )

"""The unchanged-turn skip: verify-gate stops re-proving a tree it just proved.

Stop fires once per TURN, so a turn that changed nothing the gate depends on
re-ran the whole map to reach the answer it reached a minute ago. The event is
not the gate; the STATE is -- the argument pm_pulse.py makes in its own header,
pointed here at a different verdict.

Three properties carry the safety of this, and each has a case:

1. **A skip is only ever taken after a CLEAN, COMPLETE run.** The marker is
   not written when a rule failed, and not written when the Stop budget
   deferred one. A deferred rule was never checked, so recording it would turn
   "we ran out of budget" into "this tree is verified" -- the unknown
   collapsing into the safe-looking value, which is this repository's named
   recurring defect.

2. **A skip is never silent.** 0.19.65 existed because a silent `exit 0` was
   byte-identical to a pass; a silent skip would reintroduce exactly that, so
   the gate says what it skipped and why.

3. **Both flavours agree.** The digest comes from the shared
   `verify_fingerprint.py` rather than from a hash reimplemented in bash and
   again in PowerShell, so a marker written by one flavour is honoured by the
   other. The cross-flavour case asserts that directly.

`.crew/` is excluded from the digest and that is load-bearing rather than
tidy: the gate writes its own markers there, so including it made every run
invalidate the digest it had just recorded and the skip never fired once.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

import verify_fingerprint

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

_GREEN = {
    "version": 1,
    "rules": [{"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-ok"],
               "why": "cheap and green"}],
    "default": [],
    "unmapped": "ignore",
}


def _repo(tmp_path, verify_map=None, config=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root,
                   check=True, capture_output=True, text=True)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(
        json.dumps(verify_map if verify_map is not None else _GREEN),
        encoding="utf-8")
    if config is not None:
        (root / ".crew" / "config.json").write_text(config, encoding="utf-8")
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


def _skipped(result):
    return "SKIPPED, not re-run" in result.stderr


def _ran(result):
    return "echo RAN-ok" in result.stderr and not _skipped(result)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_unchanged_turn_skips_the_second_time(flavour, tmp_path):
    root = _repo(tmp_path)
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    assert _ran(first), "the first run must actually run. " + first.stderr

    second = _run(flavour, root)
    assert second.returncode == 0, second.stderr
    assert _skipped(second), (
        "nothing changed, so the second run must skip. " + second.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_the_skip_says_so_rather_than_exiting_silently(flavour, tmp_path):
    """Must-allow, and the lesson 0.19.65 paid for: an exit 0 with nothing on
    stderr is byte-identical to a pass."""
    root = _repo(tmp_path)
    _run(flavour, root)
    result = _run(flavour, root)

    assert result.stderr.strip(), "a silent skip is indistinguishable from a pass"
    assert "SKIPPED" in result.stderr, result.stderr
    assert "fingerprint" in result.stderr, (
        "the skip must name the digest it matched, or it cannot be debugged. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_editing_a_file_runs_the_checks_again(flavour, tmp_path):
    """The paths alone are not enough -- editing in place leaves the changed
    SET identical while changing everything the checks would see."""
    root = _repo(tmp_path)
    _run(flavour, root)
    assert _skipped(_run(flavour, root))

    (root / "a.py").write_text("x = 2", encoding="utf-8")
    after = _run(flavour, root)
    assert _ran(after), (
        "the file's CONTENT changed, so the checks must run. " + after.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_failing_run_records_nothing_and_runs_again(flavour, tmp_path):
    """Must-block. A skip after a failure would wave the failing tree through
    for every later turn."""
    failing = {
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 5,
                   "run": ["sh -c 'exit 1'"], "why": "fails"}],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, verify_map=failing)
    first = _run(flavour, root)
    assert first.returncode == 2, first.stderr
    assert not (root / ".crew" / ".verify-gate.fingerprint").exists(), (
        "a failing run must leave no fingerprint marker"
    )

    second = _run(flavour, root)
    assert not _skipped(second), (
        "a failing tree must be re-checked, never skipped. " + second.stderr
    )
    assert second.returncode == 2, second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_budget_deferred_run_records_nothing_and_runs_again(flavour, tmp_path):
    """Must-block, and the subtler half.

    The run PASSED -- exit 0 -- but a rule was deferred by the Stop budget and
    therefore never checked. Recording that as a verified tree would mean the
    deferred rule never runs again on an unchanged tree, so "we ran out of
    budget" would quietly become "this is verified".
    """
    deferring = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-ok"],
             "why": "fits"},
            {"paths": ["a.py"], "seconds": 900, "run": ["echo RAN-huge"],
             "why": "cannot fit"},
        ],
        "default": [], "unmapped": "ignore",
    }
    root = _repo(tmp_path, verify_map=deferring)
    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    assert "deferred to /crew:verify" in first.stderr, first.stderr
    assert not (root / ".crew" / ".verify-gate.fingerprint").exists(), (
        "a run with a deferred rule checked less than everything and must "
        "not be recorded as clean"
    )

    second = _run(flavour, root)
    assert not _skipped(second), (
        "a tree with an unchecked rule must not be skipped. " + second.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_all_never_skips(flavour, tmp_path):
    """/crew:verify's path: it exists to re-run everything, so it must ignore
    the marker as well as the budget."""
    root = _repo(tmp_path)
    _run(flavour, root)
    assert _skipped(_run(flavour, root))

    forced = _run(flavour, root, "--all")
    assert not _skipped(forced), (
        "--all must re-run the map regardless of the fingerprint. "
        + forced.stderr
    )
    assert _ran(forced), forced.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_changing_the_map_or_the_budget_invalidates_the_skip(flavour, tmp_path):
    """verify.json decides WHICH commands run and config.json decides how many
    fit, so both have to move the digest even though neither is a source file."""
    root = _repo(tmp_path)
    _run(flavour, root)
    assert _skipped(_run(flavour, root))

    changed_map = dict(_GREEN)
    changed_map["rules"] = [{"paths": ["a.py"], "seconds": 5,
                             "run": ["echo RAN-ok", "echo RAN-extra"],
                             "why": "a new command"}]
    (root / ".crew" / "verify.json").write_text(json.dumps(changed_map),
                                                encoding="utf-8")
    assert not _skipped(_run(flavour, root)), "a changed verify.json must re-run"

    _run(flavour, root)  # settle, so the next assertion isolates the config
    (root / ".crew" / "config.json").write_text(
        json.dumps({"verify": {"stopBudgetSeconds": 900}}), encoding="utf-8")
    assert not _skipped(_run(flavour, root)), "a changed config.json must re-run"


@pytest.mark.skipif(
    _BASH is None or not sys.platform.startswith("win") or _PWSH is None,
    reason="cross-flavour agreement needs both on the same machine",
)
def test_a_marker_written_by_one_flavour_is_honoured_by_the_other(tmp_path):
    """The point of putting the digest in a shared .py instead of hashing in
    bash and again in PowerShell. If the two ever compute it differently, each
    flavour re-runs everything the other just proved."""
    root = _repo(tmp_path)
    seeded = _run("ps1", root)
    assert seeded.returncode == 0, seeded.stderr

    crossed = _run("sh", root)
    assert _skipped(crossed), (
        "the bash flavour did not recognise the fingerprint the PowerShell "
        "flavour recorded, so the two are computing different digests. "
        + crossed.stderr
    )


# ------------------------------------------------- the digest's own rules

def test_crew_bookkeeping_is_excluded_from_the_digest(tmp_path):
    """Load-bearing, not tidy. The gate writes .verify-verified-at, the
    fingerprint marker and its lock into .crew/, so including that directory
    made every run invalidate the digest it had just recorded -- measured: the
    skip never fired once until this exclusion existed."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / "a.py").write_text("x = 1", encoding="utf-8")

    bare = verify_fingerprint.fingerprint(str(root), ["a.py"])
    noisy = verify_fingerprint.fingerprint(
        str(root), ["a.py", ".crew/.verify-verified-at",
                    ".crew/.verify-gate.fingerprint", ".crew"])
    assert bare == noisy, (
        "crew's own markers moved the digest, so the gate would invalidate "
        "its own skip on every run"
    )


def test_a_deleted_file_moves_the_digest(tmp_path):
    """A missing file is recorded as absent rather than read as empty, or
    deleting an empty file would be invisible to the gate."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    empty = root / "empty.py"
    empty.write_text("", encoding="utf-8")

    present = verify_fingerprint.fingerprint(str(root), ["empty.py"])
    empty.unlink()
    absent = verify_fingerprint.fingerprint(str(root), ["empty.py"])
    assert present != absent, (
        "deleting an empty file left the digest unchanged, so the gate would "
        "skip a turn that removed a file"
    )


def test_content_not_just_paths(tmp_path):
    """The changed SET is identical across an in-place edit; the digest must
    not be."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    target = root / "a.py"

    target.write_text("x = 1", encoding="utf-8")
    before = verify_fingerprint.fingerprint(str(root), ["a.py"])
    target.write_text("x = 2", encoding="utf-8")
    after = verify_fingerprint.fingerprint(str(root), ["a.py"])
    assert before != after, "an in-place edit must move the digest"

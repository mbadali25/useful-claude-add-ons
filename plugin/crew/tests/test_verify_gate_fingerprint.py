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

## The invariant, and why it is tested as one

Every defect found in this digest so far has had the SAME signature: it hashed
something other than what a check would actually read, so Stop exited 0 with
SKIPPED while `--all` exited 2 on one unchanged tree. Two arrived together in
the 0.19.91 review -- the index was not hashed at all, and a path's leading
whitespace was stripped so a different file was hashed -- and they are one
defect wearing two faces rather than two bugs.

So the invariant is asserted directly, over a TABLE of tree states:

> if `--all` FAILS on a tree, a Stop on that same tree must not skip.

`test_a_failing_tree_is_never_skipped_whatever_moved` is that test. It exists
because fixing the two known causes one at a time would leave a third way to
move what a check reads without moving the digest, and nothing would say so.
Each known cause keeps its own named case below as well, so a regression
reports WHICH one came back rather than only that the invariant broke.
"""
import json
import os
import pathlib
import re
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

# ------------------------------------- what the digest must and must not see
#
# Added for the Codex review of 0.19.90. The blanket `.crew/` exclusion, the
# missing file mode, and non-ASCII paths hashing as absent.


def test_the_gates_own_markers_are_still_excluded(tmp_path):
    """MUST-ALLOW for narrowing the exclusion by NAME. The files the gate
    itself writes have to stay out, or every run invalidates the digest it
    just recorded -- measured: the skip never fired once before they were."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / "a.py").write_text("x = 1", encoding="utf-8")

    bare = verify_fingerprint.fingerprint(str(root), ["a.py"])
    with_markers = verify_fingerprint.fingerprint(str(root), [
        "a.py", ".crew/.verify-verified-at", ".crew/.verify-gate.fingerprint",
        ".crew/.verify-gate.lock", ".crew/.verify-gate.lock/token"])
    assert bare == with_markers, (
        "the gate's own markers moved the digest, so it would invalidate its "
        "own skip on every run"
    )


def test_a_mapped_crew_file_is_not_excluded_from_the_digest(tmp_path):
    """MUST-BLOCK for the blanket exclusion. Only the gate's own markers come
    out; any other `.crew/` path a repo maps must be hashed by content."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    mapped = root / ".crew" / "check.txt"

    mapped.write_text("GOOD", encoding="utf-8")
    before = verify_fingerprint.fingerprint(str(root), [".crew/check.txt"])
    mapped.write_text("BAD", encoding="utf-8")
    after = verify_fingerprint.fingerprint(str(root), [".crew/check.txt"])
    assert before != after, (
        "a mapped .crew/ file changed contents without moving the digest, so "
        "the gate would skip verification of it entirely"
    )


def _staged_mode_repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    script = root / "s.sh"
    script.write_text("#!/bin/sh" + chr(10) + "echo hi" + chr(10),
                      encoding="utf-8")
    subprocess.run(("git", "add", "s.sh"), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", "add"), cwd=root, check=True,
                   capture_output=True, text=True)
    return root


def _head(root):
    return subprocess.run(("git", "rev-parse", "HEAD"), cwd=root,
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def test_a_staged_mode_change_moves_the_digest(tmp_path):
    """Bytes alone miss a mode flip.

    A COMMITTED chmod is already caught -- it moves HEAD, which is hashed --
    and this case asserts HEAD did NOT move, so it is testing the staged case
    and not that one by accident. Measured byte-identical before the mode went
    into the digest. Not hypothetical: a script shipped 100644 in this
    marketplace and failed with permission denied on Linux, and a mode-only
    edit is exactly what the skip would wave through.
    """
    root = _staged_mode_repo(tmp_path)
    head_before = _head(root)
    before = verify_fingerprint.fingerprint(str(root), ["s.sh"])

    subprocess.run(("git", "update-index", "--chmod=+x", "s.sh"), cwd=root,
                   check=True, capture_output=True, text=True)

    assert _head(root) == head_before, (
        "this case is about an UNCOMMITTED mode change; if HEAD moved, the "
        "digest would change for the wrong reason and prove nothing"
    )
    after = verify_fingerprint.fingerprint(str(root), ["s.sh"])
    assert before != after, (
        "a staged chmod +x left the digest unchanged, so a check that depends "
        "on the executable bit would be skipped on a tree that just moved it"
    )


def test_a_non_ascii_path_hashes_by_content(tmp_path):
    """Under the default `core.quotePath`, git renders a non-ASCII path as an
    escaped double-quoted string -- measured here, `cafe.txt` with an acute
    comes back as a quoted, octal-escaped name. That string names no real
    file, so it hashed as absent and a later edit kept the passing digest."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    target = root / "café.txt"
    try:
        target.write_text("GOOD", encoding="utf-8")
        target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        pytest.skip("this filesystem cannot hold a non-ASCII filename: "
                    + str(exc))

    before = verify_fingerprint.fingerprint(str(root), ["café.txt"])
    target.write_text("BAD", encoding="utf-8")
    after = verify_fingerprint.fingerprint(str(root), ["café.txt"])
    assert before != after, (
        "editing a non-ASCII path did not move the digest, so it is being "
        "hashed as absent rather than read"
    )


def test_both_gates_list_paths_with_quotepath_disabled():
    """The other half of that fix, asserted at the SOURCE. The quoted form
    reaches the matcher and the scope report too, so it is fixed where the
    paths are produced rather than unquoted downstream.

    Per INVOCATION, not per line, and that distinction is not pedantic: the
    bash flavour puts BOTH git calls on one line, so a line-granular check
    passed while the `diff --name-only` half had lost its flag and only the
    `ls-files` half still carried it. Caught by sabotage -- removing the flag
    from one of the two calls left this green.
    """
    invocation = re.compile(
        r"git\s+((?:-c\s+\S+\s+)*)(diff --name-only|ls-files --others)")
    for name in ("verify-gate.sh", "verify-gate.ps1"):
        path = os.path.join(_ROOT, "hooks", "scripts", name)
        text = pathlib.Path(path).read_text(encoding="utf-8")
        found = 0
        for match in invocation.finditer(text):
            found += 1
            assert "core.quotePath=false" in match.group(1), (
                name + " lists paths without disabling core.quotePath, so a "
                "non-ASCII path arrives quoted and matches no rule: "
                + match.group(0)
            )
        assert found >= 2, (
            "expected both the diff and the ls-files listing in " + name
            + ", found " + str(found)
        )


def test_the_deferred_count_fails_closed_when_the_matcher_cannot_say():
    """The recording predicate's fail-safe, asserted at the source.

    Source-level for the same reason test_verify_gate_rule_framing gives about
    the record separator: no INPUT can produce a matcher that emits a
    malformed fourth record, so a behavioural test cannot reach this branch
    and would pass against a flipped default. Caught by sabotage -- changing
    the fallback from 1 to 0 left every behavioural case green.

    The direction is the whole point. If the count cannot be read, the run
    must be treated as "something was deferred" and the baseline held, never
    as "nothing was deferred" -- an unknown resolving to the permissive value
    is the defect this repository keeps re-finding.
    """
    text = pathlib.Path(
        os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
    ).read_text(encoding="utf-8")
    fallback = [l for l in text.splitlines() if "DEFERRED_COUNT=" in l
                and "*[!0-9]*" in l]
    assert len(fallback) == 1, (
        "expected exactly one non-numeric fallback for DEFERRED_COUNT, got: "
        + repr(fallback)
    )
    assert "DEFERRED_COUNT=1" in fallback[0], (
        "an unreadable deferred count must fail CLOSED (assume a deferral and "
        "hold the baseline). This line resolves it to the permissive value: "
        + fallback[0]
    )


# --------------------------------------------- the invariant, as a property
#
# "If --all FAILS on a tree, a Stop on that same tree must not skip." One
# table, one assertion, every state that has ever broken it plus room for the
# next. See this module's docstring for why it is a property rather than three
# independent regression cases.


def _invariant_repo(tmp_path, name, rule_path, command):
    """A repo whose single rule PASSES, ready to be seeded with a clean run."""
    root = tmp_path / name
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
    (root / ".crew" / "verify.json").write_text(json.dumps({
        "version": 1,
        "rules": [{"paths": [rule_path], "seconds": 1, "run": [command],
                   "why": name}],
        "default": [], "unmapped": "ignore",
    }), encoding="utf-8")
    return root


def _state_worktree_edit(tmp_path):
    """The state the digest has always covered. In the table so it proves the
    harness tests the invariant, and not only the two causes found in 0.19.91.
    """
    root = _invariant_repo(tmp_path, "worktree", "a.txt",
                           "grep -q GOOD a.txt")
    (root / "a.txt").write_text("GOOD", encoding="utf-8")

    def break_it():
        (root / "a.txt").write_text("BAD", encoding="utf-8")
    return root, break_it


def _state_staged_contents(tmp_path):
    """MUST-BLOCK. A check that reads the INDEX -- `git show :a.txt`, and
    every lint that runs off the staged copy -- sees something the working
    tree is free to disagree with. Measured before the fix: Stop exited 0 with
    SKIPPED while --all exited 2 on this exact tree."""
    root = _invariant_repo(tmp_path, "staged", "a.txt",
                           "git show :a.txt | grep -q GOOD")
    (root / "a.txt").write_text("GOOD", encoding="utf-8")
    subprocess.run(("git", "add", "a.txt"), cwd=root, check=True,
                   capture_output=True, text=True)

    def break_it():
        # Stage FAILING contents, then put the PASSING contents back on disk.
        # Every byte the digest used to look at ends up where it was.
        (root / "a.txt").write_text("BAD", encoding="utf-8")
        subprocess.run(("git", "add", "a.txt"), cwd=root, check=True,
                       capture_output=True, text=True)
        (root / "a.txt").write_text("GOOD", encoding="utf-8")
    return root, break_it


_LEADING = " leading.txt"


def _state_leading_space_path(tmp_path):
    """MUST-BLOCK. The digest stripped whitespace off every path handed to it,
    so it hashed `leading.txt` -- which does not exist, and hashes as absent --
    while the rule matched and the check read ` leading.txt`."""
    root = _invariant_repo(tmp_path, "leading", _LEADING,
                           'grep -q GOOD "' + _LEADING + '"')
    target = root / _LEADING
    try:
        target.write_text("GOOD", encoding="utf-8")
        listed = os.listdir(str(root))
    except OSError as exc:
        pytest.skip("MEASURED: this filesystem refused to create a file named "
                    + repr(_LEADING) + " -- " + str(exc))
    if _LEADING not in listed:
        pytest.skip("MEASURED: created " + repr(_LEADING) + " and os.listdir "
                    "returned " + repr(sorted(listed)) + ", so this filesystem "
                    "renames a leading-space filename and the case cannot be "
                    "set up here")

    def break_it():
        target.write_text("BAD", encoding="utf-8")
    return root, break_it


def _submodule_repo(root):
    """An outer repo with a real submodule, or a MEASURED skip.

    `-c protocol.file.allow=always` is not optional: git refuses a `file://`
    submodule by default since the CVE-2022-39253 mitigation, and without it
    `submodule add` fails with "transport \'file\' not allowed" -- which
    reads like the filesystem refusing rather than git\'s own policy.
    """
    inner = root.parent / (root.name + "-inner")
    inner.mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=inner, check=True,
                       capture_output=True, text=True)
    (inner / "a.txt").write_text("good", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "inner")):
        subprocess.run(("git",) + args, cwd=inner, check=True,
                       capture_output=True, text=True)

    added = subprocess.run(
        ("git", "-c", "protocol.file.allow=always", "submodule", "add", "-q",
         "../" + inner.name, "sub"),
        cwd=root, capture_output=True, text=True, check=False)
    if added.returncode != 0 or not (root / "sub" / "a.txt").exists():
        pytest.skip("MEASURED: `git submodule add` exited "
                    + str(added.returncode) + " here -- stderr: "
                    + repr(added.stderr.strip()) + "; sub/a.txt present: "
                    + str((root / "sub" / "a.txt").exists()))
    subprocess.run(("git", "commit", "-q", "-m", "add submodule"), cwd=root,
                   check=True, capture_output=True, text=True)
    # DIRTY, and still passing. Writing back the committed bytes leaves the
    # submodule CLEAN, and a clean submodule is not in `git diff --name-only`
    # at all -- so the rule on `sub` would never match, the seeding run would
    # check nothing, and the later edit would move the digest merely by making
    # a path APPEAR in the changed set. That is the shape this whole module
    # warns about for ordinary files ("editing in place leaves the changed SET
    # identical"), and the submodule fixture walked straight into it: the
    # sabotage entry for the gitlink caught the property-table row STILL GREEN
    # with the fix deleted, and the cause was here, not in the gate.
    #
    # `good and dirty` differs from the committed `good`, so the submodule is
    # dirty from the start, AND it still satisfies `grep -q good` so the
    # seeding run genuinely passes.
    (root / "sub" / "a.txt").write_text("good and dirty", encoding="utf-8")
    changed = subprocess.run(("git", "diff", "--name-only", "HEAD"), cwd=root,
                             capture_output=True, text=True,
                             check=True).stdout.split()
    assert "sub" in changed, (
        "the fixture must leave the submodule DIRTY, or `sub` is not in the "
        "changed set and every case built on it is vacuous. git reported: "
        + repr(changed)
    )
    return root / "sub" / "a.txt"


def _gitlink(root):
    return subprocess.run(("git", "ls-files", "-s", "sub"), cwd=root,
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def _state_submodule_contents(tmp_path):
    """MUST-BLOCK. A gitlink is a DIRECTORY, and `open()` on a directory
    raises -- so the path hashed to the same "absent" constant a deleted file
    gets, and a check reading `sub/a.txt` was skippable by editing
    `sub/a.txt`. The gitlink sha does not move for a dirty submodule, which is
    why nothing looked wrong."""
    root = _invariant_repo(tmp_path, "submodule", "sub",
                           "grep -q good sub/a.txt")
    target = _submodule_repo(root)

    def break_it():
        target.write_text("bad", encoding="utf-8")
    return root, break_it


_STATES = {
    "worktree-edit": _state_worktree_edit,
    "staged-contents": _state_staged_contents,
    "leading-space-path": _state_leading_space_path,
    "submodule-contents": _state_submodule_contents,
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("state", sorted(_STATES))
def test_a_failing_tree_is_never_skipped_whatever_moved(flavour, state,
                                                        tmp_path):
    root, break_it = _STATES[state](tmp_path)

    seed = _run(flavour, root)
    assert seed.returncode == 0, (
        "the fixture must PASS first, or there is no recorded fingerprint for "
        "the rest of this case to be about. " + seed.stderr
    )
    marker = root / ".crew" / ".verify-gate.fingerprint"
    assert marker.exists(), (
        "a clean run must record a fingerprint, or this case proves nothing "
        "about the skip. " + seed.stderr
    )
    recorded = marker.read_text(encoding="utf-8").strip()

    break_it()

    forced = _run(flavour, root, "--all")
    assert forced.returncode == 2, (
        "the invariant's premise: --all must FAIL on this tree, or the case "
        "is not set up. " + forced.stderr
    )

    stopped = _run(flavour, root)
    assert not _skipped(stopped), (
        "--all fails on this tree and Stop skipped it on fingerprint "
        + recorded + ". The digest is hashing something other than what the "
        "check reads, which is the one defect this module is about. "
        + stopped.stderr
    )
    assert stopped.returncode == 2, (
        "having not skipped, Stop must reach the verdict --all reached. "
        + stopped.stderr
    )


# ------------------------------------------- the two causes, at digest level


def test_staged_contents_move_the_digest(tmp_path):
    """The index half of the invariant, without the gate around it.

    HEAD is asserted not to have moved and the working-tree bytes are asserted
    to be back where they were, so this is testing the STAGED copy rather than
    catching a commit or an edit by accident.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    target = root / "a.txt"
    target.write_text("GOOD", encoding="utf-8")
    subprocess.run(("git", "add", "a.txt"), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root,
                   check=True, capture_output=True, text=True)
    head_before = _head(root)
    before = verify_fingerprint.fingerprint(str(root), ["a.txt"])

    target.write_text("BAD", encoding="utf-8")
    subprocess.run(("git", "add", "a.txt"), cwd=root, check=True,
                   capture_output=True, text=True)
    target.write_text("GOOD", encoding="utf-8")

    assert _head(root) == head_before, (
        "this case is about the INDEX; if HEAD moved, the digest would change "
        "for the wrong reason and prove nothing"
    )
    assert target.read_text(encoding="utf-8") == "GOOD", (
        "and about the index ALONE -- the working-tree bytes have to be back "
        "exactly where the passing run left them"
    )
    after = verify_fingerprint.fingerprint(str(root), ["a.txt"])
    assert before != after, (
        "failing contents were staged and the digest did not move, so a check "
        "reading `git show :a.txt` would be skipped on a tree it fails"
    )


def test_the_path_list_is_not_trimmed(tmp_path):
    """The filename half, asserted at main()'s stdin -- which is where the
    trimming was. The digest for ` leading.txt` must not be the digest for
    `leading.txt`; they name different files.

    Run as a SUBPROCESS on purpose. main() is the seam both flavours pipe
    into, and calling fingerprint() directly would skip the parsing that WAS
    the defect -- a test that proves only the reader and never the writer.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / "leading.txt").write_text("BARE", encoding="utf-8")
    script = os.path.join(_ROOT, "hooks", "scripts", "verify_fingerprint.py")

    def digest_for(stdin_text):
        out = subprocess.run((sys.executable, script, str(root)),
                             input=stdin_text, capture_output=True, text=True,
                             check=True)
        return out.stdout.strip()

    spaced = digest_for(_LEADING + chr(10))
    bare = digest_for("leading.txt" + chr(10))
    assert spaced != bare, (
        "the leading space was stripped, so a rule on " + repr(_LEADING)
        + " was checked against the digest of `leading.txt` -- a different "
        "file, and one that hashes as absent when it does not exist"
    )
    assert spaced == verify_fingerprint.fingerprint(str(root), [_LEADING]), (
        "main() and fingerprint() must agree on what the path was, or the "
        "gate and every other case in this module test different things"
    )


# ------------------------------------------------- the submodule, at digest
# level


def test_a_dirty_submodule_moves_the_digest(tmp_path):
    """The gitlink sha is asserted NOT to move, so this is testing the
    submodule's CONTENTS and not catching a `git add` by accident."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    (root / "README.md").write_text("committed", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "fixture")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    target = _submodule_repo(root)

    link_before = _gitlink(root)
    before = verify_fingerprint.fingerprint(str(root), ["sub"])
    # Dirty BEFORE and dirty after, so what moves is the submodule's contents
    # and not its clean/dirty state -- the stronger property, and the one the
    # gate actually depends on.
    target.write_text("bad", encoding="utf-8")

    assert _gitlink(root) == link_before, (
        "this case is about a DIRTY submodule; if the gitlink moved, the "
        "digest would change for the wrong reason and prove nothing"
    )
    after = verify_fingerprint.fingerprint(str(root), ["sub"])
    assert before != after, (
        "the submodule's contents changed and the digest did not, so a check "
        "reading inside it would be skipped on a tree it fails. gitlink="
        + link_before
    )


def test_a_clean_submodule_hashes_the_same_twice(tmp_path):
    """MUST-ALLOW, and load-bearing rather than tidy. Recursing into a
    submodule adds git calls whose output has to be STABLE; if any of it moved
    on its own the digest would differ between two identical turns and the
    skip would never fire again for any repo with a submodule -- which is the
    failure the `.crew/` exclusion had to be written to avoid."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    (root / "README.md").write_text("committed", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-q", "-m", "fixture")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    _submodule_repo(root)

    first = verify_fingerprint.fingerprint(str(root), ["sub"])
    second = verify_fingerprint.fingerprint(str(root), ["sub"])
    assert first == second, (
        "an untouched submodule hashed differently on two consecutive reads, "
        "so the unchanged-turn skip can never fire in a repo that has one"
    )

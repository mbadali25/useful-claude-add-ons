"""scope_report.py: the three defects that made the scope line lie.

REPORT-ONLY. Every case here also asserts the exit status stays 0 where it
runs main(), because scope_report is invoked from two hooks that CAN exit 2
and an exit code leaking out of it would hand this file the blocking-hook
regression obligation it was designed to avoid.

The three defects, each measured before it was fixed:

1. **The ticket was read from one location.** `declared_paths` looked only in
   `.work/tickets/<id>.md`. Jira, ServiceDesk Plus and Obsidian Kanban modes
   keep the ticket at `.work/cache/<id>.md` (commands/work.md step 1), so on
   any repo using one of those trackers -- this one included, its tracker is
   obsidian -- the report said "the ticket file is missing" for a ticket that
   existed.

2. **`_BOOKKEEPING` was a `str.startswith` tuple.** `TODO.md` in it therefore
   swallowed `TODO.mdx` and `TODO.md.py`, dropping real source files out of
   the report as "crew's own bookkeeping".

3. **`fnmatch` has no `**`.** `fnmatch("main.py", "**/*.py")` is False while
   `fnmatch("src/main.py", "**/*.py")` is True, so a ticket declaring
   `**/*.py` had its own root-level files reported OUTSIDE scope. This is the
   one that matters most: a scope line that names in-scope files is how the
   whole feature gets ignored. It is also a PARITY defect -- verify-gate.sh
   embeds a matcher that already handled this, and the report disagreeing with
   the gate that blocks the turn is worse than no report. The parity case at
   the bottom is what keeps the two answering the same question.
"""
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import scope_report

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCOPE_PY = os.path.join(_ROOT, "hooks", "scripts", "scope_report.py")
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")


def _repo(tmp_path, ticket="ABC-1", folder="tickets", touch="- touch: src/"):
    """A repo with an open ticket whose file lives in `folder`."""
    root = tmp_path / "repo"
    (root / ".work" / folder).mkdir(parents=True)
    (root / ".work" / "INDEX.md").write_text(
        "| " + ticket + " | in progress |", encoding="utf-8")
    if touch is not None:
        (root / ".work" / folder / (ticket + ".md")).write_text(
            "## Scope" + chr(10) + touch + chr(10), encoding="utf-8")
    return root


def _run(root, changed):
    """Drive the real script the way the gates drive it."""
    return subprocess.run(
        [sys.executable, _SCOPE_PY, str(root)],
        input=chr(10).join(changed), capture_output=True, text=True,
        check=False,
    )


# --------------------------------------------------------------- defect 1

@pytest.mark.parametrize("folder", ["tickets", "cache"])
def test_the_ticket_is_found_in_either_location(tmp_path, folder):
    """Must-allow. `cache` is the location every non-files tracker uses, so
    reading only `tickets` made the report useless on this repo."""
    root = _repo(tmp_path, folder=folder, touch="- touch: src/")
    assert scope_report.declared_paths(str(root), "ABC-1") == ["src/"]


def test_a_ticket_in_cache_is_not_reported_as_missing(tmp_path):
    root = _repo(tmp_path, folder="cache", touch="- touch: src/")
    result = _run(root, ["src/a.py"])
    assert result.returncode == 0
    assert "is missing" not in result.stderr, result.stderr
    assert "at neither" not in result.stderr, (
        "the ticket is in .work/cache and must be found there. " + result.stderr
    )


def test_a_ticket_in_no_location_still_says_so_and_names_both(tmp_path):
    """The unknown must stay an unknown, and must name both places it looked
    -- otherwise the reader checks the one path in the message, finds the
    ticket absent from it, and never learns the other was searched too."""
    root = _repo(tmp_path, folder="tickets", touch=None)
    assert scope_report.declared_paths(str(root), "ABC-1") is scope_report.MISSING
    result = _run(root, ["src/a.py"])
    assert result.returncode == 0
    assert ".work/tickets/ABC-1.md" in result.stderr, result.stderr
    assert ".work/cache/ABC-1.md" in result.stderr, result.stderr


# --------------------------------------------------------------- defect 2

def test_bookkeeping_excludes_the_exact_file_only():
    assert scope_report.bookkeeping("TODO.md")
    assert scope_report.bookkeeping(".work/INDEX.md")
    assert scope_report.bookkeeping(".crew/verify.json")


@pytest.mark.parametrize("path", ["TODO.mdx", "TODO.md.py", "TODO.market.md"])
def test_a_file_merely_starting_with_todo_md_is_not_bookkeeping(path):
    """Must-block for the str.startswith defect. Both of the first two were
    measured True before the fix, so a real source file could vanish from the
    report by being named close enough to the bookkeeping file."""
    assert not scope_report.bookkeeping(path), (
        path + " was excluded as bookkeeping; str.startswith('TODO.md') "
        "swallows anything with that prefix"
    )


def test_a_todo_lookalike_reaches_the_report(tmp_path):
    root = _repo(tmp_path, touch="- touch: src/")
    result = _run(root, ["TODO.md", "TODO.mdx"])
    assert result.returncode == 0
    # Assert on the LIST line only. The advisory paragraph underneath names
    # TODO.md itself ("these belong in TODO.md with a reason"), so a substring
    # test over the whole of stderr matches the wrong thing.
    # The fixture is not a git repository, so since 0.19.95 the line also
    # carries the "(this turn only: ...)" marker; that marker is
    # test_scope_base.py's to assert, the list is this test's.
    listed = result.stderr.splitlines()[0].split(" (this turn only:")[0]
    assert listed == "outside-scope: TODO.mdx", (
        "TODO.mdx must reach the report and the real TODO.md must not. "
        + result.stderr
    )


# --------------------------------------------------------------- defect 3

@pytest.mark.parametrize("path", ["main.py", "src/main.py", "a/b/c/main.py"])
def test_a_double_star_glob_covers_the_repository_root(path):
    """Must-allow, and the important one. A ticket declaring `**/*.py` means
    every .py file; before the fix the root-level ones were reported OUTSIDE
    the scope the ticket had just declared."""
    assert scope_report.matches(path, "**/*.py"), (
        path + " fell outside `**/*.py`. fnmatch's * spans '/', so the "
        "'**/'-stripped form has to be tested as well"
    )


def test_a_root_level_file_is_not_reported_outside_its_declared_scope(tmp_path):
    root = _repo(tmp_path, touch="- touch: **/*.py")
    result = _run(root, ["main.py", "src/deep.py"])
    assert result.returncode == 0
    # The LIST line. Since 0.19.95 a `scope-base:` line follows it (here
    # saying the ticket-wide diff was unavailable: the fixture is not a git
    # repository), and that line is test_scope_base.py's to assert.
    assert result.stderr.splitlines()[0].startswith("outside-scope: (this turn only:"), (
        "both files are inside `**/*.py`, and the fixture is not a git "
        "repository so the line must say the list is this turn's only. "
        + result.stderr
    )


def test_something_genuinely_outside_is_still_reported(tmp_path):
    """The other half: the fix must not turn the report into a rubber stamp."""
    root = _repo(tmp_path, touch="- touch: **/*.py")
    result = _run(root, ["main.py", "docs/guide.md"])
    assert result.returncode == 0
    assert "docs/guide.md" in result.stderr, result.stderr
    assert "main.py" not in result.stderr, result.stderr


# ----------------------------------------------------------------- parity

def _gate_matcher():
    """The `matches` function verify-gate.sh actually runs, lifted out of the
    python heredoc it embeds and compiled here.

    Read from the script rather than restated, so this test cannot pass
    against a gate that has since changed. If the extraction fails the test
    fails loudly -- a parity check that silently stops checking is the defect
    it exists to catch.
    """
    src = pathlib.Path(_VERIFY_SH).read_text(encoding="utf-8")
    start = src.find("def matches(path, pat):")
    assert start != -1, (
        "could not find `def matches` in verify-gate.sh. If the gate's "
        "matcher moved or was renamed, this parity check is no longer "
        "checking anything -- re-point it rather than deleting it."
    )
    end = src.find("cmds, unmatched", start)
    assert end != -1, "could not find the end of the gate's matcher"
    namespace = {}
    exec(compile(src[start:end], _VERIFY_SH, "exec"),  # pylint: disable=exec-used
         {"fnmatch": __import__("fnmatch")}, namespace)
    return namespace["matches"]


_CASES = [
    ("main.py", "**/*.py"),
    ("src/main.py", "**/*.py"),
    ("a/b/c.py", "**/*.py"),
    ("main.py", "*.py"),
    ("plugin/crew/x.sh", "plugin/**/*.sh"),
    ("plugin/x.sh", "plugin/**/*.sh"),
    ("docs/guide.md", "**/*.py"),
    ("src/a.py", "src/"),
    ("README.md", "README.md"),
    ("a/b/c/d.tf", "**/*.tf"),
    ("d.tf", "**/*.tf"),
]


def test_the_report_matcher_agrees_with_the_gate_it_reports_alongside():
    """scope_report.gate_matches is a hand-copy of the gate's matcher, and a
    hand-copy with no guard is this repo's most repeated defect. Behavioural
    parity over a case table rather than a text compare, so a comment edit in
    either copy does not fail, but a semantic drift does."""
    gate = _gate_matcher()
    for path, pat in _CASES:
        assert scope_report.gate_matches(path, pat) == gate(path, pat), (
            "scope_report and verify-gate.sh disagree about whether " + path +
            " falls under " + pat + ". The report would then name files the "
            "gate considers in scope, or stay silent about ones it does not."
        )


def test_the_report_is_a_superset_of_the_gate_never_the_reverse():
    """scope_report.matches adds the bare-directory forms a hand-written
    `- touch:` line uses. That widening is only safe in one direction: it may
    call MORE things in-scope than the gate, never fewer, so it can never
    invent a scope violation the gate would not also see."""
    gate = _gate_matcher()
    for path, pat in _CASES:
        if gate(path, pat):
            assert scope_report.matches(path, pat), (
                "the gate matches " + path + " against " + pat +
                " but the report does not -- the report would name a file as "
                "outside scope that the gate considers covered"
            )

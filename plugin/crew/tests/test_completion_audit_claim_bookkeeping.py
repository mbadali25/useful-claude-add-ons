"""T-0046: the completion audit (Stop and `/crew:done`) drops a
`plugin/*/BUDGETS.md` change from the Touch check only when it is a re-measure
of the `crew-markdown-lines` claim number by an approved ticket, judged by
`crew_bookkeeping.claim_numbers_only` from the base blob and the file on disk.
A BLOCKING hook, so must-block and must-allow cases both, on throwaway
repositories.

Anything the audit cannot read -- no base blob (an added file, the new end of
a rename), a deleted or undecodable working file, a git call that fails -- is
not dropped, and Touch decides as it did before. `sabotage_bookkeeping.py`
breaks each refusing branch and the matching case here goes red.
"""
import importlib.util
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
from review_fixtures import git
from scope_fixtures import SCRIPTS, approve_as_user, make_repo, make_ticket, ready
from test_crew_bookkeeping import BUDGETS, CHECKER

REL = "plugin/crew/BUDGETS.md"
OLD, NEW = "18,176 lines across 121 files", "18,200 lines across 122 files"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = make_repo(tmp_path, mode="block")
    _write(root, REL, BUDGETS)
    _write(root, "src/notes.md", BUDGETS)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "budgets")
    return root


def _path(repo, rel):
    return repo.joinpath(*rel.split("/"))


def _write(repo, rel, text):
    path = _path(repo, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _edit(repo, old, new, rel=REL):
    with open(_path(repo, rel), encoding="utf-8", newline="") as fh:
        text = fh.read()
    assert text.count(old) == 1, old
    _write(repo, rel, text.replace(old, new))


def _commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change")


def _fails_on(repo, rel):
    ok, lines = completion_audit.audit(str(repo), "T-1")
    return ok, rel in "\n".join(lines), lines


def _record_base(repo):
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "scope_base.py"), "--root",
                    str(repo), "--record", "T-1"], check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


# --- must-block -----------------------------------------------------------------

def test_prose_committed(repo):
    ready(repo)
    _edit(repo, "currently totals", "now totals")
    _commit(repo)

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named) == (False, True), lines


def test_number_and_prose(repo):
    ready(repo)
    _edit(repo, OLD, NEW)
    _edit(repo, "currently totals", "now totals")

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named) == (False, True), lines


def test_added(repo):
    ready(repo)
    _write(repo, "plugin/other/BUDGETS.md", BUDGETS)

    ok, named, lines = _fails_on(repo, "plugin/other/BUDGETS.md")

    assert (ok, named) == (False, True), lines


def test_added_empty(repo):
    """The neighbour of `added`: an empty new BUDGETS.md. Read as an empty
    base, it would be `unchanged` and pass."""
    ready(repo)
    _write(repo, "plugin/other/BUDGETS.md", "")

    ok, named, lines = _fails_on(repo, "plugin/other/BUDGETS.md")

    assert (ok, named) == (False, True), lines


def test_mode_change(repo):
    """The text is identical and git still reports a change."""
    ready(repo)
    os.chmod(_path(repo, REL), 0o755)

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named) == (False, True), lines


def test_deleted(repo):
    ready(repo)
    _path(repo, REL).unlink()

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named) == (False, True), lines


def test_renamed_in(repo):
    """`src/notes.md` (in Touch, same text) moves onto a BUDGETS.md absent at
    base, with a numbers-only edit. The new end has no base blob."""
    ready(repo)
    (repo / "plugin" / "other").mkdir(parents=True)
    git(repo, "mv", "src/notes.md", "plugin/other/BUDGETS.md")
    _edit(repo, OLD, NEW, rel="plugin/other/BUDGETS.md")

    ok, named, lines = _fails_on(repo, "plugin/other/BUDGETS.md")

    assert (ok, named) == (False, True), lines


def test_unapproved(repo):
    make_ticket(repo)
    _record_base(repo)
    _edit(repo, OLD, NEW)

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named, "not approved" in "\n".join(lines)) == (False, True, True), lines


def test_base_blob_unreadable(repo, monkeypatch):
    ready(repo)
    _edit(repo, OLD, NEW)
    real = completion_audit._git_fields  # pylint: disable=protected-access

    def failing(top, args, data=None, literal=False):
        if args[0] == "cat-file":
            raise RuntimeError("git cat-file failed (128): fatal: stubbed")
        return real(top, args, data=data, literal=literal)

    monkeypatch.setattr(completion_audit, "_git_fields", failing)

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named) == (False, True), lines


def test_undecodable_working_file(repo):
    ready(repo)
    with open(_path(repo, REL), "ab") as fh:
        fh.write(b"\xff\xfe\n")

    ok, named, lines = _fails_on(repo, REL)

    assert (ok, named) == (False, True), lines


# --- must-allow -----------------------------------------------------------------

def test_number_only_committed(repo):
    ready(repo)
    _edit(repo, OLD, NEW)
    _commit(repo)

    assert completion_audit.audit(str(repo), "T-1") == (True, [])


def test_number_only_uncommitted(repo):
    ready(repo)
    _edit(repo, OLD, NEW)

    assert completion_audit.audit(str(repo), "T-1") == (True, [])


def test_number_only_passes_the_check_cli(repo):
    ready(repo)
    _edit(repo, OLD, NEW)

    done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "completion_audit.py"),
                           "--check", "--ticket", "T-1", "--root", str(repo)],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False)

    assert done.returncode == 0, done.stdout + done.stderr


def _real_total(repo):
    """`count_crew_markdown_lines` from scripts/check-marketplace.py, run
    against the fixture: the number the gate itself would demand."""
    if not os.path.isfile(CHECKER):
        pytest.skip("scripts/check-marketplace.py is absent - this case was NOT run")
    spec = importlib.util.spec_from_file_location("check_marketplace_fixture", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = str(repo)
    listed = module._tracked_files("plugin/crew/*.md")  # pylint: disable=protected-access
    return module.count_crew_markdown_lines(), len(listed)


def test_docs_ticket_remeasures(repo):
    """The T-0023 shape: a new plugin/crew command in Touch, and the claim
    re-measured to the real total without BUDGETS.md in Touch."""
    make_ticket(repo, touch=("plugin/crew/commands/new.md",),
                files=["plugin/crew/commands/new.md"])
    approve_as_user(repo)
    _record_base(repo)
    _write(repo, "plugin/crew/commands/new.md", "# new\n\nA new command.\n")
    git(repo, "add", "-A")
    total, files = _real_total(repo)
    _edit(repo, OLD, f"{total:,} lines across {files} files")
    _commit(repo)

    assert completion_audit.audit(str(repo), "T-1") == (True, [])

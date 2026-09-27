"""T-0046: the scope guard lets an approved ticket re-measure the
`crew-markdown-lines` claim in `plugin/*/BUDGETS.md` without that file in its
Touch, and refuses every other write to it. A BLOCKING PreToolUse hook, so
must-block and must-allow cases both, run through the module and (as `slow`)
the bash and PowerShell wrappers. The ps1 flavour runs only where pwsh is
installed, and says so when it skips.

The after-text is computed from the tool call itself -- Write's `content`,
Edit's one exact replacement, MultiEdit's edits in order -- and judged by
`crew_bookkeeping.claim_numbers_only` against the file on disk. A call whose
after-text cannot be computed exactly is not exempt and falls through to the
Touch check. `sabotage_bookkeeping.py` breaks each refusing branch and the
matching case here goes red.
"""
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
import pytest
from review_fixtures import git
from scope_fixtures import FLAVOUR_MATRIX, make_repo, make_ticket, ready, run_hook
from test_crew_bookkeeping import BUDGETS

REL = "plugin/crew/BUDGETS.md"
OLD, NEW = "18,176 lines across 121 files", "18,200 lines across 122 files"
TOUCH_ERR = f"{REL} is outside T-1's spec ## Touch"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = make_repo(tmp_path, mode="block")
    path = root / "plugin" / "crew" / "BUDGETS.md"
    path.parent.mkdir(parents=True)
    path.write_text(BUDGETS + "\nLast measured: 18,176.\n", encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "budgets")
    return root


def _guard(flavour, root, payload):
    return run_hook(flavour, "scope_guard", payload, root)


def _call(root, tool, rel=REL, **tool_input):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    tool_input[key] = str(root.joinpath(*rel.split("/")))
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
            "cwd": str(root)}


def _text(root, rel=REL):
    with open(root.joinpath(*rel.split("/")), encoding="utf-8", newline="") as fh:
        return fh.read()


def _number_edit(root):
    return _call(root, "Edit", old_string=OLD, new_string=NEW)


# --- must-block -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_prose_edit_write(flavour, repo):
    ready(repo)
    after = _text(repo).replace("currently totals", "now totals")

    code, _, err = _guard(flavour, repo, _call(repo, "Write", content=after))

    assert (code, TOUCH_ERR in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_prose_edit_edit(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Edit", old_string="currently totals",
                                               new_string="now totals"))

    assert (code, TOUCH_ERR in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_unapproved(flavour, repo):
    make_ticket(repo)

    code, _, err = _guard(flavour, repo, _number_edit(repo))

    assert (code, "no approved plan" in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_stale_approval(flavour, repo):
    ready(repo)
    plan = repo / ".work" / "tickets" / "T-1" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\n## Step 2\nMore.\n",
                    encoding="utf-8")

    code, _, err = _guard(flavour, repo, _number_edit(repo))

    assert (code, "plan.md changed since approval" in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_cli_receipt_without_allow_cli_approval(flavour, repo):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="session")

    code, _, err = _guard(flavour, repo, _number_edit(repo))

    assert (code, "/crew:approve T-1" in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_edit_old_string_missing(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Edit", old_string="18,999 lines",
                                               new_string="18,200 lines"))

    assert (code, TOUCH_ERR in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_edit_old_string_ambiguous(flavour, repo):
    """`18,176` is on the bound line and on the last line. Replacing only the
    first would be a numbers-only change; the Edit tool refuses a non-unique
    old_string without replace_all, so the after-text is unknown."""
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Edit", old_string="18,176",
                                               new_string="18,200"))

    assert (code, TOUCH_ERR in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_replace_all_reaching_an_unbound_line(flavour, repo):
    """The neighbour of the ambiguous case: with replace_all both copies
    change, and the second is on a line no marker binds."""
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Edit", old_string="18,176",
                                               new_string="18,200", replace_all=True))

    assert (code, TOUCH_ERR in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_multiedit_one_prose_edit(flavour, repo):
    ready(repo)
    edits = [{"old_string": "18,176 lines", "new_string": "18,200 lines"},
             {"old_string": "currently totals", "new_string": "now totals"}]

    code, _, err = _guard(flavour, repo, _call(repo, "MultiEdit", edits=edits))

    assert (code, TOUCH_ERR in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_notebookedit(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "NotebookEdit", new_source="18,200"))

    assert (code, TOUCH_ERR in err) == (2, True), err


def _link(repo, name, target):
    path = repo.joinpath(*name.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(os.path.relpath(repo.joinpath(*target.split("/")), path.parent), path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks cannot be made here ({exc}) - this case was NOT run")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_symlink_named_budgets(flavour, repo):
    """`plugin/crew/BUDGETS.md` is a link to `docs/policy.md`, which holds the
    same text and is outside Touch. A numbers-only edit through the link would
    write the policy file."""
    (repo / "docs").mkdir()
    os.replace(repo / "plugin" / "crew" / "BUDGETS.md", repo / "docs" / "policy.md")
    _link(repo, REL, "docs/policy.md")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "link")
    ready(repo)

    code, _, err = _guard(flavour, repo, _number_edit(repo))

    assert (code, "outside T-1's spec ## Touch" in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_symlink_to_budgets(flavour, repo):
    """The neighbour: `docs/alias.md` is a link to the real BUDGETS.md. The
    named path is not a BUDGETS.md, so the write needs Touch."""
    _link(repo, "docs/alias.md", REL)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "alias")
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Edit", rel="docs/alias.md",
                                               old_string=OLD, new_string=NEW))

    assert (code, "outside T-1's spec ## Touch" in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_new_budgets_file(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Write", rel="plugin/other/BUDGETS.md",
                                               content=BUDGETS))

    assert (code, "plugin/other/BUDGETS.md is outside T-1's spec ## Touch" in err) == (
        2, True), err


# --- must-allow -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_number_edit_edit(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo, _number_edit(repo))

    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_number_edit_write(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo, _call(repo, "Write",
                                               content=_text(repo).replace(OLD, NEW)))

    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_number_edit_multiedit(flavour, repo):
    ready(repo)
    edits = [{"old_string": "18,176 lines", "new_string": "18,200 lines"},
             {"old_string": "121 files", "new_string": "122 files"}]

    code, _, err = _guard(flavour, repo, _call(repo, "MultiEdit", edits=edits))

    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_budgets_in_touch_prose(flavour, repo):
    ready(repo, touch=("src/**", REL))

    code, _, err = _guard(flavour, repo, _call(repo, "Edit", old_string="currently totals",
                                               new_string="now totals"))

    assert code == 0, err

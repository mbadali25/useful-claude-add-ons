"""scope_guard.py and its .sh / .ps1 wrappers: the PreToolUse plan-approval +
scope guard. A BLOCKING hook, so every rule has a must-block and a must-allow
case, and each runs through the module, the bash wrapper and the PowerShell
wrapper (pwsh with OS=Windows_NT; skipped, and said so, without pwsh).

Each rule was sabotaged by hand -- see sabotage_scope.py for the mutations.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
from scope_fixtures import (FLAVOURS, common_dir, edit, make_repo, make_ticket, ready,
                            run_hook)

pytestmark = pytest.mark.parametrize("flavour", FLAVOURS)


def _guard(flavour, root, payload):
    return run_hook(flavour, "scope_guard", payload, root)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


# --- must-block -----------------------------------------------------------------

def test_edit_with_no_approved_plan_is_blocked(flavour, repo):
    make_ticket(repo)

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, "no approved plan" in err) == (2, True)


def test_edit_after_the_spec_changed_is_blocked_as_stale(flavour, repo):
    ready(repo)
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n- `other/**`\n", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, "spec.md changed since approval" in err) == (2, True)


def test_edit_after_the_plan_changed_is_blocked_as_stale(flavour, repo):
    ready(repo)
    plan = repo / ".work" / "tickets" / "T-1" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py"))

    assert (code, "plan.md changed since approval" in err) == (2, True)


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_a_path_outside_touch_is_blocked_for_every_editing_tool(flavour, repo, tool):
    ready(repo)

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py", tool))

    assert (code, "outside T-1's spec ## Touch" in err) == (2, True)


def test_a_relative_path_outside_touch_is_blocked(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, "other/keep.py"))

    assert code == 2


def test_a_symlink_inside_touch_pointing_out_of_scope_is_blocked(flavour, repo):
    ready(repo)
    os.symlink(repo / "secret" / "x.py", repo / "src" / "link.py")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "link.py"))

    assert (code, "secret/x.py" in err) == (2, True)


def test_a_symlink_outside_touch_pointing_into_scope_is_blocked(flavour, repo):
    ready(repo)
    os.symlink(repo / "src" / "app.py", repo / "other" / "link.py")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "link.py"))

    assert (code, "other/link.py" in err) == (2, True)


def test_a_symlinked_directory_into_scope_does_not_launder_an_outside_name(flavour, repo):
    ready(repo)
    os.symlink(repo / "src", repo / "other" / "srcdir")

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "other" / "srcdir" / "new.py"))

    assert code == 2


def test_dotdot_traversal_out_of_touch_is_blocked(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo,
                          edit(repo, str(repo / "src") + "/../secret/x.py", "Edit"))

    assert (code, "secret/x.py" in err) == (2, True)


def test_dotdot_through_a_symlink_resolves_where_the_os_does(flavour, repo):
    ready(repo)
    (repo / "secret" / "deep").mkdir()
    os.symlink(repo / "secret" / "deep", repo / "src" / "hop")

    code, _, _ = _guard(flavour, repo, edit(repo, str(repo / "src" / "hop") + "/../x.py"))

    assert code == 2


@pytest.mark.parametrize("rel", [
    ("crew", "tickets", "T-1", "approval.json"),
    ("crew", "review", "T-1.json"),
    ("crew", "active-ticket"),
    ("crew", "scope-tickets.json"),
])
def test_writes_to_approval_and_ledger_state_are_blocked(flavour, repo, rel):
    ready(repo)

    code, _, err = _guard(flavour, repo, edit(repo, os.path.join(common_dir(repo), *rel)))

    assert (code, "approval/ledger state" in err) == (2, True)


def test_approval_state_is_blocked_even_in_report_mode(flavour, tmp_path):
    root = make_repo(tmp_path, mode="report")
    ready(root)
    target = os.path.join(common_dir(root), "crew", "tickets", "T-1", "approval.json")

    code, _, _ = _guard(flavour, root, edit(root, target, "Edit"))

    assert code == 2


def test_approval_state_is_blocked_with_no_active_ticket(flavour, repo):
    target = os.path.join(common_dir(repo), "crew", "tickets", "T-9", "approval.json")

    code, _, _ = _guard(flavour, repo, edit(repo, target))

    assert code == 2


def test_the_scope_base_record_is_blocked(flavour, repo):
    ready(repo, touch=(".crew/**", "src/**"))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".crew" / ".scope-base"))

    assert code == 2


@pytest.mark.parametrize("rel", [".crew/config.json", "TODO.md", ".claude/settings.json",
                                 ".work/INDEX.md", ".work/tickets/T-2/spec.md"])
def test_crew_policy_and_bookkeeping_files_have_no_blanket_exemption(flavour, repo, rel):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / rel))

    assert code == 2


def test_the_git_directory_is_never_in_scope(flavour, repo):
    ready(repo, touch=("**",))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".git" / "hooks" / "pre-commit"))

    assert code == 2


def test_a_payload_naming_no_path_is_blocked(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, {"tool_name": "Write", "tool_input": {},
                                        "cwd": str(repo)})

    assert code == 2


def test_an_unparseable_payload_under_block_is_refused(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, b"{not json")

    assert code == 2


def test_a_corrupt_config_fails_closed(flavour, repo):
    ready(repo)
    (repo / ".crew" / "config.json").write_text("{", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert (code, "does not parse" in err) == (2, True)


def test_block_messages_stay_within_six_lines(flavour, repo):
    ready(repo)

    _, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert 1 <= len(err.strip().splitlines()) <= 6


# --- must-allow -------------------------------------------------------------------

def test_an_in_scope_edit_with_an_approved_plan_is_allowed(flavour, repo):
    ready(repo)

    code, out, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, out, err) == (0, "", "")


def test_a_new_file_inside_touch_is_allowed(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "src" / "deep" / "new.py"))

    assert code == 0


@pytest.mark.parametrize("name", ["spec.md", "plan.md", "notes.md"])
def test_the_tickets_own_files_are_allowed_even_unapproved(flavour, repo, name):
    make_ticket(repo)

    code, _, _ = _guard(flavour, repo,
                        edit(repo, repo / ".work" / "tickets" / "T-1" / name, "Edit"))

    assert code == 0


def test_mode_off_allows_everything(flavour, tmp_path):
    root = make_repo(tmp_path, mode="off")
    make_ticket(root)

    code, out, err = _guard(flavour, root, edit(root, root / "other" / "keep.py"))

    assert (code, out, err) == (0, "", "")


def test_no_scope_key_is_off(flavour, tmp_path):
    root = make_repo(tmp_path, mode=None)
    make_ticket(root)

    code, _, _ = _guard(flavour, root, edit(root, root / "other" / "keep.py"))

    assert code == 0


def test_report_mode_allows_logs_and_says_so(flavour, tmp_path):
    root = make_repo(tmp_path, mode="report")
    ready(root)

    code, out, _ = _guard(flavour, root, edit(root, root / "other" / "keep.py"))
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")

    assert code == 0
    assert "would block" in json.loads(out)["systemMessage"]
    assert "\tscope\treport\treport\tT-1\t" in log


def test_no_active_ticket_is_allowed(flavour, repo):
    make_ticket(repo, activate=False)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert code == 0


def test_a_tool_that_does_not_edit_is_not_judged(flavour, repo):
    make_ticket(repo)

    code, _, _ = _guard(flavour, repo, {"tool_name": "Bash",
                                        "tool_input": {"command": "ls"}, "cwd": str(repo)})

    assert code == 0


def test_a_path_outside_the_worktree_is_not_a_repository_path(flavour, repo, tmp_path):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, tmp_path / "scratch" / "notes.md"))

    assert code == 0


# --- the ramp: report for the first ten tickets, then block --------------------------

def test_auto_reports_for_the_first_ten_tickets_then_blocks(flavour, tmp_path):
    root = make_repo(tmp_path, mode="auto")
    for number in range(1, 11):
        make_ticket(root, f"T-{number}", activate=False)
        crew_ticket.approve(str(root), f"T-{number}", by="tester")
    ready(root, "T-11")
    crew_ticket.activate(str(root), "T-10")
    tenth = _guard(flavour, root, edit(root, root / "other" / "keep.py"))[0]
    crew_ticket.activate(str(root), "T-11")

    eleventh = _guard(flavour, root, edit(root, root / "other" / "keep.py"))[0]

    assert (tenth, eleventh) == (0, 2)

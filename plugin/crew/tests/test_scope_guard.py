"""scope_guard.py and its .sh / .ps1 wrappers: the PreToolUse plan-approval +
scope guard. A BLOCKING hook, so every rule has a must-block and a must-allow
case, and each runs through the module, the bash wrapper and the PowerShell
wrapper (pwsh with OS=Windows_NT; skipped, and said so, without pwsh).

Each rule was sabotaged by hand -- see sabotage_scope.py for the mutations.
"""
import json
import os
import pathlib

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
from scope_fixtures import (FLAVOUR_MATRIX, FLAVOURS, common_dir, edit, make_repo,
                            make_ticket, ready, run_hook)

# Every test runs the module flavour by default. Five run `sh` and `ps1` by
# default too -- the per-shell parity sample: a block, an allow, a malformed
# payload refused, mode off, and report mode's message on stdout. Every other
# test's shell flavours are `slow` (FLAVOUR_MATRIX; see conftest.py).


def _guard(flavour, root, payload):
    return run_hook(flavour, "scope_guard", payload, root)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


# --- must-block -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_edit_with_no_approved_plan_is_blocked(flavour, repo):
    make_ticket(repo)

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, "no approved plan" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_edit_after_the_spec_changed_is_blocked_as_stale(flavour, repo):
    ready(repo)
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n- `other/**`\n", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, "spec.md changed since approval" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_edit_after_the_plan_changed_is_blocked_as_stale(flavour, repo):
    ready(repo)
    plan = repo / ".work" / "tickets" / "T-1" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py"))

    assert (code, "plan.md changed since approval" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_a_path_outside_touch_is_blocked_for_every_editing_tool(flavour, repo, tool):
    ready(repo)

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py", tool))

    assert (code, "outside T-1's spec ## Touch" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_relative_path_outside_touch_is_blocked(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, "other/keep.py"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_symlink_inside_touch_pointing_out_of_scope_is_blocked(flavour, repo):
    ready(repo)
    os.symlink(repo / "secret" / "x.py", repo / "src" / "link.py")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "link.py"))

    assert (code, "secret/x.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_symlink_outside_touch_pointing_into_scope_is_blocked(flavour, repo):
    ready(repo)
    os.symlink(repo / "src" / "app.py", repo / "other" / "link.py")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "link.py"))

    assert (code, "other/link.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_symlinked_directory_into_scope_does_not_launder_an_outside_name(flavour, repo):
    ready(repo)
    os.symlink(repo / "src", repo / "other" / "srcdir")

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "other" / "srcdir" / "new.py"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_dotdot_traversal_out_of_touch_is_blocked(flavour, repo):
    ready(repo)

    code, _, err = _guard(flavour, repo,
                          edit(repo, str(repo / "src") + "/../secret/x.py", "Edit"))

    assert (code, "secret/x.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_dotdot_through_a_symlink_resolves_where_the_os_does(flavour, repo):
    # The title is literal, not just flavour text: `role_write_guard.
    # _resolve_real_target` (which this guard reuses) is DELIBERATELY
    # platform-dependent here, and its own module docstring plus
    # test_role_write_guard.py's `@needs_windows` cases
    # (test_resolve_real_target_windows_collapses_dotdot_before_symlink,
    # test_windows_link_pointing_out_of_scope_with_dotdot_still_allows_bash)
    # already establish the Windows answer for this exact shape. POSIX
    # resolves the symlink FIRST, so `src/hop/../x.py` (hop -> secret/deep)
    # pops against the RESOLVED secret/deep, landing in secret/x.py -- out
    # of the ticket's src/** scope, block. Windows collapses the literal
    # `..` LEXICALLY first, before the symlink is ever consulted, so
    # `hop/..` cancels back to `src` without following it at all, landing
    # in src/x.py -- still in scope, allow. A single cross-platform
    # `assert code == 2` was asserting the POSIX answer on both hosts.
    ready(repo)
    (repo / "secret" / "deep").mkdir()
    os.symlink(repo / "secret" / "deep", repo / "src" / "hop")

    code, _, _ = _guard(flavour, repo, edit(repo, str(repo / "src" / "hop") + "/../x.py"))

    assert code == (0 if os.name == "nt" else 2)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
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


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_approval_state_is_blocked_even_in_report_mode(flavour, tmp_path):
    root = make_repo(tmp_path, mode="report")
    ready(root)
    target = os.path.join(common_dir(root), "crew", "tickets", "T-1", "approval.json")

    code, _, _ = _guard(flavour, root, edit(root, target, "Edit"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_approval_state_is_blocked_with_no_active_ticket(flavour, repo):
    target = os.path.join(common_dir(repo), "crew", "tickets", "T-9", "approval.json")

    code, _, _ = _guard(flavour, repo, edit(repo, target))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_the_scope_base_record_is_blocked(flavour, repo):
    ready(repo, touch=(".crew/**", "src/**"))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".crew" / ".scope-base"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("rel", [".crew/config.json", "TODO.md", ".claude/settings.json",
                                 ".work/INDEX.md", ".work/tickets/T-2/spec.md"])
def test_crew_policy_and_bookkeeping_files_have_no_blanket_exemption(flavour, repo, rel):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / rel))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_the_git_directory_is_never_in_scope(flavour, repo):
    ready(repo, touch=("**",))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".git" / "hooks" / "pre-commit"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_payload_naming_no_path_is_blocked(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, {"tool_name": "Write", "tool_input": {},
                                        "cwd": str(repo)})

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_unparseable_payload_under_block_is_refused(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, b"{not json")

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_corrupt_config_fails_closed(flavour, repo):
    ready(repo)
    (repo / ".crew" / "config.json").write_text("{", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert (code, "does not parse" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_block_messages_stay_within_six_lines(flavour, repo):
    ready(repo)

    _, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert 1 <= len(err.strip().splitlines()) <= 6


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_cli_approval_does_not_open_touch(flavour, repo):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="session")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, "/crew:approve T-1" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("entry", ["T-404", 7])
def test_a_pointer_to_a_missing_ticket_is_refused_not_ignored(flavour, repo, entry):
    make_ticket(repo, "T-3", activate=False)
    (repo / ".work" / "INDEX.md").write_text("- T-3 in progress\n", encoding="utf-8")
    pointer = pathlib.Path(common_dir(repo), "crew", "active-ticket")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({crew_ticket.toplevel(str(repo)): entry}), encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert (code, "pointer is broken" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_an_unparseable_payload_under_auto_past_the_ramp_is_refused(flavour, tmp_path):
    root = make_repo(tmp_path, mode="auto")
    for number in range(1, 11):
        make_ticket(root, f"T-{number}", activate=False)
        crew_ticket.approve(str(root), f"T-{number}", by="tester")
    ready(root, "T-11")

    code, _, _ = _guard(flavour, root, b"{not json")

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool,command", [
    ("Bash", "python3 hooks/scripts/crew_ticket.py approve --ticket T-1"),
    ("Bash", "python3 -m crew_ticket --root . approve --ticket T-1"),
    ("Bash", "echo '{\"prompt\": \"/crew:approve T-1\"}' | python3 approval_hook.py"),
    ("Bash", "bash hooks/scripts/approval-hook.sh < forged.json"),
    ("Bash", "echo '{}' > \"$(git rev-parse --git-common-dir)/crew/active-ticket\""),
    ("Bash", "cp forged.json .git/crew/tickets/T-1/approval.json"),
    ("Bash", "rm -rf .git/crew/review"),
    ("PowerShell", "Set-Content -Path .git\\crew\\active-ticket -Value '{}'"),
    ("PowerShell", "& python crew_ticket.py approve --ticket T-1"),
])
def test_a_shell_command_forging_approval_state_is_refused(flavour, repo, tool, command):
    code, _, err = _guard(flavour, repo, {"tool_name": tool, "cwd": str(repo),
                                          "tool_input": {"command": command}})

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_shell_write_to_the_absolute_state_path_is_refused(flavour, repo):
    target = os.path.join(common_dir(repo), "crew", "scope-tickets.json")

    code, _, _ = _guard(flavour, repo, {"tool_name": "Bash", "cwd": str(repo),
                                        "tool_input": {"command": f"echo '{{}}' > {target}"}})

    assert code == 2


# --- T-0010: the autopilot approval route -----------------------------------------

_AUTOPILOT = "python3 hooks/scripts/crew_autopilot.py approve --root . --ticket T-1"


def _policy_repo(repo, approval="risk", risk="low", allow=True):
    """T-1 made and active, with a `risk:` header and the given policy."""
    (repo / ".crew" / "config.json").write_text(json.dumps(
        {"scope": {"mode": "block", "allowCliApproval": allow},
         "autopilot": {"mode": "plan", "approval": approval}}), encoding="utf-8")
    spec = make_ticket(repo) / "spec.md"
    first, rest = spec.read_text(encoding="utf-8").split("\n", 1)
    header = f"   risk: {risk}" if risk else ""
    spec.write_text(f"{first} title   status: spec{header}\n{rest}", encoding="utf-8")
    return repo


def _shell(flavour, repo, command, tool="Bash"):
    return _guard(flavour, repo, {"tool_name": tool, "cwd": str(repo),
                                  "tool_input": {"command": command}})


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("approval,risk,allow", [
    ("human", "low", True), ("risk", "med", True), ("risk", "high", True),
    ("risk", None, True), ("self", "low", False), ("risk", "low", "true")])
def test_autopilot_approve_is_refused_when_the_policy_says_no(flavour, repo, approval, risk,
                                                             allow):
    _policy_repo(repo, approval, risk, allow)

    code, _, err = _shell(flavour, repo, _AUTOPILOT)

    assert (code, "autopilot.approval" in err or "allowCliApproval" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    _AUTOPILOT + "; rm x",
    _AUTOPILOT + " && echo done",
    _AUTOPILOT + " | tee log",
    _AUTOPILOT + "\nrm -rf src",
    "cd /tmp && " + _AUTOPILOT,
    "python3 hooks/scripts/crew_autopilot.py approve --root /elsewhere --ticket T-1",
    "python3 hooks/scripts/crew_autopilot.py approve --ticket T-1 --root .",
    "python3 $(touch x)crew_autopilot.py approve --ticket T-1",
    "python3 `touch x`crew_autopilot.py approve --ticket T-1",
    "python3 -m crew_autopilot approve --ticket T-1",
    "python3 hooks/scripts/crew_autopilot.py approve --ticket T-1 --ticket T-2",
    "python3 hooks/scripts/crew_autopilot.py approve --ticket 'T-1'",
    "bash -c 'python3 hooks/scripts/crew_autopilot.py approve --ticket T-1'",
])
def test_autopilot_approve_that_is_not_the_bare_command_is_refused(flavour, repo, command):
    _policy_repo(repo, "self")

    code, _, err = _shell(flavour, repo, command)

    assert (code, "bare command" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("approval", ["self", "human"])
@pytest.mark.parametrize("command", [
    pytest.param("python3 hooks/scripts/crew_autopilot.py \\\n  approve --root . --ticket T-1",
                 id="before-approve"),
    pytest.param("python3 hooks/scripts/crew_autopilot.py approve \\\n  --root . --ticket T-1",
                 id="after-approve"),
    pytest.param("python3 hooks/scripts/crew_auto\\\npilot.py approve --root . --ticket T-1",
                 id="inside-the-name"),
    pytest.param("python3 hooks/scripts/crew_autopilot.py \\\r\n  approve --root . --ticket T-1",
                 id="crlf"),
])
def test_autopilot_approve_across_a_line_continuation_is_refused(flavour, repo, approval,
                                                                command):
    _policy_repo(repo, approval)

    code, _, err = _shell(flavour, repo, command)

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool,command", [
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py \\\n  approve --ticket T-1",
                 id="bash-crew-ticket"),
    pytest.param("Bash", "python3 hooks/scripts/crew_tic\\\nket.py approve --ticket T-1",
                 id="bash-inside-the-name"),
    pytest.param("PowerShell", "& python crew_ticket.py `\n  approve --ticket T-1",
                 id="ps-crew-ticket"),
    pytest.param("PowerShell", "& python crew_autopilot.py `\n  approve --root . --ticket T-1",
                 id="ps-crew-autopilot"),
    pytest.param("Bash", "python3 hooks/scripts/approval_\\\nhook.py", id="bash-hook"),
])
def test_an_approval_split_across_a_line_continuation_is_refused(flavour, repo, tool, command):
    _policy_repo(repo, "self")

    code, _, err = _shell(flavour, repo, command, tool)

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_crew_ticket_approve_stays_refused_under_every_policy(flavour, repo):
    _policy_repo(repo, "self")

    code, _, _ = _shell(flavour, repo, "python3 hooks/scripts/crew_ticket.py approve "
                                       "--ticket T-1")

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("approval,risk,command", [
    ("risk", "low", _AUTOPILOT),
    ("self", "high", _AUTOPILOT),
    ("self", None, ("python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py "
                    "approve --root . --ticket T-1")),
    ("risk", "low", "python3 hooks/scripts/crew_autopilot.py approve --ticket T-1"),
])
def test_autopilot_approve_bare_command_is_allowed_when_the_policy_says_yes(
        flavour, repo, approval, risk, command):
    _policy_repo(repo, approval, risk)

    code, out, err = _shell(flavour, repo, command)

    assert (code, out, err) == (0, "", "")


def test_a_policy_that_cannot_be_told_is_refused(repo, monkeypatch):
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    import scope_guard  # pylint: disable=import-outside-toplevel
    _policy_repo(repo, "self")

    def boom(_root, _ticket):
        raise OSError("disk")
    monkeypatch.setattr(crew_autopilot, "approval_policy", boom)

    reason = scope_guard.shell_refusal(_AUTOPILOT, common_dir(repo), str(repo))

    assert (reason is not None, "could not tell" in (reason or "")) == (True, True)


@pytest.mark.parametrize("answer", [{"allow": "yes"}, {"allow": 1}, None])
def test_a_policy_answer_that_is_not_a_plain_yes_is_refused(repo, monkeypatch, answer):
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    import scope_guard  # pylint: disable=import-outside-toplevel
    _policy_repo(repo, "self")
    monkeypatch.setattr(crew_autopilot, "approval_policy", lambda _root, _ticket: answer)

    assert scope_guard.shell_refusal(_AUTOPILOT, common_dir(repo), str(repo)) is not None


# --- must-allow -------------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool,command", [
    ("Bash", "ls -la"),
    ("Bash", "python3 hooks/scripts/crew_ticket.py status --ticket T-1"),
    ("Bash", "python3 hooks/scripts/crew_ticket.py activate --ticket T-1"),
    ("Bash", "python3 crew_ticket.py status --ticket T-1 && echo approve"),
    ("Bash", "python3 crew_ticket.py status --ticket T-1\necho approve"),
    ("Bash", "python3 crew_ticket.py status \\\n  --ticket T-1\necho approve"),
    ("Bash", "cat .git/crew/active-ticket 2>/dev/null"),
    ("PowerShell", "Get-Content .git\\crew\\active-ticket"),
])
def test_ordinary_shell_commands_are_allowed(flavour, repo, tool, command):
    ready(repo)

    code, out, err = _guard(flavour, repo, {"tool_name": tool, "cwd": str(repo),
                                            "tool_input": {"command": command}})

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_forging_command_is_allowed_when_scope_is_off(flavour, tmp_path):
    root = make_repo(tmp_path, mode="off")

    code, _, _ = _guard(flavour, root, {"tool_name": "Bash", "cwd": str(root),
                                        "tool_input": {"command": "crew_ticket.py approve"}})

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_cli_approval_opens_touch_when_the_config_allows_it(flavour, repo):
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "block", "allowCliApproval": True}}), encoding="utf-8")
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="ci")

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_an_unparseable_payload_under_auto_within_the_ramp_is_allowed(flavour, tmp_path):
    root = make_repo(tmp_path, mode="auto")
    ready(root)

    code, _, _ = _guard(flavour, root, b"{not json")

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_in_scope_edit_with_an_approved_plan_is_allowed(flavour, repo):
    ready(repo)

    code, out, err = _guard(flavour, repo, edit(repo, repo / "src" / "app.py", "Edit"))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_new_file_inside_touch_is_allowed(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "src" / "deep" / "new.py"))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("name", ["spec.md", "plan.md", "notes.md"])
def test_the_tickets_own_files_are_allowed_even_unapproved(flavour, repo, name):
    make_ticket(repo)

    code, _, _ = _guard(flavour, repo,
                        edit(repo, repo / ".work" / "tickets" / "T-1" / name, "Edit"))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_mode_off_allows_everything(flavour, tmp_path):
    root = make_repo(tmp_path, mode="off")
    make_ticket(root)

    code, out, err = _guard(flavour, root, edit(root, root / "other" / "keep.py"))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_no_scope_key_is_off(flavour, tmp_path):
    root = make_repo(tmp_path, mode=None)
    make_ticket(root)

    code, _, _ = _guard(flavour, root, edit(root, root / "other" / "keep.py"))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_report_mode_allows_logs_and_says_so(flavour, tmp_path):
    root = make_repo(tmp_path, mode="report")
    ready(root)

    code, out, _ = _guard(flavour, root, edit(root, root / "other" / "keep.py"))
    log = (root / ".crew" / "guard.log").read_text(encoding="utf-8")

    assert code == 0
    assert "would block" in json.loads(out)["systemMessage"]
    assert "\tscope\treport\treport\tT-1\t" in log


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_no_active_ticket_is_allowed(flavour, repo):
    make_ticket(repo, activate=False)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_tool_that_does_not_edit_is_not_judged(flavour, repo):
    make_ticket(repo)

    code, _, _ = _guard(flavour, repo, {"tool_name": "Bash",
                                        "tool_input": {"command": "ls"}, "cwd": str(repo)})

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_path_outside_the_worktree_is_not_a_repository_path(flavour, repo, tmp_path):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, tmp_path / "scratch" / "notes.md"))

    assert code == 0


# --- the ramp: report for the first ten tickets, then block --------------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
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


# --- one read of spec.md: approval and Touch from the same bytes ------------------

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_touch_is_judged_from_the_bytes_the_approval_hashed(flavour, repo, monkeypatch):
    if flavour != "module":
        pytest.skip("in-process: the race is staged by replacing read_contract")
    import scope_guard  # pylint: disable=import-outside-toplevel
    ready(repo)
    folder = repo / ".work" / "tickets" / "T-1"
    approved = {n: (folder / n).read_bytes() for n in ("spec.md", "plan.md")}
    spec = folder / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("`src/**`", "`**`"),
                    encoding="utf-8")
    monkeypatch.setattr(crew_ticket, "read_contract", lambda top, ticket: dict(approved))

    code = scope_guard.decide(edit(repo, repo / "other" / "keep.py"))

    assert code == 2


# --- T-0068: crew's own bookkeeping is allowed outside Touch ------------------------

@pytest.mark.parametrize("approved", [True, False], ids=["approved", "no-approval"])
@pytest.mark.parametrize("rel", [".crew/metrics.md"])
def test_an_edit_to_bookkeeping_is_allowed_outside_touch(repo, rel, approved):
    """Must-allow: `/crew:review` step 6 appends `.crew/metrics.md` with Edit.
    Under `block`, with Touch `src/**` (or no approval at all), that append
    is crew's bookkeeping, not a scope change."""
    import scope_guard  # pylint: disable=import-outside-toplevel
    if approved:
        ready(repo)
    else:
        make_ticket(repo)
    target = repo.joinpath(*rel.split("/"))
    target.write_text("| row |\n", encoding="utf-8")

    code, _, err = _guard("module", repo, edit(repo, target, "Edit"))
    approval = crew_ticket.accepted(str(repo), "T-1")
    verdict = scope_guard.classify(str(repo), common_dir(repo), "T-1", approval["touch"],
                                   approval, str(target), str(repo))

    assert (code, err, verdict) == (0, "", (True, "crew bookkeeping"))


@pytest.mark.parametrize("mode", ["report", "block", "auto"])
@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_scope_base_stays_refused_though_it_is_bookkeeping(tmp_path, mode, tool):
    """Must-block: being bookkeeping for the audit and the bundle does not make
    the scope base writable -- it is what the audit trusts (rule 2)."""
    repo = make_repo(tmp_path, mode=mode)
    ready(repo)

    code, _, err = _guard("module", repo, edit(repo, repo / ".crew" / ".scope-base", tool))

    assert (code, "approval/ledger state" in err) == (2, True)


@pytest.mark.parametrize("rel", [".crew/metrics.md.bak", ".crew/metricsX.md",
                                 "docs/.crew/guard.log", ".crew/verify.json"])
def test_a_bookkeeping_lookalike_is_still_judged(repo, rel):
    ready(repo)
    target = repo.joinpath(*rel.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)

    code, _, err = _guard("module", repo, edit(repo, target))

    assert (code, "outside T-1's spec ## Touch" in err) == (2, True)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
@pytest.mark.parametrize("link,points_to", [(".crew/metrics.md", "secret/x.py"),
                                            ("other/link.md", ".crew/metrics.md")])
def test_one_side_of_a_link_being_bookkeeping_does_not_decide(repo, link, points_to):
    """Must-block: BOTH the named and the real path must be bookkeeping, as for
    refresh artifacts -- a link cannot carry a write out of `.crew/`."""
    ready(repo)
    real = repo.joinpath(*points_to.split("/"))
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("x\n", encoding="utf-8")
    os.symlink(real, repo.joinpath(*link.split("/")))

    code, _, _ = _guard("module", repo, edit(repo, repo.joinpath(*link.split("/"))))

    assert code == 2


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
def test_a_bookkeeping_name_linked_outside_the_worktree_is_not_bookkeeping(repo, tmp_path):
    """Must-block: a real path outside the worktree is never bookkeeping,
    whatever the name says (refresh artifacts' rule)."""
    make_ticket(repo)
    outside = tmp_path / "outside.txt"
    outside.write_text("x\n", encoding="utf-8")
    os.symlink(outside, repo / ".crew" / "metrics.md")

    code, _, _ = _guard("module", repo, edit(repo, repo / ".crew" / "metrics.md"))

    assert code == 2


# --- review of 514ca132: rule 5a opens ONLY crew_ticket.CREW_WRITE_ALLOWED_PATHS ---

@pytest.mark.parametrize("approved", [True, False], ids=["approved", "no-approval"])
@pytest.mark.parametrize("rel", [".crew/tfplan/x.json", ".crew/incident.json",
                                 ".crew/.deploy-in-flight", ".crew/handoffs/x.md"])
def test_a_trust_input_crew_writes_is_judged_against_touch(repo, rel, approved):
    """Must-block (FIX 1): crew writes these, but crew also READS them -- a
    `tfplan` sidecar with `deletes: []` would let `terraform apply` run
    unattended, `incident.json` stands the Stop gate down -- so an Edit out
    of Touch is refused like any other file, never opened by rule 5a."""
    if approved:
        ready(repo)
    else:
        make_ticket(repo)
    target = repo.joinpath(*rel.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)

    code, _, _ = _guard("module", repo, edit(repo, target, "Write"))
    approval = crew_ticket.accepted(str(repo), "T-1")
    verdict = scope_guard_classify(repo, approval, target)

    assert (code, verdict[0]) == (2, False)


def scope_guard_classify(repo, approval, target):
    import scope_guard  # pylint: disable=import-outside-toplevel
    return scope_guard.classify(str(repo), common_dir(repo), "T-1", approval["touch"],
                                approval, str(target), str(repo))


@pytest.mark.parametrize("tool", ["Write", "Edit"])
@pytest.mark.parametrize("rel", [".crew/.verify-gate.record.json", ".crew/.verify-gate.fingerprint",
                                 ".crew/.verify-verified-at", ".crew/.verify-gate.timings.json",
                                 ".crew/.verify-gate.lock/owner", ".crew/metrics.jsonl"])
def test_the_gates_records_are_refused_even_inside_touch(tmp_path, rel, tool):
    """Must-block (FIX 2): the review gate reads VERIFIED from the marker and
    the (unkeyed) fingerprint, and the bundle and the audit leave them out,
    so a Write/Edit to one is a forged green gate nobody would see. Refused
    by rule 2 even when Touch names `.crew/**`, and with no ticket active."""
    repo = make_repo(tmp_path, mode="block")
    ready(repo, touch=("src/**", ".crew/**"))
    target = repo.joinpath(*rel.split("/"))

    code, _, err = _guard("module", repo, edit(repo, target, tool))

    assert (code, "approval/ledger state" in err) == (2, True)


@pytest.mark.parametrize("mode", ["report", "auto"])
def test_the_gates_marker_is_refused_with_no_ticket_in_every_mode(tmp_path, mode):
    repo = make_repo(tmp_path, mode=mode)

    code, _, err = _guard("module", repo, edit(repo, repo / ".crew" / ".verify-verified-at"))

    assert (code, "approval/ledger state" in err) == (2, True)

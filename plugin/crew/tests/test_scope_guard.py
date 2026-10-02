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
from review_fixtures import git
from scope_fixtures import (FLAVOUR_MATRIX, FLAVOURS, accepted_ledger, common_dir,
                            corrupt_ledger, edit, index, make_repo, make_ticket, ready,
                            run_hook, spec_done)

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


# --- T-0504: who moves the active-ticket pointer ------------------------------------
# A move off an in-flight ticket (case D) is the owner's: the session is refused and
# told the owner types `/crew:autopilot <id>`. A move that cannot widen scope (no
# pointer, the same ticket, a ticket closed by an accepted review AND done) is allowed.

_ACTIVATE_T2 = "python3 hooks/scripts/crew_ticket.py activate --ticket T-2"
_DEACTIVATE = "python3 hooks/scripts/crew_ticket.py deactivate"
MODES = ("block", "report")


def _in_flight(tmp_path, mode="block", status="in-progress"):
    """T-1 active and approved (INDEX `status`), T-2 made and not active."""
    root = make_repo(tmp_path, mode=mode)
    ready(root)
    make_ticket(root, "T-2", activate=False)
    index(root, [("T-1", status), ("T-2", "ready")])
    return root


def _refused_for_the_owner(code, err, active, target):
    return (code, active in err, f"/crew:autopilot {target}" in err,
            "crew_ticket.py activate" in err, "crew_ticket.py deactivate" in err)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("mode", MODES)
def test_activate_off_an_open_ticket_is_refused(flavour, tmp_path, mode):
    root = _in_flight(tmp_path, mode)

    code, _, err = _shell(flavour, root, _ACTIVATE_T2)

    assert _refused_for_the_owner(code, err, "T-1", "T-2") == (2, True, True, False, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("mode", MODES)
def test_activate_off_a_ticket_closed_in_index_only_is_refused(flavour, tmp_path, mode):
    root = _in_flight(tmp_path, mode, status="done")

    code, _, err = _shell(flavour, root, _ACTIVATE_T2)

    assert _refused_for_the_owner(code, err, "T-1", "T-2") == (2, True, True, False, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("mode", MODES)
def test_activate_off_a_ticket_closed_in_spec_only_is_refused(flavour, tmp_path, mode):
    root = _in_flight(tmp_path, mode)
    spec_done(root, "T-1")

    code, _, err = _shell(flavour, root, _ACTIVATE_T2)

    assert _refused_for_the_owner(code, err, "T-1", "T-2") == (2, True, True, False, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("mode", MODES)
def test_activate_off_a_ticket_with_a_corrupt_ledger_is_refused(flavour, tmp_path, mode):
    root = _in_flight(tmp_path, mode, status="done")
    corrupt_ledger(root, "T-1")

    code, _, err = _shell(flavour, root, _ACTIVATE_T2)

    assert (_refused_for_the_owner(code, err, "T-1", "T-2"), "could not tell" in err) == (
        (2, True, True, False, False), True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("mode", MODES)
def test_deactivate_of_an_open_ticket_is_refused(flavour, tmp_path, mode):
    root = _in_flight(tmp_path, mode)

    code, _, err = _shell(flavour, root, _DEACTIVATE)

    assert _refused_for_the_owner(code, err, "T-1", "<id>") == (2, True, True, False, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "python3 hooks/scripts/crew_ticket.py activate",
    "python3 hooks/scripts/crew_ticket.py activate --ticket $T",
    "python3 hooks/scripts/crew_ticket.py activate --ticket \"$(cat t)\"",
    "python3 hooks/scripts/crew_ticket.py activate --ticket 'T-2",
])
def test_activate_without_a_ticket_is_refused_as_could_not_tell(flavour, tmp_path, command):
    root = _in_flight(tmp_path)

    code, _, err = _shell(flavour, root, command)

    assert (code, "could not tell" in err, "crew_ticket.py activate" in err) == (
        2, True, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_activate_naming_another_worktrees_root_is_judged_there(flavour, tmp_path):
    root = make_repo(tmp_path, mode="block")
    make_ticket(root, "T-2", activate=False)
    other = tmp_path / "other"
    git(root, "worktree", "add", "-q", str(other))
    (other / ".crew").mkdir(exist_ok=True)
    (other / ".crew" / "config.json").write_text(json.dumps({"scope": {"mode": "block"}}),
                                                 encoding="utf-8")
    make_ticket(other, "T-9")
    make_ticket(other, "T-2", activate=False)

    code, _, err = _shell(flavour, root, "python3 hooks/scripts/crew_ticket.py activate "
                                         f"--root {other} --ticket T-2")

    assert _refused_for_the_owner(code, err, "T-9", "T-2") == (2, True, True, False, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool,command", [
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py acti\\\nvate --ticket T-2",
                 id="bash-continuation"),
    pytest.param("PowerShell", "& python crew_ticket.py activate --ticket T-2", id="ps"),
    pytest.param("PowerShell", "& python crew_ticket.py `\n  activate --ticket T-2",
                 id="ps-continuation"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py activate --ticket=T-2",
                 id="equals"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py activate --tick T-2",
                 id="abbreviated-option"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py active; "
                         "python3 hooks/scripts/crew_ticket.py activate --ticket T-2",
                 id="second-command"),
    pytest.param("Bash", "bash -c 'python3 hooks/scripts/crew_ticket.py activate --ticket T-2'",
                 id="bash-c"),
])
def test_activate_in_another_shape_is_refused(flavour, tmp_path, tool, command):
    root = _in_flight(tmp_path)

    code, _, err = _shell(flavour, root, command, tool)

    assert (code, "T-1" in err, "crew_ticket.py activate" in err) == (2, True, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "cd ../elsewhere && python3 hooks/scripts/crew_ticket.py activate --ticket T-2",
    "pushd ../elsewhere; python3 hooks/scripts/crew_ticket.py deactivate",
])
def test_activate_after_a_directory_change_is_refused_as_could_not_tell(flavour, tmp_path,
                                                                     command):
    root = make_repo(tmp_path, mode="block")
    make_ticket(root, "T-2", activate=False)

    code, _, err = _shell(flavour, root, command)

    assert (code, "could not tell which worktree" in err) == (2, True)


# Review round 1, BLOCK crew_ticket.py:1079: a --root the guard cannot model as the
# shell will (a `~` the shell expands, a backslash path, a path that is no repository
# where the guard looked) was allowed, so the CLI could move a pointer the guard never
# judged. Each is could-not-tell now; `--root .` and an absolute worktree still judge.
@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool,command,decoy", [
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py activate --root ~/other "
                         "--ticket T-2", "~/other", id="tilde"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py activate --root=~ --ticket T-2",
                 "~", id="tilde-equals"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py deactivate --root ~/other",
                 "~/other", id="tilde-deactivate"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py activate --root no-such-dir "
                         "--ticket T-2", None, id="not-a-repository"),
    pytest.param("PowerShell", "& python crew_ticket.py activate --root C:\\repos\\other "
                               "--ticket T-2", "C:reposother", id="ps-backslash"),
    pytest.param("Bash", "python3 hooks/scripts/crew_ticket.py activate --ro 'C:\\r\\o' "
                         "--ticket T-2", "C:\\r\\o", id="abbreviated-backslash"),
])
def test_activate_with_a_root_the_guard_cannot_model_is_refused(flavour, tmp_path, tool,
                                                                command, decoy):
    root = make_repo(tmp_path, mode="block")
    make_ticket(root, "T-2", activate=False)
    try:  # the literal path the guard would model, made a directory inside this repo
        if decoy:
            (root / decoy).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    code, _, err = _shell(flavour, root, command, tool)

    assert (code, "could not tell which worktree" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "python3 hooks/scripts/crew_ticket.py activate --root . --ticket T-2",
    "python3 hooks/scripts/crew_ticket.py activate --root src --ticket T-2",
    "python3 hooks/scripts/crew_ticket.py activate --root ./ --ticket T-2",
])
def test_activate_with_a_modelled_root_and_no_pointer_is_allowed(flavour, tmp_path, command):
    root = make_repo(tmp_path, mode="block")
    (root / "src").mkdir(exist_ok=True)
    make_ticket(root, "T-2", activate=False)

    code, out, err = _shell(flavour, root, command)

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_activate_off_a_ticket_with_a_hollow_accepted_ledger_is_refused(flavour, tmp_path):
    root = _in_flight(tmp_path, status="done")
    path = pathlib.Path(common_dir(root), "crew", "review", "T-1.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"state": "ACCEPTED", "rounds": [],
                                "receipt": {"kind": "clean"}}), encoding="utf-8")

    code, _, err = _shell(flavour, root, _ACTIVATE_T2)

    assert (_refused_for_the_owner(code, err, "T-1", "T-2"), "could not tell" in err) == (
        (2, True, True, False, False), True)


def test_broken_pointer_message_names_the_owner_prompt_not_the_cli(tmp_path):
    root = make_repo(tmp_path, mode="block")
    make_ticket(root, "T-1", activate=False)
    pointer = os.path.join(common_dir(root), "crew", "active-ticket")
    os.makedirs(os.path.dirname(pointer), exist_ok=True)
    pathlib.Path(pointer).write_text(
        json.dumps({crew_ticket.toplevel(str(root)): "T-9"}), encoding="utf-8")

    code, _, err = _guard("module", root, edit(root, root / "src" / "app.py"))

    assert (code, "/crew:autopilot <id>" in err, "crew_ticket.py" in err) == (2, True, False)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_activate_with_no_pointer_is_allowed(flavour, tmp_path):
    root = make_repo(tmp_path, mode="block")
    make_ticket(root, "T-1", activate=False)
    make_ticket(root, "T-2", activate=False)

    code, out, err = _shell(flavour, root, _ACTIVATE_T2)

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("kind", ["clean", "owner-accepted"])
def test_activate_off_a_ledger_closed_ticket_is_allowed(flavour, tmp_path, kind):
    root = _in_flight(tmp_path, status="done")
    accepted_ledger(root, "T-1", kind)

    code, out, err = _shell(flavour, root, _ACTIVATE_T2)

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_deactivate_with_no_pointer_is_allowed(flavour, tmp_path):
    root = make_repo(tmp_path, mode="block")
    make_ticket(root, "T-1", activate=False)

    code, out, err = _shell(flavour, root, _DEACTIVATE)

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_deactivate_off_a_ledger_closed_ticket_is_allowed(flavour, tmp_path):
    root = _in_flight(tmp_path, status="done")
    accepted_ledger(root, "T-1")

    code, out, err = _shell(flavour, root, _DEACTIVATE)

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "python3 hooks/scripts/crew_ticket.py active",
    "python3 hooks/scripts/crew_ticket.py status --ticket T-2",
    "python3 hooks/scripts/crew_ticket.py activate --ticket T-1",
    "python3 hooks/scripts/crew_ticket.py activate --root . --ticket T-1",
])
def test_pointer_reads_and_a_same_ticket_activate_are_allowed_in_flight(flavour, tmp_path,
                                                                      command):
    root = _in_flight(tmp_path)

    code, out, err = _shell(flavour, root, command)

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [_ACTIVATE_T2, _DEACTIVATE])
def test_activate_is_allowed_when_scope_is_off(flavour, tmp_path, command):
    root = _in_flight(tmp_path, mode="off")

    code, _, _ = _shell(flavour, root, command)

    assert code == 0

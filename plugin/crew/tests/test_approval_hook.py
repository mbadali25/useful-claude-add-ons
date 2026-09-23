"""approval_hook.py and its .sh / .ps1 wrappers: the UserPromptSubmit hook that
records a plan approval only from the user's own `/crew:approve <id>` prompt.
It can BLOCK a prompt (exit 2) when an approval was asked for and not
recorded, so must-block and must-allow run through the module, bash and
PowerShell (pwsh with OS=Windows_NT; skipped, and said so, without pwsh).
"""
import hashlib
import json
import os
import pathlib
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import approval_hook
import crew_ticket
from scope_fixtures import (FLAVOURS, PWSH, SCRIPTS, common_dir, make_repo, make_ticket,
                            prompt, run_hook)


def _hook(flavour, root, payload):
    return run_hook(flavour, "approval_hook", payload, root)


def _receipt(root, ticket="T-1"):
    path = pathlib.Path(common_dir(root), "crew", "tickets", ticket, "approval.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


# --- must-record ------------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_users_prompt_records_a_user_prompt_receipt(flavour, repo):
    make_ticket(repo)

    code, out, _ = _hook(flavour, repo, prompt(repo, "/crew:approve T-1", session="s-42"))
    receipt = _receipt(repo)

    assert code == 0
    assert (receipt["approved_via"], receipt["session_id"], receipt["prompt_id"]) == \
        ("user-prompt", "s-42", "p-1")
    assert "approved T-1" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_the_receipt_hashes_the_files_as_approved(repo):
    folder = make_ticket(repo)

    approval_hook.handle(prompt(repo, "  /crew:approve T-1  \n"))

    assert _receipt(repo)["spec_sha256"] == \
        hashlib.sha256((folder / "spec.md").read_bytes()).hexdigest()


def test_the_expanded_command_form_is_accepted(repo):
    make_ticket(repo)
    text = ("<command-message>crew:approve is running</command-message>\n"
            "<command-name>/crew:approve</command-name>\n<command-args>T-1</command-args>")

    code = approval_hook.handle(prompt(repo, text))

    assert (code, _receipt(repo)["approved_via"]) == (0, "user-prompt")


def test_a_user_prompt_receipt_opens_touch_for_the_guard(repo):
    make_ticket(repo)
    approval_hook.handle(prompt(repo, "/crew:approve T-1"))

    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "approved"


# --- must-refuse (exit 2, nothing recorded) ------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_invalid_contract_blocks_the_prompt_and_records_nothing(flavour, repo):
    make_ticket(repo, files=["other/keep.py"])

    code, _, err = _hook(flavour, repo, prompt(repo, "/crew:approve T-1"))

    assert (code, "NOT recorded" in err, _receipt(repo)) == (2, True, None)


@pytest.mark.parametrize("text", ["/crew:approve", "/crew:approve T-1 T-2",
                                  "/crew:approve ../x"])
def test_a_malformed_approve_prompt_is_refused(repo, text):
    make_ticket(repo)

    code = approval_hook.handle(prompt(repo, text))

    assert (code, _receipt(repo)) == (2, None)


# --- must-allow, recording nothing -------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("text", ["please look at the widget",
                                  "should I run /crew:approve T-1 now?",
                                  "`/crew:approve T-1`"])
def test_a_prompt_that_is_not_the_command_passes_untouched(flavour, repo, text):
    make_ticket(repo)

    code, out, err = _hook(flavour, repo, prompt(repo, text))

    assert (code, out, err, _receipt(repo)) == (0, "", "", None)


def test_another_event_is_not_an_approval(repo):
    make_ticket(repo)
    payload = dict(prompt(repo, "/crew:approve T-1"), hook_event_name="PreToolUse")

    assert (approval_hook.handle(payload), _receipt(repo)) == (0, None)


# --- the wrappers ------------------------------------------------------------------------

def _no_python_env(tmp_path, root):
    """PATH with bash's own tools but no python at all."""
    folder = tmp_path / "nopy"
    folder.mkdir()
    for tool in ("cat", "dirname", "tr", "sed", "grep", "wc", "cut", "cksum", "rm"):
        for base in ("/usr/bin", "/bin"):
            if os.path.exists(os.path.join(base, tool)):
                os.symlink(os.path.join(base, tool), folder / tool)
                break
    return dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT", PATH=str(folder))


@pytest.mark.parametrize("shell", ["sh", "ps1"])
@pytest.mark.parametrize("text,expected", [("/crew:approve T-1", 2), ("hello", 0)])
def test_without_python_only_an_approve_prompt_is_blocked(tmp_path, repo, shell, text,
                                                          expected):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
    make_ticket(repo)
    cmd = ([PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, "approval-hook.ps1")]
           if shell == "ps1" else ["/bin/bash", os.path.join(SCRIPTS, "approval-hook.sh")])

    done = subprocess.run(cmd, input=json.dumps(prompt(repo, text)).encode(), cwd=str(repo),
                          capture_output=True, env=_no_python_env(tmp_path, repo),
                          check=False, timeout=120)

    assert done.returncode == expected, done.stderr


def _resolver(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.index("function Resolve-CrewPython {")
    return src[start:src.index("\n}\n", start) + 3]


def test_the_powershell_resolver_is_byte_for_byte_role_write_guards():
    assert _resolver(os.path.join(SCRIPTS, "approval-hook.ps1")) == \
        _resolver(os.path.join(SCRIPTS, "role-write-guard.ps1"))


def test_the_flavour_guard_is_the_first_executable_statement():
    lines = pathlib.Path(SCRIPTS, "approval-hook.ps1").read_text(encoding="utf-8").splitlines()
    code = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]

    assert code[code.index(")") + 1] == "if ($env:OS -ne 'Windows_NT') { exit 0 }"


@pytest.mark.parametrize("name", ["approval-hook.sh", "approval-hook.ps1", "approval_hook.py"])
def test_every_new_file_is_lf_only(name):
    assert b"\r" not in pathlib.Path(SCRIPTS, name).read_bytes()

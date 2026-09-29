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
import crew_fixtures
import crew_ticket
from scope_fixtures import (FLAVOUR_MATRIX, FLAVOURS, PWSH, SCRIPTS, common_dir, make_repo,
                            make_ticket, prompt, run_hook)

# FLAVOURS tests are the per-shell parity sample (a receipt recorded, a block,
# a malformed payload refused); FLAVOUR_MATRIX tests run `sh`/`ps1` as `slow`.


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

@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("text", ["please look at the widget",
                                  "should I run /crew:approve T-1 now?",
                                  "`/crew:approve T-1`"])
def test_a_prompt_that_is_not_the_command_passes_untouched(flavour, repo, text):
    make_ticket(repo)

    code, out, err = _hook(flavour, repo, prompt(repo, text))

    assert (code, out, err, _receipt(repo)) == (0, "", "", None)


@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("raw", [b'{"prompt": "/crew:approve T-1",',
                                 b'["/crew:approve T-1"]',
                                 b'\xff{"prompt": "/crew:approve T-1"}'],
                         ids=["truncated", "array", "bad-utf8"])
def test_a_malformed_payload_naming_the_command_is_refused(flavour, repo, raw):
    make_ticket(repo)

    code, _, err = _hook(flavour, repo, raw)

    assert (code, "NOT recorded" in err, _receipt(repo)) == (2, True, None)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_malformed_payload_not_naming_the_command_passes(flavour, repo):
    make_ticket(repo)

    code, out, err = _hook(flavour, repo, b'{"prompt": "hello",')

    assert (code, out, err) == (0, "", "")


def test_another_event_is_not_an_approval(repo):
    make_ticket(repo)
    payload = dict(prompt(repo, "/crew:approve T-1"), hook_event_name="PreToolUse")

    assert (approval_hook.handle(payload), _receipt(repo)) == (0, None)


# --- T-0024: plain text and groups reach python through every wrapper --------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_plain_text_approval_goes_pending_then_confirm_records(flavour, repo):
    make_ticket(repo)
    make_ticket(repo, "T-2", activate=False)

    first = _hook(flavour, repo, prompt(repo, "approve T-1 and T-2"))
    pending = (_receipt(repo), _receipt(repo, "T-2"))
    code, out, _ = _hook(flavour, repo, prompt(repo, "/crew:approve --confirm"))

    assert (first[0], "PENDING" in first[2], pending) == (2, True, (None, None))
    assert (code, _receipt(repo)["approved_via"], _receipt(repo, "T-2")["approved_via"]) == \
        (0, "user-prompt", "user-prompt")
    assert "group confirm" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("text", ["does the reviewer approve this?", "I approve of T-1",
                                  "Approved.", "yes"])
def test_a_prompt_using_the_word_approve_passes_untouched(flavour, repo, text):
    make_ticket(repo)

    code, out, err = _hook(flavour, repo, prompt(repo, text))

    assert (code, out, err, _receipt(repo)) == (0, "", "", None)


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
@pytest.mark.parametrize("text,expected", [("/crew:approve T-1", 2), ("hello", 0),
                                           ("approve T-1", 0), ("/crew:autopilot T-1", 0),
                                           ("does the reviewer approve this?", 0)])
def test_without_python_only_an_approve_prompt_is_blocked(tmp_path, repo, shell, text,
                                                          expected):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
    # A hardcoded "/bin/bash" doesn't exist on Windows at all (WinError 2,
    # FileNotFoundError) -- resolve_bash() is the same proven lookup
    # run_hook()/scope_fixtures.py already use for the "sh" flavour
    # elsewhere in this suite.
    bash = crew_fixtures.resolve_bash()
    if shell == "sh" and bash is None:
        pytest.skip("no working bash on PATH - the sh flavour was NOT run")
    make_ticket(repo)
    cmd = ([PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, "approval-hook.ps1")]
           if shell == "ps1" else [bash, os.path.join(SCRIPTS, "approval-hook.sh")])

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


# --- T-0504: the owner's `/crew:autopilot <id>` re-points this worktree ------------------
# The one move off an in-flight ticket the session may not make (scope_guard refuses its
# crew_ticket.py activate for it) is carried out here, from the prompt the owner typed.

def _pointed(repo, active="T-1"):
    """T-1 and T-2 with folders; this worktree's pointer on `active`."""
    make_ticket(repo, "T-1", activate=False)
    make_ticket(repo, "T-2", activate=False)
    if active:
        crew_ticket.activate(str(repo), active)
    return repo


def _pointer(repo):
    return crew_ticket.resolve_active(str(repo))[0]


def _context(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_the_owners_autopilot_prompt_repoints_the_worktree(flavour, repo):
    _pointed(repo)

    code, out, _ = _hook(flavour, repo, prompt(repo, "/crew:autopilot T-2"))

    assert (code, _pointer(repo), "T-2" in _context(out), "T-1" in _context(out)) == (
        0, "T-2", True, True)


@pytest.mark.parametrize("flavour", ["sh", "ps1"])
def test_the_bash_prefilter_passes_crew_autopilot_to_python(flavour, repo):
    _pointed(repo)

    code, _, _ = _hook(flavour, repo, prompt(repo, "/crew:autopilot T-2"))

    assert (code, _pointer(repo)) == (0, "T-2")


def test_run_form_repoints(repo):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, "  /crew:autopilot run T-2  \n"))

    assert (code, _pointer(repo)) == (0, "T-2")


def test_expanded_autopilot_form_repoints(repo):
    _pointed(repo)
    text = ("<command-message>crew:autopilot is running</command-message>\n"
            "<command-name>/crew:autopilot</command-name>\n<command-args>T-2</command-args>")

    code = approval_hook.handle(prompt(repo, text))

    assert (code, _pointer(repo)) == (0, "T-2")


def test_autopilot_prompt_with_no_pointer_activates(repo):
    _pointed(repo, active=None)

    code = approval_hook.handle(prompt(repo, "/crew:autopilot T-2"))

    assert (code, _pointer(repo)) == (0, "T-2")


def test_autopilot_prompt_on_the_active_ticket_writes_nothing(repo, capsys):
    _pointed(repo, active="T-2")
    pointer = pathlib.Path(common_dir(repo), "crew", "active-ticket")
    before = pointer.stat().st_mtime_ns

    code = approval_hook.handle(prompt(repo, "/crew:autopilot T-2"))

    assert (code, pointer.stat().st_mtime_ns, capsys.readouterr().out) == (0, before, "")


def test_autopilot_status_does_not_repoint(repo):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, "/crew:autopilot status T-2"))

    assert (code, _pointer(repo)) == (0, "T-1")


def test_bare_autopilot_does_not_repoint(repo):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, "/crew:autopilot"))

    assert (code, _pointer(repo)) == (0, "T-1")


@pytest.mark.parametrize("text", ["/crew:autopilot assign T-2", "/crew:autopilot goal T-2",
                                  "/crew:autopilot focus T-2", "/crew:autopilot --goal T-2",
                                  "/crew:autopilot run", "/crew:autopilot T-2 T-3",
                                  "/crew:autopilot run T-2 now"])
def test_autopilot_subcommands_do_not_repoint(repo, text):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, text))

    assert (code, _pointer(repo)) == (0, "T-1")


@pytest.mark.parametrize("text", ["please run /crew:autopilot T-2", "try `/crew:autopilot T-2`",
                                  "I think /crew:autopilot T-2 is next"])
def test_autopilot_mid_sentence_does_not_repoint(repo, text):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, text))

    assert (code, _pointer(repo)) == (0, "T-1")


@pytest.mark.parametrize("text", [
    ("<command-message><command-name>/crew:autopilot</command-name></command-message>\n"
     "<command-name>/crew:autopilot</command-name>\n<command-args>T-2</command-args>"),
    ("<command-name>/crew:autopilot</command-name>\n<command-args>T-2</command-args>\n"
     "and more words"),
    "<command-name>/crew:autopilot</command-name>\n<command-args>T-2\nT-3</command-args>",
])
def test_autopilot_nested_command_tag_does_not_repoint(repo, text):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, text))

    assert (code, _pointer(repo)) == (0, "T-1")


def test_autopilot_multiline_paste_does_not_repoint(repo):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, "/crew:autopilot T-2\n/crew:autopilot T-1"))

    assert (code, _pointer(repo)) == (0, "T-1")


def test_autopilot_id_without_a_folder_is_left_to_autopilot(repo, capsys):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, "/crew:autopilot T-9"))

    assert (code, _pointer(repo), capsys.readouterr().out) == (0, "T-1", "")


def test_autopilot_pointer_write_failure_blocks_the_prompt(repo, monkeypatch, capsys):
    _pointed(repo)

    def boom(_path, _data):
        raise OSError("disk full")
    monkeypatch.setattr(crew_ticket, "_write_json", boom)

    code = approval_hook.handle(prompt(repo, "/crew:autopilot T-2"))

    assert (code, _pointer(repo), "could not re-point" in capsys.readouterr().err) == (
        2, "T-1", True)


def test_an_approve_prompt_is_not_a_repoint(repo):
    _pointed(repo)

    code = approval_hook.handle(prompt(repo, "/crew:approve T-2"))

    assert (code, _pointer(repo), _receipt(repo, "T-2")["approved_via"]) == (
        0, "T-1", "user-prompt")

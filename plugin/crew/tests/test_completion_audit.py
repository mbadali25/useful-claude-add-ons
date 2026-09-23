"""completion_audit.py and its .sh / .ps1 wrappers: the Stop-time whole-tree
scope audit, plus the `--check` form `/crew:done` calls. A BLOCKING hook, so
must-block and must-allow run through the module, bash and PowerShell (pwsh
with OS=Windows_NT; skipped, and said so, without pwsh).

The case the edit guard cannot see is the reason this exists: a file written
by the shell never reaches PreToolUse.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
import crew_ticket
from review_fixtures import git
from scope_fixtures import (FLAVOURS, PWSH, SCRIPTS, make_repo, make_ticket, needs_pwsh,
                            ready, run_hook, stop)

_AUDIT = os.path.join(SCRIPTS, "completion_audit.py")


def _audit(flavour, root, payload):
    return run_hook(flavour, "completion_audit", payload, root)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


# --- must-block -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_shell_made_out_of_scope_file_blocks_the_stop(flavour, repo):
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, err = _audit(flavour, repo, stop(repo))

    assert (code, out, "other/made-by-sed.py" in err) == (2, "", True)
    assert len(err.strip().splitlines()) <= 6


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_committed_out_of_scope_change_blocks_the_stop(flavour, repo):
    ready(repo)
    (repo / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
    git(repo, "commit", "-qam", "sneak")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "other/keep.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_rename_out_of_scope_blocks_the_stop(flavour, repo):
    ready(repo)
    git(repo, "mv", "src/app.py", "other/app.py")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "other/app.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_rename_from_out_of_scope_into_scope_blocks_too(flavour, repo):
    ready(repo)
    git(repo, "mv", "other/keep.py", "src/keep.py")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "other/keep.py" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_changes_under_a_stale_approval_block(flavour, repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 3\n", encoding="utf-8")
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("`src/**`", "`**`"),
                    encoding="utf-8")

    code, _, err = _audit(flavour, repo, stop(repo))

    assert (code, "not approved" in err) == (2, True)


def test_a_staged_out_of_scope_deletion_blocks(repo):
    ready(repo)
    git(repo, "rm", "-q", "other/keep.py")

    code, _, err = _audit("module", repo, stop(repo))

    assert (code, "other/keep.py" in err) == (2, True)


# --- must-allow -------------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_in_scope_changes_pass_silently(flavour, repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "src" / "new.py").write_text("n = 1\n", encoding="utf-8")

    code, out, err = _audit(flavour, repo, stop(repo))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_stop_hook_active_never_re_blocks(flavour, repo):
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, err = _audit(flavour, repo, stop(repo, active=True))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_mode_off_does_not_audit(flavour, tmp_path):
    root = make_repo(tmp_path, mode="off")
    ready(root)
    (root / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, err = _audit(flavour, root, stop(root))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_report_mode_allows_the_stop_and_says_so(flavour, tmp_path):
    root = make_repo(tmp_path, mode="report")
    ready(root)
    (root / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, out, _ = _audit(flavour, root, stop(root))

    assert code == 0
    assert "other/made-by-sed.py" in json.loads(out)["systemMessage"]


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_no_active_ticket_is_not_audited(flavour, repo):
    make_ticket(repo, activate=False)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")

    code, _, _ = _audit(flavour, repo, stop(repo))

    assert code == 0


def test_the_tickets_own_directory_is_not_a_violation(repo):
    ready(repo)
    (repo / ".work" / "tickets" / "T-1" / "review.json").write_text("{}", encoding="utf-8")

    code, _, _ = _audit("module", repo, stop(repo))

    assert code == 0


def test_a_clean_tree_passes_even_without_approval(repo):
    make_ticket(repo)

    code, _, _ = _audit("module", repo, stop(repo))

    assert code == 0


# --- the /crew:done form -------------------------------------------------------------

def _check(root, ticket="T-1"):
    return subprocess.run([sys.executable, _AUDIT, "--check", "--ticket", ticket,
                           "--root", str(root)], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL)


def test_check_passes_on_in_scope_changes(repo):
    ready(repo)
    (repo / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")

    assert _check(repo).returncode == 0


def test_check_refuses_out_of_scope_changes_whatever_the_mode(tmp_path):
    root = make_repo(tmp_path, mode="off")
    ready(root)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")

    done = _check(root)

    assert (done.returncode, "other/keep.py" in done.stdout) == (1, True)


def test_check_refuses_a_bad_ticket_id(repo):
    assert _check(repo, "../x").returncode == 1


def test_check_is_a_failure_when_the_tree_cannot_be_diffed(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    assert _check(plain).returncode == 1


def test_audit_diffs_from_the_tickets_recorded_base(repo):
    (repo / "other" / "keep.py").write_text("x = 5\n", encoding="utf-8")
    git(repo, "commit", "-qam", "before the ticket")
    ready(repo)

    ok, _ = completion_audit.audit(str(repo), "T-1")

    assert ok is True and crew_ticket.status(str(repo), "T-1")["status"] == "approved"


# --- the wrappers, both hooks ---------------------------------------------------------

_WRAPPERS = ("scope-guard", "completion-audit")


def _resolver(path):
    src = pathlib.Path(path).read_text(encoding="utf-8")
    start = src.index("function Resolve-CrewPython {")
    return src[start:src.index("\n}\n", start) + 3]


@pytest.mark.parametrize("stem", _WRAPPERS)
def test_the_powershell_resolver_is_byte_for_byte_role_write_guards(stem):
    assert _resolver(os.path.join(SCRIPTS, stem + ".ps1")) == \
        _resolver(os.path.join(SCRIPTS, "role-write-guard.ps1"))


@pytest.mark.parametrize("stem", _WRAPPERS)
def test_the_flavour_guard_is_the_first_executable_statement(stem):
    lines = pathlib.Path(SCRIPTS, stem + ".ps1").read_text(encoding="utf-8").splitlines()
    code = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]

    assert code[code.index(")") + 1] == "if ($env:OS -ne 'Windows_NT') { exit 0 }"


@pytest.mark.parametrize("name", ["scope-guard.sh", "scope-guard.ps1", "scope_guard.py",
                                  "completion-audit.sh", "completion-audit.ps1",
                                  "completion_audit.py", "crew_ticket.py"])
def test_every_new_file_is_lf_only(name):
    assert b"\r" not in pathlib.Path(SCRIPTS, name).read_bytes()


@needs_pwsh
@pytest.mark.parametrize("stem", _WRAPPERS)
def test_the_powershell_flavour_stands_down_off_windows(stem, repo):
    ready(repo)
    (repo / "other" / "made-by-sed.py").write_text("y = 2\n", encoding="utf-8")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    env.pop("OS", None)
    payload = stop(repo) if stem == "completion-audit" else {
        "tool_name": "Write", "tool_input": {"file_path": str(repo / "other" / "x.py")},
        "cwd": str(repo)}

    done = subprocess.run([PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, stem + ".ps1")],
                          input=json.dumps(payload).encode(), cwd=str(repo),
                          capture_output=True, env=env, check=False, timeout=120)

    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")


def _broken_python(tmp_path):
    """A `python3` that passes the interpreter probe and then crashes."""
    folder = tmp_path / "fakebin"
    folder.mkdir()
    fake = folder / "python3"
    fake.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then echo "$0"; exit 0; fi\nexit 1\n',
                    encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    return folder


@pytest.mark.parametrize("stem", _WRAPPERS)
@pytest.mark.parametrize("shell", ["sh", "ps1"])
@pytest.mark.parametrize("mode,expected", [("block", 2), ("auto", 2), ("off", 0)])
def test_a_crashed_python_fails_closed_only_where_scope_is_armed(tmp_path, stem, shell,
                                                                 mode, expected):
    if shell == "ps1" and PWSH is None:
        pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
    root = make_repo(tmp_path, mode=mode)
    ready(root)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               PATH=os.pathsep.join([str(_broken_python(tmp_path)), "/usr/bin", "/bin"]))
    payload = stop(root) if stem == "completion-audit" else {
        "tool_name": "Write", "tool_input": {"file_path": str(root / "src" / "app.py")},
        "cwd": str(root)}
    cmd = ([PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, stem + ".ps1")]
           if shell == "ps1" else ["bash", os.path.join(SCRIPTS, stem + ".sh")])

    done = subprocess.run(cmd, input=json.dumps(payload).encode(), cwd=str(root),
                          capture_output=True, env=env, check=False, timeout=120)

    assert done.returncode == expected, done.stderr

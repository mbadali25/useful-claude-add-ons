"""scope_guard.py and the verify trust store (L-0888): a model-run command may
not grow or shrink the trust store, and no Write/Edit may touch it.

MUST-BLOCK: `verify_trust.py approve|allow-owner|disallow-owner|revoke` in
every spelling the `crew_ticket.py approve` cases cover (a path prefix, quoted
script name, `bash -c`, an options-first order, a bash backslash-newline or a
PowerShell backtick-newline continuation); a shell write naming
`verify-trust.json`; a Write/Edit of the store file.

MUST-ALLOW: `verify_trust.py status` and `check`, `check` chained before an
unrelated word, and a shell read of the store.
"""
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from scope_fixtures import FLAVOUR_MATRIX, make_repo, run_hook


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _shell(flavour, repo, command, tool="Bash"):
    return run_hook(flavour, "scope_guard", {"tool_name": tool, "cwd": str(repo),
                                             "tool_input": {"command": command}}, repo)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("verb", ["approve", "allow-owner github.com/x", "disallow-owner x",
                                  "revoke"])
def test_a_trust_store_change_is_refused(flavour, repo, verb):
    code, _, err = _shell(flavour, repo, f"python3 hooks/scripts/verify_trust.py {verb}")

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool,command", [
    pytest.param("Bash", "python3 /p/verify_trust.py --root . approve --yes", id="options-first"),
    pytest.param("Bash", "python3 '/p/verify_trust.py' approve", id="quoted"),
    pytest.param("Bash", "bash -c 'python3 verify_trust.py approve'", id="bash-c"),
    pytest.param("Bash", "VERIFY=1 python3 verify-trust.py revoke", id="dashed"),
    pytest.param("Bash", "python3 /p/verify_trust\\\n.py approve", id="bash-continuation-name"),
    pytest.param("Bash", "python3 /p/verify_trust.py \\\napprove", id="bash-continuation-verb"),
    pytest.param("PowerShell", "& python verify_trust.py `\n  approve", id="ps-continuation"),
    pytest.param("PowerShell", "python verify_trust.py allow-owner github.com/x --yes",
                 id="ps-plain"),
    pytest.param("Bash", "python3 -c \"import verify_trust as v; v.main(['approve','--yes'])\"",
                 id="import-main"),
    pytest.param("Bash", "python3 -c 'from verify_trust import update_store; update_store(p, f)'",
                 id="import-update-store"),
    pytest.param("Bash", "python3 -m verify_trust allow-owner github.com/a --yes", id="dash-m"),
])
def test_a_spelled_out_trust_change_is_refused(flavour, repo, tool, command):
    code, _, err = _shell(flavour, repo, command, tool)

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "python3 hooks/scripts/verify_trust.py status",
    "python3 hooks/scripts/verify_trust.py check --root .",
    "python3 hooks/scripts/verify_trust.py check; echo approve",
    "python3 -c 'import verify_trust as v; print(v.evaluate(\".\").code)'",
    "cat ~/.claude/crew/verify-trust.json",
])
def test_a_read_only_trust_command_is_allowed(flavour, repo, command):
    code, _, err = _shell(flavour, repo, command)

    assert (code, err) == (0, "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "echo '{}' > ~/.claude/crew/verify-trust.json",
    "cp /tmp/mine.json ~/.claude/crew/verify-trust.json",
])
def test_a_shell_write_of_the_store_is_refused(flavour, repo, command):
    code, _, err = _shell(flavour, repo, command)

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_a_write_or_edit_of_the_store_is_refused(flavour, repo, tool, tmp_path):
    store = os.path.join(str(tmp_path), "home", ".claude", "crew", "verify-trust.json")

    code, _, err = run_hook(flavour, "scope_guard", {
        "tool_name": tool, "cwd": str(repo), "tool_input": {"file_path": store}}, repo)

    assert (code, "SCOPE GUARD" in err) == (2, True)

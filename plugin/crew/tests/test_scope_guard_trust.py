"""scope_guard.py and the verify trust store (L-0888): a model-run command may
not grow or shrink the trust store, and no Write/Edit may touch it.

MUST-BLOCK: `verify_trust.py approve|allow-owner|disallow-owner|revoke` in
every spelling the `crew_ticket.py approve` cases cover (a path prefix, quoted
script name, `bash -c`, an options-first order, a bash backslash-newline or a
PowerShell backtick-newline continuation); a shell write naming
`verify-trust.json`; a Write/Edit of the store file.

A verb or a store path the command builds as it runs (round 4, L-0888): a
variable or substitution where the verb goes, string pieces joined, a dynamic
import beside the plugin scripts, a call into the module's writers, the store
override, a CLAUDECODE unset, and a write of a `verify-*` file under crew's
config directory.

A verb handed to a script by any name (round 7, L-0888): the verb word after `-`
(a script on stdin, by redirect, pipe or here-string), after a copy of the script
under another name, or after a wildcard script path; and a wildcard script path
given a variable where the verb goes.

MUST-ALLOW: `verify_trust.py status` and `check`, `check` chained before an
unrelated word, `check --root "$PWD"` (the variable follows the literal verb),
and a shell read of the store.
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
    pytest.param("Bash", "python3 hooks/scripts/verify_trust.py --yes approve",
                 id="flags-before-verb"),
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
    pytest.param("Bash", "python3 -c \"-1 'revoke'; import verify_trust\"",
                 id="verb-before-import"),
    pytest.param("Bash", "python3 verify_trust.py ap''prove --yes", id="empty-quotes-in-verb"),
    pytest.param("Bash", 'python3 verify_trust.py "approve" --yes', id="double-quoted-verb"),
    pytest.param("Bash", "python3 verify_trust.py app\\rove --yes", id="backslash-in-verb"),
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
    'python3 hooks/scripts/verify_trust.py check --root "$PWD"',
    "python3 hooks/scripts/verify_trust.py status --root $(pwd)",
    "grep -n approve plugin/crew/hooks/scripts/verify_trust.py",
    "python3 hooks/scripts/verify_trust.py check --root /tmp/approve",
    "python3 hooks/scripts/verify_trust.py status --root=/work/revoke/repo",
    "python3 hooks/scripts/verify_trust.py check --root ~/allow-owner/x",
])
def test_a_read_only_trust_command_is_allowed(flavour, repo, command):
    code, _, err = _shell(flavour, repo, command)

    assert (code, err) == (0, "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    pytest.param("python3 - approve --yes < plugin/crew/hooks/scripts/verify_trust.py",
                 id="verb-before-script-stdin-redirect"),
    pytest.param("cat plugin/crew/hooks/scripts/verify_trust.py | python3 - approve --yes",
                 id="verb-before-script-stdin-pipe"),
    pytest.param("python3 - allow-owner github.com/x --yes <<< \"$(cat verify_trust.py)\"",
                 id="verb-before-script-here-string"),
    pytest.param("python3 /dev/stdin revoke < verify_trust.py", id="dev-stdin"),
    pytest.param("python3 hooks/scripts/verify_t*st.py approve --yes", id="glob-in-script-name"),
    pytest.param("python3 hooks/scripts/verify_tru?st.py allow-owner github.com/x",
                 id="question-glob-in-script-name"),
    pytest.param("python3 hooks/scripts/v*.py disallow-owner github.com/x", id="short-glob"),
    pytest.param("python3 hooks/scripts/verify_t*st.py $V --yes", id="glob-script-variable-verb"),
    pytest.param("cp plugin/crew/hooks/scripts/verify_trust.py /tmp/x.py && python3 /tmp/x.py approve",
                 id="copy-under-another-name"),
    pytest.param("./hooks/scripts/verify_t*st.py approve --yes", id="executable-glob"),
    pytest.param("cd /tmp && ./x.py allow-owner github.com/x --yes", id="executable-copy"),
])
def test_a_verb_handed_to_a_script_by_any_name_is_refused(flavour, repo, command):
    code, _, err = _shell(flavour, repo, command)

    assert (code, "SCOPE GUARD" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    "python3 - check --root . < plugin/crew/hooks/scripts/verify_trust.py",
    "python3 hooks/scripts/verify_t*st.py status",
    "python3 -m pytest -k approve plugin/crew/tests",
    "python3 -m pytest plugin/crew/tests/test_*.py -q",
    "python3 tests/run.py --root approve",
    "grep -n approve plugin/crew/hooks/scripts/*.py",
    "echo approve | python3 -c 'import sys; print(sys.stdin.read())'",
])
def test_a_command_with_a_verb_word_that_is_not_the_verb_is_allowed(flavour, repo, command):
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


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_trust_change_is_refused_even_with_the_scope_guard_off(flavour, repo):
    crew = repo / ".crew"
    crew.mkdir(exist_ok=True)
    (crew / "config.json").write_text('{"scope": {"mode": "off"}}', encoding="utf-8")

    code, _, err = _shell(flavour, repo, "python3 hooks/scripts/verify_trust.py approve --yes")

    assert (code, "SCOPE GUARD" in err) == (2, True)


_ROUND4_ATTACK = (
    "part=trust; export CREW_VERIFY_TRUST_FILE=\"$HOME/.claude/crew/verify-$part.json\"; "
    "python3 -c 'import verify_trust; verify_trust.main([\"a\"+\"pprove\",\"--root\",\".\","
    "\"--yes\"])'")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("command", [
    pytest.param(_ROUND4_ATTACK, id="round-4-repro"),
    pytest.param("v=approve; python3 hooks/scripts/verify_trust.py $v --yes", id="variable-verb"),
    pytest.param("python3 hooks/scripts/verify_trust.py $(echo approve) --yes", id="subst-verb"),
    pytest.param("python3 hooks/scripts/verify_trust.py `echo approve` --yes", id="backtick-verb"),
    pytest.param("python3 hooks/scripts/verify_trust.py appro* --yes", id="glob-verb"),
    pytest.param("python3 hooks/scripts/verify_trust.py --root . $V", id="variable-after-options"),
    pytest.param("python3 -c 'import verify_trust as v; w = \"\".join([\"app\", \"rove\"])'",
                 id="join-verb"),
    pytest.param("python3 -c 'import verify_trust as v; v.cmd_approve(a)'", id="writer-call"),
    pytest.param("python3 -c 'import verify_trust as v,sys; v.main(sys.argv[1:])' x",
                 id="main-from-argv"),
    pytest.param("python3 -c 'm=__import__(\"verify_\"+\"trust\"); m.main([])'",
                 id="dynamic-module-name"),
    pytest.param("python3 -c 'import importlib; importlib.import_module(\"verify_\"+\"x\")'"
                 " --path hooks/scripts", id="importlib-beside-scripts"),
    pytest.param("CREW_VERIFY_TRUST_FILE=/tmp/s.json python3 hooks/scripts/verify_trust.py status",
                 id="store-override"),
    pytest.param("unset CLAUDECODE; python3 hooks/scripts/verify_trust.py status",
                 id="session-var-unset"),
    pytest.param("env -u CLAUDECODE python3 verify_trust.py check", id="session-var-env-u"),
    pytest.param("python3 -c 'open(\"/root/.claude/crew/verify-\"+\"x.json\",\"w\").write(\"{}\")'",
                 id="store-dir-write"),
])
def test_a_runtime_built_trust_change_is_refused(flavour, repo, command):
    code, _, err = _shell(flavour, repo, command)

    assert (code, "SCOPE GUARD" in err) == (2, True)

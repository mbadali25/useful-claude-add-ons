"""The owner's files past what the shell check reads (crew 1.3.149).

The check reads a command three levels deep, a bounded number of commands, and a bounded length. Each of those
limits used to end in silence: text nested a fourth level down was passed unread (`bash -c` four deep around a
redirect to the machine config), and a command slow enough to be killed by the dispatcher was allowed wherever
the repo is not armed. This file pins the other answer: what is not read is refused unless it plainly cannot be
the owner's, what cannot be read in time is refused, and a check that fails on its own input refuses.

Everything runs in a throwaway home; no real config is read or written.
"""
import json
import os
import sys
import time

import pytest

from test_guards_master import _armed, _run, _tool, _unarmed, blocked  # noqa: F401  pylint: disable=unused-import
from test_guards_master_shell import _home  # noqa: F401  pylint: disable=unused-import

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "scripts"))

import scope_guard  # noqa: E402  pylint: disable=wrong-import-position

OWNER = "~/.claude/crew/config.json"
RECEIPT = "~/.claude/crew/confirm-config/cc-ab12.json"


@pytest.fixture(name="bare")
def _bare(unarmed, monkeypatch):
    """The root of a repo with `scope.mode` off, judged in process with its throwaway home as the home."""
    root, home = unarmed
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)
    return root


def _refusal(command, cwd=None):
    return scope_guard._owner_command_refusal(command, cwd)  # pylint: disable=protected-access


def nested(levels, inner, shell="bash -c"):
    """`inner` handed to `shell` `levels` times over, each level quoted for the one outside it."""
    for _ in range(levels):
        inner = f"{shell} {json.dumps(inner)}"
    return inner


def mixed(levels, inner):
    """`inner` nested `levels` deep in single quotes where it holds none, in double quotes where it does."""
    for _ in range(levels):
        inner = f"bash -c {json.dumps(inner)}" if "'" in inner else f"bash -c '{inner}'"
    return inner


def idiom(levels, inner):
    """`inner` nested `levels` deep in single quotes alone, each inner quote mark spelled `'\\''`."""
    for _ in range(levels):
        inner = "bash -c '" + inner.replace("'", "'\\''") + "'"
    return inner


# --- (A) what is nested past the limit is not passed unread -------------------------------------------------------

NESTED_WRITES = (
    [nested(levels, f"echo x > {OWNER}") for levels in (1, 2, 3, 4, 5, 8)]
    + [mixed(levels, f"echo x > {OWNER}") for levels in (4, 5, 8)]
    + [nested(4, f"cp /tmp/x {RECEIPT}"),
       nested(5, f"tee {OWNER}", shell="sh -c"),
       nested(4, f"Set-Content {OWNER} x", shell="pwsh -Command"),
       nested(5, f"Set-Content {OWNER} x", shell="powershell -Command"),
       nested(2, nested(3, f"Set-Content {OWNER} x", shell="pwsh -Command")),
       nested(4, f"echo x > {OWNER}", shell="cmd /c"),
       "$(" * 5 + f"echo x > {OWNER}" + ")" * 5,
       "$(" * 8 + f"echo x > {OWNER}" + ")" * 8,
       "iex " * 5 + f"'Set-Content {OWNER} x'",
       f"trap \"trap 'trap \\\"trap \\\\\\\"echo x > {OWNER}\\\\\\\" EXIT\\\" EXIT' EXIT\" EXIT",
       "bash <<EOF\n" + mixed(3, f"echo x > {OWNER}") + "\nEOF",
       "echo " + json.dumps(mixed(3, f"echo x > {OWNER}")) + " | bash",
       # a path the shell would fill in: nobody read it to tell where it points
       nested(4, "echo x > $TARGET"),
       "bash -c 'bash -c \"bash -c \\\"bash -c \\\\\\\"echo x > $(cat where.txt)\\\\\\\"\\\"\"'",
       "$(" * 5 + "cat where.txt" + ")" * 5,
       nested(4, "echo x > ~/.c*/cr*/config.json"),
       nested(5, "rm -rf `cat where.txt`"),
       # the folder is named where the guard does read, the write is where it does not
       "cd ~/.claude/crew && " + nested(4, "echo x > config.json"),
       "cat " + OWNER + "; cd \"$(pwd)\"; " + nested(4, "echo x > config.json")])


@pytest.mark.parametrize("command", NESTED_WRITES)
def test_a_write_nested_past_what_the_guard_reads_is_refused(command, home):
    assert home and _refusal(command), command


# a command found inside another without a shell between them: a script block, what follows one, an alias, find -exec
INNER_WRITES = (
    "if ($a) { 1 } elseif ($b) { 2 } elseif ($c) { 3 } elseif ($d) { 4 } elseif ($e) { 5 } "
    "else { Set-Content " + OWNER + " x }",
    "alias a=b; alias b=c; alias c=d; alias d=e; alias e=f; alias f=tee; echo x | a " + OWNER,
    "if (1) { 1 } elseif (2) { 2 } elseif (3) { 3 } elseif (4) { 4 } elseif (5) { 5 } else { Remove-Item " + RECEIPT
    + " }",
)


@pytest.mark.parametrize("command", INNER_WRITES)
def test_a_block_or_an_alias_past_the_limit_is_refused(command, home):
    assert home and _refusal(command), command


def test_a_path_spelled_only_after_its_variables_are_filled_in_is_refused(home):
    """Nothing in the command as written spells the owner's folder; the text that reaches the limit does."""
    for inner in ("echo x > ~/$A$B", "tee ~/$A$B"):
        command = "A=.claude/cr; B=ew/config.json; " + nested(4, inner)
        assert not scope_guard._plausible(command)  # pylint: disable=protected-access
        assert home and _refusal(command), command


def test_a_variable_in_unread_text_is_refused_though_nothing_names_the_owner(home):
    command = nested(4, "echo x > $TARGET")
    assert not scope_guard._plausible(command)  # pylint: disable=protected-access
    assert home and _refusal(command), command


def test_a_read_of_the_owners_file_beside_an_unread_write_is_refused(home):
    """The command names the owner's folder only in a read, so it is no hint (`_owner_hint`); the write that
    could be aimed there is the part nobody read."""
    command = "cat " + OWNER + "; cd \"$(pwd)\"; " + nested(4, "echo x > config.json")
    assert not scope_guard._owner_hint(command)  # pylint: disable=protected-access
    assert home and _refusal(command), command


QUOTE_IDIOM_WRITES = (
    "echo 'it'\\''s' > " + OWNER,
    "printf '%s' 'a'\\''b' | tee " + RECEIPT,
    idiom(2, f"echo x > {OWNER}"),
    idiom(3, f"echo x > {OWNER}"),
    idiom(5, f"echo x > {OWNER}"),
    "bash -c 'bash -c \"bash -c '\\''echo x > " + OWNER + "'\\''\"'",
)


@pytest.mark.parametrize("command", QUOTE_IDIOM_WRITES)
def test_a_quote_mark_spelled_with_a_backslash_does_not_hide_the_write(command, home):
    """`'it'\\''s'` is one word to bash. The splitter pairs the marks differently and loses the redirect that
    follows (allowed at any depth before, the plain `echo 'it'\\''s' > <file>` included), so a command that
    quotes this way and names the owner's folder is refused without being split."""
    assert home and _refusal(command), command


@pytest.mark.parametrize("command", ["echo 'it'\\''s' > /tmp/out.txt",
                                     "git commit -m 'don'\\''t' && echo $?",
                                     idiom(5, "echo hello > /tmp/out.txt"),
                                     "cat " + OWNER + " | grep 'a.b'"])
def test_the_same_quoting_beside_another_file_is_allowed(command, home):
    assert home and _refusal(command) is None, command


NESTED_ELSEWHERE = (
    [nested(levels, "echo hello > /tmp/out.txt") for levels in (4, 5, 8)]
    + [mixed(levels, "echo hello > /tmp/out.txt") for levels in (4, 5, 8)]
    + [nested(5, "git status --short"),
       nested(4, "Set-Content C:/tmp/out.txt x", shell="pwsh -Command"),
       nested(4, "echo x > out.txt", shell="cmd /c"),
       'echo "$(basename "$(dirname "$(readlink -f "$(which python)")")")"',
       "if (1) { 1 } elseif (2) { 2 } elseif (3) { 3 } elseif (4) { 4 } elseif (5) { 5 } else { Write-Output done }",
       "alias a=b; alias b=c; alias c=d; alias d=e; alias e=f; alias f=tee; echo x | a /tmp/out.txt",
       "echo " + json.dumps(mixed(3, "echo hello > /tmp/out.txt")) + " | bash",
       # three levels are read: a variable there is followed as before
       nested(3, "echo x > $TARGET"),
       nested(3, "cat " + OWNER)])


@pytest.mark.parametrize("command", NESTED_ELSEWHERE)
def test_deep_nesting_that_names_nothing_of_the_owners_is_allowed(command, home):
    assert home and _refusal(command) is None, command


@pytest.mark.parametrize("levels", [1, 2, 3, 4, 5, 8])
def test_the_dispatcher_refuses_the_nested_write_in_both_scope_modes(levels, armed, tmp_path):
    """The review's repro, end to end: refused at one to three levels before, allowed at four."""
    import record_golden_hooks as rgh  # pylint: disable=import-outside-toplevel
    command = nested(levels, f"echo x > {OWNER}")
    root, home = armed
    assert blocked(_run("PreToolUse", _tool("Bash", command=command), root, home)), command
    bare_root, bare_home = rgh.build_repo(str(tmp_path / "bare"), False)
    assert blocked(_run("PreToolUse", _tool("Bash", command=command), bare_root, bare_home)), command
    posh = nested(levels, f"Set-Content {OWNER} x", shell="pwsh -Command")
    assert blocked(_run("PreToolUse", _tool("PowerShell", command=posh), bare_root, bare_home)), posh


def test_the_dispatcher_allows_benign_deep_nesting_in_both_scope_modes(armed, tmp_path):
    import record_golden_hooks as rgh  # pylint: disable=import-outside-toplevel
    root, home = armed
    bare_root, bare_home = rgh.build_repo(str(tmp_path / "bare"), False)
    for command in (nested(4, "echo hello"), nested(5, "echo hello"), mixed(4, "echo hello > out.txt")):
        assert not blocked(_run("PreToolUse", _tool("Bash", command=command), root, home)), command
        assert not blocked(_run("PreToolUse", _tool("Bash", command=command), bare_root, bare_home)), command


# --- (B) what cannot be read in the time a hook has is refused, not timed out -------------------------------------

def test_a_command_longer_than_the_guard_reads_is_refused(home):
    limit = scope_guard._COMMAND_LIMIT  # pylint: disable=protected-access
    assert home and _refusal("echo " + "x" * limit)
    assert _refusal("echo " + "x" * (limit - 5)) is None
    assert scope_guard._store_write("echo " + "x" * limit)  # pylint: disable=protected-access


def test_a_long_command_is_refused_before_anything_reads_it(bare, monkeypatch, capsys):
    """Reading is the cost: twenty levels of `bash -c` are seven million characters, and the trust check alone
    took longer over them than the hook is given."""
    root = bare

    def read(*_args, **_kwargs):
        raise AssertionError("the long command was read")

    monkeypatch.setattr(scope_guard, "trust_refusal", read)
    monkeypatch.setattr(scope_guard, "_joined", read)
    command = "echo " + "x" * scope_guard._COMMAND_LIMIT  # pylint: disable=protected-access
    for tool in ("Bash", "PowerShell"):
        assert scope_guard.decide({"tool_name": tool, "cwd": root, "tool_input": {"command": command}}) == 2
    assert "longer than the guard reads" in capsys.readouterr().err


@pytest.mark.wallclock
def test_twenty_levels_of_nesting_are_refused_well_inside_the_hooks_limit(armed, tmp_path):
    """The review's slow case: more than 20 s before, against a 15 s limit after which the dispatcher kills the
    guard and, in a repo that is not armed, allows the call."""
    import record_golden_hooks as rgh  # pylint: disable=import-outside-toplevel
    command = nested(20, f"echo x > {OWNER}")
    assert len(command) > 2_000_000
    bare_root, bare_home = rgh.build_repo(str(tmp_path / "bare"), False)
    for root, home in (armed, (bare_root, bare_home)):
        started = time.monotonic()
        result = _run("PreToolUse", _tool("Bash", command=command), root, home)
        elapsed = time.monotonic() - started
        assert blocked(result), result[2][-300:]
        assert elapsed < 10, elapsed


@pytest.mark.wallclock
def test_a_variable_that_doubles_with_every_command_is_refused_in_time(home):
    """`A=$A$A` thirty times is a 225-character command and a gigabyte of value: 4.6 s at twenty-six doublings by
    measurement before, and twice that for each one more."""
    for doublings in (22, 30, 60):
        command = "A=1;" + "A=$A$A;" * doublings + "echo x > $A"
        started = time.monotonic()
        assert home and _refusal(command), doublings
        assert time.monotonic() - started < 5, doublings
    assert _refusal("A=1;" + "A=$A$A;" * 10 + "echo x > /tmp/$A") is None


@pytest.mark.wallclock
def test_more_commands_than_the_guard_judges_are_refused_in_time(home):
    limit = scope_guard._STEP_LIMIT  # pylint: disable=protected-access
    for command in ("true;" * (limit + 500), "x|" * (limit + 500) + "x"):
        assert len(command) <= scope_guard._COMMAND_LIMIT  # pylint: disable=protected-access
        started = time.monotonic()
        assert home and _refusal(command), command[:40]
        assert time.monotonic() - started < 10, command[:40]
    assert _refusal("true;" * 2000) is None


def test_the_dispatcher_refuses_what_the_guard_cannot_finish_in_both_scope_modes(armed, tmp_path):
    import record_golden_hooks as rgh  # pylint: disable=import-outside-toplevel
    command = "A=1;" + "A=$A$A;" * 40 + "echo x > $A"
    root, home = armed
    assert blocked(_run("PreToolUse", _tool("Bash", command=command), root, home))
    bare_root, bare_home = rgh.build_repo(str(tmp_path / "bare"), False)
    assert blocked(_run("PreToolUse", _tool("Bash", command=command), bare_root, bare_home))


# --- (C) a check that fails on its own input refuses ---------------------------------------------------------------

def _boom(*_args, **_kwargs):
    raise RuntimeError("the check failed on its input")


def test_a_shell_check_that_raises_refuses_the_command(home, monkeypatch):
    monkeypatch.setattr(scope_guard, "_segments", _boom)
    reason = _refusal("echo hello")
    assert home and reason and "RuntimeError" in reason
    assert reason.startswith(scope_guard.OWNER_REASON)
    store_write = scope_guard._store_write  # pylint: disable=protected-access
    assert store_write("echo x > ~/.claude/crew/confirm-config/x.json") is True


@pytest.mark.parametrize("tool, tool_input", [
    ("Bash", {"command": "echo hello"}),
    ("PowerShell", {"command": "Write-Output hello"}),
    ("Write", {"file_path": "notes.txt", "content": "x"}),
    ("Edit", {"file_path": "notes.txt", "old_string": "a", "new_string": "b"})])
def test_the_owner_file_check_refuses_when_it_cannot_judge_with_scope_mode_off(tool, tool_input, bare,
                                                                               monkeypatch, capsys):
    """`main` allows what it could not judge when `scope.mode` is off, so the owner's-files rule, the one rule
    left in that mode, must not hand it an exception."""
    root = bare
    data = {"tool_name": tool, "cwd": root, "tool_input": tool_input}
    assert scope_guard.decide(data) == 0
    monkeypatch.setattr(scope_guard, "_owner_files_decision", _boom)
    assert scope_guard.decide(data) == 2
    assert "could not tell whether this" in capsys.readouterr().err


def test_a_path_that_cannot_be_resolved_is_the_owners(home, monkeypatch):
    assert home and scope_guard._owner_target(str(home / "notes.txt")) is False  # pylint: disable=protected-access
    monkeypatch.setattr(scope_guard.role_write_guard, "_resolve_real_target", _boom)
    assert scope_guard._owner_target(str(home / "notes.txt")) is True  # pylint: disable=protected-access


@pytest.mark.parametrize("tool, tool_input, broken", [("Bash", {"command": "echo hello"}, "_joined"),
                                                      ("Write", {"file_path": "notes.txt", "content": "x"}, "targets")])
def test_the_trust_check_refuses_when_it_cannot_judge(tool, tool_input, broken, bare, monkeypatch, capsys):
    root = bare
    data = {"tool_name": tool, "cwd": root, "tool_input": tool_input}
    assert scope_guard.trust_refusal(data) is None
    monkeypatch.setattr(scope_guard, broken, _boom)
    reason = scope_guard.trust_refusal(data)
    assert reason and "RuntimeError" in reason
    assert scope_guard.decide(data) == 2
    assert "could not tell whether it changes the verify trust store" in capsys.readouterr().err

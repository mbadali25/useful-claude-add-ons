"""AutoClear inside a pmux / psmux pane on native Windows.

psmux is a native Windows tmux clone (`pmux`, `psmux` and `tmux` are one
program). Verified on psmux 3.4.0: it sets `$TMUX` and `$TMUX_PANE` in the
pane's shell, `display-message -p -t %N '#{pane_pid}'` returns a Windows pid
that is an ancestor of the session, and `send-keys -l` + `Enter` reach a
raw-mode console program. What was missing was on crew's side:

  1. native Windows has no /proc, so no process could be read and the pane was
     never an ancestor of the hook: every pane was refused;
  2. Git Bash rewrote the `/clear` argument of the native tmux.exe into
     `C:/Program Files/Git/clear`.

Must-fire: a bound session whose pane pid is an ancestor sends. Must-not-fire:
another pane, a parent session in between (the tty comparison does not exist on
Windows, so a `node` host between the session and the pane refuses), a reused
parent pid, a start-time mismatch, an unreadable process snapshot.

Nothing here reads the real process table or sends a keystroke; the Windows
snapshot and start-time readers are replaced, so it also runs off Windows.
"""
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle as ac
import crew_fixtures as cf

SESSION = "55555555-eeee-4eee-8eee-000000000005"
HOOK, CLAUDE, PANE_SHELL, SERVER = 7_100_001, 7_100_002, 7_100_003, 7_100_004
OTHER_PANE = 7_100_090
START = 134386720630118107
_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access


def _windows(monkeypatch, snapshot, starts=None, tmp_path=None):
    """Make crew_autocycle read `snapshot` {pid: (ppid, exe)} as native Windows."""
    starts = starts or {}
    monkeypatch.delenv("CREW_AUTOCLEAR_PROC_STUB", raising=False)
    monkeypatch.setattr(ac, "_native_windows", lambda: True)
    monkeypatch.setattr(ac, "_read_stat", lambda pid: None)
    monkeypatch.setattr(ac, "_win_snapshot", lambda: snapshot)
    monkeypatch.setattr(ac, "_win_start", starts.get)
    monkeypatch.setattr(ac, "_start_pid", lambda: HOOK)
    if tmp_path is not None:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))


def _pane_tree(extra=None):
    """hook (python) -> claude -> pane shell (pane pid) -> psmux server."""
    table = {HOOK: (CLAUDE, "python.exe"), CLAUDE: (PANE_SHELL, "claude.exe"),
             PANE_SHELL: (SERVER, "bash.exe"), SERVER: (0, "pmux.exe")}
    table.update(extra or {})
    return table


def _starts():
    return {HOOK: str(START + 10), CLAUDE: str(START), PANE_SHELL: "200", SERVER: "100"}


def _bind(tmp_path, pane_pid, snapshot=None, starts=None, proc_start=START):
    cf.write_session_record(tmp_path / "cfg", SESSION, CLAUDE, proc_start=proc_start)
    owner = ac.session_owner(SESSION, {"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")})
    got = {"method": "tmux", "target": "%1", "label": "%1", "pane_pid": pane_pid}
    return owner, got, ac.prove_target(owner, got) if "pid" in owner else None


# --- the Windows process reader --------------------------------------------------

def test_windows_reader_gives_comm_without_exe_a_console_tty_and_the_filetime(monkeypatch):
    _windows(monkeypatch, _pane_tree(), _starts())

    assert ac._proc(CLAUDE) == {"ppid": PANE_SHELL, "tty": 1, "start": str(START),  # pylint: disable=protected-access
                                "comm": "claude"}


def test_windows_reader_is_none_for_a_pid_that_is_not_running(monkeypatch):
    _windows(monkeypatch, _pane_tree(), _starts())

    assert ac._proc(7_199_999) is None  # pylint: disable=protected-access
    assert ac._gone(7_199_999) is True  # pylint: disable=protected-access
    assert ac._gone(CLAUDE) is False  # pylint: disable=protected-access


def test_an_unreadable_snapshot_is_unread_not_gone(monkeypatch):
    _windows(monkeypatch, None)

    assert ac._proc(CLAUDE) is None  # pylint: disable=protected-access
    assert ac._gone(CLAUDE) is False  # pylint: disable=protected-access


def test_a_parent_pid_reused_after_the_child_started_is_not_the_parent(monkeypatch):
    starts = _starts()
    starts[PANE_SHELL] = str(START + 5)  # the "parent" began after claude did

    _windows(monkeypatch, _pane_tree(), starts)

    assert ac._proc(CLAUDE)["ppid"] == 0  # pylint: disable=protected-access


def test_off_windows_the_windows_reader_is_never_consulted(monkeypatch):
    monkeypatch.delenv("CREW_AUTOCLEAR_PROC_STUB", raising=False)
    monkeypatch.setattr(ac, "_native_windows", lambda: False)
    monkeypatch.setattr(ac, "_read_stat", lambda pid: None)
    monkeypatch.setattr(ac, "_proc_windows", lambda pid: pytest.fail("windows reader used off Windows"))
    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no ps")))

    assert ac._proc(CLAUDE) is None  # pylint: disable=protected-access


@pytest.mark.skipif(os.name != "nt", reason="the live Win32 snapshot only exists on Windows")
def test_the_live_snapshot_describes_this_process():
    mine = ac._proc(os.getpid())  # pylint: disable=protected-access

    assert mine["ppid"] == os.getppid() and mine["tty"] == 1 and mine["start"].isdigit()
    assert ac.ancestry()[0][:2] == [os.getpid(), os.getppid()]


# --- must fire ---------------------------------------------------------------------

def test_a_bound_session_in_a_pmux_pane_is_proven_and_would_send(tmp_path, monkeypatch):
    _windows(monkeypatch, _pane_tree(), _starts(), tmp_path)
    cf.write_session_record(tmp_path / "cfg", SESSION, CLAUDE, proc_start=START)
    monkeypatch.setenv("TMUX", "C:/Users/x/.psmux/psmux-1/default,1,0")
    monkeypatch.setenv("TMUX_PANE", "%1")
    monkeypatch.setattr(ac.shutil, "which", lambda name: "C:/bin/tmux.exe" if name == "tmux" else None)
    monkeypatch.setattr(ac, "_tmux_pane_pid", lambda pane: PANE_SHELL)

    got = ac.resolve_method({"method": "auto"})
    owner = ac.session_owner(SESSION)
    proven = ac.prove_target(owner, got)

    assert (got["method"], got["pane_pid"]) == ("tmux", PANE_SHELL)
    assert ac.classify(owner)[0] == "terminal"
    assert proven["ok"] is True and proven["target"] == "%1", proven


# --- must not fire -------------------------------------------------------------------

def test_another_pane_is_refused(tmp_path, monkeypatch):
    _windows(monkeypatch, _pane_tree({OTHER_PANE: (SERVER, "bash.exe")}), _starts(), tmp_path)

    _owner, _got, proven = _bind(tmp_path, OTHER_PANE)

    assert proven["ok"] is False and "is not an ancestor" in proven["reason"], proven


def test_a_pane_pid_of_zero_is_refused(tmp_path, monkeypatch):
    _windows(monkeypatch, _pane_tree(), _starts(), tmp_path)

    _owner, _got, proven = _bind(tmp_path, 0)

    assert proven["ok"] is False


@pytest.mark.parametrize("comm", ["node.exe", "bun.exe", "claude.exe"])
def test_a_parent_session_host_between_the_session_and_the_pane_is_refused(tmp_path, monkeypatch, comm):
    """The tty comparison cannot run on Windows, so a process that can host a
    Claude Code CLI between this session and the pane stops the typing."""
    parent = 7_100_050
    table = _pane_tree({CLAUDE: (parent, "claude.exe"), parent: (PANE_SHELL, comm)})
    starts = _starts()
    starts[parent] = "250"
    _windows(monkeypatch, table, starts, tmp_path)

    _owner, _got, proven = _bind(tmp_path, PANE_SHELL)

    assert proven["ok"] is False and "another Claude Code session" in proven["reason"], proven


def test_a_plain_shell_between_the_session_and_the_pane_is_allowed(tmp_path, monkeypatch):
    middle = 7_100_050
    table = _pane_tree({CLAUDE: (middle, "claude.exe"), middle: (PANE_SHELL, "bash.exe")})
    starts = _starts()
    starts[middle] = "250"
    _windows(monkeypatch, table, starts, tmp_path)

    _owner, _got, proven = _bind(tmp_path, PANE_SHELL)

    assert proven["ok"] is True, proven


def test_a_record_for_a_reused_pid_is_not_this_session(tmp_path, monkeypatch):
    _windows(monkeypatch, _pane_tree(), _starts(), tmp_path)

    owner, _got, proven = _bind(tmp_path, PANE_SHELL, proc_start=START + 1)

    assert "reused pid" in owner["unknown"] and proven is None


def test_without_a_readable_snapshot_nothing_is_proven(tmp_path, monkeypatch):
    _windows(monkeypatch, None, {}, tmp_path)
    cf.write_session_record(tmp_path / "cfg", SESSION, CLAUDE, proc_start=START)

    owner = ac.session_owner(SESSION)

    assert "unknown" in owner and ac.classify(owner)[0] == "unknown"


# --- the sender ----------------------------------------------------------------------

def _source():
    with open(os.path.join(_SCRIPTS, "auto-clear.sh"), encoding="utf-8") as handle:
        return handle.read()


def test_the_clear_sender_stops_git_bash_rewriting_the_slash_command():
    """Verified in a pmux pane: without it `/clear` is typed as
    `C:/Program Files/Git/clear`. It must be set before the first send-keys."""
    text = _source()
    block = text[text.index("    tmux)\n"):text.index("    xdotool)\n")]

    assert re.search(r"export MSYS_NO_PATHCONV=1", block)
    assert block.index("MSYS_NO_PATHCONV") < block.index("send-keys")


def test_the_resume_sender_stops_git_bash_rewriting_the_slash_command():
    text = _source()
    block = text[text.index("<<'SENDER'"):text.index('tmux send-keys -t "$PANE" -l')]

    assert "export MSYS_NO_PATHCONV=1" in block


def test_the_platform_table_offers_tmux_on_both_windows_rows():
    from crew_platform import _AUTOCLEAR_METHODS as table  # pylint: disable=import-outside-toplevel
    assert "tmux" in table["windows"] and "tmux" in table["windows-bash"]
    assert json.dumps(table["windows"]).count("sendkeys") == 0

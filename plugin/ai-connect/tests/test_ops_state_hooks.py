"""The peer-state hooks in Claude Code's settings: state_hooks.py, and installer.py's claude / unregister.

They are written by whatever registers the MCP server, not shipped in
hooks/hooks.json (tests/test_client_hooks.py says why). Adding them runs
again after every plugin update, into a file that belongs to the user and
holds their own hooks, so this suite is about what must NOT change: nothing
is duplicated, nothing foreign is touched or removed, and a file that is not
valid settings is left exactly as it was.

The installer runs as a subprocess with a fake `claude` first on PATH, a tmp
HOME and a tmp CLAUDE_CONFIG_DIR. No real settings file is read or written.
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import installer
import state_hooks

PLUGIN = Path(__file__).resolve().parents[1]
EVENTS = ["UserPromptSubmit", "PostToolUse", "Notification", "Stop"]

# A user's own settings: other keys, other events, and their own hooks on the events ours go to
FOREIGN = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(~/.ssh/**)"]},
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo pre"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "echo stopped", "timeout": 5}]}],
        "PostToolUse": [
            {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "fmt"}]},
            # Look like ours without being ours: another server, another tool, a command that names the tool
            {"hooks": [{"type": "mcp_tool", "server": "other", "tool": "peer_set_state", "input": {"state": "busy"}}]},
            {"hooks": [{"type": "mcp_tool", "server": "ai-connect", "tool": "peer_set_status", "input": {}}]},
            {"hooks": [{"type": "command", "command": "echo ai-connect peer_set_state"}]},
        ],
    },
    "env": {"UMLAUT": "größer"},
}


def ours(settings: dict) -> dict[str, list]:
    """event -> our hooks found there."""
    found = {}
    for event, groups in settings.get("hooks", {}).items():
        hooks = [hook for group in groups for hook in group.get("hooks", []) if state_hooks.is_state_hook(hook)]
        if hooks:
            found[event] = hooks
    return found


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- what is written


def test_the_four_state_hooks_report_only_a_state():
    """The Bridge learns busy / idle / waiting, never the text of a prompt or of a permission request."""
    assert list(state_hooks.STATE_HOOKS) == EVENTS
    states = {}
    for event, group in state_hooks.STATE_HOOKS.items():
        (hook,) = group["hooks"]
        assert state_hooks.is_state_hook(hook)
        assert set(hook) == {"type", "server", "tool", "input"} and set(hook["input"]) == {"state"}
        assert "${" not in json.dumps(group)
        states[event] = hook["input"]["state"]
    assert states == {"UserPromptSubmit": "busy", "PostToolUse": "busy", "Notification": "waiting", "Stop": "idle"}
    assert state_hooks.STATE_HOOKS["Notification"]["matcher"] == "permission_prompt"


def test_the_hooks_name_the_server_the_installer_registers():
    assert installer.MCP_SERVER == state_hooks.MCP_SERVER == "ai-connect"


def test_user_settings_follow_claude_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert state_hooks.user_settings_path() == tmp_path / "elsewhere" / "settings.json"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert state_hooks.user_settings_path() == Path.home() / ".claude" / "settings.json"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")  # set but empty is not a directory
    assert state_hooks.user_settings_path() == Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------- add


def test_add_creates_a_missing_file_with_exactly_the_four_hooks(tmp_path):
    path = tmp_path / "new" / "settings.json"
    assert state_hooks.add(path) is True
    assert load(path) == {"hooks": {event: [group] for event, group in state_hooks.STATE_HOOKS.items()}}
    assert path.read_text(encoding="utf-8").endswith("}\n")


def test_add_keeps_every_other_hook_and_key(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(FOREIGN, indent=4), encoding="utf-8")
    assert state_hooks.add(path) is True
    after = load(path)
    assert state_hooks.without_state_hooks(after) == FOREIGN  # nothing of theirs changed, in value or order
    assert list(after) == list(FOREIGN)
    for event, groups in FOREIGN["hooks"].items():
        assert after["hooks"][event][:len(groups)] == groups  # theirs first, as they were; ours after
    assert ours(after) == {event: group["hooks"] for event, group in state_hooks.STATE_HOOKS.items()}
    assert "größer" in path.read_text(encoding="utf-8")  # not escaped into \\u sequences


def test_add_twice_changes_nothing_the_second_time(tmp_path):
    """The installer runs again after every plugin update."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(FOREIGN), encoding="utf-8")
    state_hooks.add(path)
    first = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    for _ in range(3):
        assert state_hooks.add(path) is False
    assert path.read_bytes() == first and path.stat().st_mtime_ns == stamp  # not even rewritten
    assert {event: len(hooks) for event, hooks in ours(load(path)).items()} == dict.fromkeys(EVENTS, 1)
    assert state_hooks.present(path)


def test_add_replaces_an_entry_an_older_version_wrote(tmp_path):
    """Ours in another arrangement (twice, on another event, with other input) end up as the one set."""
    stale = copy.deepcopy(FOREIGN)
    busy = state_hooks.STATE_HOOKS["PostToolUse"]["hooks"][0]
    stale["hooks"]["PostToolUse"] += [{"hooks": [busy]}, {"hooks": [busy]}]
    stale["hooks"]["SessionStart"] = [{"hooks": [{**busy, "input": {"state": "idle", "detail": "old"}}]}]
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(stale), encoding="utf-8")
    assert not state_hooks.present(path)
    assert state_hooks.add(path) is True
    after = load(path)
    assert ours(after) == {event: group["hooks"] for event, group in state_hooks.STATE_HOOKS.items()}
    assert state_hooks.without_state_hooks(after) == FOREIGN


def test_ours_inside_a_group_with_a_foreign_hook_leaves_that_hook(tmp_path):
    """A user who merged their hook into our group keeps it, with the group's matcher."""
    theirs = {"type": "command", "command": "notify-send waiting"}
    mixed = {"hooks": {"Notification": [
        {"matcher": "permission_prompt", "hooks": [theirs, state_hooks.STATE_HOOKS["Notification"]["hooks"][0]]}]}}
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(mixed), encoding="utf-8")
    state_hooks.add(path)
    assert load(path)["hooks"]["Notification"] == [
        {"matcher": "permission_prompt", "hooks": [theirs]}, state_hooks.STATE_HOOKS["Notification"]]
    state_hooks.remove(path)
    assert load(path) == {"hooks": {"Notification": [{"matcher": "permission_prompt", "hooks": [theirs]}]}}


# ---------------------------------------------------------------- remove


def test_remove_takes_only_ours_and_leaves_the_file_as_it_was_before_add(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(FOREIGN), encoding="utf-8")
    state_hooks.add(path)
    assert state_hooks.holds_any(path)
    assert state_hooks.remove(path) is True
    assert load(path) == FOREIGN and list(load(path)["hooks"]) == list(FOREIGN["hooks"])
    assert state_hooks.remove(path) is False and not state_hooks.holds_any(path)


def test_remove_after_add_on_a_fresh_file_leaves_no_empty_hooks_behind(tmp_path):
    path = tmp_path / "settings.json"
    state_hooks.add(path)
    state_hooks.remove(path)
    assert load(path) == {}


def test_remove_never_creates_a_file_and_never_rewrites_one_without_ours(tmp_path):
    missing = tmp_path / "none" / "settings.json"
    assert state_hooks.remove(missing) is False and not missing.parent.exists()
    path = tmp_path / "settings.json"
    text = json.dumps(FOREIGN, indent=7) + "\n\n"  # their own formatting
    path.write_text(text, encoding="utf-8")
    assert state_hooks.remove(path) is False
    assert path.read_text(encoding="utf-8") == text
    empty = tmp_path / "empty.json"
    empty.write_text('{"hooks": {}}', encoding="utf-8")
    assert state_hooks.remove(empty) is False and empty.read_text(encoding="utf-8") == '{"hooks": {}}'


def test_only_an_exact_match_on_type_server_and_tool_is_ours():
    hook = state_hooks.STATE_HOOKS["Stop"]["hooks"][0]
    assert state_hooks.is_state_hook(hook)
    for other in ({**hook, "server": "plugin:ai-connect:ai-connect"}, {**hook, "server": "AI-Connect"},
                  {**hook, "tool": "peer_set_status"}, {**hook, "type": "command"},
                  {"type": "command", "command": "ai-connect peer_set_state mcp_tool"}, "peer_set_state", None, []):
        assert not state_hooks.is_state_hook(other), other


# ---------------------------------------------------------------- a file that is not settings


@pytest.mark.parametrize("text", [
    "{ not json", "", '{"hooks": {"Stop": [}', "[1, 2]", '"settings"', '{"hooks": []}', '{"hooks": null}',
    '{"hooks": {"Stop": {"hooks": []}}}',
])
def test_a_file_that_is_not_settings_is_refused_and_left_alone(tmp_path, text):
    path = tmp_path / "settings.json"
    path.write_text(text, encoding="utf-8")
    for step in (state_hooks.add, state_hooks.remove, state_hooks.present, state_hooks.holds_any, state_hooks.read):
        with pytest.raises(state_hooks.SettingsError) as refused:
            step(path)
        assert str(path) in str(refused.value) and "not changed" in str(refused.value)
    assert path.read_text(encoding="utf-8") == text
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]  # no temp file left either


def test_a_write_that_cannot_be_done_is_a_settings_error_and_changes_nothing(tmp_path):
    """Not a traceback after the MCP server is already registered: one line the installer can exit with."""
    path = tmp_path / "settings.json"
    text = '{"env": {"X": "\\ud83d"}}'  # a lone surrogate: valid JSON, not writable as UTF-8
    path.write_text(text, encoding="utf-8")
    with pytest.raises(state_hooks.SettingsError, match="not changed"):
        state_hooks.add(path)
    assert path.read_text(encoding="utf-8") == text
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_remove_runs_without_the_venv_for_an_uninstall_after_a_plugin_update(tmp_path):
    """install.sh --uninstall has no venv then, so no installer.py: state_hooks.py alone, standard library only."""
    config_dir = tmp_path / "claude"
    path = config_dir / "settings.json"
    config_dir.mkdir()
    path.write_text(json.dumps(FOREIGN), encoding="utf-8")
    state_hooks.add(path)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(CLAUDE_CONFIG_DIR=str(config_dir), HOME=str(tmp_path), USERPROFILE=str(tmp_path))

    def run(*args):
        # -I -S: no site-packages, so a third-party import in state_hooks.py would fail here
        return subprocess.run([sys.executable, "-I", "-S", str(PLUGIN / "state_hooks.py"), *args], env=env,
                              capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=60)
    first = run("remove")
    assert first.returncode == 0 and "removed" in first.stdout, first.stderr
    assert load(path) == FOREIGN
    assert run("remove").returncode == 0 and load(path) == FOREIGN
    assert run("add").returncode == 2 and run().returncode == 2  # removing is all it offers
    path.write_text("{", encoding="utf-8")
    refused = run("remove")
    assert refused.returncode == 1 and "not valid JSON" in refused.stderr and path.read_text(encoding="utf-8") == "{"


def test_both_install_scripts_remove_the_state_hooks_when_the_venv_is_gone():
    """The pair: each uninstall falls back to state_hooks.py remove, and neither starts a bare pwsh."""
    for name in ("install.sh", "install.ps1"):
        text = (PLUGIN / name).read_text(encoding="utf-8")
        assert "state_hooks.py" in text and "remove" in text and "python3" in text and "py" in text, name
        assert "claude mcp remove -s user ai-connect" in text, name


def test_odd_but_valid_groups_are_passed_over(tmp_path):
    """Entries this does not understand inside a valid file are not ours to judge: kept as they are."""
    odd = {"hooks": {"Stop": ["a string", {"hooks": "not a list"}, {"no": "hooks"}, 7], "PreToolUse": []}}
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(odd), encoding="utf-8")
    state_hooks.add(path)
    assert state_hooks.without_state_hooks(load(path)) == odd
    state_hooks.remove(path)
    assert load(path) == odd


# ---------------------------------------------------------------- how it is written


def test_the_file_is_written_whole_then_moved_into_place(tmp_path, monkeypatch):
    """Never opened for writing itself: a write that fails leaves the old settings, not an empty file."""
    path = tmp_path / "settings.json"
    before = json.dumps(FOREIGN)
    path.write_text(before, encoding="utf-8")
    moved = []
    real_replace = os.replace

    def replace(src, dst):
        # At the moment of the move the new file is complete and the old one untouched
        assert json.loads(Path(src).read_text(encoding="utf-8"))["hooks"]["Stop"]
        assert Path(dst).read_text(encoding="utf-8") == before
        moved.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(state_hooks.os, "replace", replace)
    state_hooks.add(path)
    assert len(moved) == 1
    src, dst = moved[0]
    assert dst == path and src.parent == path.parent and src != path
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


def test_a_failed_write_leaves_the_old_file_and_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    before = json.dumps(FOREIGN)
    path.write_text(before, encoding="utf-8")

    def fail(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(state_hooks.os, "replace", fail)
    with pytest.raises(state_hooks.SettingsError, match="disk full"):
        state_hooks.add(path)
    assert path.read_text(encoding="utf-8") == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.json"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits and symlinks")
def test_a_linked_settings_file_stays_a_link_and_keeps_its_mode(tmp_path):
    """A settings.json linked into a dotfiles checkout is written through the link, not replaced by a file."""
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    real.write_text("{}", encoding="utf-8")
    real.chmod(0o640)
    link = tmp_path / "claude" / "settings.json"
    link.parent.mkdir()
    link.symlink_to(real)
    state_hooks.add(link)
    assert link.is_symlink() and state_hooks.present(real)
    assert real.stat().st_mode & 0o777 == 0o640


def test_a_byte_order_mark_is_read(tmp_path):
    """Windows PowerShell 5.1's Set-Content -Encoding UTF8 writes one."""
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(FOREIGN).encode("utf-8"))
    assert state_hooks.add(path) is True
    assert state_hooks.without_state_hooks(load(path)) == FOREIGN


# ---------------------------------------------------------------- installer.py claude / unregister


class Machine:
    """A HOME, a CLAUDE_CONFIG_DIR and a PATH whose `claude` is a fake that logs its arguments."""

    def __init__(self, tmp_path: Path):
        self.home = tmp_path / "home"
        self.config_dir = tmp_path / "claude-config"
        self.bin = tmp_path / "bin"
        for path in (self.home, self.config_dir, self.bin):
            path.mkdir()
        self.settings = self.config_dir / "settings.json"
        self.log = tmp_path / "claude-calls.jsonl"
        fake = tmp_path / "fake_claude.py"
        fake.write_text(
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            f"open({str(self.log)!r}, 'a', encoding='utf-8').write(json.dumps(args) + '\\n')\n"
            "if args[:2] == ['mcp', 'remove']:\n"
            "    print('No MCP server named \"ai-connect\" found', file=sys.stderr)\n"
            "    sys.exit(1)\n"
            "if args[:2] == ['mcp', 'add']:\n"
            "    sys.exit(int(os.environ.get('FAKE_CLAUDE_ADD_RC', '0')))\n"
            "sys.exit(64)\n", encoding="utf-8")
        if os.name == "nt":
            (self.bin / "claude.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
        else:
            shim = self.bin / "claude"
            shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n', encoding="utf-8")
            shim.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "FAKE_CLAUDE_ADD_RC")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), CLAUDE_CONFIG_DIR=str(self.config_dir),
                        PATH=os.pathsep.join([str(self.bin), *(["/usr/bin", "/bin"] if os.name != "nt" else
                                                               [r"C:\Windows\System32", r"C:\Windows"])]),
                        PYTHONIOENCODING="utf-8")

    def installer(self, step: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(PLUGIN / "installer.py"), step], capture_output=True, text=True,
                              check=False, stdin=subprocess.DEVNULL, env=dict(self.env, **env), timeout=120,
                              cwd=self.home)

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def without_claude(self) -> None:
        for path in self.bin.iterdir():
            path.unlink()


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


def test_installer_claude_registers_the_server_then_writes_the_hooks(machine):
    result = machine.installer("claude")
    assert result.returncode == 0, result.stdout + result.stderr
    assert [call[:2] for call in machine.calls()] == [["mcp", "remove"], ["mcp", "add"]]
    add = machine.calls()[1]
    assert add[2:6] == ["-s", "user", "ai-connect", "--"] and add[-1] == str(PLUGIN / "client" / "server.py")
    assert state_hooks.present(machine.settings)
    assert str(machine.settings) in result.stdout and "State hooks" in result.stdout
    assert not (machine.home / ".claude").exists()  # CLAUDE_CONFIG_DIR, not the default beside it


def test_installer_claude_without_claude_config_dir_uses_home(machine):
    env = dict(machine.env)
    del env["CLAUDE_CONFIG_DIR"]
    machine.env = env
    assert machine.installer("claude").returncode == 0
    assert state_hooks.present(machine.home / ".claude" / "settings.json") and not machine.settings.exists()


def test_installer_claude_keeps_foreign_hooks_and_is_idempotent(machine):
    machine.settings.write_text(json.dumps(FOREIGN, indent=2), encoding="utf-8")
    assert machine.installer("claude").returncode == 0
    first = machine.settings.read_bytes()
    assert state_hooks.without_state_hooks(load(machine.settings)) == FOREIGN
    again = machine.installer("claude")  # as after a plugin update
    assert again.returncode == 0 and "already" in again.stdout
    assert machine.settings.read_bytes() == first
    assert {event: len(hooks) for event, hooks in ours(load(machine.settings)).items()} == dict.fromkeys(EVENTS, 1)


def test_installer_unregister_removes_only_ours(machine):
    machine.settings.write_text(json.dumps(FOREIGN, indent=2), encoding="utf-8")
    machine.installer("claude")
    result = machine.installer("unregister")
    assert result.returncode == 0, result.stdout + result.stderr
    assert load(machine.settings) == FOREIGN
    assert "State hooks removed" in result.stdout
    assert machine.calls()[-1][:2] == ["mcp", "remove"]


def test_installer_unregister_without_a_settings_file_creates_none(machine):
    assert machine.installer("unregister").returncode == 0
    assert not machine.settings.exists()


def test_installer_unregister_removes_the_hooks_even_without_the_claude_cli(machine):
    """They are in a file; without the server they would only fail."""
    machine.installer("claude")
    machine.without_claude()
    result = machine.installer("unregister")
    assert result.returncode == 0, result.stdout + result.stderr
    assert load(machine.settings) == {}


@pytest.mark.parametrize("step", ["claude", "unregister"])
def test_installer_refuses_invalid_settings_before_touching_anything(machine, step):
    machine.settings.write_text('{"hooks": {"Stop": [', encoding="utf-8")
    result = machine.installer(step)
    assert result.returncode != 0
    assert str(machine.settings) in result.stderr and "not valid JSON" in result.stderr
    assert "not changed" in result.stderr
    assert machine.settings.read_text(encoding="utf-8") == '{"hooks": {"Stop": ['
    assert machine.calls() == []  # no server registered or removed beside hooks that could not be
    assert sorted(p.name for p in machine.config_dir.iterdir()) == ["settings.json"]


def test_installer_writes_no_hooks_when_the_server_could_not_be_registered(machine):
    """Hooks without their server are the error this is all about."""
    machine.settings.write_text(json.dumps(FOREIGN), encoding="utf-8")
    result = machine.installer("claude", FAKE_CLAUDE_ADD_RC="1")
    assert result.returncode != 0 and "claude mcp add failed" in result.stderr
    assert load(machine.settings) == FOREIGN


def test_installer_writes_no_hooks_when_claude_is_not_installed(machine):
    machine.without_claude()
    result = machine.installer("claude")
    assert result.returncode == 0 and "Claude Code not found" in result.stdout
    assert not machine.settings.exists()

"""The plugin's hooks say nothing on a machine where AI-Connect was never set up.

`claude plugin install` alone turns hooks/hooks.json on; the venv, the config
and the MCP server only exist once an installer ran. Until then every hook
must exit 0 with nothing on stdout or stderr, on every event. Up to 0.1.8 it
did not: four `mcp_tool` hooks reported "MCP server 'ai-connect' not
connected" on every prompt, tool call, permission request and turn end, and
the watcher exited 1 at every session start and turn end.

Three states, told apart by what the installer leaves outside the plugin
directory (~/.config/ai-connect/config.yaml) and inside it (venv):

- never set up (no config, no venv): silent, exit 0
- set up (config and venv): the watcher runs and its exit code comes through
- venv lost after a plugin update (config, no venv): exit 1, naming the fix

Each test builds a throwaway plugin root and HOME; nothing real is read.
The command lines are the ones in hooks/hooks.json, run as Claude Code runs
them. The PowerShell flavour runs here only where a PowerShell 7 is found,
and outside Windows only with OS=Windows_NT forced so that watch.ps1 does
not stand down: that exercises its branches, not Windows itself.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks" / "hooks.json"
WINDOWS = os.name == "nt"
PWSH = shutil.which("pwsh") or next(
    (p for p in (r"C:\Program Files\PowerShell\7\pwsh.exe", "/usr/bin/pwsh", "/usr/local/bin/pwsh",
                 "/opt/homebrew/bin/pwsh", "/snap/bin/pwsh") if os.path.isfile(p)), None)
# What the stub watcher prints and exits with: a wake, which only a watcher that really ran can produce
WOKEN = "stub watcher ran"
WAKE = 2


def hook_commands() -> list[tuple[str, dict]]:
    """Every hook in hooks.json as (event, hook)."""
    hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]
    return [(event, hook) for event, groups in hooks.items() for group in groups for hook in group["hooks"]]


def flavour(hook: dict) -> str:
    return hook.get("shell", "bash")


COMMANDS = hook_commands()
IDS = [f"{event}-{flavour(hook)}" for event, hook in COMMANDS]


class Machine:
    """A plugin root and a HOME that exist only for one test."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path / "plugin root"  # a space: the cache path has one on some machines
        self.home = tmp_path / "home"
        self.home.mkdir()
        shutil.copytree(ROOT / "hooks", self.root / "hooks")
        self.marker = tmp_path / "watcher-ran"

    def add_config(self) -> None:
        config = self.home / ".config" / "ai-connect" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("client:\n  name: test\n", encoding="utf-8")

    def add_venv(self) -> None:
        """A venv whose 'python' is a stub: it notes that the watcher was started, and with which script."""
        for relative in ("venv/bin/python", "venv/Scripts/python.exe"):
            stub = self.root / relative
            stub.parent.mkdir(parents=True)
            stub.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{self.marker}"\necho "{WOKEN}"\nexit {WAKE}\n',
                            encoding="utf-8", newline="\n")
            stub.chmod(0o755)

    def run(self, hook: dict, windows: bool) -> subprocess.CompletedProcess:
        """Run one hooks.json command line as Claude Code does: ${CLAUDE_PLUGIN_ROOT} filled in, then the
        flavour's shell. windows: answer as a Windows machine does ($OS is Windows_NT there)."""
        command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(self.root))
        env = {k: v for k, v in os.environ.items() if k not in ("OS", "CLAUDE_CONFIG_DIR", "AI_CONNECT_HOME")}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), CLAUDE_PLUGIN_ROOT=str(self.root),
                   # A private PowerShell startup cache: two pwsh sharing one can corrupt it (scripts/pwsh-isolated.sh)
                   XDG_CACHE_HOME=str(self.home / ".cache"))
        if windows:
            env["OS"] = "Windows_NT"
        if flavour(hook) == "powershell":
            argv = [PWSH, "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            argv = ["sh", "-c", command]
        return subprocess.run(argv, capture_output=True, text=True, check=False, env=env,
                              stdin=subprocess.DEVNULL, timeout=120)


def runs_here(hook: dict) -> bool:
    """Whether this flavour's own logic can be run on this machine (see the module docstring)."""
    if flavour(hook) == "powershell":
        return PWSH is not None
    return not WINDOWS


def need(hook: dict) -> None:
    if not runs_here(hook):
        why = "no PowerShell 7 found" if flavour(hook) == "powershell" else "Windows: watch.sh stands down"
        pytest.skip(f"the {flavour(hook)} flavour cannot be run here ({why})")


def as_windows(hook: dict) -> bool:
    """The flavour's own machine: watch.ps1 acts only on Windows, watch.sh only off it."""
    return flavour(hook) == "powershell"


# ---------------------------------------------------------------- hooks.json


def test_hooks_json_has_no_mcp_tool_hook():
    """An mcp_tool hook has no quiet mode: where its server is not registered it is an error on every
    event. The state hooks are written by whatever registers the server (state_hooks.py), never shipped here."""
    assert COMMANDS, "hooks.json lists no hook at all"
    assert [(event, hook) for event, hook in COMMANDS if hook.get("type") != "command"] == []
    assert "mcp_tool" not in HOOKS.read_text(encoding="utf-8")


def test_every_hook_command_is_one_of_the_two_watch_wrappers():
    """What the three-state tests below cover is everything hooks.json can run."""
    for _, hook in COMMANDS:
        script = "watch.ps1" if flavour(hook) == "powershell" else "watch.sh"
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/hooks/{script}"' in hook["command"], hook["command"]


# ---------------------------------------------------------------- never set up: silent


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_never_set_up_every_hook_is_silent(tmp_path, event, hook):  # pylint: disable=unused-argument
    """No config and no venv: exit 0, nothing on stdout, nothing on stderr."""
    need(hook)
    result = Machine(tmp_path).run(hook, windows=as_windows(hook))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_never_set_up_the_other_flavour_is_silent_too(tmp_path, event, hook):  # pylint: disable=unused-argument
    """Both flavours are registered for every event, so each also runs on the other's machine."""
    if flavour(hook) == "powershell" and PWSH is None:
        pytest.skip("no PowerShell 7 found")
    if flavour(hook) == "bash" and WINDOWS and shutil.which("sh") is None:
        pytest.skip("no sh on PATH")
    result = Machine(tmp_path).run(hook, windows=not as_windows(hook))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


# ---------------------------------------------------------------- set up: the watcher runs


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_set_up_the_watcher_runs_and_its_exit_code_comes_through(tmp_path, event, hook):  # pylint: disable=unused-argument
    """Config and venv: the venv's Python is started on the watcher, and its exit 2 (the wake) is the hook's."""
    need(hook)
    if WINDOWS:
        pytest.skip("the stub venv Python is a shell script")
    machine = Machine(tmp_path)
    machine.add_config()
    machine.add_venv()
    result = machine.run(hook, windows=as_windows(hook))
    assert (result.returncode, result.stdout.strip(), result.stderr) == (WAKE, WOKEN, "")
    started = Path(machine.marker.read_text(encoding="utf-8"))
    assert started == machine.root / "integrations" / "claude-code" / "aiconnect_watch.py"


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_a_venv_without_a_config_still_runs_the_watcher(tmp_path, event, hook):  # pylint: disable=unused-argument
    """Only the missing venv is ever excused. With one, the watcher runs and reports a missing config itself."""
    need(hook)
    if WINDOWS:
        pytest.skip("the stub venv Python is a shell script")
    machine = Machine(tmp_path)
    machine.add_venv()
    result = machine.run(hook, windows=as_windows(hook))
    assert result.returncode == WAKE and machine.marker.exists()


# ---------------------------------------------------------------- venv lost: loud


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_venv_lost_after_an_update_is_an_error_naming_the_fix(tmp_path, event, hook):  # pylint: disable=unused-argument
    """Config but no venv: this machine was set up, and the plugin directory changed under it."""
    need(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    result = machine.run(hook, windows=as_windows(hook))
    assert result.returncode == 1 and result.stdout == ""
    installer = "install.cmd" if flavour(hook) == "powershell" else "install.sh"
    assert "no venv at" in result.stderr and installer in result.stderr, result.stderr
    assert "after each plugin update" in result.stderr
    assert str(machine.root) in result.stderr  # the directory to run it in: the cache path is not guessable
    assert not machine.marker.exists()


def test_the_three_states_are_run_for_at_least_one_flavour():
    """A machine on which every case above is skipped has tested nothing: say so instead of passing."""
    assert any(runs_here(hook) for _, hook in COMMANDS), "neither hook flavour can be run on this machine"

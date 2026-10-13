"""The plugin's hooks say nothing on a machine where AI-Connect was never set up.

`claude plugin install` alone turns hooks/hooks.json on; the venv, the config
and the MCP server only exist once an installer ran. Until then every hook
must exit 0 with nothing on stdout or stderr, on every event. Up to 0.1.8 it
did not: four `mcp_tool` hooks reported "MCP server 'ai-connect' not
connected" on every prompt, tool call, permission request and turn end, and
the watcher exited 1 at every session start and turn end.

Three states, told apart by the config an installer leaves outside the plugin
directory (~/.config/ai-connect/config.yaml) and by a venv:

- never set up (no config, no venv): silent, exit 0
- set up (config and venv): the watcher runs and its exit code comes through
- venv lost after a plugin update (config, no venv): exit 1, naming the fix

A venv is looked for in three places, in order: AI_CONNECT_VENV, the plugin
directory (install.sh), and where deploy puts it, outside the plugin directory
(deploy.sh, setup.sh). The last section has one case per place and per order.

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
import sys
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
# The watcher script, relative to the plugin directory and to deploy's copy of it
WATCHER = Path("integrations", "claude-code", "aiconnect_watch.py")


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

    def __init__(self, tmp_path: Path, home: Path | None = None):
        self.tmp = tmp_path
        self.root = tmp_path / "plugin root"  # a space: the cache path has one on some machines
        # home: a fake machine's that is already there (deploy_box.Box makes its own)
        self.home = home or tmp_path / "home"
        self.home.mkdir(exist_ok=True)
        # pwsh's startup cache: the test's own, beside the home rather than under it (L-0557)
        self.xdg_cache = tmp_path / "xdg-cache"
        self.xdg_cache.mkdir(exist_ok=True)
        shutil.copytree(ROOT / "hooks", self.root / "hooks")
        self.marker = tmp_path / "watcher-ran"

    def add_config(self) -> None:
        config = self.home / ".config" / "ai-connect" / "config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("client:\n  name: test\n", encoding="utf-8")

    def inside(self, path: Path) -> Path:
        """path, once it is known to lie under this test's tmp dir: nothing is written anywhere else."""
        if not path.resolve().is_relative_to(self.tmp.resolve()):
            raise AssertionError(f"{path} is outside this test's tmp dir {self.tmp}")
        return path

    def add_venv(self, venv: Path | None = None, label: str = "own") -> None:
        """A venv whose 'python' is a stub: it notes which venv it is (label) and which script it was
        started on. venv: where, the plugin directory's own by default."""
        venv = self.inside(venv or self.root / "venv")
        for relative in ("bin/python", "Scripts/python.exe"):
            stub = venv / relative
            stub.parent.mkdir(parents=True)
            stub.write_text(f'#!/bin/sh\nprintf "%s\\n%s" "{label}" "$1" > "{self.marker}"\necho "{WOKEN}"\n'
                            f'exit {WAKE}\n', encoding="utf-8", newline="\n")
            stub.chmod(0o755)

    def deploy_home(self, hook: dict) -> Path:
        """Where deploy installs on the machine this flavour acts on (deploy_core.py's APP_HOME)."""
        parts = ("AppData", "Local") if flavour(hook) == "powershell" else (".local", "share")
        return self.home.joinpath(*parts, "ai-connect")

    def add_deployed_app(self, deploy_home: Path) -> Path:
        """Deploy's copy of the plugin, as far as the hook looks at it: the watcher script is there."""
        script = self.inside(deploy_home) / "app" / WATCHER
        script.parent.mkdir(parents=True)
        script.write_text("# never run: the venv's python is a stub\n", encoding="utf-8")
        return script

    def started(self) -> tuple[str, Path]:
        """Which venv's Python ran (its label), and the script it was given."""
        label, script = self.marker.read_text(encoding="utf-8").split("\n", 1)
        # watch.ps1 writes the script's path with backslashes, which only Windows reads as separators
        return label, Path(script if WINDOWS else script.replace("\\", "/"))

    def run(self, hook: dict, windows: bool, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        """Run one hooks.json command line as Claude Code does: ${CLAUDE_PLUGIN_ROOT} filled in, then the
        flavour's shell. windows: answer as a Windows machine does ($OS is Windows_NT there)."""
        command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(self.root))
        env = {k: v for k, v in os.environ.items()
               if k not in ("OS", "CLAUDE_CONFIG_DIR", "AI_CONNECT_HOME", "AI_CONNECT_VENV")}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), CLAUDE_PLUGIN_ROOT=str(self.root),
                   # A private PowerShell startup cache: two pwsh sharing one can corrupt it (scripts/pwsh-isolated.sh)
                   XDG_CACHE_HOME=str(self.xdg_cache))
        env.update(extra_env or {})
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
    assert machine.started() == ("own", machine.root / WATCHER)


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
    # Both places a venv is looked for are named, and the other way to get one
    deploy_venv, deploy = machine.deploy_home(hook) / "venv", "deploy.ps1" if as_windows(hook) else "deploy.sh"
    stderr = result.stderr if WINDOWS else result.stderr.replace("\\", "/")
    assert str(deploy_venv) in stderr and deploy in stderr, result.stderr


# ---------------------------------------------------------------- which venv: three places, in order
#
# 1. AI_CONNECT_VENV  2. the plugin directory's own (install.sh / install.cmd)  3. deploy's, outside the
# plugin directory (deploy.sh / setup.sh and their .ps1 twins). Up to 0.1.16 only the second was looked
# at, so on a machine deploy had set up the watcher exited 1 on every event and no session was ever woken.


def stubs(hook: dict) -> None:
    need(hook)
    if WINDOWS:
        pytest.skip("the stub venv Python is a shell script")


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_deploys_venv_runs_the_watcher_from_deploys_copy(tmp_path, event, hook):  # pylint: disable=unused-argument
    """The machine deploy set up: no venv in the plugin directory, one at deploy's place with the copy of
    the plugin beside it. The watcher runs, with that venv and from that copy."""
    stubs(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    home = machine.deploy_home(hook)
    machine.add_venv(home / "venv", "deploy")
    script = machine.add_deployed_app(home)
    result = machine.run(hook, windows=as_windows(hook))
    assert (result.returncode, result.stdout.strip(), result.stderr) == (WAKE, WOKEN, "")
    assert machine.started() == ("deploy", script)


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_deploys_venv_without_a_copy_runs_the_plugins_watcher(tmp_path, event, hook):  # pylint: disable=unused-argument
    """`deploy peer --install-hooks` alone makes the venv and no copy of the plugin."""
    stubs(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    machine.add_venv(machine.deploy_home(hook) / "venv", "deploy")
    result = machine.run(hook, windows=as_windows(hook))
    assert (result.returncode, result.stderr) == (WAKE, "")
    assert machine.started() == ("deploy", machine.root / WATCHER)


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_ai_connect_home_moves_deploys_place(tmp_path, event, hook):  # pylint: disable=unused-argument
    """AI_CONNECT_HOME is where deploy installs when it is set, and the default place is then not looked at."""
    stubs(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    moved = tmp_path / "moved home"
    machine.add_venv(moved / "venv", "moved")
    script = machine.add_deployed_app(moved)
    machine.add_venv(machine.deploy_home(hook) / "venv", "default")
    result = machine.run(hook, windows=as_windows(hook), extra_env={"AI_CONNECT_HOME": str(moved)})
    assert (result.returncode, result.stderr) == (WAKE, "")
    assert machine.started() == ("moved", script)


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_the_plugins_own_venv_comes_before_deploys(tmp_path, event, hook):  # pylint: disable=unused-argument
    """Both there: install.sh's layout is used as before, with the plugin's own watcher."""
    stubs(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    machine.add_venv()
    home = machine.deploy_home(hook)
    machine.add_venv(home / "venv", "deploy")
    machine.add_deployed_app(home)
    result = machine.run(hook, windows=as_windows(hook))
    assert (result.returncode, result.stderr) == (WAKE, "")
    assert machine.started() == ("own", machine.root / WATCHER)


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_ai_connect_venv_comes_first(tmp_path, event, hook):  # pylint: disable=unused-argument
    """All three there: AI_CONNECT_VENV's is used, on the plugin's own watcher."""
    stubs(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    named = tmp_path / "named venv"
    machine.add_venv(named, "named")
    machine.add_venv()
    home = machine.deploy_home(hook)
    machine.add_venv(home / "venv", "deploy")
    machine.add_deployed_app(home)
    result = machine.run(hook, windows=as_windows(hook), extra_env={"AI_CONNECT_VENV": str(named)})
    assert (result.returncode, result.stderr) == (WAKE, "")
    assert machine.started() == ("named", machine.root / WATCHER)


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_an_ai_connect_venv_with_no_python_falls_through(tmp_path, event, hook):  # pylint: disable=unused-argument
    """The variable names a directory without a venv: the next place that has one is used."""
    stubs(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    home = machine.deploy_home(hook)
    machine.add_venv(home / "venv", "deploy")
    script = machine.add_deployed_app(home)
    result = machine.run(hook, windows=as_windows(hook), extra_env={"AI_CONNECT_VENV": str(tmp_path / "nothing")})
    assert (result.returncode, result.stderr) == (WAKE, "")
    assert machine.started() == ("deploy", script)


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_set_up_and_no_venv_in_any_place_names_all_three(tmp_path, event, hook):  # pylint: disable=unused-argument
    """Config, and AI_CONNECT_VENV and AI_CONNECT_HOME both pointing at nothing: exit 1, each place named."""
    need(hook)
    machine = Machine(tmp_path)
    machine.add_config()
    named, moved = tmp_path / "nothing", tmp_path / "moved home"
    result = machine.run(hook, windows=as_windows(hook),
                         extra_env={"AI_CONNECT_VENV": str(named), "AI_CONNECT_HOME": str(moved)})
    assert result.returncode == 1 and result.stdout == ""
    stderr = result.stderr if WINDOWS else result.stderr.replace("\\", "/")
    for place in (named, machine.root / "venv", moved / "venv"):
        assert str(place) in stderr, result.stderr
    assert "AI_CONNECT_VENV" in stderr
    assert not machine.marker.exists()


@pytest.mark.parametrize(("event", "hook"), COMMANDS, ids=IDS)
def test_never_set_up_stays_silent_with_both_variables_set(tmp_path, event, hook):  # pylint: disable=unused-argument
    """No config and no venv anywhere: the variables alone do not make the hook speak."""
    need(hook)
    result = Machine(tmp_path).run(hook, windows=as_windows(hook),
                                   extra_env={"AI_CONNECT_VENV": str(tmp_path / "nothing"),
                                              "AI_CONNECT_HOME": str(tmp_path / "moved home")})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_deploys_place_is_the_one_deploy_core_computes(box):
    """Not a second copy of the path: deploy_core.py is asked, on deploy's own fake machine (deploy_box.Box),
    where it installs for that HOME, and watch.sh finds a venv put exactly there."""
    hook = next((hook for _, hook in COMMANDS if flavour(hook) == "bash"), None)
    assert hook is not None, "hooks.json has no bash watcher"
    stubs(hook)
    # The box names its own venv through AI_CONNECT_VENV; asked for here is where deploy puts one unasked
    env = {k: v for k, v in box.env.items() if k != "AI_CONNECT_VENV"}
    asked = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import deploy_core as d; "
                               "print(d.APP_HOME); print(d.VENV); print(d.APP)", str(ROOT / "deploy")],
        capture_output=True, text=True, check=True, env=env, stdin=subprocess.DEVNULL, timeout=60, cwd=box.project)
    app_home, venv, app = (Path(line) for line in asked.stdout.splitlines())
    machine = Machine(box.tmp, home=box.home)
    assert (app_home, venv, app) == (machine.deploy_home(hook), app_home / "venv", box.app)
    machine.add_config()
    machine.add_venv(venv, "deploy")
    script = machine.add_deployed_app(app_home)
    assert script == app / WATCHER
    result = machine.run(hook, windows=False)
    assert (result.returncode, result.stderr) == (WAKE, "")
    assert machine.started() == ("deploy", script)


def test_the_windows_place_is_still_the_one_deploy_core_spells():
    """watch.ps1's AppData\\Local cannot be asked of deploy_core.py off Windows. This is the tripwire
    instead: if the line that spells both places changes, the two watch wrappers have to follow."""
    source = (ROOT / "deploy" / "deploy_core.py").read_text(encoding="utf-8")
    assert '*(("AppData", "Local") if os.name == "nt" else (".local", "share")), "ai-connect"))' in source
    assert 'VENV = Path(os.environ.get("AI_CONNECT_VENV") or APP_HOME / "venv")' in source
    wrapper = (ROOT / "hooks" / "watch.ps1").read_text(encoding="utf-8")
    assert "'AppData') 'Local') 'ai-connect'" in wrapper and "$env:USERPROFILE" in wrapper


def test_the_three_states_are_run_for_at_least_one_flavour():
    """A machine on which every case above is skipped has tested nothing: say so instead of passing."""
    assert any(runs_here(hook) for _, hook in COMMANDS), "neither hook flavour can be run on this machine"

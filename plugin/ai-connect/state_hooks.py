"""The peer-state hooks (busy / idle / waiting) in a Claude Code settings file.

They are `mcp_tool` hooks that call this plugin's MCP server, and that hook
type has no quiet mode: where the server is not registered, each of them is
an error on every prompt, tool call, permission request and turn end. So
they are not in the plugin's hooks/hooks.json, which is active from
`claude plugin install` on. Whatever registers the MCP server writes them
next to that registration, and takes them out with it:

- installer.py claude / unregister: the user's settings.json
- deploy.py --register-mcp --install-hooks / uninstall: the user's
  settings.json for --scope user, the project's .claude/settings.local.json
  for --scope project (the server is then only in that project's .mcp.json)

Standard library only: deploy.py runs under the system Python, before there
is a venv.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from pathlib import Path

MCP_SERVER = "ai-connect"
STATE_TOOL = "peer_set_state"


class SettingsError(Exception):
    """A settings file that is not what this module can safely change; it was left as it is."""


def _state_hook(state: str) -> dict:
    return {"type": "mcp_tool", "server": MCP_SERVER, "tool": STATE_TOOL, "input": {"state": state}}


# Event -> the one matcher group kept there. Only the state goes to the
# Bridge, never the text of a prompt or of a permission request.
STATE_HOOKS: dict[str, dict] = {
    "UserPromptSubmit": {"hooks": [_state_hook("busy")]},
    "PostToolUse": {"hooks": [_state_hook("busy")]},
    "Notification": {"matcher": "permission_prompt", "hooks": [_state_hook("waiting")]},
    "Stop": {"hooks": [_state_hook("idle")]},
}


def user_settings_path() -> Path:
    """Claude Code's user settings: in CLAUDE_CONFIG_DIR when that is set, else ~/.claude."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json"


def project_settings_path(project: Path) -> Path:
    """A project's settings that are this machine's alone (Claude Code keeps the file out of git)."""
    return project / ".claude" / "settings.local.json"


def is_state_hook(hook: object) -> bool:
    """Whether a hook entry is one of ours: an mcp_tool call of our server's peer_set_state, nothing looser."""
    return (
        isinstance(hook, dict)
        and hook.get("type") == "mcp_tool"
        and hook.get("server") == MCP_SERVER
        and hook.get("tool") == STATE_TOOL
    )


def _has_state_hook(group: object) -> bool:
    inner = group.get("hooks") if isinstance(group, dict) else None
    return isinstance(inner, list) and any(is_state_hook(hook) for hook in inner)


def read(path: Path) -> dict | None:
    """The settings in path, None when there is no file yet.

    SettingsError for a file that is not JSON or not shaped like settings:
    the caller stops rather than rewrite something it does not understand.
    """
    if not path.exists():
        return None
    unchanged = "It was not changed. Repair it, then run this again."
    try:
        # utf-8-sig: Windows PowerShell 5.1 writes a byte order mark
        settings = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise SettingsError(f"{path} is not valid JSON ({error}).\n{unchanged}") from error
    problem = None
    if not isinstance(settings, dict):
        problem = "its top level is not an object"
    elif not isinstance(settings.get("hooks", {}), dict):
        problem = '"hooks" is not an object'
    else:
        for event, groups in settings.get("hooks", {}).items():
            if not isinstance(groups, list):
                problem = f'"hooks.{event}" is not a list'
                break
    if problem:
        raise SettingsError(f"{path}: {problem}.\n{unchanged}")
    return settings


def without_state_hooks(settings: dict) -> dict:
    """A copy of settings without our state hooks; every other hook and key as it was.

    A matcher group is dropped only when ours were its only hooks, an event
    only when that emptied it, and "hooks" itself only when that emptied it.
    """
    result = copy.deepcopy(settings)
    hooks = result.get("hooks")
    if not hooks:
        return result
    removed = False
    for event in list(hooks):
        if not any(_has_state_hook(group) for group in hooks[event]):
            continue
        removed = True
        kept = []
        for group in hooks[event]:
            if not _has_state_hook(group):
                kept.append(group)
                continue
            others = [hook for hook in group["hooks"] if not is_state_hook(hook)]
            if others:
                kept.append({**group, "hooks": others})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if removed and not hooks:
        del result["hooks"]
    return result


def has_state_hooks(settings: dict) -> bool:
    """Whether settings holds exactly one of each state hook, as this version writes them, and no other of ours."""
    hooks = settings.get("hooks") or {}
    ours = {event: [group for group in groups if _has_state_hook(group)] for event, groups in hooks.items()}
    return {event: groups for event, groups in ours.items() if groups} == {
        event: [group] for event, group in STATE_HOOKS.items()
    }


def with_state_hooks(settings: dict) -> dict:
    """A copy of settings with exactly one of each state hook.

    Whatever registers the MCP server runs again after every plugin update,
    so an entry that is already there is not added twice, and one from an
    older version is replaced.
    """
    if has_state_hooks(settings):
        return copy.deepcopy(settings)
    result = without_state_hooks(settings)
    for event, group in STATE_HOOKS.items():
        result.setdefault("hooks", {}).setdefault(event, []).append(copy.deepcopy(group))
    return result


def write(path: Path, settings: dict) -> None:
    """Write the settings whole: the full text first, then a temp file moved into place.

    Opening the file itself for writing would empty it before there is
    anything to put in, and a failure in between would leave Claude Code
    without its settings.
    """
    text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    # realpath: a settings.json that is a link into a dotfiles checkout stays one
    target = Path(os.path.realpath(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if target.exists():
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def present(path: Path) -> bool:
    """Whether path already holds the state hooks as add() would leave them."""
    settings = read(path)
    return settings is not None and has_state_hooks(settings)


def holds_any(path: Path) -> bool:
    """Whether path holds any state hook of ours, in whatever arrangement."""
    settings = read(path)
    return settings is not None and without_state_hooks(settings) != settings


def add(path: Path) -> bool:
    """Put the state hooks into path, creating the file when there is none. False when nothing had to change."""
    settings = read(path)
    if settings is not None and has_state_hooks(settings):
        return False
    write(path, with_state_hooks(settings or {}))
    return True


def remove(path: Path) -> bool:
    """Take our state hooks out of path. False when it held none (a missing file is never created)."""
    settings = read(path)
    if settings is None:
        return False
    updated = without_state_hooks(settings)
    if updated == settings:
        return False
    write(path, updated)
    return True

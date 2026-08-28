"""Shared vault-path resolution for every hook and command script in this plugin.

One function, because a vault path resolved two different ways in two different
scripts is how a guard ends up checking the wrong directory. Every hook here
imports this rather than re-deriving the path.

Resolution order, first hit wins:
  1. OBSIDIAN_VAULT_PATH env var - explicit override, always wins.
  2. ~/.claude/obsidian/config.json -> "vaultPath" - written once by /obsidian:init.
  3. The Obsidian app's own registry (obsidian.json) - the vault marked "open",
     or the newest by "ts" if none is. This is detection, not configuration: it
     answers "what vault does Obsidian itself think is current" without the user
     ever telling this plugin anything.
  4. None. Every caller must treat that as "do nothing, stay silent" - a hook
     that guesses a path and writes there is worse than a hook that no-ops.

No default vault path ships in this file. A hardcoded personal path is correct
for exactly one machine and wrong for everyone else who installs the plugin.
"""
import json
import os
import platform


def _home():
    """The user's home directory, HOME-first.

    os.path.expanduser("~") reads USERPROFILE on Windows, not HOME - so a
    caller (a test harness, a container, a user who sets HOME deliberately in
    Git Bash) that only overrides HOME is silently ignored on that platform.
    Checking HOME explicitly first makes the override behave the same way on
    every OS this plugin runs on.
    """
    return os.environ.get("HOME") or os.path.expanduser("~")


def config_path():
    return os.path.join(_home(), ".claude", "obsidian", "config.json")


def read_config():
    path = config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(data):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def obsidian_app_json_path():
    """Where the Obsidian desktop app records known vaults, per OS.

    Windows: %APPDATA%\\obsidian\\obsidian.json
    macOS:   ~/Library/Application Support/obsidian/obsidian.json
    Linux:   ~/.config/obsidian/obsidian.json (respects XDG_CONFIG_HOME)
    """
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or os.path.join(_home(), "AppData", "Roaming")
        return os.path.join(base, "obsidian", "obsidian.json")
    if system == "Darwin":
        return os.path.join(_home(), "Library", "Application Support", "obsidian", "obsidian.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home(), ".config")
    return os.path.join(base, "obsidian", "obsidian.json")


def detect_vault_from_app():
    """The vault Obsidian itself last had open, or the most recently touched one.

    Returns (path, vault_id) or (None, None). Never raises - a malformed or
    absent obsidian.json just means detection found nothing.
    """
    path = obsidian_app_json_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None, None
    vaults = data.get("vaults") if isinstance(data, dict) else None
    if not isinstance(vaults, dict) or not vaults:
        return None, None

    def ts(entry):
        try:
            return int(entry.get("ts", 0))
        except (TypeError, ValueError):
            return 0

    open_vaults = [(vid, v) for vid, v in vaults.items()
                   if isinstance(v, dict) and v.get("open") and v.get("path")]
    pool = open_vaults or [(vid, v) for vid, v in vaults.items()
                            if isinstance(v, dict) and v.get("path")]
    if not pool:
        return None, None
    vid, entry = max(pool, key=lambda kv: ts(kv[1]))
    return entry.get("path"), vid


def resolve_vault_path():
    """The vault path this session should act on, or None.

    Detection (source 3) is intentionally not cached back into config.json here -
    /obsidian:init is the only thing that writes config, so a hook never turns a
    one-time detection into a standing decision the user did not make.
    """
    env = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env and os.path.isdir(env):
        return env

    cfg = read_config()
    configured = cfg.get("vaultPath")
    if configured and os.path.isdir(configured):
        return configured

    detected, _ = detect_vault_from_app()
    if detected and os.path.isdir(detected):
        return detected

    return None


def rest_api_data_path(vault_path):
    return os.path.join(vault_path, ".obsidian", "plugins",
                         "obsidian-local-rest-api", "data.json")


def community_plugins_path(vault_path):
    return os.path.join(vault_path, ".obsidian", "community-plugins.json")

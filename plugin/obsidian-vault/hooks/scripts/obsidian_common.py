"""Shared vault resolution for every hook and command script in this plugin.

Supports multiple NAMED vaults - a user can have a primary memory vault and a
separate one (e.g. a graphify code-graph vault, which can run to hundreds of
thousands of notes) that must never be confused with each other, since each
has its own Local REST API port and, at that scale, its own performance
tradeoffs (see vault_layout / prefer_filesystem below).

Config shape, ~/.claude/obsidian/config.json:

    {
      "vaults": {
        "memory":     { "path": "C:\\...", "port": 27123, "default": true },
        "codegraphs": { "path": "C:\\...", "port": 27125, "layout": "org/repo" }
      },
      "guard": { ... }
    }

`layout` is free-form metadata for commands that need to know a vault's folder
convention (a code-graph vault laid out `<org>/<repo>/` is not addressed the
same way a flat note vault is) - it has no effect on resolution itself.

Legacy single-vault shape (`"vaultPath": "..."` at the top level, no `vaults`
key) is still read and treated as one vault named "memory", so a config
written by an earlier version of this plugin keeps working unmodified.

Resolution order for a given vault name, first hit wins:
  1. OBSIDIAN_VAULT_PATH env var - but ONLY for the default vault; an env
     override must not silently redirect a named non-default vault lookup.
  2. ~/.claude/obsidian/config.json -> vaults[name].path (or legacy
     "vaultPath" when name is the default and no `vaults` block exists).
  3. For the default vault only: the Obsidian app's own registry
     (obsidian.json) - the vault marked "open", or the newest by "ts". This is
     detection, not configuration, and only ever applies to the vault this
     plugin treats as primary - a named vault the user configured explicitly
     is never silently swapped for whatever Obsidian last had open.
  4. None. Every caller must treat that as "do nothing, stay silent" - a hook
     that guesses a path and writes there is worse than a hook that no-ops.

No default vault path ships in this file. A hardcoded personal path is correct
for exactly one machine and wrong for everyone else who installs the plugin.
"""
import json
import os
import platform
import sys


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


DEFAULT_PORT = 27123


def _valid_port(value, context):
    """A config `port` value is untrusted input from a hand-edited JSON file.

    A string, a float, or an out-of-range int reaching bridge_status.py's
    `https_port = http_port + 1` raises TypeError, which an outer
    `except Exception: sys.exit(0)` then swallows completely silently - a
    hook that reports nothing is worse than one that reports the wrong thing.
    Validate once, here, at load: on failure, print the defect to stderr
    (visible in the transcript even for a hook that must still exit 0) and
    fall back to DEFAULT_PORT rather than letting the bad value propagate.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        print(
            "obsidian-vault config: %s is not an integer (%r) - using default port %d"
            % (context, value, DEFAULT_PORT), file=sys.stderr,
        )
        return DEFAULT_PORT
    if not (1 <= value <= 65535):
        print(
            "obsidian-vault config: %s is out of range (%r) - using default port %d"
            % (context, value, DEFAULT_PORT), file=sys.stderr,
        )
        return DEFAULT_PORT
    return value


def list_vaults():
    """Every configured vault as {name: {path, port, layout, default}}.

    Normalizes the legacy single-vault shape into the same structure so every
    other function here only has to handle one shape. Entries with no usable
    path are dropped - a vault named in config that does not exist on disk is
    not a vault a caller should be handed.
    """
    cfg = read_config()
    raw = cfg.get("vaults")
    if isinstance(raw, dict) and raw:
        out = {}
        for name, entry in raw.items():
            if not isinstance(entry, dict) or not entry.get("path"):
                continue
            if not os.path.isdir(entry["path"]):
                # Declared in config but not there right now - a second vault
                # is commonly only mounted/open sometimes. Drop it rather than
                # handing every caller a path that will fail isdir again a
                # moment later; that filtering belongs in exactly one place.
                continue
            out[name] = {
                "path": entry["path"],
                "port": _valid_port(entry.get("port", DEFAULT_PORT), "vaults.%s.port" % name),
                "layout": entry.get("layout"),
                "default": entry.get("default") is True,
            }
        if out and not any(v["default"] for v in out.values()):
            # No surviving vault explicitly marked default (either none was,
            # or the one that was got dropped above): the first one declared
            # wins, deterministically, rather than leaving "which vault is
            # primary" undefined for every caller that asks.
            first = next(iter(out))
            out[first]["default"] = True
        return out

    legacy_path = cfg.get("vaultPath")
    if legacy_path and os.path.isdir(legacy_path):
        return {"memory": {"path": legacy_path, "port": DEFAULT_PORT,
                            "layout": None, "default": True}}

    # No config file at all yet - /obsidian-vault:init has never run. Still
    # surface whatever Obsidian itself last had open, the same way the
    # single-vault version of this plugin always did, so bridge-status has
    # something to report on a fresh install rather than going silent until
    # the user configures a vault it could already see.
    detected, _ = detect_vault_from_app()
    if detected and os.path.isdir(detected):
        return {"memory": {"path": detected, "port": DEFAULT_PORT,
                            "layout": None, "default": True}}
    return {}


def default_vault_name():
    vaults = list_vaults()
    for name, entry in vaults.items():
        if entry["default"]:
            return name
    return next(iter(vaults), None)


def _declared_default_entry():
    """The raw config entry for the default vault, ignoring whether its own
    configured `path` currently resolves on disk.

    Used only by the OBSIDIAN_VAULT_PATH override below: the env var replaces
    *where* the default vault lives, not *what port it runs on* - if it also
    reset the port to DEFAULT_PORT, a default vault configured on a
    non-standard port would silently probe the wrong port the moment someone
    set the env var, which is a worse bug than the one the env var exists to
    solve.
    """
    cfg = read_config()
    raw = cfg.get("vaults")
    if isinstance(raw, dict) and raw:
        for name, entry in raw.items():
            if isinstance(entry, dict) and entry.get("default") is True:
                return entry
        first = next(iter(raw.values()), None)
        return first if isinstance(first, dict) else None
    return None


def resolve_vault(name=None):
    """The full {path, port, layout} dict for a named vault, or None.

    `name=None` resolves the default vault, and is the only case where the
    env var and Obsidian's own registry are consulted - see the module
    docstring for why a named non-default vault never falls through to those.
    """
    vaults = list_vaults()
    is_default = name is None or name == default_vault_name()

    if is_default:
        env = os.environ.get("OBSIDIAN_VAULT_PATH")
        if env and os.path.isdir(env):
            declared = _declared_default_entry() or {}
            port = _valid_port(declared.get("port", DEFAULT_PORT), "vaults default port (env override)")
            return {"path": env, "port": port, "layout": declared.get("layout"), "default": True}

    target = name or default_vault_name()
    entry = vaults.get(target)
    if entry and os.path.isdir(entry["path"]):
        return entry

    if is_default:
        detected, _ = detect_vault_from_app()
        if detected and os.path.isdir(detected):
            return {"path": detected, "port": DEFAULT_PORT, "layout": None, "default": True}

    return None


def resolve_vault_path(name=None):
    """The vault path this session should act on, or None.

    Detection is intentionally not cached back into config.json here -
    /obsidian-vault:init is the only thing that writes config, so a hook never
    turns a one-time detection into a standing decision the user did not make.
    """
    entry = resolve_vault(name)
    return entry["path"] if entry else None


def rest_api_data_path(vault_path):
    return os.path.join(vault_path, ".obsidian", "plugins",
                         "obsidian-local-rest-api", "data.json")


def community_plugins_path(vault_path):
    return os.path.join(vault_path, ".obsidian", "community-plugins.json")

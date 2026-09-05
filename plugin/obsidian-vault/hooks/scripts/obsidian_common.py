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
import re
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


def port_in_range(value):
    """One rule for what counts as a port, wherever a port is accepted.

    `_valid_port` repairs a bad value in an already-written config, because a
    hook that dies on someone else's typo helps nobody. Anything ACCEPTING a
    port from a person has to reject instead: repairing input at the point of
    entry turns a typo into a working config for a port the user never chose,
    and it looks like it worked. Both paths ask this one question so the two
    answers can never drift.
    """
    return not isinstance(value, bool) and isinstance(value, int) and 1 <= value <= 65535


def _valid_port(value, context):
    """A config `port` value is untrusted input from a hand-edited JSON file.

    A string, a float, or an out-of-range int used in arithmetic downstream
    raises TypeError, which an outer `except Exception: sys.exit(0)` then
    swallows completely silently - a hook that reports nothing is worse than
    one that reports the wrong thing. Validate once, here, at load: on
    failure, print the defect to stderr (visible in the transcript even for a
    hook that must still exit 0) and fall back to DEFAULT_PORT rather than
    letting the bad value propagate.

    Note this is the vault's *HTTP* (insecure) port - the one an MCP server is
    registered against. The HTTPS port is a separate, unrelated number that
    only data.json knows; see read_rest_settings.
    """
    if not port_in_range(value):
        print(
            f"obsidian-vault config: {context} is not a port in 1-65535 ({value!r}) - "
            f"using default port {DEFAULT_PORT}", file=sys.stderr,
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
                "port": _valid_port(entry.get("port", DEFAULT_PORT), f"vaults.{name}.port"),
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
        for entry in raw.values():
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


def rest_api_plugin_dir(vault_path):
    return os.path.join(vault_path, ".obsidian", "plugins", "obsidian-local-rest-api")


# --- Local REST API settings, read from disk and never derived ---------------
#
# data.json names its two ports in a way that reads backwards if skimmed:
#
#     "port"          -> the HTTPS listener (self-signed cert)
#     "insecurePort"  -> the HTTP listener, the one an MCP server is registered
#                        against, and the one Claude Code's Node client can
#                        actually talk to
#
# They are independent numbers the user picks per vault, and on a real machine
# they are neither adjacent nor consistently ordered - one vault here runs
# https 27126 / http 27127, i.e. HTTPS *below* HTTP. Deriving one from the
# other (`https = http + 1`) was wrong for every vault on that machine and hid
# a port collision for weeks. Read both, or report neither.

def _optional_port(value):
    """A port from data.json, or None if it is missing or unusable.

    Unlike _valid_port there is no sensible default to fall back to: a wrong
    port here means probing someone else's server, so "unknown" is the only
    honest answer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 65535 else None


def read_rest_settings(vault_path):
    """This vault's Local REST API settings as recorded on disk.

    Returns a dict, always with the same keys, never raising:

        installed   True when data.json exists and parses. False means the
                    plugin was never installed or never ran - a different
                    verdict from "installed but down", and the two must not be
                    reported the same way.
        plugin_dir_present  the plugin folder exists (files are there) even if
                    data.json is not - i.e. installed but never enabled.
        data_path   where the above was looked for.
        https_port  data.json "port".
        http_port   data.json "insecurePort".
        enable_insecure_server  data.json "enableInsecureServer", or None when
                    unknown. Only ever report this flag as the cause of an
                    outage when it is literally False here.
        api_key     data.json "apiKey", used to authenticate a probe of THIS
                    vault - and, deliberately, to detect a server that answers
                    a different vault's key.
        warnings    human-readable defects found while reading.
    """
    data_path = rest_api_data_path(vault_path)
    out = {
        "installed": False,
        "plugin_dir_present": os.path.isdir(rest_api_plugin_dir(vault_path)),
        "data_path": data_path,
        "https_port": None,
        "http_port": None,
        "enable_insecure_server": None,
        "api_key": None,
        "warnings": [],
    }
    try:
        with open(data_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError:
        return out
    except ValueError:
        out["warnings"].append(f"{data_path} is not valid JSON")
        return out
    if not isinstance(data, dict):
        out["warnings"].append(f"{data_path} is not a JSON object")
        return out

    out["installed"] = True
    out["https_port"] = _optional_port(data.get("port"))
    out["http_port"] = _optional_port(data.get("insecurePort"))
    if data.get("port") is not None and out["https_port"] is None:
        out["warnings"].append(f"{data_path}: 'port' (HTTPS) is not a usable port number")
    if data.get("insecurePort") is not None and out["http_port"] is None:
        out["warnings"].append(f"{data_path}: 'insecurePort' (HTTP) is not a usable port number")
    flag = data.get("enableInsecureServer")
    out["enable_insecure_server"] = flag if isinstance(flag, bool) else None
    key = data.get("apiKey")
    out["api_key"] = key if isinstance(key, str) and key else None
    return out


def resolve_ports(vault_path, config_port=None, settings=None):
    """(http_port, https_port) for a vault. Both read, neither derived.

    `config_port` is the HTTP port from ~/.claude/obsidian/config.json, used
    only when data.json does not name one - config has never carried the HTTPS
    port, so an uninstalled plugin yields (config_port, None) and callers must
    treat a None port as "not knowable", not as a number to guess at.
    """
    s = settings if settings is not None else read_rest_settings(vault_path)
    http_port = s["http_port"] if s["http_port"] is not None else config_port
    return http_port, s["https_port"]


# --- Discovery: every vault on the machine, not just the configured ones -----

def _norm_path(path):
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def list_app_vaults():
    """Every vault in Obsidian's own registry as {vault_id: {path, open, ts}}.

    Never raises - an absent or malformed obsidian.json is just an empty
    registry. This is the same file detect_vault_from_app() picks one entry
    out of; discovery needs all of them, because the vault that is broken is
    routinely the one nobody got around to configuring.
    """
    try:
        with open(obsidian_app_json_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    vaults = data.get("vaults") if isinstance(data, dict) else None
    if not isinstance(vaults, dict):
        return {}
    out = {}
    for vid, entry in vaults.items():
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        try:
            ts = int(entry.get("ts", 0))
        except (TypeError, ValueError):
            ts = 0
        out[vid] = {"path": entry["path"], "open": entry.get("open") is True, "ts": ts}
    return out


def discover_vaults(include_missing=False):
    """Every vault this machine knows about, configured or not.

    list_vaults() answers "what did the user configure"; this answers "what is
    actually on the machine", by merging that with Obsidian's own registry. A
    vault that was never added to config.json still gets diagnosed - which
    matters most exactly when it is the one misbehaving, since an unconfigured
    vault can still bind a port a configured vault wanted.

    Each entry carries everything list_vaults() does, plus:

        configured  present in ~/.claude/obsidian/config.json
        in_app      present in Obsidian's registry
        source      "config" | "obsidian" | "both", for reporting provenance
        vault_id    Obsidian's own id, when known

    `include_missing` keeps registry entries whose directory is gone (a vault
    Obsidian remembers but that has been deleted or unmounted); the default
    drops them, matching list_vaults().
    """
    out = {}
    by_path = {}
    for name, entry in list_vaults().items():
        merged = dict(entry)
        merged.update({"configured": True, "in_app": False, "source": "config", "vault_id": None})
        out[name] = merged
        by_path[_norm_path(entry["path"])] = name

    for vid, app_entry in list_app_vaults().items():
        path = app_entry["path"]
        known = by_path.get(_norm_path(path))
        if known:
            out[known]["in_app"] = True
            out[known]["source"] = "both"
            out[known]["vault_id"] = vid
            continue
        if not include_missing and not os.path.isdir(path):
            continue
        name = os.path.basename(os.path.normpath(path)) or vid
        if name in out:
            # Two different directories with the same basename, or a config
            # name that happens to match one. Disambiguate rather than letting
            # one silently shadow the other - a shadowed vault is invisible to
            # every check downstream, which is the failure mode this whole
            # module exists to stop.
            name = f"{name}-{vid[:6]}"
        out[name] = {
            "path": path,
            "port": None,
            "layout": None,
            "default": False,
            "configured": False,
            "in_app": True,
            "source": "obsidian",
            "vault_id": vid,
        }
        by_path[_norm_path(path)] = name
    return out


# --- Port collisions ---------------------------------------------------------
#
# The fault this exists to catch: two vaults both declared HTTPS 27126. One won
# the bind; the loser's Local REST API plugin then failed to start its server at
# all, which took its HTTP listener down with it. Three symptoms - HTTP never
# listening, the HTTPS port answering with the other vault's API key, the other
# vault's files being served - and one cause. Nothing checked for a duplicate
# port, so the diagnosis landed on enableInsecureServer, which was already true
# on disk.
#
# Claims are grouped over the union of (vault, protocol, port) tuples rather
# than per protocol: one vault's insecurePort can equal another's port, and
# grouping per protocol is blind to exactly that.

def collect_rest_settings(vaults):
    """{name: read_rest_settings(entry["path"])} for a discovered vault map."""
    return {name: read_rest_settings(entry["path"]) for name, entry in vaults.items()}


def find_port_collisions(vaults, settings_by_name=None):
    """Every port claimed by more than one vault, or twice by one vault.

    Returns a list, lowest port first:

        [{"port": 27126,
          "claims": [{"vault": "codegraphs", "protocol": "https"},
                     {"vault": "anew", "protocol": "https"}]}]

    Pure: it reads data.json but touches no socket. A collision is a fact about
    what is *declared*, and stays true whether or not Obsidian is running -
    which is what makes it checkable before anything is probed, and reportable
    before any other diagnosis is attempted.
    """
    settings = settings_by_name if settings_by_name is not None else collect_rest_settings(vaults)
    claims = {}
    for name in vaults:
        s = settings.get(name)
        if not s or not s["installed"]:
            continue
        for protocol, port in (("https", s["https_port"]), ("http", s["http_port"])):
            if port is None:
                continue
            claims.setdefault(port, []).append({"vault": name, "protocol": protocol})
    return [{"port": port, "claims": entries}
            for port, entries in sorted(claims.items())
            if len(entries) > 1]


def collisions_for(collisions, name):
    """The subset of find_port_collisions() output that involves one vault."""
    return [c for c in collisions if any(claim["vault"] == name for claim in c["claims"])]


def describe_collision(collision):
    """One sentence naming who collides on what, for a report or a hook line."""
    port = collision["port"]
    names = []
    for claim in collision["claims"]:
        label = f"{claim['vault']} ({claim['protocol'].upper()})"
        if label not in names:
            names.append(label)
    if len({c["vault"] for c in collision["claims"]}) == 1:
        return (f"port {port} is claimed twice by the same vault: "
                f"{' and '.join(names)}")
    return f"port {port} is claimed by {' and '.join(names)}"


# --- Identity: which vault actually answered? --------------------------------
#
# The collision above was invisible for weeks because every check asked "did
# something answer on this port", never "is the thing that answered serving the
# vault I asked about". A server that is up, authenticated, and serving someone
# else's notes passes every liveness check there is, so identity gets its own
# verdict rather than being folded into "UP".

def _visible_root_entries(vault_path):
    """Top-level names Local REST API would list for a vault.

    Dotfiles (notably .obsidian) are excluded: the API does not list them, so
    including them here would depress every comparison by a constant.
    """
    try:
        names = os.listdir(vault_path)
    except OSError:
        return set()
    return {n.rstrip("/") for n in names if not n.startswith(".")}


def identity_check(vault_path, served_files, other_vaults=None, threshold=0.5):
    """Does the root listing a server returned match the vault on disk?

    `served_files` is what the API reported for the vault root (Local REST API
    marks directories with a trailing "/", which is stripped here).
    `other_vaults` is {name: path}; when the listing does not match, each is
    tried in turn so the answer can name the impostor instead of saying only
    that something is wrong.

    Returns {"verdict": "match" | "mismatch" | "unknown", "score": float,
             "served_vault": name or None, "detail": str}. "unknown" is
    returned rather than a guess when either side has nothing to compare - an
    empty vault genuinely cannot be told apart from another empty one.
    """
    served = {str(f).rstrip("/") for f in (served_files or []) if str(f).strip()}
    served = {s for s in served if not s.startswith(".")}
    expected = _visible_root_entries(vault_path)
    if not served or not expected:
        return {"verdict": "unknown", "score": 0.0, "served_vault": None,
                "detail": "nothing to compare (one side listed no root entries)"}

    def score(a, b):
        return len(a & b) / float(len(a | b))

    mine = score(served, expected)
    if mine >= threshold:
        return {"verdict": "match", "score": mine, "served_vault": None,
                "detail": f"root listing matches (overlap {mine:.0%})"}

    best_name, best_score = None, 0.0
    for name, path in (other_vaults or {}).items():
        if _norm_path(path) == _norm_path(vault_path):
            continue
        other = score(served, _visible_root_entries(path))
        if other > best_score:
            best_name, best_score = name, other
    if best_name and best_score >= threshold:
        detail = (f"the server on this port is serving vault '{best_name}' "
                  f"(overlap {best_score:.0%}), not this one (overlap {mine:.0%})")
    else:
        detail = (f"root listing does not match this vault (overlap {mine:.0%}) "
                  "and matches no other known vault either")
        best_name = None
    return {"verdict": "mismatch", "score": mine, "served_vault": best_name, "detail": detail}


# --- Is a window open for this vault? ----------------------------------------
#
# The fault this exists to separate: one vault's Obsidian window (2.2 GB
# resident) simply exited. The symptom - a silent port - was indistinguishable
# from a server that had been misconfigured, and both rendered as one line
# saying "down". Three people each blamed something different and one was
# right.
#
# What can actually be checked, verified against Obsidian 1.13.7:
#
#   * NOT the command line. Every Obsidian process - main, gpu, renderer,
#     utility - carries at most `--user-data-dir=<app config dir>`. None of
#     them names the vault a window has open, so a process list can only ever
#     say "Obsidian is running somewhere", which is the same answer whether
#     the vault in question is open, closed, or was never added.
#   * The WINDOW TITLE does name it: "<vault> - Obsidian <version>", or
#     "<note or view> - <vault> - Obsidian <version>". On Windows every
#     top-level window is enumerable in-process through user32 - no
#     subprocess, no third-party module, and it sees every vault window, not
#     just the foreground one.
#   * On macOS and Linux there is no equivalent that is installed by default:
#     the window list needs an AppleScript accessibility grant, or
#     wmctrl/xdotool. Those platforms therefore answer only "an Obsidian
#     process is / is not running" and say, in as many words, that they could
#     not tell which vault - a wrong attribution costs far more than an
#     admitted gap.
#
# Absence of a process is the one negative that generalizes: no Obsidian
# process at all means no window for ANY vault. Nothing else here infers a
# vault's state from evidence that cannot see vaults.

WINDOW_OPEN = "open"
WINDOW_ABSENT = "absent"
WINDOW_UNKNOWN = "unknown"

# The tail of an Obsidian window title, e.g. "Obsidian 1.13.7". Anchored so a
# browser window reading "Obsidian Publish - Google Chrome" is not mistaken for
# the app, and so the segment before it can be taken as the vault name.
_OBSIDIAN_TITLE_TAIL = re.compile(r"^Obsidian(\s+v?\d[\d.]*)?$")


def parse_window_vault(title):
    """The vault name an Obsidian window title carries, or None.

    Both observed shapes end the same way, so the vault is always the segment
    immediately before the "Obsidian <version>" tail:

        "claude-memories-codegraphs - Obsidian 1.13.7"     -> the vault
        "Graph view - claude-memories - Obsidian 1.13.7"   -> the vault

    The name in the title is the vault FOLDER's basename, which is what the
    caller compares against. A vault whose folder name itself contains " - "
    yields only its last segment here and therefore fails to match - that is
    deliberate: it degrades to "cannot tell", never to a wrong vault.
    """
    if not title:
        return None
    parts = [p.strip() for p in str(title).split(" - ")]
    if len(parts) < 2 or not _OBSIDIAN_TITLE_TAIL.match(parts[-1]):
        return None
    return parts[-2] or None


def _windows_window_titles():
    """Every titled top-level window on Windows. Windows-only; may raise.

    ctypes.windll / ctypes.WINFUNCTYPE do not exist off Windows, which is why
    every import here is local to this function - a module-level import would
    kill the hook on the two platforms that cannot be tested from a Windows
    box.
    """
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32  # pylint: disable=no-member  # Windows-only, guarded by caller
    titles = []
    callback = ctypes.WINFUNCTYPE(  # pylint: disable=no-member  # Windows-only, guarded by caller
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _collect(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value:
                titles.append(buf.value)
        return True

    if not user32.EnumWindows(callback(_collect), 0):
        raise OSError("EnumWindows failed")
    return titles


def _linux_obsidian_running():
    """True/False from /proc, or None when /proc could not be read.

    Reads comm rather than shelling out to ps: a SessionStart hook that spawns
    a process on every session pays for it on every session, and /proc is
    always there on the platform this branch runs on.
    """
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    seen_any = False
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/comm", "r", encoding="utf-8", errors="replace") as fh:
                comm = fh.read().strip()
        except OSError:
            # The process exited between listdir and open. Not an error, and
            # not evidence either way.
            continue
        seen_any = True
        if "obsidian" in comm.lower():
            return True
    return False if seen_any else None


def _macos_obsidian_running():
    """True/False from ps, or None when ps could not be run."""
    import subprocess
    try:
        proc = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True,
                              timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return any("obsidian" in line.lower() for line in proc.stdout.splitlines())


def obsidian_window_evidence():
    """What this machine can actually observe about open Obsidian windows.

    Never raises, and always returns the same keys:

        method        what was used, or None when nothing could be
        window_vaults vault names read off window titles, or None when this
                      platform's window list could not be read at all
        app_running   True / False / None - whether an Obsidian PROCESS was
                      seen. None means the check itself could not run, which
                      is a different answer from False and is reported as one.
        detail        what was checked and what it found
        cannot        what this method structurally cannot determine, "" when
                      it determined everything the caller asked for
        next_check    the check a human can run to settle what `cannot` names
    """
    system = platform.system()
    out = {"method": None, "window_vaults": None, "app_running": None,
           "detail": "", "cannot": "", "next_check": ""}

    if system == "Windows":
        try:
            titles = _windows_window_titles()
        except Exception as e:  # pylint: disable=broad-except
            out["detail"] = f"the Windows window list could not be read ({type(e).__name__}: {e})"
            out["cannot"] = "whether Obsidian has a window open for this vault"
            out["next_check"] = ("look at Obsidian's own window list, or its vault switcher, "
                                 "for this vault")
            return out
        names = [n for n in (parse_window_vault(t) for t in titles) if n]
        out["method"] = "windows-window-titles"
        out["window_vaults"] = names
        out["app_running"] = True if names else None
        out["detail"] = (
            f"read {len(titles)} window titles; "
            + (f"Obsidian windows: {', '.join(sorted(set(names)))}" if names
               else "none of them is an Obsidian window")
        )
        if not names:
            # No window does not mean no process: Obsidian can sit in the tray
            # with every window closed, and that is exactly the state a closed
            # vault is in. Say what was seen, not what it implies about the app.
            out["cannot"] = "whether Obsidian is still resident with all its windows closed"
            out["next_check"] = "the tray icon, or a process list"
        return out

    running = _linux_obsidian_running() if system == "Linux" else _macos_obsidian_running()
    out["method"] = "linux-proc-comm" if system == "Linux" else "macos-ps"
    out["app_running"] = running
    windowing = ("wmctrl or xdotool" if system == "Linux"
                 else "AppleScript with an accessibility grant")
    if running is None:
        out["detail"] = f"the process list could not be read on {system}"
        out["cannot"] = "whether Obsidian is running at all, let alone which vault it has open"
        out["next_check"] = "a process list, and Obsidian's own window list"
        return out
    out["detail"] = (f"an Obsidian process is running on this {system} machine" if running
                     else f"no Obsidian process is running on this {system} machine")
    if running:
        out["cannot"] = ("which vault an open window belongs to - Obsidian's process command "
                         "lines name only its user-data directory, never the vault (verified "
                         f"on 1.13.7), and reading window titles on {system} needs {windowing}, "
                         "which this script does not require you to install")
        out["next_check"] = ("look at Obsidian's window list: a window for this vault means the "
                             "plugin's server failed to start; no window means the vault is "
                             "simply closed and nothing about the plugin is wrong")
    return out


def vault_window_state(vault_path, evidence, known_vault_paths=None):
    """Does an open window on this machine belong to THIS vault?

    Returns {"state": WINDOW_OPEN | WINDOW_ABSENT | WINDOW_UNKNOWN,
             "evidence": str, "cannot": str, "next_check": str}.

    `evidence` is obsidian_window_evidence() output; None means the check was
    never run, which is reported as such rather than as a negative.
    `known_vault_paths` is {name: path} for every vault on the machine: two
    vaults whose folders share a basename cannot be told apart by a window
    title, and that ambiguity is returned as UNKNOWN instead of a coin flip.
    """
    out = {"state": WINDOW_UNKNOWN, "evidence": "", "cannot": "", "next_check": ""}
    if not evidence:
        out["evidence"] = "the window check was not run"
        out["cannot"] = "whether Obsidian has a window open for this vault"
        out["next_check"] = "run this hook again, or look at Obsidian's window list"
        return out

    names = evidence.get("window_vaults")
    if names is None:
        if evidence.get("app_running") is False:
            # The one negative that generalizes: no process, so no window, for
            # this vault or any other.
            out["state"] = WINDOW_ABSENT
            out["evidence"] = evidence.get("detail") or "no Obsidian process is running"
            return out
        out["evidence"] = evidence.get("detail") or "the window list could not be read"
        out["cannot"] = evidence.get("cannot") or \
            "whether Obsidian has a window open for this vault"
        out["next_check"] = evidence.get("next_check") or "Obsidian's own window list"
        return out

    basename = os.path.basename(os.path.normpath(vault_path))
    matched = [n for n in names if n.lower() == basename.lower()]
    if matched:
        twins = sorted(
            name for name, path in (known_vault_paths or {}).items()
            if _norm_path(path) != _norm_path(vault_path)
            and os.path.basename(os.path.normpath(path)).lower() == basename.lower()
        )
        if twins:
            out["evidence"] = (
                f"an Obsidian window is titled '{basename}', but {len(twins) + 1} vaults on "
                f"this machine have a folder called '{basename}' ({', '.join(twins)} and this "
                "one), and a window title carries only the folder name"
            )
            out["cannot"] = "which of those vaults that window has open"
            out["next_check"] = ("Obsidian's vault switcher shows the full path of the open "
                                 "vault")
            return out
        out["state"] = WINDOW_OPEN
        out["evidence"] = f"an Obsidian window is titled '{basename}'"
        return out

    out["state"] = WINDOW_ABSENT
    if names:
        out["evidence"] = (f"Obsidian has {len(set(names))} vault window(s) open "
                           f"({', '.join(sorted(set(names)))}) and none of them names "
                           f"'{basename}'")
    else:
        out["evidence"] = "no Obsidian window is open on this machine"
    return out

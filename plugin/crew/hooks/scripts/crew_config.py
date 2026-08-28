"""Owns the single definition of a fresh `.crew/config.json`.

Three things read this module and must never disagree with each other:

  * `templates/config.template.json`, the file `/crew:init` copies down when
    setting up a new repo. A committed test (`test_crew_config.py`) asserts
    the template equals `default_config()` byte-for-byte, so drift between
    "what setup writes" and "what this module produces" fails CI instead of
    surfacing months later on someone else's machine.
  * `crew_platform.heal_config`, which calls this when `.crew/` exists but
    `config.json` does not, or is not readable as a config.
  * `skills/crew-setup/SKILL.md`, whose inline JSON is prose for a human
    reading the skill and is a COPY of this module's output, not a second
    definition of it.

The `pm` and `graph` blocks are not hand-copied here either. `pm` comes from
`crew_state.PM_DEFAULTS` -- the same object the SessionStart brief merges a
config's `pm` block onto -- and `graph` comes from `crew_upgrade.GRAPH_BLOCK`,
the same object `/crew:upgrade` merges a v1 config's `graph` block onto. A
freshly created repo and a freshly upgraded one must land on identical
defaults; sourcing both blocks from the modules that already own them is what
makes that true by construction rather than by two authors remembering to
keep three copies in sync.

## Global + repo config layering

This module also owns `resolve_config`, the one place that answers "what is
the EFFECTIVE config" once a machine-global file enters the picture. Three
layers, lowest precedence first: `default_config()`, the machine-global file
at `GLOBAL_CONFIG_PATH` (`~/.claude/crew/config.json`), and the repo's own
`.crew/config.json` -- repo overrides global overrides built-in defaults,
merged one level deep with `crew_state.merge_defaults`, the same policy
`crew_upgrade.upgrade_config` uses.

Only readers that want SETTINGS should call `resolve_config`. Two things
deliberately read the repo file directly instead:

  * `crew_state.collect`'s `schema` field is a fact about the repo file's own
    layout version, not a setting -- merging it would make an unmigrated v1
    repo (no `schema` key at all) look current the moment any global file
    exists, since the built-in default layer always supplies the current
    schema number.
  * `crew_platform.heal_config` and the `platform-sync` writer touch only the
    repo file, always -- the global file is never read for a decision about
    what to WRITE, and this module never writes it at all. There is no
    command that creates it either; a user who wants one writes
    `~/.claude/crew/config.json` by hand.
"""

import copy
import json
import os
import sys

import crew_state

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "skills", "crew-graph", "scripts",
))
import crew_upgrade  # pylint: disable=wrong-import-position

# A module attribute, not a baked-in constant used directly everywhere, so a
# test can point it at a scratch file instead of the real machine-wide one.
GLOBAL_CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".claude", "crew", "config.json")


def default_config():
    """A fresh, current `.crew/config.json`, as a plain dict.

    Every call builds a new object. A caller that goes on to `json.dump` it,
    or to stamp platform facts into it, must not be able to corrupt a shared
    default for the next caller in the same process -- the same rule
    `crew_upgrade.upgrade_config` follows for its own `GRAPH_BLOCK`.

    Key order matches `skills/crew-setup/SKILL.md`'s prose template, so a
    diff against the committed template file is a diff of VALUES, not of
    reordered keys.
    """
    return {
        "schema": crew_state.SCHEMA_CURRENT,
        "tier": 0,
        "roles": ["explorer", "qa-reviewer"],
        "qa": {"provider": "auto"},
        "secondOpinion": {
            "provider": "none",
            "mode": "cli",
            "model": None,
            "keyEnv": "GEMINI_API_KEY",
            "sendsCode": False,
        },
        "tracker": "files",
        "jira": {"project": None},
        "sdp": {
            "portal": None,
            "noteVisibility": "private",
            "closeOnDone": False,
        },
        "obsidian": {
            "vaultPath": None,
            "boardDir": None,
            "board": "Board.md",
            "columns": {
                "backlog": "Backlog",
                "ready": "Ready",
                "inProgress": "In Progress",
                "review": "Review",
                "done": "Done",
            },
        },
        "memory": {"mode": "repo", "vaultPath": None},
        "verifyGate": True,
        "context": {
            "enabled": True,
            "warnAt": 0.8,
            "budgetTokens": None,
            "reserveTokens": 100000,
            "handoffPath": ".work/HANDOFF.md",
            "keepTranscripts": 5,
        },
        "emergency": {
            "standDown": True,
            "ttlMinutes": 120,
            "maxTtlMinutes": 480,
        },
        "notify": {
            "provider": "none",
            "urlEnv": None,
            "tokenEnv": None,
            "chatId": None,
            "events": ["phase", "gate", "waiting"],
        },
        # Left nulled deliberately -- the platform-sync SessionStart hook
        # fills these in on first run and repairs them on every later one.
        # Hand-writing a value here only means it gets overwritten.
        "platform": {
            "os": None,
            "wsl": None,
            "shell": None,
            "windowsHostIp": None,
        },
        "pm": copy.deepcopy(crew_state.PM_DEFAULTS),
        "graph": copy.deepcopy(crew_upgrade.GRAPH_BLOCK),
    }


def read_global_config(path=None):
    """The machine-global crew config, or `{}` when absent, malformed, or not
    a JSON object.

    `path` defaults to `GLOBAL_CONFIG_PATH`; pass it explicitly in a test
    rather than monkeypatching the module attribute mid-call, since
    `resolve_config` reads the attribute itself and a stale local reference
    would not see a patch applied after import.

    Never raises. `resolve_config` is reached from a SessionStart hook by way
    of `crew_state.collect`, and a broken global file must look exactly like
    no global file at all -- the same reasoning `crew_upgrade.
    _read_config_strict` documents for "absent" on the repo side. Unlike the
    repo file, a broken global file is never backed up or rewritten here;
    nothing in this module ever writes it.
    """
    text = crew_state.read_text(GLOBAL_CONFIG_PATH if path is None else path)
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def resolve_config(root):
    """The effective config for the repo at `root` -- see the module
    docstring's "Global + repo config layering" section for the precedence
    rule and the two callers that deliberately bypass this.

    Never raises: `crew_state.load_config` and `read_global_config` each
    already collapse "malformed" to "absent" on their own, so a broken file
    at either layer contributes nothing to the merge rather than failing the
    whole resolution.
    """
    merged = crew_state.merge_defaults(default_config(), read_global_config())
    return crew_state.merge_defaults(merged, crew_state.load_config(root))


def layered_state(root):
    """`crew_state.collect(root)`, with settings layered per `resolve_config`
    wherever the repo is already crew-managed.

    Composing "what is the repo's raw state" (`crew_state.collect`, which
    this module already depends on for `PM_DEFAULTS` and `SCHEMA_CURRENT`)
    with "what is the effective config" (`resolve_config`, above) has to
    happen up here, not inside `crew_state.collect` itself -- `crew_state`
    must not import this module, or the two modules import each other, a
    real cyclic import rather than a stylistic one. `collect` takes the
    resolved config as a plain `cfg_override` argument instead; it ignores
    the override for anything it does not recognise as crew-managed, so
    computing `resolve_config` here unconditionally costs nothing on a plain
    repo and needs no `isCrew` check of its own.

    Every caller that wants a config-layered brief -- `pm_brief.py`, and
    anything else that would otherwise call `crew_state.collect` directly --
    should call this instead.
    """
    return crew_state.collect(root, cfg_override=resolve_config(root))

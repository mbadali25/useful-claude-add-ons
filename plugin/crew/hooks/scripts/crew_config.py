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
"""

import copy
import os
import sys

import crew_state

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "skills", "crew-graph", "scripts",
))
import crew_upgrade  # pylint: disable=wrong-import-position


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

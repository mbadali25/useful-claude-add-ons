#!/usr/bin/env python3
"""Regression test for obsidian_common's multi-vault resolution.

Plain assertions, no pytest dependency, run directly:

    python3 hooks/scripts/_test/test_obsidian_common.py

Uses a throwaway HOME under a temp directory so it never touches the real
~/.claude/obsidian/config.json. Covers the two things most likely to break
silently in a multi-vault config: which vault "default" resolves to, and that
a named non-default vault never falls through to env/detection the way the
default vault does.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import obsidian_common  # noqa: E402  pylint: disable=wrong-import-position

FAILURES = []


def _norm(v):
    # Paths may differ only in separator style ("/" from the {tmp}-substituted
    # config vs os.path.join's native separator) - normalize before comparing,
    # since that difference is an artifact of this test's own string building,
    # not a real result to catch.
    return os.path.normpath(v) if isinstance(v, str) else v


def check(desc, got, want):
    if _norm(got) != _norm(want):
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


def with_config(config, vault_dirs, fn):
    """Runs fn() with HOME pointed at a fresh throwaway config, and the given
    vault directories actually created on disk (resolution requires
    os.path.isdir to be true). Cleans up after itself.
    """
    tmp = tempfile.mkdtemp(prefix="obsidian-common-test-")
    try:
        home = os.path.join(tmp, "home")
        os.makedirs(os.path.join(home, ".claude", "obsidian"))
        for d in vault_dirs:
            os.makedirs(os.path.join(tmp, d), exist_ok=True)

        # Resolve any {tmp} placeholders in the config to real paths before writing.
        def resolve(obj):
            if isinstance(obj, str):
                return obj.replace("{tmp}", tmp)
            if isinstance(obj, dict):
                return {k: resolve(v) for k, v in obj.items()}
            return obj

        with open(os.path.join(home, ".claude", "obsidian", "config.json"),
                   "w", encoding="utf-8") as fh:
            json.dump(resolve(config), fh)

        old_home = os.environ.get("HOME")
        old_env_vault = os.environ.pop("OBSIDIAN_VAULT_PATH", None)
        os.environ["HOME"] = home
        try:
            fn(tmp)
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
            if old_env_vault is not None:
                os.environ["OBSIDIAN_VAULT_PATH"] = old_env_vault
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- Explicit default wins, even declared second -----------------------------

def _t1(tmp):
    vaults = obsidian_common.list_vaults()
    check("two vaults, explicit default: count", len(vaults), 2)
    check("two vaults, explicit default: name", obsidian_common.default_vault_name(), "memory")
    entry = obsidian_common.resolve_vault("codegraphs")
    check("named non-default vault resolves", entry["path"], os.path.join(tmp, "codegraphs"))
    check("named non-default vault carries its layout", entry["layout"], "org/repo")

with_config(
    {"vaults": {
        "codegraphs": {"path": "{tmp}/codegraphs", "port": 27125, "layout": "org/repo"},
        "memory": {"path": "{tmp}/memory", "port": 27123, "default": True},
    }},
    ["codegraphs", "memory"],
    _t1,
)

# --- No vault marked default: first declared wins, deterministically --------

def _t2(_tmp):
    check("no explicit default: first-declared wins", obsidian_common.default_vault_name(), "alpha")

with_config(
    {"vaults": {
        "alpha": {"path": "{tmp}/alpha"},
        "beta": {"path": "{tmp}/beta"},
    }},
    ["alpha", "beta"],
    _t2,
)

# --- Legacy vaultPath shape still resolves as one vault named "memory" ------

def _t3(tmp):
    vaults = obsidian_common.list_vaults()
    check("legacy shape: one vault", list(vaults.keys()), ["memory"])
    check("legacy shape: path", obsidian_common.resolve_vault_path(), os.path.join(tmp, "onlyvault"))

with_config({"vaultPath": "{tmp}/onlyvault"}, ["onlyvault"], _t3)

# --- A named non-default vault does NOT fall through to env override -------

def _t4(tmp):
    os.environ["OBSIDIAN_VAULT_PATH"] = os.path.join(tmp, "memory")
    got = obsidian_common.resolve_vault("codegraphs")
    check("env var does not redirect a named non-default vault",
          got["path"], os.path.join(tmp, "codegraphs"))
    default_got = obsidian_common.resolve_vault()
    check("env var DOES override the default vault",
          default_got["path"], os.path.join(tmp, "memory"))
    # Codex QA finding: the env var overrides *where* the default vault lives,
    # not *what port it runs on* - a default vault configured on a
    # non-standard port must keep that port when only the path is overridden.
    check("env var override still uses the configured port, not DEFAULT_PORT",
          default_got["port"], 27177)
    check("env var override still carries the configured layout",
          default_got["layout"], "daily-notes")

with_config(
    {"vaults": {
        "memory": {"path": "{tmp}/memory-configured", "port": 27177,
                   "layout": "daily-notes", "default": True},
        "codegraphs": {"path": "{tmp}/codegraphs", "layout": "org/repo"},
    }},
    ["memory", "memory-configured", "codegraphs"],
    _t4,
)

# --- A vault entry pointing at a nonexistent directory is dropped -----------

def _t5(tmp):
    vaults = obsidian_common.list_vaults()
    check("nonexistent vault path is dropped", "ghost" in vaults, False)
    check("the real vault is still there", "memory" in vaults, True)

with_config(
    {"vaults": {
        "memory": {"path": "{tmp}/memory", "default": True},
        "ghost": {"path": "{tmp}/does-not-exist"},
    }},
    ["memory"],
    _t5,
)

# --- A malformed config port never reaches bridge_status.py ----------------
# Codex QA finding: an unvalidated string/negative port used to raise
# TypeError in that hook's port arithmetic, swallowed silently by an outer
# `except Exception: sys.exit(0)`. list_vaults() must coerce it to
# DEFAULT_PORT instead of passing the bad value through. (The arithmetic
# itself is gone - see test_vault_ops.py - but a bad port still must not
# escape config parsing.)

def _t6(tmp):
    vaults = obsidian_common.list_vaults()
    check("string port falls back to DEFAULT_PORT", vaults["stringport"]["port"], 27123)
    check("negative port falls back to DEFAULT_PORT", vaults["negport"]["port"], 27123)
    check("out-of-range port falls back to DEFAULT_PORT", vaults["hugeport"]["port"], 27123)
    check("valid port is used as-is", vaults["goodport"]["port"], 27200)

with_config(
    {"vaults": {
        "stringport": {"path": "{tmp}/stringport", "port": "27123"},
        "negport": {"path": "{tmp}/negport", "port": -1},
        "hugeport": {"path": "{tmp}/hugeport", "port": 99999},
        "goodport": {"path": "{tmp}/goodport", "port": 27200, "default": True},
    }},
    ["stringport", "negport", "hugeport", "goodport"],
    _t6,
)

# --- A malformed port on the vault the env var overrides still falls back --

def _t7(tmp):
    os.environ["OBSIDIAN_VAULT_PATH"] = os.path.join(tmp, "memory")
    got = obsidian_common.resolve_vault()
    check("env override with an invalid configured port falls back to DEFAULT_PORT",
          got["port"], 27123)

with_config(
    {"vaults": {
        "memory": {"path": "{tmp}/memory-configured", "port": "not-a-port", "default": True},
    }},
    ["memory", "memory-configured"],
    _t7,
)

print(f"RESULT: {len(FAILURES)} failed")
for f in FAILURES:
    print("FAIL:", f)
sys.exit(1 if FAILURES else 0)

#!/usr/bin/env python3
"""Sabotage suite for check-marketplace.py's check_license_consistency.

Root `LICENSE` is GNU GPL v2. Before this check existed, two plugins declared
`"license": "MIT"` in their own `plugin.json` and three declared no `license`
key at all, so a consumer reading a plugin's manifest and a consumer reading
the repository's `LICENSE` reached different conclusions about the same code.

No git repo is built here, unlike `version-drift.py` and
`crew-ignore-policy.py` - the check this suite covers never calls `git()`, it
only reads `plugin.json` off disk for each entry whose `source` starts with
`./plugin/`, so a plain temp directory is enough.

Run: python3 scripts/_test/license-consistency.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-marketplace.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()

ENTRIES = [
    {"name": "widget", "source": "./plugin/widget", "version": "1.0.0"},
    # A ./skills/ entry, to prove the check does not walk skills looking for a
    # plugin.json that was never supposed to exist there.
    {"name": "gadget", "source": "./skills/gadget", "version": "1.0.0"},
]


def write_manifest(tmp: str, name: str, license_value: str | None) -> None:
    path = os.path.join(tmp, "plugin", name, ".claude-plugin", "plugin.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"name": name, "version": "1.0.0", "description": "d"}
    if license_value is not None:
        data["license"] = license_value
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2)


def run_check(tmp: str) -> list[str]:
    """Run the real check_license_consistency with ROOT pointed at a fixture."""
    old_root = CHECKER.ROOT
    CHECKER.ROOT = tmp
    problems: list[str] = []
    try:
        CHECKER.check_license_consistency(ENTRIES, problems.append)
    finally:
        CHECKER.ROOT = old_root
    return problems


# ----------------------------------------------------------------- scenarios

def s_mit_blocks(tmp: str) -> None:
    """The exact pre-existing shape: license declared, but the wrong one."""
    write_manifest(tmp, "widget", "MIT")


def s_missing_key_blocks(tmp: str) -> None:
    """No `license` key at all - the other pre-existing shape."""
    write_manifest(tmp, "widget", None)


def s_correct_is_quiet(tmp: str) -> None:
    """The fixed shape: GPL-2.0-only declared. MUST PASS."""
    write_manifest(tmp, "widget", "GPL-2.0-only")


def s_no_manifest_is_quiet(tmp: str) -> None:
    """A plugin entry with no plugin.json on disk at all is skipped, not failed -
    `check_plugin_manifests` (the version-parity check right above this one in
    check-marketplace.py) makes the same call, and this check should not be
    stricter about a missing file than the check it sits beside.
    """
    # Deliberately write nothing under plugin/widget/.


SCENARIOS = {
    "mit declared -> blocks, names the plugin": (s_mit_blocks, True),
    "no license key -> blocks, names the plugin": (s_missing_key_blocks, True),
    "GPL-2.0-only declared -> quiet": (s_correct_is_quiet, False),
    "no plugin.json on disk -> quiet (skipped, not failed)": (s_no_manifest_is_quiet, False),
}


def main() -> int:
    failures = []
    for label, (build, should_block) in SCENARIOS.items():
        with tempfile.TemporaryDirectory() as tmp:
            build(tmp)
            problems = run_check(tmp)
        blocked = bool(problems)
        if blocked != should_block:
            failures.append(
                f"{label}: expected {'BLOCK' if should_block else 'ALLOW'}, "
                f"got {'BLOCK' if blocked else 'ALLOW'} ({problems!r})"
            )
        elif should_block and "widget" not in problems[0]:
            failures.append(f"{label}: blocked but did not name the plugin: {problems!r}")

    if failures:
        print(f"{len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"license-consistency: {len(SCENARIOS)} scenario(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Regression suite: this repo's code map places every root file a plugin
version bump touches.

crew autopilot's split-check counts the code-map subsystems a ticket's Touch
spans (`crew_split._subsystems`). An entry no note's `paths:` line covers makes
that count None, and autopilot stops with `split-check-unknown`, because an
unplaced entry might be another subsystem. A crew version bump always touches
`.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md` and
`README.md` (the "What's new" block), and three of the four were unplaced until
2026-11-12, so every bump ticket stopped there (found on T-0112).

The positive cases read this repository's tracked `.crew/codemap/` and write
nothing. The must-fail case builds a throwaway code map in a temp directory
with the pre-fix `paths:` line and asserts the count comes back None there, so
the positive cases cannot pass by measuring nothing.

Run: python3 scripts/_test/codemap-coverage.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "plugin", "crew", "hooks", "scripts"))

import crew_context  # noqa: E402  pylint: disable=wrong-import-position
import crew_split  # noqa: E402  pylint: disable=wrong-import-position

BUMP_FILES = (".claude-plugin/marketplace.json", "plugin/PLUGINS.md", "CHANGELOG.md", "README.md")
NOTE = os.path.join(".crew", "codemap", "marketplace-registration.md")
OLD_PATHS_LINE = "paths: scripts/**, plugin/PLUGINS.md"

FAILURES = []


def check(label, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f" - {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(label)


def main():
    subs = crew_context.subsystems(ROOT)
    check("the repo's code map has subsystems", bool(subs))
    for path in BUMP_FILES:
        hits = [s["name"] for s in crew_context.subsystems_for_path(subs, path)]
        check(f"{path} is placed by a code-map note", bool(hits), "no `paths:` line covers it")
        check(f"{path} is placed by marketplace-registration",
              hits[:1] == ["marketplace-registration"], f"longest match is {hits[:1]}")
    count = crew_split._subsystems(ROOT, list(BUMP_FILES))  # pylint: disable=protected-access
    check("the bump set measures as a subsystem count, not unknown", count == 1, f"got {count!r}")
    # A crew file stays crew's: `.claude-plugin/**` must not reach into plugin/.
    hits = [s["name"] for s in crew_context.subsystems_for_path(
        subs, "plugin/crew/.claude-plugin/plugin.json")]
    check("plugin/crew/.claude-plugin/plugin.json stays under crew", hits[:1] == ["crew"],
          f"longest match is {hits[:1]}")

    # Must-fail: the same code map with the pre-fix line reads unknown.
    tmp = tempfile.mkdtemp(prefix="codemap-coverage-")
    try:
        shutil.copytree(os.path.join(ROOT, ".crew", "codemap"), os.path.join(tmp, ".crew", "codemap"))
        path = os.path.join(tmp, NOTE)
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines(keepends=True)
        replaced = [OLD_PATHS_LINE + "\n" if line.startswith("paths:") else line for line in lines]
        check("sabotage: the fixture note had a `paths:` line to replace", replaced != lines)
        text = "".join(replaced)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        count = crew_split._subsystems(tmp, list(BUMP_FILES))  # pylint: disable=protected-access
        check("sabotage: the pre-fix paths line reads unknown (None)", count is None, f"got {count!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall cases passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

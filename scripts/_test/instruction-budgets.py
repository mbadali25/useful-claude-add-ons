#!/usr/bin/env python3
"""Sabotage suite for check_instructions.py.

Every case builds a throwaway `plugin/crew`-shaped fixture under a temp
directory and points the checker's ROOT/CREW/ALLOWANCE_PATH at it, the same
isolation pattern `scripts/_test/self-claims.py` uses for check-marketplace.py.
Nothing here touches this repository's own files.

The four cases the ticket names explicitly: a command file over the line
budget, a stale name in a maintained "new 1.0" file, a broken
`${CLAUDE_PLUGIN_ROOT}` path, and an allowance-listed file that grew past its
recorded line count -- each must go red, and each has a must-allow twin so a
future edit that makes the check fail a correct fixture is caught here rather
than in someone else's repo.

Run: python3 scripts/_test/instruction-budgets.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check_instructions.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_instructions", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def _write(path: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def _root_at(tmp):
    """Point CHECKER's ROOT/CREW/ALLOWANCE_PATH at `tmp` for the duration of
    the `with` block, restoring them afterwards."""
    class _Ctx:
        def __init__(self):
            self.saved = None

        def __enter__(self):
            self.saved = (CHECKER.ROOT, CHECKER.CREW, CHECKER.ALLOWANCE_PATH)
            CHECKER.ROOT = tmp
            CHECKER.CREW = os.path.join(tmp, "plugin", "crew")
            CHECKER.ALLOWANCE_PATH = os.path.join(CHECKER.CREW, ".budget-allowance.json")
            return self

        def __exit__(self, *exc):
            CHECKER.ROOT, CHECKER.CREW, CHECKER.ALLOWANCE_PATH = self.saved
            return False

    return _Ctx()


def _patched(tmp, fn, *args):
    """Run `fn(*args, fail)` with CHECKER's ROOT/CREW/ALLOWANCE_PATH pointed
    at `tmp`, and return the collected failure messages."""
    with _root_at(tmp):
        problems: list[str] = []
        fn(*args, problems.append)
        return problems


def _load_allowance(tmp):
    """Run CHECKER.load_allowance with ROOT/CREW pointed at `tmp`, discarding
    any failure it reports (a malformed-allowance fixture is its own case,
    below) and returning the dict it built."""
    with _root_at(tmp):
        return CHECKER.load_allowance(lambda _msg: None)


FRONTMATTER = (
    "---\n"
    "description: fixture command\n"
    "argument-hint: none\n"
    "allowed-tools: Read\n"
    "---\n\n"
)


def run_command_budget(tmp_lines, allowance):
    with tempfile.TemporaryDirectory() as tmp:
        body = FRONTMATTER + "line\n" * tmp_lines
        _write(os.path.join(tmp, "plugin", "crew", "commands", "fixture.md"), body)
        if allowance is not None:
            _write(os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
                   json.dumps(allowance))
        loaded = _load_allowance(tmp) if allowance is not None else {}
        return _patched(tmp, CHECKER.check_command_budget, loaded)


def run_stale_names(body: str, path_rel: str, maintained: bool = True):
    """``maintained=False`` writes the file WITHOUT adding it to the fixture's
    maintained-files list, proving a file the list does not name is never
    scanned at all -- distinct from every other case here, which proves what
    happens to a file the list DOES name."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, path_rel), body)
        saved_files = CHECKER.NEW_1_0_FILES
        CHECKER.NEW_1_0_FILES = (path_rel,) if maintained else ("plugin/crew/commands/other.md",)
        try:
            return _patched(tmp, CHECKER.check_stale_names)
        finally:
            CHECKER.NEW_1_0_FILES = saved_files


def run_broken_references(body: str):
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "plugin", "crew", "commands", "fixture.md"), body)
        return _patched(tmp, CHECKER.check_broken_references)


def run_allowance_growth(recorded_lines: int, total_lines: int, reason: str):
    """Mirrors main()'s own sequence: load_allowance then check_command_budget
    against the SAME fail collector, so a malformed allowance entry's own
    message is visible here too, not just a downstream budget failure.

    ``total_lines`` is the fixture file's actual total line count (frontmatter
    included); ``recorded_lines`` is what the allowance entry claims.
    """
    with tempfile.TemporaryDirectory() as tmp:
        content_lines = total_lines - len(FRONTMATTER.splitlines())
        body = FRONTMATTER + "line\n" * content_lines
        _write(os.path.join(tmp, "plugin", "crew", "commands", "fixture.md"), body)
        _write(
            os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
            json.dumps({
                "plugin/crew/commands/fixture.md":
                    {"lines": recorded_lines, "reason": reason},
            }),
        )
        with _root_at(tmp):
            problems: list[str] = []
            allowance = CHECKER.load_allowance(problems.append)
            CHECKER.check_command_budget(allowance, problems.append)
            return problems


def main() -> int:
    passed = failed = 0

    def check(name, problems, expect_block, needle=""):
        nonlocal passed, failed
        ok = bool(problems) == expect_block
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {'a' if expect_block else 'no'} problem"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {problems}")

    # --- command line budget ------------------------------------------
    check(
        "a command file over 120 lines with no allowance entry is red",
        run_command_budget(150, allowance=None),
        True,
        "budget 120",
    )
    check(
        "a command file at exactly 120 lines is allowed",
        run_command_budget(120 - len(FRONTMATTER.splitlines()), allowance=None),
        False,
    )
    check(
        "a command file over 120 lines but listed in the allowance is allowed",
        run_command_budget(150, allowance={
            "plugin/crew/commands/fixture.md":
                {"lines": 150 + len(FRONTMATTER.splitlines()), "reason": "T8: to trim"},
        }),
        False,
    )
    check(
        "an allowance-listed file that grew past its recorded line count is red",
        run_allowance_growth(recorded_lines=150, total_lines=160,
                              reason="T8: to trim"),
        True,
        "grew to",
    )
    check(
        "an allowance-listed file at exactly its recorded line count is allowed",
        run_allowance_growth(recorded_lines=150, total_lines=150,
                              reason="held: awaiting owner decision on T2 deletions"),
        False,
    )
    check(
        "an allowance entry with an unrecognised reason is rejected",
        run_allowance_growth(recorded_lines=150, total_lines=150,
                              reason="because I said so"),
        True,
        "must be",
    )

    # --- stale names ----------------------------------------------------
    check(
        "a stale name in a maintained new-1.0 file is red",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the fallback pass.\n",
            "plugin/crew/commands/newthing.md",
        ),
        True,
        "stale name",
    )
    check(
        "the same stale name marked <!-- deliberate --> in the same paragraph is allowed",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the fallback pass. <!-- deliberate -->\n",
            "plugin/crew/commands/newthing.md",
        ),
        False,
    )
    check(
        "a marker on the NEXT line of the same paragraph still exempts a wrapped sentence",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the\nfallback pass. <!-- deliberate -->\n",
            "plugin/crew/commands/newthing.md",
        ),
        False,
    )
    check(
        "a marker in the NEXT paragraph does not exempt an earlier one",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the fallback pass.\n\n"
            "Unrelated paragraph. <!-- deliberate -->\n",
            "plugin/crew/commands/newthing.md",
        ),
        True,
        "stale name",
    )
    check(
        "a stale name inside frontmatter (a description) is not flagged",
        run_stale_names(
            "---\ndescription: crew 1.0 successor of qa-reviewer\n---\n\nbody text\n",
            "plugin/crew/agents/newagent.md",
        ),
        False,
    )
    check(
        "the same stale name in a file NOT on the maintained list is not checked",
        run_stale_names(
            FRONTMATTER + "qa-reviewer\n",
            "plugin/crew/commands/untracked.md",
            maintained=False,
        ),
        False,
    )

    # --- broken references ----------------------------------------------
    check(
        "a ${CLAUDE_PLUGIN_ROOT} path that does not exist is red",
        run_broken_references(
            FRONTMATTER + "Run ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/does_not_exist.py\n"
        ),
        True,
        "names missing",
    )
    check(
        "a ${CLAUDE_PLUGIN_ROOT} path that exists is allowed",
        run_broken_references(
            FRONTMATTER + "Run ${CLAUDE_PLUGIN_ROOT}/commands/fixture.md\n"
        ),
        False,
    )
    check(
        "a relative Markdown link that does not resolve is red",
        run_broken_references(
            FRONTMATTER + "See [the skill](../skills/does-not-exist/SKILL.md).\n"
        ),
        True,
        "does not resolve",
    )
    check(
        "an http(s) link is never checked as a local path",
        run_broken_references(
            FRONTMATTER + "See [docs](https://example.com/does/not/exist).\n"
        ),
        False,
    )

    print(f"\ninstruction-budgets: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

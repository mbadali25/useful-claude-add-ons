#!/usr/bin/env python3
"""Sabotage suite for check-marketplace.py's check_crew_ignore_policy.

Every case builds a throwaway git repo in a temp directory and points the
checker's ROOT at it. Nothing touches this repository's own files.

The check asserts that the `.crew/` un-ignore list is ONE set wherever it is
stated: `.gitignore` is the authority (it is what git obeys), the shipped
template in `crew-setup/SKILL.md` teaches it to consuming repos, and several
docs restate it in prose. Before this existed they had drifted into stating
three different policies at once, including a `.gitignore` comment asserting
that nothing under `.crew/` is ever committed, fifty lines below two negations
that committed two paths.

Like `self-claims.py`, **much of the value is in what this does NOT report.**
The check is marker-keyed, so a file that mentions one or two paths in passing
is deliberately not checked - `TODO.md` and `commands/review.md` both do, and a
checker that read "two mentions" as "a declaration" would fail them for being
correctly narrow. That silence is asserted here as hard as the failures are.

The three fail-open shapes get their own cases, because each would let the
check pass while checking nothing: an empty extraction (a doc that stops using
the `!.crew/x` form), every marker deleted, and `.crew/` written with a trailing
slash (git then refuses to descend and every negation below is dead, while the
file still reads as though the policy were in force).

The marker is `crew-ignore-policy:list`, with the colon, and the colon is
load-bearing. It was a bare hyphenated word first, which is also a legal
FILENAME - and `.github/workflows/marketplace.yml` names this very file in its
`run:` line, so the workflow read as a file declaring the policy and failed for
declaring none. A colon cannot appear in a Windows path, so a citation of the
suite can no longer be mistaken for a declaration of the list.

Run: python3 scripts/_test/crew-ignore-policy.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
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

# A .gitignore that states the policy correctly: `.crew/*`, the three-path
# un-ignore list, then the approval marker BELOW the negations.
GOOD_GITIGNORE = """\
# crew-ignore-policy:list
.crew/*
!.crew/codemap/
!.crew/endpoints.json
!.crew/verify.json
.crew/.approved-*
.work/
"""

# The shipped template, same list, inside a fenced block.
GOOD_TEMPLATE = """\
## 3c. Gitignore

<!-- crew-ignore-policy:list -->

```gitignore
.crew/*
!.crew/codemap/
!.crew/endpoints.json
!.crew/verify.json
.crew/.approved-*
```
"""


def build(tmp: str, files: dict[str, str]) -> None:
    """Write a fixture repo and git-add it so `git ls-files` sees the files."""
    for name, body in files.items():
        path = os.path.join(tmp, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    subprocess.run(["git", "-C", tmp, "init", "-q"], check=False, capture_output=True)
    # -f: the fixture .gitignore ignores paths the fixture itself creates.
    subprocess.run(["git", "-C", tmp, "add", "-A", "-f"],
                   check=False, capture_output=True)


def run(files: dict[str, str]) -> list[str]:
    """Run check_crew_ignore_policy against a fixture and return its failures."""
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, files)
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            problems: list[str] = []
            CHECKER.check_crew_ignore_policy(problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved


def base(**overrides: str) -> dict[str, str]:
    """The two required sources, correct, with any file overridden or added."""
    files = {
        ".gitignore": GOOD_GITIGNORE,
        CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE,
    }
    files.update(overrides)
    return files


DOC = "plugin/crew/README.md"

CASES: list[tuple[str, dict, int, str]] = [
    # --- must block ------------------------------------------------------
    (
        "a marked doc listing two of the three paths",
        base(**{DOC: "<!-- crew-ignore-policy:list -->\n"
                     "`!.crew/codemap/` and `!.crew/verify.json`.\n"}),
        1,
        "omits !.crew/endpoints.json",
    ),
    (
        "a marked doc naming a fourth path nothing un-ignores",
        base(**{DOC: "<!-- crew-ignore-policy:list -->\n`!.crew/codemap/`, "
                     "`!.crew/endpoints.json`, `!.crew/verify.json`, "
                     "`!.crew/metrics.md`.\n"}),
        1,
        "adds !.crew/metrics.md",
    ),
    (
        "the shipped template drifting from .gitignore",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            "!.crew/endpoints.json\n", "")}),
        1,
        "omits !.crew/endpoints.json",
    ),
    (
        "a marked doc that declares nothing at all (empty extraction)",
        base(**{DOC: "<!-- crew-ignore-policy:list -->\nThe policy is described "
                     "here in prose with no paths.\n"}),
        1,
        "declares no",
    ),
    (
        ".gitignore carrying the marker but no negations at all",
        base(**{".gitignore": "# crew-ignore-policy:list\n.crew/*\n.crew/.approved-*\n"}),
        1,
        "declares no",
    ),
    (
        ".gitignore losing its marker entirely",
        base(**{".gitignore": GOOD_GITIGNORE.replace("# crew-ignore-policy:list\n", "")}),
        2,
        "does not carry",
    ),
    (
        "a marked markdown source shipping no fenced block at all",
        base(**{CHECKER.POLICY_TEMPLATE: "## 3c\n\n<!-- crew-ignore-policy:list -->\n"
                                         "Copy `!.crew/codemap/`, `!.crew/endpoints.json` "
                                         "and `!.crew/verify.json` into .gitignore.\n"}),
        1,
        "no ```gitignore fenced block",
    ),
    (
        "the shipped template losing its marker entirely",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            "<!-- crew-ignore-policy:list -->\n", "")}),
        1,
        "does not carry",
    ),
    (
        "`.crew/` with a trailing slash, which kills every negation below it",
        base(**{".gitignore": GOOD_GITIGNORE.replace(".crew/*\n", ".crew/\n")}),
        5,
        "trailing slash",
    ),
    (
        "the approval marker dropped from the shipped template",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            ".crew/.approved-*\n", "")}),
        1,
        "no active `.crew/.approved-*` rule",
    ),
    # --- the four mutations Codex found, each of which produced ZERO failures
    # --- against the first version of this check.
    (
        "BLOCK 1a: the template's negation COMMENTED OUT, prose left intact",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            "!.crew/endpoints.json\n", "# !.crew/endpoints.json\n")}),
        1,
        "omits !.crew/endpoints.json",
    ),
    (
        # Reported against the TEMPLATE, not against .gitignore, and that is
        # right: .gitignore is the authority, so when it loses a rule every
        # other source is what now disagrees with it. The failure names a real
        # divergence and points at a real file either way.
        "BLOCK 1b: a .gitignore negation DELETED while a comment still names it",
        base(**{".gitignore": GOOD_GITIGNORE.replace(
            "!.crew/endpoints.json\n",
            "# the endpoint ledger, !.crew/endpoints.json, travels\n")}),
        1,
        "adds !.crew/endpoints.json",
    ),
    (
        "BLOCK 1c: the active `.crew/*` DELETED, its explanatory comment left behind",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            ".crew/*\n", "# `.crew/*`, never `.crew/`, or the negations die\n")}),
        2,
        "no active `.crew/*` rule",
    ),
    (
        "BLOCK 2: `.crew/*` moved BELOW the negations, suppressing all three",
        base(**{CHECKER.POLICY_TEMPLATE: "## 3c\n\n<!-- crew-ignore-policy:list -->\n\n"
                                         "```gitignore\n!.crew/codemap/\n"
                                         "!.crew/endpoints.json\n!.crew/verify.json\n"
                                         ".crew/*\n.crew/.approved-*\n```\n"}),
        3,
        "git disagrees with the stated policy",
    ),
    (
        # Asserted because the FIRST version of this check claimed the opposite,
        # and was wrong. `.crew/*` already ignores the marker and none of the
        # three exceptions re-admits it, so where `.crew/.approved-*` sits
        # relative to the negations does not change what git does. Proven by
        # probing git rather than by reading the lines.
        "the approval marker ABOVE the negations is harmless, and git says so",
        base(**{".gitignore": "# crew-ignore-policy:list\n.crew/*\n.crew/.approved-*\n"
                              "!.crew/codemap/\n!.crew/endpoints.json\n"
                              "!.crew/verify.json\n"}),
        0,
        "",
    ),
    # --- must allow ------------------------------------------------------
    (
        # The check shipped with this as a live false positive, found in review
        # rather than by the suite. The ordering search ran over the WHOLE
        # markdown file, so one sentence written below the fence moved the last
        # `!.crew/` past `.crew/.approved-*` and failed a correct template - the
        # "fails correct lines" failure mode, inside the check written to prevent
        # it. Ordering is now scoped to the fenced block.
        "prose mentioning a path BELOW the template's fence, which is not the template",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE
                + "\nNote that `!.crew/verify.json` is the newest entry.\n"}),
        0,
        "",
    ),
    (
        "prose mentioning a path ABOVE the fence does not add to the shipped set",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            "```gitignore", "An earlier draft also had `!.crew/metrics.md`.\n\n```gitignore")}),
        0,
        "",
    ),
    (
        "the policy stated correctly in .gitignore, the template and a doc",
        base(**{DOC: "<!-- crew-ignore-policy:list -->\n`!.crew/codemap/`, "
                     "`!.crew/endpoints.json`, `!.crew/verify.json`.\n"}),
        0,
        "",
    ),
    (
        "trailing-slash variance between a .gitignore and a doc's prose",
        base(**{DOC: "<!-- crew-ignore-policy:list -->\n`!.crew/codemap` (no slash), "
                     "`!.crew/endpoints.json`, `!.crew/verify.json`.\n"}),
        0,
        "",
    ),
    (
        "an UNMARKED file mentioning one path in passing is not checked",
        base(**{"TODO.md": "Resolved by adding `!.crew/verify.json`.\n"}),
        0,
        "",
    ),
    (
        "an UNMARKED file mentioning two paths in passing is still not checked",
        base(**{"TODO.md": "`!.crew/verify.json` followed `!.crew/codemap/`.\n"}),
        0,
        "",
    ),
    (
        # BLOCK 1 of round 2. `.strip()` before the probe made this line and a
        # correct one identical, so the checker repaired the rule and then
        # verified the repair. Measured: with the leading space git leaves
        # .crew/endpoints.json IGNORED while .crew/verify.json is un-ignored.
        "a leading space on an exception, which git does NOT treat as the same rule",
        base(**{".gitignore": GOOD_GITIGNORE.replace(
            "!.crew/endpoints.json\n", " !.crew/endpoints.json\n")}),
        1,
        ".crew/endpoints.json is ignored but must be tracked",
    ),
    (
        "a leading space in the shipped template is caught the same way",
        base(**{CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
            "!.crew/verify.json\n", "\t!.crew/verify.json\n")}),
        1,
        ".crew/verify.json is ignored but must be tracked",
    ),
    (
        # Found while sabotage-testing: the 0.19.46 CHANGELOG entry describes
        # this check and names its marker, which silently made an append-only
        # history file a marked source. It passed only because the policy it
        # describes is today's. The next entry recording a CHANGE to the list
        # would state the old list, correctly, and fail for being accurate.
        "CHANGELOG.md is history and is never a declaration, even carrying the marker",
        base(**{"CHANGELOG.md": "<!-- crew-ignore-policy:list -->\n0.19.0 un-ignored "
                                "only `!.crew/metrics.md`, which is no longer the list.\n"}),
        0,
        "",
    ),
    (
        "an UNMARKED file stating a flatly wrong list is not checked",
        base(**{"CHANGELOG.md": "0.1.0 un-ignored `!.crew/metrics.md` only.\n"}),
        0,
        "",
    ),
    (
        "a fourth path added consistently everywhere is a policy change, not a drift",
        base(**{
            ".gitignore": GOOD_GITIGNORE.replace(
                "!.crew/verify.json\n", "!.crew/verify.json\n!.crew/runbooks/\n"),
            CHECKER.POLICY_TEMPLATE: GOOD_TEMPLATE.replace(
                "!.crew/verify.json\n", "!.crew/verify.json\n!.crew/runbooks/\n"),
        }),
        0,
        "",
    ),
]


GOOD_RULES = [".crew/*", "!.crew/codemap/", "!.crew/endpoints.json",
              "!.crew/verify.json", ".crew/.approved-*"]
GOOD_EXCEPTIONS = {"codemap/", "endpoints.json", "verify.json"}


class _Broken:
    """Force one git subcommand to fail, leaving the rest real.

    Mocks the failures that cannot be produced by writing a fixture: a fatal
    `git check-ignore` (status 128 - a corrupt index, a pathspec git rejects, a
    binary that cannot run) and a `git init` that does not create a repo (a full
    disk, a read-only temp directory, an interfering GIT_DIR).
    """

    def __init__(self, subcommand: str, status: int, message: str):
        self.subcommand = subcommand
        self.status = status
        self.message = message
        self.real = CHECKER.subprocess.run

    def __call__(self, cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and self.subcommand in cmd:
            return subprocess.CompletedProcess(
                cmd, self.status, stdout="", stderr=self.message)
        return self.real(cmd, *args, **kwargs)


def run_probe(broken: _Broken | None) -> list[str]:
    """`_ignore_behaviour` on a CORRECT rule set, with one git call sabotaged.

    The rules are right, so any finding at all means the probe reported its own
    inability to answer - which is the whole point. A silent empty list here is
    the bug: an unknown collapsing into the safe-looking value.
    """
    saved = CHECKER.subprocess.run
    if broken:
        CHECKER.subprocess.run = broken
    try:
        return CHECKER._ignore_behaviour(  # pylint: disable=protected-access
            list(GOOD_RULES), set(GOOD_EXCEPTIONS))
    finally:
        CHECKER.subprocess.run = saved


PROBE_CASES: list[tuple[str, _Broken | None, int, str]] = [
    (
        "correct rules, real git: the probe finds nothing to report",
        None,
        0,
        "",
    ),
    (
        "BLOCK 2a: `git check-ignore` exits 128 on every probe",
        _Broken("check-ignore", 128, "fatal: unable to read index file"),
        5,
        "UNVERIFIABLE",
    ),
    (
        "BLOCK 2b: `git check-ignore` exits 129 (usage), also not an answer",
        _Broken("check-ignore", 129, "usage: git check-ignore"),
        5,
        "is UNKNOWN, not clean",
    ),
    (
        "BLOCK 2c: `git init` fails, so no probe repo exists at all",
        _Broken("init", 128, "fatal: cannot mkdir: No space left on device"),
        1,
        "could not create the probe repository",
    ),
]


def main() -> int:
    passed = failed = 0
    for name, broken, expected, needle in PROBE_CASES:
        problems = run_probe(broken)
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} finding(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    for name, files, expected, needle in CASES:
        problems = run(files)
        ok = len(problems) == expected
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s)"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {len(problems)}: {problems}")

    print(f"\ncrew-ignore-policy: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

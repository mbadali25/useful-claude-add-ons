#!/usr/bin/env python3
"""Sabotage suite for check-marketplace.py's check_self_claims.

Every case here builds a throwaway git repo in a temp directory and points the
checker's ROOT at it. Nothing touches this repository's own files.

The suite exists because the check it covers is unusual: **most of its value is
in what it does NOT report.** A marker-keyed check that quietly started
flagging every unmarked number would be indistinguishable, in CI, from one that
was working - right up to the point where it failed a correct line and somebody
"fixed" the line. So the silence is asserted as hard as the failures.

The must-block cases are the ones the check was written for; the must-allow
cases are the ones that keep it honest.

Run: python3 scripts/_test/self-claims.py
"""

from __future__ import annotations

import importlib.util
import json
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

ENTRIES = [
    {"name": f"skill-{n}", "source": f"./skills/skill-{n}", "version": "1.0.0"}
    for n in range(3)
] + [{"name": "widget", "source": "./plugin/widget", "version": "2.5.1"}]
SKILLS = 3  # three ./skills/ entries above


def build(
    tmp: str,
    docs: dict[str, str],
    plugin_version: str = "2.5.1",
    widget_skills: list[str] | None = None,
) -> None:
    """Write a fixture repo: the docs under test plus one plugin manifest.

    ``widget_skills`` names the subdirectories of ``plugin/widget/skills/`` to
    create, each with its own ``SKILL.md`` -- mirroring how `plugin-skills:`
    counts a real plugin's bundle. ``None`` creates no ``skills/`` directory at
    all, which `count_plugin_skills` treats the same as zero.
    """
    manifest = os.path.join(tmp, "plugin", "widget", ".claude-plugin")
    os.makedirs(manifest, exist_ok=True)
    with open(os.path.join(manifest, "plugin.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": "widget", "version": plugin_version}, fh)

    if widget_skills is not None:
        for skill in widget_skills:
            skill_dir = os.path.join(tmp, "plugin", "widget", "skills", skill)
            os.makedirs(skill_dir, exist_ok=True)
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write(f"# {skill}\n")

    for name, body in docs.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)

    subprocess.run(["git", "-C", tmp, "init", "-q"], check=False, capture_output=True)
    subprocess.run(["git", "-C", tmp, "add", "-A"], check=False, capture_output=True)


def run(
    docs: dict[str, str],
    plugin_version: str = "2.5.1",
    widget_skills: list[str] | None = None,
) -> list[str]:
    """Run check_self_claims against a fixture and return its failures."""
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, docs, plugin_version, widget_skills)
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            problems: list[str] = []
            CHECKER.check_self_claims(ENTRIES, problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved


CASES: list[tuple[str, dict, int, str]] = [
    # --- must block ------------------------------------------------------
    (
        "a marked number that disagrees with marketplace.json",
        {"README.md": "The repo ships 9 skills<!-- claim: skills-count --> today.\n"},
        1,
        "registers 3",
    ),
    (
        "a marked 'N of N' where only one half was updated",
        {"README.md": "<!-- claim: skills-count -->\n```\n  [x] 3 of 9 skills\n```\n"},
        1,
        "registers 3",
    ),
    (
        "a marked catalog version that disagrees with plugin.json",
        {"P.md": "<!-- claim: plugin-version:widget -->\n| **Version** | 1.0.0 |\n"},
        1,
        "plugin.json",
    ),
    (
        "a claim type the checker does not implement",
        {"README.md": "<!-- claim: hook-count -->\nsomething\n"},
        1,
        "unknown claim type",
    ),
    (
        "a claim naming a plugin that is not registered",
        {"P.md": "<!-- claim: plugin-version:ghost -->\n| **Version** | 1.0.0 |\n"},
        1,
        "no entry",
    ),
    (
        "a marker whose target was edited away binds to nothing",
        {"README.md": "<!-- claim: skills-count -->\n" + "filler\n" * 20},
        1,
        "binds to nothing",
    ),
    (
        "a marker further from its target than the binding window",
        {
            "README.md": "<!-- claim: skills-count -->\n"
            + "filler\n" * 15
            + "3 skills\n"
        },
        1,
        "binds to nothing",
    ),
    # --- must allow ------------------------------------------------------
    (
        "a marked number that is correct",
        {"README.md": "The repo ships 3 skills<!-- claim: skills-count --> today.\n"},
        0,
        "",
    ),
    (
        "a marked 'N of N' where both halves are correct",
        {"README.md": "<!-- claim: skills-count -->\n```\n  [x] 3 of 3 skills\n```\n"},
        0,
        "",
    ),
    (
        "a marked catalog version that matches plugin.json",
        {"P.md": "<!-- claim: plugin-version:widget -->\n| **Version** | 2.5.1 |\n"},
        0,
        "",
    ),
    (
        "a marker reaching into a fenced block from above it",
        {"README.md": "intro\n\n<!-- claim: skills-count -->\n```\n  3 skills\n```\n"},
        0,
        "",
    ),
    # --- the silence, asserted ------------------------------------------
    # Each of these is a WRONG number with no marker. The check must say
    # nothing. If one of them ever fails, the check has started guessing which
    # numbers are claims, and it cannot do that correctly - `17 skills` is a
    # true sentence about crew's bundle and a false one about the marketplace.
    (
        "an unmarked wrong number is not the checker's business",
        {"README.md": "The repo ships 9 skills today.\n"},
        0,
        "",
    ),
    (
        "an unmarked wrong number beside a marked correct one",
        {
            "README.md": "crew bundles 17 skills.\n"
            "The repo ships 3 skills<!-- claim: skills-count --> today.\n"
        },
        0,
        "",
    ),
    (
        "an unmarked catalog version row is not checked",
        {"P.md": "| **Version** | 0.0.1 |\n"},
        0,
        "",
    ),
    (
        "a file with no markers at all produces nothing",
        {"README.md": "28 skills, 50 agents, 4 plugins, and 7 of 4 marketplaces.\n"},
        0,
        "",
    ),
    # --- documenting the convention is not making a claim -----------------
    # CLAUDE.md explains this syntax, and the first version of the check read
    # that explanation as nine live claims and failed on the paragraph
    # describing itself. A marker only counts where it would really be an
    # invisible HTML comment.
    (
        "a marker inside a code span is documentation, not a claim",
        {
            "CLAUDE.md": "Write `<!-- claim: skills-count -->` beside it. "
            "`17 skills` is true of crew's bundle and false of the marketplace.\n"
        },
        0,
        "",
    ),
    (
        "a marker inside a fenced block is not a claim either",
        {"README.md": "```\n<!-- claim: skills-count -->\n9 skills\n```\n"},
        0,
        "",
    ),
    (
        "a real marker still works on a line that also has a code span",
        {"README.md": "all 3 skills<!-- claim: skills-count --> in `skills/`\n"},
        0,
        "",
    ),
    (
        "a real marker on a line with a code span still catches a wrong number",
        {"README.md": "all 9 skills<!-- claim: skills-count --> in `skills/`\n"},
        1,
        "registers 3",
    ),
]

# `plugin-skills:<name>` -- a plugin's OWN bundled-skill count, as opposed to
# `skills-count`'s marketplace total. Each case names how many SKILL.md-bearing
# directories to create under plugin/widget/skills/, distinct from CASES above
# because this marker type reads the filesystem, not marketplace.json.
CASES_PLUGIN_SKILLS: list[tuple[str, dict, int, str, list[str] | None]] = [
    # --- must block ------------------------------------------------------
    (
        "a marked plugin-skills count that disagrees with the filesystem",
        {"P.md": "widget bundles 5 skills<!-- claim: plugin-skills:widget -->.\n"},
        1,
        "plugin/widget/skills/ has 2",
        ["alpha", "beta"],
    ),
    (
        "a plugin-skills claim naming a plugin with no ./plugin/ entry",
        {"P.md": "<!-- claim: plugin-skills:ghost -->\n5 skills\n"},
        1,
        "no entry",
        None,
    ),
    (
        "a plugin-skills marker whose target was edited away binds to nothing",
        {"P.md": "<!-- claim: plugin-skills:widget -->\n" + "filler\n" * 20},
        1,
        "binds to nothing",
        ["alpha"],
    ),
    # --- must allow ------------------------------------------------------
    (
        "a marked plugin-skills count that matches the filesystem",
        {"P.md": "widget bundles 2 skills<!-- claim: plugin-skills:widget -->.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
    (
        "a marked plugin-skills count of zero, no skills/ directory at all",
        {"P.md": "widget bundles 0 skills<!-- claim: plugin-skills:widget -->.\n"},
        0,
        "",
        None,
    ),
    (
        "'bundled skills' phrasing, not just 'skills', still binds",
        {"P.md": "54 agents, 2 bundled skills<!-- claim: plugin-skills:widget -->.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
    (
        "singular 'skill' still binds",
        {"P.md": "1 skill<!-- claim: plugin-skills:widget -->, no agents.\n"},
        0,
        "",
        ["alpha"],
    ),
    # --- the silence, asserted ------------------------------------------
    (
        "an unmarked plugin skill count is not the checker's business",
        {"P.md": "widget bundles 5 skills, actually 2.\n"},
        0,
        "",
        ["alpha", "beta"],
    ),
]


def main() -> int:
    passed = failed = 0
    for name, docs, expected, needle in CASES:
        problems = run(docs)
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

    for name, docs, expected, needle, widget_skills in CASES_PLUGIN_SKILLS:
        problems = run(docs, widget_skills=widget_skills)
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

    print(f"\nself-claims: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

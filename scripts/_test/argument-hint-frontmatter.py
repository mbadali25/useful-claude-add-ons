#!/usr/bin/env python3
"""Sabotage suite for check-marketplace.py's check_argument_hint_frontmatter.

Every case here builds a throwaway directory and points the checker's ROOT at
it, so nothing touches this repository's own files. It mirrors
scripts/_test/self-claims.py's fixture-and-monkeypatch shape.

The bug this guards: `argument-hint: [a] [b]` - two bracket groups, unquoted -
parses to PyYAML as a flow sequence for the first `[...]` with the second left
over as trailing garbage, and the parse fails. Claude Code then loads the file
with EMPTY frontmatter, silently, not just a dropped `argument-hint`. This
shipped in `localgpu` 0.1.19 and `obsidian-vault` 0.3.9 in four files, and
`claude plugin validate` found it, not this repo's own gate.

The check parses the whole frontmatter block, so it also has to catch a
frontmatter break that has nothing to do with brackets - the must-block cases
below include one, and it is the same bug class that turned up separately in
`notify` 1.1.0's SKILL.md (an unquoted `: ` inside a plain scalar), fixed
alongside this suite.

The checker's globs originally covered commands and SKILL.md files only -
agent files (`plugin/**/agents/*.md`, `skills/**/agents/*.md`) were missing
entirely, so `plugin/crew/agents/*.md` (54 files) had no frontmatter parse at
all. The gap surfaced the same bug class in a third shape: the `<example>`
convention documented in the `plugin-dev` plugin's own `plugin-validator.md`
puts a bare trailing `Examples:` in an unquoted plain `description` scalar,
which YAML reads as the start of a new mapping key and refuses with "mapping
values are not allowed here" - silently dropping `tools` and `model` right
alongside it. The must-block cases below cover both `plugin/**/agents/*.md`
and `skills/**/agents/*.md`; the matching must-allow case shows the fix is a
block scalar (`description: |`), which carries the identical text without
tripping the parser.

Codex review of that same function found two more files the checker was
silently not scanning, rather than scanning and passing:

- The `commands`/`agents` globs ended in a literal `*.md`, matching only
  files directly inside those directories. Claude Code namespaces a command
  by its subdirectory (`commands/group/x.md` -> `/plugin:group:x`), so a
  file at that depth was skipped outright. Widened to `**/*.md` under both
  `commands` and `agents`, for both `plugin` and `skills`.
- The closing-delimiter search required a newline after the closing `---`.
  A file whose content ends exactly at that delimiter - no trailing
  newline - has no `\n---\n` substring anywhere in it, so it was skipped
  regardless of what its frontmatter said. The delimiter search now also
  accepts the closing `---` at end of file.

Run: python3 scripts/_test/argument-hint-frontmatter.py
"""

from __future__ import annotations

import importlib.util
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-marketplace.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def build(tmp: str, files: dict[str, str]) -> None:
    """Write a fixture repo: just the frontmatter-bearing files under test."""
    for name, body in files.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)


def run(files: dict[str, str]) -> list[str]:
    """Run check_argument_hint_frontmatter against a fixture, return failures."""
    with tempfile.TemporaryDirectory() as tmp:
        build(tmp, files)
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            problems: list[str] = []
            CHECKER.check_argument_hint_frontmatter(problems.append)
            return problems
        finally:
            CHECKER.ROOT = saved


CASES: list[tuple[str, dict, int, str]] = [
    # --- must block --------------------------------------------------------
    (
        "an unquoted argument-hint with two bracket groups (the shipped bug)",
        {
            "plugin/widget/commands/index.md": (
                "---\n"
                "description: does a thing\n"
                "argument-hint: [--full] [--root <path>]\n"
                "allowed-tools: Read\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "the exact obsidian-vault/graph.md shape, three bracket groups deep",
        {
            "plugin/widget/commands/graph.md": (
                "---\n"
                "description: build a graph\n"
                'argument-hint: [repo-path, default cwd] [vault-name, default "codegraphs"]\n'
                "allowed-tools: Read, Bash\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "a frontmatter break unrelated to brackets - the notify shape",
        {
            "skills/widget/SKILL.md": (
                "---\n"
                "name: widget\n"
                "description: does a thing: with an unquoted colon-space\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "a nested skill under a plugin carries the same rule",
        {
            "plugin/widget/skills/inner/SKILL.md": (
                "---\n"
                "name: inner\n"
                "argument-hint: [a] [b]\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "a skill's own commands/ directory is covered too",
        {
            "skills/widget/commands/setup.md": (
                "---\n"
                "description: set up\n"
                "argument-hint: [a] [b]\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "an agent's own <example> convention breaks the same way - a bare "
        "trailing 'Examples:' in a plain scalar description",
        {
            "plugin/widget/agents/reviewer.md": (
                "---\n"
                "name: widget-reviewer\n"
                "description: Use this agent when reviewing widget code for "
                "defects. Examples:\n\n<example>\n"
                'Context: A PR touches widget rendering.\n'
                'user: "review this widget change"\n'
                'assistant: "I will use the widget-reviewer agent to check it."\n'
                "</example>\n"
                "tools: Read, Grep, Glob\n"
                "model: sonnet\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "a skill's own agents/ directory is covered too, same shape",
        {
            "skills/widget/agents/reviewer.md": (
                "---\n"
                "name: widget-reviewer\n"
                "description: Use this agent when reviewing widget code for "
                "defects. Examples:\n\n<example>\ndone\n</example>\n"
                "tools: Read\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "a command in a namespaced subdirectory is not exempt - Claude Code "
        "reads commands/group/x.md as /plugin:group:x, same as commands/x.md",
        {
            "plugin/widget/commands/group/test.md": (
                "---\n"
                "description: does a thing\n"
                "argument-hint: [a] [b]\n"
                "---\n\nbody\n"
            )
        },
        1,
        "not valid YAML",
    ),
    (
        "the same nesting rule applies under a skill's commands/, and under "
        "agents/ for both plugins and skills",
        {
            "skills/widget/commands/group/setup.md": (
                "---\ndescription: set up\nargument-hint: [a] [b]\n---\n\nbody\n"
            ),
            "plugin/widget/agents/team/reviewer.md": (
                "---\nname: r\nargument-hint: [a] [b]\n---\n\nbody\n"
            ),
            "skills/widget/agents/team/reviewer.md": (
                "---\nname: r\nargument-hint: [a] [b]\n---\n\nbody\n"
            ),
        },
        3,
        "not valid YAML",
    ),
    (
        "malformed frontmatter is not exempt just because the file ends "
        "exactly at the closing '---' with no trailing newline",
        {
            "plugin/widget/commands/truncated.md": (
                "---\nargument-hint: [a] [b]\n---"
            )
        },
        1,
        "not valid YAML",
    ),
    # --- must allow ----------------------------------------------------------
    (
        "a single-bracket argument-hint parses fine (a 1-item list)",
        {
            "plugin/widget/commands/one.md": (
                "---\n"
                "description: does a thing\n"
                "argument-hint: [--full]\n"
                "allowed-tools: Read\n"
                "---\n\nbody\n"
            )
        },
        0,
        "",
    ),
    (
        "a two-bracket argument-hint quoted as a string is the fix",
        {
            "plugin/widget/commands/fixed.md": (
                "---\n"
                "description: does a thing\n"
                'argument-hint: "[--full] [--root <path>]"\n'
                "allowed-tools: Read\n"
                "---\n\nbody\n"
            )
        },
        0,
        "",
    ),
    (
        "no frontmatter at all is not this check's problem",
        {"plugin/widget/commands/bare.md": "# no frontmatter here\n"},
        0,
        "",
    ),
    (
        "ordinary valid frontmatter with no argument-hint at all",
        {
            "skills/widget/SKILL.md": (
                "---\nname: widget\ndescription: does a thing\n---\n\nbody\n"
            )
        },
        0,
        "",
    ),
    (
        "the same 'Examples:' text as a block scalar (description: |) is the "
        "agent-file fix - it carries the identical text without tripping the "
        "parser",
        {
            "plugin/widget/agents/reviewer.md": (
                "---\n"
                "name: widget-reviewer\n"
                "description: |\n"
                "  Use this agent when reviewing widget code for defects. "
                "Examples:\n\n"
                "  <example>\n"
                "  Context: A PR touches widget rendering.\n"
                '  user: "review this widget change"\n'
                '  assistant: "I will use the widget-reviewer agent to check it."\n'
                "  </example>\n"
                "tools: Read, Grep, Glob\n"
                "model: sonnet\n"
                "---\n\nbody\n"
            )
        },
        0,
        "",
    ),
]


def main() -> int:
    failures = 0
    for label, files, want_count, want_substr in CASES:
        problems = run(files)
        ok = len(problems) == want_count and (
            not want_substr or any(want_substr in p for p in problems)
        )
        status = "ok" if ok else "FAIL"
        print(f"[{status}] {label} -> {problems}")
        if not ok:
            failures += 1

    # Sabotage: prove the must-block cases actually exercise the checker by
    # confirming a known-good fixture (the "fixed" case, re-run standalone)
    # stays green when nothing is broken, and that removing the quote from it
    # turns it red again - i.e. this suite would notice check_argument_hint_
    # frontmatter regressing to a no-op.
    good = run({
        "plugin/widget/commands/fixed.md": (
            "---\ndescription: d\nargument-hint: \"[a] [b]\"\n---\n\nbody\n"
        )
    })
    broken = run({
        "plugin/widget/commands/fixed.md": (
            "---\ndescription: d\nargument-hint: [a] [b]\n---\n\nbody\n"
        )
    })
    if good or not broken:
        print(f"[FAIL] sabotage control: good={good} broken={broken}")
        failures += 1
    else:
        print(f"[ok] sabotage control: quoting is what fixes it (broken -> {broken})")

    print()
    if failures:
        print(f"{failures} case(s) failed")
        return 1
    print(f"all {len(CASES)} cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify crew 1.0's instruction-surface budgets and checks.

`docs/review/04-redesign.md`'s "Instruction surface" table sets the sizes;
`plugin/crew/BUDGETS.md` tracks where the plugin actually stands against them
(the aggregate total is reported there, checked for ACCURACY by
`check_self_claims`'s `crew-markdown-lines` marker, not gated here -- it
cannot pass while T2's deletions are held, per `TODO.md`). What this script
gates, file by file:

    command file line budget    plugin/crew/commands/*.md, <= COMMAND_MAX_LINES,
                                 exceptions only via .budget-allowance.json,
                                 and a listed file may not GROW past its
                                 recorded line count either
    frontmatter presence        every command/agent/skill starts with a
                                 `---`-delimited block (full parsing and tool-
                                 name checks are validate-prompts.py's job;
                                 this is a cheap presence check, not a
                                 replacement for it)
    generated-file drift        crew_instructions.py --check, for any
                                 generated file this repo actually has
                                 committed (none, at present -- crew's
                                 generators target a CONSUMING repo, not this
                                 marketplace)
    stale names                 a maintained list of pre-1.0 names, checked
                                 only against a maintained list of NEW 1.0
                                 files -- flagging every historical mention
                                 across the repo would fail `04-redesign.md`
                                 itself, which documents the rename on purpose
    broken references           `${CLAUDE_PLUGIN_ROOT}/...` paths and
                                 relative Markdown links in plugin/crew's
                                 Markdown, scoped to plugin/crew the same way
                                 every other check here is
    typed policy IDs            `guards.<name>` references resolve against
                                 `crew_guards.ALL_GUARD_NAMES`, the one place
                                 those names are actually declared

Run with no arguments from anywhere in the repo. Exit status is 0 when clean,
1 when anything is wrong.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREW = os.path.join(ROOT, "plugin", "crew")
ALLOWANCE_PATH = os.path.join(CREW, ".budget-allowance.json")
COMMAND_MAX_LINES = 120
ALLOWED_REASONS = (
    "held: awaiting owner decision on T2 deletions",
    "T8: to trim",
)

# Names that pre-date the crew 1.0 rebuild (`docs/review/04-redesign.md`) and
# should not appear in a file the rebuild itself introduced. Checked only
# against NEW_1_0_FILES below -- an old file (e.g. `commands/ticket.md`) is
# allowed to still say "ticket", and a DESIGN doc that documents the rename
# ("spec replaces /crew:ticket") is not a regression either.
STALE_NAMES = (
    "qa-reviewer",
    "/crew:work",
    "/crew:ticket",
    "/crew:pm",
    "/crew:roster",
    "/crew:scale",
    "pm-journal",
    "pm-pulse",
)

# The maintained list itself. A file belongs here once it is part of the 1.0
# lifecycle rebuild -- add to this list in the same commit that adds the file,
# the same discipline CLAUDE.md asks of marketplace registration.
NEW_1_0_FILES = (
    "AGENTS.md",
    "plugin/crew/commands/approve.md",
    "plugin/crew/commands/brainstorm.md",
    "plugin/crew/commands/spec.md",
    "plugin/crew/commands/plan.md",
    "plugin/crew/commands/implement.md",
    "plugin/crew/commands/done.md",
    "plugin/crew/commands/status.md",
    "plugin/crew/commands/migrate.md",
    "plugin/crew/commands/review.md",
    "plugin/crew/agents/reviewer.md",
)

PLUGIN_PATH_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_\-./]+)")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
GUARD_REF_RE = re.compile(r"\bguards\.([A-Za-z][A-Za-z0-9]*)(\*)?")
FRONTMATTER_START_RE = re.compile(r"\A---\s*\n")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT)


def load_allowance(fail) -> dict:
    """Read `.budget-allowance.json`, or {} with a failure if it is missing
    or malformed -- silently treating a broken allowance file as "no
    exceptions" would fail every currently-held file at once, which is loud
    enough to look like a real regression rather than the allowance file
    itself breaking."""
    if not os.path.isfile(ALLOWANCE_PATH):
        fail(f"{rel(ALLOWANCE_PATH)}: missing")
        return {}
    try:
        data = json.loads(read(ALLOWANCE_PATH))
    except ValueError as exc:
        fail(f"{rel(ALLOWANCE_PATH)}: not valid JSON ({exc})")
        return {}
    if not isinstance(data, dict):
        fail(f"{rel(ALLOWANCE_PATH)}: top level must be an object")
        return {}
    out = {}
    for path, entry in data.items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("lines"), int)
            or entry.get("reason") not in ALLOWED_REASONS
        ):
            fail(
                f"{rel(ALLOWANCE_PATH)}: entry '{path}' must be "
                '{"lines": <int>, "reason": one of ' + repr(ALLOWED_REASONS) + "}"
            )
            continue
        out[path] = entry
    return out


def check_command_budget(allowance: dict, fail) -> None:
    """Every plugin/crew/commands/*.md is <= COMMAND_MAX_LINES, unless
    `.budget-allowance.json` lists it -- and a listed file still fails if it
    has grown past the line count the allowance recorded, so the file is
    debt that cannot be repaid by editing the allowance instead of the file.
    """
    for path in sorted(glob.glob(os.path.join(CREW, "commands", "*.md"))):
        path_rel = rel(path)
        lines = len(read(path).splitlines())
        entry = allowance.get(path_rel)
        if entry is None:
            if lines > COMMAND_MAX_LINES:
                fail(
                    f"{path_rel}: {lines} lines, budget {COMMAND_MAX_LINES} "
                    "and not listed in .budget-allowance.json"
                )
            continue
        if lines > entry["lines"]:
            fail(
                f"{path_rel}: grew to {lines} lines, allowance recorded "
                f"{entry['lines']} ({entry['reason']}) - update the file, "
                "not just the allowance"
            )


def check_allowance_paths_exist(allowance: dict, fail) -> None:
    """A path the allowance still lists but that no longer exists is stale
    bookkeeping, not a passing check -- most likely the file was deleted (the
    T2 held-deletion case this allowance exists for) and the entry was never
    removed."""
    for path_rel in sorted(allowance):
        if not os.path.isfile(os.path.join(ROOT, path_rel)):
            fail(f"{rel(ALLOWANCE_PATH)}: lists '{path_rel}', which no longer exists")


def _has_frontmatter(path: str) -> bool:
    text = read(path)
    if not FRONTMATTER_START_RE.match(text):
        return False
    return "\n---" in text[3:]


def check_frontmatter(fail) -> None:
    """A cheap presence check (frontmatter block exists), not a replacement
    for validate-prompts.py's full YAML parse and tool-name validation."""
    for path in sorted(glob.glob(os.path.join(CREW, "commands", "*.md"))):
        if not _has_frontmatter(path):
            fail(f"{rel(path)}: no frontmatter block")
    for path in sorted(glob.glob(os.path.join(CREW, "agents", "*.md"))):
        if not _has_frontmatter(path):
            fail(f"{rel(path)}: no frontmatter block")
    for path in sorted(glob.glob(os.path.join(CREW, "skills", "*", "SKILL.md"))):
        if not _has_frontmatter(path):
            fail(f"{rel(path)}: no frontmatter block")


def _tracked_generated_files() -> list[str]:
    """Which of this repo's own tracked files are crew_instructions.py
    output, identified the same way the generator identifies its own output
    (the `crew:generated` marker), never by path alone -- a hand-written
    AGENTS.md at the same path (this repo's own, at the time of writing) must
    NOT be treated as drift."""
    found = []
    candidates = [os.path.join(ROOT, "AGENTS.md")]
    candidates += glob.glob(os.path.join(ROOT, ".claude", "rules", "*.md"))
    for path in candidates:
        if os.path.isfile(path) and "crew:generated" in read(path)[:2000]:
            found.append(path)
    codex_hooks = os.path.join(ROOT, ".codex", "hooks.json")
    codex_config = os.path.join(ROOT, ".codex", "config.toml")
    if os.path.isfile(codex_hooks):
        found.append(codex_hooks)
    if os.path.isfile(codex_config) and "crew:generated" in read(codex_config)[:2000]:
        found.append(codex_config)
    return found


def check_generated_drift(fail) -> None:
    generated = _tracked_generated_files()
    if not generated:
        return
    script = os.path.join(CREW, "hooks", "scripts", "crew_instructions.py")
    for kind, path in (("rules", None), ("agents", os.path.join(ROOT, "AGENTS.md")),
                       ("codex", None)):
        if kind == "agents" and path not in generated:
            continue
        if kind != "agents" and not any(p.startswith(os.path.join(ROOT, ".claude")
                                                       if kind == "rules"
                                                       else os.path.join(ROOT, ".codex"))
                                         for p in generated):
            continue
        done = subprocess.run(
            [sys.executable, script, kind, "--root", ROOT, "--check"],
            capture_output=True, text=True, check=False,
        )
        if done.returncode != 0:
            fail(f"generated {kind}: drift - {done.stdout.strip() or done.stderr.strip()}")


def _body_after_frontmatter(text: str) -> tuple[str, int]:
    """(body, first body line number). Frontmatter is metadata (a `name:` or
    `description:` field), not prose to grep for a stale name -- an agent's
    own description legitimately says what it succeeds, and there is nowhere
    to put an inline `<!-- deliberate -->` inside a YAML scalar that would not
    become part of the value itself."""
    if not FRONTMATTER_START_RE.match(text):
        return text, 1
    end = text.find("\n---", 3)
    if end == -1:
        return text, 1
    body_start = text.index("\n", end + 1) + 1 if "\n" in text[end + 1:] else len(text)
    return text[body_start:], text[:body_start].count("\n") + 1


def check_stale_names(fail) -> None:
    """A stale name in a NEW 1.0 file is usually a leftover, but sometimes a
    deliberate cross-reference to the thing it replaces (`04a-redesign-fable.md`'s
    own contradiction-check design uses exactly this escape hatch, `<!--
    deliberate -->`, for the same reason: a rename note that says what it
    replaces is not the regression this check exists to catch). A line
    carrying the marker is skipped; everything else is a live finding.
    """
    for path_rel in NEW_1_0_FILES:
        path = os.path.join(ROOT, path_rel)
        if not os.path.isfile(path):
            continue
        body, start_line = _body_after_frontmatter(read(path))
        lines = body.splitlines()
        # Group into paragraphs (blank-line-delimited), not single lines: this
        # repo hand-wraps prose, so a marked sentence can carry the stale name
        # on one line and the `<!-- deliberate -->` marker on the next after
        # any edit re-wraps it (test_codemap_read_path.py's `_norm` docstring
        # names the same hazard for its own assertions). A marker anywhere in
        # the paragraph exempts the whole paragraph.
        para_start = None
        paragraphs = []
        for i, line in enumerate(lines):
            if line.strip():
                if para_start is None:
                    para_start = i
            elif para_start is not None:
                paragraphs.append((para_start, i - 1))
                para_start = None
        if para_start is not None:
            paragraphs.append((para_start, len(lines) - 1))
        for start, end in paragraphs:
            block = lines[start:end + 1]
            if any("<!-- deliberate -->" in line for line in block):
                continue
            for offset, line in enumerate(block):
                for stale in STALE_NAMES:
                    if stale in line:
                        fail(f"{path_rel}:{start_line + start + offset}: stale name "
                             f"'{stale}' in a crew 1.0 file")


def check_broken_references(fail) -> None:
    for path in sorted(glob.glob(os.path.join(CREW, "**", "*.md"), recursive=True)):
        path_rel = rel(path)
        text = read(path)
        for match in PLUGIN_PATH_RE.finditer(text):
            target = match.group(1).rstrip(".,`)")
            if not os.path.exists(os.path.join(CREW, target)):
                fail(f"{path_rel}: names missing ${{CLAUDE_PLUGIN_ROOT}}/{target}")
        for match in MD_LINK_RE.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = target.split("#", 1)[0].strip()
            if not target or target.startswith("${"):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                fail(f"{path_rel}: relative link target does not resolve: {target}")


def _guard_names() -> set[str] | None:
    scripts_dir = os.path.join(CREW, "hooks", "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import crew_guards  # pylint: disable=import-outside-toplevel,import-error
    except ImportError:
        return None
    return set(crew_guards.ALL_GUARD_NAMES)


def check_policy_ids(fail) -> None:
    names = _guard_names()
    if names is None:
        fail("could not import crew_guards to resolve guards.* policy IDs")
        return
    for path in sorted(glob.glob(os.path.join(CREW, "**", "*.md"), recursive=True)):
        path_rel = rel(path)
        text = read(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in GUARD_REF_RE.finditer(line):
                name, star = match.group(1), match.group(2)
                if star:
                    # `guards.prod*` is a documented PREFIX for prodDatabase/
                    # prodServer, not a policy ID of its own - valid if it is
                    # a real prefix of at least one guard name.
                    if not any(n.startswith(name) for n in names):
                        fail(
                            f"{path_rel}:{lineno}: references guards.{name}*, "
                            "which is not a prefix of any name in "
                            "crew_guards.ALL_GUARD_NAMES"
                        )
                    continue
                if name not in names:
                    fail(
                        f"{path_rel}:{lineno}: references guards.{name}, which "
                        "is not in crew_guards.ALL_GUARD_NAMES"
                    )


def main() -> int:
    problems: list[str] = []

    def fail(message: str) -> None:
        problems.append(message)

    allowance = load_allowance(fail)
    check_command_budget(allowance, fail)
    check_allowance_paths_exist(allowance, fail)
    check_frontmatter(fail)
    check_generated_drift(fail)
    check_stale_names(fail)
    check_broken_references(fail)
    check_policy_ids(fail)

    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("instruction budgets: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verify crew 1.0's instruction-surface budgets and checks.

`docs/review/04-redesign.md`'s "Instruction surface" table sets the sizes;
`plugin/crew/BUDGETS.md` tracks where the plugin actually stands against them
(the aggregate total is reported there, checked for ACCURACY by
`check_self_claims`'s `crew-markdown-lines` marker, not gated here -- it
cannot pass while T2's deletions are held, per `TODO.md`). What this script
gates, file by file:

    command file line budget    plugin/crew/commands/**/*.md (recursed, since
                                 a namespaced command in a subdirectory loads
                                 the same as a top-level one), <= COMMAND_MAX_LINES,
                                 exceptions only via .budget-allowance.json
    allowance growth             no file listed in .budget-allowance.json --
                                 command, agent or skill alike -- may grow past
                                 the line count the allowance recorded
    allowance ceiling            a listed ceiling may not be raised in the same
                                 change that grows the file, unless the entry's
                                 reason is changed to an explicit "raised: <why>"
                                 -- checked against the allowance file as
                                 committed at the merge-base with the default
                                 branch (or --base); UNVERIFIED fails loudly
                                 rather than passing silently when git cannot
                                 answer
    frontmatter presence        every command/agent/skill starts with a
                                 `---`-delimited block and closes it with an
                                 exact `---` line (full parsing and tool-
                                 name checks are validate-prompts.py's job;
                                 this is a cheap presence check, not a
                                 replacement for it)
    generated-file drift        crew_instructions.py --check, for any
                                 generated file this repo actually has
                                 committed (none, at present -- crew's
                                 generators target a CONSUMING repo, not this
                                 marketplace)
    stale names                 a maintained list of pre-1.0 names, scanned
                                 across every plugin/crew Markdown file (and
                                 AGENTS.md) by default -- an explicit,
                                 maintained list of legacy/held files is what
                                 is EXEMPT, so a new 1.0 file nobody remembers
                                 to list is checked, not silently skipped
    broken references           `${CLAUDE_PLUGIN_ROOT}/...` paths, inline
                                 Markdown links (angle-bracket destinations,
                                 titles, balanced parens) and reference-style
                                 links/definitions in plugin/crew's Markdown,
                                 scoped to plugin/crew the same way every other
                                 check here is
    typed policy IDs            `guards.<name>` references resolve against
                                 `crew_guards.ALL_GUARD_NAMES`, the one place
                                 those names are actually declared

Run with no arguments from anywhere in the repo, or with `--base <ref>` to pin
the allowance-ceiling check's comparison point instead of the merge-base with
the default branch. Exit status is 0 when clean, 1 when anything is wrong.
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
# A ceiling MAY be raised past what the merge-base version of the allowance
# file recorded, but only by changing the reason to this explicit form in the
# same edit -- see check_allowance_no_silent_raise. It is deliberately not
# one more member of ALLOWED_REASONS: that tuple is a closed set of reasons a
# file is HELD at a size, and "raised: <why>" is a different kind of claim,
# about why the ceiling itself moved.
RAISED_REASON_RE = re.compile(r"^raised: .+")


def _reason_allowed(reason: object) -> bool:
    return isinstance(reason, str) and (
        reason in ALLOWED_REASONS or bool(RAISED_REASON_RE.match(reason))
    )


# Names that pre-date the crew 1.0 rebuild (`docs/review/04-redesign.md`) and
# should not appear in a file the rebuild itself introduced.
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

# check_stale_names scans every plugin/crew Markdown file (and AGENTS.md) by
# DEFAULT. This is the inverse of the list it used to run against: that list
# named which NEW files to check, so a new 1.0 file nobody remembered to add
# to it was never scanned at all -- omission failed open. This list instead
# names the pre-1.0 and held files that are ALLOWED to mention a name crew 1.0
# retires (an old command's own name, e.g. `commands/scale.md` saying
# `/crew:scale`, or a file that legitimately cross-references a still-active
# pre-1.0 command); omitting a file from THIS list means it gets checked, not
# the opposite. Maintained the same way the old list was -- add a file here in
# the same commit that gives it a real reason to mention a stale name.
LEGACY_STALE_NAME_FILES = (
    "plugin/crew/CONFIG.md",
    "plugin/crew/README.md",
    "plugin/crew/agents/analyst.md",
    "plugin/crew/agents/angular-architect.md",
    "plugin/crew/agents/code-reviewer.md",
    "plugin/crew/agents/dba.md",
    "plugin/crew/agents/developer.md",
    "plugin/crew/agents/docs-writer.md",
    "plugin/crew/agents/dotnet-core-expert.md",
    "plugin/crew/agents/exchange-online-specialist.md",
    "plugin/crew/agents/node-developer.md",
    "plugin/crew/agents/php-pro.md",
    "plugin/crew/agents/pm.md",
    "plugin/crew/agents/power-automate-specialist.md",
    "plugin/crew/agents/powershell-5.1-expert.md",
    "plugin/crew/agents/powershell-7-expert.md",
    "plugin/crew/agents/python-pro.md",
    "plugin/crew/agents/qa-researcher.md",
    "plugin/crew/agents/qa-reviewer.md",
    "plugin/crew/agents/react-specialist.md",
    "plugin/crew/agents/rust-engineer.md",
    "plugin/crew/agents/sharepoint-developer.md",
    "plugin/crew/agents/skill-author.md",
    "plugin/crew/agents/sql-pro.md",
    "plugin/crew/agents/terraform-engineer.md",
    "plugin/crew/agents/windows-infra-admin.md",
    "plugin/crew/commands/change.md",
    "plugin/crew/commands/debug.md",
    "plugin/crew/commands/emergency.md",
    "plugin/crew/commands/jira-sync.md",
    "plugin/crew/commands/model.md",
    "plugin/crew/commands/obsidian-sync.md",
    "plugin/crew/commands/pm.md",
    "plugin/crew/commands/roster.md",
    "plugin/crew/commands/scale.md",
    "plugin/crew/commands/sdp-sync.md",
    "plugin/crew/commands/split.md",
    "plugin/crew/commands/survey.md",
    "plugin/crew/commands/ticket.md",
    "plugin/crew/commands/upgrade.md",
    "plugin/crew/commands/verify.md",
    "plugin/crew/commands/work.md",
    "plugin/crew/evals/qa-reviewer-stays-read-only/prompt.md",
    "plugin/crew/skills/crew-best-practices/SKILL.md",
    "plugin/crew/skills/crew-change/SKILL.md",
    "plugin/crew/skills/crew-context/SKILL.md",
    "plugin/crew/skills/crew-docs/SKILL.md",
    "plugin/crew/skills/crew-pm/SKILL.md",
    "plugin/crew/skills/crew-pm/offboarding.md",
    "plugin/crew/skills/crew-pm/onboarding.md",
    "plugin/crew/skills/crew-providers/SKILL.md",
    "plugin/crew/skills/crew-scaling/SKILL.md",
    "plugin/crew/skills/crew-setup/SKILL.md",
    "plugin/crew/skills/crew-setup/global-config.md",
    "plugin/crew/skills/crew-setup/phases.md",
    "plugin/crew/skills/crew-setup/trackers.md",
)

PLUGIN_PATH_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_\-./]+)")

# Inline Markdown link destination: `[text](dest)`, `[text](<dest>)`, either
# optionally followed by a title (`"..."`, '...' or (...)). CommonMark allows
# a bare destination to contain one level of balanced parentheses and no
# unescaped whitespace; the angle-bracket form drops both restrictions by
# wrapping the destination instead. This is "CommonMark-ish", not a full
# parser -- it does not handle backslash escapes -- but it is enough for the
# relative paths and ${...} placeholders this repo actually writes, and it no
# longer stops at the first `)` a query string or a balanced-paren path
# happens to contain.
INLINE_LINK_RE = re.compile(
    r"\[[^\]]*\]\("
    r"\s*(?:<([^<>\n]*)>|((?:[^\s()]|\([^\s()]*\))*))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?"
    r"\s*\)"
)

# Reference-style links: `[text][label]` and the collapsed `[text][]` (label
# defaults to text), resolved against `[label]: dest` definitions -- which
# CommonMark scopes to the whole document, not the paragraph, so definitions
# are collected once per file. The bare shortcut form (`[label]` with no
# second bracket pair) is deliberately not matched: it is indistinguishable
# from a plain bracketed word in this repo's prose without a full CommonMark
# parse, and a checker that cannot tell the two apart would fail correct
# lines -- the same reason `check_self_claims` in check-marketplace.py stays
# marker-keyed instead of guessing from shape.
REFERENCE_USE_RE = re.compile(r"\[([^\]]*)\]\[([^\]]*)\]")
REFERENCE_DEF_RE = re.compile(
    r"^[ ]{0,3}\[([^\]]+)\]:\s*(?:<([^<>\n]*)>|(\S+))", re.MULTILINE
)

# The token after `guards.` must be matched in full, underscore included --
# `[A-Za-z0-9]*` alone stops consuming at the first `_`, so `guards.cloudGuard_x`
# was read as the real name `cloudGuard` plus leftover text the regex simply
# never looked at, and a bogus identifier passed by accident. `_` is already a
# `\w` character, so the trailing `\b` still ends the match at a genuine word
# boundary once it is in the class.
GUARD_REF_RE = re.compile(r"\bguards\.([A-Za-z][A-Za-z0-9_]*)(\*)?")
FRONTMATTER_START_RE = re.compile(r"\A---\s*\n")
FRONTMATTER_CLOSE_RE = re.compile(r"\n---\s*(?:\n|$)")


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
            or not _reason_allowed(entry.get("reason"))
        ):
            fail(
                f"{rel(ALLOWANCE_PATH)}: entry '{path}' must be "
                '{"lines": <int>, "reason": one of ' + repr(ALLOWED_REASONS) +
                ' or "raised: <why>"}'
            )
            continue
        out[path] = entry
    return out


def check_command_budget(allowance: dict, fail) -> None:
    """Every plugin/crew/commands/**/*.md (recursed -- Claude Code loads a
    namespaced command in a subdirectory, `commands/group/x.md`, the same as
    a top-level one, so a budget that only globbed the top level let a nested
    command evade it entirely) is <= COMMAND_MAX_LINES, unless
    `.budget-allowance.json` lists it. Growth past a listed ceiling is
    check_allowance_growth's job, not this function's -- an allowance entry
    is not restricted to a command file, so that check has to walk every
    entry, not just the ones this glob finds.
    """
    for path in sorted(glob.glob(os.path.join(CREW, "commands", "**", "*.md"), recursive=True)):
        path_rel = rel(path)
        if path_rel in allowance:
            continue
        lines = len(read(path).splitlines())
        if lines > COMMAND_MAX_LINES:
            fail(
                f"{path_rel}: {lines} lines, budget {COMMAND_MAX_LINES} "
                "and not listed in .budget-allowance.json"
            )


def check_allowance_growth(allowance: dict, fail) -> None:
    """No file `.budget-allowance.json` lists -- command, agent or skill
    alike -- may grow past the line count the allowance recorded, so the file
    is debt that cannot be repaid by editing the allowance instead of it.

    This used to live inside check_command_budget and only ever walked
    `commands/*.md`, so an allowance entry naming an agent or a skill file
    could grow without limit and nothing here would notice. Walking the
    allowance's own keys instead of a directory glob is what closes that --
    every listed path is checked, whatever kind of file it names.
    """
    for path_rel, entry in sorted(allowance.items()):
        path = os.path.join(ROOT, path_rel)
        if not os.path.isfile(path):
            continue  # check_allowance_paths_exist already reports this
        lines = len(read(path).splitlines())
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


def _resolve_default_branch() -> str | None:
    """Best-effort name for this repo's default branch, tried in the order
    most to least likely to exist in a real checkout. None means neither
    resolved -- a shallow clone or a detached HEAD with no matching ref is
    exactly the "git could not answer" case, not a reason to skip quietly."""
    for candidate in ("origin/main", "main"):
        done = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "--verify", "--quiet", candidate],
            capture_output=True, text=True, check=False,
        )
        if done.returncode == 0:
            return candidate
    return None


def _allowance_at(ref: str) -> dict | None:
    """`.budget-allowance.json` as committed at `ref`. None means git could
    not answer at all (no binary, not a repository, unreadable JSON); {} means
    git answered and the file did not exist at that commit yet, which is a
    real, checkable "no prior ceilings" rather than a failure to read one."""
    allowance_rel = os.path.relpath(ALLOWANCE_PATH, ROOT)
    done = subprocess.run(
        ["git", "-C", ROOT, "show", f"{ref}:{allowance_rel}"],
        capture_output=True, text=True, check=False,
    )
    if done.returncode != 0:
        stderr = done.stderr.lower()
        if "exists on disk, but not in" in stderr or "does not exist" in stderr:
            return {}
        return None
    try:
        data = json.loads(done.stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def check_allowance_no_silent_raise(allowance: dict, fail, base: str | None = None) -> None:
    """A listed ceiling can be raised in the very same change that grows the
    file it constrains, which defeats the whole point of check_allowance_growth
    -- the allowance is a promise not to grow, and nothing stops editing the
    promise alongside the file.

    Compares every ceiling here against `.budget-allowance.json` as committed
    at `base` (or, when `base` is None, the merge-base with this repo's
    default branch). A raised ceiling is only allowed when its `reason` is
    changed to the explicit "raised: <why>" form -- load_allowance already
    requires that shape via `_reason_allowed` -- and even then it is printed,
    because a raise that passes silently is the exact failure mode this
    exists to catch.

    If git cannot answer -- no binary, not a repository, no default branch
    resolves, or the base copy of the allowance file will not parse -- this
    is UNVERIFIED and reported as a failure. Passing clean because the
    comparison could not run is the same "unknown collapsing into the
    safe-looking value" bug this repo has shipped before; it fails loudly
    instead of quietly agreeing that nothing was raised.
    """
    ref = base
    if ref is None:
        default_branch = _resolve_default_branch()
        if default_branch is None:
            fail(
                "UNVERIFIED: could not resolve a default branch (tried "
                "origin/main, main) to check .budget-allowance.json ceilings "
                "against - pass --base explicitly for a shallow or "
                "detached-HEAD checkout"
            )
            return
        done = subprocess.run(
            ["git", "-C", ROOT, "merge-base", "HEAD", default_branch],
            capture_output=True, text=True, check=False,
        )
        if done.returncode != 0 or not done.stdout.strip():
            fail(
                f"UNVERIFIED: could not compute a merge-base with "
                f"{default_branch} to check .budget-allowance.json ceilings "
                "against"
            )
            return
        ref = done.stdout.strip()

    base_allowance = _allowance_at(ref)
    if base_allowance is None:
        fail(
            f"UNVERIFIED: could not read .budget-allowance.json at {ref} - "
            "git show failed, so a raised ceiling cannot be checked"
        )
        return

    for path_rel, entry in sorted(allowance.items()):
        base_entry = base_allowance.get(path_rel)
        if not isinstance(base_entry, dict) or not isinstance(base_entry.get("lines"), int):
            continue  # new entry at HEAD, not a raise of an existing ceiling
        if entry["lines"] <= base_entry["lines"]:
            continue
        if RAISED_REASON_RE.match(entry["reason"]):
            print(
                f"{rel(ALLOWANCE_PATH)}: {path_rel} ceiling raised "
                f"{base_entry['lines']} -> {entry['lines']} ({entry['reason']})"
            )
            continue
        fail(
            f"{rel(ALLOWANCE_PATH)}: {path_rel} ceiling raised "
            f"{base_entry['lines']} -> {entry['lines']} in this change "
            f"(from {ref}) without an explicit 'raised: <why>' reason - "
            "defeats the no-growth invariant"
        )


def _has_frontmatter(path: str) -> bool:
    """A `---`-delimited block: an opening `---` line and, somewhere after
    it, a closing line that is EXACTLY `---` (optional trailing whitespace).
    `"\\n---" in text[3:]` used to accept this on a substring match alone, so
    a line like `----` or `--- foo` -- either one a real edit could produce
    and neither a valid closing fence -- read as present when it was not."""
    text = read(path)
    if not FRONTMATTER_START_RE.match(text):
        return False
    return bool(FRONTMATTER_CLOSE_RE.search(text, 3))


def check_frontmatter(fail) -> None:
    """A cheap presence check (frontmatter block exists), not a replacement
    for validate-prompts.py's full YAML parse and tool-name validation.
    Commands are globbed recursively -- see check_command_budget's docstring
    for why a nested command file is a real command and not exempt."""
    for path in sorted(glob.glob(os.path.join(CREW, "commands", "**", "*.md"), recursive=True)):
        if not _has_frontmatter(path):
            fail(f"{rel(path)}: no frontmatter block")
    for path in sorted(glob.glob(os.path.join(CREW, "agents", "*.md"))):
        if not _has_frontmatter(path):
            fail(f"{rel(path)}: no frontmatter block")
    for path in sorted(glob.glob(os.path.join(CREW, "skills", "*", "SKILL.md"))):
        if not _has_frontmatter(path):
            fail(f"{rel(path)}: no frontmatter block")


def _codex_hooks_looks_generated(text: str) -> bool:
    """Whether a `.codex/hooks.json` is crew_instructions.py's own output --
    imported from that module's own `_codex_hooks_generated`, rather than
    re-implemented here a second time to drift out of sync with it. JSON
    cannot carry the `crew:generated` comment marker every OTHER generated
    file uses, so treating "the file merely exists" as "the file is ours"
    (as this used to) meant a hand-written `.codex/hooks.json` at that path
    would be reported as drifting -- or silently overwritten by --force --
    instead of being left alone the way a hand-written AGENTS.md already is.
    Returns False (not generated) if the module cannot be imported; that
    leaves nothing to compare for codex, the same outcome as today when the
    module genuinely is not on disk yet."""
    scripts_dir = os.path.join(CREW, "hooks", "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import crew_instructions  # pylint: disable=import-outside-toplevel,import-error
    except ImportError:
        return False
    return crew_instructions._codex_hooks_generated(text)  # pylint: disable=protected-access


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
    if os.path.isfile(codex_hooks) and _codex_hooks_looks_generated(read(codex_hooks)):
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


def _stale_name_scan_paths() -> list[str]:
    """Every plugin/crew Markdown file, recursively, plus AGENTS.md -- the
    default is now "scanned", not "skipped". `LEGACY_STALE_NAME_FILES` is the
    explicit opt-OUT list; a brand-new 1.0 file nobody remembers to add
    anywhere is checked automatically instead of passing by omission."""
    paths = glob.glob(os.path.join(CREW, "**", "*.md"), recursive=True)
    agents_md = os.path.join(ROOT, "AGENTS.md")
    if os.path.isfile(agents_md):
        paths.append(agents_md)
    return sorted(paths)


def check_stale_names(fail) -> None:
    """A stale name in a crew 1.0 file is usually a leftover, but sometimes a
    deliberate cross-reference to the thing it replaces (`04a-redesign-fable.md`'s
    own contradiction-check design uses exactly this escape hatch, `<!--
    deliberate -->`, for the same reason: a rename note that says what it
    replaces is not the regression this check exists to catch). A line
    carrying the marker is skipped; everything else is a live finding.

    Scanned by default; `LEGACY_STALE_NAME_FILES` names the pre-1.0/held
    files that are allowed to mention a name crew 1.0 retires (most often
    because it IS one -- `commands/scale.md` legitimately says `/crew:scale`).
    """
    for path in _stale_name_scan_paths():
        path_rel = rel(path)
        if path_rel in LEGACY_STALE_NAME_FILES:
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


def _local_link_target(raw: str) -> str | None:
    """Strip a trailing #fragment and ?query, then None for anything that is
    not this checker's business: empty, a `${...}` placeholder (handled
    separately, above), or an absolute URL."""
    target = raw.strip()
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target or target.startswith("${"):
        return None
    return target


def check_broken_references(fail) -> None:
    for path in sorted(glob.glob(os.path.join(CREW, "**", "*.md"), recursive=True)):
        path_rel = rel(path)
        text = read(path)
        for match in PLUGIN_PATH_RE.finditer(text):
            target = match.group(1).rstrip(".,`)")
            if not os.path.exists(os.path.join(CREW, target)):
                fail(f"{path_rel}: names missing ${{CLAUDE_PLUGIN_ROOT}}/{target}")

        def _check(raw: str, describe: str, path=path, path_rel=path_rel) -> None:
            target = _local_link_target(raw)
            if target is None:
                return
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                fail(f"{path_rel}: {describe} does not resolve: {target}")

        for match in INLINE_LINK_RE.finditer(text):
            raw = match.group(1) if match.group(1) is not None else match.group(2)
            _check(raw, "relative link target")

        # Reference-style definitions are document-scoped in CommonMark, not
        # paragraph-scoped, so they are collected once per file rather than
        # inline with the usage that resolves against them.
        definitions = {}
        for match in REFERENCE_DEF_RE.finditer(text):
            label = match.group(1).strip().lower()
            dest = match.group(2) if match.group(2) is not None else match.group(3)
            definitions[label] = dest
        for match in REFERENCE_USE_RE.finditer(text):
            label = (match.group(2) or match.group(1)).strip().lower()
            dest = definitions.get(label)
            if dest is None:
                continue  # not every [x][y] is a link use - could be prose
            _check(dest, f"reference link [{label}]")


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
    args = sys.argv[1:]
    base = None
    if args:
        if len(args) == 2 and args[0] == "--base":
            base = args[1]
        else:
            print(f"usage: {sys.argv[0]} [--base <ref>]", file=sys.stderr)
            return 2

    problems: list[str] = []

    def fail(message: str) -> None:
        problems.append(message)

    allowance = load_allowance(fail)
    check_command_budget(allowance, fail)
    check_allowance_growth(allowance, fail)
    check_allowance_no_silent_raise(allowance, fail, base)
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

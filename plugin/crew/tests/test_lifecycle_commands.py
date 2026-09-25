"""Structural and sabotage tests for crew 1.0's lifecycle commands and the
three vendored skills backing them (T4).

    python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py -q

Two kinds of check. The structural ones are what
`_test/validate-prompts.py` already covers for every command and skill --
frontmatter parses, ≤120 lines -- re-asserted here scoped to the new files so
this suite is a complete regression signal for T4 on its own. The sabotage
ones prove the text-presence checks are not vacuous: each mutates a
scratch COPY of the real file (never the tracked one), confirms the check
goes red on the mutation, and diffs the scratch against the tracked file to
prove the tracked file itself was never touched.
"""
import os
import re
import shutil
import tempfile

import pytest
import yaml

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMANDS = os.path.join(CREW, "commands")
SKILLS = os.path.join(CREW, "skills")
MAX_LINES = 120

NEW_COMMANDS = ("brainstorm.md", "spec.md", "plan.md", "implement.md",
                "done.md", "fix.md", "approve.md", "autopilot.md")
NEW_SKILLS = ("crew-brainstorm", "crew-plan", "crew-execute")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _frontmatter(text, path):
    assert text.startswith("---\n"), f"{path}: no frontmatter"
    end = text.index("\n---", 4)
    return yaml.safe_load(text[4:end])


def _line_count(text):
    # Trailing newline is not a 121st line; a file ending without one still
    # counts its last line. Matches how `wc -l` and this repo's other budget
    # checks (validate-prompts.py) read a file.
    return len(text.splitlines())


@pytest.mark.parametrize("name", NEW_COMMANDS)
def test_command_frontmatter_and_budget(name):
    path = os.path.join(COMMANDS, name)
    text = _read(path)
    fm = _frontmatter(text, path)
    assert isinstance(fm, dict), f"{name}: frontmatter did not parse to a mapping"
    assert fm.get("description"), f"{name}: no description"
    assert fm.get("allowed-tools"), f"{name}: no allowed-tools"
    lines = _line_count(text)
    assert lines <= MAX_LINES, f"{name}: {lines} lines, budget {MAX_LINES}"


@pytest.mark.parametrize("name", NEW_SKILLS)
def test_skill_frontmatter_and_budget(name):
    path = os.path.join(SKILLS, name, "SKILL.md")
    text = _read(path)
    fm = _frontmatter(text, path)
    assert fm.get("name") == name, f"{path}: frontmatter name != directory name"
    assert fm.get("description"), f"{name}: no description"
    lines = _line_count(text)
    assert lines <= MAX_LINES, f"{name}: {lines} lines, budget {MAX_LINES}"


# Each command names the T3 contract scripts with the exact CLI the brief
# gives: `crew_ticket.py validate|status --ticket <id>`, approval as the
# user-typed `/crew:approve <id>` (never the CLI, since crew 0.20.25),
# `completion_audit.py --check --ticket <id>`, and the review receipt check
# that already exists in review.md (`--ticket "$TICKET" --check-receipt`).
EXPECTED_CLI = {
    "plan.md": ("`/crew:approve $1`",),
    "implement.md": ("crew_ticket.py validate --ticket $1",
                      "scope_base.py --root . --record $1"),
    "done.md": ('review_ledger.py --ticket "$1" --check-receipt',
                'completion_audit.py --check --ticket "$1"',
                'crew_metrics.py record --ticket "$1"'),
    "fix.md": ("`/crew:approve <id>`",),
    "approve.md": ("Never run `crew_ticket.py approve` yourself",),
    "autopilot.md": ("crew_autopilot.py settings --root .",
                     "crew_autopilot.py resume --root .",
                     "crew_autopilot.py next --root ."),
}


@pytest.mark.parametrize("name,snippets", EXPECTED_CLI.items())
def test_command_names_exact_cli(name, snippets):
    text = _read(os.path.join(COMMANDS, name))
    for snippet in snippets:
        assert snippet in text, f"{name}: missing exact CLI {snippet!r}"


IMPLEMENT_APPROVAL_TEXT = (
    "This command refuses to edit anything unless that call reports the plan\n"
    "approved."
)


def _implement_refuses_without_approval(text):
    return (IMPLEMENT_APPROVAL_TEXT in text
            and "crew_ticket.py validate --ticket $1" in text)


def test_implement_refuses_without_approval():
    text = _read(os.path.join(COMMANDS, "implement.md"))
    assert _implement_refuses_without_approval(text)


DONE_CHECKS = (
    'review_ledger.py --ticket "$1" --check-receipt',
    'crew_status.py --root .',
    'completion_audit.py --check --ticket "$1"',
)


def _done_has_all_checks(text):
    return all(check in text for check in DONE_CHECKS)


def test_done_requires_all_three_checks():
    text = _read(os.path.join(COMMANDS, "done.md"))
    assert _done_has_all_checks(text)


FIX_PHASES = ("## 1. Direction", "## 2. Spec", "## 3. Plan",
              "## 4. Implement, tests, docs", "## 5. Review", "## 6. Done")


def test_fix_has_every_lifecycle_phase():
    text = _read(os.path.join(COMMANDS, "fix.md"))
    for phase in FIX_PHASES:
        assert phase in text, f"fix.md: missing phase heading {phase!r}"


_PLAN_HEADER_STATUS = re.compile(r"plan\.md`?(?:'s)? header")


def test_plan_never_adds_status_to_plan_md():
    """T-0026: the approval digest normalises an existing status VALUE, never a
    token added where there was none, so a writer adding `status:` to plan.md
    after approval would stale the approval it just got."""
    flat = " ".join(_read(os.path.join(COMMANDS, "plan.md")).split())

    assert (_PLAN_HEADER_STATUS.search(flat) is None
            and "`spec.md`'s header to `status: planned`" in flat)


@pytest.mark.parametrize("name", ["implement.md", "done.md"])
def test_status_edits_say_they_keep_the_approval(name):
    flat = " ".join(_read(os.path.join(COMMANDS, name)).split())

    assert "keeps the approval" in flat


def _sabotage(path, target, checker, expected_before=True):
    """Copy `path` to a scratch file, remove `target` from the copy, and
    confirm `checker` flips from `expected_before` to its opposite. A text
    comparison against the tracked file proves the mutation landed only in
    the scratch copy and the tracked file was never touched.

    `shutil.copyfile`, not a spawned `cp`/`diff` -- neither exists on native
    Windows without Git Bash's `usr/bin` on PATH, and a bare `subprocess.run`
    on either raised `FileNotFoundError: [WinError 2]` there (Windows burn-in
    family D, `docs/review/06-windows-burn-in.md`@84f32325)."""
    with tempfile.TemporaryDirectory() as tmp:
        scratch = os.path.join(tmp, os.path.basename(path))
        shutil.copyfile(path, scratch)
        before_text = _read(scratch)
        assert target in before_text, f"sabotage target not found in {path}"
        assert checker(before_text) is expected_before
        after_text = before_text.replace(target, "", 1)
        assert after_text != before_text
        with open(scratch, "w", encoding="utf-8") as fh:
            fh.write(after_text)
        assert checker(after_text) is not expected_before, (
            f"{path}: check did not go red after removing {target!r} - "
            "the assertion is not exercising this text"
        )
        assert _read(path) != _read(scratch), (
            "sabotage produced no diff against the tracked file")
        tracked_now = _read(path)
        assert tracked_now == before_text, "tracked file was mutated by this test"


def test_sabotage_drop_the_approval_check_from_implement_goes_red():
    path = os.path.join(COMMANDS, "implement.md")
    _sabotage(path, IMPLEMENT_APPROVAL_TEXT, _implement_refuses_without_approval)


@pytest.mark.parametrize("missing", DONE_CHECKS)
def test_sabotage_drop_one_done_check_goes_red(missing):
    path = os.path.join(COMMANDS, "done.md")
    _sabotage(path, missing, _done_has_all_checks)

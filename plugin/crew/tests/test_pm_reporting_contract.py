"""The PM must report mid-pass and answer a status request, not just at the end.

Diagnosed by an analyst session on 2026-09-19: the standing `crew-pm` agent ran
roughly three hours, then (a) wrote four version bumps of code itself instead
of dispatching a developer, and (b) after being resumed and dispatching
correctly, sent no report to the main session across five explicit status
requests over roughly fifty minutes.

Before this change, `pm.md`'s `## Reporting` section
(`plugin/crew/agents/pm.md`), `pm_pulse.py`'s directives, and `commands/pm.md`'s
`assign` section all said "report what you did when finished" and nothing
else. No file told the PM to report after each dispatched role returns, and no
file said what to do when an interim status request arrives mid-pass. That gap
is what this test guards.

Like `test_scope_discipline.py`, these assertions are PROMPT TEXT, not
executable behaviour — a subagent prompt cannot be run, so the only mechanical
regression this suite can catch is the instruction going missing again. Text
is matched on whitespace-normalised substrings so a rewrap does not break the
test; the substrings are specific sentences, not keywords, so a rewrite that
keeps a word but drops the instruction is still caught.

Sabotage-tested by hand against `dedd1150` (git worktree
`C:/repos/personal/crew-wt-pmcontract`, branch `crew-pm-reporting-contract`):
each assertion below was tripped by deleting the phrase it checks, confirmed
RED, then restored with `git checkout --` and reverified byte-identical by
sha256. See the commit message on this change for the table of shas.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]


def _norm(text):
    """Collapse whitespace so an assertion survives hand-wrapped prose being
    rewrapped. See test_scope_discipline.py's _norm for the same rationale:
    sensitive to a sentence being REMOVED, blind to where its line breaks
    fall."""
    return re.sub(r"\s+", " ", text)


def _pm_agent():
    return _norm((PLUGIN / "agents" / "pm.md").read_text(encoding="utf-8"))


def _pm_agent_raw():
    return (PLUGIN / "agents" / "pm.md").read_text(encoding="utf-8")


def _skill():
    return _norm(
        (PLUGIN / "skills" / "crew-pm" / "SKILL.md").read_text(encoding="utf-8")
    )


def _commands_pm():
    return _norm((PLUGIN / "commands" / "pm.md").read_text(encoding="utf-8"))


# --- agents/pm.md ------------------------------------------------------


def test_pm_has_a_reporting_cadence():
    body = _pm_agent()
    assert (
        "Report after every dispatched role returns, before your next dispatch"
        in body
    ), "pm.md no longer tells the PM to report mid-pass, not only at the end"
    assert "under 1,500 characters" in body, (
        "pm.md lost the size bound on the mid-pass report, which is what "
        "keeps it a paragraph rather than a second full report"
    )


def test_pm_has_an_interrupt_rule():
    body = _pm_agent()
    assert (
        "A status request from the session that spawned you outranks the pass"
        in body
    ), "pm.md no longer says an interim status request outranks the dispatch pass"
    assert "Silence is never the right answer to a status request" in body, (
        "pm.md lost the line ruling out silence as a response to a status "
        "request — this is the exact defect the analyst diagnosed"
    )


def test_pm_one_hat_rule_names_paths():
    body = _pm_agent()
    assert (
        "you do not create or edit files under `plugin/`, `skills/`, `src/`, "
        "`scripts/`, or `tests/` — those are a" in body
    ), "pm.md's one-hat rule no longer names checkable paths, only categories"
    assert (
        "Your own writes are `.crew/**`, `TODO.md`, ticket text under "
        "`.work/`, and `docs/diagrams/**`." in body
    ), "pm.md dropped the explicit list of what the PM itself may write"
    assert "When a path is on neither list, it is a developer's — dispatch." in body, (
        "pm.md no longer resolves a path that is on neither the forbidden "
        "nor the permitted list — Codex found the earlier wording forbade "
        "and permitted TODO.md and .crew/** at once by routing both lists "
        "through .crew/verify.json, which maps exactly those paths"
    )


def test_pm_still_holds_write_and_edit():
    """The one-hat fix must not be done by stripping the tools the PM needs
    for its own carved-out writes (.crew/ bookkeeping, TODO.md, ticket text,
    diagrams) — that is the wrong fix the team lead's brief explicitly warned
    against."""
    lines = [l for l in _pm_agent_raw().splitlines() if l.startswith("tools:")]
    assert lines, "pm.md frontmatter no longer declares a tools: line"
    line = lines[0]
    assert "Write" in line, "pm.md lost Write, which its own carved-out writes need"
    assert "Edit" in line, "pm.md lost Edit, which its own carved-out writes need"


# --- skills/crew-pm/SKILL.md --------------------------------------------


def test_skill_one_hat_names_paths():
    body = _skill()
    assert (
        "it does not create or edit files under `plugin/`, `skills/`, `src/`, "
        "`scripts/`, or `tests/` — those are a developer's" in body
    ), "SKILL.md's one-hat section no longer agrees with pm.md's path list"
    assert "A path on neither list is a developer's — dispatch." in body, (
        "SKILL.md no longer resolves a path that is on neither list, so it "
        "has fallen out of agreement with pm.md's fixed wording again"
    )


def test_skill_states_the_reporting_cadence_and_interrupt_rule():
    body = _skill()
    assert (
        "the PM reports after every dispatched role returns, not only at "
        "the end of the pass" in body
    ), "SKILL.md's narration-failure section no longer states the reporting cadence"
    assert (
        "a status request from the session that spawned it outranks the pass"
        in body
    ), "SKILL.md no longer states the interrupt rule"


# --- commands/pm.md -------------------------------------------------------


def test_commands_pm_assign_states_the_cadence_and_interrupt_rule():
    body = _commands_pm()
    assert (
        "The PM reports after each returned dispatch, not only at the end"
        in body
    ), "commands/pm.md's assign section no longer states the reporting cadence"
    assert (
        "if a status request goes unanswered for one full dispatch cycle, "
        "say so to the user rather than waiting" in body
    ), "commands/pm.md no longer tells the caller to flag an unanswered status request"

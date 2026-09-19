"""The roles that touch code must carry a scope rule, and report what they left.

Crew advertises this discipline about itself -- `plugin/README.md` and the root
`README.md` both describe the crew as "bounded so it fixes only what blocks the
job and tickets the rest" -- and before crew 0.19.62 it existed in exactly one
place: the PM. `pm_pulse.py:188-189` and `:215-217` put it in the hook text at
every authority tier. Measured across the roles that actually edit and review
code, `grep -ci 'defer|out of scope|unrelated'` returned 0 for developer.md,
qa-reviewer.md, smoke-author.md, dba.md and work.md; smoke-author.md had no
scope language of any kind. The instruction existed only where it was already
being followed.

Like test_codemap_read_path.py, these assert PROMPT TEXT. A subagent prompt is
not executable and there is nothing to run; the only mechanical regression is
the instruction going missing, which is the state the feature was in for its
whole life before this. The assertions name specific strings rather than
keywords so that a rewrite which drops the load-bearing half is caught too.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]

DOING_ROLES = ("developer", "dba", "qa-reviewer", "smoke-author")


def _norm(text):
    """Collapse runs of whitespace so an assertion survives a rewrap.

    These files are hand-wrapped prose. A phrase that sits on one line today
    can straddle two after any edit, and a test that fails on that is a test
    people learn to "fix" by deleting the assertion. Collapsing whitespace
    keeps the test sensitive to the sentence being REMOVED -- which is the
    regression -- while blind to where the line breaks fall.
    """
    return re.sub(r"\s+", " ", text)


def _agent(name):
    return _norm((PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8"))


def _work():
    return _norm((PLUGIN / "commands" / "work.md").read_text(encoding="utf-8"))


def test_every_doing_role_carries_the_scope_clause():
    for name in DOING_ROLES:
        body = _agent(name)
        assert "Fix only what blocks the task you were given" in body, (
            f"{name}.md dropped the scope clause. Without it the role has no "
            "rule against fixing whatever it notices, which is the veering "
            "0.19.62 exists to stop"
        )
        assert "TODO.md" in body, (
            f"{name}.md names no destination for a deferred finding. A rule "
            "to not fix something, with nowhere to put it, loses the finding"
        )


def test_every_doing_role_requires_a_deferred_section_even_when_empty():
    """The empty case is the one that matters. A missing section reads the same
    whether the role found nothing or found something and quietly fixed it."""
    for name in DOING_ROLES:
        body = _agent(name)
        assert "## Deferred — and where it went" in body, (
            f"{name}.md dropped the Deferred report heading"
        )
        assert "present even when empty" in body, (
            f"{name}.md no longer requires the Deferred section when there is "
            "nothing to defer, so an absent section becomes ambiguous again"
        )
        assert "Nothing deferred." in body, (
            f"{name}.md dropped the explicit empty-case wording, which is what "
            "makes 'found nothing' distinguishable from 'said nothing'"
        )


def test_work_command_holds_roles_to_the_clause():
    body = _work()
    assert "## Deferred — and where it went" in body, (
        "work.md must state the Deferred section it expects back, or nothing "
        "notices when a role omits it"
    )


def test_work_command_emits_a_goal_line():
    body = _work()
    assert "/goal" in body, "work.md no longer emits the goal line"
    assert "proven by" in body, (
        "the goal line lost its stated-check clause, so the condition names an "
        "end state with no way for the turn to demonstrate it"
    )
    assert "is modified" in body, (
        "the goal line lost its scope-constraint clause, which is the half "
        "that does the focus work"
    )


def test_goal_line_ships_with_the_evidence_that_makes_it_checkable():
    """The evaluator runs no commands and reads no files. A constraint whose
    evidence is never printed passes because nothing contradicted it -- not
    because it held. That is this repo's named recurring defect, and it is the
    reason the porcelain print is part of the feature rather than a nicety."""
    body = _work()
    assert "git status --porcelain" in body, (
        "work.md dropped the porcelain print, so the goal's scope constraint "
        "is unverifiable and the evaluator will return Met vacuously"
    )
    assert "including when it is empty" in body, (
        "work.md no longer requires printing an empty porcelain result, so a "
        "silent turn and a clean turn are indistinguishable again"
    )
    assert "runs no commands and opens no files" in body, (
        "work.md lost the explanation of WHY the print is required. A "
        "mechanism with no stated reason is the first thing a later edit drops"
    )


def test_goal_line_names_the_specific_test_not_only_the_mapped_command():
    body = _work()
    assert "coarse globs" in body, (
        "work.md no longer warns that verify.json rules are coarse, so the "
        "emitted goal will cite only the top-level checker -- true of every "
        "change, and therefore discriminating for none"
    )

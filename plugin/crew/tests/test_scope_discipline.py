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


def _agent_raw(name):
    """Unnormalised. Frontmatter is line-structured, and _norm collapses it to
    a single line, so `tools:` can never be found through the normalised
    reader -- the first version of the grant test raised IndexError rather
    than failing an assertion, which is a broken test, not a caught defect."""
    return (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")


def _work():
    return _norm((PLUGIN / "commands" / "work.md").read_text(encoding="utf-8"))


# Roles that hold Write/Edit. They file their own deferrals.
WRITER_ROLES = ("developer", "smoke-author")
# Roles granted Read, Grep, Glob, Bash, Skill and NOTHING that mutates.
READONLY_ROLES = ("dba", "qa-reviewer")


def test_the_split_matches_the_actual_tool_grants():
    """The lists above are a claim about frontmatter; check it, do not trust it.

    Codex found the original clause telling `dba` and `qa-reviewer` to append
    to TODO.md when neither has Write or Edit. The clause was right for the
    two roles it was written against and wrong for the two it was pasted into.
    If a grant changes later, this test fails before the prose goes stale."""
    for name in WRITER_ROLES:
        line = [l for l in _agent_raw(name).splitlines()
                if l.startswith("tools:")][0]
        assert "Write" in line and "Edit" in line, f"{name} lost its write tools"
    for name in READONLY_ROLES:
        line = [l for l in _agent_raw(name).splitlines()
                if l.startswith("tools:")][0]
        assert "Write" not in line and "Edit" not in line, (
            f"{name} gained write tools; its scope clause says it has none"
        )


def test_writer_roles_file_their_own_deferrals():
    for name in WRITER_ROLES:
        body = _agent(name)
        assert "Fix only what blocks the task you were given" in body
        assert "TODO.md" in body, f"{name} has no destination for a deferral"
        assert "## Deferred — and where it went" in body
        assert "present even when empty" in body
        assert "Nothing deferred." in body


def test_readonly_roles_are_not_told_to_write():
    """Asking a read-only role to append to TODO.md does not fail safely -- it
    gets done by shell redirection, because Bash is granted. That works, which
    is what makes it worse than an outright failure."""
    for name in READONLY_ROLES:
        body = _agent(name)
        assert "REPORT the rest" in body, (
            f"{name} carries the writer clause; it cannot write"
        )
        assert "do not write it anywhere" in body, (
            f"{name} no longer forbids writing the finding itself"
        )


def test_qa_reviewer_has_no_deferred_section():
    """Its contract is defect lines or exactly CLEAN (qa-reviewer.md). A
    mandatory prose heading makes every clean review violate one rule or the
    other -- there is no output that satisfies both."""
    body = _agent("qa-reviewer")
    assert "## Deferred" not in body, (
        "qa-reviewer regained a Deferred section, so a CLEAN review must now "
        "either break the output format or break the scope rule"
    )
    assert "NIT" in body, (
        "qa-reviewer must route an unrelated defect through the finding "
        "format at NIT severity, since it has nowhere else to put it"
    )


def test_work_command_enforces_per_role_not_uniformly():
    body = _work()
    assert "## Deferred — and where it went" in body
    assert "not the same one" in body, (
        "work.md enforces one clause across every role again. That is the "
        "defect Codex found: the rule was applied to roles whose tools and "
        "output contracts cannot satisfy it"
    )
    assert "never expect one from" in body, (
        "work.md no longer exempts qa-reviewer from the Deferred section"
    )


def test_goal_line_excludes_crew_bookkeeping():
    """TODO.md is tracked. Without the carve-out the goal forbids the very
    write the same clause requires, so a correct deferral reads as a scope
    violation and the only compliant behaviour is to stop deferring."""
    body = _work()
    assert "except TODO.md and .crew/ and .work/" in body, (
        "the goal template no longer carves out crew bookkeeping, so "
        "deferring a finding now violates the goal it was emitted with"
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
    assert "git diff --name-only" in body, (
        "work.md dropped the changed-file print, so the goal's scope "
        "constraint is unverifiable and the evaluator returns Met vacuously"
    )
    assert "git ls-files --others --exclude-standard" in body, (
        "work.md prints tracked changes only, so a new untracked file lands "
        "outside the ticket's paths without ever appearing in the evidence"
    )
    assert "Not `git status --porcelain`" in body, (
        "work.md must say WHY porcelain is the wrong command here. Asserting "
        "only the right command lets a later edit swap it back for the "
        "familiar one, which is how this was wrong in 0.19.62"
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


def test_developer_may_not_commit():
    """Nothing forbade this before crew 0.19.63, and it defeats the evidence.

    A commit mid-ticket moves work out of the working tree, so the changed-file
    print the goal constraint relies on comes back short while the branch still
    carries the change. The turn then reports a clean scope truthfully and
    wrongly at the same time."""
    body = _agent("developer")
    assert "Never `git commit`" in body, (
        "developer.md no longer forbids committing mid-ticket, so the scope "
        "evidence can be emptied by an action nothing rules out"
    )

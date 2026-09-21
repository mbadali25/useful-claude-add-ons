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


# The commit rule, in ONE form wherever a developer is briefed. A paraphrase
# per file is how the role file and the briefs came to disagree (T-0003: two
# developers refused to commit, three committed, and the model decided which
# sentence won). Every file below must carry both halves verbatim.
COMMIT_RULE = "commit on the ticket's own branch and nowhere else"
COMMIT_RULE_LIMITS = "never a shared branch, never `git stash`"
BRIEFING_FILES = ("agents/developer.md", "commands/work.md", "agents/pm.md")


def _prose(rel):
    return _norm((PLUGIN / rel).read_text(encoding="utf-8"))


def test_developer_commits_only_on_the_tickets_own_branch():
    """Narrowed in crew 0.19.95, not deleted. Before that, `developer.md`
    forbade committing at all, because the scope evidence diffed from the
    gate's verified marker and a verified commit left it after one turn. The
    evidence now diffs from the ticket's own start (scope_base.py), so the
    ban keeps only the part that still holds."""
    body = _agent("developer")
    assert COMMIT_RULE in body, (
        "developer.md no longer states the narrowed rule; a developer reading "
        "it cannot tell whether committing on its own branch is allowed"
    )
    assert COMMIT_RULE_LIMITS in body, (
        "developer.md lost the limits: a shared branch and a stash are the "
        "two moves that still hide work from the people who read the tree"
    )
    assert "**Never `git commit`" not in body, (
        "the blanket ban is back on developer.md while every brief in this "
        "repository tells the developer to commit on its branch -- the "
        "contradiction T-0003 closed"
    )
    # The reason the ban was ever blanket must stay visible, or the next
    # reader re-widens it for the same reason the first writer had.
    assert ".verify-verified-at" in body and "scope_base.py" in body, (
        "developer.md no longer explains why the ban was blanket and what "
        "replaced it, so the narrowing reads as an accident"
    )


# The whole rule is ONE sentence, and it is extracted rather than matched:
# `The developer <verb> commit...` up to the full stop. Matching on the verb
# would let a file that says "never commit" slip past a test looking for
# "commit on the ticket's own branch" (Codex, round 1: a one-word reversal in
# pm.md left the agreement test green). Extracting the sentence whatever the
# verb, then comparing the three extracts to each other AND to the meaning,
# is what makes one changed word in one file fail.
_RULE_SENTENCE = re.compile(r"The developer \S+ commits? on [^.]*\.")


def _rule_sentences(rel):
    return _RULE_SENTENCE.findall(_prose(rel))


def test_every_file_that_briefs_a_developer_states_the_same_commit_rule():
    """The role file and the templates must not contradict each other. The
    full sentence, identical in every file, so a rewrite of one that drifts
    from the others by a word fails here before a dispatched developer has
    to pick a side."""
    found = {rel: _rule_sentences(rel) for rel in BRIEFING_FILES}
    for rel, sentences in found.items():
        assert sentences, f"{rel} carries no 'The developer ... commit' sentence"
    distinct = {s for sentences in found.values() for s in sentences}
    assert len(distinct) == 1, (
        "the commit rule is stated differently across the briefing files: "
        + " | ".join(f"{rel}: {sentences}" for rel, sentences in found.items())
    )
    sentence = distinct.pop()
    assert "may commit on the ticket's own branch" in sentence, (
        "the shared sentence no longer PERMITS the commit; a one-word "
        "reversal applied to every file at once reads as agreement: " + sentence
    )
    assert "never commit" not in sentence, sentence
    assert COMMIT_RULE in sentence and COMMIT_RULE_LIMITS in sentence, sentence
    for rel in BRIEFING_FILES:
        assert "Never `git commit`" not in _prose(rel), (
            f"{rel} states the blanket ban the others narrowed"
        )


def test_work_records_the_ticket_base_before_printing_the_evidence():
    """The base is what makes the narrowed rule safe. work.md must record it
    when work begins (step 1) and diff the evidence from it (step 5), in that
    order, and must say the evidence is NOT the gate's verified marker."""
    body = _work()
    record = "scope_base.py --root . --record $1"
    base = "scope_base.py --root . --base $1"
    assert record in body, "work.md no longer records where the ticket starts"
    assert base in body, "work.md's evidence no longer diffs from the ticket base"
    assert body.index(record) < body.index(base), (
        "work.md prints the evidence before it records the base it diffs from"
    )
    assert "NOT the base verify-gate.sh" in body, (
        "work.md no longer says the evidence base is not the gate's marker, "
        "which is the conflation the whole change exists to undo"
    )
    assert "shows MORE, never less" in body, (
        "work.md dropped the fallback direction; a missing record must widen "
        "the evidence, not narrow it"
    )

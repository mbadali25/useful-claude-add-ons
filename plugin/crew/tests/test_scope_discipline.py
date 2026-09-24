"""The roles that touch code must carry a scope rule, and report what they left.

crew 1.0 deleted the writing roles this file first covered (developer,
smoke-author, dba, pm) and folded `/crew:work` into `/crew:implement`. What
remains: every shipped agent is read-only and routes an unrelated defect
through its own output, and `/crew:implement` -- the session that writes --
records the ticket base, prints the changed-file evidence and files
deferrals to TODO.md. The history below is kept because it is why.

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


def _implement():
    return _norm((PLUGIN / "commands" / "implement.md").read_text(encoding="utf-8"))


# crew 1.0's whole roster. None holds Write or Edit.
READONLY_ROLES = ("explorer", "reviewer", "security", "researcher")


def test_every_shipped_agent_is_read_only():
    """The claim above is about frontmatter; check it, do not trust it. A
    grant added later fails here before the prose that assumes it goes stale."""
    for name in READONLY_ROLES:
        line = [l for l in _agent_raw(name).splitlines()
                if l.startswith("tools:")][0]
        assert "Write" not in line and "Edit" not in line, (
            f"{name} gained write tools; crew 1.0 ships no writing agent"
        )


def test_reviewer_has_no_deferred_section_and_routes_a_deferral_as_a_nit():
    """Its contract is defect lines or exactly CLEAN. A mandatory prose
    heading makes every clean review violate one rule or the other."""
    body = _agent("reviewer")
    assert "## Deferred" not in body, (
        "reviewer regained a Deferred section, so a CLEAN review must now "
        "either break the output format or break the scope rule"
    )
    assert "An unrelated defect is a finding: emit it as `NIT|file:line|...`" in body, (
        "reviewer must route an unrelated defect through the finding format "
        "at NIT severity, since it has nowhere else to put it"
    )


def test_implement_files_a_deferral_to_todo_not_to_the_diff():
    body = _implement()
    assert "File it to `TODO.md`, not to the diff." in body, (
        "implement.md no longer says where an out-of-scope finding goes"
    )


def test_implement_prints_the_changed_file_evidence_even_empty():
    """A constraint whose evidence is never printed passes because nothing
    contradicted it -- not because it held."""
    body = _implement()
    assert "Print the changed-file list, every time, even empty" in body
    assert "git diff --name-only" in body, (
        "implement.md dropped the changed-file print"
    )
    assert "git ls-files --others --exclude-standard" in body, (
        "implement.md prints tracked changes only, so a new untracked file "
        "lands outside the ticket's paths without ever appearing"
    )


# The commit rule, in one form. Narrowed in crew 0.19.95 from a blanket ban:
# the scope evidence diffs from the ticket's own start (scope_base.py), so a
# commit on the ticket's branch no longer drops out of it.
COMMIT_RULE = "may commit on this ticket's own branch and nowhere else"


def test_implement_permits_a_commit_only_on_the_tickets_own_branch():
    body = _implement()
    assert COMMIT_RULE in body, (
        "implement.md no longer states the narrowed commit rule"
    )
    assert "Never `git commit`" not in body, (
        "the blanket ban is back while the evidence base makes it unnecessary"
    )


def test_implement_records_the_ticket_base_before_printing_the_evidence():
    """The base is what makes the narrowed rule safe: record it when work
    begins, diff the evidence from it later, in that order, and never from
    the gate's own verified marker."""
    body = _implement()
    record = "scope_base.py --root . --record $1"
    base = "scope_base.py --root . --base $1"
    assert record in body, "implement.md no longer records where the ticket starts"
    assert base in body, "implement.md's evidence no longer diffs from the ticket base"
    assert body.index(record) < body.index(base), (
        "implement.md prints the evidence before it records the base it diffs from"
    )
    assert "not from the verify gate's own marker" in body, (
        "implement.md no longer says the evidence base is not the gate's marker"
    )

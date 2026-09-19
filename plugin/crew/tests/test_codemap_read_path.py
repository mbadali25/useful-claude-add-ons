"""The roles that touch code must be told to read the code map.

Crew wrote a per-repo "what breaks here" store -- each codemap note's
`## Landmines` section -- and then never told the roles that do the work to
open it. Measured before crew 0.19.61: `grep -ci codemap` returned 0 for
commands/review.md, commands/work.md, and the developer, dba, qa-reviewer and
smoke-author agents. Every reviewer re-derived this repo's failure modes from
the diff plus CLAUDE.md, in an empty context, every single time.

These assertions are deliberately about the PROMPT TEXT rather than about
behaviour. A subagent prompt is not executable, so there is nothing to run; the
only thing that can regress mechanically is the instruction going missing from
the file, and that is exactly what happened for the whole life of the feature
before this. A prose-only fix here is not a weaker test than a behavioural one,
it is the only kind available -- but it is also why this file asserts the
SPECIFIC strings a reader needs rather than merely that the word appears.
"""
import pathlib

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]

# The roles that read or write code, and therefore need this repo's landmines.
# `explorer` and `analyst` are NOT here: both already read the codemap, and
# both existed before this change.
DOING_ROLES = ("developer", "dba", "qa-reviewer", "smoke-author")


def _agent(name):
    return (PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8")


def test_every_doing_role_is_told_to_read_the_codemap():
    for name in DOING_ROLES:
        body = _agent(name)
        assert ".crew/codemap/INDEX.md" in body, (
            f"{name}.md no longer names the codemap index, so the role has no "
            "entry point into the map and will re-derive the repo's failure "
            "modes from the diff, which is the defect 0.19.61 fixed"
        )
        assert "## Landmines" in body, (
            f"{name}.md no longer names the Landmines section by name. "
            "Pointing at the codemap without naming the section is not "
            "enough: the section is the part that carries what breaks here"
        )


def test_every_doing_role_carries_the_anchor_recheck_rule():
    """A stale anchor means re-check, and a role that does not know that
    either ignores a current note or distrusts a correct one. Both are worse
    than not reading it, because both look like diligence."""
    for name in DOING_ROLES:
        body = _agent(name)
        assert "git diff --name-only" in body, (
            f"{name}.md dropped the per-path freshness check. Without it the "
            "role treats 'anchor behind HEAD' as 'note is wrong', which "
            "over-reports staleness and sends it re-deriving anyway"
        )


def test_every_doing_role_must_report_which_notes_it_read():
    """A note read and a note skipped are indistinguishable in a summary that
    mentions neither -- the same shape as the metrics bug that counted rows
    instead of tickets. The evidence has to survive into the report."""
    for name in DOING_ROLES:
        body = _agent(name)
        assert "Say which notes you read" in body, (
            f"{name}.md dropped the reporting requirement, so a skipped "
            "landmine and a checked one now look identical downstream"
        )


def test_data_touching_roles_are_pointed_at_the_schema_note():
    for name in DOING_ROLES:
        body = _agent(name)
        assert "schema-<datasource>.md" in body, (
            f"{name}.md does not name the schema note, so a migration or "
            "index change is reviewed with no column, key or index facts"
        )


def test_onboard_writes_the_schema_note_and_refuses_to_invent_one():
    body = (PLUGIN / "commands" / "onboard.md").read_text(encoding="utf-8")
    assert ".crew/codemap/schema-<datasource>.md" in body
    assert "no datasource found" in body, (
        "onboard.md must tell the writer to report an absent datasource "
        "rather than writing an empty or inferred schema file. A schema note "
        "nobody can trace to a migration is the failure the command exists "
        "to prevent"
    )
    assert "`## Unverified`, not in" in body, (
        "onboard.md must route schema it could not trace to a file into "
        "## Unverified. Collapsing 'confirmed' and 'could not confirm' into "
        "one section is this repo's named recurring defect"
    )


def test_review_injects_repo_landmines_into_the_shared_prompt():
    """0.19.61 wired the FALLBACK reviewer and nobody else.

    /crew:review tries Codex then Copilot before falling back to the in-session
    qa-reviewer, and all three read one prompt.txt that had no codemap content.
    So on any machine with Codex installed, the reviewer that actually ran
    never saw the landmines. Wiring an agent file is not wiring the reviewer.
    """
    body = (PLUGIN / "commands" / "review.md").read_text(encoding="utf-8")
    assert "context.txt" in body, (
        "review.md no longer gathers repo landmines, so the provider path "
        "reviews with no knowledge of what breaks in this repository"
    )
    assert "## Landmines" in body and "Written by" in body
    assert 'git diff --name-only "$BASE"...HEAD > "$SCRATCH/changed.txt"' in body, (
        "review.md must BUILD the changed-file list it filters on. An earlier "
        "draft grepped a changed.txt nothing wrote; the failure went to "
        "/dev/null, no note ever matched, and the step reported itself done"
    )


def test_review_keeps_the_byte_identical_prompt_invariant():
    """All three providers must receive the same bytes.

    review.md states this as its reason for building the prompt in one place:
    'a defect count that differs between them is a fact about the model and
    not about how you worded it'. Injecting landmines for one provider would
    destroy exactly that. So the injection must land INSIDE the single
    heredoc, and no provider block may append to prompt.txt afterwards.
    """
    body = (PLUGIN / "commands" / "review.md").read_text(encoding="utf-8")
    assert body.count('cat > "$SCRATCH/prompt.txt"') == 1, (
        "prompt.txt is written in more than one place, so providers can now "
        "receive different bytes and cross-provider counts stop comparing"
    )
    assert '>> "$SCRATCH/prompt.txt"' not in body, (
        "something appends to prompt.txt after it is built, which is how one "
        "provider ends up with context another does not have"
    )
    _, _, tail = body.partition('cat > "$SCRATCH/prompt.txt"')
    # Split on the heredoc TERMINATOR (EOF at line start), not on the string
    # "EOF" -- that also matches the `<<EOF` marker three characters along, so
    # the body under test comes back as " <<" and the assertion passes or
    # fails for reasons having nothing to do with the prompt.
    heredoc = tail.split("\nEOF")[0]
    assert 'context.txt' in heredoc, (
        "the landmine injection is not inside the shared heredoc, so it is "
        "not part of what every provider reads"
    )

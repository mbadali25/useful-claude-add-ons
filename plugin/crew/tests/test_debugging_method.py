"""Crew ships a debugging method, and something dispatches it.

Before crew 0.19.66 this plugin had 27 commands and 19 skills and no method
for finding a cause. The gap was not subtle -- no command named diagnosis, no
skill described one, no role's job was to establish why something broke -- and
what fills that gap by default is fixing where the error surfaced, which is the
defect that comes back wearing a different symptom.

The method itself is `superpowers:systematic-debugging` by Jesse Vincent, MIT,
copied under `skills/crew-debugging/`. So these assertions cover three distinct
things that regress differently:

1. **The copy is complete.** Specifically the four adversarial pressure tests,
   which are the part most likely to be dropped as "not documentation" -- and
   they are exactly what makes the method hold in the situation that motivated
   it, where a deadline makes guessing tempting.
2. **The attribution survives.** MIT's one substantive condition is that the
   notice travel with the copy. A copy whose notice was edited away is a
   licence violation that no test but this one would notice.
3. **Something dispatches it.** A skill nothing routes to is a file. The
   routing lives in `commands/work.md` and `agents/developer.md`, and it is
   prose in a subagent prompt, so -- exactly as in test_codemap_read_path.py
   and test_scope_discipline.py -- there is nothing executable to run and the
   only mechanical regression is the instruction going missing. That is the
   state the feature would have been in from birth without this file.

Assertions run through `_norm`, so they survive a rewrap and fail only on the
sentence actually being removed.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
SKILL_DIR = PLUGIN / "skills" / "crew-debugging"

# Upstream's adversarial scenarios plus the no-pressure control. The control
# matters: a model that answers test-academic correctly and then folds under
# test-pressure-1 has shown it knows the method and abandons it, which is a
# different and worse finding than not knowing it.
PRESSURE_TESTS = (
    "test-pressure-1.md",
    "test-pressure-2.md",
    "test-pressure-3.md",
    "test-academic.md",
)

# The supporting techniques SKILL.md points at by name. A pointer to a file
# that is not there is worse than no pointer: it reads as an available
# technique right up to the moment somebody needs it.
TECHNIQUES = (
    "root-cause-tracing.md",
    "defense-in-depth.md",
    "condition-based-waiting.md",
    "find-polluter.sh",
)


def _norm(text):
    """Collapse runs of whitespace so an assertion survives a rewrap."""
    return re.sub(r"\s+", " ", text)


def _skill():
    return _norm((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))


def _agent(name):
    return _norm((PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8"))


def _command(name):
    return _norm((PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8"))


def test_the_skill_exists_with_its_entry_point():
    assert (SKILL_DIR / "SKILL.md").is_file(), (
        "skills/crew-debugging/SKILL.md is gone, so crew has no debugging "
        "method again -- the exact gap 0.19.66 was written to close"
    )


def test_the_pressure_tests_ship():
    """These are the first thing a tidy-up deletes, and the reason the method
    holds under the conditions that break it."""
    for name in PRESSURE_TESTS:
        assert (SKILL_DIR / name).is_file(), (
            f"{name} is missing. The pressure tests are not examples and not "
            "documentation -- they are the check on whether the Iron Law "
            "survives a deadline, sunk cost, or a senior engineer who is "
            "certain. Dropping them drops the part that works in exactly the "
            "situation the skill was added for"
        )
    body = _skill()
    for name in PRESSURE_TESTS:
        assert name in body, (
            f"SKILL.md no longer names {name}, so the file ships but nothing "
            "tells a reader it exists or what it is for"
        )


def test_the_supporting_techniques_ship_and_are_named():
    for name in TECHNIQUES:
        assert (SKILL_DIR / name).is_file(), f"{name} is missing from the skill"
        assert name in _skill(), (
            f"SKILL.md no longer names {name}; a technique nothing points at "
            "is a file nobody opens"
        )


def test_find_polluter_is_not_crlf():
    """`pathlib.write_text` is text mode on Windows, so a rewrite of this file
    through the obvious call turns every \\n into \\r\\n and bash dies on the
    shebang as `bad interpreter: ...^M`. The repo's .gitattributes governs
    what git stores, not what sits in the worktree bash executes -- so this
    asserts the bytes on disk, which is the thing that actually breaks."""
    raw = (SKILL_DIR / "find-polluter.sh").read_bytes()
    assert b"\r\n" not in raw, (
        "find-polluter.sh has CRLF line endings in the worktree. It will fail "
        "on its shebang as 'bad interpreter'. Rewrite it with newline='\\n' "
        "or restore with `git checkout -- <path>`"
    )
    assert raw.startswith(b"#!/usr/bin/env bash"), "shebang lost"


def test_the_attribution_survives():
    """MIT's one substantive condition. A copy that loses the notice is a
    licence violation, and nothing else in this repo would report it."""
    body = _skill()
    assert "Jesse Vincent" in body, (
        "SKILL.md dropped the author attribution for a method it copied "
        "wholesale from superpowers:systematic-debugging"
    )
    assert "MIT" in body, "SKILL.md no longer states the licence of what it copied"
    assert "plugin/crew/NOTICE.md" in body, (
        "SKILL.md no longer points at the notice file carrying the full "
        "copyright and permission text, so the attribution chain is broken "
        "at the only place a reader would follow it"
    )

    notice = PLUGIN / "NOTICE.md"
    assert notice.is_file(), (
        "plugin/crew/NOTICE.md is gone. It is the only place this plugin "
        "carries the MIT copyright and permission notice it is obliged to "
        "reproduce"
    )
    notice_body = _norm(notice.read_text(encoding="utf-8"))
    assert "Copyright (c) 2025 Jesse Vincent" in notice_body
    assert "Permission is hereby granted, free of charge" in notice_body, (
        "NOTICE.md no longer contains the MIT permission notice. The "
        "copyright line alone does not satisfy the licence -- it requires "
        "both, verbatim"
    )
    assert "crew-debugging" in notice_body, (
        "NOTICE.md no longer says WHICH files the notice covers, which makes "
        "it unattributable to anything in the next reader's tree"
    )


def test_the_iron_law_is_intact():
    """The whole method reduces to this one line under pressure. Softening it
    -- to 'should', or 'where time allows' -- is the failure it exists to
    prevent, and it would not fail any other check."""
    body = _skill()
    assert "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST" in body, (
        "SKILL.md lost or reworded the Iron Law. Every pressure test in this "
        "directory is a test of that one sentence"
    )


def test_phase_one_reads_crews_own_artifacts():
    """This is the adaptation -- the reason crew has a copy rather than a
    dependency. Lose it and the file is a duplicate of upstream."""
    body = _skill()
    for source, why in (
        ("## Landmines", "the per-repo record of what already broke here"),
        (".crew/codemap/INDEX.md", "the entry point into the map"),
        (".crew/codemap/schema-<datasource>.md", "the schema note for data defects"),
        ("graphify-out/graph.json", "the code graph, for a cross-file backward trace"),
        (".crew/verify.json", "the command the gate will actually run"),
    ):
        assert source in body, (
            f"SKILL.md's Phase 1 no longer names {source} ({why}). Without "
            "it the method re-derives this repo's failure modes from the diff "
            "in an empty context, every time, which is what crew already "
            "fixed once for the reviewer"
        )
    assert "git diff --name-only" in body, (
        "SKILL.md dropped the anchor re-check. Without it a note whose anchor "
        "is behind HEAD reads as 'wrong' rather than 'check it', so a current "
        "note gets discarded and the evidence source stops being used"
    )


def test_the_upstream_skill_is_preferred_when_present():
    body = _skill()
    assert "Invoke `superpowers:systematic-debugging` with the `Skill` tool" in body, (
        "SKILL.md no longer instructs an invocation of the upstream skill, so "
        "a session with the maintained original installed reads crew's "
        "snapshot instead. Asserting the NAME is not enough -- it appears "
        "several times in this file in sentences about provenance, so the "
        "routing step can be deleted while every mention survives. That is "
        "not hypothetical: it is the miss this suite's own sabotage run "
        "found, and the reason this assertion names the instruction"
    )
    assert "`Skill` tool" in body, (
        "the availability check must be a real Skill invocation. Prose asking "
        "the model to consider whether something is installed is not "
        "harness-enforced; an invocation of an absent skill errors, which is"
    )
    assert "absent from this session" in body or "absent **from this session**" in body, (
        "SKILL.md dropped the honest limit on the availability check. A "
        "failed invocation proves the skill is missing from THIS SESSION, "
        "not from the machine -- a disabled-but-installed plugin looks "
        "identical. Reporting it as 'not installed' is the unknown "
        "collapsing into a definite-sounding value, which is this repo's "
        "named recurring defect"
    )


def test_the_command_exists_and_cannot_edit_the_tree():
    """'Diagnosis does not patch' is enforced by the tool grant, not by the
    prose. A Write or Edit in allowed-tools silently converts this command
    into one that can fix what it was supposed to only explain."""
    path = PLUGIN / "commands" / "debug.md"
    assert path.is_file(), "commands/debug.md is gone; /crew:debug no longer exists"
    raw = path.read_text(encoding="utf-8")
    front = raw.split("---")[1]
    tools = [t.strip() for t in front.split("allowed-tools:")[1].split("\n")[0].split(",")]
    for forbidden in ("Write", "Edit"):
        assert forbidden not in tools, (
            f"/crew:debug was granted {forbidden}. The command's contract is "
            "that it ends with a cause and evidence and does not touch the "
            "tree; that separation is what makes the evidence auditable "
            "apart from the patch"
        )
    assert "Skill" in tools, (
        "/crew:debug lost the Skill tool, so it cannot load the method it "
        "exists to run, nor probe for the upstream skill"
    )


def test_the_command_carries_the_deferred_contract():
    """Composes with the scope discipline 0.19.62 gave the roles. Debugging
    finds unrelated problems more reliably than anything else the crew does,
    because tracing a data flow means reading code nobody was looking at."""
    body = _command("debug")
    assert "## Deferred — and where it went" in body, (
        "debug.md lost its Deferred section, so an investigation that turned "
        "up three unrelated defects reports identically to one that found "
        "none"
    )
    assert "Nothing deferred." in body, (
        "the empty case must be spelled. An absent section reads the same "
        "whether nothing was found or something was found and quietly fixed"
    )
    assert "TODO.md" in body, (
        "debug.md no longer says where a deferred finding goes, which makes "
        "the instruction unactionable and the queue unwritten"
    )


def test_work_routes_a_defect_to_the_debug_command():
    """A copy nobody dispatches is a file, not an integration."""
    body = _command("work")
    assert "run `/crew:debug` before you plan" in body, (
        "work.md no longer routes a defect to /crew:debug before planning, so "
        "a defect ticket goes straight to plan-and-fix and the method ships "
        "unreachable. The bare string `/crew:debug` also appears in the "
        "paragraph explaining what the command returns, so asserting only "
        "the name passes while the routing step is gone -- a miss this "
        "suite's sabotage run actually produced"
    )
    assert "defect rather than a feature" in body, (
        "work.md dropped the condition that decides when to debug. 'Run "
        "/crew:debug' with no trigger is either always or never, and in "
        "practice never"
    )


def test_developer_debugs_before_proposing_a_fix():
    body = _agent("developer")
    assert "run `/crew:debug` **before** you write the fix" in body, (
        "developer.md no longer runs /crew:debug before a fix, so the role "
        "that actually writes the diff is the one role not using the method. "
        "The bare name appears again further down, in the paragraph about a "
        "brief that already carries a debug report, so a presence check on "
        "it alone passes with the instruction deleted"
    )
    assert "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST" in body, (
        "developer.md dropped the Iron Law. Pointing at a command without "
        "stating the rule it enforces leaves the obvious fix looking "
        "reasonable, which is the whole failure mode"
    )
    assert "follow the `crew-debugging` skill it loads" in body, (
        "developer.md no longer sends the role into the crew-debugging skill, "
        "so it reaches the command but not the method behind it. Asserting "
        "the bare skill name passes on the mention in the reporting "
        "requirement below, which is about provenance rather than method"
    )

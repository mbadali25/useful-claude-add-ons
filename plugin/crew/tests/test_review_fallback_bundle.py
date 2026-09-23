"""`/crew:review` step 2c handed the Claude fallback nothing to read.

Codex BLOCK (`plugin/crew/commands/review.md:459`, found while probing every
QA provider ineligible so review fell through to 2c): step 2 builds
`$SCRATCH/diff.txt` + `$SCRATCH/manifest.json` via `review_patch.py` -- the
committed range PLUS staged, unstaged and untracked changes -- and writes
`$SCRATCH/prompt.txt` (codemap landmines included) for Codex (2a) and Copilot
(2b) to read. Step 2c just said "invoke crew:qa-reviewer" with no mention of
that bundle, and `qa-reviewer.md:59` told it to start over with its own
`git diff` against the base branch -- committed-range-only, the exact defect
`review_patch.py` exists to fix (`docs/review/03-codex-review.md`). So an
untracked-only defect could reach the fallback reviewer and still come back
CLEAN, on a dirty tree with nothing committed.

These are prompt-text assertions, the same shape as
`test_codemap_read_path.py` and for the same reason: a subagent prompt is not
executable, so the only thing that can regress mechanically is the
instruction going missing from the file.
"""
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]


def _norm(text):
    """Collapse whitespace so a rewrap does not break the assertion -- same
    helper, same reason, as test_codemap_read_path.py and
    test_scope_discipline.py."""
    return re.sub(r"\s+", " ", text)


def _review_raw():
    return (PLUGIN / "commands" / "review.md").read_text(encoding="utf-8")


def _qa_reviewer_raw():
    return (PLUGIN / "agents" / "qa-reviewer.md").read_text(encoding="utf-8")


def _step_2c(body_raw):
    """The Step 2c section text: from its own heading to the next bold
    "**Step" heading (Step 2d), so an assertion here cannot pass by matching
    something written for 2a or 2b instead."""
    start = body_raw.index("**Step 2c")
    end = body_raw.index("**Step 2d", start)
    return _norm(body_raw[start:end])


def test_step_2c_hands_qa_reviewer_the_manifest_built_patch():
    """The fix: 2c must reference the SAME three scratch paths 2a/2b's shared
    prompt is built from -- prompt.txt, diff.txt and manifest.json -- so the
    fallback reviewer reads the manifest-built patch rather than re-deriving
    one. Sabotage: remove the diff.txt reference from 2c and this goes red."""
    section = _step_2c(_review_raw())
    assert "$SCRATCH/prompt.txt" in section, (
        "step 2c no longer hands qa-reviewer the shared prompt, so it gets "
        "no codemap landmines and no instructions the other two providers "
        "were given"
    )
    assert "$SCRATCH/diff.txt" in section, (
        "step 2c no longer names the manifest-built patch path, so "
        "qa-reviewer has nothing to read except its own re-derived git diff"
    )
    assert "$SCRATCH/manifest.json" in section, (
        "step 2c dropped the manifest path, so qa-reviewer cannot be told "
        "which committed/staged/unstaged/untracked files were actually "
        "diffed"
    )
    assert "review that patch only" in section, (
        "step 2c no longer tells qa-reviewer to review ONLY the handed "
        "patch, which leaves room for it to fall back to its own git diff"
    )
    assert "must not re-derive its own diff with `git diff`" in section, (
        "step 2c no longer forbids qa-reviewer re-deriving its own diff, "
        "which is exactly the committed-range-only mistake review_patch.py "
        "exists to fix"
    )


def test_qa_reviewer_uses_the_supplied_patch_instead_of_git_diff():
    """qa-reviewer.md must prefer a supplied patch path over its own
    `git diff`, and the git-diff procedure must survive only as a fallback
    for the no-patch case, not as the unconditional first step. Sabotage:
    restore "Start with `git diff` against the base branch" as the
    unconditional first step and this goes red."""
    body = _norm(_qa_reviewer_raw())

    assert "review that patch file only" in body, (
        "qa-reviewer.md no longer tells the agent to review a supplied "
        "patch path when it is given one"
    )
    assert "Do NOT re-derive your own diff with `git diff`" in body, (
        "qa-reviewer.md no longer forbids re-deriving the diff when a patch "
        "was supplied"
    )

    guard_marker = "invoked with no patch path at all"
    git_diff_marker = "start with `git diff` against the base branch"
    guard_index = body.find(guard_marker)
    git_diff_index = body.find(git_diff_marker)
    assert guard_index != -1, (
        "qa-reviewer.md dropped the no-patch guard clause entirely, so the "
        "git diff fallback reads as unconditional again"
    )
    assert git_diff_index != -1, (
        "qa-reviewer.md dropped the git-diff fallback procedure outright -- "
        "it must still exist for the no-patch case"
    )
    assert guard_index < git_diff_index, (
        "'git diff against the base branch' appears before the no-patch "
        "guard that conditions it, which is the unconditional-first-step "
        "shape this fix removed"
    )


def test_qa_reviewer_self_derived_fallback_says_so_in_its_output():
    """When qa-reviewer falls back to its own git diff, its own-diff
    procedure must say so as part of the defect-line output -- the only
    channel its strict output contract allows -- rather than silently
    returning CLEAN on a diff that may have missed untracked content."""
    body = _norm(_qa_reviewer_raw())
    assert "NIT|self-derived|" in body, (
        "qa-reviewer.md no longer emits a self-derived marker line, so a "
        "fallback run that missed untracked files looks identical to a run "
        "that read the full manifest-built patch"
    )
    assert "may miss staged, unstaged or untracked changes" in body, (
        "qa-reviewer.md dropped the caveat naming what a self-derived git "
        "diff can miss"
    )
    # The strict CLEAN-only contract must carry the same exception, or the
    # two instructions contradict each other.
    assert "never `CLEAN` alone" in body or "never CLEAN alone" in body, (
        "the CLEAN-only output contract was not updated to allow the "
        "self-derived marker line ahead of it"
    )

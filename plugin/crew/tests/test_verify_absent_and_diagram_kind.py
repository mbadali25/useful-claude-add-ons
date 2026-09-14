"""Two unknowns that used to collapse into the safe-looking value.

Both fixes in this file are the same bug in two places: something that could
not be checked reported as something that was checked and found clean.

1. `read_diagrams` accepted `process-bitbucket-svg.mmd` as proof that `process`
   was documented, because it matched on `startswith(kind + "-")`. A diagram
   about one flow is not an overview of all of them, and the repo that has only
   the narrow one is exactly the repo that needs telling.
2. `/crew:review` step 0b read a `.crew/verify.json` that could be absent and
   selected nobody, which is what it also does when a map exists and matches
   nothing. Those are different findings and the command must name which one
   happened. (Since 2026-09-14 `!.crew/verify.json` is on the `.crew/*` stanza's
   named un-ignore list and this repo tracks its own map, so the absent case is
   now a repo that never ran `/crew:init` rather than every fresh clone. The
   distinction the command has to draw is unchanged.)
"""
import os
import subprocess

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_state

# The command file is the artifact under test for the review half. Read it from
# the repo rather than the installed plugin: the installed copy is whatever
# version this machine last pulled, and this suite is about THIS tree.
_REVIEW_MD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "commands", "review.md",
)


def _review_text():
    with open(_REVIEW_MD, encoding="utf-8") as handle:
        return handle.read().replace("\r\n", "\n")


def _diagrams(tmp_path, names):
    """A repo whose diagrams dir holds exactly `names`."""
    root = crew_fixtures.make_repo(tmp_path)
    dirpath = root / "docs" / "diagrams"
    dirpath.mkdir(parents=True)
    for name in names:
        # An anchor is deliberately absent: this file is about `missing`, and
        # `behind` must not be what makes the assertion pass.
        (dirpath / name).write_text("graph TD\n  a-->b\n", encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# 1. read_diagrams: a specific diagram does not discharge a general one
# --------------------------------------------------------------------------

def test_a_specific_process_diagram_does_not_satisfy_process(tmp_path):
    """The regression. `process-bitbucket-svg` is not `process`.

    Before the fix this returned `missing: []` -- the repo looked fully
    documented while having no process overview at all.
    """
    root = _diagrams(tmp_path, ["process-bitbucket-svg.mmd"])
    out = crew_state.read_diagrams(root, {})
    assert "process" in out["missing"]
    # And the other two are still reported, so this is not "everything is
    # missing now" masking the specific claim.
    assert set(out["missing"]) == {"architecture", "data-flow", "process"}
    assert out["total"] == 1


def test_the_exact_stem_still_satisfies_its_kind(tmp_path):
    """The fix must not make every kind permanently missing."""
    root = _diagrams(
        tmp_path,
        ["architecture.mmd", "data-flow.mmd", "process.mmd"],
    )
    out = crew_state.read_diagrams(root, {})
    assert out["missing"] == []
    assert out["total"] == 3


def test_a_specific_diagram_beside_its_general_one_is_fine(tmp_path):
    """This repo's own shape: both the overview and the narrow one.

    `process.mmd` satisfies `process`; `process-bitbucket-svg.mmd` is counted
    in `total` and obliges nothing. This is why the fix is a no-op here, and
    the test records that rather than leaving it to a claim in a PR body.
    """
    root = _diagrams(tmp_path, [
        "architecture.mmd", "data-flow.mmd", "process.mmd",
        "process-bitbucket-svg.mmd", "data-flow-crew-config.mmd",
    ])
    out = crew_state.read_diagrams(root, {})
    assert out["missing"] == []
    assert out["total"] == 5


def test_an_empty_diagrams_dir_reports_every_kind_missing(tmp_path):
    root = _diagrams(tmp_path, [])
    out = crew_state.read_diagrams(root, {})
    assert set(out["missing"]) == set(crew_state.DIAGRAM_KINDS)


def test_a_hyphenated_kind_is_matched_exactly_not_by_prefix(tmp_path):
    """`data-flow` is itself hyphenated, so it is the case a prefix rule
    handles worst: `data-flow-crew-config` must not satisfy it."""
    root = _diagrams(tmp_path, ["data-flow-crew-config.mmd"])
    out = crew_state.read_diagrams(root, {})
    assert "data-flow" in out["missing"]


# --------------------------------------------------------------------------
# 2. /crew:review step 0b: absence is its own outcome
# --------------------------------------------------------------------------

def test_review_names_the_absent_map_as_its_own_outcome():
    """The absent case must be reachable and must name /crew:init."""
    text = _review_text()
    assert "no verification map" in text
    assert "/crew:init" in text


def test_review_distinguishes_absent_from_matched_nothing():
    """The two must be DIFFERENT reported outcomes.

    This is the assertion that matters. A command file that mentions the absent
    case in prose but still routes it through the same sentence as "no rule
    matched" has not fixed anything -- so assert both strings exist and that
    they are not the same string.
    """
    text = _review_text()
    absent = "no verification map"
    matched_nothing = "no rule matched"
    assert absent in text
    assert matched_nothing in text
    assert absent != matched_nothing
    # They must not be collapsed by the old fall-through, which sent every
    # non-dispatching case to step 1 with nothing said.
    assert "If no matched rule names an agent, skip to step 1." not in text


def test_review_states_the_gap_without_resting_it_on_trackedness():
    """The premise under the GAP paragraph has now been wrong in BOTH directions.

    It first claimed the map "is committed and travels between machines" when
    `.crew/*` ignored it and nothing tracked it. That was corrected, and this
    test pinned the correction. On 2026-09-14 the policy changed -
    `!.crew/verify.json` joined the named un-ignore list - and the correction
    became the stale claim, so a test asserting the old wording is absent would
    now be pinning a second wrong reason.

    So this no longer pins EITHER reason. What it pins is the property that
    survived both: the GAP conclusion must not be derived from whether the map
    travels. A map that travels makes a named-but-missing agent more likely, not
    less, because it reaches machines whose roster nobody checked.
    """
    text = _review_text()
    assert "machine-local, so it was written against whatever was installed" not in text
    assert "Tracking the map makes this MORE likely" in text


def test_review_states_the_gap_rule_it_used_to_justify_wrongly():
    """Correcting the reason must not drop the conclusion."""
    text = _review_text()
    assert "GAP" in text
    assert "Never drop it silently." in text


def test_verify_json_really_is_tracked_here():
    """The trip-wire fired, and this is it re-armed pointing the other way.

    It used to assert `.crew/verify.json` was NOT tracked, with a docstring
    saying "if `.crew/verify.json` ever becomes tracked, this test fails and the
    wording in review.md gets revisited instead of quietly going stale". On
    2026-09-14 it became tracked, this test went red, and the wording was
    revisited - which is the whole of what the trip-wire was for.

    It now asserts the new state and the ordering that new state depends on: the
    un-ignore list is below `.crew/*`, and `.crew/.approved-*` is below the list,
    so promote-gate's own approval marker can never become trackable. Get that
    order wrong and the gate dirties the tree writing the file it just asked for.

    `check_crew_ignore_policy` in scripts/check-marketplace.py is what keeps the
    LIST from drifting across the docs; this is the narrower claim that the one
    repo running this suite actually tracks its own map.
    """
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    gitignore = os.path.join(repo, ".gitignore")
    if not os.path.isfile(gitignore):
        return  # not a checkout of this repo; nothing to claim
    with open(gitignore, encoding="utf-8") as handle:
        body = handle.read().replace("\r\n", "\n")
    assert ".crew/*" in body, (
        "`.crew/` with a trailing slash stops git descending into the directory, "
        "and every `!.crew/...` negation below it silently does nothing."
    )
    assert body.index(".crew/*") < body.index("!.crew/verify.json")
    assert body.index("!.crew/verify.json") < body.index(".crew/.approved-*"), (
        "`.crew/.approved-*` must sit BELOW the un-ignore list: later rules win, "
        "so a negation below it could re-admit promote-gate's own marker."
    )

    tracked = subprocess.run(
        ["git", "-C", repo, "ls-files", "--error-unmatch", ".crew/verify.json"],
        capture_output=True, text=True, check=False)
    assert tracked.returncode == 0, (
        ".crew/verify.json is NOT tracked. This repo's README and review.md say "
        "the verification map travels; if that changed back, revisit them both."
    )


def test_review_no_longer_pins_a_number_to_the_roster():
    """`crew's eleven` was written when `agents/` held 11 files. The roster is
    a moving number that nothing checks, so the fix removes the count rather
    than correcting it -- the shape `plugin/PLUGINS.md` already uses."""
    text = _review_text()
    assert "crew's eleven" not in text
    assert "crew's own roles" in text

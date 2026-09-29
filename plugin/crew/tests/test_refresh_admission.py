"""T-0094: `crew_refresh_check.artifact_verdicts`, the judgement the completion
audit uses to admit a changed refresh artifact without Touch (direction.md
Option 1, owner standing rule 2026-09-28: "re-anchor/regenerate only, never a
content rewrite", "when its own changes made them stale").

A changed artifact is admitted only when a path the ticket changed REACHES it
and the edit is a RE-ANCHOR (a map's `anchor:` or a diagram's provenance sha
moved to a commit reachable from HEAD; INDEX.md rows of such maps; a rendered
diagram beside such a source) or a REGENERATION (a rule equal to
`crew_instructions.expected_rules`, or a generated rule removed because no map
expects it; the graph after a code change). "Could not tell" is its own
verdict, None, and never admits. It judges shape and reach, never truth: a
re-anchored map may still say something wrong, and that is the reviewer's.

A guard class: must-allow and must-block cases both, and every rung has a
mutation in `sabotage_refresh.py` after the `# T-0094` marker that turns one
of these red.
"""
import context  # noqa: F401  pylint: disable=unused-import
import crew_instructions
import crew_refresh_check
import pytest
from crew_fixtures import head_sha
from refresh_fixtures import (
    DIAGRAM,
    GRAPH,
    INDEX,
    MAP,
    RENDERED,
    RULE,
    anchored_repo,
    index_row_append,
    map_text,
    re_anchor_diagram,
    re_anchor_map,
    read,
    rebuild_graph,
    write,
)
from review_fixtures import git

REACH = ["src/app.py"]
APP = MAP.format(name="app")
APP_RULE = RULE.format(name="app")
FLOW = DIAGRAM.format(name="flow")


def _verdicts(root, base, reach, artifacts):
    return crew_refresh_check.artifact_verdicts(str(root), base, reach, artifacts)


def _verdict(root, base, reach, rel):
    verdict, reason = _verdicts(root, base, reach, [rel])[rel]
    return verdict, reason


def _judged(root, base, reach, rel, expected):
    """(verdict, whether `expected` is in the reason): a wrong verdict and a
    wrong reason fail differently."""
    verdict, reason = _verdict(root, base, reach, rel)
    return verdict, expected in reason, reason


@pytest.fixture(name="anchored")
def _anchored(tmp_path):
    return anchored_repo(tmp_path)


# --- must-allow -----------------------------------------------------------------

def test_a_reached_map_re_anchored_to_head_is_admitted(anchored):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40))

    assert _judged(root, base, REACH, APP, "re-anchored")[:2] == (True, True)


def test_a_map_whose_base_anchor_names_no_commit_is_admitted_when_re_anchored(tmp_path):
    root, base = anchored_repo(tmp_path, map_anchor="deadbeefdead")
    re_anchor_map(root, "app", head_sha(root, 40))

    assert _judged(root, base, REACH, APP, "re-anchored")[:2] == (True, True)


def test_the_index_rows_of_re_anchored_maps_are_admitted(anchored):
    root, base = anchored
    head = head_sha(root, 40)
    re_anchor_map(root, "app", head)
    index_row_append(root, "app", f"re-anchored to `{head[:8]}`")

    got = _verdicts(root, base, REACH, [APP, INDEX])

    assert (got[APP][0], got[INDEX][0]) == (True, True), got


def test_a_regenerated_rule_is_admitted_whatever_the_map_did(anchored):
    root, base = anchored
    write(root, APP, read(root, APP).replace("x is one", "x is two"))
    crew_instructions.rules(str(root))

    got = _verdicts(root, base, REACH, [APP, APP_RULE])

    assert (got[APP_RULE][0], got[APP][0], "anchor did not move" in got[APP][1]) == (
        True, False, True), got


def test_a_generated_rule_removed_because_no_map_expects_it_is_admitted(anchored):
    root, base = anchored
    git(root, "rm", "-q", APP, APP_RULE)

    got = _verdicts(root, base, REACH, [APP, APP_RULE])

    assert (got[APP_RULE][0], got[APP][0], "deleted, not a re-anchor" in got[APP][1]) == (
        True, False, True), got


def test_a_reached_diagram_re_anchored_to_head_is_admitted(anchored):
    root, base = anchored
    re_anchor_diagram(root, "flow", head_sha(root, 40))

    assert _judged(root, base, REACH, FLOW, "re-anchored")[:2] == (True, True)


def test_a_rendered_diagram_beside_an_admitted_source_is_admitted(anchored):
    root, base = anchored
    head = head_sha(root, 40)
    re_anchor_diagram(root, "flow", head)
    write(root, RENDERED, f"<svg><!-- {head} --></svg>\n")

    got = _verdicts(root, base, REACH, [FLOW, RENDERED])

    assert (got[FLOW][0], got[RENDERED][0]) == (True, True), got


def test_a_graph_rebuilt_after_a_code_change_is_admitted(anchored):
    root, base = anchored
    rebuild_graph(root, head_sha(root, 40))

    got = _verdicts(root, base, REACH, list(GRAPH))

    assert [got[g][0] for g in GRAPH] == [True, True], got


def test_a_version_bump_reaches_the_map_citing_the_manifest(anchored):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40), cites=(".claude-plugin/plugin.json:3",))

    got = _judged(root, base, [".claude-plugin/plugin.json"], APP, "re-anchored")

    assert got[:2] == (True, True), got


def test_a_merged_in_main_path_in_the_reach_admits_the_map_it_reaches(anchored):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40), cites=("other/keep.py:1",))

    got = _judged(root, base, ["other/keep.py"], APP, "re-anchored")

    assert got[:2] == (True, True), got


def test_changelog_is_a_code_path_for_the_graph(anchored):
    """`CHANGELOG.md` is not under `GRAPH_NONCODE_PATHS`, so for the graph it
    is code: the documented reading, asserted rather than implied. The
    refusal case is `docs/x.md`, below."""
    root, base = anchored
    rebuild_graph(root, head_sha(root, 40))

    assert _verdict(root, base, ["CHANGELOG.md"], GRAPH[0])[0] is True


# --- must-block -----------------------------------------------------------------

def test_a_map_edited_without_moving_its_anchor_is_refused(anchored):
    root, base = anchored
    write(root, APP, read(root, APP).replace("x is one", "x is two"))

    assert _judged(root, base, REACH, APP, "anchor did not move")[:2] == (False, True)


def test_a_re_anchored_map_no_changed_path_reaches_is_refused(anchored):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40))

    got = _judged(root, base, ["other/keep.py"], APP, "no changed path reaches it")

    assert got[:2] == (False, True), got


def test_a_map_anchored_to_a_commit_not_reachable_from_head_is_refused(anchored):
    root, base = anchored
    git(root, "checkout", "-q", "-b", "side", base)
    write(root, "other/keep.py", "x = 3\n")
    git(root, "commit", "-qam", "side commit")
    side = head_sha(root, 40)
    git(root, "checkout", "-q", "main")
    re_anchor_map(root, "app", side)

    got = _judged(root, base, REACH, APP, "is not reachable from HEAD")

    assert got[:2] == (False, True), got


def test_a_map_anchored_to_no_commit_is_refused(anchored):
    root, base = anchored
    re_anchor_map(root, "app", "deadbeefdead")

    assert _judged(root, base, REACH, APP, "names no commit")[:2] == (False, True)


def test_a_map_with_no_anchor_line_is_refused(anchored):
    root, base = anchored
    write(root, APP, map_text("app", None, ("src/app.py:2",), "x is two"))

    assert _judged(root, base, REACH, APP, "no anchor: line")[:2] == (False, True)


def test_a_new_map_is_not_a_re_anchor(anchored):
    root, base = anchored
    rel = MAP.format(name="new")
    write(root, rel, map_text("new", head_sha(root, 40), ("src/app.py:2",), "new"))

    assert _judged(root, base, REACH, rel, "new file, not a re-anchor")[:2] == (False, True)


def test_a_deleted_map_is_not_a_re_anchor(anchored):
    root, base = anchored
    git(root, "rm", "-q", APP)

    assert _judged(root, base, REACH, APP, "deleted, not a re-anchor")[:2] == (False, True)


def test_a_map_named_in_not_subsystems_is_judged_by_touch(anchored):
    root, base = anchored
    rel = ".crew/codemap/UPGRADE.md"
    write(root, rel, f"anchor: r@{head_sha(root, 40)}\n`src/app.py:1`\n")

    assert _judged(root, base, REACH, rel, "not a subsystem map")[:2] == (False, True)


@pytest.mark.parametrize("edit", ["header-prose", "row-of-an-unjudged-map"])
def test_an_index_edit_outside_a_re_anchored_row_is_refused(anchored, edit):
    root, base = anchored
    head = head_sha(root, 40)
    re_anchor_map(root, "app", head)
    if edit == "header-prose":
        write(root, INDEX, read(root, INDEX).replace("One row per subsystem map.",
                                                     "Rewritten prose."))
        artifacts = [APP, INDEX]
    else:
        index_row_append(root, "app", f"re-anchored to `{head[:8]}`")
        artifacts = [INDEX]

    got = _verdicts(root, base, REACH, artifacts)[INDEX]

    assert (got[0], "INDEX.md line" in got[1]) == (False, True), got


def test_a_hand_edited_rule_is_refused(anchored):
    root, base = anchored
    write(root, APP_RULE, read(root, APP_RULE) + "- a hand-written landmine\n")

    assert _judged(root, base, REACH, APP_RULE, "bytes differ from expected_rules")[:2] == (
        False, True)


def test_a_rule_removed_while_its_map_still_expects_it_is_refused(anchored):
    root, base = anchored
    git(root, "rm", "-q", APP_RULE)

    got = _judged(root, base, REACH, APP_RULE, "removed, but a map still expects it")

    assert got[:2] == (False, True), got


def test_a_rule_removed_that_was_not_generated_is_refused(tmp_path):
    rel = RULE.format(name="hand")
    root, base = anchored_repo(tmp_path, extra={rel: "# hand\nwritten by a person\n"})
    git(root, "rm", "-q", rel)

    got = _judged(root, base, REACH, rel, "removed, but it was not generated")

    assert got[:2] == (False, True), got


def test_a_diagram_edited_without_moving_its_anchor_is_refused(anchored):
    root, base = anchored
    write(root, FLOW, read(root, FLOW) + "  b --> c\n")

    assert _judged(root, base, REACH, FLOW, "anchor did not move")[:2] == (False, True)


def test_a_diagram_with_no_provenance_line_is_refused(anchored):
    root, base = anchored
    write(root, FLOW, "%% Anchors: src/app.py\nflowchart LR\n  a --> c\n")

    assert _judged(root, base, REACH, FLOW, "no provenance line")[:2] == (False, True)


def test_a_rendered_diagram_whose_source_was_not_re_anchored_is_refused(anchored):
    root, base = anchored
    write(root, RENDERED, "<svg><!-- redrawn by hand --></svg>\n")

    got = _judged(root, base, REACH, RENDERED,
                  "rendered file whose source flow.mmd was not re-anchored")

    assert got[:2] == (False, True), got


def test_a_graph_rebuild_with_no_code_change_is_refused(anchored):
    root, base = anchored
    rebuild_graph(root, head_sha(root, 40))

    got = _judged(root, base, ["docs/x.md"], GRAPH[0], "no code change")

    assert got[:2] == (False, True), got


def test_a_git_failure_while_judging_a_map_is_could_not_tell(anchored, monkeypatch):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40))
    monkeypatch.setattr(crew_refresh_check, "_git_rc", lambda *a, **k: None)

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL)) == (None, True), reason


def test_an_unreadable_base_copy_is_could_not_tell(anchored, monkeypatch):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40))
    monkeypatch.setattr(crew_refresh_check, "_base_text", lambda *a, **k: (None, "error: boom"))

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL)) == (None, True), reason


def test_an_unreadable_config_is_could_not_tell_for_every_artifact(anchored):
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40))
    write(root, ".crew/config.json", "{not json")

    got = _verdicts(root, base, REACH, [APP, GRAPH[0]])

    assert {v for v, _ in got.values()} == {None}, got


def test_a_file_under_an_artifact_dir_of_no_admitted_kind_is_refused(anchored):
    root, base = anchored
    rel = ".crew/codemap/notes.txt"
    write(root, rel, "scratch\n")

    assert _verdict(root, base, REACH, rel)[0] is False

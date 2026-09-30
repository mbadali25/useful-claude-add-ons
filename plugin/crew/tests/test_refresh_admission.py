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
import os
import re
import subprocess

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
    ambiguous_commit_prefix,
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


def _failing_git(monkeypatch, name, match, result):
    """Patch crew_refresh_check.<name> (`_git_rc` or `_git_lines`) to return
    `result` (None, or an exit code such as 129) for the one call whose args
    satisfy `match(args)`, and delegate every other call to the real helper."""
    real = getattr(crew_refresh_check, name)
    monkeypatch.setattr(crew_refresh_check, name,
                        lambda r, *a: result if match(a) else real(r, *a))


def _dangling(root, rel):
    """A symlink at `rel` to a path that does not exist: `os.path.lexists` is
    True, `read_text` returns None. Skipped where symlinks cannot be made."""
    path = root.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(os.path.join(str(root), "nonexistent"), str(path))
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


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


@pytest.mark.parametrize("manifest", [".claude-plugin/plugin.json",
                                      "plugin/crew/.claude-plugin/plugin.json"],
                         ids=["root", "plugin"])
def test_a_version_bump_reaches_the_map_citing_the_manifest(tmp_path, manifest):
    root, base = anchored_repo(tmp_path, cites=(manifest + ":3",))
    re_anchor_map(root, "app", head_sha(root, 40), cites=(manifest + ":3",))

    got = _judged(root, base, [manifest], APP, "re-anchored")

    assert got[:2] == (True, True), got


def test_a_merged_in_main_path_in_the_reach_admits_the_map_it_reaches(tmp_path):
    root, base = anchored_repo(tmp_path, cites=("other/keep.py:1",))
    re_anchor_map(root, "app", head_sha(root, 40), cites=("other/keep.py:1",))

    got = _judged(root, base, ["other/keep.py"], APP, "re-anchored")

    assert got[:2] == (True, True), got


def test_a_map_re_anchored_forward_to_a_commit_behind_head_is_admitted(anchored):
    root, base = anchored
    re_anchor_map(root, "app", base)

    assert _judged(root, base, REACH, APP, "re-anchored")[:2] == (True, True)


def test_a_map_whose_base_anchor_is_off_heads_history_is_admitted_when_re_anchored(tmp_path):
    """A squash merge leaves the commit a refresh anchored to in the object
    store but off HEAD's history: nothing to be behind, so any qualifying
    anchor has moved -- the case "names no commit" covers once it is gone."""
    root, base = anchored_repo(tmp_path, map_anchor="side")
    re_anchor_map(root, "app", head_sha(root, 40))

    assert _judged(root, base, REACH, APP, "re-anchored")[:2] == (True, True)


def test_a_diagram_with_no_anchors_line_is_reached_by_any_code_change(tmp_path):
    root, base = anchored_repo(tmp_path, diagram_anchors=None)
    re_anchor_diagram(root, "flow", head_sha(root, 40))

    assert _judged(root, base, ["other/keep.py"], FLOW, "re-anchored")[:2] == (True, True)


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


@pytest.mark.parametrize("bookkeeping", ["CHANGELOG.md", "TODO.md", "plugin/PLUGINS.md",
                                         ".claude-plugin/marketplace.json",
                                         "plugin/crew/BUDGETS.md"])
def test_release_bookkeeping_other_than_a_manifest_reaches_no_map(tmp_path, bookkeeping):
    """Every release rewrites these and most maps cite one, so a reach that
    kept them would reach nearly every map on every ticket (review round 1)."""
    root, base = anchored_repo(tmp_path, cites=(bookkeeping + ":1",))
    re_anchor_map(root, "app", head_sha(root, 40), cites=(bookkeeping + ":1",))

    got = _judged(root, base, [bookkeeping], APP, "no changed path reaches it")

    assert got[:2] == (False, True), got


def test_a_citation_the_edit_adds_does_not_make_the_map_reached(anchored):
    """Reach is read from the BASE copy: an edit cannot cite its way in."""
    root, base = anchored
    re_anchor_map(root, "app", head_sha(root, 40), cites=("other/keep.py:1",))

    got = _judged(root, base, ["other/keep.py"], APP, "no changed path reaches it")

    assert got[:2] == (False, True), got


def test_a_map_anchored_backwards_is_refused(anchored):
    root, base = anchored
    older = git(root, "rev-parse", base + "~2").strip()
    re_anchor_map(root, "app", older)

    got = _judged(root, base, REACH, APP, "not forward")

    assert got[:2] == (False, True), got


def test_a_map_re_anchored_to_the_same_commit_by_another_name_is_refused(anchored):
    root, base = anchored
    first = git(root, "rev-parse", base + "~1").strip()
    re_anchor_map(root, "app", first[:12])

    assert _judged(root, base, REACH, APP, "anchor did not move")[:2] == (False, True)


def test_an_unchanged_anchor_git_cannot_resolve_is_not_a_move(anchored, monkeypatch):
    """Review round 1: a failed `rev-parse` of the base anchor read as "the
    anchor moved". An anchor whose text did not change has not moved,
    whatever git says."""
    root, base = anchored
    first = git(root, "rev-parse", base + "~1").strip()
    write(root, APP, read(root, APP).replace("x is one", "x is two"))
    real = crew_refresh_check._git_lines  # pylint: disable=protected-access
    monkeypatch.setattr(crew_refresh_check, "_git_lines",
                        lambda r, *a: None if first + "^{commit}" in a else real(r, *a))

    assert _judged(root, base, REACH, APP, "anchor did not move")[:2] == (False, True)


@pytest.mark.parametrize("fails", ["rev-parse", "cat-file"])
def test_a_base_anchor_git_cannot_resolve_is_could_not_tell(anchored, monkeypatch, fails):
    """The neighbour: the anchor TEXT changed (a short name for the same
    commit), so only git can say whether it moved -- and it cannot."""
    root, base = anchored
    first = git(root, "rev-parse", base + "~1").strip()
    re_anchor_map(root, "app", first[:12])
    name = "_git_lines" if fails == "rev-parse" else "_git_rc"
    real = getattr(crew_refresh_check, name)
    monkeypatch.setattr(crew_refresh_check, name,
                        lambda r, *a: None if first + "^{commit}" in a else real(r, *a))

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL)) == (None, True), reason


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


OTHER_ROW = "| [`other.md`](other.md) | `00000000` | first pass | other |\n"


@pytest.mark.parametrize("deleted", ["One row per subsystem map.\n", OTHER_ROW],
                         ids=["header-prose", "another-maps-row"])
def test_an_index_line_deleted_outside_a_re_anchored_row_is_refused(tmp_path, deleted):
    """A pure deletion has no new-side line, so only the base side can
    refuse it (review round 1): the header prose, or another map's row."""
    root, base = anchored_repo(tmp_path)
    write(root, INDEX, read(root, INDEX) + OTHER_ROW)
    git(root, "commit", "-qam", "a second row")
    base = head_sha(root, 40)
    git(root, "commit", "-q", "--allow-empty", "-m", "ticket edit")
    head = head_sha(root, 40)
    re_anchor_map(root, "app", head)
    index_row_append(root, "app", f"re-anchored to `{head[:8]}`")
    write(root, INDEX, read(root, INDEX).replace(deleted, ""))

    got = _verdicts(root, base, REACH, [APP, INDEX])

    assert (got[APP][0], got[INDEX][0], "INDEX.md base line" in got[INDEX][1]) == (
        True, False, True), got


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


def test_a_re_anchored_diagram_no_changed_path_reaches_is_refused(anchored):
    root, base = anchored
    re_anchor_diagram(root, "flow", head_sha(root, 40))

    got = _judged(root, base, ["other/keep.py"], FLOW, "no changed path reaches it")

    assert got[:2] == (False, True), got


def test_a_diagram_with_no_anchors_line_is_refused_with_no_code_change(tmp_path):
    root, base = anchored_repo(tmp_path, diagram_anchors=None)
    re_anchor_diagram(root, "flow", head_sha(root, 40))

    got = _judged(root, base, ["docs/x.md"], FLOW, "no changed path reaches it")

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


@pytest.mark.parametrize("rule", ["removed", "regenerated"])
def test_a_rule_renderer_that_raises_is_could_not_tell(anchored, monkeypatch, rule):
    root, base = anchored
    if rule == "removed":
        git(root, "rm", "-q", APP_RULE)
    else:
        write(root, APP, read(root, APP).replace("x is one", "x is two"))
        crew_instructions.rules(str(root))

    def boom(_root):
        raise RuntimeError("renderer broke")

    monkeypatch.setattr(crew_instructions, "expected_rules", boom)

    verdict, reason = _verdict(root, base, REACH, APP_RULE)

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


# --- could not tell (review round 2) -------------------------------------------

@pytest.mark.parametrize("case", ["unexpected", "expected"])
def test_an_unreadable_rule_is_could_not_tell(anchored, case):
    """Review round 2: `read_text` returned None for a rule file that exists,
    and `None == expected.get(key)` admitted one no map expects as
    `regenerated` and called one a map expects `bytes differ`."""
    root, base = anchored
    if case == "unexpected":
        rel = RULE.format(name="ghost")
    else:
        rel = APP_RULE
        root.joinpath(*rel.split("/")).unlink()
    _dangling(root, rel)

    verdict, reason = _verdict(root, base, REACH, rel)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL)) == (None, True), reason


# Review round 2: every could-not-tell branch of `_sha_moved`, `_moved_from`
# and `_rule_verdict` has a control. Each patch fails ONE git call and lets the
# rest run, and each asserts its branch's own reason text, so an earlier branch
# answering for it fails the test too. These pass on correct code; the round-2
# entries in `sabotage_refresh.py` turn each one red.

def _args_are(*want):
    return lambda args: tuple(args) == want


@pytest.mark.parametrize("case", ["cat-file-none", "cat-file-129", "ancestor-129",
                                  "ancestor-none", "rev-parse"])
def test_a_new_anchor_git_cannot_judge_is_could_not_tell(anchored, monkeypatch, case):
    root, base = anchored
    new = head_sha(root, 40)
    re_anchor_map(root, "app", new)
    cat_file = _args_are("cat-file", "-e", new + "^{commit}")
    ancestor = _args_are("merge-base", "--is-ancestor", new, "HEAD")
    name, match, result, text = {
        "cat-file-none": ("_git_rc", cat_file, None, "git could not run"),
        "cat-file-129": ("_git_rc", cat_file, 129, "git exited 129 reading anchor"),
        "ancestor-129": ("_git_rc", ancestor, 129, "is behind HEAD"),
        "ancestor-none": ("_git_rc", ancestor, None, "is behind HEAD"),
        "rev-parse": ("_git_lines", _args_are("rev-parse", "--verify", new + "^{commit}"),
                      None, "could not resolve"),
    }[case]
    _failing_git(monkeypatch, name, match, result)

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            text in reason) == (None, True, True), reason


@pytest.mark.parametrize("case", ["behind-head", "forward"])
def test_a_moved_anchor_git_cannot_order_is_could_not_tell(anchored, monkeypatch, case):
    root, base = anchored
    new = head_sha(root, 40)
    old = re.search(r"anchor: r@([0-9a-f]+)", read(root, APP)).group(1)
    was = git(root, "rev-parse", "--verify", old + "^{commit}").strip()
    re_anchor_map(root, "app", new)
    of, text = {"behind-head": ("HEAD", f"whether {old[:12]} is behind HEAD"),
                "forward": (new, f"whether {new[:12]} follows {old[:12]}")}[case]
    _failing_git(monkeypatch, "_git_rc", _args_are("merge-base", "--is-ancestor", was, of), 129)

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            text in reason) == (None, True, True), reason


def test_the_moved_anchor_fixture_reaches_the_ordering_branches(anchored):
    """The two cases above test nothing unless the base anchor is on HEAD's
    history and is not HEAD: `_moved_from` returns before its ordering
    branches otherwise."""
    root, _base = anchored
    old = re.search(r"anchor: r@([0-9a-f]+)", read(root, APP)).group(1)
    on_history = crew_refresh_check._is_ancestor(str(root), old)  # pylint: disable=protected-access

    assert (on_history, old != head_sha(root, 40)) == (True, True)


def test_a_removed_rule_whose_base_copy_git_cannot_read_is_could_not_tell(tmp_path, monkeypatch):
    rel = RULE.format(name="hand")
    root, base = anchored_repo(tmp_path, extra={rel: "# hand\nwritten by a person\n"})
    git(root, "rm", "-q", rel)
    _failing_git(monkeypatch, "_git_rc", _args_are("cat-file", "-e", f"{base}:{rel}"), 129)

    verdict, reason = _verdict(root, base, REACH, rel)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            "base copy error: git exited 129" in reason) == (None, True, True), reason


# --- review round 3 -------------------------------------------------------------
# Nothing moves from a base with no anchor; INDEX.md and a rule are judged by
# the bytes git sees change, not by decoded, newline-normalised text. Each
# must-block case has an entry after the round-3 marker in `sabotage_refresh.py`.

BARE_DIAGRAM = "%% Anchors: src/app.py\nflowchart LR\n  a --> b\n"


@pytest.mark.parametrize("kind", ["map", "diagram"])
def test_an_anchor_added_where_the_base_copy_had_none_is_refused(tmp_path, kind):
    if kind == "map":
        rel = MAP.format(name="bare")
        before = map_text("bare", None, ("src/app.py:1",), "x is one")
    else:
        rel = DIAGRAM.format(name="bare")
        before = BARE_DIAGRAM
    root, base = anchored_repo(tmp_path, extra={rel: before})
    head = head_sha(root, 40)
    if kind == "map":
        write(root, rel, map_text("bare", head, ("src/app.py:2",), "x is two"))
    else:
        write(root, rel, f"%% Generated from r@{head} on 2026-09-30.\n{before}")

    got = _judged(root, base, REACH, rel, "the base copy has no anchor")

    assert got[:2] == (False, True), got


BYTE_EDITS = {
    "final-newline-removed": lambda data: data[:-1],
    "crlf": lambda data: data.replace(b"\n", b"\r\n"),
    "bom": lambda data: b"\xef\xbb\xbf" + data,
}


def _edit_bytes(root, rel, edit):
    path = root.joinpath(*rel.split("/"))
    path.write_bytes(BYTE_EDITS[edit](path.read_bytes()))


@pytest.mark.parametrize("edit", list(BYTE_EDITS))
def test_an_index_byte_edit_with_no_re_anchored_map_is_refused(anchored, edit):
    root, base = anchored
    _edit_bytes(root, INDEX, edit)

    got = _verdicts(root, base, REACH, [INDEX])[INDEX]

    assert (got[0], "INDEX.md" in got[1]) == (False, True), got


@pytest.mark.skipif(os.name == "nt", reason="core.fileMode is false on Windows")
def test_an_index_mode_change_with_no_re_anchored_map_is_refused(anchored):
    root, base = anchored
    path = root.joinpath(*INDEX.split("/"))
    path.chmod(path.stat().st_mode | 0o111)

    got = _judged(root, base, REACH, INDEX, "mode")

    assert got[:2] == (False, True), got


@pytest.mark.parametrize("edit", ["crlf", "bom"])
def test_a_rule_whose_bytes_are_not_the_generated_bytes_is_refused(anchored, edit):
    root, base = anchored
    _edit_bytes(root, APP_RULE, edit)

    got = _judged(root, base, REACH, APP_RULE, "bytes differ from expected_rules")

    assert got[:2] == (False, True), got


@pytest.mark.parametrize("rel", [INDEX, APP_RULE], ids=["index", "rule"])
def test_a_crlf_checkout_under_autocrlf_is_judged_as_git_stores_it(anchored, rel):
    """The must-allow neighbour: Git for Windows' default `core.autocrlf=true`
    checks text out as CRLF and stores it as LF, so a CRLF working copy of a
    real refresh is the refresh."""
    root, base = anchored
    git(root, "config", "core.autocrlf", "true")
    head = head_sha(root, 40)
    re_anchor_map(root, "app", head)
    index_row_append(root, "app", f"re-anchored to `{head[:8]}`")
    crew_instructions.rules(str(root))
    _edit_bytes(root, rel, "crlf")

    got = _verdicts(root, base, REACH, [APP, rel])

    assert (got[APP][0], got[rel][0]) == (True, True), got


def _failing_out(monkeypatch, first, result):
    """Patch `_git_out` to return `result` for the one call whose first arg is
    `first`, delegating every other call."""
    real = crew_refresh_check._git_out  # pylint: disable=protected-access
    monkeypatch.setattr(crew_refresh_check, "_git_out",
                        lambda r, *a, **k: result if a[0] == first else real(r, *a, **k))


@pytest.mark.parametrize("result", [(None, b""), (129, b"")], ids=["none", "129"])
def test_an_index_git_cannot_diff_is_could_not_tell(anchored, monkeypatch, result):
    root, base = anchored
    head = head_sha(root, 40)
    re_anchor_map(root, "app", head)
    index_row_append(root, "app", f"re-anchored to `{head[:8]}`")
    _failing_out(monkeypatch, "diff", result)

    verdict, reason = _verdicts(root, base, REACH, [APP, INDEX])[INDEX]

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            "git diff" in reason) == (None, True, True), reason


@pytest.mark.parametrize("result", [(None, b""), (129, b"")], ids=["none", "129"])
def test_a_rule_git_cannot_hash_is_could_not_tell(anchored, monkeypatch, result):
    root, base = anchored
    _edit_bytes(root, APP_RULE, "crlf")
    _failing_out(monkeypatch, "hash-object", result)

    verdict, reason = _verdict(root, base, REACH, APP_RULE)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            "could not hash" in reason) == (None, True, True), reason


# --- review round 4 (owner-rejected, narrow successor) --------------------------
# Real git, not a patched exit code: the defect is what `cat-file -e`'s exit
# 128 means, and only git can show that a short anchor two commits share is
# refused as AMBIGUOUS with the same exit as one that names nothing.

def _ambiguous_objects(root, prefix, bodies):
    """Write both commit bodies into `root`'s object store; assert each sha
    git computes starts with `prefix` and that `cat-file -e <prefix>^{commit}`
    exits 128 saying `ambiguous` (the finding's premise, measured here)."""
    for body in bodies:
        done = subprocess.run(["git", "-C", str(root), "hash-object", "-t", "commit",
                               "-w", "--stdin"], input=body, capture_output=True, check=True)
        assert done.stdout.decode().strip().startswith(prefix), done.stdout
    probe = subprocess.run(["git", "-C", str(root), "cat-file", "-e", prefix + "^{commit}"],
                           capture_output=True, check=False)
    assert (probe.returncode, b"ambiguous" in probe.stderr) == (128, True), probe


def test_an_ambiguous_base_anchor_is_could_not_tell(tmp_path):
    prefix, bodies = ambiguous_commit_prefix()
    root, base = anchored_repo(tmp_path, map_anchor=prefix)
    _ambiguous_objects(root, prefix, bodies)
    re_anchor_map(root, "app", head_sha(root, 40))

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            "ambiguous" in reason) == (None, True, True), reason


def test_a_base_anchor_git_cannot_disambiguate_is_could_not_tell(tmp_path, monkeypatch):
    root, base = anchored_repo(tmp_path, map_anchor="deadbeefdead")
    re_anchor_map(root, "app", head_sha(root, 40))
    _failing_git(monkeypatch, "_git_lines", _args_are("rev-parse", "--disambiguate=deadbeefdead"),
                 None)

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            "names a commit" in reason) == (None, True, True), reason


def test_a_base_anchor_whose_candidates_git_cannot_type_is_could_not_tell(tmp_path, monkeypatch):
    prefix, bodies = ambiguous_commit_prefix()
    root, base = anchored_repo(tmp_path, map_anchor=prefix)
    _ambiguous_objects(root, prefix, bodies)
    re_anchor_map(root, "app", head_sha(root, 40))
    monkeypatch.setattr(crew_refresh_check, "_git_lines", _typing_fails(
        crew_refresh_check._git_lines))  # pylint: disable=protected-access

    verdict, reason = _verdict(root, base, REACH, APP)

    assert (verdict, reason.startswith(crew_refresh_check.COULD_NOT_TELL),
            "names a commit" in reason) == (None, True, True), reason


def _typing_fails(real):
    return lambda r, *a: None if a[:2] == ("cat-file", "-t") else real(r, *a)


def test_an_ambiguous_new_anchor_is_refused(tmp_path):
    """The neighbour (a control): the map re-anchored TO a prefix two commits
    share. `_sha_moved`'s own exit-128 branch must not admit it."""
    prefix, bodies = ambiguous_commit_prefix()
    root, base = anchored_repo(tmp_path)
    _ambiguous_objects(root, prefix, bodies)
    re_anchor_map(root, "app", prefix)

    verdict, reason = _verdict(root, base, REACH, APP)

    assert verdict is not True, reason


@pytest.mark.parametrize("ext", [".mmd", ".MMD"])
def test_a_rendered_diagram_beside_an_admitted_source_is_admitted_whatever_its_case(tmp_path, ext):
    """`_kind` judges `flow.MMD` a diagram source (its extension case-folded),
    so the rendered file beside it pairs with it the same way."""
    root, base = anchored_repo(tmp_path, diagram_ext=ext)
    head = head_sha(root, 40)
    source = FLOW[:-len(".mmd")] + ext
    re_anchor_diagram(root, "flow", head, ext=ext)
    write(root, RENDERED, f"<svg><!-- {head} --></svg>\n")

    got = _verdicts(root, base, REACH, [source, RENDERED])

    assert (got[source][0], got[RENDERED][0]) == (True, True), got


def test_a_rendered_diagram_whose_upper_case_source_was_not_re_anchored_is_refused(tmp_path):
    root, base = anchored_repo(tmp_path, diagram_ext=".MMD")
    write(root, RENDERED, "<svg><!-- redrawn by hand --></svg>\n")

    verdict, reason = _verdict(root, base, REACH, RENDERED)

    assert verdict is False, reason


def test_a_rendered_diagram_is_not_paired_with_another_stems_admitted_source(tmp_path):
    """The neighbour of the case-folded pairing: `other.svg` has no source,
    and the admitted `flow.mmd` beside it is not its pair."""
    other = "docs/diagrams/other.svg"
    root, base = anchored_repo(tmp_path, extra={other: "<svg><!-- base --></svg>\n"})
    head = head_sha(root, 40)
    re_anchor_diagram(root, "flow", head)
    write(root, other, f"<svg><!-- {head} --></svg>\n")

    got = _verdicts(root, base, REACH, [FLOW, other])

    assert (got[FLOW][0], got[other][0]) == (True, False), got

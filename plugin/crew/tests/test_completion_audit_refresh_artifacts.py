"""T-0008 review round 1 (BLOCK): the completion audit accepts the
refresh-artifact paths for an approved ticket, under exactly the condition the
scope guard does (`crew_ticket.accepted`: current, and from the user's prompt
unless `scope.allowCliApproval`). A BLOCKING hook, so must-block and
must-allow cases both.

T-0094 narrowed what the approval admits: a changed artifact passes without
Touch only when a path the ticket changed reaches it and the edit is a
re-anchor or a regeneration (`crew_refresh_check.artifact_verdicts`, unit-tested
in `test_refresh_admission.py`). So the must-allow half runs on
`refresh_fixtures.refreshed`, the shape `8bbb26d9` wrote in this repository,
and no longer on the bytes `refreshed` written over each artifact -- a map with
no anchor, a rule that is not `expected_rules` and a graph with no code change
are now must-block inputs, and the T-0094 block below asserts the audit names
the reason for each.

The fixtures un-ignore `.crew/codemap/` the way this repository's own
`.gitignore` does (`.crew/*` then `!.crew/codemap/`); without that, a codemap
write is invisible to git and to the audit, and the codemap cases would pass
while testing nothing.

`sabotage_refresh.py` drops the approval condition, and the unapproved, cli
and stale must-block cases go red; its `# T-0094` entries make the audit ignore the
verdicts or drop the reason, and the T-0094 must-block cases go red.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
import crew_refresh_check
import crew_ticket
from crew_fixtures import head_sha
from refresh_fixtures import (MAP, RULE, anchored_repo, map_text, read, rebuild_graph,
                              re_anchor_map, refreshed, write)
from review_fixtures import git
from scope_fixtures import SCRIPTS, FLAVOURS, make_repo, make_ticket, ready, run_hook, stop

APP = MAP.format(name="app")
APP_RULE = RULE.format(name="app")
ARTIFACTS = [".crew/codemap/crew.md", "docs/diagrams/architecture.mmd",
             "graphify-out/graph.json", ".claude/rules/crew.md"]


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = make_repo(tmp_path, mode="block")
    (root / ".gitignore").write_text(".work/\n.crew/*\n!.crew/codemap/\n", encoding="utf-8")
    git(root, "commit", "-qam", "un-ignore the code map")
    return root


def _write(repo, rel, text="refreshed\n"):
    path = repo.joinpath(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _refresh_everything(repo):
    for rel in ARTIFACTS:
        _write(repo, rel)


# --- must-block -----------------------------------------------------------------

# The three approval-gate cases perform a REAL refresh (T-0094): one that
# `artifact_verdicts` admits, so only the approval gate in
# `_outside_refresh_artifacts` keeps it listed -- a refresh the verdicts
# refuse anyway would stay listed with that gate removed, and the
# `_AUDIT_GATE` sabotage entries would survive.

def test_an_unapproved_ticket_cannot_leave_a_refresh_artifact_changed(tmp_path):
    root, _base = anchored_repo(tmp_path)
    os.remove(crew_ticket.approval_path(str(root), "T-1"))
    refreshed(root)

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, ".crew/codemap/app.md" in "\n".join(lines)) == (False, True), lines


def test_a_cli_approval_cannot_leave_a_refresh_artifact_changed(tmp_path):
    root, _base = anchored_repo(tmp_path)
    crew_ticket.approve(str(root), "T-1", by="session")
    refreshed(root)

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, "/crew:approve T-1" in "\n".join(lines),
            ".crew/codemap/app.md" in "\n".join(lines)) == (False, True, True), lines


def test_a_stale_approval_cannot_leave_a_refresh_artifact_changed(tmp_path):
    root, _base = anchored_repo(tmp_path)
    spec = root / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n- `other/**`\n", encoding="utf-8")
    refreshed(root)

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, "not approved" in lines[0],
            ".crew/codemap/app.md" in "\n".join(lines)) == (False, True, True), lines


def test_an_unapproved_ticket_is_never_judged_for_reach_or_shape(tmp_path, monkeypatch):
    """Review round 1 NIT: without a current approval nothing is admitted, so
    the verdicts are not computed at all."""
    root, _base = anchored_repo(tmp_path)
    os.remove(crew_ticket.approval_path(str(root), "T-1"))
    refreshed(root)
    calls = []
    monkeypatch.setattr(crew_refresh_check, "artifact_verdicts",
                        lambda *a, **k: calls.append(a) or {})

    completion_audit.audit(str(root), "T-1")

    assert calls == []


@pytest.mark.parametrize("rel", ["docs/diagrams-old/a.mmd", "graphify-outX/graph.json",
                                 ".claude/rulesX/crew.md", "other/.crew/codemap/crew.md"])
def test_a_path_that_only_prefix_matches_an_artifact_dir_is_out_of_scope(repo, rel):
    ready(repo)
    _write(repo, rel)

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, rel in "\n".join(lines)) == (False, True), lines


def test_a_rename_into_an_artifact_dir_still_judges_its_source(repo):
    ready(repo)
    (repo / ".crew" / "codemap").mkdir(parents=True)
    git(repo, "mv", "other/keep.py", ".crew/codemap/keep.py")

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, "other/keep.py" in "\n".join(lines)) == (False, True), lines


def test_an_artifact_beside_an_out_of_scope_change_still_fails(repo):
    ready(repo)
    _refresh_everything(repo)
    _write(repo, "other/keep.py", "x = 9\n")

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, "other/keep.py" in "\n".join(lines)) == (False, True), lines


# --- must-block: a refresh artifact of the wrong shape or reach (T-0094) ---------

def test_a_map_edited_without_moving_its_anchor_fails_the_audit(tmp_path):
    root, _base = anchored_repo(tmp_path)
    write(root, APP, read(root, APP).replace("x is one", "x is two"))

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, lines[0].startswith("COMPLETION AUDIT: 1 changed path(s) outside T-1's "
                                    "spec ## Touch"),
            ".crew/codemap/app.md [anchor did not move]" in lines[1]) == (False, True, True), lines


def test_a_refresh_that_no_changed_path_reaches_fails_the_audit(tmp_path):
    root, _base = anchored_repo(tmp_path)
    git(root, "revert", "--no-edit", "HEAD")
    write(root, "src/other.py", "y = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "ticket edit elsewhere")
    re_anchor_map(root, "app", head_sha(root, 40), cites=("src/app.py:1",))

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, "[no changed path reaches it]" in "\n".join(lines)) == (False, True), lines


def test_a_hand_edited_rule_fails_the_audit(tmp_path):
    root, _base = anchored_repo(tmp_path)
    write(root, APP_RULE, read(root, APP_RULE) + "- a hand-written landmine\n")

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, APP_RULE + " [bytes differ" in "\n".join(lines)) == (False, True), lines


def test_a_graph_rebuild_with_no_code_change_fails_the_audit(tmp_path):
    root, _base = anchored_repo(tmp_path, touch=("src/**", "docs/x.md"))
    git(root, "revert", "--no-edit", "HEAD")
    write(root, "docs/x.md", "prose\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs only")
    rebuild_graph(root, head_sha(root, 40))

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, "[graph changed with no code change" in "\n".join(lines)) == (False, True), lines


def test_a_could_not_tell_verdict_fails_the_audit_and_says_so(tmp_path, monkeypatch):
    root, _base = anchored_repo(tmp_path)
    re_anchor_map(root, "app", head_sha(root, 40))
    monkeypatch.setattr(crew_refresh_check, "_git_rc", lambda *a, **k: None)

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, "[could not tell:" in "\n".join(lines)) == (False, True), lines


def test_a_bookkeeping_bump_does_not_admit_a_rewrite_of_the_map_citing_it(tmp_path):
    """Review round 1: a ticket changing `src/app.py` and CHANGELOG.md rewrote
    another map citing CHANGELOG.md and moved its anchor, and was admitted."""
    rel = MAP.format(name="notes")
    root, _base = anchored_repo(tmp_path, touch=("src/**", "CHANGELOG.md"), extra={
        rel: map_text("notes", "deadbeefdead", ("CHANGELOG.md:1",), "the release notes")})
    write(root, "CHANGELOG.md", "# Changelog\n- 1.0.1\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "bump")
    refreshed(root)
    write(root, rel, map_text("notes", head_sha(root, 40), ("CHANGELOG.md:1",), "REWRITTEN"))

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, rel + " [no changed path reaches it]" in "\n".join(lines)) == (
        False, True), lines


@pytest.mark.parametrize("raises", ["refresh_artifact_paths", "artifact_verdicts"])
def test_a_verdict_step_that_raises_fails_the_audit_closed(tmp_path, monkeypatch, raises):
    """Review round 1 NIT: `--check` catches only TicketError, so a raise in
    the verdict step would escape as a traceback. It is could-not-tell:
    nothing admitted, and the audit still answers."""
    root, _base = anchored_repo(tmp_path)
    refreshed(root)

    def boom(*_a, **_k):
        raise RuntimeError("broke")

    monkeypatch.setattr(crew_refresh_check, raises, boom)

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, ".crew/codemap/app.md" in "\n".join(lines)) == (False, True), lines


def test_the_message_stays_inside_six_lines_with_many_refused_artifacts(tmp_path):
    root, _base = anchored_repo(tmp_path)
    for n in range(10):
        write(root, f".crew/codemap/m{n}.md", map_text(f"m{n}", None, ("src/app.py:1",), "x"))

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, len(completion_audit.physical(lines)), len(lines)) == (False, len(lines), 4), lines


def test_an_intermediate_stop_mid_refresh_is_told_the_anchor_did_not_move(tmp_path):
    root, _base = anchored_repo(tmp_path)
    write(root, APP, read(root, APP).replace("x is one", "x is two"))

    code, _out, err = run_hook("module", "completion_audit", stop(root), root)

    assert (code, "anchor did not move" in err) == (2, True), err


# --- must-allow -----------------------------------------------------------------

def _pass_lines(lines):
    """A pass: no lines -- or, once T-0100 lands, only its `merged main` lines."""
    return all(line.startswith("  merged main") for line in lines)


def test_an_approved_ticket_passes_with_a_real_refresh(tmp_path):
    root, _base = anchored_repo(tmp_path)
    refreshed(root)

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, _pass_lines(lines)) == (True, True), lines


def test_committed_refreshes_pass_too(tmp_path):
    root, _base = anchored_repo(tmp_path)
    refreshed(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "refresh the artifacts")

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, _pass_lines(lines)) == (True, True), lines


def test_a_cli_approval_passes_when_the_config_allows_it(repo):
    write(repo, APP, map_text("app", head_sha(repo, 40), ("src/app.py:1",), "x is one"))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a map, before the ticket starts")
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "block", "allowCliApproval": True}}), encoding="utf-8")
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="ci")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "scope_base.py"), "--root", str(repo),
                    "--record", "T-1"], check=True, capture_output=True, stdin=subprocess.DEVNULL)
    write(repo, "src/app.py", "x = 2\n")
    git(repo, "commit", "-qam", "ticket edit")
    re_anchor_map(repo, "app", head_sha(repo, 40))

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, _pass_lines(lines)) == (True, True), lines


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_stop_hook_lets_an_approved_refresh_through(flavour, tmp_path):
    root, _base = anchored_repo(tmp_path)
    refreshed(root)

    code, out, err = run_hook(flavour, "completion_audit", stop(root), root)

    assert (code, out, err) == (0, "", "")


def test_a_refused_artifact_named_in_touch_passes(tmp_path):
    root, _base = anchored_repo(tmp_path, touch=("src/**", ".crew/codemap/**"))
    write(root, APP, read(root, APP).replace("x is one", "x is two"))

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, _pass_lines(lines)) == (True, True), lines

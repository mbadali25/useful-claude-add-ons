"""T-0008 review round 1 (BLOCK): the completion audit accepts the
refresh-artifact paths for an approved ticket, under exactly the condition the
scope guard does (`crew_ticket.accepted`: current, and from the user's prompt
unless `scope.allowCliApproval`). A BLOCKING hook, so must-block and
must-allow cases both.

The fixture un-ignores `.crew/codemap/` the way this repository's own
`.gitignore` does (`.crew/*` then `!.crew/codemap/`); without that, a codemap
write is invisible to git and to the audit, and the codemap cases would pass
while testing nothing.

`sabotage_refresh.py` drops the approval condition, and the unapproved and
cli must-block cases go red.
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
import crew_ticket
from review_fixtures import git
from scope_fixtures import FLAVOURS, make_repo, make_ticket, ready, run_hook, stop

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

def test_an_unapproved_ticket_cannot_leave_a_refresh_artifact_changed(repo):
    make_ticket(repo)
    _write(repo, ".crew/codemap/crew.md")

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, ".crew/codemap/crew.md" in "\n".join(lines)) == (False, True), lines


def test_a_cli_approval_cannot_leave_a_refresh_artifact_changed(repo):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="session")
    _write(repo, ".crew/codemap/crew.md")

    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (ok, "/crew:approve T-1" in "\n".join(lines)) == (False, True), lines


def test_a_stale_approval_cannot_leave_a_refresh_artifact_changed(repo):
    ready(repo)
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n- `other/**`\n", encoding="utf-8")
    _write(repo, "docs/diagrams/architecture.mmd")

    ok, _ = completion_audit.audit(str(repo), "T-1")

    assert ok is False


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


# --- must-allow -----------------------------------------------------------------

@pytest.mark.parametrize("rel", ARTIFACTS)
def test_an_approved_ticket_passes_with_each_refresh_artifact_changed(repo, rel):
    ready(repo)
    _write(repo, rel)

    assert completion_audit.audit(str(repo), "T-1") == (True, [])


def test_committed_refreshes_pass_too(repo):
    ready(repo)
    _refresh_everything(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "refresh the artifacts")

    assert completion_audit.audit(str(repo), "T-1") == (True, [])


def test_a_cli_approval_passes_when_the_config_allows_it(repo):
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"mode": "block", "allowCliApproval": True}}), encoding="utf-8")
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="ci")
    _write(repo, ".crew/codemap/crew.md")

    assert completion_audit.audit(str(repo), "T-1") == (True, [])


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_stop_hook_lets_an_approved_refresh_through(flavour, repo):
    ready(repo)
    _refresh_everything(repo)

    code, out, err = run_hook(flavour, "completion_audit", stop(repo), repo)

    assert (code, out, err) == (0, "", "")

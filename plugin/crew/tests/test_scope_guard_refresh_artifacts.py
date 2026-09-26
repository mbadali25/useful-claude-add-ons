"""T-0008 review round 1 (BLOCK): the refresh-artifact allowance in the scope
guard. A BLOCKING hook, so must-block and must-allow cases both, through the
module and (as `slow`) the bash and PowerShell wrappers.

`/crew:implement` step 6 runs `/crew:onboard --refresh`, `/crew:diagram` and
`graphify update .`, which write `.crew/codemap/**`, the diagrams dir,
`graph.out` and `.claude/rules/**`. No ticket's Touch names those, so an
approved ticket may write them without naming them -- and ONLY an approved
ticket: the approval must be current and come from the user's prompt (a `cli`
receipt counts only with `scope.allowCliApproval`). The allowance matches
whole path segments (`.crew/codemapX` is not `.crew/codemap`), after `..` is
collapsed, on the real path and the named path both.

`sabotage_refresh.py` drops the approval condition, and the unapproved,
stale and cli must-block cases go red.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
import scope_guard
from scope_fixtures import FLAVOUR_MATRIX, FLAVOURS, edit, make_repo, make_ticket, ready, run_hook

ARTIFACTS = [".crew/codemap/crew.md", "docs/diagrams/architecture.mmd",
             "graphify-out/graph.json", ".claude/rules/crew.md"]


def _guard(flavour, root, payload):
    return run_hook(flavour, "scope_guard", payload, root)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _config(repo, **extra):
    data = {"scope": {"mode": "block"}}
    data.update(extra)
    (repo / ".crew" / "config.json").write_text(json.dumps(data), encoding="utf-8")


# --- must-block -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_unapproved_ticket_cannot_write_a_refresh_artifact(flavour, repo):
    make_ticket(repo)

    code, _, err = _guard(flavour, repo, edit(repo, repo / ".crew" / "codemap" / "crew.md"))

    assert (code, "no approved plan" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_stale_approval_cannot_write_a_refresh_artifact(flavour, repo):
    ready(repo)
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\n- `other/**`\n", encoding="utf-8")

    code, _, err = _guard(flavour, repo, edit(repo, repo / ".crew" / "codemap" / "crew.md"))

    assert (code, "spec.md changed since approval" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_cli_approval_cannot_write_a_refresh_artifact(flavour, repo):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="session")

    code, _, err = _guard(flavour, repo, edit(repo, repo / ".crew" / "codemap" / "crew.md"))

    assert (code, "/crew:approve T-1" in err) == (2, True)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("rel", [".crew/codemapX/crew.md", "docs/diagrams-old/a.mmd",
                                 "graphify-outX/graph.json", ".claude/rulesX/crew.md",
                                 "other/.crew/codemap/crew.md", ".crew/codemap"])
def test_a_path_that_only_prefix_matches_an_artifact_dir_is_blocked(flavour, repo, rel):
    ready(repo)

    code, _, err = _guard(flavour, repo, edit(repo, repo / rel))

    assert (code, "outside T-1's spec ## Touch" in err) == (2, True), err


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("rel", [".crew/codemap/../config.json",
                                 ".crew/codemap/../../other/keep.py",
                                 "docs/diagrams/../../other/keep.py"])
def test_dotdot_out_of_an_artifact_dir_is_blocked(flavour, repo, rel):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, rel))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_backslash_path_is_an_artifact_only_where_backslash_separates(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, ".crew\\codemap\\crew.md"))

    assert code == (0 if os.sep == "\\" else 2)


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_link_in_an_artifact_dir_pointing_out_of_scope_is_blocked(flavour, repo):
    ready(repo)
    (repo / ".crew" / "codemap").mkdir(parents=True)
    os.symlink(str(repo / "other"), str(repo / ".crew" / "codemap" / "link"))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".crew" / "codemap" / "link" / "keep.py"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_link_in_an_artifact_dir_pointing_out_of_the_worktree_is_blocked(flavour, repo,
                                                                            tmp_path):
    ready(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (repo / ".crew" / "codemap").mkdir(parents=True)
    os.symlink(str(elsewhere), str(repo / ".crew" / "codemap" / "out"))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".crew" / "codemap" / "out" / "x.md"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("rel", ["other/keep.py", ".crew/codemap/keep.py"])
def test_an_artifact_dir_that_is_itself_a_link_opens_nothing(flavour, repo, rel):
    ready(repo)
    os.symlink(str(repo / "other"), str(repo / ".crew" / "codemap"))

    code, _, _ = _guard(flavour, repo, edit(repo, repo / rel))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_configured_dir_replaces_the_default_rather_than_adding_to_it(flavour, repo):
    _config(repo, docs={"diagramsDir": "design/mmd"})
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "docs" / "diagrams" / "a.mmd"))

    assert code == 2


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_configured_dir_naming_the_repo_root_opens_nothing(flavour, repo):
    _config(repo, docs={"diagramsDir": "."}, graph={"out": "./"})
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / "other" / "keep.py"))

    assert code == 2


# --- must-allow -----------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
@pytest.mark.parametrize("rel", ARTIFACTS)
def test_an_approved_ticket_writes_each_refresh_artifact(flavour, repo, rel):
    ready(repo)

    code, out, err = _guard(flavour, repo, edit(repo, repo / rel))

    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_relative_artifact_path_is_allowed(flavour, repo):
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, ".crew/codemap/crew.md"))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
@pytest.mark.parametrize("rel", ["design/mmd/a.mmd", "out/graph/graph.json"])
def test_an_approved_ticket_writes_the_configured_dirs(flavour, repo, rel):
    _config(repo, docs={"diagramsDir": "design/mmd"}, graph={"out": "out/graph"})
    ready(repo)

    code, _, _ = _guard(flavour, repo, edit(repo, repo / rel))

    assert code == 0


@pytest.mark.parametrize("flavour", FLAVOUR_MATRIX)
def test_a_cli_approval_writes_artifacts_when_the_config_allows_it(flavour, repo):
    _config(repo, scope={"mode": "block", "allowCliApproval": True})
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", by="ci")

    code, _, _ = _guard(flavour, repo, edit(repo, repo / ".crew" / "codemap" / "crew.md"))

    assert code == 0


def test_an_absolute_path_into_another_repos_codemap_is_judged_as_outside_the_worktree(
        repo, tmp_path):
    other = make_repo(tmp_path, mode="block", name="other")
    approval = {"status": "none", "why": "no approval", "touch": []}
    target = str(other / ".crew" / "codemap" / "crew.md")

    verdict = scope_guard.classify(str(repo), crew_ticket.common_dir(str(repo)), "T-1", [],
                                   approval, target, str(repo))

    assert verdict == (True, "outside the worktree")

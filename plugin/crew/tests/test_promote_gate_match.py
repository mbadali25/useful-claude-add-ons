"""A command is a declared deploy only when it CONTAINS the declared text (L-0689).

Both promote gates also matched the reverse - a command that is a FRAGMENT of
a declared deploy - so `git rev-parse HEAD`, `HEAD` or `development` matched
`gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse
HEAD)`: on a clean tree the gate let it through and wrote
`.crew/.deploy-in-flight`, and the Stop gate then demanded a PROMOTIONS row
("DEPLOY NOT RECORDED") for a deploy that never ran. Reproduced on this branch
before the fix (development only declared: exit 0, marker `development
<sha>`; with production declared too, the fragment matched both and was
blocked as production).

The declared command run verbatim, with arguments after it, or wrapped
(`cd <dir> && <declared>`) is gated as before. The PowerShell flavour's two
sites use one literal, case-insensitive containment test. Both flavours run
every case (`ps1` slow, skipped without PowerShell 7).
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import test_promote_gate_effective_tree as tree
from test_promote_gate_effective_tree import _git

# L-0703: review evidence is opted out here; test_promote_gate_review.py owns
# the review rule.
_NO_REVIEW = {"requireReview": False, "reviewReason": "fixture"}

DEV = "gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)"
PROD = "gh workflow run deploy.yml -f environment=production -f ref=$(git rev-parse HEAD)"
MAP = {"environments": {
    "development": {"deploy": DEV, "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW},
    "production": {"deploy": PROD, "requires": ["development"],
                   "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW},
}}


def _write(repo, doc, commit=True):
    (repo.main / ".crew" / "verify.json").write_text(json.dumps(doc, indent=2) + "\n",
                                                     encoding="utf-8")
    if commit:
        _git(repo.main, "add", "-A")
        _git(repo.main, "commit", "-q", "-m", "match map")
        repo.main_sha = _git(repo.main, "rev-parse", "--short", "HEAD")
        repo.main_full = _git(repo.main, "rev-parse", "HEAD")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    made = tree.Repo(tmp_path)
    _write(made, MAP)
    return made


_FRAGMENTS = ["git rev-parse HEAD", "HEAD", "development", "echo development",
              "gh workflow run", "gh workflow run --help", "gh workflow run deploy.yml",
              "-f environment=development"]


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("command", _FRAGMENTS)
def test_a_fragment_of_a_declared_deploy_is_not_a_deploy_must_allow(flavour, command, repo):
    """must-allow: no in-flight marker, and exit 0 - except the two
    dispatch-shaped fragments, which T-0062's dispatch reader (it runs when
    containment matches nothing) reads as could-not-tell: `gh workflow run`
    names no workflow (gh would prompt for one) and `gh workflow run
    deploy.yml` fits no declared environment. Those block as could-not-tell,
    never as a deploy of development; the spec's must-allow list predates
    T-0062's reader."""
    code, err = tree.run_gate(flavour, repo, command)
    if command in ("gh workflow run", "gh workflow run deploy.yml"):
        assert code == 2 and "could not tell" in err, err
        assert "(development" not in err, err
    else:
        assert code == 0, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_a_fragment_with_the_map_dirty_matches_nothing_committed(flavour, repo):
    """must-allow, committed-map site: with an uncommitted edit renaming the
    deploy, `git rev-parse HEAD` still matches neither map."""
    doc = json.loads(json.dumps(MAP))
    doc["environments"]["development"]["deploy"] = "./deploy-dev.sh"
    _write(repo, doc, commit=False)
    code, err = tree.run_gate(flavour, repo, "git rev-parse HEAD")
    assert code == 0, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_the_production_deploy_verbatim_must_block(flavour, repo):
    code, err = tree.run_gate(flavour, repo, PROD)
    assert code == 2, err
    assert "PROMOTION BLOCKED (production" in err and "'development' has no all-pass row" in err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("form", ["verbatim", "extra-args", "wrapped"])
def test_the_declared_deploy_is_still_gated(flavour, form, repo):
    """The declared text verbatim, with ` --verbose` after it, or as
    `cd <worktree> && <declared>`: allowed, the marker names development."""
    command = {"verbatim": DEV, "extra-args": DEV + " --verbose",
               "wrapped": tree._cd(flavour, repo.main) + DEV}[form]  # pylint: disable=protected-access
    code, err = tree.run_gate(flavour, repo, command)
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.main_sha}"


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("deploy,command", [
    ("gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'",
     "gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
     "-f 'inputs[environment]=production'"),
    ("Deploy-App prod", "deploy-app prod"),
], ids=["brackets", "case"])
def test_a_literal_case_insensitive_match(flavour, deploy, command, tmp_path):
    """U3: brackets in a declared deploy are text, and case is ignored: the
    command matches its own declared text and the unmet `requires` blocks."""
    repo = tree.Repo(tmp_path)
    _write(repo, {"environments": {
        "development": {"deploy": "deploy-dev", "rollback": "none", "rollbackReason": "f", **_NO_REVIEW},
        "production": {"deploy": deploy, "requires": ["development"],
                       "rollback": "none", "rollbackReason": "f", **_NO_REVIEW}}})
    code, err = tree.run_gate(flavour, repo, command)
    assert code == 2, err
    assert "PROMOTION BLOCKED (production" in err, err

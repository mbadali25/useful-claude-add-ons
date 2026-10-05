"""promote-gate.sh treats a workflow dispatch of a declared deploy workflow as
that deploy, in either spelling (T-0062).

Before this, a command was a deploy only when it and a declared `deploy`
string contained one another. The same workflow dispatch spelled `gh api -X
POST repos/<o>/<r>/actions/workflows/<wf>/dispatches -f
'inputs[environment]=...'` -- or `gh workflow run <wf>` with its inputs
reordered -- matched nothing and exited 0 with no check at all. Now, when
containment matches nothing and the map declares a dispatch deploy, the
command is read with T-0009's dispatch reader (`crew_dispatch.dispatch_read`)
through `_promote_dispatch.py`.

This is a guard that can BLOCK, so the suite carries both directions (repo
CLAUDE.md, "Adding a hook"); `promote_tree_mutations.py` holds the mutations
that must turn named cases here red. Every repository is built under
`tmp_path` and `CLAUDE_PROJECT_DIR` points at it. The PowerShell flavour is
L-0664's; this file runs the Bash one.
"""
import json
import shutil

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import test_promote_gate_effective_tree as tree
from test_promote_gate_effective_tree import _git, run_gate

pytestmark = pytest.mark.skipif(tree._BASH is None,  # pylint: disable=protected-access
                                reason="no MSYS/POSIX bash")

DEV = "gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)"
PROD = "gh workflow run deploy.yml -f environment=production -f ref=$(git rev-parse HEAD)"
MAP = {"environments": {
    "dev": {"deploy": DEV, "rollback": "none", "rollbackReason": "fixture"},
    "prod": {"deploy": PROD, "requires": ["dev"], "requireHuman": True,
             "rollback": "none", "rollbackReason": "fixture"},
}}
REST = ("gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
        "-f ref=main -f 'inputs[environment]={env}'")
CNT = "could not tell"


def _write_map(repo, doc, commit=True):
    (repo.main / ".crew" / "verify.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if commit:
        _git(repo.main, "add", "-A")
        _git(repo.main, "commit", "-q", "-m", "dispatch map")
        repo.main_sha = _git(repo.main, "rev-parse", "--short", "HEAD")
        repo.main_full = _git(repo.main, "rev-parse", "HEAD")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    made = tree.Repo(tmp_path)
    _write_map(made, MAP)
    return made


def gate(repo, command):
    return run_gate("sh", repo, command)


def _approve(repo, env):
    (repo.main / ".crew" / f".approved-{env}-{repo.main_sha}").write_text(
        "", encoding="utf-8")


# --- must-block -------------------------------------------------------------

def test_the_rest_spelling_of_a_prod_deploy_is_gated(repo):
    """The direction's bypass: the REST spelling, no dev PASS row, no
    marker. It used to match nothing and exit 0."""
    code, err = gate(repo, REST.format(env="production"))
    assert code == 2, err
    assert "PROMOTION BLOCKED (prod" in err
    assert "'dev' has no all-pass row" in err
    assert repo.in_flight() is None


def test_the_rest_spelling_from_a_dirty_tree_blocks_as_dirty(repo):
    repo.dirty_main()
    code, err = gate(repo, REST.format(env="development"))
    assert code == 2, err
    assert "dirty" in err and "(dev" in err


def test_reordered_inputs_still_reach_the_environment(repo):
    """Containment misses `-f ref=<sha>` before `-f environment=...`."""
    code, err = gate(repo, "gh workflow run deploy.yml "
                     f"-f ref={repo.main_full} -f environment=production")
    assert code == 2, err
    assert "PROMOTION BLOCKED (prod" in err


def test_a_quoted_ref_input_that_is_not_head_blocks(repo):
    """U5: `_promote_tree.py` reads the sha inside `'inputs[ref]=<sha>'`."""
    code, err = gate(repo, REST.format(env="development")
                     + f" -f 'inputs[ref]={repo.wt_full}'")
    assert code == 2, err
    assert f"names commit '{repo.wt_full}'" in err


@pytest.mark.parametrize("command", [
    "gh workflow run deploy.yml -f environment=$E",
    'gh workflow run deploy.yml -f "environment=production"',
    "gh workflow run deploy.yml -f environment=production --json",
    "gh workflow run deploy.yml --input body.json",
    "gh api -X POST repos/o/r/actions/workflows/deploy.yml/dispatches "
    "-F 'inputs[environment]=@f'",
    "echo gh workflow run deploy.yml -f environment=production | bash",
    "gh workflow run 12345",
    "gh workflow run 'Deploy'",
    "gh api repos/o/r/actions/workflows/$WF/dispatches -f x=y",
])
def test_a_dispatch_the_gate_cannot_read_is_could_not_tell(repo, command):
    """Each blocks before any precondition: the tree is dirty on purpose,
    and the reason is never "dirty"."""
    repo.dirty_main()
    code, err = gate(repo, command)
    assert code == 2, err
    assert CNT in err
    assert "dirty" not in err and "all-pass row" not in err
    assert repo.in_flight() is None


def test_a_declared_workflow_fitting_no_environment_blocks(repo):
    code, err = gate(repo, "gh workflow run deploy.yml -f environment=staging")
    assert code == 2, err
    assert "fits no declared environment" in err


def test_a_declared_workflow_fitting_two_environments_blocks(repo):
    doc = json.loads(json.dumps(MAP))
    doc["environments"]["qa"] = {"deploy": "gh workflow run deploy.yml",
                                 "rollback": "none", "rollbackReason": "fixture"}
    _write_map(repo, doc)
    code, err = gate(repo, REST.format(env="production"))
    assert code == 2, err
    assert "more than one declared environment (prod, qa)" in err


def test_a_dispatch_deploy_removed_from_the_working_map_still_matches(repo):
    """The committed map's declared dispatches are matched too, so an
    uncommitted edit cannot make the REST line match nothing."""
    doc = json.loads(json.dumps(MAP))
    doc["environments"]["dev"]["deploy"] = "./deploy-dev.sh"
    _write_map(repo, doc, commit=False)
    code, err = gate(repo, REST.format(env="development"))
    assert code == 2, err
    assert "uncommitted changes" in err and "(dev" in err


def test_the_helper_failing_blocks(repo, tmp_path, monkeypatch):
    """A helper that crashes is never "not a deploy"."""
    scripts = tmp_path / "scripts-copy"
    shutil.copytree(tree._SH.parent, scripts)  # pylint: disable=protected-access
    (scripts / "_promote_dispatch.py").write_text(
        "raise SystemExit('boom')\n", encoding="utf-8")
    monkeypatch.setattr(tree, "_SH", scripts / "promote-gate.sh")
    code, err = gate(repo, REST.format(env="development"))
    assert code == 2, err
    assert "This is not a pass" in err
    assert repo.in_flight() is None


# --- must-allow -------------------------------------------------------------

def test_the_rest_spelling_of_a_dev_deploy_runs(repo):
    code, err = gate(repo, REST.format(env="development"))
    assert code == 0, err
    assert repo.in_flight() == f"dev {repo.main_sha}"


def test_the_rest_spelling_of_prod_runs_with_its_preconditions_met(repo):
    repo.promotions(("dev", repo.main_sha))
    _approve(repo, "prod")
    code, err = gate(repo, REST.format(env="production"))
    assert code == 0, err
    assert repo.in_flight() == f"prod {repo.main_sha}"


@pytest.mark.parametrize("command", [
    "gh workflow run ci.yml",
    "gh api repos/o/r/actions/workflows/ci.yml/dispatches -f ref=main",
    "gh api repos/o/r/actions/workflows/deploy.yml/runs",
    "gh workflow run deploy.yml --help",
    'gh pr create --title "$T"',
    "echo done",
])
def test_a_command_that_is_no_declared_dispatch_passes_untouched(repo, command):
    code, err = gate(repo, command)
    assert code == 0, err
    assert err == ""
    assert repo.in_flight() is None


def test_a_map_with_no_dispatch_deploy_sees_no_new_refusal(tmp_path):
    """U4's limit: repos that declare no dispatch deploy see no change."""
    repo = tree.Repo(tmp_path)
    code, err = gate(repo, "gh workflow run x.yml -f a=$B")
    assert code == 0, err
    assert repo.in_flight() is None


def test_an_open_incident_records_the_block_and_exits_0(repo):
    (repo.main / ".crew" / "incident.json").write_text(
        json.dumps({"expiresAtEpoch": 4102444800}), encoding="utf-8")
    code, err = gate(repo, "gh workflow run deploy.yml -f environment=$E")
    assert code == 0, err
    log = (repo.main / ".crew" / "incident-skips.log").read_text(encoding="utf-8")
    assert "workflow dispatch" in log and CNT in log

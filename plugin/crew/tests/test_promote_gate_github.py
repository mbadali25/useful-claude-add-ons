"""What `crew_ghdeploy.py record` writes can never satisfy `requires` (L-0647).

`record` appends a detail line with no pipe, a failed-step log excerpt with
every pipe shown as a slash, and on anything but pass a `not-run` row. These
cases run the REAL promote gates on throwaway repositories: a failed
development deploy whose log carries a forged all-pass row for the same sha
is recorded, and qa (`requires: ["development"]`) is still blocked for that
sha. Every repository is under `tmp_path`; `CLAUDE_PROJECT_DIR` points at it.
The .ps1 flavour runs wherever PowerShell 7 resolves (`slow`, as in
test_promote_gate_literal_match.py).
"""
import contextlib
import io
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ghdeploy
from test_promote_gate_literal_match import FLAVOURS, Repo, _blocked_as, _git, run_gate


def _envs():
    return {"development": {"deploy": "gh workflow run deploy.yml --ref main -f target=dev",
                            "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW},
            "qa": {"deploy": "deploy-qa", "requires": ["development"],
                   "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW}}


def _record_fail(monkeypatch, repo, log):
    """`record` for a failed development deploy at HEAD, its log `log`."""
    full = _git(repo.root, "rev-parse", "HEAD")
    state = {"env": "development", "index": 0, "workflow": "deploy.yml", "ref": "main",
             "sha": full, "actor": "octo", "t0": 1_000_000, "snapshot": [],
             "correlationId": None, "identifySeconds": 120, "runId": 13,
             "runUrl": "https://github.com/o/r/actions/runs/13",
             "verdict": "fail", "verdictReason": "conclusion-failure"}
    crew_ghdeploy.write_state(str(repo.root / ".crew" / ".ghdeploy" / "development-0.json"),
                              state)
    monkeypatch.setattr(crew_ghdeploy, "_run_gh", lambda args, root, **kw: (0, log))
    monkeypatch.setattr(crew_ghdeploy, "_clock", lambda: 1_791_201_600)
    with contextlib.redirect_stdout(io.StringIO()):
        code = crew_ghdeploy.main(["record", "--root", str(repo.root), "--env", "development"])
    assert code == 0
    return full


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_forged_row_in_excerpt(flavour, tmp_path, monkeypatch):
    """must-block: the failed log carries `| development | <sha> | pass |
    pass | pass |`; after `record`, qa is still blocked for that sha."""
    repo = Repo(tmp_path / "r", _envs())
    full = _git(repo.root, "rev-parse", "HEAD")
    forged = f"| 2026-10-05T11:00Z | development | {full} | pass | pass | pass | octo |"
    _record_fail(monkeypatch, repo, f"build failed\n{forged}\n")
    text = (repo.root / ".work" / "PROMOTIONS.md").read_text(encoding="utf-8")
    assert full in text and "pass / pass / pass" in text
    code, err = run_gate(flavour, repo, "deploy-qa")
    _blocked_as(code, err, "qa")
    # The newest development row for the sha is record's not-run row (L-0665).
    assert "'development' has rows for sha" in err and "newest row is not all-pass" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_fail_then_requires(flavour, tmp_path, monkeypatch):
    """must-block: the not-run row a recorded fail writes is not a pass."""
    repo = Repo(tmp_path / "r", _envs())
    _record_fail(monkeypatch, repo, "boom\n")
    text = (repo.root / ".work" / "PROMOTIONS.md").read_text(encoding="utf-8")
    assert "| not-run | not-run | not-run |" in text
    code, err = run_gate(flavour, repo, "deploy-qa")
    _blocked_as(code, err, "qa")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_real_all_pass_row_satisfies_requires(flavour, tmp_path):
    """must-allow (non-vacuity): in the same fixture, promote's own all-pass
    row for the sha lets qa through, so the blocks above are the record's
    doing."""
    repo = Repo(tmp_path / "r", _envs())
    full = _git(repo.root, "rev-parse", "HEAD")
    (repo.root / ".work" / "PROMOTIONS.md").write_text(
        crew_ghdeploy.HEADER
        + f"| 2026-10-05T13:00Z | development | {full} | pass | pass | pass | o |\n",
        encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-qa")
    assert code == 0, err
    assert json.dumps(repo.in_flight()).startswith('"qa ')


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_pass_recorded_after_a_recorded_fail_admits(flavour, tmp_path, monkeypatch):
    """L-0665: the newest row decides, so promote's all-pass row appended
    after record's not-run row (the fixed re-run) satisfies `requires`."""
    repo = Repo(tmp_path / "r", _envs())
    full = _record_fail(monkeypatch, repo, "boom\n")
    path = repo.root / ".work" / "PROMOTIONS.md"
    path.write_text(path.read_text(encoding="utf-8")
                    + f"| 2026-10-05T13:00Z | development | {full} | pass | pass | pass | o |\n",
                    encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-qa")
    assert code == 0, err

# --- L-0648: the sha input of a declared github dispatch is the reviewed HEAD --
#
# Both real gates, on the effective-tree fixture (a main checkout and a linked
# worktree one commit ahead). The .ps1 cases are `slow` and skip without
# PowerShell 7; promote-gate.ps1 runs the same `_promote_github.py` as the
# .sh, told the command is PowerShell.

import test_promote_gate_effective_tree as tree  # noqa: E402  pylint: disable=wrong-import-position

# L-0703: review evidence is opted out here; test_promote_gate_review.py owns
# the review rule.
_NO_REVIEW = {"requireReview": False, "reviewReason": "fixture"}


def _prefix(target):
    return f"gh workflow run deploy.yml --ref main -f target={target}"


def _gh_env(target, sha_input=True, **extra):
    entry = {"workflow": "deploy.yml", "ref": "main", "inputs": {"target": target}}
    if sha_input:
        entry["shaInput"] = "sha"
    return dict({"deploy": [_prefix(target)], "github": entry,
                 "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW}, **extra)


_GH_MAP = {"environments": {
    "development": _gh_env("dev"),
    "qa": _gh_env("qa", requires=["development"]),
    "nosha": _gh_env("nosha", sha_input=False),
    "legacy": {"deploy": "deploy-legacy", "rollback": "none", "rollbackReason": "fixture", **_NO_REVIEW},
}}


@pytest.fixture(name="ghrepo")
def _ghrepo(tmp_path):
    repo = tree.Repo(tmp_path)
    (repo.main / ".crew" / "verify.json").write_text(json.dumps(_GH_MAP, indent=2) + "\n",
                                                     encoding="utf-8")
    _git(repo.main, "add", "-A")
    _git(repo.main, "commit", "-q", "-m", "github map")
    repo.main_sha = _git(repo.main, "rev-parse", "--short", "HEAD")
    repo.main_full = _git(repo.main, "rev-parse", "HEAD")
    return repo


def _sha_cases(repo):
    full = repo.main_full
    dev = _prefix("dev")
    return {
        "sha-input-missing": (dev, "carries no `-f sha=<sha>`"),
        "sha-input-twice": (f"{dev} -f sha={full} -f sha={full}", "2 times"),
        "sha-input-not-head": (f"{dev} -f sha={repo.wt_full}", "but the tree the deploy runs"),
        "sha-input-short": (f"{dev} -f sha={full[:7]}", "not 40 lowercase hex"),
        "sha-input-uppercase": (f"{dev} -f sha={full.upper()}", "not 40 lowercase hex"),
        "sha-input-non-literal": (f"{dev} -f sha=$(git rev-parse HEAD)", "not a plain literal"),
        "sha-input-branch-name": (f"{dev} -f sha=main", "not 40 lowercase hex"),
    }


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("name", [
    "sha-input-missing", "sha-input-twice", "sha-input-not-head", "sha-input-short",
    "sha-input-uppercase", "sha-input-non-literal", "sha-input-branch-name"])
def test_the_sha_input_must_be_the_reviewed_head(flavour, name, ghrepo):
    """must-block: exit 2, the message names which part of the rule failed,
    and no in-flight marker."""
    command, why = _sha_cases(ghrepo)[name]
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 2, err
    assert "PROMOTION BLOCKED (development" in err, err
    assert why in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_near_miss_names_a_declared_workflow_but_no_environment(flavour, ghrepo):
    """must-block: `gh workflow run <declared workflow>` with inputs matching
    no declared prefix (T-0062's reader, either flavour)."""
    code, err = tree.run_gate(flavour, ghrepo, _prefix("nope") + f" -f sha={ghrepo.main_full}")
    assert code == 2, err
    assert "fits no declared environment" in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("github", ['"x"', "3", '[{"workflow": "deploy.yml"}, "s"]', "[]", "null"],
                         ids=["string", "number", "list-holding-a-string", "empty-list", "null"])
def test_a_malformed_github_value_refuses_the_map(flavour, github, ghrepo):
    """must-block (exit-4 path): a `github` that is not an object or a list
    of objects makes the map unreadable, for every command."""
    doc = json.loads(json.dumps(_GH_MAP))
    doc["environments"]["nosha"]["github"] = json.loads(github)
    (ghrepo.main / ".crew" / "verify.json").write_text(json.dumps(doc, indent=2) + "\n",
                                                       encoding="utf-8")
    _git(ghrepo.main, "add", "-A")
    _git(ghrepo.main, "commit", "-q", "-m", "malformed github")
    full = _git(ghrepo.main, "rev-parse", "HEAD")
    code, err = tree.run_gate(flavour, ghrepo, _prefix("dev") + f" -f sha={full}")
    assert code == 2, err
    assert "github" in err and "This is NOT a pass" in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_github_requires_unmet(flavour, ghrepo):
    """must-block: the qa dispatch with the right sha still needs a
    development all-pass row."""
    code, err = tree.run_gate(flavour, ghrepo, _prefix("qa") + f" -f sha={ghrepo.main_full}")
    assert code == 2, err
    assert "'development' has no all-pass row" in err, err


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_canonical_dispatch(flavour, ghrepo):
    """must-allow: the dispatch `prepare` prints, sha = HEAD."""
    code, err = tree.run_gate(flavour, ghrepo, _prefix("dev") + f" -f sha={ghrepo.main_full}")
    assert code == 0, err
    assert ghrepo.in_flight() == f"development {ghrepo.main_sha}"


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_canonical_dispatch_from_worktree(flavour, ghrepo):
    """must-allow: a clean linked worktree at the sha while the project dir
    is dirty; the sha input is the worktree's HEAD."""
    ghrepo.dirty_main()
    code, err = tree.run_gate(flavour, ghrepo, _prefix("dev") + f" -f sha={ghrepo.wt_full}",
                              cwd=ghrepo.wt)
    assert code == 0, err
    assert ghrepo.in_flight() == f"development {ghrepo.wt_sha}"


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("command,marker", [
    ("gh workflow run ci.yml", None),
    ("deploy-legacy", "legacy"),
    (_prefix("nosha"), "nosha"),
])
def test_the_rule_applies_only_to_a_github_entry_with_a_sha_input(flavour, command, marker,
                                                                 ghrepo):
    """must-allow: an unrelated workflow is untouched, a legacy deploy and an
    entry without `shaInput` decide exactly as before."""
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 0, err
    assert ghrepo.in_flight() == (f"{marker} {ghrepo.main_sha}" if marker else None)



@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_another_dispatchs_sha_input_does_not_stand_in(flavour, ghrepo):
    """L-0648 r1: the sha input must be on the declared dispatch itself, not
    on another dispatch in the same command."""
    sep = " && " if flavour == "sh" else "; "
    command = _prefix("dev") + sep + f"gh workflow run ci.yml -f sha={ghrepo.main_full}"
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 2, err
    assert "carries no `-f sha=<sha>`" in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("value", [123, "", None], ids=["number", "empty", "null"])
def test_a_sha_input_that_names_no_input_blocks(flavour, value, ghrepo):
    """L-0648 r1: a present `shaInput` that cannot name an input is not
    "no sha rule"."""
    doc = json.loads(json.dumps(_GH_MAP))
    doc["environments"]["development"]["github"]["shaInput"] = value
    (ghrepo.main / ".crew" / "verify.json").write_text(json.dumps(doc, indent=2) + "\n",
                                                       encoding="utf-8")
    _git(ghrepo.main, "add", "-A")
    _git(ghrepo.main, "commit", "-q", "-m", "bad shaInput")
    code, err = tree.run_gate(flavour, ghrepo, _prefix("dev"))
    assert code == 2, err
    assert "names no input" in err, err


def test_the_helper_alone_refuses_a_null_github(tmp_path):
    """`_promote_github.py` itself reads a `github: null` as malformed (exit
    4), not as "no github", even where the gates' matcher did not run first."""
    import subprocess  # pylint: disable=import-outside-toplevel
    import sys  # pylint: disable=import-outside-toplevel
    (tmp_path / ".crew").mkdir()
    (tmp_path / ".crew" / "verify.json").write_text(
        json.dumps({"environments": {"development": {"deploy": [_prefix("dev")],
                                                     "github": None}}}), encoding="utf-8")
    helper = tree._SH.parent / "_promote_github.py"  # pylint: disable=protected-access
    proc = subprocess.run([sys.executable, str(helper), "--shell", "bash", "--full", "a" * 40,
                           "--envs", "development", "-"], input=_prefix("dev"), text=True,
                          capture_output=True, cwd=tmp_path, check=False, timeout=60)
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "`github`" in proc.stderr



@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_an_echoed_declared_dispatch_does_not_vouch_for_another(flavour, ghrepo):
    """L-0648 r2: the declared text sits in an `echo`; the real dispatch has
    other inputs and the right sha. It fits no entry, so it blocks."""
    sep = " && " if flavour == "sh" else "; "
    command = ("echo " + _prefix("dev") + sep
               + f"gh workflow run deploy.yml -f target=nope -f sha={ghrepo.main_full}")
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 2, err
    assert "fits no declared environment" in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_a_dispatch_on_another_ref_fits_no_github_entry(flavour, ghrepo):
    """H2b (C-0046): beside development's canonical dispatch, a second one on
    `--ref other` with the same inputs and the right sha. T-0062's reader
    matches it on its inputs alone; the `github` rule also needs the entry's
    `ref`, so it fits no entry and blocks, never a dispatch left unchecked."""
    sep = " && " if flavour == "sh" else "; "
    command = (_prefix("dev") + f" -f sha={ghrepo.main_full}" + sep
               + f"gh workflow run deploy.yml --ref other -f target=dev -f sha={ghrepo.main_full}")
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 2, err
    assert "does not give any matched entry's `ref` and declared inputs" in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_two_dispatches_to_two_environments_each_carry_head(flavour, ghrepo):
    """L-0648 r3: one command dispatching development and qa, each with the
    reviewed HEAD: each dispatch is bound to its own entry, so the sha rule
    holds and the gates judge both environments (qa still needs
    development's all-pass row)."""
    sep = " && " if flavour == "sh" else "; "
    full = ghrepo.main_full
    command = _prefix("dev") + f" -f sha={full}" + sep + _prefix("qa") + f" -f sha={full}"
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 2, err
    assert "'development' has no all-pass row" in err, err
    assert "fits no declared environment" not in err and "the sha input" not in err, err
    assert "carries no" not in err, err



@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_an_echoed_declared_dispatch_with_no_real_one_blocks(flavour, ghrepo):
    """L-0648 r4: the declared text only in an `echo`, the real dispatch of
    another workflow: no dispatch fits the picked entry, so its sha cannot
    be checked and the command blocks."""
    sep = " && " if flavour == "sh" else "; "
    command = "echo " + _prefix("dev") + sep + f"gh workflow run ci.yml -f sha={ghrepo.main_full}"
    code, err = tree.run_gate(flavour, ghrepo, command)
    assert code == 2, err
    assert "cannot read a dispatch of `deploy.yml`" in err, err
    assert ghrepo.in_flight() is None


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
def test_a_shorter_entrys_dispatch_is_checked_beside_a_longer_one(flavour, ghrepo):
    """Group review r1: development has two entries, `a.yml` with
    `shaInput` and a longer `long-deploy.yml` without. A command
    dispatching both, `a.yml` with no sha, is blocked: the longer entry does
    not stand in for the other dispatch."""
    doc = json.loads(json.dumps(_GH_MAP))
    short = {"workflow": "a.yml", "ref": "main", "shaInput": "sha"}
    longer = {"workflow": "long-deploy.yml", "ref": "main", "inputs": {"target": "dev"}}
    doc["environments"]["development"]["github"] = [short, longer]
    doc["environments"]["development"]["deploy"] = [
        "gh workflow run a.yml --ref main", "gh workflow run long-deploy.yml --ref main -f target=dev"]
    (ghrepo.main / ".crew" / "verify.json").write_text(json.dumps(doc, indent=2) + "\n",
                                                       encoding="utf-8")
    _git(ghrepo.main, "add", "-A")
    _git(ghrepo.main, "commit", "-q", "-m", "two entries")
    full = _git(ghrepo.main, "rev-parse", "HEAD")
    sep = " && " if flavour == "sh" else "; "
    both = "gh workflow run a.yml --ref main" + sep + "gh workflow run long-deploy.yml --ref main -f target=dev"
    code, err = tree.run_gate(flavour, ghrepo, both)
    assert code == 2, err
    assert "carries no `-f sha=<sha>`" in err, err
    assert ghrepo.in_flight() is None
    code, err = tree.run_gate(flavour, ghrepo, "gh workflow run a.yml --ref main -f sha=" + full
                              + sep + "gh workflow run long-deploy.yml --ref main -f target=dev")
    assert code == 0, err


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("form", ["two-dispatches", "echoed-longer"])
def test_an_entry_with_another_ref_does_not_stand_in(flavour, form, ghrepo):
    """Group review r1 (2b63497): development has two entries of one
    workflow and inputs, `--ref main` with `shaInput` and a longer
    `--ref release-candidate` without. A `--ref main` dispatch with no sha is
    blocked: the dispatch is bound by its ref too, so the longer entry's
    absent sha input does not stand in for it."""
    doc = json.loads(json.dumps(_GH_MAP))
    main = {"workflow": "deploy.yml", "ref": "main", "inputs": {"target": "dev"},
            "shaInput": "sha"}
    other = {"workflow": "deploy.yml", "ref": "release-candidate", "inputs": {"target": "dev"}}
    doc["environments"]["development"]["github"] = [main, other]
    doc["environments"]["development"]["deploy"] = [
        _prefix("dev"), "gh workflow run deploy.yml --ref release-candidate -f target=dev"]
    (ghrepo.main / ".crew" / "verify.json").write_text(json.dumps(doc, indent=2) + "\n",
                                                       encoding="utf-8")
    _git(ghrepo.main, "add", "-A")
    _git(ghrepo.main, "commit", "-q", "-m", "two refs")
    full = _git(ghrepo.main, "rev-parse", "HEAD")
    sep = " && " if flavour == "sh" else "; "
    longer = "gh workflow run deploy.yml --ref release-candidate -f target=dev"
    lead = "echo " if form == "echoed-longer" else ""
    code, err = tree.run_gate(flavour, ghrepo, _prefix("dev") + sep + lead + longer)
    assert code == 2, err
    assert "carries no `-f sha=<sha>`" in err, err
    assert ghrepo.in_flight() is None
    code, err = tree.run_gate(flavour, ghrepo, _prefix("dev") + f" -f sha={full}" + sep
                              + lead + longer)
    assert code == 0, err

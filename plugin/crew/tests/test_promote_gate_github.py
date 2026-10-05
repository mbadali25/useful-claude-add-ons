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
                            "rollback": "none", "rollbackReason": "fixture"},
            "qa": {"deploy": "deploy-qa", "requires": ["development"],
                   "rollback": "none", "rollbackReason": "fixture"}}


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
    assert "'development' has no all-pass row" in err, err


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
    doing. (After a recorded fail, a later pass row for the same sha is
    shadowed by the not-run row: promote-gate's first-row `passed()`, which
    this ticket does not change.)"""
    repo = Repo(tmp_path / "r", _envs())
    full = _git(repo.root, "rev-parse", "HEAD")
    (repo.root / ".work" / "PROMOTIONS.md").write_text(
        crew_ghdeploy.HEADER
        + f"| 2026-10-05T13:00Z | development | {full} | pass | pass | pass | o |\n",
        encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-qa")
    assert code == 0, err
    assert json.dumps(repo.in_flight()).startswith('"qa ')

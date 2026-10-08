"""promote-gate reads the NEWEST PROMOTIONS.md row for an environment and sha (L-0665).

Both flavours used to return on the FIRST row matching the upstream
environment and the sha prefix, so a failure followed by a fixed re-run stayed
blocked forever, and a pass followed by a later failure still admitted the
deploy. Rows are appended, so file order is time order: the newest row
decides. This is a guard that can block, so the table holds both directions,
run through both real gates (`ps1` cases are `slow` and skip without
PowerShell 7, as in test_promote_gate_effective_tree.py).
"""
import pytest

import context  # noqa: F401  pylint: disable=unused-import
import test_promote_gate_effective_tree as tree

_HEAD = "| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n"
_REVOKED = "the newest row is not all-pass"
_NO_ROW = "has no all-pass row"


def _row(env, sha, smoke="pass", regression="pass", verify="pass"):
    return f"| 2026-10-05 | {env} | {sha} | {smoke} | {regression} | {verify} | t |\n"


def _table(repo):
    """name -> (rows, exit code, text the block must name or None)."""
    # L-0703: a row counts only with the full sha, so every row is written in
    # full (test_promote_gate_review.py owns the short-row refusal).
    sha, other = repo.main_full, repo.wt_full
    fail = _row("development", sha, verify="FAIL")
    good = _row("development", sha)
    return {
        "fail-then-pass": ([fail, good], 0, None),
        "pass-then-fail": ([good, fail], 2, _REVOKED),
        "no-row": ([], 2, _NO_ROW),
        "another-sha-only": ([_row("development", other)], 2, _NO_ROW),
        "newest-smoke-not-pass": ([good, _row("development", sha, smoke="skip")], 2, _REVOKED),
        "newest-regression-not-run": ([good, _row("development", sha, regression="not-run")],
                                      2, _REVOKED),
        "single-all-pass": ([good], 0, None),
        "pass-in-capitals": ([_row("development", sha, "PASS", "PASS", "PASS")], 0, None),
        "newer-pass-for-another-env": ([fail, _row("prod", sha)], 2, _REVOKED),
        "newer-pass-for-another-sha": ([fail, _row("development", other)], 2, _REVOKED),
    }


_NAMES = ["fail-then-pass", "pass-then-fail", "no-row", "another-sha-only",
          "newest-smoke-not-pass", "newest-regression-not-run", "single-all-pass",
          "pass-in-capitals", "newer-pass-for-another-env", "newer-pass-for-another-sha"]


@pytest.mark.parametrize("flavour", tree.FLAVOURS)
@pytest.mark.parametrize("name", _NAMES)
def test_the_newest_row_decides(flavour, name, tmp_path):
    """qa requires development: the newest development row for this sha
    admits (all three cells pass) or blocks (anything else, or no row)."""
    repo = tree.Repo(tmp_path)
    rows, code_wanted, why = _table(repo)[name]
    (repo.main / ".work" / "PROMOTIONS.md").write_text(_HEAD + "".join(rows), encoding="utf-8")
    code, err = tree.run_gate(flavour, repo, "deploy-qa")
    assert code == code_wanted, err
    if why:
        assert "PROMOTION BLOCKED (qa" in err and why in err, err
        assert repo.in_flight() is None
    else:
        assert repo.in_flight() == f"qa {repo.main_sha}"

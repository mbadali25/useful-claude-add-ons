"""The acceptance receipt is bound to the bundle hash the reviewer read.

`review_ledger.py --check-receipt` rebuilds the bundle from the receipt's base
and fails unless its sha256 still matches, so an edit after review invalidates
the receipt. `/crew:done` (T4) gates on this; in 0.20.16 it is exposed and
documented.
"""
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
from review_fixtures import git, init_repo

_LEDGER = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_ledger.py")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = init_repo(tmp_path / "r")
    (root / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    return root


def _review(repo, verdict):
    base = git(repo, "rev-parse", "HEAD")
    manifest, _, _ = review_patch.compute(str(repo), base)
    ok, number, _ = rl.reserve(str(repo), "T1", "codex")
    assert ok
    rl.record(str(repo), "T1", number, {
        "verdict": verdict, "counts": {}, "bundle_sha256": manifest["bundle_sha256"],
        "base": base, "head": manifest["head"], "provider": "codex", "model": None,
        "model_family": "gpt"})


def _check(repo):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", "T1",
                           "--check-receipt"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def test_check_receipt_passes_for_a_clean_review_of_the_current_tree(repo):
    _review(repo, "CLEAN")

    result = _check(repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_check_receipt_fails_after_the_tree_is_edited(repo):
    _review(repo, "CLEAN")
    (repo / "feature.txt").write_text("feature v2, edited after review\n", encoding="utf-8")

    result = _check(repo)

    assert result.returncode == 1 and "stale" in result.stdout


def test_check_receipt_fails_after_a_new_untracked_file(repo):
    _review(repo, "CLEAN")
    (repo / "extra.txt").write_text("added after review\n", encoding="utf-8")

    result = _check(repo)

    assert result.returncode == 1


def test_check_receipt_survives_committing_the_reviewed_change(repo):
    _review(repo, "CLEAN")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "land the reviewed change")

    result = _check(repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_check_receipt_fails_with_no_review(repo):
    result = _check(repo)

    assert result.returncode == 1 and "no accepted review receipt" in result.stdout


@pytest.mark.parametrize("verdict", ["FINDINGS", "INCOMPLETE"])
def test_check_receipt_fails_for_an_unaccepted_verdict(repo, verdict):
    _review(repo, verdict)

    result = _check(repo)

    assert result.returncode == 1


def test_accept_findings_records_who_and_when_and_passes_the_check(repo):
    _review(repo, "FINDINGS")

    receipt = rl.accept(str(repo), "T1", "the owner")

    assert (receipt["kind"], receipt["accepted_by"]) == ("owner-accepted", "the owner")
    assert receipt["accepted_at"]
    assert _check(repo).returncode == 0


def test_accept_refuses_incomplete(repo):
    _review(repo, "INCOMPLETE")

    with pytest.raises(rl.LedgerError):
        rl.accept(str(repo), "T1", "the owner")


def test_accept_refuses_without_who(repo):
    _review(repo, "FINDINGS")

    with pytest.raises(rl.LedgerError):
        rl.accept(str(repo), "T1", " ")


def test_accept_refuses_when_the_tree_changed_since_the_review(repo):
    _review(repo, "FINDINGS")
    (repo / "feature.txt").write_text("edited\n", encoding="utf-8")

    with pytest.raises(rl.LedgerError):
        rl.accept(str(repo), "T1", "the owner")

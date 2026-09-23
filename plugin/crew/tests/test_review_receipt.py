"""The acceptance receipt is bound to the bundle hash the reviewer read.

`review_ledger.py --check-receipt` rebuilds the bundle from the receipt's base
and fails unless its sha256 still matches, so an edit after review invalidates
the receipt. `/crew:done` (T4) gates on this; in 0.20.17 it is exposed and
documented.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
from review_fixtures import git, init_repo

_LEDGER = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_ledger.py")
_RUN = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                    "review_run.py")


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


def test_truncated_bundle_parts_are_incomplete_and_mint_no_receipt(repo, tmp_path):
    """Codex BLOCK: build a bundle, truncate every part, return the READ lines
    plus CLEAN -- the receipt used to pass, bound to the untouched tree hash
    while the reviewer read empty files."""
    base = git(repo, "rev-parse", "HEAD")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    review_patch.build(str(repo), base, str(scratch / "diff.txt"),
                       str(scratch / "manifest.json"))
    parts = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))["parts"]
    for part in parts:
        pathlib.Path(part["path"]).write_bytes(b"")
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['name']}\n" for p in parts) + "CLEAN\n", encoding="utf-8")
    common = [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1",
              "--scratch", str(scratch), "--provider", "claude"]
    subprocess.run(common + ["--reserve-only"], capture_output=True,
                   stdin=subprocess.DEVNULL, check=True)

    verdict = subprocess.run(common + ["--round", "1", "--output", str(scratch / "out.txt"),
                                       "--exit-code", "0", "--work-dir", str(tmp_path / "w")],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL,
                             check=False)

    assert verdict.returncode == 3, verdict.stdout + verdict.stderr
    assert _check(repo).returncode == 1


def test_accept_an_older_round_after_needs_replan_is_refused(repo):
    """Codex BLOCK: complete round 1 with FINDINGS, reserve round 2, attempt a
    third reservation to enter NEEDS_REPLAN, then run --accept. Round 1 was
    accepted and the state moved back from NEEDS_REPLAN to ACCEPTED."""
    _review(repo, "FINDINGS")
    rl.reserve(str(repo), "T1", "codex")
    rl.reserve(str(repo), "T1", "codex")

    result = subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", "T1",
                             "--accept", "--by", "the owner"], capture_output=True,
                            text=True, stdin=subprocess.DEVNULL, check=False)

    assert (result.returncode, rl.status(str(repo), "T1")["state"],
            rl.status(str(repo), "T1")["receipt"]) == (1, rl.NEEDS_REPLAN, None)


def test_accept_the_latest_findings_round_once_it_is_needs_replan_is_refused(repo):
    """Round 2 FINDINGS left unaccepted, then a third reservation: refused,
    NEEDS_REPLAN, and --accept of round 2 is refused from then on."""
    _review(repo, "FINDINGS")
    _review(repo, "FINDINGS")
    ok, _, _ = rl.reserve(str(repo), "T1", "codex")
    assert (ok, rl.status(str(repo), "T1")["state"]) == (False, rl.NEEDS_REPLAN)

    with pytest.raises(rl.LedgerError, match=rl.NEEDS_REPLAN):
        rl.accept(str(repo), "T1", "the owner")


def _accept_cli(repo):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", "T1",
                           "--accept", "--by", "the owner"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def test_accept_round_two_findings_writes_a_receipt(repo):
    _review(repo, "FINDINGS")
    _review(repo, "FINDINGS")

    result = _accept_cli(repo)

    receipt = rl.status(str(repo), "T1")["receipt"]
    assert (result.returncode, rl.status(str(repo), "T1")["state"], receipt["round"],
            receipt["kind"], receipt["accepted_by"], _check(repo).returncode) == (
                0, rl.ACCEPTED, 2, "owner-accepted", "the owner", 0), result.stderr


def test_accept_the_same_round_twice_is_refused(repo):
    _review(repo, "FINDINGS")
    rl.accept(str(repo), "T1", "the owner")
    first = rl.status(str(repo), "T1")["receipt"]

    with pytest.raises(rl.LedgerError, match="already accepted"):
        rl.accept(str(repo), "T1", "someone else")

    assert rl.status(str(repo), "T1")["receipt"] == first


def _reject_cli(repo, *extra):
    return subprocess.run([sys.executable, _LEDGER, "--root", str(repo), "--ticket", "T1",
                           "--reject", *extra], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def test_reject_sets_needs_replan_and_accept_is_then_refused(repo):
    _review(repo, "FINDINGS")

    rejected = _reject_cli(repo, "--by", "the owner")

    assert (rejected.returncode, rl.status(str(repo), "T1")["state"],
            _accept_cli(repo).returncode, rl.status(str(repo), "T1")["receipt"]) == (
                0, rl.NEEDS_REPLAN, 1, None), rejected.stderr


@pytest.mark.parametrize("setup", ["needs_replan", "accepted", "no_by"])
def test_reject_is_refused_and_changes_nothing(repo, setup):
    _review(repo, "CLEAN" if setup == "accepted" else "FINDINGS")
    if setup == "needs_replan":
        _review(repo, "FINDINGS")
        rl.reserve(str(repo), "T1", "codex")
    before = rl.status(str(repo), "T1")

    result = _reject_cli(repo) if setup == "no_by" else _reject_cli(repo, "--by", "x")

    assert (result.returncode, rl.status(str(repo), "T1")) == (1, before)


def test_accept_an_older_round_while_a_later_one_is_reserved_is_refused(repo):
    _review(repo, "FINDINGS")
    rl.reserve(str(repo), "T1", "codex")

    with pytest.raises(rl.LedgerError, match="most recent"):
        rl.accept(str(repo), "T1", "the owner")


def _claude_round(repo, tmp_path, edit_manifest, max_part_bytes=None):
    """Build a bundle, let `edit_manifest` rewrite the manifest, answer CLEAN
    for every part it still lists, and finish a reserved claude round."""
    base = git(repo, "rev-parse", "HEAD")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    extra = {"max_part_bytes": max_part_bytes} if max_part_bytes else {}
    review_patch.build(str(repo), base, str(scratch / "diff.txt"),
                       str(scratch / "manifest.json"), **extra)
    manifest = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    edit_manifest(manifest)
    (scratch / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (scratch / "out.txt").write_text(
        "".join(f"READ|{p['name']}\n" for p in manifest["parts"]) + "CLEAN\n",
        encoding="utf-8")
    common = [sys.executable, _RUN, "--root", str(repo), "--ticket", "T1",
              "--scratch", str(scratch), "--provider", "claude"]
    subprocess.run(common + ["--reserve-only"], capture_output=True,
                   stdin=subprocess.DEVNULL, check=True)
    return subprocess.run(common + ["--round", "1", "--output", str(scratch / "out.txt"),
                                    "--exit-code", "0", "--work-dir", str(tmp_path / "w")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False)


def test_empty_parts_manifest_is_incomplete_and_mints_no_receipt(repo, tmp_path):
    """Codex BLOCK: build a valid manifest, replace parts with [], return
    CLEAN, and finish the reserved round. With no parts nothing was size- or
    hash-checked, and CLEAN minted a receipt for a bundle nobody read."""

    def empty(manifest):
        manifest["parts"] = []

    verdict = _claude_round(repo, tmp_path, empty)

    assert (verdict.returncode, _check(repo).returncode) == (3, 1), \
        verdict.stdout + verdict.stderr


def test_dropped_part_with_a_rewritten_bundle_hash_is_incomplete(repo, tmp_path):
    """The neighbour: drop the last part and rewrite bundle_sha256 over what
    is left. Every remaining part and the whole-bundle hash then agree with
    the manifest; only the byte total against patch_bytes does not."""
    (repo / "second.txt").write_text("second file\n" * 20, encoding="utf-8")

    def drop_last(manifest):
        assert len(manifest["parts"]) > 1
        manifest["parts"] = manifest["parts"][:-1]
        whole = hashlib.sha256()
        for row in manifest["parts"]:
            whole.update(pathlib.Path(row["path"]).read_bytes())
        manifest["bundle_sha256"] = whole.hexdigest()

    verdict = _claude_round(repo, tmp_path, drop_last, max_part_bytes=200)

    assert verdict.returncode == 3, verdict.stdout + verdict.stderr

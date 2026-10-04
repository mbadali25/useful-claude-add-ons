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
import merged_main_fixtures
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


def _review(repo, verdict, base=None):
    base = base or git(repo, "rev-parse", "HEAD")
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


@pytest.mark.parametrize("later", ["INCOMPLETE", "FINDINGS", "reserved"])
def test_check_receipt_fails_when_a_later_round_exists(repo, later):
    """Codex BLOCK: round 1 CLEAN, then round 2 INCOMPLETE -- --check-receipt
    exited 0 because only round 1's bundle hash was checked."""
    _review(repo, "CLEAN")
    if later == "reserved":
        rl.reserve(str(repo), "T1", "codex")
    else:
        _review(repo, later)

    result = _check(repo)

    assert (result.returncode, "latest" in result.stdout) == (1, True), result.stdout


def test_check_receipt_fails_once_needs_replan_even_on_the_latest_clean_round(repo):
    rl.reserve(str(repo), "T1", "codex")
    _review(repo, "CLEAN")
    rl.reserve(str(repo), "T1", "codex")

    result = _check(repo)

    assert (rl.status(str(repo), "T1")["state"], result.returncode,
            rl.NEEDS_REPLAN in result.stdout) == (rl.NEEDS_REPLAN, 1, True), result.stdout


def test_check_receipt_fails_when_the_latest_round_is_not_clean_or_accepted(repo):
    _review(repo, "CLEAN")
    path = rl.ledger_path(str(repo), "T1")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["rounds"][-1]["verdict"] = "FINDINGS"
    text = json.dumps(data)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    result = _check(repo)

    assert (result.returncode, "CLEAN or owner-accepted" in result.stdout) == (1, True), \
        result.stdout


# --- T-0100: a merge of main is judged against what the reviewer read ------------

def _reviewed_clone(tmp_path):
    """A ticket clone whose own change (`feature.txt`, committed) was reviewed
    CLEAN from the ticket start. Returns `(clone, upstream)`."""
    root, upstream, sha = merged_main_fixtures.build(tmp_path)
    merged_main_fixtures.ticket_commit(root, "feature.txt", "feature v1\n")
    _review(root, "CLEAN", base=sha["base"])
    return root, upstream


def test_check_receipt_survives_a_merge_of_main_that_touches_no_reviewed_path(tmp_path):
    root, upstream = _reviewed_clone(tmp_path)
    merged_main_fixtures.advance_main(upstream, *merged_main_fixtures.MAIN_EDITS[:4])
    merged_main_fixtures.merge_main(root)

    result = _check(root)

    assert (result.returncode, result.stdout.strip().endswith(
        "(5 path(s) identical to merged main left out)")) == (0, True), result.stdout


def test_check_receipt_is_stale_when_a_merge_of_main_changes_a_reviewed_path(tmp_path):
    root, upstream = _reviewed_clone(tmp_path)
    merged = merged_main_fixtures.advance_main(
        upstream, ("write", "feature.txt", "feature from main, a longer line\n"))
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-edit", "origin/main", check=False)
    git(root, "checkout", "--theirs", "--", "feature.txt")
    git(root, "add", "--", "feature.txt")
    git(root, "commit", "-q", "--no-edit")

    result = _check(root)

    assert (result.returncode, "receipt is stale" in result.stdout,
            f"merged main: {merged[:12]}" in result.stdout) == (1, True, True), result.stdout


def test_check_receipt_stale_message_says_could_not_tell(tmp_path):
    root, upstream = _reviewed_clone(tmp_path)
    merged_main_fixtures.advance_main(upstream)
    merged_main_fixtures.merge_main(root)
    git(root, "checkout", "-q", "--detach")

    result = _check(root)

    assert (result.returncode, "merged main: could not tell" in result.stdout) == (
        1, True), result.stdout


@pytest.mark.parametrize("stale", [False, True], ids=["current", "stale"])
def test_check_receipt_says_could_not_tell_when_the_fork_lookup_fails(
        tmp_path, monkeypatch, stale):
    """Review round 2: a rebuild whose `git merge-base <start> <merged>` gave no
    answer diffs main's paths from the start; the receipt line says the fork was
    unknown on a current receipt and on a stale one alike."""
    root, upstream = _reviewed_clone(tmp_path)
    merged_main_fixtures.advance_main(upstream, *merged_main_fixtures.MAIN_EDITS[:4])
    merged_main_fixtures.merge_main(root)
    if stale:
        merged_main_fixtures.write(root, "feature.txt", "feature v2, edited after review\n")
    real = review_patch.crew_common.git_out

    def fake(top, *args):
        fork_lookup = args[:1] == ("merge-base",) and len(args) == 3 and args[1] != "HEAD"
        return None if fork_lookup else real(top, *args)

    monkeypatch.setattr(review_patch.crew_common, "git_out", fake)

    ok, message = rl.check_receipt(str(root), "T1")

    assert (ok, "receipt is stale" in message, message.endswith("; fork: could not tell")) == (
        not stale, stale, True), message

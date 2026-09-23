"""`/crew:review` used to build its patch with `git diff "$BASE"...HEAD` --
committed range only. On a dirty tree that produced a 0-byte patch while
`git diff HEAD` showed real, uncommitted change, and untracked files never
entered it at all (see `plugin/crew/hooks/scripts/review_patch.py`'s own
docstring and `docs/review/03-codex-review.md`). A reviewer handed that empty
file reported CLEAN on nothing it had read.

`review_patch.build` is the fix: one patch covering the committed range PLUS
staged PLUS unstaged PLUS untracked changes, built without ever writing to
the real index. Every case here runs against a real, throwaway git
repository built fresh per test -- the questions are about what git actually
diffs, and a mock would only prove the mock agrees with itself.

Sabotage confirmed RED by hand against scratch copies of the script (never
the tracked file) before this suite was written, matching the ticket's
required three: (a) diff base->HEAD instead of base->working-tree drops all
dirty-tree content from a patch that still reports success; (b) `git add -u`
instead of `git add -A` silently drops untracked files while the exit code
still looks clean; (c) staging into the real index instead of a
`GIT_INDEX_FILE`-redirected temp copy corrupts the developer's own staged
change. `test_untracked_content_reaches_the_patch`,
`test_real_index_is_never_touched` and the dirty-tree assertions in
`test_dirty_tree_produces_a_nonempty_patch_with_all_four_categories`
reproduce those three checks directly.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "review_patch.py")


def _git(root, *args, check=True):
    return subprocess.run(
        ("git",) + args, cwd=root, check=check, capture_output=True,
        text=True, stdin=subprocess.DEVNULL,
    ).stdout.strip()


def _init_repo(root):
    root.mkdir(exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return root


def _run_script(root, base, out_path, manifest_path):
    return subprocess.run(
        [sys.executable, _SCRIPT, "--root", str(root), "--base", base,
         "--out", str(out_path), "--manifest", str(manifest_path)],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
    )


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return _init_repo(tmp_path / "r")


def test_dirty_tree_produces_a_nonempty_patch_with_all_four_categories(repo, tmp_path):
    """Committed, staged, unstaged AND untracked changes all land in one
    patch -- the direct reproduction of the defect: the old command produced
    0 bytes here."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "committed.txt").write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add committed.txt")
    (repo / "staged.txt").write_text("staged-content\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "seed.txt").write_text("seed\nunstaged-content\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked-content\n", encoding="utf-8")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)

    assert result.returncode == 0, result.stderr
    patch = out.read_text(encoding="utf-8")
    assert patch, "patch must not be empty on a dirty tree with real changes"
    assert "committed.txt" in patch
    assert "staged-content" in patch
    assert "unstaged-content" in patch
    assert "untracked-content" in patch


def test_staged_only_change_is_included(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "staged.txt").write_text("only-staged\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)

    assert result.returncode == 0, result.stderr
    assert "only-staged" in out.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["staged_files"] == ["staged.txt"]


def test_untracked_content_reaches_the_patch(repo, tmp_path):
    """Sabotage (b): `git add -u` instead of `git add -A` drops this
    silently -- exit code stays 0, only the content goes missing."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "brand_new.txt").write_text("new-file-content\n", encoding="utf-8")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)

    assert result.returncode == 0, result.stderr
    patch = out.read_text(encoding="utf-8")
    assert "new-file-content" in patch
    assert "brand_new.txt" in patch
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["untracked_files"] == ["brand_new.txt"]


def test_committed_range_change_is_included(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "committed.txt").write_text("committed-only\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add committed.txt")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)

    assert result.returncode == 0, result.stderr
    assert "committed-only" in out.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["committed_files"] == ["committed.txt"]
    assert manifest["dirty"] is False


def test_real_index_is_never_touched(repo, tmp_path):
    """Sabotage (c): staging into the real index instead of a
    `GIT_INDEX_FILE`-redirected temp copy corrupts whatever the developer
    already staged for their own next commit."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
    (repo / "loose.txt").write_text("loose\n", encoding="utf-8")

    before = _git(repo, "diff", "--cached", "--name-only")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)
    assert result.returncode == 0, result.stderr

    after = _git(repo, "diff", "--cached", "--name-only")
    assert before == after == "staged.txt"


def test_clean_tree_reports_nothing_to_review(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)

    assert result.returncode == 2
    assert "nothing to review" in result.stderr
    assert out.read_text(encoding="utf-8") == ""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["dirty"] is False
    assert manifest["committed_files"] == []


def test_manifest_lists_each_category_correctly(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "committed.txt").write_text("c\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add committed.txt")
    (repo / "staged.txt").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "seed.txt").write_text("seed\nchanged\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("u\n", encoding="utf-8")

    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, base, out, manifest_path)
    assert result.returncode == 0, result.stderr

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["committed_files"] == ["committed.txt"]
    assert manifest["staged_files"] == ["staged.txt"]
    assert manifest["unstaged_files"] == ["seed.txt"]
    assert manifest["untracked_files"] == ["untracked.txt"]
    assert manifest["dirty"] is True
    assert manifest["base"] == base
    assert manifest["head"] == _git(repo, "rev-parse", "HEAD")
    assert manifest["branch"] == "main"
    assert manifest["patch_bytes"] == len(out.read_text(encoding="utf-8").encode("utf-8"))


def test_bad_base_fails_loudly(repo, tmp_path):
    out, manifest_path = tmp_path / "diff.txt", tmp_path / "manifest.json"
    result = _run_script(repo, "not-a-real-sha", out, manifest_path)

    assert result.returncode == 1
    assert "does not resolve to a commit" in result.stderr
    assert not out.exists()
    assert not manifest_path.exists()


# ---- 0.20.17 (T1): completeness, splitting, bundle hash --------------------

def _manifest(tmp_path):
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def test_rename_mode_change_and_binary_appear_in_the_manifest(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "tool.sh").write_text("echo hi\n", encoding="utf-8")
    _git(repo, "add", "tool.sh")
    _git(repo, "commit", "-qm", "tool")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "seed.txt", "renamed.txt")
    # Both: POSIX (core.filemode=true) takes the mode from the file, Windows
    # (core.filemode=false) from the index entry.
    (repo / "tool.sh").chmod(0o755)
    _git(repo, "update-index", "--chmod=+x", "tool.sh")
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02binary\x00payload" * 8)

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    manifest = _manifest(tmp_path)
    assert manifest["renames"] == ["renamed.txt"]
    rename = next(e for e in manifest["entries"] if e["status"] == "R")
    assert (rename["old_path"], rename["path"]) == ("seed.txt", "renamed.txt")
    assert manifest["mode_changes"] == ["tool.sh"]
    mode = next(e for e in manifest["entries"] if e["path"] == "tool.sh")
    assert (mode["old_mode"], mode["new_mode"]) == ("100644", "100755")
    assert manifest["binary_files"] == ["blob.bin"]
    binary = next(e for e in manifest["entries"] if e["path"] == "blob.bin")
    assert binary["new_size"] == len(b"\x00\x01\x02binary\x00payload" * 8)
    assert len(binary["new_id"]) == 40
    patch = (tmp_path / "diff.txt").read_bytes()
    assert b"Binary files" in patch and binary["new_id"].encode() in patch


def test_submodule_entry_is_recorded(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    sub = repo / "vendored"
    sub.mkdir()
    _git(sub, "init", "-q", "-b", "main")
    _git(sub, "config", "user.email", "t@example.com")
    _git(sub, "config", "user.name", "t")
    (sub / "x.txt").write_text("x\n", encoding="utf-8")
    _git(sub, "add", "-A")
    _git(sub, "commit", "-qm", "sub")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    manifest = _manifest(tmp_path)
    assert manifest["submodules"] == ["vendored"]
    entry = next(e for e in manifest["entries"] if e["path"] == "vendored")
    assert entry["new_mode"] == "160000" and entry["binary"] is False


def test_oversized_bundle_splits_and_concatenates_to_the_whole(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    for i in range(4):
        (repo / f"big{i}.txt").write_text("".join(f"line {n} of file {i}\n"
                                                  for n in range(60)), encoding="utf-8")
    (repo / "one-long-line.txt").write_text("x" * 900 + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, _SCRIPT, "--root", str(repo), "--base", base,
         "--out", str(tmp_path / "diff.txt"), "--manifest", str(tmp_path / "manifest.json"),
         "--max-part-bytes", "400"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = _manifest(tmp_path)
    parts = manifest["parts"]
    assert len(parts) > 1
    whole = (tmp_path / "diff.txt").read_bytes()
    joined = b"".join(pathlib.Path(p["path"]).read_bytes() for p in parts)
    assert joined == whole
    assert all(p["bytes"] <= 400 for p in parts)
    assert manifest["bundle_sha256"] == hashlib.sha256(whole).hexdigest()
    assert [p["name"] for p in parts] == sorted(p["name"] for p in parts)


def test_bundle_hash_is_stable_and_moves_with_content(repo, tmp_path):
    import review_patch  # pylint: disable=import-outside-toplevel
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")

    first, _, _ = review_patch.compute(str(repo), base)
    second, _, _ = review_patch.compute(str(repo), base)
    (repo / "a.txt").write_text("a changed\n", encoding="utf-8")
    third, _, _ = review_patch.compute(str(repo), base)

    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert third["bundle_sha256"] != first["bundle_sha256"]


def test_work_dir_is_excluded_and_says_so(repo, tmp_path):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / ".work" / "review").mkdir(parents=True)
    (repo / ".work" / "review" / "scratch.txt").write_text("scratch\n", encoding="utf-8")
    (repo / "real.txt").write_text("real\n", encoding="utf-8")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    manifest = _manifest(tmp_path)
    assert manifest["untracked_files"] == ["real.txt"]
    assert manifest["excluded"] == [".work/"]
    assert b"scratch" not in (tmp_path / "diff.txt").read_bytes()


def test_split_parts_never_truncates():
    import review_patch  # pylint: disable=import-outside-toplevel
    data = b"diff --git a/x b/x\n" + b"y" * 1000 + b"\ndiff --git a/z b/z\nshort\n"
    for limit in (1, 7, 64, 500, 5000):
        parts = review_patch.split_parts(data, limit)
        assert b"".join(parts) == data
        assert all(0 < len(p) <= limit for p in parts)


def test_gitignored_work_dir_still_builds_a_bundle(repo, tmp_path):
    """Dogfood BLOCK: `git add -A -- . ':(exclude).work'` exits 1 ("paths are
    ignored by one of your .gitignore files") in every repo that gitignores
    `.work/` -- this marketplace included -- so no bundle could be built. The
    earlier fixtures never gitignored `.work`, which is how it shipped."""
    (repo / ".gitignore").write_text(".work/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-qm", "ignore .work")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / ".work" / "tickets").mkdir(parents=True)
    (repo / ".work" / "tickets" / "scratch.txt").write_text("scratch\n", encoding="utf-8")
    (repo / "real.txt").write_text("real-change\n", encoding="utf-8")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    assert b"real-change" in (tmp_path / "diff.txt").read_bytes()


def test_work_entries_already_in_the_index_stay_out_of_the_bundle(repo, tmp_path):
    """The exclusion used to act only on what `add -A` staged, so a `.work`
    path the copied real index already held -- force-added, or committed --
    still reached the bundle and its hash."""
    (repo / ".work").mkdir()
    (repo / ".work" / "committed.txt").write_text("committed-scratch\n", encoding="utf-8")
    _git(repo, "add", "-f", ".work/committed.txt")
    _git(repo, "commit", "-qm", "a .work file in history")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / ".work" / "committed.txt").write_text("edited-scratch\n", encoding="utf-8")
    (repo / ".work" / "staged.txt").write_text("staged-scratch\n", encoding="utf-8")
    _git(repo, "add", "-f", ".work/staged.txt")
    (repo / "real.txt").write_text("real\n", encoding="utf-8")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    patch = (tmp_path / "diff.txt").read_bytes()
    assert b".work/" not in patch and b"scratch" not in patch

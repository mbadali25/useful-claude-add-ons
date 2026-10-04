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
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import merged_main_fixtures
import review_patch

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
    assert (manifest["merged_main"]["applies"],
            "HEAD is on main itself" in manifest["merged_main"]["reason"]) == (False, True)


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


def _seed_graph(repo):
    """Track a generated `graphify-out/` at the base, the shape this
    repository has (`git ls-files graphify-out/` lists both files)."""
    (repo / "graphify-out").mkdir()
    (repo / "graphify-out" / "graph.json").write_text('{"nodes": 1}\n', encoding="utf-8")
    (repo / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "graph")
    return _git(repo, "rev-parse", "HEAD")


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
    assert manifest["excluded"] == [".work/", "graphify-out/", ".crew/metrics.md"]
    assert b"scratch" not in (tmp_path / "diff.txt").read_bytes()


def test_split_parts_never_truncates():
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


# ---- 1.0.54 (T-0092): generated graphify-out/ is excluded like .work/ -------

def test_generated_graph_dir_is_excluded_and_says_so(repo, tmp_path):
    """A 24 MB `graphify-out/graph.json` split into ~120 parts left a Claude
    review INCOMPLETE on 77 of 80 parts (T-0075 round 5). The generated graph
    stays out of every diff, listing and entry, and the manifest says so."""
    base = _seed_graph(repo)
    (repo / "graphify-out" / "graph.json").write_text('{"nodes": 2}\n', encoding="utf-8")
    (repo / "graphify-out" / "new.json").write_text("{}\n", encoding="utf-8")
    (repo / "real.txt").write_text("real\n", encoding="utf-8")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    patch = (tmp_path / "diff.txt").read_bytes()
    assert b"real" in patch
    assert b"graphify-out/" not in patch
    assert b'"nodes": 2' not in patch
    m = _manifest(tmp_path)
    assert m["excluded"] == [".work/", "graphify-out/", ".crew/metrics.md"]
    listed = (m["committed_files"] + m["unstaged_files"] + m["untracked_files"]
              + [e["path"] for e in m["entries"]])
    assert not [p for p in listed if p.startswith("graphify-out/")]
    assert m["untracked_files"] == ["real.txt"]


def test_graph_only_change_keeps_the_bundle_hash(repo, tmp_path):
    """A graph rebuild after an accepted review no longer stales its receipt;
    a real edit still does (guards against a hash that ignores everything)."""
    base = _seed_graph(repo)
    (repo / "real.txt").write_text("real\n", encoding="utf-8")
    _git(repo, "add", "real.txt")
    _git(repo, "commit", "-qm", "real")

    _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")
    h1 = _manifest(tmp_path)["bundle_sha256"]
    (repo / "graphify-out" / "graph.json").write_text('{"nodes": 3}\n', encoding="utf-8")
    (repo / "graphify-out" / "extra.json").write_text("{}\n", encoding="utf-8")
    _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")
    h2 = _manifest(tmp_path)["bundle_sha256"]
    with open(repo / "real.txt", "a", encoding="utf-8") as fh:
        fh.write("more\n")
    _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")
    h3 = _manifest(tmp_path)["bundle_sha256"]

    assert h1 is not None
    assert h2 == h1
    assert h3 != h1


def test_look_alike_paths_are_still_bundled(repo, tmp_path):
    """Must-not: the exclusion is root-anchored, so a hand-written file under
    a similarly named path -- a sibling `graphify-out-notes/` or a nested
    `docs/graphify-out/` -- still reaches the reviewer."""
    base = _seed_graph(repo)
    (repo / "graphify-out" / "graph.json").write_text('{"nodes": 4}\n', encoding="utf-8")
    (repo / "graphify-out-notes").mkdir()
    (repo / "graphify-out-notes" / "README.md").write_text("notes\n", encoding="utf-8")
    (repo / "docs" / "graphify-out").mkdir(parents=True)
    (repo / "docs" / "graphify-out" / "x.md").write_text("nested\n", encoding="utf-8")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    m = _manifest(tmp_path)
    assert m["untracked_files"] == ["docs/graphify-out/x.md", "graphify-out-notes/README.md"]
    patch = (tmp_path / "diff.txt").read_bytes()
    assert b"notes" in patch and b"nested" in patch
    assert b"graphify-out/graph.json" not in patch


# ---- L-0578: review_run.py appends .crew/metrics.md between bundle and receipt ----

def test_metrics_row_stays_out_of_the_bundle_and_the_rest_of_crew_stays_in(repo, tmp_path):
    """review_run.py writes the round's row after the bundle is built; in a repo
    that does not gitignore .crew/ that row must not change what the receipt
    rebuilds, while every other .crew/ file is still reviewed."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "metrics.md").write_text("2026-10-01 | T1 | x (r1) | 0 | 0\n",
                                               encoding="utf-8")
    (repo / ".crew" / "verify.json").write_text("{}\n", encoding="utf-8")

    result = _run_script(repo, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    assert (_manifest(tmp_path)["untracked_files"],
            b"(r1)" in (tmp_path / "diff.txt").read_bytes()) == ([".crew/verify.json"], False)


# ---- T-0100: paths byte-identical to merged main leave the bundle -------------

_SHARED_ON_TOP = "shared = 1\nmain_line = 2\nticket_line = 3\n"


def _merged_fixture(tmp_path, merge=True):
    """The spec's Evidence shape: a ticket commit, main advancing (edit, add,
    delete, rename, and an edit to `src/shared.py`), a merge of main, the
    ticket editing `src/shared.py` on top, an unstaged out-of-Touch edit and
    an untracked file. Returns `(clone, base, merged commit or None)`."""
    root, upstream, sha = merged_main_fixtures.build(tmp_path)
    merged_main_fixtures.ticket_commit(root, "src/t.txt", "ticket line\n")
    merged_main_fixtures.advance_main(upstream)
    merged = merged_main_fixtures.merge_main(root) if merge else None
    if not merge:
        _git(root, "fetch", "-q", "origin")
    merged_main_fixtures.ticket_commit(root, "src/shared.py", _SHARED_ON_TOP)
    merged_main_fixtures.write(root, "other/x.py", "x = 2  # unstaged\n")
    merged_main_fixtures.write(root, "src/untracked.txt", "untracked\n")
    return root, sha["base"], merged


def _working_tree_id(root, tmp_path):
    """The tree `review_patch.compute` diffs against, rebuilt the same way."""
    index = tmp_path / "rebuilt-index"
    real = _git(root, "rev-parse", "--git-path", "index")
    shutil.copy(os.path.join(root, real), index)
    env = dict(os.environ, GIT_INDEX_FILE=str(index))
    subprocess.run(["git", "add", "-A", "--", "."], cwd=root, env=env, check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)
    return subprocess.run(["git", "write-tree"], cwd=root, env=env, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def test_merged_main_paths_leave_the_bundle(tmp_path):
    root, base, merged = _merged_fixture(tmp_path)

    result = _run_script(root, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert result.returncode == 0, result.stderr
    patch, m = (tmp_path / "diff.txt").read_bytes(), _manifest(tmp_path)
    assert (b"ticket line" in patch, b"x = 2" in patch,
            [s for s in (b"m v2", b"m2.txt", b"gone.txt", b"r_old.txt", b"r_new.txt")
             if s in patch]) == (True, True, [])
    assert {k: v for k, v in m["merged_main"].items() if k != "reason"} == {
        "ref": "origin/main", "commit": merged, "applies": True, "fork": base,
        "dropped": merged_main_fixtures.DROPPED, "diffed_from_merged": ["src/shared.py"]}
    assert (m["base"], m["committed_files"]) == (base, ["src/shared.py", "src/t.txt"])
    assert [e["path"] for e in m["entries"] if e["path"] in merged_main_fixtures.DROPPED
            or e["old_path"] in merged_main_fixtures.DROPPED] == []
    assert f"merged-main={merged[:12]} dropped=5 diffed-from-merged=1" in result.stderr


def test_the_bundle_is_byte_identical_to_the_pathspec_form(tmp_path):
    """The kept paths diffed from the merged commit: the start's content for
    every path main left alone, main's for the one it changed too."""
    root, base, merged = _merged_fixture(tmp_path)
    manifest, patch, _ = review_patch.compute(str(root), base)
    tree = _working_tree_id(root, tmp_path)
    kept = ["other/x.py", "src/shared.py", "src/t.txt", "src/untracked.txt"]

    expected = subprocess.run(
        ["git", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "-M", "--full-index",
         merged, tree, "--"] + kept, cwd=root, check=True, capture_output=True,
        stdin=subprocess.DEVNULL).stdout

    assert (manifest["merged_main"]["applies"], patch) == (True, expected)


def test_a_ticket_edit_on_top_of_merged_mains_edit_stays_in_the_bundle(tmp_path):
    """The hunk shows main's already-landed line as context and only the
    ticket's line as `+` (review round 1: `+main_line` read as the ticket's)."""
    root, base, _ = _merged_fixture(tmp_path)

    manifest, patch, _ = review_patch.compute(str(root), base)

    shared = patch.split(b"diff --git a/src/shared.py")[1].split(b"diff --git")[0]
    assert (b"+ticket_line = 3" in shared, b"\n main_line = 2" in shared,
            b"+main_line = 2" in shared) == (True, True, False)
    assert (manifest["merged_main"]["fork"], "fork_reason" in manifest["merged_main"]) == (
        _git(root, "merge-base", base, manifest["merged_main"]["commit"]), False)


def _fork_lookup_fails(monkeypatch, base, merged):
    """`git merge-base <start> <merged>` gives no answer; every other git call,
    `merged_main.resolve`'s `merge-base HEAD <ref>` included, still answers."""
    real = review_patch.crew_common.git_out

    def fake(root, *args):
        return None if args == ("merge-base", base, merged) else real(root, *args)

    monkeypatch.setattr(review_patch.crew_common, "git_out", fake)


def test_a_failed_fork_lookup_is_could_not_tell(tmp_path, monkeypatch, capsys):
    """Review round 2: with no fork, every path main also changed is diffed from
    the start (the more-inclusive bundle, kept), and that is said -- an empty
    `diffed_from_merged` must never pass as "main changed none of them"."""
    root, base, merged = _merged_fixture(tmp_path)
    _fork_lookup_fails(monkeypatch, base, merged)

    manifest, patch, _ = review_patch.compute(str(root), base)
    code = review_patch.main(["--root", str(root), "--base", base,
                              "--out", str(tmp_path / "diff.txt"),
                              "--manifest", str(tmp_path / "manifest.json")])

    got = manifest["merged_main"]
    shared = patch.split(b"diff --git a/src/shared.py")[1].split(b"diff --git")[0]
    assert (got["applies"], got["fork"], got["fork_reason"].startswith(
        "could not tell: git merge-base"), base[:12] in got["fork_reason"],
            merged[:12] in got["fork_reason"], got["diffed_from_merged"],
            b"+main_line = 2" in shared) == (True, None, True, True, True, [], True)
    assert (code, " diffed-from-merged=could-not-tell" in capsys.readouterr().err) == (0, True)


def test_review_md_step_2_echo_names_why():
    """Review round 2 NIT, resolved by the spec amendment and pinned here: in the
    merged-main exit-2 case HEAD need not match $BASE, so the echo defers to
    review-patch's own line instead of claiming it."""
    text = pathlib.Path(_ROOT, "commands", "review.md").read_text(encoding="utf-8")

    assert (text.count('echo "nothing to review since $BASE: review-patch\'s line above says '
                       'why"'), "HEAD matches $BASE and the tree is clean" in text) == (1, False)


def test_a_start_after_the_fork_diffs_only_mains_paths_from_the_merged_commit(tmp_path):
    """Neighbour: a start recorded after a ticket commit is not an ancestor of
    the merged commit. What the ticket did before its start is not main's, so
    that file is still diffed from the start; main's file is still diffed from
    the merged commit."""
    root, upstream, _ = merged_main_fixtures.build(tmp_path)
    base = merged_main_fixtures.ticket_commit(root, "src/t.txt", "ticket line\n")
    merged_main_fixtures.advance_main(upstream)
    merged_main_fixtures.merge_main(root)
    merged_main_fixtures.ticket_commit(root, "src/t.txt", "ticket line\nsecond, after\n")
    merged_main_fixtures.ticket_commit(root, "src/shared.py", _SHARED_ON_TOP)

    manifest, patch, _ = review_patch.compute(str(root), base)

    own = patch.split(b"diff --git a/src/t.txt")[1].split(b"diff --git")[0]
    assert (manifest["merged_main"]["diffed_from_merged"], b"\n ticket line" in own,
            b"+ticket line" in own, b"+second, after" in own) == (
                ["src/shared.py"], True, False, True)


def test_no_merge_of_main_leaves_the_bundle_unchanged(tmp_path):
    root, base, _ = _merged_fixture(tmp_path, merge=False)
    manifest, patch, _ = review_patch.compute(str(root), base)
    tree = _working_tree_id(root, tmp_path)

    before = subprocess.run(
        ["git", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "-M", "--full-index",
         base, tree, "--", ".", ":(exclude).work", ":(exclude)graphify-out"], cwd=root,
        check=True, capture_output=True, stdin=subprocess.DEVNULL).stdout

    assert (manifest["merged_main"]["applies"], manifest["merged_main"]["dropped"],
            patch) == (False, [], before)


def test_could_not_tell_bundles_everything_and_says_so(tmp_path):
    root, base, _ = _merged_fixture(tmp_path)
    _git(root, "checkout", "-q", "--detach")

    result = _run_script(root, base, tmp_path / "diff.txt", tmp_path / "manifest.json")

    patch, m = (tmp_path / "diff.txt").read_bytes(), _manifest(tmp_path)
    assert (result.returncode, [s for s in (b"m v2", b"m2.txt", b"gone.txt", b"r_new.txt")
                                if s not in patch]) == (0, [])
    assert (m["merged_main"]["commit"], m["merged_main"]["reason"].startswith("could not tell"),
            "merged-main=could-not-tell" in result.stderr) == (None, True, True)


def test_everything_merged_and_nothing_else_is_nothing_to_review(tmp_path):
    root, upstream, sha = merged_main_fixtures.build(tmp_path)
    merged_main_fixtures.advance_main(upstream)
    merged = merged_main_fixtures.merge_main(root)

    result = _run_script(root, sha["base"], tmp_path / "diff.txt", tmp_path / "manifest.json")

    assert (result.returncode, f"identical to merged origin/main {merged[:12]}" in result.stderr,
            "matches" in result.stderr) == (2, True, False)

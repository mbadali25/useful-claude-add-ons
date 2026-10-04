"""merged_main.py: which commit of the integration branch a ticket branch has
merged, and the one rule both the review bundle and the completion audit use
to leave out a path byte-identical to it (T-0100).

The unknown never collapses into "nothing merged" or "everything merged":
each could-not-tell cause drops nothing and says so.
"""
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
import crew_common
import merged_main
import review_patch
import scope_base
from merged_main_fixtures import DROPPED, advance_main, build, merge_main, ticket_commit, write
from review_fixtures import git, init_repo


def test_no_merge_past_the_start_changes_nothing(tmp_path):
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    git(root, "fetch", "-q", "origin")

    got = merged_main.resolve(str(root), sha["base"])

    assert (got["applies"], got["commit"], got["ref"]) == (False, sha["base"], "origin/main")
    assert "no merge of origin/main past" in got["reason"]


def test_a_merge_of_main_is_found_and_the_latest_one_wins(tmp_path):
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    first = merge_main(root)
    once = merged_main.resolve(str(root), sha["base"])
    advance_main(upstream, ("write", "later.txt", "later, from main\n"))
    second = merge_main(root)

    twice = merged_main.resolve(str(root), sha["base"])

    assert ((once["applies"], once["commit"]), (twice["applies"], twice["commit"])) == (
        (True, first), (True, second))


def test_head_on_the_integration_branch_never_applies(tmp_path):
    root = init_repo(tmp_path / "r")
    base = git(root, "rev-parse", "HEAD")
    write(root, "other/after.py", "y = 22\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "after the start")

    got = merged_main.resolve(str(root), base)

    assert (got["applies"], got["ref"]) == (False, "main")
    assert "HEAD is on main itself" in got["reason"]


def test_a_fallback_base_equal_to_the_merge_base_changes_nothing(tmp_path):
    root, upstream, _ = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    merged = merge_main(root)
    fallback = git(root, "merge-base", "HEAD", "origin/main")

    got = merged_main.resolve(str(root), fallback)

    assert (fallback, got["applies"], got["commit"]) == (merged, False, merged)


def _no_ref(monkeypatch, _root):
    monkeypatch.setattr(scope_base, "base_branch", lambda root: (None, None))


def _base_branch_names_no_commit(_monkeypatch, root):
    """T-0061: a configured `tickets.baseBranch` naming no commit is its own
    could-not-tell, never a fall back to origin/HEAD's main."""
    write(root, ".crew/config.json", '{"tickets": {"baseBranch": "nope"}}\n')


def _detached(_monkeypatch, root):
    git(root, "checkout", "-q", "--detach")


def _merge_base_fails(monkeypatch, _root):
    real = crew_common.git_out

    def fake(root, *args):
        if args[:1] == ("merge-base",) and "--is-ancestor" not in args:
            return None
        return real(root, *args)
    monkeypatch.setattr(crew_common, "git_out", fake)


def _is_ancestor_fails(monkeypatch, _root):
    monkeypatch.setattr(merged_main, "_is_ancestor", lambda root, older, newer: None)


@pytest.mark.parametrize("cause", [_no_ref, _detached, _merge_base_fails, _is_ancestor_fails,
                                   _base_branch_names_no_commit],
                         ids=["no-ref", "detached-head", "merge-base-fails", "is-ancestor-fails",
                              "base-branch-names-no-commit"])
def test_could_not_tell_drops_nothing(tmp_path, monkeypatch, cause):
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    merge_main(root)
    cause(monkeypatch, root)

    got = merged_main.resolve(str(root), sha["base"])

    assert (got["applies"], got["commit"], got["reason"].startswith("could not tell")) == (
        False, None, True)


def test_could_not_tell_names_t0061s_reason_for_a_configured_base_branch(tmp_path):
    """The reason carries `scope_base.base_branch`'s own problem, not a claim
    that origin/HEAD, origin/main and main were tried."""
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    merge_main(root)
    write(root, ".crew/config.json", '{"tickets": {"baseBranch": "nope"}}\n')

    got = merged_main.resolve(str(root), sha["base"])

    assert ("tickets.baseBranch 'nope' names no commit here" in got["reason"],
            "origin/HEAD, origin/main, main" in got["reason"]) == (True, False)


def test_the_configured_base_branch_is_the_integration_ref(tmp_path):
    """T-0061: with `tickets.baseBranch: development` the merged commit is the
    merge-base with origin/development, although origin/HEAD names main; and
    HEAD on development itself never applies."""
    root, upstream, sha = build(tmp_path)
    git(upstream, "branch", "development", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "checkout", "-q", "-B", "T-1", "origin/development")
    write(root, ".crew/config.json", '{"tickets": {"baseBranch": "development"}}\n')
    ticket_commit(root, "src/t.txt", "ticket line\n")
    git(upstream, "checkout", "-q", "development")
    advance_main(upstream)
    git(upstream, "checkout", "-q", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-edit", "origin/development")
    merged = git(root, "rev-parse", "origin/development")
    on_branch = merged_main.resolve(str(root), sha["base"])
    git(root, "checkout", "-q", "-b", "development", "origin/development")

    on_development = merged_main.resolve(str(root), sha["base"])

    assert ((on_branch["ref"], on_branch["commit"], on_branch["applies"]),
            (on_development["applies"], "HEAD is on development itself" in on_development["reason"])
            ) == (("origin/development", merged, True), (False, True))


def test_is_ancestor_answers_true_false_and_none_when_git_cannot(tmp_path):
    """Neighbour of the is-ancestor-fails cause: a real git error (a sha
    that names no commit) is None, never False."""
    root, upstream, sha = build(tmp_path)
    head = ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    git(root, "fetch", "-q", "origin")

    got = (merged_main._is_ancestor(str(root), sha["base"], head),  # pylint: disable=protected-access
           merged_main._is_ancestor(str(root), head, sha["base"]),  # pylint: disable=protected-access
           merged_main._is_ancestor(str(root), "f" * 40, head))  # pylint: disable=protected-access

    assert got == (True, False, None)


def test_keep_is_the_intersection():
    since_base = ["a", "b", "c", "d"]
    since_merged = {"d", "b", "z"}

    kept = merged_main.keep(since_base, since_merged)

    assert kept == ["b", "d"]


def test_the_bundle_and_the_audit_name_the_same_changed_paths(tmp_path):
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    merge_main(root)
    ticket_commit(root, "src/shared.py", "shared = 1\nmain_line = 2\nticket_line = 3\n")
    write(root, "other/x.py", "x = 2, unstaged\n")
    write(root, "src/untracked.txt", "untracked\n")
    top, base = str(root), sha["base"]

    manifest, _, _ = review_patch.compute(top, base)
    audited = completion_audit.changed_paths(top, base, merged_main.resolve(top, base))

    bundled = set()
    for key in ("committed_files", "staged_files", "unstaged_files", "untracked_files"):
        bundled.update(manifest[key])
    assert (bundled, bundled & set(DROPPED)) == (set(audited), set())


@pytest.mark.parametrize("content,counted", [("m v2, a longer line from main\n", False),
                                             ("m v3, the ticket's own edit\n", True)],
                         ids=["identical-to-merged", "edited"])
def test_the_bundle_and_the_audit_agree_on_a_merged_in_path_removed_from_the_index(
        tmp_path, content, counted):
    """`git rm --cached` on a merged-in path leaves it untracked on disk. The
    bundle stages it again (`add -A`), so both consumers judge its bytes:
    identical to the merged commit drops from both, edited stays in both."""
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    merge_main(root)
    git(root, "rm", "-q", "--cached", "m.txt")
    write(root, "m.txt", content)
    top, base = str(root), sha["base"]

    manifest, _, _ = review_patch.compute(top, base)
    audited = completion_audit.changed_paths(top, base, merged_main.resolve(top, base))

    bundled = set()
    for key in ("committed_files", "staged_files", "unstaged_files", "untracked_files"):
        bundled.update(manifest[key])
    assert (bundled == set(audited), "m.txt" in audited) == (True, counted)


@pytest.mark.skipif(os.name == "nt", reason="NTFS carries no execute bit git can see, so "
                    "every file reads 100644 there")
@pytest.mark.parametrize("exec_bit,file_mode,counted", [
    (True, "true", True), (True, "false", False), (False, "true", False),
    (False, "false", False)], ids=["exec-filemode-true", "exec-filemode-false",
                                   "noexec-filemode-true", "noexec-filemode-false"])
def test_the_bundle_and_the_audit_agree_on_the_mode_of_a_merged_in_path_removed_from_the_index(
        tmp_path, exec_bit, file_mode, counted):
    """Content identical to merged main, so only the mode can tell. The bundle's
    `add -A` records the execute bit only when core.fileMode is not false; the audit
    must judge the same way, or the reviewer and the audit see different sets."""
    root, upstream, sha = build(tmp_path)
    ticket_commit(root, "src/t.txt", "ticket line\n")
    advance_main(upstream)
    merge_main(root)
    git(root, "rm", "-q", "--cached", "m.txt")
    git(root, "config", "core.fileMode", file_mode)
    path = root / "m.txt"
    mode = path.stat().st_mode
    path.chmod(mode | 0o111 if exec_bit else mode & ~0o111)
    top, base = str(root), sha["base"]

    manifest, _, _ = review_patch.compute(top, base)
    audited = completion_audit.changed_paths(top, base, merged_main.resolve(top, base))

    bundled = set()
    for key in ("committed_files", "staged_files", "unstaged_files", "untracked_files"):
        bundled.update(manifest[key])
    assert (bundled == set(audited), "m.txt" in audited) == (True, counted)

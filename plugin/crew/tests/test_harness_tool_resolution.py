"""L-1508 PR B: the review/gate harness runs the git `shutil.which` found.

PR A moved every other crew script onto `crew_common.require_tool`; the
harness files waited for this PR because a harness change lands alone (owner
rule T-0087). Each test here puts a FAILING git where only `shutil.which` can
reach it (tool_fixtures.which_only): a site still running a bare "git" reaches
the real, healthy one on PATH and answers as if nothing were wrong, so the test
is red until the site runs the resolved path. Every guard must then refuse, or
report could-not-tell, exactly as it did when git was missing -- never pass.

Modelled on test_ci_receipt.py::test_check_runs_the_git_which_resolves.
"""
import json
import shutil

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import completion_audit
import crew_ticket
import merged_main
import review_gate
import review_ledger
import review_patch
import review_prompt
import tool_fixtures
import verify_fingerprint
import verify_record
from review_fixtures import git, init_repo
from scope_fixtures import make_repo, ready


def _resolved_git_fails(monkeypatch, tmp_path):
    tool_fixtures.which_only(monkeypatch, tmp_path / "resolved", "git")


# --- review_gate: a verified tree is UNKNOWN when the resolved git fails --------

def _verified_repo(tmp_path):
    """A committed tree whose marker names HEAD and where nothing material
    differs: `gate_state` says VERIFIED without running the gate itself."""
    root = init_repo(tmp_path / "r")
    (root / ".crew").mkdir()
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": [{"paths": ["**"], "seconds": 1, "run": ["echo ok"],
                                  "why": "fixture"}], "default": [], "unmapped": "ignore"}),
        encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "map")
    (root / ".crew" / ".verify-verified-at").write_text(git(root, "rev-parse", "HEAD") + "\n",
                                                        encoding="utf-8")
    return root


def test_review_gate_fixture_is_verified_through_a_healthy_git(tmp_path):
    state, reason = review_gate.gate_state(str(_verified_repo(tmp_path)))

    assert state == review_gate.VERIFIED, reason


def test_review_gate_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = _verified_repo(tmp_path)
    _resolved_git_fails(monkeypatch, tmp_path)

    state, reason = review_gate.gate_state(str(root))

    assert (state, "fatal: broken" in reason) == (review_gate.UNKNOWN, True), reason


def test_review_gate_is_unknown_when_git_does_not_resolve(tmp_path, monkeypatch):
    root = _verified_repo(tmp_path)
    tool_fixtures.which_none(monkeypatch, "git")

    state, reason = review_gate.gate_state(str(root))

    assert (state, "git is not on PATH" in reason) == (review_gate.UNKNOWN, True), reason


# --- completion_audit: the tree listing refuses, it never passes ----------------

def _in_scope_change(tmp_path):
    root = make_repo(tmp_path, mode="block")
    ready(root)
    (root / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    return root


def _failing_c_subcommand(sub="diff-index"):
    """(sh, cmd) for a git that fails `git -C <dir> <sub>` and hands every
    other call to the real git: tool_fixtures.failing_subcommand reads `$1`,
    and every completion_audit call starts `-C <top>`. On Windows the cmd
    pass-through re-parses `%*`, which eats the `^` in the listing's own
    `rev-parse --verify <sha>^{commit}`, so that earlier call of the same
    listing fails instead (CI, windows-latest): either way only a resolved git
    can make the listing fail, and a bare one passes."""
    real = shutil.which("git")
    sh = (f"#!/bin/sh\nif [ \"$1\" = -C ] && [ \"$3\" = {sub} ]; then echo 'fatal: broken' >&2; "
          f"exit 128; fi\nexec '{real}' \"$@\"\n")
    cmd = (f"@echo off\r\nif \"%~1\"==\"-C\" if \"%~3\"==\"{sub}\" (\r\n  echo fatal: broken 1>&2\r\n"
           f"  exit /b 128\r\n)\r\n\"{real}\" %*\r\nexit /b %ERRORLEVEL%\r\n")
    return sh, cmd


def test_completion_audit_runs_the_git_which_resolves(tmp_path, monkeypatch):
    # Only the audit's own listing breaks; toplevel, scope base and merged main
    # are handed to the real git, so a pass here can only be a bare-name diff.
    root = _in_scope_change(tmp_path)
    tool_fixtures.which_only(monkeypatch, tmp_path / "resolved", "git", *_failing_c_subcommand())

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert (ok, "could not diff the tree" in " ".join(lines)) == (False, True), lines


def test_completion_audit_refuses_when_git_does_not_resolve(tmp_path, monkeypatch):
    root = _in_scope_change(tmp_path)
    tool_fixtures.which_none(monkeypatch, "git")

    ok, lines = completion_audit.audit(str(root), "T-1")

    assert ok is False, lines


# --- crew_ticket: the repository is not found through a failing git -------------

def test_crew_ticket_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    assert crew_ticket.toplevel(str(root)) is None


# --- merged_main: ancestry is could-not-tell, not True/False ---------------------

def test_merged_main_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    head = git(root, "rev-parse", "HEAD")
    _resolved_git_fails(monkeypatch, tmp_path)

    assert merged_main._is_ancestor(str(root), head, head) is None  # pylint: disable=protected-access


# --- verify_record: the tree snapshot and the refs digest are could-not-tell ----

def test_verify_record_tree_snapshot_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    assert verify_record.tree_snapshot(str(root)) is None


def test_verify_record_refs_digest_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    assert verify_record._refs_digest(str(root)) is None  # pylint: disable=protected-access


def _failing_arg(arg):
    """(sh, cmd) for a git that fails any call carrying `arg` as a whole
    argument and hands every other call to the real git, so one of
    tree_snapshot's two git sites breaks while the other answers. The cmd
    loop splits on `=` and stops at a `)`: fine for tree_snapshot's argv,
    which holds no parenthesis."""
    real = shutil.which("git")
    sh = (f"#!/bin/sh\nfor a in \"$@\"; do if [ \"$a\" = {arg} ]; then echo 'fatal: broken' >&2; "
          f"exit 128; fi; done\nexec '{real}' \"$@\"\n")
    cmd = (f"@echo off\r\nfor %%a in (%*) do if \"%%~a\"==\"{arg}\" (\r\n  echo fatal: broken 1>&2\r\n"
           f"  exit /b 128\r\n)\r\n\"{real}\" %*\r\nexit /b %ERRORLEVEL%\r\n")
    return sh, cmd


@pytest.mark.parametrize("arg", ["diff", "-v"], ids=["listing", "index-flags"])
def test_verify_record_tree_snapshot_each_site_runs_the_git_which_resolves(tmp_path, monkeypatch,
                                                                           arg):
    # "diff" breaks only the listing loop, "-v" only the skip-worktree probe.
    root = init_repo(tmp_path / "r")
    assert verify_record.tree_snapshot(str(root)) is not None  # the healthy git answers
    tool_fixtures.which_only(monkeypatch, tmp_path / "resolved", "git", *_failing_arg(arg))

    assert verify_record.tree_snapshot(str(root)) is None


def test_verify_record_tree_snapshot_is_none_when_git_does_not_resolve(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    tool_fixtures.which_none(monkeypatch, "git")

    assert verify_record.tree_snapshot(str(root), stable=True) is None


# --- verify_fingerprint: no head, no index, nothing changed inside -------------

def test_verify_fingerprint_head_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    assert verify_fingerprint._head(str(root)) == "no-head"  # pylint: disable=protected-access


@pytest.mark.parametrize("probe", ["_index_entries", "_sub_changed"])
def test_verify_fingerprint_listings_run_the_git_which_resolves(tmp_path, monkeypatch, probe):
    root = init_repo(tmp_path / "r")
    (root / "seed.txt").write_text("edited\n", encoding="utf-8")
    assert getattr(verify_fingerprint, probe)(str(root))  # the healthy git lists something
    _resolved_git_fails(monkeypatch, tmp_path)

    assert not getattr(verify_fingerprint, probe)(str(root))


def test_verify_fingerprint_head_says_no_git_when_git_does_not_resolve(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    tool_fixtures.which_none(monkeypatch, "git")

    assert verify_fingerprint._head(str(root)) == "no-git"  # pylint: disable=protected-access


# --- the review bundle's own git calls ------------------------------------------

def test_review_ledger_common_dir_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    with pytest.raises(review_ledger.LedgerError, match="fatal: broken"):
        review_ledger.common_dir(str(root))


def test_review_patch_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="fatal: broken"):
        review_patch._run_raw(str(root), ["rev-parse", "HEAD"])  # pylint: disable=protected-access


def test_review_patch_names_git_when_it_does_not_resolve(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    tool_fixtures.which_none(monkeypatch, "git")

    with pytest.raises(RuntimeError, match="git is not on PATH"):
        review_patch._run_raw(str(root), ["rev-parse", "HEAD"])  # pylint: disable=protected-access


def test_review_prompt_head_runs_the_git_which_resolves(tmp_path, monkeypatch):
    root = init_repo(tmp_path / "r")
    _resolved_git_fails(monkeypatch, tmp_path)

    assert review_prompt._head(str(root)) == ""  # pylint: disable=protected-access

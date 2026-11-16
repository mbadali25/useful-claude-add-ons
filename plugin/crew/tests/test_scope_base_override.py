"""A per-run base override: a PR that targets `qa` (not the repo-wide
`tickets.baseBranch`) is measured against `qa`. `CREW_BASE_BRANCH` is the
transport; `review_run.py --prepare --base-branch REF` sets it for the run.

Fixture: upstream `main` (seed), `development` three commits ahead, `qa` two
commits ahead of main; the clone's origin/HEAD is `main`, `fix/t-1` is cut
from `origin/qa`, and the repo config pins `development`.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import scope_base

_ROOT = context._ROOT  # pylint: disable=protected-access
_REVIEW_RUN_PY = os.path.join(_ROOT, "hooks", "scripts", "review_run.py")
_ENV = scope_base.BASE_BRANCH_ENV


def _git(root, *args):
    return subprocess.run(
        ("git",) + args, cwd=root, check=True, capture_output=True,
        text=True, stdin=subprocess.DEVNULL).stdout.strip()


def _commit(root, name):
    (root / name).write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"add {name}")


@pytest.fixture(scope="module", name="template")
def _template(tmp_path_factory):
    base = tmp_path_factory.mktemp("template")
    upstream = base / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    _git(upstream, "config", "user.email", "t@example.com")
    _git(upstream, "config", "user.name", "t")
    _commit(upstream, "seed.txt")
    for branch, names in (("development", ("d1.txt", "d2.txt", "d3.txt")),
                          ("qa", ("q1.txt", "q2.txt"))):
        _git(upstream, "checkout", "-q", "-b", branch, "main")
        for name in names:
            _commit(upstream, name)
    _git(upstream, "checkout", "-q", "main")
    clone = base / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)],
                   check=True, capture_output=True, text=True)
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "t")
    _git(clone, "remote", "set-head", "origin", "main")
    _git(clone, "checkout", "-q", "-b", "fix/t-1", "origin/qa")
    (clone / ".git" / "info" / "exclude").write_text(".crew/\n.work/\n", encoding="utf-8")
    (clone / ".crew").mkdir()
    (clone / ".crew" / "config.json").write_text(
        json.dumps({"tickets": {"baseBranch": "development"}}), encoding="utf-8")
    return base


@pytest.fixture(name="clone")
def _clone(tmp_path, template, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    dst = tmp_path / "w"
    shutil.copytree(template, dst)
    return dst / "clone"


def test_env_override_wins_over_the_repo_config(clone, monkeypatch):
    """Happy: CREW_BASE_BRANCH=qa beats tickets.baseBranch=development."""
    monkeypatch.setenv(_ENV, "qa")
    assert scope_base.base_branch(str(clone)) == ("origin/qa", None)


def test_unset_env_keeps_the_repo_config(clone):
    """Unset: today's behaviour, unchanged."""
    assert scope_base.base_branch(str(clone)) == ("origin/development", None)


def test_blank_env_is_unset(clone, monkeypatch):
    monkeypatch.setenv(_ENV, "   ")
    assert scope_base.base_branch(str(clone)) == ("origin/development", None)


def test_invalid_ref_is_a_problem_not_a_fallback(clone, monkeypatch):
    """Invalid ref: no base, a problem naming the env var; never origin/HEAD."""
    monkeypatch.setenv(_ENV, "no-such-branch")
    ref, problem = scope_base.base_branch(str(clone))
    assert ref is None
    assert _ENV in problem and "no-such-branch" in problem, problem


def test_cli_base_measures_against_the_override(clone):
    """The merge-base printed by `scope_base.py --base` is qa's tip for a branch
    cut from qa, where the configured development gives main."""
    script = os.path.join(_ROOT, "hooks", "scripts", "scope_base.py")
    cmd = [sys.executable, script, "--root", str(clone), "--base", "T-1"]
    env = dict(os.environ, **{_ENV: "qa"})
    done = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env,
                          stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == _git(clone, "rev-parse", "origin/qa")


def _prepare(clone, *extra):
    env = {k: v for k, v in os.environ.items() if k != _ENV}
    return subprocess.run(
        [sys.executable, _REVIEW_RUN_PY, "--root", str(clone), "--prepare",
         "--ticket", "T-1", *extra],
        capture_output=True, text=True, check=False, env=env, stdin=subprocess.DEVNULL)


def test_prepare_base_branch_flag_sets_the_base(clone):
    done = _prepare(clone, "--base-branch", "qa")
    assert f"BASE={_git(clone, 'rev-parse', 'origin/qa')}" in done.stdout, (
        done.stdout, done.stderr)


def test_prepare_base_branch_flag_invalid_ref_stops(clone):
    done = _prepare(clone, "--base-branch", "no-such-branch")
    assert done.returncode == 3, (done.returncode, done.stdout, done.stderr)
    assert "BASE=" not in done.stdout


def test_base_branch_flag_needs_prepare(clone):
    done = subprocess.run(
        [sys.executable, _REVIEW_RUN_PY, "--root", str(clone), "--base-branch", "qa"],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    assert done.returncode == 2 and "--base-branch" in done.stderr, done.stderr


def _head_sha(clone):
    return _git(clone, "rev-parse", "HEAD")


def test_override_beats_an_existing_exact_record(clone, monkeypatch):
    """BLOCK: a ticket started on development (exact record at that tip) then
    PR'd to qa is measured against qa's merge-base, not the recorded start."""
    _git(clone, "checkout", "-q", "-b", "fix/t-2", "origin/development")
    dev_tip = _git(clone, "rev-parse", "origin/development")
    scope_base._write(str(clone), {"T-1": {  # pylint: disable=protected-access
        "base": dev_tip, "from": "HEAD", "recordedAt": "2026-01-01T00:00:00+00:00"}})
    monkeypatch.setenv(_ENV, "qa")
    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert base == _git(clone, "merge-base", "HEAD", "origin/qa") != dev_tip, (
        base, source, reason)
    assert source != scope_base.RECORDED, (source, reason)
    assert "origin/qa" in reason or "qa" in reason, reason


def test_record_still_wins_without_an_override(clone):
    """Unset env: an exact record is still the answer."""
    seed = _git(clone, "rev-parse", "origin/main")
    scope_base._write(str(clone), {"T-1": {  # pylint: disable=protected-access
        "base": seed, "from": "HEAD", "recordedAt": "2026-01-01T00:00:00+00:00"}})
    base, source, _ = scope_base.resolve(str(clone), "T-1")
    assert (base, source) == (seed, scope_base.RECORDED)


@pytest.mark.parametrize("spelling", ["HEAD", "head-sha", "short-sha"])
def test_override_rejects_a_commit_that_is_not_a_branch(clone, monkeypatch, spelling):
    """FIX: HEAD or a SHA as the base would give an empty range; refuse it."""
    head = _head_sha(clone)
    value = {"HEAD": "HEAD", "head-sha": head, "short-sha": head[:10]}[spelling]
    monkeypatch.setenv(_ENV, value)
    ref, problem = scope_base.base_branch(str(clone))
    assert ref is None
    assert problem and _ENV in problem and "branch" in problem, problem


def test_override_rejects_a_tag(clone, monkeypatch):
    """A tag names a commit but is not a branch: refuse it as a base."""
    _git(clone, "tag", "v1", "origin/qa")
    monkeypatch.setenv(_ENV, "v1")
    ref, problem = scope_base.base_branch(str(clone))
    assert ref is None
    assert problem and _ENV in problem and "branch" in problem, problem


def test_override_accepts_a_fully_spelled_branch_ref(clone, monkeypatch):
    monkeypatch.setenv(_ENV, "refs/remotes/origin/qa")
    assert scope_base.base_branch(str(clone)) == ("refs/remotes/origin/qa", None)


def test_persist_override_keeps_other_bases_and_survives_a_corrupt_file(clone):
    root = str(clone)
    path = os.path.join(root, scope_base.OVERRIDE_RECORD)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert scope_base.persisted_override(root, "a" * 40) == ""
    scope_base.persist_override(root, "a" * 40, "qa")
    scope_base.persist_override(root, "b" * 40, "development")
    assert scope_base.persisted_override(root, "a" * 40) == "qa"
    assert scope_base.persisted_override(root, "b" * 40) == "development"
    assert scope_base.persisted_override(root, None) == ""
    assert scope_base.persisted_override(root, "c" * 40) == ""


def test_landing_reads_the_persisted_override(clone):
    """review_delta.landing measures against the branch the review was prepared
    against: HEAD (qa's tip) is inside qa, so with the override persisted the
    landing is looked for (could not tell: no merge), and without it the
    configured `development` does not hold HEAD."""
    import review_delta  # pylint: disable=import-outside-toplevel
    root = str(clone)
    base = _git(clone, "rev-parse", "origin/main")
    head = _head_sha(clone)
    assert review_delta.landing(root, base, head) == (None, None)
    scope_base.persist_override(root, base, "qa")
    landed, why = review_delta.landing(root, base, head)
    assert landed is None and why and review_delta.COULD_NOT_TELL in why, (landed, why)


def test_prepare_persists_the_override_for_later_checks(clone):
    """FIX: later receipt validation (merged_main.resolve, no env, no flag)
    reads the same branch the review was prepared against."""
    import merged_main  # pylint: disable=import-outside-toplevel
    done = _prepare(clone, "--base-branch", "qa")
    base = _git(clone, "rev-parse", "origin/qa")
    assert f"BASE={base}" in done.stdout, (done.stdout, done.stderr)
    assert merged_main.resolve(str(clone), base)["ref"] == "origin/qa"
    # a base the override was not prepared for still reads the config
    other = _git(clone, "rev-parse", "origin/main")
    assert merged_main.resolve(str(clone), other)["ref"] == "origin/development"

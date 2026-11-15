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

"""promote-gate's policy is the map COMMITTED IN THE SHA BEING DEPLOYED (L-0768).

Reported by the TSS-win session (crew 1.2.17, deploying from a linked git
worktree): both flavours read `.crew/verify.json` from the session's project
dir, so a `requireReview: false` waiver committed on the branch being deployed
was never seen, the main checkout's own waiver or dirt decided the worktree's
deploy instead, and `_promote_review.py` run by hand in the worktree exited 0
while the hook's call with the same arguments blocked.

The rule now: requires, rollback, requireHuman and requireReview come from
`git -C <tree> ls-tree <sha> -- .crew/verify.json`'s blob - what a checkout of
that sha reads - and the project dir's map only when the sha carries none.
Matching (which command deploys) and state (PROMOTIONS.md, approval markers)
stay in the project dir. The uncommitted-map guard judges the map that is
policy.

A guard that can BLOCK carries must-block and must-allow cases (repo
CLAUDE.md); each new branch has a mutation in promote_tree_mutations.py.
Every repository is built under tmp_path; `CLAUDE_PROJECT_DIR` names it.

The ps1 cases are `wallclock` (L-0759): the gate's 16s deadline counts from
PowerShell's start, and under `-n 16` contention start-up alone spends it.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
_GIT = shutil.which("git")
_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="PATH shims are POSIX scripts")

FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")),
    pytest.param("ps1", marks=[pytest.mark.skipif(_PWSH is None,
                                                  reason="no PowerShell 7 on this machine"),
                               pytest.mark.wallclock]),
]

_ROLLBACK = {"rollback": "none", "rollbackReason": "fixture"}
_WAIVER = {"requireReview": False, "reviewReason": "fixture: the branch's own waiver"}


def _map(dev=None, qa=None, requires=True):
    """development and qa, review required unless a waiver is merged in."""
    qa_env = {"deploy": "deploy-qa", **_ROLLBACK, **(qa or {})}
    if requires:
        qa_env["requires"] = ["development"]
    return {"environments": {"development": {"deploy": "deploy-dev", **_ROLLBACK, **(dev or {})},
                             "qa": qa_env}}


def _git(cwd, *args):
    return subprocess.run((_GIT,) + args, cwd=cwd, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


class Repo:
    """A main checkout (the project dir) and one linked worktree on `feature`,
    branched from it. Both start with the same committed map, review required."""

    def __init__(self, tmp_path):
        self.main = tmp_path / "main"
        self.main.mkdir()
        _git(self.main, "init", "-q", "-b", "main")
        _git(self.main, "config", "user.email", "t@example.invalid")
        _git(self.main, "config", "user.name", "T")
        _git(self.main, "config", "commit.gpgsign", "false")
        (self.main / ".gitignore").write_text(".crew/*\n!.crew/verify.json\n.work/\n",
                                              encoding="utf-8")
        (self.main / ".crew").mkdir()
        (self.main / ".work").mkdir()
        self.write(self.main, _map())
        (self.main / "app.txt").write_text("v1\n", encoding="utf-8")
        _git(self.main, "add", "-A")
        _git(self.main, "commit", "-q", "-m", "base")
        self.wt = tmp_path / "wt-l0768"
        _git(self.main, "worktree", "add", "-q", "-b", "feature", str(self.wt))
        (self.wt / "app.txt").write_text("v2\n", encoding="utf-8")
        _git(self.wt, "add", "-A")
        _git(self.wt, "commit", "-q", "-m", "feature")

    @staticmethod
    def write(where, doc):
        text = doc if isinstance(doc, str) else json.dumps(doc, indent=2) + "\n"
        (where / ".crew").mkdir(exist_ok=True)
        (where / ".crew" / "verify.json").write_text(text, encoding="utf-8")

    def commit(self, where, doc):
        self.write(where, doc)
        _git(where, "add", "-A")
        _git(where, "commit", "-q", "-m", "map")

    def head(self, where):
        return _git(where, "rev-parse", "HEAD")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return Repo(tmp_path)


def run_gate(flavour, repo, command, cwd, path=None):
    payload = {"tool_name": "Bash" if flavour == "sh" else "PowerShell",
               "tool_input": {"command": command}, "cwd": str(cwd)}
    child = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo.main))
    child.pop("CREW_PROMOTE_REVIEW_BUDGET", None)
    if path is not None:
        child["PATH"] = path
    if flavour == "sh":
        argv = [_BASH, (_SCRIPTS / "promote-gate.sh").as_posix()]
    else:
        child["OS"] = "Windows_NT"
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File",
                str(_SCRIPTS / "promote-gate.ps1")]
    proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                          check=False, env=child, cwd=str(repo.main), timeout=90)
    return proc.returncode, proc.stderr


# --- requireReview: the TSS-win case ---------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_waiver_committed_on_the_worktree_branch_admits(flavour, repo):
    """MUST ALLOW (the reported bug): the branch being deployed commits the
    waiver; the main checkout's map still requires review."""
    repo.commit(repo.wt, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_main_checkout_only_waiver_does_not_admit_a_worktree_deploy(flavour, repo):
    """MUST BLOCK: the main checkout's committed waiver is not the deployed
    sha's policy."""
    repo.commit(repo.main, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert "requires an accepted review" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_uncommitted_waiver_in_the_worktree_does_not_admit(flavour, repo):
    """MUST BLOCK: the deployed tree's own working copy is judged - an
    uncommitted map there is dirt."""
    repo.write(repo.wt, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert "is dirty" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_uncommitted_waiver_in_the_main_checkout_does_not_admit(flavour, repo):
    """MUST BLOCK: an uncommitted edit in the project dir is never policy."""
    repo.write(repo.main, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert "requires an accepted review" in err, err


# --- the uncommitted-map guard judges the map that is policy ---------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_dirty_main_checkout_map_does_not_block_a_clean_worktree_deploy(flavour, repo):
    """MUST ALLOW (bug 3): the project dir's dirty map judged a checkout
    unrelated to the deployed tree."""
    repo.commit(repo.wt, _map(dev=_WAIVER))
    repo.write(repo.main, _map(qa={"note": "an unrelated edit in progress"}))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_dirty_map_still_blocks_a_deploy_from_the_project_dir(flavour, repo):
    """MUST BLOCK: from the project dir the dirty map is the deployed tree's
    own working copy."""
    repo.write(repo.main, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.main)
    assert code == 2, err
    assert "verify.json in the project dir" in err and "has uncommitted changes" in err, err


# --- requires / rollback / requireHuman follow the same map ----------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_requires_dropped_only_in_the_main_checkout_still_applies(flavour, repo):
    """MUST BLOCK: the worktree's committed `requires` is the policy."""
    repo.commit(repo.main, _map(dev=_WAIVER, qa=_WAIVER, requires=False))
    repo.commit(repo.wt, _map(dev=_WAIVER, qa=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-qa", repo.wt)
    assert code == 2, err
    assert "'development' has no all-pass row" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_requires_dropped_on_the_deployed_branch_is_its_policy(flavour, repo):
    """MUST ALLOW (parity): the deployed sha's map is what a checkout of that
    sha would read, so the branch's committed policy applies."""
    repo.commit(repo.wt, _map(dev=_WAIVER, qa=_WAIVER, requires=False))
    code, err = run_gate(flavour, repo, "deploy-qa", repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_environment_the_deployed_map_does_not_declare_blocks(flavour, repo):
    """MUST BLOCK: matched by the project dir's map, absent from the policy -
    its requirements cannot be told, so they are not "none"."""
    doc = _map(qa=_WAIVER)
    del doc["environments"]["development"]
    repo.commit(repo.wt, doc)
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert "does not declare it" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_deployed_map_that_does_not_parse_blocks(flavour, repo):
    """MUST BLOCK: could not tell."""
    repo.commit(repo.wt, "{not json\n")
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert "parse" in err, err


_DISPATCH = "gh workflow run deploy.yml --ref main -f target=dev"


def _gh_map(sha_input):
    entry = {"workflow": "deploy.yml", "ref": "main", "inputs": {"target": "dev"}}
    if sha_input:
        entry["shaInput"] = "sha"
    return {"environments": {"development": {"deploy": [_DISPATCH], "github": entry,
                                             **_ROLLBACK, **_WAIVER}}}


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_github_sha_rule_comes_from_the_deployed_map(flavour, repo):
    """MUST BLOCK: the deployed branch's `github` entry sets `shaInput`; the
    main checkout's committed entry does not. The branch's rule applies."""
    repo.commit(repo.main, _gh_map(sha_input=False))
    repo.commit(repo.wt, _gh_map(sha_input=True))
    code, err = run_gate(flavour, repo, _DISPATCH, repo.wt)
    assert code == 2, err
    assert "carries no `-f sha=<sha>`" in err, err


def _replace_map(repo, doc):
    """A `refs/replace/` entry swapping the worktree HEAD's map blob for
    `doc`: nothing committed, sha, tree and `git status` unchanged."""
    old = _git(repo.wt, "rev-parse", "HEAD:.crew/verify.json")
    new = subprocess.run((_GIT, "hash-object", "-w", "--stdin"), cwd=repo.wt, check=True,
                         capture_output=True, text=True,
                         input=json.dumps(doc, indent=2) + "\n").stdout.strip()
    _git(repo.wt, "replace", old, new)


def _blocked_by(err, expected):
    """The expected refusal. On Windows `git status` re-reads the replaced
    blob (no stat-cache hit, CI run 38073578918), so the tree reads as dirty
    and the clean-tree check blocks first: also a block, never an admit."""
    return expected in err or (os.name == "nt" and "is dirty" in err)


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_replace_ref_cannot_waive_review(flavour, repo):
    """MUST BLOCK (L-0768 security review): the map is read with
    --no-replace-objects, so a replace ref cannot swap in a waiver."""
    _replace_map(repo, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert _blocked_by(err, "requires an accepted review"), err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_replace_ref_cannot_drop_requires(flavour, repo):
    """MUST BLOCK: the same for the VERDICT step's requirements."""
    repo.commit(repo.wt, _map(dev=_WAIVER, qa=_WAIVER))
    _replace_map(repo, _map(dev=_WAIVER, qa=_WAIVER, requires=False))
    code, err = run_gate(flavour, repo, "deploy-qa", repo.wt)
    assert code == 2, err
    assert _blocked_by(err, "'development' has no all-pass row"), err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_github_rule_matches_the_environment_ignoring_case(flavour, repo):
    """MUST BLOCK (Codex L-0768 r1): the deployed map spells the environment
    `Development`; its shaInput still applies to the matched `development`."""
    repo.commit(repo.main, _gh_map(sha_input=False))
    doc = _gh_map(sha_input=True)
    doc["environments"]["Development"] = doc["environments"].pop("development")
    repo.commit(repo.wt, doc)
    code, err = run_gate(flavour, repo, _DISPATCH, repo.wt)
    assert code == 2, err
    assert "carries no `-f sha=<sha>`" in err, err


def _stalling_git(tmp_path, pattern):
    shim_dir = tmp_path / "gitstall"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(f'#!/bin/sh\ncase "$*" in *"{pattern}"*) exec sleep 60 ;; esac\n'
                    f'exec "{_GIT}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return f"{shim_dir}{os.pathsep}{os.environ['PATH']}"


@_POSIX_ONLY
@pytest.mark.wallclock
@pytest.mark.parametrize("pattern", ["ls-tree --full-tree", "cat-file blob"])
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_stalled_map_read_blocks_inside_the_hook_timeout(flavour, pattern, repo, tmp_path):
    """MUST BLOCK (Codex L-0768 r1): every read of the deployed map is bounded
    by the gate's deadline; a hook that outlives its 20s timeout is not a
    block. `wallclock`: it times the deadline."""
    repo.commit(repo.wt, _map(dev=_WAIVER))
    start = time.monotonic()
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt,
                         path=_stalling_git(tmp_path, pattern))
    took = time.monotonic() - start
    assert code == 2, err
    assert took < 20, took


# --- a sha carrying no map: the project dir's map, as before ---------------

def _drop_map_on_branch(repo):
    _git(repo.wt, "rm", "-q", ".crew/verify.json")
    _git(repo.wt, "commit", "-q", "-m", "no map")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_sha_without_a_map_falls_back_to_the_project_dir(flavour, repo):
    """MUST ALLOW: no committed map in the sha - the project dir's committed
    map is the policy, as before L-0768."""
    _drop_map_on_branch(repo)
    repo.commit(repo.main, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_fallback_refuses_a_dirty_project_dir_map(flavour, repo):
    """MUST BLOCK: when the project dir's map is the policy, its uncommitted
    edit is refused."""
    _drop_map_on_branch(repo)
    repo.write(repo.main, _map(dev=_WAIVER))
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt)
    assert code == 2, err
    assert "carries no committed .crew/verify.json" in err, err


@_POSIX_ONLY
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_failed_listing_of_the_deployed_map_blocks(flavour, repo, tmp_path):
    """MUST BLOCK: a listing that fails is could-not-tell, never "no map"."""
    repo.commit(repo.wt, _map(dev=_WAIVER))
    shim_dir = tmp_path / "gitwrap"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(f'#!/bin/sh\ncase "$*" in *"ls-tree --full-tree"*) exit 128 ;; esac\n'
                    f'exec "{_GIT}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    code, err = run_gate(flavour, repo, "deploy-dev", repo.wt,
                         path=f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    assert code == 2, err
    assert "cannot tell which deployment map is policy" in err, err


# --- the reporter's repro: the helper alone ---------------------------------

def test_the_helper_from_the_project_dir_reads_the_worktree_branch_waiver(repo):
    """The hook runs the helper from the project dir with the worktree as its
    tree; it used to block there while a hand run inside the worktree passed."""
    repo.commit(repo.wt, _map(dev=_WAIVER))
    proc = subprocess.run([sys.executable, str(_SCRIPTS / "_promote_review.py"), str(repo.wt),
                           repo.head(repo.wt), str(int(time.time()) + 15), "development"],
                          cwd=str(repo.main), capture_output=True, text=True, check=False,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "", proc.stdout

"""promote-gate judges the tree the deploy RUNS FROM, not the session's checkout.

T-0505. Both flavours used to `cd "$CLAUDE_PROJECT_DIR"` and read HEAD and
`git status` there. A session that deploys from a clean linked worktree -- the
payload `cwd` after EnterWorktree, a leading `cd <worktree> &&`, or a
`git -C <worktree>` inside the command -- was therefore blocked by the main
checkout's dirt and told it was deploying the main checkout's sha (TSS, crew
1.0.75: "You would be deploying b853583a", while the command shipped 1581b5f5).
The reverse was worse and silent: a clean main checkout let a dirty or
wrong-sha worktree through.

This is a guard that can BLOCK, so the suite carries both directions (repo
CLAUDE.md, "Adding a hook"): must-allow cases prove the fix does not turn into
"block everything", must-block cases prove a worktree cannot launder a sha.
The main checkout's own state -- `.work/PROMOTIONS.md`, the
`.crew/.approved-<env>-<sha>` markers, `.crew/verify.json` -- stays the policy,
deliberately, and three cases pin that: a PASS row or an approval marker for
the MAIN checkout's sha does not admit the worktree's sha, and a marker planted
inside the worktree admits nothing.

Every repository here is built under `tmp_path`. `CLAUDE_PROJECT_DIR` points
at the fixture, never at this repo, and no real config is read or written.

The pwsh flavour runs wherever PowerShell 7 resolves, with `OS=Windows_NT` in
the child environment only: the `.ps1` stands down unless it can prove it is on
Windows, and the logic under test is git plumbing that behaves the same on
Linux. A machine with no pwsh skips those cases rather than failing them.
"""
import json
import os
import pathlib
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
_SH = _SCRIPTS / "promote-gate.sh"
_PS1 = _SCRIPTS / "promote-gate.ps1"

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()

FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(
        _BASH is None, reason="no MSYS/POSIX bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        _PWSH is None, reason="no PowerShell 7 on this machine")),
]

_WT_NAME = "deploy-worktree-t0505"

_VERIFY = {
    "environments": {
        "development": {"deploy": "deploy-dev", "rollback": "none",
                        "rollbackReason": "fixture"},
        "qa": {"deploy": "deploy-qa", "requires": ["development"],
               "rollback": "none", "rollbackReason": "fixture"},
        "prod": {"deploy": "deploy-prod", "requireHuman": True,
                 "rollback": "none", "rollbackReason": "fixture"},
    }
}


def _git(cwd, *args):
    return subprocess.run(("git",) + args, cwd=cwd, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def _init(root):
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "commit.gpgsign", "false")


class Repo:  # pylint: disable=too-few-public-methods
    """A main checkout, one linked worktree one commit ahead, a foreign repo."""

    def __init__(self, tmp_path):
        self.main = tmp_path / "main"
        _init(self.main)
        # The layout this repository and crew-setup ship: `.crew/*` ignored
        # with verify.json re-admitted, `.work/` ignored. The gate's own
        # in-flight marker must never dirty the tree it judges.
        (self.main / ".gitignore").write_text(
            ".crew/*\n!.crew/verify.json\n.work/\n", encoding="utf-8")
        (self.main / ".crew").mkdir()
        (self.main / ".work").mkdir()
        (self.main / ".crew" / "verify.json").write_text(
            json.dumps(_VERIFY, indent=2) + "\n", encoding="utf-8")
        (self.main / "README.md").write_text("main\n", encoding="utf-8")
        _git(self.main, "add", "-A")
        _git(self.main, "commit", "-q", "-m", "fixture")
        self.main_sha = _git(self.main, "rev-parse", "--short", "HEAD")
        self.main_full = _git(self.main, "rev-parse", "HEAD")

        self.wt = tmp_path / _WT_NAME
        _git(self.main, "worktree", "add", "-q", "-b", "feature", str(self.wt))
        (self.wt / "feature.txt").write_text("feature\n", encoding="utf-8")
        _git(self.wt, "add", "-A")
        _git(self.wt, "commit", "-q", "-m", "feature")
        self.wt_sha = _git(self.wt, "rev-parse", "--short", "HEAD")
        self.wt_full = _git(self.wt, "rev-parse", "HEAD")
        assert self.wt_sha != self.main_sha

        self.foreign = tmp_path / "foreign"
        _init(self.foreign)
        (self.foreign / ".crew").mkdir()
        (self.foreign / ".crew" / "verify.json").write_text(
            json.dumps(_VERIFY), encoding="utf-8")
        (self.foreign / "x.txt").write_text("x\n", encoding="utf-8")
        _git(self.foreign, "add", "-A", "-f")
        _git(self.foreign, "commit", "-q", "-m", "foreign")

        self.outside = tmp_path / "not-a-repo"
        self.outside.mkdir()

    def dirty_main(self):
        (self.main / "scratch-from-another-session.txt").write_text(
            "pending\n", encoding="utf-8")

    def dirty_wt(self):
        (self.wt / "uncommitted.txt").write_text("oops\n", encoding="utf-8")

    def promotions(self, *rows):
        body = ["| when | env | sha | smoke | regression | verify | by |",
                "|---|---|---|---|---|---|---|"]
        body += [f"| 2026-09-30 | {env} | {sha} | pass | pass | pass | t |"
                 for env, sha in rows]
        (self.main / ".work" / "PROMOTIONS.md").write_text(
            "\n".join(body) + "\n", encoding="utf-8")

    def in_flight(self):
        path = self.main / ".crew" / ".deploy-in-flight"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return Repo(tmp_path)


def run_gate(flavour, repo, command, cwd=None):
    """Run one flavour as Claude Code would: the payload on stdin, the project
    dir in the environment. `cwd=None` leaves `cwd` out of the payload, which
    is what an older Claude Code sends."""
    payload = {"tool_name": "Bash" if flavour == "sh" else "PowerShell",
               "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo.main))
    if flavour == "sh":
        argv = [_BASH, _SH.as_posix()]
    else:
        env["OS"] = "Windows_NT"
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(_PS1)]
    proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True,
                          text=True, check=False, env=env, cwd=str(repo.main),
                          timeout=120)
    return proc.returncode, proc.stderr


def _cd(flavour, path):
    """A leading directory change in the syntax of the tool being judged."""
    return f"cd {path} && " if flavour == "sh" else f"cd {path}; "


# --- must-allow -------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_clean_worktree_deploys_while_the_main_checkout_is_dirty(flavour, repo):
    """The TSS repro: payload cwd = a clean worktree, main checkout dirty."""
    repo.dirty_main()
    code, err = run_gate(flavour, repo, "deploy-dev", cwd=repo.wt)
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.wt_sha}", \
        "the in-flight marker lands in the project dir and names the sha deployed"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_leading_cd_into_a_clean_worktree_deploys_from_a_dirty_main(flavour, repo):
    repo.dirty_main()
    code, err = run_gate(flavour, repo, _cd(flavour, repo.wt) + "deploy-dev",
                         cwd=repo.main)
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.wt_sha}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_git_dash_C_names_the_tree_being_deployed(flavour, repo):
    repo.dirty_main()
    code, err = run_gate(
        flavour, repo, f"deploy-dev --ref $(git -C {repo.wt} rev-parse HEAD)",
        cwd=repo.main)
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.wt_sha}"


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_literal_sha_equal_to_the_trees_head_deploys(flavour, repo):
    code, err = run_gate(flavour, repo, f"deploy-dev --ref {repo.wt_full}",
                         cwd=repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_pass_row_for_the_worktree_sha_admits_it(flavour, repo):
    """Control for the laundering case below: the row that names the sha
    being deployed, in the project dir's PROMOTIONS.md, is what admits it."""
    repo.promotions(("development", repo.wt_sha))
    code, err = run_gate(flavour, repo, "deploy-qa", cwd=repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_approval_marker_for_the_worktree_sha_admits_it(flavour, repo):
    (repo.main / ".crew" / f".approved-prod-{repo.wt_sha}").write_text(
        "", encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-prod", cwd=repo.wt)
    assert code == 0, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_no_payload_cwd_judges_the_project_dir_as_before(flavour, repo):
    code, err = run_gate(flavour, repo, "deploy-dev")
    assert code == 0, err
    assert repo.in_flight() == f"development {repo.main_sha}"


# --- must-block -------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_dirty_worktree_blocks_even_when_main_is_clean(flavour, repo):
    repo.dirty_wt()
    code, err = run_gate(flavour, repo, "deploy-dev", cwd=repo.wt)
    assert code == 2, err
    assert "dirty" in err and _WT_NAME in err, err
    assert repo.wt_sha in err, "the block names the sha being deployed"
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_clean_root_does_not_launder_a_cd_into_a_dirty_worktree(flavour, repo):
    repo.dirty_wt()
    code, err = run_gate(flavour, repo, _cd(flavour, repo.wt) + "deploy-dev",
                         cwd=repo.main)
    assert code == 2, err
    assert "dirty" in err and _WT_NAME in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_worktree_of_a_different_repository_blocks(flavour, repo):
    code, err = run_gate(flavour, repo, "deploy-dev", cwd=repo.foreign)
    assert code == 2, err
    assert "different repository" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_cwd_outside_any_worktree_blocks(flavour, repo):
    code, err = run_gate(flavour, repo, "deploy-dev", cwd=repo.outside)
    assert code == 2, err
    assert "not inside a git worktree" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_pass_row_for_the_main_sha_does_not_admit_the_worktree_sha(flavour, repo):
    repo.promotions(("development", repo.main_sha))
    code, err = run_gate(flavour, repo, "deploy-qa", cwd=repo.wt)
    assert code == 2, err
    assert f"no all-pass row for sha {repo.wt_sha}" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_require_human_with_no_marker_for_the_worktree_sha_blocks(flavour, repo):
    (repo.main / ".crew" / f".approved-prod-{repo.main_sha}").write_text(
        "", encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-prod", cwd=repo.wt)
    assert code == 2, err
    assert f".approved-prod-{repo.wt_sha}" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_marker_planted_in_the_worktree_admits_nothing(flavour, repo):
    """State is read from the project dir. A worktree's own gitignored
    `.crew/` is somewhere anybody can write a marker for any sha."""
    (repo.wt / ".crew").mkdir(exist_ok=True)
    (repo.wt / ".crew" / f".approved-prod-{repo.wt_sha}").write_text(
        "", encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-prod", cwd=repo.wt)
    assert code == 2, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_literal_sha_that_is_not_the_trees_head_blocks(flavour, repo):
    """The first TSS repro's shape: `ref=<literal>` from a tree at another
    commit. The PASS rows would be checked for one sha while another shipped."""
    code, err = run_gate(flavour, repo, f"deploy-dev --ref {repo.main_full}",
                         cwd=repo.wt)
    assert code == 2, err
    assert repo.main_full[:7] in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_command_naming_two_trees_blocks(flavour, repo):
    code, err = run_gate(
        flavour, repo,
        f"deploy-dev --a $(git rev-parse HEAD) --b $(git -C {repo.wt} rev-parse HEAD)",
        cwd=repo.main)
    assert code == 2, err
    assert "more than one tree" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_unresolvable_directory_blocks(flavour, repo):
    target = "$DEPLOY_DIR" if flavour == "sh" else "$env:DEPLOY_DIR"
    code, err = run_gate(flavour, repo, _cd(flavour, target) + "deploy-dev",
                         cwd=repo.wt)
    assert code == 2, err
    assert "cannot tell which directory" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_uncommitted_edits_to_the_deploy_map_block(flavour, repo):
    """The neighbour case the fix opens: the main checkout's dirt no longer
    blocks a worktree deploy, and the deploy map is read from the main
    checkout -- so an uncommitted edit to it must not become policy."""
    path = repo.main / ".crew" / "verify.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    del doc["environments"]["qa"]["requires"]
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    code, err = run_gate(flavour, repo, "deploy-qa", cwd=repo.wt)
    assert code == 2, err
    assert "uncommitted" in err and "verify.json" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_cd_after_the_start_of_the_command_blocks(flavour, repo):
    """Neighbour of the leading-cd case. `true && cd <wt> && deploy` runs the
    deploy in the worktree, but the chain the gate reads ends at `true`, so it
    would judge the main checkout -- whose PASS row then admits the worktree's
    unpromoted sha. Refuse and ask for the cd to come first."""
    repo.promotions(("development", repo.main_sha))
    lead = "true && " if flavour == "sh" else "echo x; "
    code, err = run_gate(flavour, repo, lead + _cd(flavour, repo.wt) + "deploy-qa",
                         cwd=repo.main)
    assert code == 2, err
    assert "changes directory after it starts" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_git_dir_pointing_elsewhere_blocks(flavour, repo):
    code, err = run_gate(
        flavour, repo,
        f"deploy-dev --ref $(git --git-dir={repo.wt}/.git rev-parse HEAD)",
        cwd=repo.main)
    assert code == 2, err
    assert "--git-dir" in err, err

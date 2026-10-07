"""Publishing rules for the generated Markdown, and the docs-only PR gate.

Every shell fragment here is the RENDERED one, run with bash against real
throwaway git repositories (a bare `origin` plus a clone) - nothing is
re-implemented in Python except where a test says so:

  - docs-only detection (CHANGED_SH): a merge-base diff, never a path filter
    or `condition.changesets`; "could not tell" fails, it never passes;
  - the GitHub tier-1 gate PASSes a docs-only PR ("no scannable changes") and
    the Bitbucket PR step exits 0 before bootstrapping any scanner;
  - self-commits land on the branch only, never the default branch, carry
    `[skip ci]` plus the self-commit mark, commit nothing when nothing
    changed, and refuse to loop;
  - the `if:` guards keep `contents: write` off the default branch and off
    the weekly sweep, and no publishing job or step can see a secret.

Git runs with an isolated configuration (no global or system config, so no
user hook or template reaches these repositories).
"""
import json
import os
import re
import subprocess
from pathlib import Path

import ci_render
import pytest
import yaml
from test_ci_triggers import _truthy, evaluate, plain, pr_event, render

PLUGIN = Path(__file__).resolve().parent.parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "monorepo"
MARK = ci_render.SELF_COMMIT_MARK


# --------------------------------------------------------------------------
# throwaway repositories
# --------------------------------------------------------------------------

def git_env(tmp_path):
    cfg = tmp_path / "gitconfig"
    cfg.write_text("", encoding="utf-8")
    return {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "GIT_CONFIG_GLOBAL": str(cfg),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.test",
            "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.test"}


class Repo:
    """origin (bare) + a working clone on `main` seeded from the monorepo fixture."""

    def __init__(self, tmp_path, seed=FIXTURE):
        self.env = git_env(tmp_path)
        self.origin = tmp_path / "origin.git"
        self.work = tmp_path / "work"
        self.git_at(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git_at(tmp_path, "clone", "-q", str(self.origin), str(self.work))
        self.git("checkout", "-q", "-B", "main")
        if seed:
            subprocess.run(["cp", "-R", f"{seed}/.", str(self.work)], check=True)
        else:
            (self.work / "README.md").write_text("seed\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "seed")
        self.git("push", "-q", "origin", "main")

    def git_at(self, cwd, *args, check=True):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True,
                              check=check).stdout.strip()

    def git(self, *args, check=True):
        return self.git_at(self.work, *args, check=check)

    def origin_log(self, branch):
        return self.git_at(self.origin, "log", "--format=%s", branch, check=False).splitlines()

    def write(self, rel, text):
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, msg, *paths):
        self.git("add", *(paths or ["-A"]))
        self.git("commit", "-q", "-m", msg)

    def branch(self, name):
        self.git("checkout", "-q", "-b", name)

    def run(self, script, **env):
        return subprocess.run(["bash", "-c", script], cwd=self.work, env=dict(self.env, **env),
                              capture_output=True, text=True, check=False)


@pytest.fixture()
def repo(tmp_path):
    return Repo(tmp_path)


def stale_the_inventory(repo):
    decl = repo.work / "billing-portal" / "public-endpoint.md"
    decl.write_text(decl.read_text(encoding="utf-8").replace("https://billing.example.test",
                                                             "https://portal.example.test"), encoding="utf-8")
    repo.commit("change the declared url")


# --------------------------------------------------------------------------
# docs-only detection and the gate
# --------------------------------------------------------------------------

def changed(repo, base="main"):
    out = repo.work.parent / "gh-output"
    script = ci_render.CHANGED_SH + '\necho "scannable=$scannable" >> "$GITHUB_OUTPUT"'
    p = repo.run(script, GIZMODUCK_DIFF_BASE=base, GITHUB_OUTPUT=str(out))
    return p.returncode, out.read_text(encoding="utf-8").strip() if out.exists() else ""


@pytest.mark.parametrize("files,expected", [
    ({"README.md": "x", "docs/guide.md": "y"}, "scannable=false"),
    ({"orders-api/NOTES.md": "x", "docs/img/arch.png": "y"}, "scannable=false"),
    ({"endpoints-inventory.md": "x"}, "scannable=false"),
    ({"README.md": "x", "orders-api/Program.cs": "y"}, "scannable=true"),
    ({"docs/run.sh": "x"}, "scannable=false"),      # docs/** is docs, whatever the extension
    ({"docsite/app.js": "x"}, "scannable=true"),
])
def test_changes_job_decides_from_the_merge_base_diff(repo, files, expected):
    repo.branch("feature/x")
    for rel, text in files.items():
        repo.write(rel, text)
    repo.commit("change")

    assert changed(repo) == (0, expected)


def test_a_code_commit_followed_by_a_docs_commit_is_still_scannable(repo):
    """The tip commit alone is docs-only - the push is not. condition.changesets
    looked at the tip (measured on a Bitbucket pipeline); this does not."""
    repo.branch("feature/x")
    repo.write("orders-api/Program.cs", "code")
    repo.commit("code")
    repo.write("README.md", "typo fix")
    repo.commit("docs")

    assert changed(repo) == (0, "scannable=true")


def test_changes_job_fails_when_it_cannot_tell(repo):
    rc, out = changed(repo, base="0" * 40)
    assert rc == 2 and out == ""


def _gate(ev, **env):
    _, gh = render()
    job = gh[ci_render.PR_FILE]["jobs"]["gate"]
    base = {"GIZMODUCK_APPLIES": str(_truthy(evaluate(job["env"]["GIZMODUCK_APPLIES"], ev["ctx"]))).lower(),
            "IMAGE_RESULT": "skipped", "BOOT_RESULT": "skipped", "PATH": os.environ.get("PATH", "")}
    return subprocess.run(["bash", "-c", job["steps"][0]["run"]], env=dict(base, **env), capture_output=True,
                          text=True, check=False)


def test_docs_only_pr_gate_passes_with_no_scannable_changes():
    ev = pr_event(changed=("README.md",))
    _, gh = render()
    assert "paths-ignore" not in (gh[ci_render.PR_FILE].get("on", gh[ci_render.PR_FILE].get(True))["pull_request"])
    assert not _truthy(evaluate(gh[ci_render.PR_FILE]["jobs"]["scan"]["if"], ev["ctx"]))

    p = _gate(ev, CHANGES_RESULT="success", SCANNABLE="false")

    assert p.returncode == 0 and "gate PASS - no scannable changes" in p.stdout, p.stdout


@pytest.mark.parametrize("env,needle", [
    ({"CHANGES_RESULT": "failure", "SCANNABLE": ""}, "could not tell what this PR changed"),
    ({"CHANGES_RESULT": "skipped", "SCANNABLE": ""}, "could not tell what this PR changed"),
    ({"CHANGES_RESULT": "success", "SCANNABLE": ""}, "reported no verdict"),
    ({"CHANGES_RESULT": "success", "SCANNABLE": "true"}, "did not pass"),   # scannable, and nothing scanned
])
def test_gate_fails_when_the_docs_only_verdict_is_missing_or_the_scan_did_not_run(env, needle):
    p = _gate(pr_event(), **env)
    assert p.returncode == 1 and needle in p.stdout, p.stdout


def test_gate_passes_a_scannable_pr_only_on_a_successful_scan():
    assert _gate(pr_event(), CHANGES_RESULT="success", SCANNABLE="true", IMAGE_RESULT="success").returncode == 0


def _bb_pr_changed_items():
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    (pr,) = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    return [x for x in pr["script"] if "GIZMODUCK_DIFF_BASE=FETCH_HEAD" in x]


@pytest.mark.parametrize("rel,scanned", [("README.md", False), ("orders-api/Program.cs", True)])
def test_bitbucket_pr_step_passes_docs_only_before_any_scanner(repo, rel, scanned):
    (item,) = _bb_pr_changed_items()
    repo.branch("feature/x")
    repo.write(rel, "change")
    repo.commit("change")

    p = repo.run(item + "\necho SCANNED", BITBUCKET_PR_DESTINATION_BRANCH="main")

    assert p.returncode == 0 and ("SCANNED" in p.stdout) is scanned, p.stdout + p.stderr
    assert ("check PASS - no scannable changes" in p.stdout) is (not scanned)


def test_bitbucket_pr_step_fails_when_the_destination_cannot_be_fetched(repo):
    (item,) = _bb_pr_changed_items()
    p = repo.run(item + "\necho SCANNED", BITBUCKET_PR_DESTINATION_BRANCH="no-such-branch")
    assert p.returncode == 2 and "SCANNED" not in p.stdout


def test_bitbucket_pr_step_passes_a_docs_only_fork_pr_with_no_read_token(repo):
    """A fork's pull request never gets GIZMODUCK_BB_READ_TOKEN. Docs-only
    detection needs no secret at all, so it must be decided - and a
    docs-only PR passed - before the draft check that DOES need the token
    ever runs; otherwise a docs-only fork PR fails for a reason that has
    nothing to do with what it changed."""
    bb = _bb()
    (pr,) = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    script = "\n".join(pr["script"])
    repo.branch("feature/x")
    repo.write("README.md", "docs change")
    repo.commit("docs change")

    p = repo.run(script + "\necho SCANNED", BITBUCKET_PR_DESTINATION_BRANCH="main", BITBUCKET_PR_ID="7")

    assert p.returncode == 0 and "SCANNED" not in p.stdout, p.stdout + p.stderr
    assert "check PASS - no scannable changes" in p.stdout
    assert "GIZMODUCK_BB_READ_TOKEN" not in p.stdout


# --------------------------------------------------------------------------
# the self-commit
# --------------------------------------------------------------------------

def self_commit(repo, branch, what="endpoints-inventory.md", **env):
    return repo.run(ci_render.SELF_COMMIT_SH, GIZMODUCK_PUBLISH_BRANCH=branch, GIZMODUCK_DEFAULT_BRANCH="main",
                    GIZMODUCK_PUBLISH_FILES=what, GIZMODUCK_PUBLISH_WHAT=what, **env)


def test_self_commit_lands_on_the_branch_with_skip_ci(repo):
    repo.branch("feature/x")
    repo.write("endpoints-inventory.md", "regenerated\n")

    p = self_commit(repo, "feature/x")

    assert p.returncode == 0, p.stdout + p.stderr
    top = repo.origin_log("feature/x")[0]
    assert "[skip ci]" in top and MARK in top
    assert repo.origin_log("main") == ["seed"]


@pytest.mark.parametrize("branch", ["main", "refs/heads/main", ""])
def test_self_commit_never_commits_to_the_default_branch(repo, branch):
    repo.write("endpoints-inventory.md", "regenerated\n")

    p = self_commit(repo, branch)

    assert p.returncode == 0 and "verify-only" in p.stdout
    assert repo.origin_log("main") == ["seed"]
    assert repo.git("log", "--format=%s") == "seed", "not even a local commit"


def test_self_commit_commits_nothing_when_nothing_changed(repo):
    repo.branch("feature/x")
    repo.git("push", "-q", "origin", "feature/x")
    p = self_commit(repo, "feature/x")
    assert p.returncode == 0 and "nothing to commit" in p.stdout
    assert repo.origin_log("feature/x") == ["seed"]


def test_loop_guard_refuses_a_second_self_commit(repo):
    repo.branch("feature/x")
    repo.write("endpoints-inventory.md", "first\n")
    assert self_commit(repo, "feature/x").returncode == 0
    repo.write("endpoints-inventory.md", "second - the generator is not deterministic\n")

    p = self_commit(repo, "feature/x")

    assert p.returncode == 1 and "loop guard" in p.stdout
    assert len(repo.origin_log("feature/x")) == 2


def test_a_rejected_push_fails_the_step(repo):
    repo.branch("feature/x")
    repo.git("push", "-q", "origin", "feature/x")
    other = Path(str(repo.work) + "-other")
    repo.git_at(repo.work.parent, "clone", "-q", "-b", "feature/x", str(repo.origin), str(other))
    (other / "x.txt").write_text("moved", encoding="utf-8")
    repo.git_at(other, "add", "x.txt")
    repo.git_at(other, "commit", "-q", "-m", "someone else")
    repo.git_at(other, "push", "-q", "origin", "feature/x")
    repo.write("endpoints-inventory.md", "regenerated\n")

    p = self_commit(repo, "feature/x")

    assert p.returncode == 1 and "could not push" in p.stdout


# --------------------------------------------------------------------------
# the rendered inventory steps, end to end
# --------------------------------------------------------------------------

def _bb():
    files, _ = render()
    return yaml.safe_load(files["bitbucket-pipelines.yml"])


def _bb_step_script(pipeline_path):
    node = _bb()["pipelines"]
    for key in pipeline_path:
        node = node[key]
    return "\n".join(node[0]["step"]["script"])


def test_bitbucket_branch_step_commits_the_regenerated_inventory_on_the_branch(repo):
    repo.branch("feature/x")
    stale_the_inventory(repo)
    repo.git("push", "-q", "origin", "feature/x")

    p = repo.run(_bb_step_script(["default"]), BITBUCKET_BRANCH="feature/x", BITBUCKET_CLONE_DIR=str(repo.work),
                 GIZMODUCK_HOME=str(PLUGIN))

    assert p.returncode == 0, p.stdout + p.stderr
    assert MARK in repo.origin_log("feature/x")[0]
    assert "https://portal.example.test" in repo.git_at(repo.origin, "show", "feature/x:endpoints-inventory.md")
    assert repo.origin_log("main") == ["seed"]


def test_bitbucket_branch_step_on_the_default_branch_pushes_nothing(repo):
    stale_the_inventory(repo)
    repo.git("push", "-q", "origin", "main")

    p = repo.run(_bb_step_script(["default"]), BITBUCKET_BRANCH="main", BITBUCKET_CLONE_DIR=str(repo.work),
                 GIZMODUCK_HOME=str(PLUGIN))

    assert p.returncode == 0 and "verify-only" in p.stdout
    assert repo.origin_log("main") == ["change the declared url", "seed"]


@pytest.mark.parametrize("stale,rc", [(False, 0), (True, 1)])
def test_bitbucket_main_step_verifies_and_never_writes(repo, stale, rc):
    if stale:
        stale_the_inventory(repo)
    before = repo.git("rev-parse", "HEAD")

    p = repo.run(_bb_step_script(["branches", "main"]), BITBUCKET_BRANCH="main",
                 BITBUCKET_CLONE_DIR=str(repo.work), GIZMODUCK_HOME=str(PLUGIN))

    assert p.returncode == rc, p.stdout + p.stderr
    assert ("GIZMODUCK_INVENTORY_STALE" in p.stderr) is stale
    assert repo.git("rev-parse", "HEAD") == before and not repo.git("status", "--porcelain")


def _gh_inventory():
    _, gh = render()
    return gh[ci_render.INVENTORY_FILE]


def _gh_publish_run(repo, branch):
    job = _gh_inventory()["jobs"]["publish"]
    step = job["steps"][-1]
    env = {k: str(v) for k, v in job["env"].items() if "${{" not in str(v)}
    return repo.run(step["run"], GIZMODUCK_HOME=str(PLUGIN), GITHUB_WORKSPACE=str(repo.work),
                    GIZMODUCK_DEFAULT_BRANCH="main", GIZMODUCK_PUBLISH_BRANCH=branch, GH_TOKEN="fake-token",
                    GITHUB_SERVER_URL="https://git.example.test", **env)


def test_github_publish_job_commits_on_the_branch(repo):
    repo.branch("feature/x")
    stale_the_inventory(repo)
    repo.git("push", "-q", "origin", "feature/x")

    p = _gh_publish_run(repo, "feature/x")

    assert p.returncode == 0, p.stdout + p.stderr
    assert "[skip ci]" in repo.origin_log("feature/x")[0]
    assert repo.origin_log("main") == ["seed"]


def test_github_publish_job_script_refuses_the_default_branch_even_if_its_if_guard_is_bypassed(repo):
    stale_the_inventory(repo)
    repo.git("push", "-q", "origin", "main")

    p = _gh_publish_run(repo, "main")

    assert p.returncode == 0 and "verify-only" in p.stdout
    assert repo.origin_log("main") == ["change the declared url", "seed"]


# --------------------------------------------------------------------------
# GitHub `if:` guards
# --------------------------------------------------------------------------

def push(ref, message="work"):
    ev = plain("push", head_commit={"message": message})
    ev["ctx"]["github"]["ref"] = ref
    ev["ctx"]["github"]["ref_name"] = ref.split("refs/heads/", 1)[-1]
    return ev


def runs(job, ev):
    return _truthy(evaluate(job["if"], ev["ctx"]))


@pytest.mark.parametrize("ev,verify,publish,comment", [
    (push("refs/heads/main"), True, False, False),
    (push("refs/heads/feature/x"), False, True, False),
    (push("refs/heads/release/2.4"), False, True, False),
    (push("refs/heads/feature/x", f"gizmoduck: regenerate endpoints-inventory.md [skip ci] {MARK}"),
     False, False, False),
    (push("refs/tags/v1.0"), False, False, False),
    (pr_event(), False, False, True),
    (pr_event(draft=True), False, False, False),
])
def test_github_inventory_jobs_write_only_off_the_default_branch(ev, verify, publish, comment):
    jobs = _gh_inventory()["jobs"]
    if ev["name"] == "pull_request":
        ev["ctx"]["github"]["event"]["pull_request"]["head"] = {"repo": {"full_name": "acme/app"}}
    assert (runs(jobs["verify"], ev), runs(jobs["publish"], ev), runs(jobs["comment"], ev)) == \
        (verify, publish, comment)


def test_github_inventory_comment_skips_a_fork_pull_request():
    ev = pr_event()
    ev["ctx"]["github"]["event"]["pull_request"]["head"] = {"repo": {"full_name": "attacker/app"}}
    assert not runs(_gh_inventory()["jobs"]["comment"], ev)


def _endpoint_event(name, ref="refs/heads/main", deployment_ref=None, ref_type="branch"):
    ev = plain(name)
    ev["ctx"]["github"]["ref"] = ref
    ev["ctx"]["github"]["ref_name"] = ref.split("refs/heads/", 1)[-1].split("refs/tags/", 1)[-1]
    ev["ctx"]["github"]["ref_type"] = ref_type
    if deployment_ref:
        ev["ctx"]["github"]["event"]["deployment"] = {"ref": deployment_ref}
    ev["ctx"]["needs"] = {"scan": {"result": "success"}, "scan-bootstrap": {"result": "skipped"}}
    return ev


@pytest.mark.parametrize("ev,publishes", [
    (_endpoint_event("workflow_dispatch", "refs/heads/feature/x"), True),
    (_endpoint_event("workflow_dispatch", "refs/heads/main"), False),
    (_endpoint_event("deployment_status", deployment_ref="release/2.4"), True),
    (_endpoint_event("deployment_status", deployment_ref="main"), False),
    (_endpoint_event("deployment_status", deployment_ref="refs/heads/main"), False),
    (_endpoint_event("schedule"), False),
    (_endpoint_event("schedule", "refs/heads/feature/x"), False),     # a sweep never commits
])
def test_github_scan_report_is_committed_only_off_the_default_branch_and_never_by_the_sweep(ev, publishes):
    _, gh = render()
    job = gh[ci_render.ENDPOINTS_FILE]["jobs"]["publish-report"]
    assert runs(job, ev) is publishes


def test_github_scan_report_is_not_committed_for_a_manual_run_on_a_tag():
    """A `workflow_dispatch` run on a tag falls to `github.ref_name` for its
    branch, and a tag's short name can equal a branch name (release/1) -
    checking it out and pushing HEAD there would create/overwrite that
    branch. `github.ref_type` is 'tag' here, never 'branch'."""
    _, gh = render()
    job = gh[ci_render.ENDPOINTS_FILE]["jobs"]["publish-report"]
    ev = _endpoint_event("workflow_dispatch", "refs/tags/release/1", ref_type="tag")
    assert not runs(job, ev)


def test_github_scan_report_is_not_committed_when_no_scan_ran():
    _, gh = render()
    job = gh[ci_render.ENDPOINTS_FILE]["jobs"]["publish-report"]
    ev = _endpoint_event("workflow_dispatch", "refs/heads/feature/x")
    ev["ctx"]["needs"] = {"scan": {"result": "skipped"}, "scan-bootstrap": {"result": "skipped"}}
    assert not runs(job, ev)


# --------------------------------------------------------------------------
# no secret reaches a self-commit
# --------------------------------------------------------------------------

_SECRET_REF = re.compile(r"\$\{?(" + "|".join(ci_render.TRUSTED_SECRETS) + r")\b")


def test_no_publishing_job_or_step_can_see_a_secret():
    files, gh = render()
    assert "secrets." not in files[ci_render.INVENTORY_FILE]
    assert "secrets." not in json.dumps(gh[ci_render.ENDPOINTS_FILE]["jobs"]["publish-report"])
    bb = _bb()
    steps = [bb["pipelines"]["default"][0]["step"], bb["pipelines"]["branches"]["main"][0]["step"]]
    for items in bb["pipelines"]["custom"].values():
        steps += [i["step"] for i in items if "step" in i]
    # inventory x2, then publish-sweep, also in its bootstrap twin. The
    # full-tier report commit is no longer an ordinary step here (see
    # test_bitbucket_endpoint_scan_after_script_purges_every_secret) - it
    # moved into gizmoduck-endpoint-scan's after-script so it still runs
    # when the gate blocks.
    assert len(steps) == 4
    for step in steps:
        body = "\n".join(step["script"])
        assert not _SECRET_REF.search(body) and "deployment" not in step, step.get("name")
        assert "unset " + " ".join(ci_render.TRUSTED_SECRETS) in body


def test_read_token_is_unset_from_every_secret_free_commit_step():
    """GIZMODUCK_BB_READ_TOKEN is a repository variable (not a deployment
    variable), so it is visible in every step regardless of stage - a
    "secret-free" commit step must unset it explicitly or it is not."""
    bb = _bb()
    steps = [bb["pipelines"]["default"][0]["step"], bb["pipelines"]["branches"]["main"][0]["step"]]
    for items in bb["pipelines"]["custom"].values():
        steps += [i["step"] for i in items if "step" in i]
    assert steps
    for step in steps:
        assert "unset GIZMODUCK_BB_READ_TOKEN" in "\n".join(step["script"]), step.get("name")


def test_every_self_commit_is_skip_ci_and_marked():
    files, _ = render()
    for rel, text in files.items():
        for line in text.splitlines():
            if "git -c user.name=gizmoduck-ci" in line:
                assert "[skip ci]" in line and MARK in line, rel


def test_the_weekly_results_branch_refuses_the_default_branch_and_release(repo):
    bb = _bb()
    (step,) = [i["step"] for i in bb["pipelines"]["custom"]["security-weekly"] if "step" in i]
    script = "\n".join(step["script"])
    for bad in ("main", "release/2.4"):
        p = repo.run(script, GIZMODUCK_RESULTS_BRANCH=bad)
        assert p.returncode == 1 and "refusing results branch" in p.stdout
    p = repo.run(script)
    assert p.returncode == 0 and "stays in this run's artifacts" in p.stdout


def test_the_weekly_results_branch_gets_the_report_and_main_does_not(repo):
    bb = _bb()
    (step,) = [i["step"] for i in bb["pipelines"]["custom"]["security-weekly"] if "step" in i]
    repo.write("gizmoduck-out/endpoints/security-scan-report.md", "# Security scan report\n")

    p = repo.run("\n".join(step["script"]), GIZMODUCK_RESULTS_BRANCH="gizmoduck-results",
                 BITBUCKET_BRANCH="main")

    assert p.returncode == 0, p.stdout + p.stderr
    assert "[skip ci]" in repo.origin_log("gizmoduck-results")[0]
    assert repo.git_at(repo.origin, "show", "gizmoduck-results:security-scan-report.md") == "# Security scan report"
    assert repo.origin_log("main") == ["seed"]


def test_the_weekly_results_branch_can_be_updated_more_than_once(repo):
    """Every prior commit on the results branch carries the self-commit
    mark, and a new week's report always differs (a fresh run URL) - the
    loop guard used to read that as a loop and refuse every run after the
    first."""
    bb = _bb()
    (step,) = [i["step"] for i in bb["pipelines"]["custom"]["security-weekly"] if "step" in i]
    script = "\n".join(step["script"])
    repo.write("gizmoduck-out/endpoints/security-scan-report.md", "# Security scan report\nweek 1\n")
    p1 = repo.run(script, GIZMODUCK_RESULTS_BRANCH="gizmoduck-results", BITBUCKET_BRANCH="main")
    assert p1.returncode == 0, p1.stdout + p1.stderr

    repo.write("gizmoduck-out/endpoints/security-scan-report.md", "# Security scan report\nweek 2\n")
    p2 = repo.run(script, GIZMODUCK_RESULTS_BRANCH="gizmoduck-results", BITBUCKET_BRANCH="main")

    assert p2.returncode == 0, p2.stdout + p2.stderr
    assert "loop guard" not in p2.stdout
    assert len(repo.origin_log("gizmoduck-results")) == 2
    assert repo.git_at(repo.origin, "show", "gizmoduck-results:security-scan-report.md") == \
        "# Security scan report\nweek 2"


# --------------------------------------------------------------------------
# the full-tier report survives a blocked/failed gate (BB after-script)
# --------------------------------------------------------------------------

def _bb_endpoint_scan_after_script_commit_item():
    bb = _bb()
    (step,) = [s["step"] for s in bb["definitions"]["steps"]
              if s["step"].get("name", "").startswith("gizmoduck tier 2: staging endpoint scan")]
    (item,) = [x for x in step["after-script"] if "Commit security-scan-report.md" in x]
    return item


def test_bitbucket_endpoint_scan_after_script_purges_every_secret_before_committing():
    body = _bb_endpoint_scan_after_script_commit_item()
    unset_line = next(ln for ln in body.splitlines() if ln.strip().startswith("unset "))
    assert " ".join(ci_render.TRUSTED_SECRETS) in unset_line and "GIZMODUCK_BB_READ_TOKEN" in unset_line
    assert _SECRET_REF.search(body) is None


def test_bitbucket_endpoint_scan_after_script_commits_even_though_the_step_it_belongs_to_would_fail(repo):
    """The after-script runs unconditionally in Bitbucket regardless of the
    step's own exit code - simulated here by simply invoking it after the
    report has been generated, exactly as Bitbucket would after a blocked
    gate left the main script non-zero."""
    item = _bb_endpoint_scan_after_script_commit_item()
    repo.branch("feature/x")
    repo.git("push", "-q", "origin", "feature/x")
    out_dir = repo.work.parent / "scan-out"
    out_dir.mkdir()
    (out_dir / "security-scan-report.md").write_text("# Security scan report\n", encoding="utf-8")

    p = repo.run(item, GIZMODUCK_OUT=str(out_dir), BITBUCKET_CLONE_DIR=str(repo.work),
                 BITBUCKET_BRANCH="feature/x")

    assert p.returncode == 0, p.stdout + p.stderr
    assert "[skip ci]" in repo.origin_log("feature/x")[0]
    assert repo.origin_log("main") == ["seed"]

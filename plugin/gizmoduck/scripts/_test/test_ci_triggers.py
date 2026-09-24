"""The trigger tiers, asserted from the RENDERED files rather than from the
Python that renders them: for each event, which workflow triggers, which job's
`if:` evaluates true, and what that run may block on. The GitHub `if:`
expressions are evaluated by a small evaluator below covering the subset the
renderer emits (==, !=, &&, ||, !, parentheses, startsWith, contains,
property paths with `*`), with GitHub's loose-equality and `&&`/`||`
value semantics.

Also here, because they check the same rendered files: actionlint over every
GitHub workflow, and the official Bitbucket Pipelines JSON schema over the
Bitbucket file. Neither tool ships with the plugin, so those two tests run only
when pointed at them - ACTIONLINT=<binary> and GIZMODUCK_BB_SCHEMA=<schema
json from https://api.bitbucket.org/schemas/pipelines-configuration> - and
skip, saying so, otherwise.
"""
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess

import ci_render
import pytest
import yaml
from test_ci_render import GOLDEN_CFG

# --------------------------------------------------------------------------
# a GitHub expression evaluator, for the subset the renderer emits
# --------------------------------------------------------------------------

_TOK = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\)|,)|"
                  r"(?P<name>[A-Za-z_][\w-]*(?:\.(?:[\w-]+|\*))*))")


def _tokens(expr):
    pos, out = 0, []
    while pos < len(expr):
        m = _TOK.match(expr, pos)
        if not m or m.end() == pos:
            if expr[pos:].strip() == "":
                break
            raise ValueError(f"cannot tokenize {expr[pos:]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


def _lookup(ctx, path):
    parts = path.split(".")
    values = [ctx]
    for part in parts:
        nxt = []
        for v in values:
            if part == "*":
                nxt.extend(v if isinstance(v, list) else list(v.values()) if isinstance(v, dict) else [])
            elif isinstance(v, dict):
                nxt.append(v.get(part))
            else:
                nxt.append(None)
        values = nxt
    return values if "*" in parts else values[0]


def _num(v):
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v) if str(v).strip() else 0.0
    except ValueError:
        return float("nan")


def _eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    if type(a) is type(b):
        return a == b
    return _num(a) == _num(b)


def _truthy(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0 and not math.isnan(v)
    return not (v is None or v is False or v == "")


class _Parser:
    def __init__(self, expr, ctx):
        self.toks, self.i, self.ctx = _tokens(expr), 0, ctx

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if value is not None and tok[1] != value:
            raise ValueError(f"expected {value!r}, got {tok!r}")
        self.i += 1
        return tok

    def parse(self):
        v = self.or_()
        if self.i != len(self.toks):
            raise ValueError(f"trailing tokens {self.toks[self.i:]}")
        return v

    def or_(self):
        v = self.and_()
        while self.peek()[1] == "||":
            self.take()
            rhs = self.and_()
            v = v if _truthy(v) else rhs
        return v

    def and_(self):
        v = self.cmp()
        while self.peek()[1] == "&&":
            self.take()
            rhs = self.cmp()
            v = rhs if _truthy(v) else v
        return v

    def cmp(self):
        v = self.unary()
        while self.peek()[1] in ("==", "!="):
            op = self.take()[1]
            rhs = self.unary()
            v = _eq(v, rhs) if op == "==" else not _eq(v, rhs)
        return v

    def unary(self):
        if self.peek()[1] == "!":
            self.take()
            return not _truthy(self.unary())
        return self.atom()

    def atom(self):
        kind, val = self.take()
        if val == "(":
            v = self.or_()
            self.take(")")
            return v
        if kind == "str":
            return val[1:-1].replace("''", "'")
        if val in ("true", "false"):
            return val == "true"
        if val == "null":
            return None
        if self.peek()[1] == "(":
            self.take("(")
            args = [self.or_()]
            while self.peek()[1] == ",":
                self.take()
                args.append(self.or_())
            self.take(")")
            return self.call(val, args)
        return _lookup(self.ctx, val)

    @staticmethod
    def call(name, args):
        a, b = args
        if name == "startsWith":
            return str(a or "").lower().startswith(str(b or "").lower())
        if name == "contains":
            if isinstance(a, list):
                return any(_eq(x, b) for x in a)
            return str(b or "").lower() in str(a or "").lower()
        raise ValueError(f"unknown function {name}")


def evaluate(expr, ctx):
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2]
    return _Parser(expr, ctx).parse()


def test_evaluator_semantics():
    ctx = {"github": {"event_name": "schedule", "event": {"pull_request": {"labels": [{"name": "Security-Scan"}]}}}}
    assert evaluate("github.event_name == 'schedule' && 'sweep' || 'full'", ctx) == "sweep"
    assert evaluate("github.event_name == 'push' && 'sweep' || 'full'", ctx) == "full"
    assert evaluate("contains(github.event.pull_request.labels.*.name, 'security-scan')", ctx) is True
    assert evaluate("!(startsWith('release/1', 'RELEASE/'))", ctx) is False
    assert evaluate("github.event.missing == false", ctx) is True, "GitHub coerces null == false to true"


# --------------------------------------------------------------------------
# events -> which tier runs
# --------------------------------------------------------------------------

def render():
    files = ci_render.render_all(GOLDEN_CFG, ("github", "bitbucket"))
    gh = {rel: yaml.safe_load(text) for rel, text in files.items() if rel.startswith(".github/")}
    return files, gh


def _on(doc):
    return doc.get("on", doc.get(True))


def pr_event(base="feature/x", draft=False, labels=(), action="synchronize", changed=("src/app.py",)):
    return {"name": "pull_request", "action": action, "changed": list(changed), "ref": "refs/pull/7/merge",
            "ctx": {"github": {"event_name": "pull_request", "base_ref": base, "ref": "refs/pull/7/merge",
                               "repository": REPO,
                               "event": {"action": action,
                                         "label": {"name": labels[-1]} if action == "labeled" and labels else {},
                                         "pull_request": {"draft": draft, "number": 7,
                                                          "labels": [{"name": n} for n in labels]}}},
                    "vars": {}}}


REPO = "acme/app"


def plain(name, **event):
    return {"name": name, "ref": "refs/heads/main",
            "ctx": {"github": {"event_name": name, "base_ref": "", "ref": "refs/heads/main", "event": event,
                               "repository": REPO},
                    "vars": {}}}


def deploy(state="success", environment="staging", ref="main", repo=REPO):
    return plain("deployment_status", deployment_status={"state": state},
                 deployment={"environment": environment, "ref": ref}, repository={"full_name": repo})


def deploy_run(conclusion="success", branch="main", repo=REPO, event="push"):
    return plain("workflow_run", workflow_run={"conclusion": conclusion, "head_branch": branch, "event": event,
                                               "head_repository": {"full_name": repo}})


def triggered(doc, ev):
    on = _on(doc)
    if ev["name"] not in on:
        return False
    spec = on[ev["name"]] or {}
    if ev["name"] == "pull_request":
        types = spec.get("types") or ["opened", "synchronize", "reopened"]
        if ev["action"] not in types:
            return False
        ignore = spec.get("paths-ignore") or []
        if ignore and all(any(fnmatch.fnmatch(f, p) or fnmatch.fnmatch("/" + f, "/" + p.replace("**/", ""))
                              for p in ignore) for f in ev["changed"]):
            return False
    return True


def env_value(raw, ctx):
    raw = str(raw)
    return evaluate(raw, ctx) if raw.strip().startswith("${{") else raw


def running(ev, gh):
    """{workflow file: (GIZMODUCK_TIER, GIZMODUCK_BLOCK_AT)} for every workflow
    whose runner-image job would run for this event."""
    out = {}
    for rel, doc in gh.items():
        if not triggered(doc, ev):
            continue
        if not _truthy(evaluate(doc["jobs"]["scan"]["if"], ev["ctx"])):
            continue
        assert not _truthy(evaluate(doc["jobs"]["scan-bootstrap"]["if"], ev["ctx"])), \
            "the image job and the bootstrap job must never both run"
        env = doc["env"]
        out[rel.rsplit("/", 1)[-1]] = (env_value(env["GIZMODUCK_TIER"], ev["ctx"]),
                                       env_value(env["GIZMODUCK_BLOCK_AT"], ev["ctx"]))
    return out


PR, FULL, EP = "gizmoduck-pr.yml", "gizmoduck-full.yml", "gizmoduck-endpoints.yml"
TIER1 = {PR: ("light", "critical")}
TIER2_CODE = {FULL: ("full", "high")}

MATRIX = [
    ("draft PR into a feature branch", pr_event(draft=True), {}),
    ("draft PR into main", pr_event(base="main", draft=True), {}),
    ("PR into a feature branch", pr_event(), TIER1),
    ("PR into a feature branch marked ready", pr_event(action="ready_for_review"), TIER1),
    ("docs-only PR into a feature branch", pr_event(changed=("README.md", "docs/guide.md")), {}),
    ("PR into main", pr_event(base="main"), TIER2_CODE),
    ("docs-only PR into main (tier 2 has no path filter)", pr_event(base="main", changed=("README.md",)),
     TIER2_CODE),
    ("PR into release/2.4", pr_event(base="release/2.4"), TIER2_CODE),
    ("PR into releases-old (not release/*)", pr_event(base="releases-old"), TIER1),
    ("security-scan label added to a feature PR",
     pr_event(labels=("security-scan",), action="labeled"), TIER2_CODE),
    ("push to a feature PR already carrying the label", pr_event(labels=("security-scan",)), TIER2_CODE),
    ("some other label added to a feature PR", pr_event(labels=("docs",), action="labeled"), {}),
    # Tier 2 is decided from the label SET: an unrelated label on a tier-2 PR
    # re-runs it rather than leaving a skipped run to stand in for the scan.
    ("some other label added to a PR into main (re-evaluated, not skipped)",
     pr_event(base="main", labels=("docs",), action="labeled"), TIER2_CODE),
    ("some other label added to a labelled feature PR",
     pr_event(labels=("security-scan", "docs"), action="labeled"), TIER2_CODE),
    ("security-scan label removed from a feature PR", pr_event(action="unlabeled"), {}),
    ("draft PR with the label", pr_event(draft=True, labels=("security-scan",), action="labeled"), {}),
    ("weekly schedule", plain("schedule"), {FULL: ("sweep", "never"), EP: ("sweep", "never")}),
    ("manual dispatch", plain("workflow_dispatch"), {FULL: ("full", "high"), EP: ("full", "high")}),
    ("staging deploy of main succeeded", deploy(), {EP: ("full", "high")}),
    ("staging deploy of refs/heads/main succeeded", deploy(ref="refs/heads/main"), {EP: ("full", "high")}),
    ("staging deploy of release/2.4 succeeded", deploy(ref="release/2.4"), {EP: ("full", "high")}),
    ("staging deploy of a PR branch (untrusted ref)", deploy(ref="feature/x"), {}),
    ("staging deploy of a bare SHA (not a trusted branch)", deploy(ref="0123abcd"), {}),
    ("staging deploy failed", deploy(state="failure"), {}),
    ("production deploy succeeded", deploy(environment="production"), {}),
    ("deploy workflow succeeded on main", deploy_run(), {EP: ("full", "high")}),
    ("deploy workflow succeeded on release/2.4", deploy_run(branch="release/2.4"), {EP: ("full", "high")}),
    ("deploy workflow run by a fork PR", deploy_run(repo="attacker/app", event="pull_request"), {}),
    ("deploy workflow from a fork's branch named main", deploy_run(repo="attacker/app"), {}),
    ("deploy workflow run by a same-repo PR", deploy_run(branch="feature/x", event="pull_request"), {}),
    ("deploy workflow run by a same-repo PR from release/*",
     deploy_run(branch="release/evil", event="pull_request"), {}),
    ("deploy workflow failed", deploy_run(conclusion="failure"), {}),
    ("push to main", plain("push"), {}),
    ("push to a branch named security-scan", plain("push"), {}),
]


@pytest.mark.parametrize("label,ev,expected", MATRIX, ids=[m[0] for m in MATRIX])
def test_trigger_matrix(label, ev, expected):
    _, gh = render()
    assert running(ev, gh) == expected, label


def gate_verdict(doc, ev, image_result=None, boot_result="skipped"):
    """Run the gate job's own decision for this event: its `if:` must be
    always(), and its script passes iff the tier does not apply, or exactly
    one scan job succeeded and the other was skipped."""
    job = doc["jobs"]["gate"]
    assert job["if"] == "always()"
    applies = _truthy(evaluate(job["env"]["GIZMODUCK_APPLIES"], ev["ctx"]))
    scan_ran = _truthy(evaluate(doc["jobs"]["scan"]["if"], ev["ctx"]))
    if image_result is None:
        image_result = "success" if scan_ran else "skipped"
    script = job["steps"][0]["run"]
    env = {"GIZMODUCK_APPLIES": "true" if applies else "false", "IMAGE_RESULT": image_result,
           "BOOT_RESULT": boot_result, "PATH": os.environ.get("PATH", "")}
    p = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)
    return applies, p.returncode


@pytest.mark.parametrize("label,ev,expected", [m for m in MATRIX if m[1]["name"] == "pull_request"],
                         ids=[m[0] for m in MATRIX if m[1]["name"] == "pull_request"])
def test_gate_job_applies_exactly_when_the_tier_runs(label, ev, expected):
    _, gh = render()
    for rel, doc in gh.items():
        name = rel.rsplit("/", 1)[-1]
        if "gate" not in doc["jobs"] or not triggered(doc, ev):
            continue
        applies, rc = gate_verdict(doc, ev)
        assert applies is (name in expected), (label, name)
        assert rc == 0, (label, name)


def test_a_failed_tier_2_scan_fails_the_gate_and_an_unrelated_label_cannot_supersede_it():
    _, gh = render()
    full = gh[ci_render.FULL_FILE]
    failed = pr_event(base="main")
    assert gate_verdict(full, failed, image_result="failure")[1] == 1
    later_label = pr_event(base="main", labels=("docs",), action="labeled")
    applies, rc = gate_verdict(full, later_label, image_result="failure")
    assert applies and rc == 1, "the next labeled event re-runs the tier-2 scan and gates on it"
    assert gate_verdict(full, later_label, image_result="skipped", boot_result="skipped")[1] == 1, \
        "a tier-2 event whose scan did not run is a failure, never a pass"


def test_permissions_are_least_privilege_per_job():
    _, gh = render()
    for rel, doc in gh.items():
        assert doc["permissions"] == {}, rel
        for name, job in doc["jobs"].items():
            perms = job.get("permissions")
            assert perms is not None, f"{rel}:{name} must state its permissions"
            if name == "sarif":
                assert perms == {"contents": "read", "security-events": "write"}, rel
            else:
                assert "write" not in (perms or {}).values(), f"{rel}:{name} holds a write permission"
        assert "pull_request_target" not in _on(doc), rel


def test_no_secret_reaches_a_pull_request_job():
    files, gh = render()
    assert "secrets." not in files[ci_render.PR_FILE]
    full = gh[ci_render.FULL_FILE]
    ctx = pr_event(base="main")["ctx"]
    for job in ("scan", "scan-bootstrap"):
        for step in full["jobs"][job]["steps"]:
            env = step.get("env") or {}
            refs_secret = any("secrets." in str(v) for v in env.values())
            if not refs_secret:
                continue
            runs = "if" not in step or _truthy(evaluate(step["if"].replace("always() && ", ""),
                                                        dict(ctx, steps={"gate": {"outcome": "failure"}})))
            if runs:
                values = [evaluate(v, dict(ctx, secrets={"NVD_API_KEY": "S"})) for v in env.values()
                          if "secrets." in str(v)]
                assert all(v in ("", None, False) for v in values), (job, step["name"])


def test_manual_dispatch_is_the_only_way_a_dispatch_runs_each_workflow():
    """A dispatch targets ONE workflow; both the code and the endpoint workflow
    accept it, and the PR workflow does not."""
    _, gh = render()
    assert "workflow_dispatch" not in _on(gh[ci_render.PR_FILE])
    assert "workflow_dispatch" in _on(gh[ci_render.FULL_FILE])
    assert "workflow_dispatch" in _on(gh[ci_render.ENDPOINTS_FILE])


def test_endpoint_scans_never_run_on_a_pull_request():
    files, gh = render()
    for rel, text in files.items():
        if " endpoint-stage " in text and rel.startswith(".github/"):
            assert "pull_request" not in _on(gh[rel]), rel
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    pr_steps = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    assert all(" endpoint-stage " not in "\n".join(s["script"]) for s in pr_steps)


def test_no_branch_name_or_push_triggers():
    files, gh = render()
    for rel, doc in gh.items():
        on = _on(doc)
        assert "push" not in on, rel
        assert not (on.get("pull_request") or {}).get("branches"), rel
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    assert set(bb["pipelines"]) == {"pull-requests", "custom"}


def test_every_workflow_cancels_in_progress_per_ref():
    _, gh = render()
    for rel, doc in gh.items():
        assert doc["concurrency"]["cancel-in-progress"] is True, rel
        assert "github.ref" in doc["concurrency"]["group"], rel


def test_the_weekly_sweep_is_sunday_night_and_updates_templates():
    files, gh = render()
    for rel in (ci_render.FULL_FILE, ci_render.ENDPOINTS_FILE):
        assert _on(gh[rel])["schedule"] == [{"cron": "0 23 * * 0"}], rel
    assert 'prepare-templates --dir "$GIZMODUCK_NUCLEI_TEMPLATES" --tier "$GIZMODUCK_TIER"' in \
        files[ci_render.ENDPOINTS_FILE]


def test_caches_for_trivy_nvd_and_nuclei():
    files, _ = render()
    assert "key: gizmoduck-trivy-" in files[ci_render.PR_FILE]
    assert "key: gizmoduck-trivy-" in files[ci_render.FULL_FILE] and "key: gizmoduck-nvd-" in files[ci_render.FULL_FILE]
    assert "key: gizmoduck-nuclei-" in files[ci_render.ENDPOINTS_FILE]
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    assert set(bb["definitions"]["caches"]) == {"gizmoduck-trivy", "gizmoduck-nvd", "gizmoduck-nuclei",
                                                 "gizmoduck-pr-trivy"}


def _cache_key_outputs(event_name, run_id="777"):
    _, gh = render()
    step = next(s for s in gh[ci_render.FULL_FILE]["jobs"]["scan"]["steps"] if s.get("id") == "week")
    out = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"gz-cache-key-{os.getpid()}-{event_name}")
    subprocess.run(["bash", "-c", step["run"]], check=True,
                   env={"GITHUB_EVENT_NAME": event_name, "GITHUB_RUN_ID": run_id, "GITHUB_OUTPUT": out,
                        "PATH": os.environ.get("PATH", "")})
    with open(out, encoding="utf-8") as fh:
        values = dict(line.strip().split("=", 1) for line in fh if "=" in line)
    os.remove(out)
    return values


@pytest.mark.parametrize("event,trust", [("pull_request", "pr"), ("schedule", "trusted"),
                                         ("workflow_dispatch", "trusted")])
def test_github_cache_keys_are_scoped_by_trust(event, trust):
    values = _cache_key_outputs(event)
    assert values["trust"] == trust
    files, _ = render()
    for rel in ci_render.GITHUB_FILES:
        for line in files[rel].splitlines():
            if line.strip().startswith(("key: gizmoduck-", "restore-keys: gizmoduck-")):
                assert "${{ steps.week.outputs.trust }}-" in line, (rel, line)


def test_the_weekly_sweep_always_saves_a_fresh_cache():
    assert _cache_key_outputs("schedule", "777")["suffix"] == "-sweep-777"
    assert _cache_key_outputs("workflow_dispatch")["suffix"] == ""


def test_bitbucket_pr_caches_never_meet_trusted_ones():
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    (pr,) = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    assert pr["caches"] == ["gizmoduck-pr-trivy"]
    for step in _bb_trusted_steps(bb):
        assert not any(c.startswith("gizmoduck-pr-") for c in step.get("caches") or []), step["name"]


def _bb_exports(step):
    body = "\n".join(step["script"])
    return {k: v.strip("'") for k, v in re.findall(r"^export (GIZMODUCK_TIER|GIZMODUCK_BLOCK_AT)=(\S+)$", body, re.M)}


def _bb_trusted_steps(bb):
    """Every step of every custom pipeline - each must sit in a stage bound to
    the trusted deployment environment."""
    out = []
    for name, items in bb["pipelines"]["custom"].items():
        stages = [i["stage"] for i in items if "stage" in i]
        assert not [i for i in items if "step" in i], f"custom: {name} has a step outside the trusted stage"
        for st in stages:
            assert st["deployment"] == ci_render.BB_TRUSTED_ENV, name
            out += [s["step"] for s in st["steps"]]
    return out


def _bb_run(script_items, env):
    """Run the given script items as Bitbucket does - one shell, in order -
    with `curl` and `python3` faked on PATH."""
    body = "\n".join(script_items)
    return subprocess.run(["bash", "-c", body], env=env, capture_output=True, text=True, check=False)


def _bb_pr_trust_items():
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    (pr,) = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    return [x for x in pr["script"] if "write-capable secret" in x]


def _fake_bin(tmp_path, draft="false", curl_rc=0):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    body = f"echo '{{\"draft\": {draft}}}'\n" if curl_rc == 0 else ""
    (bindir / "curl").write_text(f"#!/bin/sh\n{body}exit {curl_rc}\n", encoding="utf-8")
    (bindir / "curl").chmod(0o755)
    return f"{bindir}:{os.environ.get('PATH', '')}"


@pytest.mark.parametrize("secret", list(ci_render.WRITE_SECRETS))
def test_bitbucket_pr_step_refuses_a_write_capable_repository_variable(tmp_path, secret):
    env = {"PATH": _fake_bin(tmp_path), "GIZMODUCK_BB_READ_TOKEN": "r", "BITBUCKET_PR_ID": "7", secret: "w"}
    p = _bb_run(_bb_pr_trust_items() + ["echo SCANNED"], env)
    assert p.returncode == 1 and "SCANNED" not in p.stdout and "repository variable" in p.stdout


@pytest.mark.parametrize("draft,curl_rc,rc,scanned", [
    ("false", 0, 0, True),      # ready for review: scans
    ("true", 0, 0, False),      # draft: skipped
    ("false", 22, 1, False),    # API failed: fails closed, never scans blind
])
def test_bitbucket_pr_step_draft_detection(tmp_path, draft, curl_rc, rc, scanned):
    env = {"PATH": _fake_bin(tmp_path, draft, curl_rc), "GIZMODUCK_BB_READ_TOKEN": "r", "BITBUCKET_PR_ID": "7"}
    p = _bb_run(_bb_pr_trust_items() + ["echo SCANNED"], env)
    assert (p.returncode, "SCANNED" in p.stdout) == (rc, scanned), p.stdout + p.stderr


def test_bitbucket_pr_step_without_the_read_token_fails_rather_than_scanning(tmp_path):
    """A fork's PR never gets secured variables: previously it scanned drafts
    regardless; now it fails, saying why."""
    p = _bb_run(_bb_pr_trust_items() + ["echo SCANNED"], {"PATH": _fake_bin(tmp_path), "BITBUCKET_PR_ID": "7"})
    assert p.returncode == 1 and "SCANNED" not in p.stdout and "GIZMODUCK_BB_READ_TOKEN" in p.stdout


def test_bitbucket_write_token_is_used_only_in_trusted_stages():
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    (pr,) = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    pr_body = "\n".join(pr["script"])
    assert "$GIZMODUCK_BB_TOKEN" not in pr_body and "$SDP_API_KEY" not in pr_body
    assert "GIZMODUCK_BB_READ_TOKEN" in pr_body
    for step in _bb_trusted_steps(bb):
        assert any("is not a trusted branch" in x for x in step["script"]), step["name"]


@pytest.mark.parametrize("branch,dropped", [("main", False), ("release/2.4", False), ("feature/x", True)])
def test_bitbucket_trusted_steps_drop_write_secrets_off_trusted_branches(branch, dropped):
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    step = _bb_trusted_steps(bb)[0]
    items = [x for x in step["script"] if "is not a trusted branch" in x]
    p = _bb_run(items + ['echo "token=${GIZMODUCK_BB_TOKEN:-}"'],
                {"PATH": os.environ.get("PATH", ""), "BITBUCKET_BRANCH": branch,
                 "GIZMODUCK_DEFAULT_BRANCH": "main", "GIZMODUCK_BB_TOKEN": "w"})
    assert ("token=w" not in p.stdout) is dropped, p.stdout


def test_bitbucket_code_insights_failures_fail_the_step():
    files, _ = render()
    text = files["bitbucket-pipelines.yml"]
    assert "report upload failed" not in text and "annotation upload failed" not in text
    assert '--srcroot "$BITBUCKET_CLONE_DIR" || true' not in text
    bb = yaml.safe_load(text)
    (pr,) = [s["step"] for s in bb["pipelines"]["pull-requests"]["**"]]
    tail = pr["script"][-1]
    p = _bb_run(["gate_rc=0", "insights_rc=6", f"BITBUCKET_CLONE_DIR=$(mktemp -d); GIZMODUCK_OUT=$(mktemp -d)\n{tail}"],
                {"PATH": os.environ.get("PATH", "")})
    assert p.returncode == 6 and "Code Insights report failed" in p.stdout
    p = _bb_run(["gate_rc=1", "insights_rc=6", f"BITBUCKET_CLONE_DIR=$(mktemp -d); GIZMODUCK_OUT=$(mktemp -d)\n{tail}"],
                {"PATH": os.environ.get("PATH", "")})
    assert p.returncode == 1, "the gate's own verdict comes first"


def test_bitbucket_tiers():
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    pipes = bb["pipelines"]
    (pr,) = [s["step"] for s in pipes["pull-requests"]["**"]]
    assert _bb_exports(pr) == {"GIZMODUCK_TIER": "light", "GIZMODUCK_BLOCK_AT": "critical"}
    assert pr["condition"]["changesets"]["excludePaths"] == list(ci_render.DOCS_ONLY)
    assert "--tier light --base-ref" in "\n".join(pr["script"])
    assert "draft" in "\n".join(pr["script"])
    full = [s["step"] for i in pipes["custom"]["security-full"] if "stage" in i for s in i["stage"]["steps"]]
    assert [_bb_exports(s) for s in full] == [{"GIZMODUCK_TIER": "full", "GIZMODUCK_BLOCK_AT": "high"}] * 2
    assert " endpoint-stage " in "\n".join(full[1]["script"])
    weekly = [s["step"] for i in pipes["custom"]["security-weekly"] for s in i["stage"]["steps"]]
    assert [_bb_exports(s) for s in weekly] == [{"GIZMODUCK_TIER": "sweep", "GIZMODUCK_BLOCK_AT": "never"}] * 2
    assert "gizmoduck-nvd" in weekly[0]["caches"]
    assert full[0]["clone"]["depth"] == "full" and weekly[0]["clone"]["depth"] == "full", \
        "gitleaks scans the whole history on tier 2 and the sweep"
    assert "Pipeline: custom: security-weekly" in files["bitbucket-pipelines.yml"], "one-time UI setup documented"


# --------------------------------------------------------------------------
# external validators
# --------------------------------------------------------------------------

def test_actionlint_on_every_rendered_workflow(tmp_path):
    binary = os.environ.get("ACTIONLINT") or shutil.which("actionlint")
    if not binary:
        pytest.skip("actionlint not available - set ACTIONLINT=<path> to run this check")
    files = ci_render.render_all(GOLDEN_CFG, ("github",))
    paths = []
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        paths.append(str(path))
    argv = [binary, "-no-color"]
    if os.environ.get("SHELLCHECK"):
        argv += ["-shellcheck", os.environ["SHELLCHECK"]]
    p = subprocess.run(argv + paths, capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stdout + p.stderr


def test_bitbucket_file_against_the_official_schema():
    schema_path = os.environ.get("GIZMODUCK_BB_SCHEMA")
    if not schema_path:
        pytest.skip("set GIZMODUCK_BB_SCHEMA to the official Bitbucket Pipelines schema JSON to run this check")
    jsonschema = pytest.importorskip("jsonschema")
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    doc = yaml.safe_load(ci_render.render_all(GOLDEN_CFG, ("bitbucket",))["bitbucket-pipelines.yml"])
    errors = [f"{list(e.path)}: {e.message[:200]}" for e in jsonschema.Draft7Validator(schema).iter_errors(doc)]
    assert errors == []

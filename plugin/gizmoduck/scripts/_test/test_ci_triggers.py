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
                               "event": {"action": action,
                                         "label": {"name": labels[-1]} if action == "labeled" and labels else {},
                                         "pull_request": {"draft": draft, "number": 7,
                                                          "labels": [{"name": n} for n in labels]}}},
                    "vars": {}}}


def plain(name, **event):
    return {"name": name, "ref": "refs/heads/main",
            "ctx": {"github": {"event_name": name, "base_ref": "", "ref": "refs/heads/main", "event": event},
                    "vars": {}}}


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
    ("some other label added to a PR into main (no redundant rerun)",
     pr_event(base="main", labels=("docs",), action="labeled"), {}),
    ("draft PR with the label", pr_event(draft=True, labels=("security-scan",), action="labeled"), {}),
    ("weekly schedule", plain("schedule"), {FULL: ("sweep", "never"), EP: ("sweep", "never")}),
    ("manual dispatch", plain("workflow_dispatch"), {FULL: ("full", "high"), EP: ("full", "high")}),
    ("staging deploy succeeded", plain("deployment_status", deployment_status={"state": "success"},
                                       deployment={"environment": "staging"}), {EP: ("full", "high")}),
    ("staging deploy failed", plain("deployment_status", deployment_status={"state": "failure"},
                                    deployment={"environment": "staging"}), {}),
    ("production deploy succeeded", plain("deployment_status", deployment_status={"state": "success"},
                                          deployment={"environment": "production"}), {}),
    ("deploy workflow succeeded", plain("workflow_run", workflow_run={"conclusion": "success"}),
     {EP: ("full", "high")}),
    ("push to main", plain("push"), {}),
    ("push to a branch named security-scan", plain("push"), {}),
]


@pytest.mark.parametrize("label,ev,expected", MATRIX, ids=[m[0] for m in MATRIX])
def test_trigger_matrix(label, ev, expected):
    _, gh = render()
    assert running(ev, gh) == expected, label


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
    assert set(bb["definitions"]["caches"]) == {"gizmoduck-trivy", "gizmoduck-nvd", "gizmoduck-nuclei"}


def _bb_exports(step):
    body = "\n".join(step["script"])
    return {k: v.strip("'") for k, v in re.findall(r"^export (GIZMODUCK_TIER|GIZMODUCK_BLOCK_AT)=(\S+)$", body, re.M)}


def test_bitbucket_tiers():
    files, _ = render()
    bb = yaml.safe_load(files["bitbucket-pipelines.yml"])
    pipes = bb["pipelines"]
    (pr,) = [s["step"] for s in pipes["pull-requests"]["**"]]
    assert _bb_exports(pr) == {"GIZMODUCK_TIER": "light", "GIZMODUCK_BLOCK_AT": "critical"}
    assert pr["condition"]["changesets"]["excludePaths"] == list(ci_render.DOCS_ONLY)
    assert "--tier light --base-ref" in "\n".join(pr["script"])
    assert "draft" in "\n".join(pr["script"])
    full = [i["step"] for i in pipes["custom"]["security-full"] if "step" in i]
    assert [_bb_exports(s) for s in full] == [{"GIZMODUCK_TIER": "full", "GIZMODUCK_BLOCK_AT": "high"}] * 2
    assert " endpoint-stage " in "\n".join(full[1]["script"])
    weekly = [i["step"] for i in pipes["custom"]["security-weekly"]]
    assert [_bb_exports(s) for s in weekly] == [{"GIZMODUCK_TIER": "sweep", "GIZMODUCK_BLOCK_AT": "never"}] * 2
    assert "gizmoduck-nvd" in weekly[0]["caches"]
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

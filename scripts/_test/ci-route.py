#!/usr/bin/env python3
"""Suite for scripts/ci-route.py, the router and gate behind ci.yml.

Three halves, and the failing cases are the point of each:
  route    must-skip cases (docs-only PRs skip every routed suite) and must-run
           cases (an unknown path, a workflow change, a renamed crew guide, an
           empty change list each run what they must);
  verdict  every way the required `CI gate` could go green over a suite that
           should have run and did not, or failed;
  ci.yml   the workflow agrees with ci-route.py's tables: an output per routed
           suite, a job per suite gated on it, a gate needing every job, and no
           other workflow left starting on its own for a pull_request.

Run: python3 scripts/_test/ci-route.py      (needs PyYAML for the ci.yml half)
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "scripts", "ci-route.py")
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")

_spec = importlib.util.spec_from_file_location("ci_route", SCRIPT)
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

NONE = set()
ALL = {"crew", "shell", "mcp", "lint"}


def _on(paths):
    return {s for s, v in cr.route(paths).items() if v}


# ---- route ------------------------------------------------------------------

ROUTE_CASES = [
    # must-skip
    ("docs-only PR", ["docs/review/01-x.md", "README.md", "CHANGELOG.md"], NONE),
    ("root prose and ignore files", ["TODO.md", "LICENSE", ".gitignore"], NONE),
    ("a docs/ image", ["docs/diagrams/x.png"], NONE),
    ("mcp-servers only", ["mcp-servers/packages/a/src/x.ts"], {"mcp"}),
    ("docs plus mcp-servers", ["docs/x.md", "mcp-servers/package.json"], {"mcp"}),
    # must-run
    ("crew guide", ["docs/guides/crew/src/guide.md"], {"crew"}),
    ("crew hook .py", ["plugin/crew/hooks/scripts/x.py"], {"crew", "shell", "lint"}),
    ("a skill's SKILL.md", ["skills/notify/SKILL.md"], {"crew", "shell"}),
    ("a skill asset (doc-builder scans every one)", ["skills/github/assets/brand.json"],
     {"crew", "shell"}),
    ("scripts/", ["scripts/check-tooling-pr.py"], {"crew", "lint"}),
    (".crew/verify.json", [".crew/verify.json"], {"crew"}),
    ("marketplace.json", [".claude-plugin/marketplace.json"], {"crew"}),
    ("any workflow change", [".github/workflows/marketplace.yml"], ALL),
    ("a .github file that is not a workflow", [".github/dependabot.yml"], ALL),
    ("unknown root file", ["Makefile"], ALL),
    ("unknown directory", ["newtool/run.sh"], ALL),
    ("look-alike of docs/", ["docs-old/x.md"], ALL),
    ("root-prose name below an unknown dir", ["newtool/README.md"], ALL),
    ("root .py (unknown, and lint)", ["setup.py"], ALL),
    ("empty change list", [], ALL),
    ("blank lines only", ["", "  "], ALL),
    ("backslash path", ["docs\\guides\\crew\\x.md"], {"crew"}),
    ("one unknown among docs", ["docs/x.md", "README.md", "Dockerfile"], ALL),
    ("lint config anywhere", ["mcp-servers/ruff.toml"], {"mcp", "lint"}),
]


def run_route_cases():
    out = []
    for name, paths, want in ROUTE_CASES:
        got = _on(paths)
        out.append((f"route: {name}", got == want, f"paths {paths}: want {sorted(want)}, got {sorted(got)}"))
    return out


# ---- changes (a real git repo) -----------------------------------------------

def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _changes(cwd, *args):
    res = subprocess.run([sys.executable, SCRIPT, "changes", *args], cwd=cwd,
                         capture_output=True, text=True, timeout=60, check=False)
    vals = dict(l.split("=", 1) for l in res.stdout.splitlines() if "=" in l)
    return res.returncode, vals, res.stderr


def _repo(root):
    _git(root, "init", "-q")
    for rel in ("docs/guides/crew/a.md", "docs/b.md", "README.md"):
        os.makedirs(os.path.join(root, os.path.dirname(rel) or "."), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(rel + "\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")


def run_changes_cases():
    out = []
    with tempfile.TemporaryDirectory() as root:
        _repo(root)
        with open(os.path.join(root, "README.md"), "a", encoding="utf-8") as fh:
            fh.write("more\n")
        _git(root, "commit", "-q", "-am", "docs")
        rc, vals, err = _changes(root)
        ok = rc == 0 and all(vals.get(s) == "false" for s in ALL) and "SKIPPED, not passed" in err
        out.append(("changes: docs-only commit skips every routed suite", ok, f"rc {rc} {vals} {err}"))

        # A rename out of the crew guides: the OLD path is a crew input too.
        _git(root, "mv", "docs/guides/crew/a.md", "docs/a.md")
        _git(root, "commit", "-q", "-m", "move")
        rc, vals, err = _changes(root)
        ok = rc == 0 and vals.get("crew") == "true"
        out.append(("changes: a rename out of docs/guides/crew still runs crew", ok,
                    f"rc {rc} {vals} {err}"))

        rc, vals, err = _changes(root, "--base", "no-such-rev")
        ok = (rc == 0 and all(vals.get(s) == "true" for s in ALL)
              and vals.get("reason") == "diff-failed" and "::warning::" in err)
        out.append(("changes: a diff that cannot be computed runs every suite", ok,
                    f"rc {rc} {vals} {err}"))

        rc, vals, err = _changes(root, "--bogus")
        out.append(("changes: an unknown argument is a usage error", rc == 2, f"rc {rc}"))
    return out


# ---- verdict -----------------------------------------------------------------

def _results(**override):
    base = {j: {"result": "success", "outputs": {}} for j in cr.JOB.values()}
    base["changes"] = {"result": "success", "outputs": {}}
    for job, res in override.items():
        job = job.replace("_", "-")
        if res is None:
            base.pop(job, None)
        else:
            base[job] = {"result": res, "outputs": {}}
    return base


ROUTES_ALL = {"crew": "true", "shell": "true", "mcp": "true", "lint": "true", "reason": "x"}
ROUTES_DOCS = {"crew": "false", "shell": "false", "mcp": "false", "lint": "false", "reason": "x"}
SKIPPED = {"pytest_crew": "skipped", "shell_suites": "skipped", "mcp_servers": "skipped",
           "pylint": "skipped"}

VERDICT_CASES = [
    # (name, changes_result, routes, results, want_pass, needle)
    ("everything routed and green", "success", ROUTES_ALL, _results(), True, "PASS"),
    ("docs-only: routed suites skipped", "success", ROUTES_DOCS, _results(**SKIPPED), True,
     "skipped (not needed"),
    ("routed suite skipped", "success", ROUTES_ALL, _results(pytest_crew="skipped"), False,
     "pytest-crew: routed crew=true"),
    ("routed suite failed", "success", ROUTES_ALL, _results(shell_suites="failure"), False,
     "shell-suites"),
    ("routed suite cancelled", "success", ROUTES_ALL, _results(mcp_servers="cancelled"), False,
     "mcp-servers"),
    ("unrouted suite ran anyway (an if: wired wrong)", "success", ROUTES_DOCS,
     _results(**{**SKIPPED, "pylint": "success"}), False, "pylint: routed lint=false"),
    ("always suite failed", "success", ROUTES_DOCS, _results(**{**SKIPPED, "marketplace": "failure"}),
     False, "marketplace: always runs"),
    ("always suite skipped", "success", ROUTES_ALL, _results(budgets="skipped"), False,
     "budgets: always runs"),
    ("routing job failed", "failure", {}, _results(), False, "changes:"),
    ("routing job skipped", "skipped", {}, _results(), False, "changes:"),
    ("a job missing from needs (renamed in ci.yml)", "success", ROUTES_ALL,
     _results(pylint=None), False, "pylint"),
    ("routing output missing", "success", {"crew": "true"}, _results(), False,
     "routing output None"),
    ("routing output not a boolean", "success", {**ROUTES_ALL, "mcp": "yes"}, _results(), False,
     "routing output 'yes'"),
]


def _verdict(changes_result, routes, results, raw=None):
    env = {**os.environ, "CHANGES_RESULT": changes_result,
           "ROUTES": raw[0] if raw else json.dumps(routes),
           "RESULTS": raw[1] if raw else json.dumps(results)}
    res = subprocess.run([sys.executable, SCRIPT, "verdict"], env=env, capture_output=True,
                         text=True, timeout=60, check=False)
    return res.returncode, res.stdout + res.stderr


def run_verdict_cases():
    out = []
    for name, ch, routes, results, want_pass, needle in VERDICT_CASES:
        rc, text = _verdict(ch, routes, results)
        ok = (rc == 0) == want_pass and needle in text
        out.append((f"verdict: {name}", ok, f"rc {rc}: {text.strip()}"))
    for name, raw in (("unreadable ROUTES", ("{", "{}")), ("RESULTS not an object", ("{}", "[]")),
                      ("ROUTES absent", ("", "{}"))):
        rc, text = _verdict("success", None, None, raw=raw)
        out.append((f"verdict: {name}", rc == 1 and "FAIL" in text, f"rc {rc}: {text.strip()}"))
    return out


# ---- ci.yml agrees with ci-route.py ---------------------------------------------

def _load(name):
    import yaml  # pylint: disable=import-outside-toplevel
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    # PyYAML reads the bare key `on` as the boolean True.
    return doc, (doc.get("on", doc.get(True)) or {})


def run_workflow_cases():
    try:
        import yaml  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return [("ci.yml: PyYAML importable", False, "pip install pyyaml - the ci.yml half did NOT run")]
    out = []
    doc, on = _load("ci.yml")
    jobs = doc.get("jobs") or {}
    out.append(("ci.yml: starts on pull_request only", set(on) == {"pull_request"}, f"on: {on}"))

    outputs = (jobs.get("changes") or {}).get("outputs") or {}
    for s in cr.ROUTED:
        want = f"${{{{ steps.route.outputs.{s} }}}}"
        out.append((f"ci.yml: changes exports {s}", outputs.get(s) == want, f"{s}: {outputs.get(s)!r}"))

    for s, job in cr.JOB.items():
        spec = jobs.get(job) or {}
        uses = spec.get("uses", "")
        if s in cr.ROUTED:
            want_if = f"needs.changes.outputs.{s} == 'true'"
            ok = spec.get("if") == want_if
        else:
            want_if, ok = None, "if" not in spec
        out.append((f"ci.yml: job {job} gated on {want_if}", ok and spec.get("needs") == "changes",
                    f"{job}: if={spec.get('if')!r} needs={spec.get('needs')!r}"))
        called = uses[len("./.github/workflows/"):] if uses.startswith("./.github/workflows/") else ""
        if not called or not os.path.isfile(os.path.join(WORKFLOWS, called)):
            out.append((f"ci.yml: job {job} calls a workflow in this repo", False, f"uses: {uses!r}"))
            continue
        _, con = _load(called)
        out.append((f"{called}: callable, and not started by pull_request itself",
                    "workflow_call" in con and "pull_request" not in con, f"on: {sorted(con)}"))

    gate = next((j for j in jobs.values() if j.get("name") == "CI gate"), {})
    needs = set(gate.get("needs") or [])
    want = set(cr.JOB.values()) | {"changes"}
    out.append(("ci.yml: CI gate needs every job", needs == want,
                f"missing {sorted(want - needs)}, extra {sorted(needs - want)}"))
    out.append(("ci.yml: CI gate runs if: always()", gate.get("if") == "always()", f"if={gate.get('if')!r}"))
    every = set(jobs) - {k for k, j in jobs.items() if j is gate}
    out.append(("ci.yml: no job outside the gate's needs", every == want,
                f"jobs {sorted(every)} vs {sorted(want)}"))

    # Nothing else may start on a pull_request without a reason written here:
    # it would run before routing and outside the gate.
    allowed = {"ci.yml": "the dispatcher",
               "plugin-evals.yml": "paths-filtered, billed model calls; not a required check",
               "runner-autostart.yml": "starts the self-hosted runner host; checks nothing"}
    for name in sorted(os.listdir(WORKFLOWS)):
        if not name.endswith((".yml", ".yaml")):
            continue
        _, con = _load(name)
        if "pull_request" in con and name not in allowed:
            out.append((f"{name}: does not start on pull_request outside ci.yml", False,
                        "call it from ci.yml (workflow_call) or add it to `allowed` with a reason"))
    return out


def main() -> int:
    results = run_route_cases() + run_changes_cases() + run_verdict_cases() + run_workflow_cases()
    failed = 0
    for name, ok, detail in results:
        if ok:
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}\n       {detail}")
    print(f"\nci-route: {len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

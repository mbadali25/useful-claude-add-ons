#!/usr/bin/env python3
"""Which CI suites a pull request needs, from the files it changes.

.github/workflows/ci.yml is the only workflow a pull_request starts. Its first
job runs `changes` here; every suite after it starts only when its output is
`true`, and its last job, `CI gate` (the one required check), runs `verdict`.

Run: python3 scripts/ci-route.py changes [--base REV] [--head REV]
         git diff --no-renames --name-only BASE HEAD; prints `key=true|false`
         lines for $GITHUB_OUTPUT. Default BASE is HEAD^1, the base-branch
         parent of a pull_request merge commit.
     python3 scripts/ci-route.py route PATH...
         the same lines for a given file list; what the suite drives.
     python3 scripts/ci-route.py verdict
         reads CHANGES_RESULT, ROUTES (needs.changes.outputs as JSON) and
         RESULTS (needs as JSON) from the environment; exit 0 only when the
         routing job succeeded, every ALWAYS suite succeeded, every routed suite
         succeeded and every unrouted suite was skipped.

Two suites always run: marketplace (scripts/check-marketplace.py, the repo's
gate) and instruction-budgets. Both are minutes or less, and both read docs: a
self-claim in README.md, a VERIFYING.md path or a referenced runbook is theirs
to check, so no change is too small for them.

The routed suites, and why each rule below says what it says, were MEASURED, not
read from the code: each suite ran under `strace -f` and every path under the
checkout it opened, stat'ed or listed was recorded (2026-10-05, this container).
That found reads nobody would guess - doc-builder's checklist lists every
skills/*/assets for a brand.json, crew's tests read docs/guides/crew/ and
.claude-plugin/marketplace.json. Re-measure before narrowing a rule.

An unknown never collapses into "nothing to run":
  - a path no rule names routes to EVERY suite;
  - a diff that cannot be computed routes to every suite;
  - .github/** routes to every suite (a workflow change runs what it changes).
"""

import json
import os
import re
import subprocess
import sys

ROUTED = ("crew", "shell", "mcp", "lint")
ALWAYS = ("marketplace", "budgets")
EVERY = frozenset(ROUTED)
# Suite -> its job id in ci.yml (the keys of `needs` the gate receives).
# scripts/_test/ci-route.py holds ci.yml to this table: an output per routed
# suite, a job per suite whose `if:` reads that output, and a gate needing all.
JOB = {"crew": "pytest-crew", "shell": "shell-suites", "mcp": "mcp-servers",
       "lint": "pylint", "marketplace": "marketplace", "budgets": "budgets"}

# First match wins. A path's suites are its rule's set plus `lint` for any .py
# (pylint and ruff read nothing else that matters - see LINT_CONFIG).
RULES = (
    (".github/**", EVERY),
    ("mcp-servers/**", frozenset({"mcp"})),
    # crew's tests read the crew guides (test_docs_routing, test_crew_train,
    # sabotage's archive list).
    ("docs/guides/crew/**", frozenset({"crew"})),
    ("docs/**", frozenset()),
    # The suites' own trees, and everything they scan: crew's tool-resolution
    # lint reads every .py under plugin/ and skills/, its pwsh-cache test every
    # tests/ and _test/ file, doc-builder every skills/*/assets, the obsidian
    # suite plugin/crew's hook scripts.
    ("plugin/**", frozenset({"crew", "shell"})),
    ("skills/**", frozenset({"crew", "shell"})),
    ("scripts/**", frozenset({"crew"})),
    (".crew/**", frozenset({"crew"})),
    (".claude-plugin/**", frozenset({"crew"})),
)
# Root-level prose. A path with a "/" never matches these.
ROOT_DOCS = ("*.md", "*.txt", "LICENSE", ".gitignore", ".gitattributes")
LINT_CONFIG = (".pylintrc", "ruff.toml", "pyproject.toml", "setup.cfg")


def _regex(glob: str) -> re.Pattern:
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


_RULES = tuple((_regex(g), s) for g, s in RULES)
_ROOT_DOCS = tuple(_regex(g) for g in ROOT_DOCS)


def suites_for(path: str) -> frozenset:
    path = path.strip().replace("\\", "/")
    lint = path.endswith(".py") or path.rsplit("/", 1)[-1] in LINT_CONFIG
    extra = frozenset({"lint"}) if lint else frozenset()
    for rx, suites in _RULES:
        if rx.match(path):
            return suites | extra
    if any(rx.match(path) for rx in _ROOT_DOCS):
        return extra
    return EVERY


def route(paths) -> dict:
    """{suite: bool} for every routed suite. An empty change list runs every
    suite: a PR that changes no file cannot be told apart from a diff that
    read nothing."""
    paths = [p for p in paths if p.strip()]
    if not paths:
        return {s: True for s in ROUTED}
    want = set()
    for p in paths:
        want |= suites_for(p)
    return {s: s in want for s in ROUTED}


def _lines(routes: dict, reason: str) -> str:
    out = [f"{s}={'true' if routes[s] else 'false'}" for s in ROUTED]
    out.append(f"reason={reason}")
    return "\n".join(out)


def cmd_changes(argv) -> int:
    base, head = "HEAD^1", "HEAD"
    it = iter(argv)
    for a in it:
        if a == "--base":
            base = next(it, base)
        elif a == "--head":
            head = next(it, head)
        else:
            print(f"ci-route: unknown argument {a!r}", file=sys.stderr)
            return 2
    try:
        res = subprocess.run(["git", "diff", "--no-renames", "--name-only", base, head],
                             capture_output=True, text=True, check=False, timeout=120)
        err = res.stderr.strip() if res.returncode != 0 else ""
    except (OSError, subprocess.SubprocessError) as exc:
        res, err = None, str(exc)
    if res is None or res.returncode != 0:
        print(f"::warning::ci-route: could not diff {base}..{head} ({err}), so every suite runs.",
              file=sys.stderr)
        print(_lines({s: True for s in ROUTED}, "diff-failed"))
        return 0
    paths = res.stdout.splitlines()
    routes = route(paths)
    for p in paths:
        print(f"  {p} -> {', '.join(sorted(suites_for(p))) or '(always-run suites only)'}",
              file=sys.stderr)
    skipped = [s for s in ROUTED if not routes[s]]
    if skipped:
        print(f"::notice::ci-route: {len(paths)} changed file(s); SKIPPED, not passed: "
              f"{', '.join(skipped)}. Push to main and the nightly schedule run every suite.",
              file=sys.stderr)
    print(_lines(routes, f"{len(paths)}-files" if paths else "no-files"))
    return 0


def cmd_route(argv) -> int:
    print(_lines(route(argv), f"{len(argv)}-files"))
    return 0


def verdict(changes_result: str, routes: dict, results: dict) -> list:
    """Why the gate fails, one line each; [] when it passes."""
    bad = []
    if changes_result != "success":
        return [f"changes: the routing job's result is {changes_result!r}, not 'success'"]
    for s in ALWAYS:
        got = (results.get(JOB[s]) or {}).get("result")
        if got != "success":
            bad.append(f"{JOB[s]}: always runs, result {got!r}")
    for s in ROUTED:
        flag = routes.get(s)
        if flag not in ("true", "false"):
            bad.append(f"{s}: routing output {flag!r} is neither 'true' nor 'false'")
            continue
        got = (results.get(JOB[s]) or {}).get("result")
        want = "success" if flag == "true" else "skipped"
        if got != want:
            bad.append(f"{JOB[s]}: routed {s}={flag}, so its result must be {want!r}; it is {got!r}")
    return bad


def cmd_verdict(_argv) -> int:
    try:
        routes = json.loads(os.environ.get("ROUTES") or "null")
        results = json.loads(os.environ.get("RESULTS") or "null")
    except json.JSONDecodeError as exc:
        print(f"CI gate: FAIL - unreadable ROUTES/RESULTS: {exc}")
        return 1
    if not isinstance(routes, dict) or not isinstance(results, dict):
        print("CI gate: FAIL - ROUTES or RESULTS is missing or not a JSON object")
        return 1
    bad = verdict(os.environ.get("CHANGES_RESULT", ""), routes, results)
    for line in bad:
        print(f"CI gate: FAIL - {line}")
    if bad:
        return 1
    ran = [JOB[s] for s in ALWAYS + ROUTED if s in ALWAYS or routes.get(s) == "true"]
    skipped = [JOB[s] for s in ROUTED if routes.get(s) == "false"]
    print(f"CI gate: PASS - ran {', '.join(ran)}"
          + (f"; skipped (not needed for these files) {', '.join(skipped)}" if skipped else ""))
    return 0


def main(argv) -> int:
    cmds = {"changes": cmd_changes, "route": cmd_route, "verdict": cmd_verdict}
    if not argv or argv[0] not in cmds:
        print(__doc__.split("\n\n", 1)[0], file=sys.stderr)
        print(f"usage: ci-route.py {{{'|'.join(cmds)}}} ...", file=sys.stderr)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

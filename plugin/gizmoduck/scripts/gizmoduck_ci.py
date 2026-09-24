#!/usr/bin/env python3
"""gizmoduck_ci.py - install and run gizmoduck security-scan pipelines (/gizmoduck:ci).

Rendering (run on the operator's machine):
  gizmoduck_ci.py render --platform github|bitbucket|both --staging-url URL [--staging-url URL ...]
                         --authorized-by TEXT [--repo PATH] [--production-url URL ...]
                         [--allow-ip-origin URL ...] [--enable nikto,nmap,sqlmap]
                         [--image REF] [--gizmoduck-ref SHA] [--default-branch main]
                         [--staging-environment staging] [--deploy-workflow NAME]
                         [--bitbucket-out PATH] [--apply] [--force]
      Dry run by default: prints every file it would write and writes nothing.
      --apply writes them; an existing file is refused unless --force.

Setup (run on the operator's machine, before render):
  detect         [--repo PATH] [--json]         # findings + Decision-needed blocks; writes nothing
  setup          --staging-url URL|none --auth none|header|exclude-protected
                 --accept high|medium|low (--scope all | --include GLOB ... --exclude GLOB ...)
                 [--openapi-path PATH|none] [--auth-header NAME] [--repo PATH] [--apply]
      Dry run by default. --apply writes gizmoduck-ci.json, and - only when crew
      is present - appends the accepted endpoints to .crew/endpoints.json as
      declared records. Owner answers only: nothing here is inferred.

Pipeline steps (run inside the rendered pipeline):
  endpoints      --config gizmoduck-ci.json --repo . --out DIR         # committed list + re-detect;
                                                                       # exit 2 UNVERIFIED on zero
  targets        --run-endpoints DIR/endpoints-run.json --out targets.json   # prod-refusal guard
                 (legacy: --endpoints .crew/endpoints.json)
  endpoint-stage --targets targets.json --out DIR                      # re-guards, then scans
  prepare-templates --dir DIR [--tier sweep]                           # seed / weekly-update templates
  code-stage     --path . --out DIR [--tier light|full|sweep] [--base-ref SHA]
  publish        --out DIR [--baseline FILE] [--title T]               # reports + diff.md
  gate           --baseline FILE --current FILE [--manifest FILE] [--block-at critical|high|never] ...
  sarif          FINDINGS --out FILE [--srcroot DIR]
  bb-insights    FINDINGS --gate gate.json --outdir DIR [--srcroot DIR]
  gh-previous-run --workflow FILE --artifact NAME [--trusted "main release/*"]  # prints run_id=...
  tickets        NEW.jsonl --out FILE [--yes]                          # SDP, opt-in only
  image-check                                                          # runner image build: doctor + every
                                                                       # scanner, or exit 1 (ci/Dockerfile)

Guard configuration at runtime comes from the environment: GIZMODUCK_STAGING_URLS
(baked into the rendered file), GIZMODUCK_ALLOWED_PROD_ORIGINS plus
GIZMODUCK_ALLOW_PROD_SCAN=true (both, or production is refused), and
GIZMODUCK_ALLOWED_IP_ORIGINS. See ci_guard.py for the rules.

Stdlib only apart from routine.py's PyYAML, which only the two *-stage
commands import.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import ci_detect
import ci_gate
import ci_guard
import ci_render

GIZMODUCK_PY = os.path.join(_HERE, "gizmoduck.py")
PLUGIN_JSON = os.path.join(os.path.dirname(_HERE), ".claude-plugin", "plugin.json")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
_SEV_LABEL = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}


def plugin_version():
    with open(PLUGIN_JSON, encoding="utf-8") as fh:
        return json.load(fh)["version"]


def _truthy(value):
    return str(value or "").strip().lower() == "true"


def _split(value):
    return [v for v in re.split(r"[\s,]+", value or "") if v]


def write_files(files, root):
    """Every file's content is already a finished string in `files` before
    the first open() - a truncating open must never run ahead of its payload."""
    for rel, content in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)


def write_json(path, obj):
    text = json.dumps(obj, indent=2) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# --------------------------------------------------------------------------
# Endpoint ledger ingestion (.crew/endpoints.json, written by crew_state.py)
# --------------------------------------------------------------------------

class LedgerError(ValueError):
    pass


def ingest_endpoints(doc, base_urls):
    """Turn ledger records into candidate URLs. Returns (candidates, skipped).

    The ledger's shape is `{"records": [{"id", "endpoint", "status", ...}],
    "nextSeq": N}` (crew_endpoints.declare_endpoint). A record's `endpoint` is
    a URL, a host, or a path; a path is joined onto every base URL. Closed
    records and values that are none of those three are skipped and reported,
    never guessed at. Every candidate still has to pass the guard.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("records"), list):
        raise LedgerError("endpoints.json has no 'records' list")
    candidates, skipped = [], []
    for n, rec in enumerate(doc["records"], 1):
        if not isinstance(rec, dict):
            skipped.append({"record": n, "reason": "not an object"})
            continue
        rid = str(rec.get("id") or f"record-{n}")
        value = rec.get("endpoint")
        if str(rec.get("status", "")).lower() == "closed":
            skipped.append({"id": rid, "endpoint": ci_guard.redact_url(value), "reason": "status is closed"})
            continue
        if not isinstance(value, str) or not value or any(ci_guard.bad_char(c) for c in value):
            skipped.append({"id": rid, "endpoint": ci_guard.redact_url(value),
                            "reason": "not a URL, host or path (free text, or whitespace/control characters "
                                      "anywhere - refused, not stripped - is not a target)"})
            continue
        lowered = value.lower()
        if lowered.startswith(("http://", "https://")):
            candidates.append((rid, value))
        elif value.startswith("/"):
            for base in base_urls:
                candidates.append((rid, urllib.parse.urljoin(base.rstrip("/") + "/", value.lstrip("/"))))
        elif "://" in value:
            skipped.append({"id": rid, "endpoint": ci_guard.redact_url(value), "reason": "scheme is not http(s)"})
        else:
            candidates.append((rid, "https://" + value))
    return candidates, skipped


def load_ledger(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except ValueError as exc:
            raise LedgerError(f"{path} is not valid JSON: {exc}") from exc


def policy_from_env(env):
    return ci_guard.Policy.build(
        staging_urls=_split(env.get("GIZMODUCK_STAGING_URLS")),
        production_urls=_split(env.get("GIZMODUCK_ALLOWED_PROD_ORIGINS")),
        allow_production=_truthy(env.get("GIZMODUCK_ALLOW_PROD_SCAN")),
        ip_allowed_urls=_split(env.get("GIZMODUCK_ALLOWED_IP_ORIGINS")),
    )


def _run_doc_as_ledger(run_doc):
    return {"records": [{"id": f"run-{i}", "endpoint": e.get("endpoint"), "status": "open"}
                        for i, e in enumerate(run_doc.get("endpoints") or [], 1) if isinstance(e, dict)]}


def build_targets(env, ledger_doc, redirects=True, fetch=ci_guard.http_fetch, run_doc=None):
    """The runtime guard. Returns (report, exit_code). Exit 2 when a configured
    staging URL is refused or nothing is left to scan; a refused ledger
    endpoint is dropped and listed, and scanned by nothing.

    With `run_doc` (the `endpoints` step's output) the endpoint list comes from
    it instead of the raw ledger, and the stage additionally needs at least one
    endpoint to survive the guard: a run that would scan only the bare base URL
    is UNVERIFIED, never a pass. GIZMODUCK_TARGET_URL (a manual run's URL)
    replaces the configured base URLs as what is scanned; it still has to pass
    the same guard, whose staging list does not change."""
    try:
        policy = policy_from_env(env)
    except ci_guard.GuardError as exc:
        return {"allowed": [], "refused": [{"url": None, "rule": exc.rule,
                                            "reason": ci_guard.redact_text(exc.reason)}],
                "skipped": []}, 2
    base_urls = _split(env.get("GIZMODUCK_TARGET_URL")) or _split(env.get("GIZMODUCK_STAGING_URLS"))
    report = {"allowed": [], "refused": [], "skipped": []}
    rc = 0
    if run_doc is not None:
        report["auth"] = run_doc.get("auth") or {"mode": "none"}
        if run_doc.get("status") != "OK" or not run_doc.get("endpoints"):
            report["refused"].append({"url": None, "source": "endpoints", "rule": "UNVERIFIED",
                                      "reason": run_doc.get("reason") or f"no endpoints - {ci_detect.DETECT_HINT}"})
            return report, 2
        ledger_doc = _run_doc_as_ledger(run_doc)

    def decide(url):
        d = ci_guard.check_target(url, policy)
        if d.allowed and redirects:
            d = ci_guard.check_redirects(url, policy, fetch=fetch)
        return d

    seen, covered = set(), 0
    for n, url in enumerate(base_urls, 1):
        d = decide(url)
        if not d.allowed:
            report["refused"].append({"url": ci_guard.redact_url(url), "source": "configured", "rule": d.rule,
                                      "reason": ci_guard.redact_text(d.reason)})
            rc = 2
            continue
        name = "staging" if n == 1 else f"staging-{n}"
        report["allowed"].append({"name": name, "url": url, "kind": "base"})
        seen.add(url)
    if ledger_doc is not None:
        candidates, skipped = ingest_endpoints(ledger_doc, base_urls)
        report["skipped"] = skipped
        for i, (rid, url) in enumerate(candidates, 1):
            if url.rstrip("/") in {u.rstrip("/") for u in seen}:
                covered += 1
                continue
            d = decide(url)
            if not d.allowed:
                report["refused"].append({"url": ci_guard.redact_url(url), "source": f"endpoints.json:{rid}",
                                          "rule": d.rule, "reason": ci_guard.redact_text(d.reason)})
                continue
            seen.add(url)
            covered += 1
            name = _SAFE_NAME.sub("-", f"endpoint-{rid}-{i}")
            report["allowed"].append({"name": name, "url": url, "kind": "endpoint"})
    if not report["allowed"]:
        rc = 2
    if run_doc is not None and not covered:
        report["refused"].append({"url": None, "source": "endpoints", "rule": "UNVERIFIED",
                                  "reason": f"every endpoint was refused by the guard, so none would be "
                                            f"scanned - {ci_detect.DETECT_HINT}"})
        rc = 2
    return report, rc


def cmd_targets(args, env=None):
    env = os.environ if env is None else env
    run_doc, doc = None, None
    try:
        if args.run_endpoints:
            if not os.path.exists(args.run_endpoints):
                raise LedgerError(f"{args.run_endpoints} is missing - the endpoints step did not run; "
                                  f"the endpoint stage is UNVERIFIED")
            with open(args.run_endpoints, encoding="utf-8") as fh:
                run_doc = json.load(fh)
            if not isinstance(run_doc, dict):
                raise LedgerError(f"{args.run_endpoints} is not a JSON object")
        else:
            doc = load_ledger(args.endpoints)
    except (LedgerError, ValueError) as exc:
        print(f"GIZMODUCK_GUARD_REFUSED: {ci_guard.redact_text(str(exc))}", file=sys.stderr)
        return 2
    try:
        report, rc = build_targets(env, doc, redirects=not args.no_redirect_check, run_doc=run_doc)
    except LedgerError as exc:
        print(f"GIZMODUCK_GUARD_REFUSED: {ci_guard.redact_text(str(exc))}", file=sys.stderr)
        return 2
    write_json(args.out, report)
    for t in report["allowed"]:
        print(f"allowed  {ci_guard.redact_url(t['url'])}  ({t['kind']})")
    for r in report["refused"]:
        print(f"REFUSED  {ci_guard.redact_url(r['url'])}  [{r['rule']}] {ci_guard.redact_text(r['reason'])}")
    for s in report["skipped"]:
        print(f"skipped  {ci_guard.redact_url(s.get('endpoint'))!r}  {s['reason']}")
    if rc:
        print("GIZMODUCK_GUARD_REFUSED: no endpoint scan will run", file=sys.stderr)
    return rc


# --------------------------------------------------------------------------
# Stages (both call routine.run_routine; nothing here invokes a scanner itself)
# --------------------------------------------------------------------------

# How each endpoint scanner is kept on the target origin. The guard's redirect
# probe (ci_guard R9) is a pre-check only - a server can answer the probe and
# a scanner differently - so the control is per scanner, plus the post-scan
# audit of every recorded URL (ci_guard.audit_findings) in cmd_endpoint_stage.
#   nuclei   -dr (-disable-redirects): no template follows a redirect.
#   zap      the AF context's includePaths is the target origin only, anchored
#            and regex-escaped (scanners/zap.py), so the spider and active
#            scan never request an out-of-scope URL; a Location elsewhere is
#            out of scope.
#   testssl  speaks TLS to the one host:port it is given; it reports a
#            Location header and has no option to follow it.
#   nikto    follows nothing unless -followredirects is passed; it is not.
#   nmap     host-level; NSE's http library refuses a redirect to another
#            host or port by default (its redirect_ok rules).
#   sqlmap   --ignore-redirects (opts["no_redirects"], scanners/sqlmap.py).
NUCLEI_NO_REDIRECTS = "-dr"


def endpoint_manifest(targets, authorized_by, enable, templates_dir=None, headers=None):
    import routine
    extra = f"-t {templates_dir} -duc" if templates_dir else "-duc"
    extra += f" {NUCLEI_NO_REDIRECTS}"
    out = []
    for t in targets:
        tools = ["nuclei", "zap"]
        options = {"extra": extra, "no_redirects": True}
        if headers:
            options["headers"] = list(headers)
        if t["kind"] == "base":
            tools.append("testssl")
            tools += [x for x in ("nmap", "nikto") if x in enable]
        else:
            tools += [x for x in ("nikto",) if x in enable]
            if "sqlmap" in enable:
                tools.append("sqlmap")
                options["sqlmap"] = True
        out.append(routine.Target(name=t["name"], kind="web", url=t["url"],
                                  tools=tools, options=options))
    return routine.Manifest(authorized_by=authorized_by, targets=out)


def cmd_endpoint_stage(args, env=None, runner=None, fetch=ci_guard.http_fetch):
    env = os.environ if env is None else env
    with open(args.targets, encoding="utf-8") as fh:
        report = json.load(fh)
    policy = policy_from_env(env)
    targets = []
    for t in report.get("allowed", []):
        d = ci_guard.check_target(t["url"], policy)
        if d.allowed and not args.no_redirect_check:
            d = ci_guard.check_redirects(t["url"], policy, fetch=fetch)
        if not d.allowed:
            print(f"GIZMODUCK_GUARD_REFUSED: {ci_guard.redact_url(t['url'])} [{d.rule}] "
                  f"{ci_guard.redact_text(d.reason)}", file=sys.stderr)
            return 2
        targets.append(t)
    if not targets:
        print("GIZMODUCK_GUARD_REFUSED: no targets", file=sys.stderr)
        return 2
    enable = set(_split(env.get("GIZMODUCK_ENABLE")))
    auth = report.get("auth") or {"mode": "none"}
    headers = None
    if auth.get("mode") == "header":
        secret = auth.get("secret") or ci_detect.AUTH_SECRET
        value = (env.get(secret) or "").strip()
        name = auth.get("header") or "Authorization"
        if not value or any(c in value for c in "\r\n") or not re.fullmatch(r"[A-Za-z0-9-]+", name):
            print(f"GIZMODUCK_GUARD_REFUSED: gizmoduck-ci.json sets auth mode 'header' but the {secret} "
                  f"secret is empty or malformed; refusing to scan protected endpoints anonymously while "
                  f"reporting them as scanned", file=sys.stderr)
            return 2
        headers = [f"{name}: {value}"]
    manifest = endpoint_manifest(targets, env.get("GIZMODUCK_AUTHORIZED_BY", ""), enable,
                                 env.get("GIZMODUCK_NUCLEI_TEMPLATES"), headers)
    if runner is None:
        import routine
        runner = routine.run_routine
    runner(manifest, args.out, confirm="sqlmap" in enable)
    return audit_endpoint_findings(os.path.join(args.out, "findings.jsonl"), policy)


def audit_endpoint_findings(findings_path, policy):
    """R9's second half: every URL the scanners recorded must still be on an
    allowed origin. A missing findings file means the scan did not finish, and
    an out-of-policy URL means a scanner left the target; both exit 2."""
    if not os.path.isfile(findings_path):
        print(f"GIZMODUCK_GUARD_REFUSED: {findings_path} is missing - the scan did not complete, so "
              f"what it requested cannot be audited", file=sys.stderr)
        return 2
    records = []
    with open(findings_path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                print(f"GIZMODUCK_GUARD_REFUSED: {findings_path}:{n} is not JSON - cannot audit the "
                      f"scan's requests", file=sys.stderr)
                return 2
    bad = ci_guard.audit_findings(records, policy)
    for fld, url, d in bad:
        print(f"GIZMODUCK_GUARD_REFUSED: a scanner recorded {url} ({fld}) outside the allowed origins "
              f"[{d.rule}] {ci_guard.redact_text(d.reason)}", file=sys.stderr)
    return 2 if bad else 0


def code_manifest(path, authorized_by):
    import routine
    return routine.Manifest(authorized_by=authorized_by, targets=[
        routine.Target(name="code", kind="code", path=path),
        routine.Target(name="deps", kind="deps", path=path),
        routine.Target(name="iac", kind="iac", path=path),
    ])


_MANIFEST_NAMES = {
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "pipfile", "pipfile.lock", "poetry.lock", "pyproject.toml", "uv.lock",
    "setup.py", "setup.cfg", "go.mod", "go.sum", "cargo.toml", "cargo.lock", "gemfile", "gemfile.lock",
    "composer.json", "composer.lock", "packages.lock.json", "packages.config", "directory.packages.props",
    "pom.xml", "build.gradle", "build.gradle.kts", "gradle.lockfile", "mix.lock", "pubspec.lock",
    "podfile.lock", "package.resolved",
}
_MANIFEST_RE = re.compile(r"(?i)^requirements[\w.-]*\.txt$|\.(csproj|fsproj|vbproj)$")


def is_dependency_manifest(rel):
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    return name.lower() in _MANIFEST_NAMES or bool(_MANIFEST_RE.search(name))


def changed_files(path, base_ref, run=subprocess.run):
    """Files added or changed since the merge base with base_ref, relative to
    path. Raises RuntimeError when git cannot say: a light check that cannot
    tell what changed must fail, not scan nothing and pass."""
    root = os.path.abspath(path)
    p = run(["git", "-c", f"safe.directory={root}", "-C", root, "diff", "--name-only",
             "--diff-filter=ACMRT", f"{base_ref}...HEAD"], capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"git diff {base_ref}...HEAD failed (exit {p.returncode}): "
                           f"{(p.stderr or '').strip()}")
    return sorted({ln.strip() for ln in p.stdout.splitlines() if ln.strip()})


def tiered_code_manifest(path, authorized_by, tier, base_ref=None, env=None, run=subprocess.run):
    """(Manifest, plan) for one trigger tier. The plan records what runs and
    why, and is written beside the findings so a light run's gaps are stated,
    not silent.

      light  Semgrep diff-aware on the changed files; Trivy only when a
             lockfile/manifest changed; Checkov only when a *.tf changed;
             gitleaks over the commits base..HEAD.
      full   Semgrep, Trivy fs, Checkov + Trivy config, gitleaks over the
             whole git history.
      sweep  full, plus Dependency-Check against NVD (cached data directory).
    """
    import routine
    env = env or {}
    root = os.path.abspath(path)
    plan = {"tier": tier, "ran": [], "skipped": []}
    targets = []
    if tier == "light":
        if not base_ref:
            raise RuntimeError("--tier light needs --base-ref (the pull request's base commit)")
        files = [f for f in changed_files(path, base_ref, run=run) if os.path.isfile(os.path.join(root, f))]
        plan["changed_files"] = len(files)
        if files:
            targets.append(routine.Target(name="code", kind="code", path=root, options={
                "semgrep_paths": files, "semgrep_baseline_commit": base_ref, "cwd": root}))
            plan["ran"].append(f"semgrep on {len(files)} changed file(s), baseline {base_ref[:12]}")
        else:
            plan["skipped"].append("semgrep: no added or changed files")
        if any(is_dependency_manifest(f) for f in files):
            targets.append(routine.Target(name="deps", kind="deps", path=root, tools=["trivy"]))
            plan["ran"].append("trivy: a lockfile/manifest changed")
        else:
            plan["skipped"].append("trivy: no lockfile/manifest changed")
        if any(f.endswith(".tf") for f in files):
            targets.append(routine.Target(name="iac", kind="iac", path=root, tools=["checkov"]))
            plan["ran"].append("checkov: a *.tf file changed")
        else:
            plan["skipped"].append("checkov: no *.tf file changed")
        targets.append(routine.Target(name="secrets", kind="secrets", path=root, options={
            "gitleaks_mode": "git", "gitleaks_log_opts": f"{base_ref}..HEAD", "cwd": root}))
        plan["ran"].append(f"gitleaks on commits {base_ref[:12]}..HEAD")
    elif tier in ("full", "sweep"):
        targets.append(routine.Target(name="code", kind="code", path=root))
        deps_opts = {}
        if tier == "sweep" and env.get("GIZMODUCK_DEPCHECK_DATA"):
            deps_opts["depcheck_data_dir"] = env["GIZMODUCK_DEPCHECK_DATA"]
        targets.append(routine.Target(name="deps", kind="deps", path=root,
                                      tools=None if tier == "sweep" else ["trivy"], options=deps_opts))
        targets.append(routine.Target(name="iac", kind="iac", path=root))
        # Git mode over the whole history (the pipelines clone it in full): a
        # secret committed and then deleted is still in the history, and a
        # tree scan would miss it where tier 1's commit-range scan does not.
        targets.append(routine.Target(name="secrets", kind="secrets", path=root,
                                      options={"gitleaks_mode": "git", "cwd": root}))
        plan["ran"] += ["semgrep", "trivy fs", "checkov + trivy config", "gitleaks (full git history)"]
        if tier == "sweep":
            plan["ran"].append("dependency-check (NVD)")
        else:
            plan["skipped"].append("dependency-check: weekly sweep only")
    else:
        raise RuntimeError(f"unknown tier {tier!r}")
    return routine.Manifest(authorized_by=authorized_by, targets=targets), plan


def cmd_code_stage(args, env=None, runner=None, run=subprocess.run):
    env = os.environ if env is None else env
    authorized_by = env.get("GIZMODUCK_AUTHORIZED_BY", "")
    if args.tier:
        try:
            manifest, plan = tiered_code_manifest(args.path, authorized_by, args.tier, args.base_ref, env, run)
        except RuntimeError as exc:
            print(f"GIZMODUCK_CODE_STAGE_FAILED: {exc}", file=sys.stderr)
            return 2
        write_json(os.path.join(args.out, "tier-plan.json"), plan)
        for line in plan["ran"]:
            print(f"runs     {line}")
        for line in plan["skipped"]:
            print(f"skipped  {line}")
    else:
        manifest = code_manifest(args.path, authorized_by)
    if runner is None:
        import routine
        runner = routine.run_routine
    runner(manifest, args.out)
    return 0


# --------------------------------------------------------------------------
# Endpoint list per run, and the Nuclei template cache
# --------------------------------------------------------------------------

_MAX_DOC_BYTES = 5_000_000


def fetch_document(url, timeout=20.0):
    """(status, body bytes) for one GET, redirects NOT followed - the guard has
    already walked the chain, and this fetch must not wander off it."""
    opener = urllib.request.build_opener(ci_guard._NoRedirect())  # pylint: disable=protected-access
    req = urllib.request.Request(url, headers={"User-Agent": "gizmoduck-ci-endpoints",
                                               "Accept": "application/json, application/yaml"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read(_MAX_DOC_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def live_openapi(config, env, fetch=ci_guard.http_fetch, fetch_doc=fetch_document):
    """([(METHOD, path, protected)], note). Never raises: a live document that
    cannot be reached is reported and the committed list still stands."""
    path = ((config or {}).get("staging") or {}).get("openapi_path")
    if not path:
        return [], "not configured"
    bases = _split(env.get("GIZMODUCK_TARGET_URL")) or _split(env.get("GIZMODUCK_STAGING_URLS"))
    if not bases:
        return [], "no staging URL configured"
    url = urllib.parse.urljoin(bases[0].rstrip("/") + "/", path.lstrip("/"))
    try:
        policy = policy_from_env(env)
    except ci_guard.GuardError as exc:
        return [], f"guard refused [{exc.rule}] {exc.reason}"
    d = ci_guard.check_target(url, policy)
    if d.allowed:
        d = ci_guard.check_redirects(url, policy, fetch=fetch)
    if not d.allowed:
        return [], f"{url} refused by the guard [{d.rule}] {d.reason}"
    try:
        status, body = fetch_doc(url)
    except (OSError, ValueError) as exc:
        return [], f"{url} unreachable ({exc})"
    if status != 200:
        return [], f"{url} answered HTTP {status}"
    if len(body) > _MAX_DOC_BYTES:
        return [], f"{url} is larger than {_MAX_DOC_BYTES} bytes; not read"
    try:
        text = body.decode("utf-8")
        try:
            doc = json.loads(text)
        except ValueError:
            import yaml
            doc = yaml.safe_load(text)
        ops, _ = ci_detect.parse_openapi(doc)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Any unreadable body (bad UTF-8, YAML error, no PyYAML, not OpenAPI)
        # is a note, not a crash: the committed list still stands.
        return [], f"{url} is not a readable OpenAPI document ({type(exc).__name__}: {exc})"
    return ops, f"{url}: {len(ops)} operation(s)"


def cmd_endpoints(args, env=None, fetch=ci_guard.http_fetch, fetch_doc=fetch_document):
    env = os.environ if env is None else env
    try:
        config = None
        if os.path.exists(args.config):
            with open(args.config, encoding="utf-8") as fh:
                config = json.load(fh)
            if not isinstance(config, dict):
                raise ValueError(f"{args.config} is not a JSON object")
    except (OSError, ValueError) as exc:
        print(f"GIZMODUCK_ENDPOINTS_UNVERIFIED: {exc} - {ci_detect.DETECT_HINT}", file=sys.stderr)
        return 2
    try:
        ledger = load_ledger(os.path.join(args.repo, ".crew", "endpoints.json"))
    except LedgerError as exc:
        print(f"GIZMODUCK_ENDPOINTS_UNVERIFIED: {exc} - {ci_detect.DETECT_HINT}", file=sys.stderr)
        return 2
    det = ci_detect.detect(args.repo)
    ops, note = ([], "skipped (--no-live)") if args.no_live else live_openapi(config, env, fetch, fetch_doc)
    run = ci_detect.merge_for_run(config, ledger, det, ops)
    run["config_present"] = config is not None
    run["live_openapi"] = note
    write_json(os.path.join(args.out, "endpoints-run.json"), run)
    report = ci_detect.render_run_report(run, note)
    if config is None:
        report += f"\n_No {ci_detect.CONFIG_NAME} is committed - {ci_detect.DETECT_HINT}._\n"
    with open(os.path.join(args.out, "endpoints-run.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(report)
    print(report)
    if run["status"] != "OK":
        print(f"GIZMODUCK_ENDPOINTS_UNVERIFIED: {run['reason']}", file=sys.stderr)
        return 2
    return 0


def cmd_prepare_templates(args, run=subprocess.run, seeds=None):
    """Make args.dir hold Nuclei templates: seed it from the runner image (or
    the inline bootstrap's ~/nuclei-templates) when the cache came back empty,
    and on the weekly sweep update it in place."""
    import shutil
    target = os.path.abspath(args.dir)
    seeds = seeds if seeds is not None else ["/opt/nuclei-templates",
                                            os.path.expanduser("~/nuclei-templates")]
    has = os.path.isdir(target) and any(os.scandir(target))
    if not has:
        for seed in seeds:
            if os.path.isdir(seed) and os.path.abspath(seed) != target:
                shutil.copytree(seed, target, dirs_exist_ok=True)
                print(f"gizmoduck: templates seeded from {seed}")
                has = True
                break
    if args.tier == "sweep" or not has:
        os.makedirs(target, exist_ok=True)
        p = run(["nuclei", "-update-templates", "-ud", target, "-silent"], capture_output=True, text=True,
                check=False)
        if p.returncode != 0:
            print(f"gizmoduck: nuclei -update-templates failed (exit {p.returncode}): "
                  f"{(p.stderr or p.stdout or '').strip()[:500]}", file=sys.stderr)
            return 0 if has else 2
        print(f"gizmoduck: templates updated in {target}")
    return 0


# --------------------------------------------------------------------------
# Setup: detect, then persist only what the owner decided
# --------------------------------------------------------------------------

def cmd_detect(args):
    det = ci_detect.detect(args.repo)
    try:
        config = ci_detect.load_config(args.repo)
    except ci_detect.SetupError as exc:
        print(f"GIZMODUCK_CI_REFUSED: {exc}", file=sys.stderr)
        return 2
    decs = ci_detect.decisions(det, config)
    if args.json:
        print(json.dumps({"detection": det.to_dict(),
                          "decisions": [{"key": d.key, "question": d.question, "options": d.options}
                                        for d in decs]}, indent=2))
        return 0
    print(ci_detect.render_findings(det))
    for d in decs:
        print(d.render())
    if not decs:
        print(f"# nothing left to decide - {ci_detect.CONFIG_NAME} settles every question")
    return 0


def cmd_setup(args):
    det = ci_detect.detect(args.repo)
    try:
        config, ledger_new = ci_detect.build_config(
            det, args.staging_url, args.auth, args.accept, include=args.include or (),
            exclude=args.exclude or (), scope_all=args.scope == "all", openapi_path=args.openapi_path,
            auth_header=args.auth_header)
        additions = ci_detect.ledger_additions(args.repo, ledger_new) if ledger_new else []
    except ci_detect.SetupError as exc:
        print(f"GIZMODUCK_CI_REFUSED: {exc}", file=sys.stderr)
        return 2
    text = ci_detect.config_text(config)
    print(f"===== {ci_detect.CONFIG_NAME} =====")
    print(text)
    if det.crew_present:
        print(f"===== {ci_detect.LEDGER_REL}: {len(additions)} declared record(s) to append =====")
        for e in additions:
            print(f"+ {e['path']}  ({e['source']}, {e['confidence']})")
    if not args.apply:
        print("# dry run - nothing written. Re-run with --apply once the owner has confirmed the above.")
        return 0
    cfg_path = os.path.join(args.repo, ci_detect.CONFIG_NAME)
    with open(cfg_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {cfg_path}")
    if additions:
        try:
            added = ci_detect.apply_ledger(args.repo, additions,
                                           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        except (ci_detect.SetupError, OSError, ValueError) as exc:
            print(f"GIZMODUCK_CI_REFUSED: {exc}", file=sys.stderr)
            return 2
        print(f"appended {len(added)} declared record(s) to {os.path.join(args.repo, ci_detect.LEDGER_REL)}")
    return 0


# --------------------------------------------------------------------------
# publish / gate / sarif / bb-insights
# --------------------------------------------------------------------------

def cmd_publish(args, run=subprocess.run):
    findings = os.path.join(args.out, "findings.jsonl")
    base = [sys.executable, GIZMODUCK_PY]
    steps = [
        ("report.md", base + ["report", findings, "--format", "md", "--out",
                              os.path.join(args.out, "report.md"), "--title", args.title]),
        ("report.html", base + ["report", findings, "--format", "html", "--out",
                                os.path.join(args.out, "report.html"), "--title", args.title]),
        ("report.pdf", base + ["report", findings, "--format", "pdf", "--out",
                               os.path.join(args.out, "report.pdf"), "--title", args.title]),
    ]
    rc = 0
    for label, argv in steps:
        p = run(argv, capture_output=True, text=True, check=False)
        if p.returncode != 0:
            print(f"{label}: exit {p.returncode}: {(p.stderr or p.stdout).strip()}", file=sys.stderr)
            if label != "report.pdf":
                rc = 1
    diff_path = os.path.join(args.out, "diff.md")
    if args.baseline and os.path.exists(args.baseline):
        p = run(base + ["diff", args.baseline, findings, "--min-severity", "low"],
                capture_output=True, text=True, check=False)
        text = p.stdout if p.returncode == 0 else f"diff failed (exit {p.returncode}): {p.stderr}"
    else:
        text = "# Scan Diff\n\n_No baseline was available, so nothing can be called new or resolved._\n"
    with open(diff_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return rc


def cmd_gate(args, env=None):
    env = os.environ if env is None else env
    trust = _truthy(env.get("GIZMODUCK_TRUST_ASSIGNED_SEVERITY"))
    try:
        current = ci_gate.load_findings(args.current, trust)
        baseline = None
        if args.baseline and os.path.exists(args.baseline):
            baseline = ci_gate.load_findings(args.baseline, trust)
        manifest = None
        if args.manifest:
            if not os.path.exists(args.manifest):
                raise ci_gate.GateInputError(f"run manifest {args.manifest} is missing")
            with open(args.manifest, encoding="utf-8") as fh:
                manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"GIZMODUCK_GATE_FAILED: unreadable input, failing closed: {exc}", file=sys.stderr)
        return 2
    result = ci_gate.evaluate(baseline, current, manifest,
                              allow_missing_baseline=_truthy(env.get("GIZMODUCK_ALLOW_NO_BASELINE")),
                              allow_incomplete=_truthy(env.get("GIZMODUCK_ALLOW_INCOMPLETE")),
                              block_at=ci_gate.BLOCK_AT[args.block_at])
    if args.json_out:
        write_json(args.json_out, result.to_dict())
    if args.new_out:
        lines = "".join(json.dumps(f.record) + "\n" for f in result.new_blocking)
        with open(args.new_out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(lines)
    verdict = "FAIL" if result.fail else ("REPORT ONLY" if args.block_at == "never" else "PASS")
    summary = [f"## gizmoduck gate: {verdict} (blocks at: {args.block_at})", ""]
    summary += [f"- {r}" for r in result.reasons] or [
        "- no new Critical findings" if args.block_at == "critical" else "- no new Critical/High findings"]
    for f in result.new_blocking + result.new_unknown:
        summary.append(f"  - [{f.severity_label}] {f.name} `{f.key[0]}` @ {f.key[1]}")
    text = "\n".join(summary) + "\n"
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 1 if result.fail else 0


def _path_line(matched_at, srcroot):
    where = str(matched_at or "")
    path, sep, tail = where.rpartition(":")
    line = None
    if sep and tail.isdigit():
        line = int(tail)
    else:
        path = where
    if srcroot and path.startswith(srcroot.rstrip("/") + "/"):
        path = path[len(srcroot.rstrip("/")) + 1:]
    path = path.removeprefix("./")
    return path, line


def _read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(ci_gate.parse_line(line.strip(), where=path))
    return out


def _key_id(key):
    return hashlib.sha256(json.dumps(list(key)).encode("utf-8")).hexdigest()[:32]


def to_sarif(findings, srcroot="", version=""):
    rules, results = {}, []
    levels = {4: "error", 3: "error", 2: "warning", 1: "note", 0: "note"}
    scores = {4: "9.5", 3: "8.0", 2: "5.5", 1: "2.0", 0: "0.0"}
    for f in findings:
        rec = f.record
        rid = f.key[0] or "gizmoduck:unknown"
        if rid not in rules:
            rule = {"id": rid, "name": rid, "shortDescription": {"text": f.name[:1000] or rid},
                    "properties": {"tags": ["security"]}}
            if f.severity >= 0:
                rule["properties"]["security-severity"] = scores[f.severity]
            refs = [r for r in (rec.get("reference") or []) if str(r).startswith("http")]
            if refs:
                rule["helpUri"] = refs[0]
            rules[rid] = rule
        path, line = _path_line(rec.get("matched_at") or rec.get("host"), srcroot)
        loc = {"physicalLocation": {"artifactLocation": {"uri": path or "."}}}
        if line and line > 0:
            loc["physicalLocation"]["region"] = {"startLine": line}
        desc = str(rec.get("description") or "").strip()
        text = f"{f.name} [{f.severity_label}]" + (f" - {desc[:800]}" if desc else "")
        results.append({"ruleId": rid, "level": levels.get(f.severity, "warning"),
                        "message": {"text": text}, "locations": [loc],
                        "partialFingerprints": {"gizmoduckKey/v1": _key_id(f.key)}})
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "gizmoduck", "version": version,
                                          "informationUri": ci_render.SOURCE_REPO,
                                          "rules": list(rules.values())}},
                      "results": results}]}


def cmd_sarif(args):
    write_json(args.out, to_sarif(_read_jsonl(args.findings), args.srcroot, plugin_version()))
    return 0


def bb_insights(findings, gate, srcroot="", chunk=100, limit=1000):
    bb_sev = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW", 0: "LOW"}
    report = {
        "title": "gizmoduck security scan",
        "details": ("; ".join(gate.get("reasons") or []) or "No new Critical/High findings.")[:2000],
        "report_type": "SECURITY",
        "reporter": "gizmoduck",
        "result": "FAILED" if gate.get("fail", True) else "PASSED",
        "data": [
            {"title": "New Critical/High", "type": "NUMBER", "value": len(gate.get("new_blocking") or [])},
            {"title": "New findings", "type": "NUMBER", "value": int(gate.get("new_total") or 0)},
            {"title": "Total findings", "type": "NUMBER", "value": len(findings)},
        ],
    }
    annotations = []
    for f in findings[:limit]:
        path, line = _path_line(f.record.get("matched_at") or f.record.get("host"), srcroot)
        a = {"external_id": _key_id(f.key), "annotation_type": "VULNERABILITY",
             "summary": f"[{f.severity_label}] {f.name}"[:450],
             "severity": bb_sev.get(f.severity, "HIGH")}
        desc = str(f.record.get("description") or "").strip()
        if desc:
            a["details"] = desc[:2000]
        if path:
            a["path"] = path
        if line and line > 0:
            a["line"] = line
        annotations.append(a)
    chunks = [annotations[i:i + chunk] for i in range(0, len(annotations), chunk)]
    return report, chunks


def cmd_bb_insights(args):
    with open(args.gate, encoding="utf-8") as fh:
        gate = json.load(fh)
    report, chunks = bb_insights(_read_jsonl(args.findings), gate, args.srcroot)
    write_json(os.path.join(args.outdir, "report.json"), report)
    for i, c in enumerate(chunks):
        write_json(os.path.join(args.outdir, f"annotations-{i:03d}.json"), c)
    return 0


# --------------------------------------------------------------------------
# GitHub baseline lookup
# --------------------------------------------------------------------------

_UNTRUSTED_EVENTS = {"pull_request", "pull_request_target", "pull_request_review",
                     "pull_request_review_comment", "issue_comment", "merge_group"}


def _trusted_run(run, repo, trusted):
    """A run whose results may become a baseline: not a pull-request event, from
    this repository (not a fork), on a branch matching a trusted pattern."""
    head_repo = (run.get("head_repository") or {}).get("full_name")
    branch = run.get("head_branch") or ""
    return (run.get("event") not in _UNTRUSTED_EVENTS and head_repo == repo
            and any(fnmatch.fnmatchcase(branch, pat) for pat in trusted))


def previous_run_id(workflow, trusted, env, opener=urllib.request.urlopen, artifact=None):
    """The newest successful, TRUSTED run of `workflow` (see _trusted_run) that
    still has `artifact`. "" when there is none - the gate then fails closed on
    the missing baseline unless the first-run opt-in is set."""
    api = env.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    repo = env["GITHUB_REPOSITORY"]
    trusted = [t for t in (trusted or []) if t]
    if not trusted:
        raise ValueError("no trusted branch pattern given")
    query = {"status": "success", "per_page": "50"}
    if len(trusted) == 1 and not any(c in trusted[0] for c in "*?["):
        query["branch"] = trusted[0]
    headers = {"Accept": "application/vnd.github+json"}
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def get(url):
        with opener(urllib.request.Request(url, headers=headers), timeout=30) as resp:
            return json.load(resp)

    data = get(f"{api}/repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}/runs?"
               f"{urllib.parse.urlencode(query)}")
    current = str(env.get("GITHUB_RUN_ID", ""))
    for run in data.get("workflow_runs") or []:
        if str(run.get("id")) == current or not _trusted_run(run, repo, trusted):
            continue
        if artifact:
            arts = get(f"{api}/repos/{repo}/actions/runs/{run['id']}/artifacts?"
                       f"{urllib.parse.urlencode({'name': artifact})}")
            if not any(a.get("name") == artifact and not a.get("expired")
                       for a in arts.get("artifacts") or []):
                continue
        return str(run["id"])
    return ""


def cmd_gh_previous_run(args, env=None):
    env = os.environ if env is None else env
    try:
        rid = previous_run_id(args.workflow, _split(args.trusted), env, artifact=args.artifact)
    except (OSError, ValueError, KeyError) as exc:
        print(f"gizmoduck: baseline run lookup failed ({exc}); the gate will treat the "
              f"baseline as missing", file=sys.stderr)
        rid = ""
    print(f"run_id={rid}")
    return 0


# --------------------------------------------------------------------------
# ServiceDesk Plus tickets - gizmoduck.py's confirm-then-open, driven by CI
# --------------------------------------------------------------------------

_DIGEST_RE = re.compile(r"--yes\s+([0-9a-f]{12})\s*$")


def ticket_records(findings_path, yes, run=subprocess.run):
    """Drive gizmoduck.py tickets exactly as an attended session does: preview
    first, read the digest it prints for THIS batch, and only with `yes` rerun
    with `--yes <digest>`. Returns (records, preview_text)."""
    argv = [sys.executable, GIZMODUCK_PY, "tickets", findings_path, "--min-severity", "high"]
    p = run(argv, capture_output=True, text=True, check=False)
    if p.returncode == 0:
        return json.loads(p.stdout or "[]"), p.stdout
    if p.returncode != 3 or "GIZMODUCK_CONFIRMATION_REQUIRED" not in (p.stdout or ""):
        raise RuntimeError(f"gizmoduck.py tickets exited {p.returncode}: {p.stderr or p.stdout}")
    digests = [m.group(1) for m in (_DIGEST_RE.search(ln) for ln in p.stdout.splitlines()) if m]
    if len(digests) != 1:
        raise RuntimeError("could not read exactly one digest from the tickets preview")
    if not yes:
        return None, p.stdout
    p2 = run(argv + ["--yes", digests[0]], capture_output=True, text=True, check=False)
    if p2.returncode != 0:
        raise RuntimeError(f"gizmoduck.py tickets --yes exited {p2.returncode}: {p2.stdout}")
    return json.loads(p2.stdout), p.stdout


class SdpClient:
    """Minimal ServiceDesk Plus v3 client: search for an open request carrying
    the `[Nuclei <template-id>]` tag, add a note if one exists, else create."""

    def __init__(self, base_url, api_key, auth_header="authtoken", opener=urllib.request.urlopen):
        self.base = base_url.rstrip("/")
        self.headers = {auth_header or "authtoken": api_key,
                        "Accept": "application/vnd.manageengine.sdp.v3+json"}
        self.opener = opener

    def _call(self, method, path, input_data):
        body = urllib.parse.urlencode({"input_data": json.dumps(input_data)})
        if method == "GET":
            req = urllib.request.Request(f"{self.base}{path}?{body}", headers=self.headers)
        else:
            headers = dict(self.headers, **{"Content-Type": "application/x-www-form-urlencoded"})
            req = urllib.request.Request(f"{self.base}{path}", data=body.encode("utf-8"),
                                         headers=headers, method=method)
        with self.opener(req, timeout=30) as resp:
            return json.load(resp)

    def open_or_note(self, record):
        tag = record["subject"].split("]", 1)[0] + "]"
        found = self._call("GET", "/api/v3/requests", {"list_info": {"row_count": 1, "search_criteria": [
            {"field": "subject", "condition": "contains", "value": tag},
            {"field": "status.name", "condition": "is not", "value": "Closed", "logical_operator": "AND"},
        ]}})
        existing = found.get("requests") or []
        if existing:
            rid = existing[0]["id"]
            self._call("POST", f"/api/v3/requests/{rid}/notes",
                       {"note": {"description": record["description"]}})
            return "noted", rid
        made = self._call("POST", "/api/v3/requests",
                          {"request": {"subject": record["subject"],
                                       "description": record["description"]}})
        return "created", (made.get("request") or {}).get("id")


def cmd_tickets(args, env=None, run=subprocess.run, client=None):
    env = os.environ if env is None else env
    if not _truthy(env.get("GIZMODUCK_SDP_TICKETS")):
        print("gizmoduck: GIZMODUCK_SDP_TICKETS is not 'true' - no tickets (default off)")
        return 0
    if not (env.get("SDP_BASE_URL") and env.get("SDP_API_KEY")):
        print("gizmoduck: SDP_BASE_URL / SDP_API_KEY secrets are not present - no tickets")
        return 0
    if not os.path.exists(args.findings) or os.path.getsize(args.findings) == 0:
        print("gizmoduck: no new Critical/High findings - nothing to ticket")
        return 0
    try:
        records, preview = ticket_records(args.findings, args.yes, run=run)
    except (RuntimeError, ValueError) as exc:
        print(f"gizmoduck: ticketing refused: {exc}", file=sys.stderr)
        return 2
    print(preview)
    if records is None:
        print("gizmoduck: preview only - rerun with --yes to open these tickets")
        return 3
    write_json(args.out, records)
    if client is None:
        client = SdpClient(env["SDP_BASE_URL"], env["SDP_API_KEY"], env.get("SDP_AUTH_HEADER") or "authtoken")
    rc = 0
    for rec in records:
        try:
            action, rid = client.open_or_note(rec)
            print(f"{action}: {rid} {rec['subject']}")
        except (OSError, ValueError, KeyError) as exc:
            print(f"failed: {rec['subject']}: {exc}", file=sys.stderr)
            rc = 2
    return rc


# --------------------------------------------------------------------------
# image-check - the runner image's build-time health check
# --------------------------------------------------------------------------

def cmd_image_check(_args=None, run=subprocess.run, adapters=None):
    """Fail (exit 1) unless `gizmoduck.py doctor` passes AND every scanner
    adapter reports itself runnable. doctor alone lets a missing scanner
    through by design (an interactive install may be partial); an image that
    is missing one would record it as skipped-missing on every run, so the
    image build fails instead."""
    p = run([sys.executable, GIZMODUCK_PY, "doctor"], capture_output=True, text=True, check=False)
    print(p.stdout or "", end="")
    problems = []
    if p.returncode != 0:
        problems.append(f"gizmoduck.py doctor exited {p.returncode}")
    if adapters is None:
        import scanners
        adapters = scanners.ADAPTERS
    for name in sorted(adapters):
        try:
            ok = bool(adapters[name].is_available())
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Any failure of the probe is the same answer: not runnable.
            ok = False
            problems.append(f"{name}: availability check raised {type(exc).__name__}: {exc}")
            continue
        if not ok:
            problems.append(f"{name}: not installed")
    for line in problems:
        print(f"GIZMODUCK_IMAGE_CHECK_FAILED: {line}", file=sys.stderr)
    return 1 if problems else 0


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

class RenderError(ValueError):
    pass


def build_config(args, version):
    enable = []
    for t in _split(args.enable):
        if t not in ci_render.OPT_IN_TOOLS:
            raise RenderError(f"--enable accepts only {', '.join(ci_render.OPT_IN_TOOLS)}; got {t!r}")
        if t not in enable:
            enable.append(t)
    if not (args.authorized_by or "").strip() or "\n" in args.authorized_by:
        raise RenderError("--authorized-by is required: one line naming who authorised scanning staging")
    for value in [args.authorized_by, *args.staging_url]:
        # GitHub evaluates ${{ }} anywhere in a workflow, env values included.
        if "${{" in value:
            raise RenderError(f"refusing a value containing a GitHub expression: {value!r}")
    try:
        policy = ci_guard.Policy.build(args.staging_url, args.production_url or (),
                                       allow_production=False,
                                       ip_allowed_urls=args.allow_ip_origin or ())
    except ci_guard.GuardError as exc:
        raise RenderError(f"[{exc.rule}] {exc.reason}") from exc
    for url in args.staging_url:
        origin, _ = ci_guard.normalise_origin(url)
        if origin in policy.production:
            raise RenderError(f"{url} is listed as both staging and production; refusing")
        d = ci_guard.check_target(url, policy)
        if not d.allowed:
            raise RenderError(f"staging URL {url} refused: [{d.rule}] {d.reason}")
    for value in (args.default_branch, args.staging_environment, args.gizmoduck_ref,
                  args.deploy_workflow or "x"):
        if not re.fullmatch(r"[A-Za-z0-9._/@+-]+( [A-Za-z0-9._/@+-]+)*", value or ""):
            raise RenderError(f"refusing unsafe name {value!r}")
    try:
        ci_render.check_image(args.image)
    except ValueError as exc:
        raise RenderError(str(exc)) from exc
    return {
        "version": version,
        "staging_urls": list(args.staging_url),
        "authorized_by": args.authorized_by.strip(),
        "enable": enable,
        "image": args.image,
        "gizmoduck_ref": args.gizmoduck_ref,
        "source_repo": ci_render.SOURCE_REPO,
        "default_branch": args.default_branch,
        "staging_environment": args.staging_environment,
        "deploy_workflow": args.deploy_workflow,
        "bitbucket_out": args.bitbucket_out,
    }


def cmd_render(args):
    version = plugin_version()
    if args.image is None:
        args.image = f"ghcr.io/mbadali25/gizmoduck-ci:{version}"
    try:
        cfg = build_config(args, version)
    except RenderError as exc:
        print(f"GIZMODUCK_CI_REFUSED: {exc}", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[0-9a-f]{40}", cfg["gizmoduck_ref"]):
        print(f"# warning: --gizmoduck-ref {cfg['gizmoduck_ref']!r} is not a commit SHA, so the "
              f"inline-bootstrap fallback runs whatever that ref points at when the pipeline "
              f"runs. The runner image tag is pinned; this path is not.", file=sys.stderr)
    platforms = ("github", "bitbucket") if args.platform == "both" else (args.platform,)
    files = ci_render.render_all(cfg, platforms)
    existing = [rel for rel in files if os.path.exists(os.path.join(args.repo, rel))]
    for rel, content in files.items():
        state = "exists - refused without --force" if rel in existing and not args.force else \
            ("exists - will overwrite (--force)" if rel in existing else "new")
        print(f"===== {rel} ({state}) =====")
        if not args.apply:
            print(content)
    for legacy in ci_render.LEGACY_FILES:
        if "github" in platforms and os.path.exists(os.path.join(args.repo, legacy)):
            print(f"# note: {legacy} is from gizmoduck before 0.7.0 and runs an untiered scan on every PR "
                  f"and push; delete it - {', '.join(ci_render.GITHUB_FILES)} replace it")
    if not os.path.exists(os.path.join(args.repo, ci_detect.CONFIG_NAME)):
        print(f"# note: no {ci_detect.CONFIG_NAME} in {args.repo} - the endpoint stage will fail UNVERIFIED "
              f"until endpoints are set up; {ci_detect.DETECT_HINT}")
    ledger = os.path.join(args.repo, ".crew", "endpoints.json")
    if os.path.exists(ledger):
        try:
            cands, skipped = ingest_endpoints(load_ledger(ledger), cfg["staging_urls"])
            print(f"# .crew/endpoints.json: {len(cands)} candidate endpoint(s), {len(skipped)} skipped; "
                  f"each is re-checked by the guard at runtime")
        except LedgerError as exc:
            print(f"# .crew/endpoints.json is unreadable ({exc}); the runtime guard will refuse the scan")
    if not args.apply:
        print("# dry run - nothing written. Re-run with --apply to write these files.")
        return 0
    if existing and not args.force:
        print(f"GIZMODUCK_CI_REFUSED: {', '.join(existing)} already exist(s); nothing written. "
              f"Pass --force to overwrite, or --bitbucket-out to write the Bitbucket file elsewhere.",
              file=sys.stderr)
        return 1
    write_files(files, args.repo)
    for rel in files:
        print(f"wrote {os.path.join(args.repo, rel)}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="gizmoduck CI pipelines", allow_abbrev=False)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("render", allow_abbrev=False)
    r.add_argument("--platform", choices=["github", "bitbucket", "both"], required=True)
    r.add_argument("--repo", default=".")
    r.add_argument("--staging-url", action="append", required=True)
    r.add_argument("--authorized-by", required=True)
    r.add_argument("--production-url", action="append")
    r.add_argument("--allow-ip-origin", action="append")
    r.add_argument("--enable", default="")
    r.add_argument("--image", default=None)
    r.add_argument("--gizmoduck-ref", default="main")
    r.add_argument("--default-branch", default="main")
    r.add_argument("--staging-environment", default="staging")
    r.add_argument("--deploy-workflow", default=None)
    r.add_argument("--bitbucket-out", default=None)
    r.add_argument("--apply", action="store_true")
    r.add_argument("--force", action="store_true")

    d = sub.add_parser("detect", allow_abbrev=False)
    d.add_argument("--repo", default=".")
    d.add_argument("--json", action="store_true")

    su = sub.add_parser("setup", allow_abbrev=False)
    su.add_argument("--repo", default=".")
    su.add_argument("--staging-url", default=None)
    su.add_argument("--auth", choices=ci_detect.AUTH_MODES, default=None)
    su.add_argument("--auth-header", default="Authorization")
    su.add_argument("--accept", choices=["high", "medium", "low"], default=None)
    su.add_argument("--scope", choices=["all"], default=None)
    su.add_argument("--include", action="append")
    su.add_argument("--exclude", action="append")
    su.add_argument("--openapi-path", default=None)
    su.add_argument("--apply", action="store_true")

    en = sub.add_parser("endpoints", allow_abbrev=False)
    en.add_argument("--repo", default=".")
    en.add_argument("--config", default=ci_detect.CONFIG_NAME)
    en.add_argument("--out", required=True)
    en.add_argument("--summary", default=None)
    en.add_argument("--no-live", action="store_true")

    pt = sub.add_parser("prepare-templates", allow_abbrev=False)
    pt.add_argument("--dir", required=True)
    pt.add_argument("--tier", default="")

    t = sub.add_parser("targets", allow_abbrev=False)
    t.add_argument("--endpoints", default=".crew/endpoints.json")
    t.add_argument("--run-endpoints", default=None)
    t.add_argument("--out", required=True)
    t.add_argument("--no-redirect-check", action="store_true")

    e = sub.add_parser("endpoint-stage", allow_abbrev=False)
    e.add_argument("--targets", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--no-redirect-check", action="store_true")

    c = sub.add_parser("code-stage", allow_abbrev=False)
    c.add_argument("--path", default=".")
    c.add_argument("--out", required=True)
    c.add_argument("--tier", choices=["light", "full", "sweep"], default=None)
    c.add_argument("--base-ref", default=None)

    pb = sub.add_parser("publish", allow_abbrev=False)
    pb.add_argument("--out", required=True)
    pb.add_argument("--baseline", default=None)
    pb.add_argument("--title", default="gizmoduck scan")

    g = sub.add_parser("gate", allow_abbrev=False)
    g.add_argument("--baseline", default=None)
    g.add_argument("--current", required=True)
    g.add_argument("--manifest", default=None)
    g.add_argument("--json-out", default=None)
    g.add_argument("--new-out", default=None)
    g.add_argument("--summary", default=None)
    g.add_argument("--block-at", choices=sorted(ci_gate.BLOCK_AT), default="high")

    s = sub.add_parser("sarif", allow_abbrev=False)
    s.add_argument("findings")
    s.add_argument("--out", required=True)
    s.add_argument("--srcroot", default="")

    b = sub.add_parser("bb-insights", allow_abbrev=False)
    b.add_argument("findings")
    b.add_argument("--gate", required=True)
    b.add_argument("--outdir", required=True)
    b.add_argument("--srcroot", default="")

    h = sub.add_parser("gh-previous-run", allow_abbrev=False)
    h.add_argument("--workflow", required=True)
    h.add_argument("--trusted", default="main",
                   help="space-separated branch patterns a baseline run may come from")
    h.add_argument("--artifact", default=None)

    k = sub.add_parser("tickets", allow_abbrev=False)
    k.add_argument("findings")
    k.add_argument("--out", required=True)
    k.add_argument("--yes", action="store_true",
                   help="CI's out-of-band approval: the GIZMODUCK_SDP_TICKETS repository "
                        "variable. Without it the preview is printed and nothing is opened.")
    sub.add_parser("image-check", allow_abbrev=False)
    return p


_COMMANDS = {
    "render": cmd_render, "detect": cmd_detect, "setup": cmd_setup, "endpoints": cmd_endpoints,
    "prepare-templates": cmd_prepare_templates,
    "targets": cmd_targets, "endpoint-stage": cmd_endpoint_stage,
    "code-stage": cmd_code_stage, "publish": cmd_publish, "gate": cmd_gate,
    "sarif": cmd_sarif, "bb-insights": cmd_bb_insights,
    "gh-previous-run": cmd_gh_previous_run, "tickets": cmd_tickets,
    "image-check": cmd_image_check,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

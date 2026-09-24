"""ci_render.py - the pipeline files `/gizmoduck:ci` writes into a target repo.

Pure text generation: nothing here reads the network or the filesystem, so the
golden-file tests pin the output byte for byte. gizmoduck_ci.py validates the
inputs (the prod-refusal guard runs there, before anything is rendered) and
does the writing.

Trigger tiers - which event runs what, and what it may block:

  Tier 1  light PR check     every non-draft PR (path-filtered) that tier 2
                             does not cover: Semgrep diff-aware on the changed
                             files, Trivy only if a lockfile/manifest changed,
                             Checkov only if a *.tf changed, gitleaks over the
                             PR's commits. Blocks on a NEW Critical only.
  Tier 2  targeted full      GitHub: PRs into the default branch or release/*,
                             or carrying the `security-scan` label. Bitbucket:
                             the manual `custom: security-full` pipeline. All
                             code scans, plus the endpoint scans after the
                             staging deploy. Blocks on a new Critical/High.
                             No branch-name or path triggers.
  Tier 3  weekly sweep       GitHub `schedule`, Sunday 23:00 UTC; Bitbucket a
                             scheduled `custom: security-weekly` (set up once
                             in the UI). Everything, Dependency-Check with NVD
                             included, against the default branch and staging,
                             plus the weekly Nuclei template update. Never
                             blocks: saves results as the next baseline, diffs
                             against the last one, optionally tickets.
  Manual                     `workflow_dispatch` (any ref; any URL the guard
                             allows) / the Bitbucket custom pipelines. Blocks
                             per the tier-2 rule.

Endpoint scans never run on a pull_request event. Draft PRs are skipped; every
workflow has a `concurrency` group per event and ref with cancel-in-progress;
the Trivy DB, NVD data and Nuclei templates are cached.

Action pinning: every third-party action is pinned to a full commit SHA with
the release it came from in a trailing comment. A tag - even a major tag like
`@v4` - is a mutable pointer that the action's owner (or anyone who takes over
the account) can move, and a security-scan workflow holds `security-events:
write` and reads repository secrets. A SHA cannot be moved. The cost is that
updates are manual; Dependabot's `github-actions` ecosystem updates SHA pins
and keeps the comment in step.
"""
import json
import shlex

ACTIONS = {
    "checkout": ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "upload-artifact": ("actions/upload-artifact", "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "v7.0.1"),
    "download-artifact": ("actions/download-artifact", "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c", "v8.0.1"),
    "upload-sarif": ("github/codeql-action/upload-sarif", "1c5b675653bb5c22dbe9b12b556ec555138e09fd", "v4.38.1"),
    "cache": ("actions/cache", "5a3ec84eff668545956fd18022155c47e93e2684", "v4.2.3"),
}

SOURCE_REPO = "https://github.com/mbadali25/useful-claude-add-ons"
OPT_IN_TOOLS = ("nikto", "nmap", "sqlmap")
CODE_OUT = "/tmp/gizmoduck-out/code"
ENDPOINT_OUT = "/tmp/gizmoduck-out/endpoints"
CACHE_ROOT = "/tmp/gizmoduck-cache"
CLI = 'python3 "$GIZMODUCK_HOME/scripts/gizmoduck_ci.py"'

TIER2_LABEL = "security-scan"
WEEKLY_CRON = "0 23 * * 0"
DOCS_ONLY = ("**/*.md", "docs/**", "**/*.png", "**/*.jpg", "**/*.gif")
PR_FILE = ".github/workflows/gizmoduck-pr.yml"
FULL_FILE = ".github/workflows/gizmoduck-full.yml"
ENDPOINTS_FILE = ".github/workflows/gizmoduck-endpoints.yml"
GITHUB_FILES = (PR_FILE, FULL_FILE, ENDPOINTS_FILE)
LEGACY_FILES = (".github/workflows/gizmoduck-code.yml",)
BB_FULL = "security-full"
BB_WEEKLY = "security-weekly"


def _publish_cmd(stage, title):
    return (f'{CLI} publish --out "$GIZMODUCK_OUT" '
            f'--baseline /tmp/gizmoduck-baseline/{stage}/findings.jsonl --title {shlex.quote(title)}')


def _gate_cmd(stage):
    return (f'{CLI} gate --baseline /tmp/gizmoduck-baseline/{stage}/findings.jsonl '
            '--current "$GIZMODUCK_OUT/findings.jsonl" --manifest "$GIZMODUCK_OUT/run-manifest.json" '
            '--block-at "$GIZMODUCK_BLOCK_AT" '
            '--json-out "$GIZMODUCK_OUT/gate.json" --new-out "$GIZMODUCK_OUT/new-blocking.jsonl"')


_TICKETS_CMD = (f'{CLI} tickets "$GIZMODUCK_OUT/new-blocking.jsonl" '
                '--out "$GIZMODUCK_OUT/tickets.json" --yes')
_TICKETS_IF = ("always() && (steps.gate.outcome == 'success' || steps.gate.outcome == 'failure') && "
               "github.event_name != 'pull_request' && vars.GIZMODUCK_SDP_TICKETS == 'true'")
_INLINE_NOTICE = ('echo "gizmoduck: runner image not in use - inline bootstrap from '
                  '$GIZMODUCK_SOURCE_REPO@$GIZMODUCK_REF (slow; build the image to skip this)"')


def uses(key):
    repo, sha, tag = ACTIONS[key]
    return f"uses: {repo}@{sha} # {tag}"


def _indent(text, n):
    pad = " " * n
    return "\n".join((pad + line) if line.strip() else "" for line in text.splitlines())


def _yq(value):
    """A YAML double-quoted scalar. JSON string syntax is a subset of YAML's."""
    return json.dumps(value, ensure_ascii=True)


def _sq(value):
    """A GitHub expression string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _opt_in_label(cfg):
    return "".join(f", {t}" for t in cfg["enable"])


BOOTSTRAP_SH = """\
GIZMODUCK_HOME="${GIZMODUCK_HOME:-/opt/gizmoduck}"
if [ -f "$GIZMODUCK_HOME/scripts/gizmoduck_ci.py" ]; then
  echo "gizmoduck: toolchain present at $GIZMODUCK_HOME (runner image)"
else
  @@NOTICE@@
  SUDO=""
  if [ "$(id -u)" -ne 0 ]; then SUDO=sudo; fi
  if ! command -v sudo >/dev/null 2>&1; then apt-get update -y && apt-get install -y sudo; fi
  $SUDO apt-get update -y
  $SUDO apt-get install -y ca-certificates curl git unzip python3 python3-pip python3-yaml
  src="$(mktemp -d)"
  git -C "$src" init -q
  git -C "$src" fetch -q --depth 1 "$GIZMODUCK_SOURCE_REPO" "$GIZMODUCK_REF"
  git -C "$src" checkout -q FETCH_HEAD
  $SUDO rm -rf "$GIZMODUCK_HOME"
  $SUDO cp -r "$src/plugin/gizmoduck" "$GIZMODUCK_HOME"
  PIP_BREAK_SYSTEM_PACKAGES=1 bash "$GIZMODUCK_HOME/bootstrap.sh"
fi""".replace("@@NOTICE@@", _INLINE_NOTICE)


# --------------------------------------------------------------------------
# GitHub Actions
# --------------------------------------------------------------------------

def _tier2_pr(cfg):
    return (f"(github.base_ref == {_sq(cfg['default_branch'])} || startsWith(github.base_ref, 'release/') || "
            f"contains(github.event.pull_request.labels.*.name, {_sq(TIER2_LABEL)}))")


_NOT_DRAFT = "github.event.pull_request.draft == false"
_LABEL_EVENT_OK = f"(github.event.action != 'labeled' || github.event.label.name == {_sq(TIER2_LABEL)})"
_IS_SWEEP = "github.event_name == 'schedule'"


def _gh_header(title, cfg):
    return (f"# Rendered by /gizmoduck:ci (gizmoduck {cfg['version']}) - {title}.\n"
            f"# Re-render with gizmoduck_ci.py rather than hand-editing; the prod-refusal\n"
            f"# guard's staging origins are baked in below and re-checked at runtime.\n"
            f"# Actions are pinned by full commit SHA; the trailing comment names the release.\n"
            f"# Tiers: gizmoduck-pr.yml (1, light PR check), gizmoduck-full.yml (2 + weekly\n"
            f"# code sweep + manual), gizmoduck-endpoints.yml (2 after the staging deploy +\n"
            f"# weekly endpoint sweep + manual). Endpoint scans never run on a pull request.\n")


def _gh_env(cfg, out, tier, block_at, extra=()):
    return "\n".join([
        "env:",
        "  GIZMODUCK_HOME: /opt/gizmoduck",
        f"  GIZMODUCK_OUT: {out}",
        f"  GIZMODUCK_TIER: {tier}",
        f"  GIZMODUCK_BLOCK_AT: {block_at}",
        f"  GIZMODUCK_AUTHORIZED_BY: {_yq(cfg['authorized_by'])}",
        f"  GIZMODUCK_DEFAULT_BRANCH: {_yq(cfg['default_branch'])}",
        f"  GIZMODUCK_SOURCE_REPO: {_yq(cfg['source_repo'])}",
        f"  GIZMODUCK_REF: {_yq(cfg['gizmoduck_ref'])}",
        f"  GIZMODUCK_STAGING_URLS: {_yq(' '.join(cfg['staging_urls']))}",
        f"  GIZMODUCK_ENABLE: {_yq(','.join(cfg['enable']))}",
        *[f"  {k}: {v}" for k, v in extra],
    ])


def _gh_checkout(fetch_depth=None, ref_input=False):
    lines = ["- name: Check out", f"  {uses('checkout')}", "  with:", "    persist-credentials: false"]
    if fetch_depth is not None:
        lines.append(f"    fetch-depth: {fetch_depth}")
    if ref_input:
        lines.append("    ref: ${{ inputs.ref }}")
    return "\n".join(lines)


def _gh_bootstrap_step():
    body = BOOTSTRAP_SH + '\nif [ -n "${GITHUB_PATH:-}" ]; then echo "$HOME/.local/bin" >> "$GITHUB_PATH"; fi'
    return ("- name: Ensure the gizmoduck toolchain\n"
            "  run: |\n" + _indent(body, 4))


_CACHES = {
    "trivy": ("the Trivy vulnerability DB", f"{CACHE_ROOT}/trivy"),
    "nvd": ("Dependency-Check's NVD data", f"{CACHE_ROOT}/nvd"),
    "nuclei": ("the Nuclei templates", f"{CACHE_ROOT}/nuclei-templates"),
}


def _gh_caches(names, conditions=None):
    """One week-stamped key per cache: every run restores the newest copy
    (restore-keys), and the first run of each ISO week saves a fresh one - so
    the weekly sweep's refreshed data reaches the next week's PR checks."""
    conditions = conditions or {}
    out = ["- name: Cache key (ISO week)\n  id: week\n  run: echo \"key=$(date -u +%G-%V)\" >> \"$GITHUB_OUTPUT\""]
    for name in names:
        label, path = _CACHES[name]
        cond = f"\n  if: {conditions[name]}" if name in conditions else ""
        out.append(f"""\
- name: Cache {label}{cond}
  {uses('cache')}
  with:
    path: {path}
    key: gizmoduck-{name}-${{{{ steps.week.outputs.key }}}}
    restore-keys: gizmoduck-{name}-""")
    return "\n".join(out)


def _gh_baseline(stage, workflow_file, branch_filter):
    branch_arg = ' --branch "$GIZMODUCK_DEFAULT_BRANCH"' if branch_filter else ""
    return f"""\
- name: Find the baseline run
  id: prev
  env:
    GH_TOKEN: ${{{{ github.token }}}}
  run: {CLI} gh-previous-run --workflow {workflow_file}{branch_arg} >> "$GITHUB_OUTPUT"
- name: Download the baseline
  if: steps.prev.outputs.run_id != ''
  continue-on-error: true
  {uses('download-artifact')}
  with:
    name: gizmoduck-{stage}
    path: /tmp/gizmoduck-baseline/{stage}
    github-token: ${{{{ github.token }}}}
    run-id: ${{{{ steps.prev.outputs.run_id }}}}"""


def _guard_env(target_url=False, auth=False):
    lines = ["env:",
             "  GIZMODUCK_ALLOWED_PROD_ORIGINS: ${{ vars.GIZMODUCK_ALLOWED_PROD_ORIGINS }}",
             "  GIZMODUCK_ALLOW_PROD_SCAN: ${{ vars.GIZMODUCK_ALLOW_PROD_SCAN }}",
             "  GIZMODUCK_ALLOWED_IP_ORIGINS: ${{ vars.GIZMODUCK_ALLOWED_IP_ORIGINS }}"]
    if target_url:
        lines.append("  GIZMODUCK_TARGET_URL: ${{ inputs.url }}")
    if auth:
        lines.append("  GIZMODUCK_AUTH_HEADER_VALUE: ${{ secrets.GIZMODUCK_AUTH_HEADER_VALUE }}")
    return "\n".join(lines)


_GATE_ENV = """\
env:
  GIZMODUCK_ALLOW_NO_BASELINE: ${{ vars.GIZMODUCK_ALLOW_NO_BASELINE }}
  GIZMODUCK_ALLOW_INCOMPLETE: ${{ vars.GIZMODUCK_ALLOW_INCOMPLETE }}
  GIZMODUCK_TRUST_ASSIGNED_SEVERITY: ${{ vars.GIZMODUCK_TRUST_ASSIGNED_SEVERITY }}"""

_TICKETS_ENV = """\
env:
  GIZMODUCK_SDP_TICKETS: ${{ vars.GIZMODUCK_SDP_TICKETS }}
  SDP_BASE_URL: ${{ secrets.SDP_BASE_URL }}
  SDP_API_KEY: ${{ secrets.SDP_API_KEY }}
  SDP_AUTH_HEADER: ${{ vars.SDP_AUTH_HEADER }}"""


def _gh_sarif():
    return f"""\
- name: SARIF
  id: sarif
  if: always() && steps.scan.outcome == 'success'
  run: {CLI} sarif "$GIZMODUCK_OUT/findings.jsonl" --out "$GIZMODUCK_OUT/gizmoduck.sarif" --srcroot "$GITHUB_WORKSPACE"
- name: Upload SARIF to code scanning
  if: always() && steps.sarif.outcome == 'success'
  continue-on-error: ${{{{ github.event.pull_request.head.repo.fork == true }}}}
  {uses('upload-sarif')}
  with:
    sarif_file: {CODE_OUT}/gizmoduck.sarif
    category: gizmoduck-code"""


def _gh_tail(stage, title, tickets):
    out = f"""\
- name: Reports (JSONL, Markdown, HTML, PDF) and diff
  if: always() && steps.scan.outcome == 'success'
  run: {_publish_cmd(stage, title)}
- name: Gate (blocks at $GIZMODUCK_BLOCK_AT)
  id: gate
  if: always() && steps.scan.outcome == 'success'
{_indent(_GATE_ENV, 2)}
  run: {_gate_cmd(stage)} --summary "$GITHUB_STEP_SUMMARY"
- name: Upload results
  if: always()
  {uses('upload-artifact')}
  with:
    name: gizmoduck-{stage}
    path: {CODE_OUT if stage == 'code' else ENDPOINT_OUT}
    retention-days: 90
    if-no-files-found: warn"""
    if tickets:
        out += f"""
- name: ServiceDesk Plus tickets for new Critical/High (opt-in)
  if: {_TICKETS_IF}
{_indent(_TICKETS_ENV, 2)}
  run: {_TICKETS_CMD}"""
    return out


def _gh_jobs(steps, label, condition, permissions):
    perm = "\n".join(f"      {k}: {v}" for k, v in permissions)
    image_job = f"""\
  scan:
    name: {label} (runner image)
    if: {condition.format(runner="vars.GIZMODUCK_RUNNER != 'bootstrap'")}
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    container:
      image: @@IMAGE@@
    permissions:
{perm}
    steps:
{_indent(steps, 6)}"""
    boot_job = f"""\
  scan-bootstrap:
    name: {label} (inline bootstrap fallback)
    if: {condition.format(runner="vars.GIZMODUCK_RUNNER == 'bootstrap'")}
    runs-on: ubuntu-24.04
    timeout-minutes: 180
    permissions:
{perm}
    steps:
{_indent(steps, 6)}"""
    return "jobs:\n" + image_job + "\n\n" + boot_job + "\n"


def _gh_file(title, name, triggers, group, env, jobs, cfg):
    text = "\n".join([
        _gh_header(title, cfg),
        f"name: {name}",
        "",
        "on:",
        *triggers,
        "",
        "permissions:",
        "  contents: read",
        "",
        "concurrency:",
        f"  group: {group}",
        "  cancel-in-progress: true",
        "",
        "defaults:",
        "  run:",
        "    shell: bash",
        "",
        env,
        "",
        jobs,
    ])
    return text.replace("@@IMAGE@@", cfg["image"])


_CODE_PERMS = [("contents", "read"), ("actions", "read"), ("security-events", "write")]


def github_pr(cfg):
    """Tier 1. Every non-draft PR that tier 2 does not cover, docs-only
    changes excluded by path; blocks on a new Critical only."""
    steps = "\n".join([
        _gh_checkout(fetch_depth=0),
        _gh_bootstrap_step(),
        _gh_caches(["trivy"]),
        _gh_baseline("code", "gizmoduck-full.yml", branch_filter=True),
        f"""\
- name: Scan (Semgrep diff-aware, Trivy if a manifest changed, Checkov if *.tf changed, gitleaks)
  id: scan
  env:
    GIZMODUCK_BASE_SHA: ${{{{ github.event.pull_request.base.sha }}}}
  run: |
    git config --global --add safe.directory "$GITHUB_WORKSPACE"
    {CLI} code-stage --tier light --base-ref "$GIZMODUCK_BASE_SHA" \\
      --path "$GITHUB_WORKSPACE" --out "$GIZMODUCK_OUT\"""",
        _gh_sarif(),
        _gh_tail("code", "gizmoduck PR check", tickets=False),
    ])
    condition = ("{runner} && github.event_name == 'pull_request' && " + _NOT_DRAFT +
                 " && !" + _tier2_pr(cfg))
    triggers = ["  pull_request:",
                "    types: [opened, synchronize, reopened, ready_for_review]",
                "    paths-ignore:",
                *[f"      - {_yq(p)}" for p in DOCS_ONLY]]
    env = _gh_env(cfg, CODE_OUT, "light", "critical", [("TRIVY_CACHE_DIR", _CACHES["trivy"][1])])
    return _gh_file("tier 1, light PR check (blocks on a new Critical only)", "gizmoduck PR check", triggers,
                    "gizmoduck-pr-${{ github.event.pull_request.number || github.ref }}", env,
                    _gh_jobs(steps, "gizmoduck PR check", condition, _CODE_PERMS), cfg)


def github_full(cfg):
    """Tier 2 code scans (PRs into the default branch or release/*, or the
    security-scan label), the tier-3 weekly code sweep (schedule), and a
    manual full scan of any ref (workflow_dispatch)."""
    steps = "\n".join([
        _gh_checkout(ref_input=True),
        _gh_bootstrap_step(),
        _gh_caches(["trivy", "nvd"], {"nvd": _IS_SWEEP}),
        _gh_baseline("code", "gizmoduck-full.yml", branch_filter=True),
        f"""\
- name: Scan (Semgrep, Trivy fs, Checkov, gitleaks; Dependency-Check on the weekly sweep)
  id: scan
  env:
    NVD_API_KEY: ${{{{ secrets.NVD_API_KEY }}}}
  run: {CLI} code-stage --tier "$GIZMODUCK_TIER" --path "$GITHUB_WORKSPACE" --out "$GIZMODUCK_OUT\"""",
        _gh_sarif(),
        _gh_tail("code", "gizmoduck full code scan", tickets=True),
    ])
    condition = ("{runner} && ((github.event_name == 'pull_request' && " + _NOT_DRAFT + " && " +
                 _tier2_pr(cfg) + " && " + _LABEL_EVENT_OK + ") || " + _IS_SWEEP +
                 " || github.event_name == 'workflow_dispatch')")
    triggers = ["  pull_request:",
                "    types: [opened, synchronize, reopened, ready_for_review, labeled]",
                "  schedule:",
                f"    - cron: {_yq(WEEKLY_CRON)}",
                "  workflow_dispatch:",
                "    inputs:",
                "      ref:",
                "        description: Branch, tag or SHA to scan (blank = the branch picked above)",
                "        required: false",
                "        default: ''",
                "        type: string"]
    env = _gh_env(cfg, CODE_OUT, f"${{{{ {_IS_SWEEP} && 'sweep' || 'full' }}}}",
                  f"${{{{ {_IS_SWEEP} && 'never' || 'high' }}}}",
                  [("TRIVY_CACHE_DIR", _CACHES["trivy"][1]), ("GIZMODUCK_DEPCHECK_DATA", _CACHES["nvd"][1])])
    return _gh_file("tier 2 full code scan, tier 3 weekly code sweep, manual scans", "gizmoduck full code scan",
                    triggers,
                    "gizmoduck-full-${{ github.event_name }}-${{ github.event.pull_request.number || github.ref }}",
                    env, _gh_jobs(steps, "gizmoduck full code scan", condition, _CODE_PERMS), cfg)


def github_endpoints(cfg):
    """Tier 2 endpoint scans after the staging deploy, the tier-3 weekly
    endpoint sweep, and a manual scan of any guard-allowed URL. Never on a
    pull_request."""
    env_name = cfg["staging_environment"]
    triggers = ["  deployment_status:"]
    conds = ["github.event_name == 'workflow_dispatch'", _IS_SWEEP,
             ("(github.event_name == 'deployment_status' && "
              "github.event.deployment_status.state == 'success' && "
              f"github.event.deployment.environment == {_sq(env_name)})")]
    if cfg.get("deploy_workflow"):
        triggers += ["  workflow_run:",
                     f"    workflows: [{_yq(cfg['deploy_workflow'])}]",
                     "    types: [completed]"]
        conds.append("(github.event_name == 'workflow_run' && "
                     "github.event.workflow_run.conclusion == 'success')")
    triggers += ["  schedule:",
                 f"    - cron: {_yq(WEEKLY_CRON)}",
                 "  workflow_dispatch:",
                 "    inputs:",
                 "      url:",
                 "        description: Base URL to scan (blank = the configured staging URL; the prod-refusal "
                 "guard still applies)",
                 "        required: false",
                 "        default: ''",
                 "        type: string"]
    condition = "{runner} && (" + " || ".join(conds) + ")"
    steps = "\n".join([
        _gh_checkout(),
        _gh_bootstrap_step(),
        _gh_caches(["nuclei"]),
        f"""\
- name: Nuclei templates (seeded from the runner; updated by the weekly sweep)
  run: {CLI} prepare-templates --dir "$GIZMODUCK_NUCLEI_TEMPLATES" --tier "$GIZMODUCK_TIER"
- name: Endpoints (committed list + re-detect; none is UNVERIFIED and fails)
{_indent(_guard_env(target_url=True), 2)}
  run: |
    mkdir -p "$GIZMODUCK_OUT"
    {CLI} endpoints --config "$GITHUB_WORKSPACE/gizmoduck-ci.json" --repo "$GITHUB_WORKSPACE" \\
      --out "$GIZMODUCK_OUT" --summary "$GITHUB_STEP_SUMMARY"
- name: Prod-refusal guard (runs before any endpoint scan)
{_indent(_guard_env(target_url=True), 2)}
  run: {CLI} targets --run-endpoints "$GIZMODUCK_OUT/endpoints-run.json" --out "$GIZMODUCK_OUT/targets.json\"""",
        _gh_baseline("endpoints", "gizmoduck-endpoints.yml", branch_filter=False),
        f"""\
- name: Scan staging (Nuclei, ZAP baseline, testssl{_opt_in_label(cfg)})
  id: scan
{_indent(_guard_env(target_url=True, auth=True), 2)}
  run: {CLI} endpoint-stage --targets "$GIZMODUCK_OUT/targets.json" --out "$GIZMODUCK_OUT\"""",
        _gh_tail("endpoints", "gizmoduck staging endpoint scan", tickets=True),
    ])
    env = _gh_env(cfg, ENDPOINT_OUT, f"${{{{ {_IS_SWEEP} && 'sweep' || 'full' }}}}",
                  f"${{{{ {_IS_SWEEP} && 'never' || 'high' }}}}",
                  [("GIZMODUCK_NUCLEI_TEMPLATES", _CACHES["nuclei"][1])])
    return _gh_file("endpoint stage (Nuclei, ZAP baseline, testssl against staging)",
                    "gizmoduck staging endpoint scan", triggers,
                    "gizmoduck-endpoints-${{ github.event_name }}-${{ github.ref }}", env,
                    _gh_jobs(steps, "gizmoduck staging endpoint scan", condition,
                             [("contents", "read"), ("actions", "read")]), cfg)


# --------------------------------------------------------------------------
# Bitbucket Pipelines
# --------------------------------------------------------------------------

def _bb_exports(cfg, out, tier, block_at):
    pairs = [
        ("GIZMODUCK_OUT", out),
        ("GIZMODUCK_TIER", tier),
        ("GIZMODUCK_BLOCK_AT", block_at),
        ("GIZMODUCK_AUTHORIZED_BY", cfg["authorized_by"]),
        ("GIZMODUCK_DEFAULT_BRANCH", cfg["default_branch"]),
        ("GIZMODUCK_SOURCE_REPO", cfg["source_repo"]),
        ("GIZMODUCK_REF", cfg["gizmoduck_ref"]),
        ("GIZMODUCK_STAGING_URLS", " ".join(cfg["staging_urls"])),
        ("GIZMODUCK_ENABLE", ",".join(cfg["enable"])),
        ("TRIVY_CACHE_DIR", _CACHES["trivy"][1]),
        ("GIZMODUCK_DEPCHECK_DATA", _CACHES["nvd"][1]),
        ("GIZMODUCK_NUCLEI_TEMPLATES", _CACHES["nuclei"][1]),
    ]
    lines = ['export GIZMODUCK_HOME="${GIZMODUCK_HOME:-/opt/gizmoduck}"']
    lines += [f"export {k}={shlex.quote(v)}" for k, v in pairs]
    lines.append('export PATH="$HOME/.local/bin:$PATH"')
    return "\n".join(lines)


def _bb_item(text):
    return "- |\n" + _indent(text, 2)


def _bb_baseline_download(stage):
    return f"""\
mkdir -p /tmp/gizmoduck-baseline/{stage} "$GIZMODUCK_OUT"
if [ -n "${{GIZMODUCK_BB_TOKEN:-}}" ]; then
  curl -fsSL -H "Authorization: Bearer $GIZMODUCK_BB_TOKEN" -o /tmp/gizmoduck-baseline/{stage}/findings.jsonl \
"https://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/downloads/gizmoduck-{stage}-baseline.jsonl" \
|| {{ rm -f /tmp/gizmoduck-baseline/{stage}/findings.jsonl; echo "gizmoduck: no {stage} baseline in Downloads yet"; }}
else
  echo "gizmoduck: GIZMODUCK_BB_TOKEN is not set - no baseline can be read or saved"
fi"""


_BB_DRAFT_SKIP = """\
# Tier 1 skips draft PRs. Bitbucket passes no draft flag to a pipeline, so it
# is read from the pull request itself - which needs GIZMODUCK_BB_TOKEN.
if [ -n "${GIZMODUCK_BB_TOKEN:-}" ] && [ -n "${BITBUCKET_PR_ID:-}" ]; then
  draft="$(curl -fsS -H "Authorization: Bearer $GIZMODUCK_BB_TOKEN" \
"https://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/pullrequests/$BITBUCKET_PR_ID" \
| python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("draft", False)).lower())' || echo unknown)"
  if [ "$draft" = "true" ]; then
    echo "gizmoduck: draft pull request - tier 1 is skipped until it is marked ready for review"
    exit 0
  fi
else
  echo "gizmoduck: GIZMODUCK_BB_TOKEN is not set - cannot tell a draft PR apart, so this runs regardless"
fi"""


def _bb_tail(stage, title, insights):
    parts = [
        _publish_cmd(stage, title),
        f"gate_rc=0\n{_gate_cmd(stage)} || gate_rc=$?",
    ]
    if insights:
        parts.append(f"""\
{CLI} bb-insights "$GIZMODUCK_OUT/findings.jsonl" --gate "$GIZMODUCK_OUT/gate.json" \
--outdir "$GIZMODUCK_OUT/insights" --srcroot "$BITBUCKET_CLONE_DIR" || true
rep="http://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/commit/$BITBUCKET_COMMIT\
/reports/gizmoduck-{stage}"
if [ -f "$GIZMODUCK_OUT/insights/report.json" ]; then
  curl -fsS --proxy http://localhost:29418 -X PUT "$rep" -H "Content-Type: application/json" \
--data-binary @"$GIZMODUCK_OUT/insights/report.json" || echo "gizmoduck: Code Insights report upload failed"
  for f in "$GIZMODUCK_OUT"/insights/annotations-*.json; do
    [ -f "$f" ] || continue
    curl -fsS --proxy http://localhost:29418 -X POST "$rep/annotations" -H "Content-Type: application/json" \
--data-binary @"$f" || echo "gizmoduck: annotation upload failed for $f"
  done
fi""")
    parts.append(f"""\
# The next baseline: the weekly sweep's results (it never blocks), or a clean
# tier-2 run - both only on the default branch, never from a pull request.
if {{ [ "$GIZMODUCK_TIER" = "sweep" ] || [ "$gate_rc" -eq 0 ]; }} \
&& [ "${{BITBUCKET_BRANCH:-}}" = "$GIZMODUCK_DEFAULT_BRANCH" ] \
&& [ -z "${{BITBUCKET_PR_ID:-}}" ] && [ -n "${{GIZMODUCK_BB_TOKEN:-}}" ]; then
  curl -fsS -X POST -H "Authorization: Bearer $GIZMODUCK_BB_TOKEN" \
-F "files=@$GIZMODUCK_OUT/findings.jsonl;filename=gizmoduck-{stage}-baseline.jsonl" \
"https://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/downloads" \
|| echo "gizmoduck: baseline upload failed - the next run compares against the previous baseline"
fi""")
    parts.append(f"""\
if [ -z "${{BITBUCKET_PR_ID:-}}" ] && [ "${{GIZMODUCK_SDP_TICKETS:-}}" = "true" ] \
&& [ -s "$GIZMODUCK_OUT/new-blocking.jsonl" ]; then
  {_TICKETS_CMD} || echo "gizmoduck: ticketing failed"
fi""")
    parts.append(f"""\
mkdir -p "$BITBUCKET_CLONE_DIR/gizmoduck-out"
cp -r "$GIZMODUCK_OUT" "$BITBUCKET_CLONE_DIR/gizmoduck-out/{stage}"
exit "$gate_rc\"""")
    return parts


def _bb_step(anchor, name, script_items, caches, max_time=120, pr_check=False):
    items = "\n".join(_bb_item(s) for s in script_items)
    extra = ""
    if pr_check:
        paths = "\n".join(f"              - {_yq(p)}" for p in DOCS_ONLY)
        extra = ("        clone:\n          depth: full\n"
                 "        condition:\n          changesets:\n            excludePaths:\n" + paths + "\n")
    cache_lines = "\n".join(f"          - gizmoduck-{c}" for c in caches)
    return f"""\
    - step: &{anchor}
        name: {_yq(name)}
        size: 2x
        max-time: {max_time}
{extra}        caches:
{cache_lines}
        script:
{_indent(items, 10)}
        artifacts:
          - gizmoduck-out/**"""


def _bb_code_items(cfg, tier, block_at, stage_cmd, title, pr_check=False):
    items = [_bb_exports(cfg, CODE_OUT, tier, block_at)]
    if pr_check:
        items.append(_BB_DRAFT_SKIP)
    items += [BOOTSTRAP_SH, _bb_baseline_download("code"), stage_cmd,
              *_bb_tail("code", title, insights=True)]
    return items


def _bb_endpoint_items(cfg, tier, block_at):
    return [
        _bb_exports(cfg, ENDPOINT_OUT, tier, block_at),
        BOOTSTRAP_SH,
        f'{CLI} prepare-templates --dir "$GIZMODUCK_NUCLEI_TEMPLATES" --tier "$GIZMODUCK_TIER"',
        ("# Endpoints: the committed list merged with a cheap re-detect. None at all\n"
         "# is UNVERIFIED and fails here - an empty scan never passes.\n"
         f'mkdir -p "$GIZMODUCK_OUT"\n{CLI} endpoints --config "$BITBUCKET_CLONE_DIR/gizmoduck-ci.json" '
         '--repo "$BITBUCKET_CLONE_DIR" --out "$GIZMODUCK_OUT"'),
        ("# Prod-refusal guard: runs before any endpoint scan and fails the step on a refused target.\n"
         f'{CLI} targets --run-endpoints "$GIZMODUCK_OUT/endpoints-run.json" '
         '--out "$GIZMODUCK_OUT/targets.json"'),
        _bb_baseline_download("endpoints"),
        f'{CLI} endpoint-stage --targets "$GIZMODUCK_OUT/targets.json" --out "$GIZMODUCK_OUT"',
        *_bb_tail("endpoints", "gizmoduck staging endpoint scan", insights=False),
    ]


def bitbucket(cfg):
    code_light = (
        "# Diff-aware: everything is measured from the merge base with the PR's destination.\n"
        'git fetch -q origin "$BITBUCKET_PR_DESTINATION_BRANCH"\n'
        'GIZMODUCK_BASE_SHA="$(git merge-base HEAD FETCH_HEAD)"\n'
        f'{CLI} code-stage --tier light --base-ref "$GIZMODUCK_BASE_SHA" --path "$BITBUCKET_CLONE_DIR" '
        '--out "$GIZMODUCK_OUT"')
    code_tiered = f'{CLI} code-stage --tier "$GIZMODUCK_TIER" --path "$BITBUCKET_CLONE_DIR" --out "$GIZMODUCK_OUT"'
    ep = f"Nuclei, ZAP baseline, testssl{_opt_in_label(cfg)}"
    steps = "\n".join([
        _bb_step("gizmoduck-pr-check", "gizmoduck tier 1: light PR check (blocks on a new Critical)",
                 _bb_code_items(cfg, "light", "critical", code_light, "gizmoduck PR check", pr_check=True),
                 ["trivy"], max_time=30, pr_check=True),
        _bb_step("gizmoduck-full-code", "gizmoduck tier 2: full code scan (Semgrep, Trivy, Checkov, gitleaks)",
                 _bb_code_items(cfg, "full", "high", code_tiered, "gizmoduck full code scan"), ["trivy"]),
        _bb_step("gizmoduck-endpoint-scan", f"gizmoduck tier 2: staging endpoint scan ({ep})",
                 _bb_endpoint_items(cfg, "full", "high"), ["nuclei"]),
        _bb_step("gizmoduck-sweep-code", "gizmoduck tier 3: weekly code sweep incl. Dependency-Check (never blocks)",
                 _bb_code_items(cfg, "sweep", "never", code_tiered, "gizmoduck weekly code sweep"),
                 ["trivy", "nvd"], max_time=240),
        _bb_step("gizmoduck-sweep-endpoints", f"gizmoduck tier 3: weekly endpoint sweep ({ep}; never blocks)",
                 _bb_endpoint_items(cfg, "sweep", "never"), ["nuclei"], max_time=240),
    ])
    caches = "\n".join(f"    gizmoduck-{k}: {v[1]}" for k, v in _CACHES.items())
    default = cfg["default_branch"]
    return f"""\
# Rendered by /gizmoduck:ci (gizmoduck {cfg['version']}).
# Re-render with gizmoduck_ci.py rather than hand-editing; the prod-refusal
# guard's staging origins are baked in below and re-checked at runtime.
#
# Trigger tiers:
#   1  light PR check   pull-requests '**' (docs-only changes skipped); blocks on a new Critical.
#   2  targeted full    custom: {BB_FULL} - run it by hand (Pipelines -> Run pipeline -> pick
#                       the branch -> custom: {BB_FULL}); blocks on a new Critical/High. Set
#                       GIZMODUCK_TARGET_URL to scan another guard-allowed base URL.
#   3  weekly sweep     custom: {BB_WEEKLY}, scheduled - never blocks.
# One-time setup for tier 3 (a schedule cannot be declared in this file):
#   Repository settings -> Pipelines -> Schedules -> New schedule
#   Branch: {default}   Pipeline: custom: {BB_WEEKLY}   Interval: Weekly, Sunday, 23:00 UTC
# Bitbucket has no PR labels and no cancel-in-progress. Endpoint scans never run on a PR.
#
# Repository variables read at runtime: GIZMODUCK_BB_TOKEN (secured; baseline
# Downloads, draft detection), GIZMODUCK_ALLOWED_PROD_ORIGINS + GIZMODUCK_ALLOW_PROD_SCAN,
# GIZMODUCK_ALLOWED_IP_ORIGINS, GIZMODUCK_ALLOW_NO_BASELINE,
# GIZMODUCK_ALLOW_INCOMPLETE, GIZMODUCK_TRUST_ASSIGNED_SEVERITY, NVD_API_KEY,
# GIZMODUCK_AUTH_HEADER_VALUE (secured; only when gizmoduck-ci.json sets auth "header"),
# GIZMODUCK_SDP_TICKETS + SDP_BASE_URL + SDP_API_KEY (+ SDP_AUTH_HEADER).
image: {cfg['image']}

definitions:
  caches:
{caches}
  steps:
{steps}

pipelines:
  pull-requests:
    '**':
      - step: *gizmoduck-pr-check
  custom:
    {BB_FULL}:
      - variables:
          - name: GIZMODUCK_TARGET_URL
            default: ""
            description: Base URL to scan instead of the configured staging URL (the guard still applies)
      - step: *gizmoduck-full-code
      # If this pipeline also deploys staging, put the deploy step here so the
      # endpoint scan runs against what was just deployed.
      - step: *gizmoduck-endpoint-scan
    {BB_WEEKLY}:
      - step: *gizmoduck-sweep-code
      - step: *gizmoduck-sweep-endpoints
    {BB_FULL}-bootstrap:
      - variables:
          - name: GIZMODUCK_TARGET_URL
            default: ""
            description: Base URL to scan instead of the configured staging URL (the guard still applies)
      - step:
          <<: *gizmoduck-full-code
          image: ubuntu:24.04
      - step:
          <<: *gizmoduck-endpoint-scan
          image: ubuntu:24.04
    {BB_WEEKLY}-bootstrap:
      - step:
          <<: *gizmoduck-sweep-code
          image: ubuntu:24.04
      - step:
          <<: *gizmoduck-sweep-endpoints
          image: ubuntu:24.04
"""


def render_all(cfg, platforms):
    files = {}
    if "github" in platforms:
        files[PR_FILE] = github_pr(cfg)
        files[FULL_FILE] = github_full(cfg)
        files[ENDPOINTS_FILE] = github_endpoints(cfg)
    if "bitbucket" in platforms:
        files[cfg.get("bitbucket_out") or "bitbucket-pipelines.yml"] = bitbucket(cfg)
    return files

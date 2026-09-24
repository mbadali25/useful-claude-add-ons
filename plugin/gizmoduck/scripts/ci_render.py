"""ci_render.py - the pipeline files `/gizmoduck:ci` writes into a target repo.

Pure text generation: nothing here reads the network or the filesystem, so the
golden-file tests pin the output byte for byte. gizmoduck_ci.py validates the
inputs (the prod-refusal guard runs there, before anything is rendered) and
does the writing.

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
}

SOURCE_REPO = "https://github.com/mbadali25/useful-claude-add-ons"
OPT_IN_TOOLS = ("nikto", "nmap", "sqlmap")
CODE_OUT = "/tmp/gizmoduck-out/code"
ENDPOINT_OUT = "/tmp/gizmoduck-out/endpoints"
CLI = 'python3 "$GIZMODUCK_HOME/scripts/gizmoduck_ci.py"'


def _publish_cmd(stage, title):
    return (f'{CLI} publish --out "$GIZMODUCK_OUT" '
            f'--baseline /tmp/gizmoduck-baseline/{stage}/findings.jsonl --title {shlex.quote(title)}')


def _gate_cmd(stage):
    return (f'{CLI} gate --baseline /tmp/gizmoduck-baseline/{stage}/findings.jsonl '
            '--current "$GIZMODUCK_OUT/findings.jsonl" --manifest "$GIZMODUCK_OUT/run-manifest.json" '
            '--json-out "$GIZMODUCK_OUT/gate.json" --new-out "$GIZMODUCK_OUT/new-blocking.jsonl"')


_TICKETS_CMD = (f'{CLI} tickets "$GIZMODUCK_OUT/new-blocking.jsonl" '
                '--out "$GIZMODUCK_OUT/tickets.json" --yes')
_TICKETS_IF = ("always() && steps.gate.outcome == 'failure' && "
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

def _gh_header(title, cfg):
    return (f"# Rendered by /gizmoduck:ci (gizmoduck {cfg['version']}) - {title}.\n"
            f"# Re-render with gizmoduck_ci.py rather than hand-editing; the prod-refusal\n"
            f"# guard's staging origins are baked in below and re-checked at runtime.\n"
            f"# Actions are pinned by full commit SHA; the trailing comment names the release.\n")


def _gh_env(cfg, out):
    return "\n".join([
        "env:",
        "  GIZMODUCK_HOME: /opt/gizmoduck",
        f"  GIZMODUCK_OUT: {out}",
        f"  GIZMODUCK_AUTHORIZED_BY: {_yq(cfg['authorized_by'])}",
        f"  GIZMODUCK_DEFAULT_BRANCH: {_yq(cfg['default_branch'])}",
        f"  GIZMODUCK_SOURCE_REPO: {_yq(cfg['source_repo'])}",
        f"  GIZMODUCK_REF: {_yq(cfg['gizmoduck_ref'])}",
        f"  GIZMODUCK_STAGING_URLS: {_yq(' '.join(cfg['staging_urls']))}",
        f"  GIZMODUCK_ENABLE: {_yq(','.join(cfg['enable']))}",
    ])


def _gh_bootstrap_step():
    body = BOOTSTRAP_SH + '\nif [ -n "${GITHUB_PATH:-}" ]; then echo "$HOME/.local/bin" >> "$GITHUB_PATH"; fi'
    return ("- name: Ensure the gizmoduck toolchain\n"
            "  run: |\n" + _indent(body, 4))


_GUARD_ENV = """\
env:
  GIZMODUCK_ALLOWED_PROD_ORIGINS: ${{ vars.GIZMODUCK_ALLOWED_PROD_ORIGINS }}
  GIZMODUCK_ALLOW_PROD_SCAN: ${{ vars.GIZMODUCK_ALLOW_PROD_SCAN }}
  GIZMODUCK_ALLOWED_IP_ORIGINS: ${{ vars.GIZMODUCK_ALLOWED_IP_ORIGINS }}"""

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


def _gh_common_head(stage, workflow_file, branch_filter):
    branch_arg = ' --branch "$GIZMODUCK_DEFAULT_BRANCH"' if branch_filter else ""
    return f"""\
- name: Check out
  {uses('checkout')}
  with:
    persist-credentials: false
{_gh_bootstrap_step()}
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


def _gh_common_tail(stage, title):
    return f"""\
- name: Reports (JSONL, Markdown, HTML, PDF) and diff
  if: always() && steps.scan.outcome == 'success'
  run: {_publish_cmd(stage, title)}
- name: Fail on new Critical/High
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
    if-no-files-found: warn
- name: ServiceDesk Plus tickets for new Critical/High (opt-in)
  if: {_TICKETS_IF}
{_indent(_TICKETS_ENV, 2)}
  run: {_TICKETS_CMD}"""


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


def github_code(cfg):
    steps = "\n".join([
        _gh_common_head("code", "gizmoduck-code.yml", branch_filter=True),
        f"""\
- name: Scan (Semgrep, Trivy fs, Checkov, Dependency-Check)
  id: scan
  env:
    NVD_API_KEY: ${{{{ secrets.NVD_API_KEY }}}}
  run: {CLI} code-stage --path "$GITHUB_WORKSPACE" --out "$GIZMODUCK_OUT"
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
    category: gizmoduck-code""",
        _gh_common_tail("code", "gizmoduck code scan"),
    ])
    text = "\n".join([
        _gh_header("code stage (Semgrep, Trivy fs, Checkov, Dependency-Check)", cfg),
        "name: gizmoduck code scan",
        "",
        "on:",
        "  pull_request:",
        "  push:",
        f"    branches: [{_yq(cfg['default_branch'])}]",
        "  workflow_dispatch:",
        "",
        "permissions:",
        "  contents: read",
        "",
        "concurrency:",
        "  group: gizmoduck-code-${{ github.ref }}",
        "  cancel-in-progress: true",
        "",
        "defaults:",
        "  run:",
        "    shell: bash",
        "",
        _gh_env(cfg, CODE_OUT),
        "",
        _gh_jobs(steps, "gizmoduck code scan", "{runner}",
                 [("contents", "read"), ("actions", "read"), ("security-events", "write")]),
    ])
    return text.replace("@@IMAGE@@", cfg["image"])


def github_endpoints(cfg):
    env_name = cfg["staging_environment"]
    triggers = ["on:", "  deployment_status:", "  workflow_dispatch:"]
    conds = ["github.event_name == 'workflow_dispatch'",
             ("(github.event_name == 'deployment_status' && "
              "github.event.deployment_status.state == 'success' && "
              f"github.event.deployment.environment == {_sq(env_name)})")]
    if cfg.get("deploy_workflow"):
        triggers += ["  workflow_run:",
                     f"    workflows: [{_yq(cfg['deploy_workflow'])}]",
                     "    types: [completed]"]
        conds.append("(github.event_name == 'workflow_run' && "
                     "github.event.workflow_run.conclusion == 'success')")
    condition = "{runner} && (" + " || ".join(conds) + ")"
    steps = "\n".join([
        f"""\
- name: Check out
  {uses('checkout')}
  with:
    persist-credentials: false
{_gh_bootstrap_step()}
- name: Prod-refusal guard (runs before any endpoint scan)
{_indent(_GUARD_ENV, 2)}
  run: {CLI} targets --endpoints "$GITHUB_WORKSPACE/.crew/endpoints.json" --out "$GIZMODUCK_OUT/targets.json"
- name: Find the baseline run
  id: prev
  env:
    GH_TOKEN: ${{{{ github.token }}}}
  run: {CLI} gh-previous-run --workflow gizmoduck-endpoints.yml >> "$GITHUB_OUTPUT"
- name: Download the baseline
  if: steps.prev.outputs.run_id != ''
  continue-on-error: true
  {uses('download-artifact')}
  with:
    name: gizmoduck-endpoints
    path: /tmp/gizmoduck-baseline/endpoints
    github-token: ${{{{ github.token }}}}
    run-id: ${{{{ steps.prev.outputs.run_id }}}}
- name: Scan staging (Nuclei, ZAP baseline, testssl{_opt_in_label(cfg)})
  id: scan
{_indent(_GUARD_ENV, 2)}
  run: {CLI} endpoint-stage --targets "$GIZMODUCK_OUT/targets.json" --out "$GIZMODUCK_OUT\"""",
        _gh_common_tail("endpoints", "gizmoduck staging endpoint scan"),
    ])
    text = "\n".join([
        _gh_header("endpoint stage (Nuclei, ZAP baseline, testssl against staging)", cfg),
        "name: gizmoduck staging endpoint scan",
        "",
        *triggers,
        "",
        "permissions:",
        "  contents: read",
        "",
        "concurrency:",
        "  group: gizmoduck-endpoints",
        "  cancel-in-progress: false",
        "",
        "defaults:",
        "  run:",
        "    shell: bash",
        "",
        _gh_env(cfg, ENDPOINT_OUT),
        "",
        _gh_jobs(steps, "gizmoduck staging endpoint scan", condition,
                 [("contents", "read"), ("actions", "read")]),
    ])
    return text.replace("@@IMAGE@@", cfg["image"])


def _sq(value):
    """A GitHub expression string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _opt_in_label(cfg):
    return "".join(f", {t}" for t in cfg["enable"])


# --------------------------------------------------------------------------
# Bitbucket Pipelines
# --------------------------------------------------------------------------

def _bb_exports(cfg, out):
    pairs = [
        ("GIZMODUCK_OUT", out),
        ("GIZMODUCK_AUTHORIZED_BY", cfg["authorized_by"]),
        ("GIZMODUCK_DEFAULT_BRANCH", cfg["default_branch"]),
        ("GIZMODUCK_SOURCE_REPO", cfg["source_repo"]),
        ("GIZMODUCK_REF", cfg["gizmoduck_ref"]),
        ("GIZMODUCK_STAGING_URLS", " ".join(cfg["staging_urls"])),
        ("GIZMODUCK_ENABLE", ",".join(cfg["enable"])),
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
if [ "$gate_rc" -eq 0 ] && [ "${{BITBUCKET_BRANCH:-}}" = "$GIZMODUCK_DEFAULT_BRANCH" ] \
&& [ -z "${{BITBUCKET_PR_ID:-}}" ] && [ -n "${{GIZMODUCK_BB_TOKEN:-}}" ]; then
  curl -fsS -X POST -H "Authorization: Bearer $GIZMODUCK_BB_TOKEN" \
-F "files=@$GIZMODUCK_OUT/findings.jsonl;filename=gizmoduck-{stage}-baseline.jsonl" \
"https://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/downloads" \
|| echo "gizmoduck: baseline upload failed - the next run compares against the previous baseline"
fi""")
    parts.append(f"""\
if [ "$gate_rc" -eq 1 ] && [ -z "${{BITBUCKET_PR_ID:-}}" ] && [ "${{GIZMODUCK_SDP_TICKETS:-}}" = "true" ]; then
  {_TICKETS_CMD} || echo "gizmoduck: ticketing failed"
fi""")
    parts.append(f"""\
mkdir -p "$BITBUCKET_CLONE_DIR/gizmoduck-out"
cp -r "$GIZMODUCK_OUT" "$BITBUCKET_CLONE_DIR/gizmoduck-out/{stage}"
exit "$gate_rc\"""")
    return parts


def _bb_step(anchor, name, script_items):
    items = "\n".join(_bb_item(s) for s in script_items)
    return f"""\
    - step: &{anchor}
        name: {_yq(name)}
        size: 2x
        max-time: 120
        script:
{_indent(items, 10)}
        artifacts:
          - gizmoduck-out/**"""


def bitbucket(cfg):
    code_items = [
        _bb_exports(cfg, CODE_OUT),
        BOOTSTRAP_SH,
        _bb_baseline_download("code"),
        f'{CLI} code-stage --path "$BITBUCKET_CLONE_DIR" --out "$GIZMODUCK_OUT"',
        *_bb_tail("code", "gizmoduck code scan", insights=True),
    ]
    endpoint_items = [
        _bb_exports(cfg, ENDPOINT_OUT),
        BOOTSTRAP_SH,
        ("# Prod-refusal guard: runs before any endpoint scan and fails the step on a refused target.\n"
         f'mkdir -p "$GIZMODUCK_OUT"\n{CLI} targets --endpoints "$BITBUCKET_CLONE_DIR/.crew/endpoints.json" '
         '--out "$GIZMODUCK_OUT/targets.json"'),
        _bb_baseline_download("endpoints"),
        f'{CLI} endpoint-stage --targets "$GIZMODUCK_OUT/targets.json" --out "$GIZMODUCK_OUT"',
        *_bb_tail("endpoints", "gizmoduck staging endpoint scan", insights=False),
    ]
    branch = _yq(cfg["default_branch"])
    code_name = "gizmoduck: code scan (Semgrep, Trivy fs, Checkov, Dependency-Check)"
    endpoint_name = f"gizmoduck: staging endpoint scan (Nuclei, ZAP baseline, testssl{_opt_in_label(cfg)})"
    return f"""\
# Rendered by /gizmoduck:ci (gizmoduck {cfg['version']}).
# Re-render with gizmoduck_ci.py rather than hand-editing; the prod-refusal
# guard's staging origins are baked in below and re-checked at runtime.
# Repository variables read at runtime: GIZMODUCK_BB_TOKEN (secured; baseline
# Downloads), GIZMODUCK_ALLOWED_PROD_ORIGINS + GIZMODUCK_ALLOW_PROD_SCAN,
# GIZMODUCK_ALLOWED_IP_ORIGINS, GIZMODUCK_ALLOW_NO_BASELINE,
# GIZMODUCK_ALLOW_INCOMPLETE, GIZMODUCK_TRUST_ASSIGNED_SEVERITY, NVD_API_KEY,
# GIZMODUCK_SDP_TICKETS + SDP_BASE_URL + SDP_API_KEY (+ SDP_AUTH_HEADER).
image: {cfg['image']}

definitions:
  steps:
{_bb_step("gizmoduck-code-scan", code_name, code_items)}
{_bb_step("gizmoduck-endpoint-scan", endpoint_name, endpoint_items)}

pipelines:
  pull-requests:
    '**':
      - step: *gizmoduck-code-scan
  branches:
    {branch}:
      - step: *gizmoduck-code-scan
      # Put your staging deploy step here, between the two scans, so the
      # endpoint scan runs against what was just deployed.
      - step: *gizmoduck-endpoint-scan
  custom:
    gizmoduck-endpoint-scan:
      - step: *gizmoduck-endpoint-scan
    gizmoduck-code-scan-bootstrap:
      - step:
          <<: *gizmoduck-code-scan
          image: ubuntu:24.04
    gizmoduck-endpoint-scan-bootstrap:
      - step:
          <<: *gizmoduck-endpoint-scan
          image: ubuntu:24.04
"""


def render_all(cfg, platforms):
    files = {}
    if "github" in platforms:
        files[".github/workflows/gizmoduck-code.yml"] = github_code(cfg)
        files[".github/workflows/gizmoduck-endpoints.yml"] = github_endpoints(cfg)
    if "bitbucket" in platforms:
        files[cfg.get("bitbucket_out") or "bitbucket-pipelines.yml"] = bitbucket(cfg)
    return files

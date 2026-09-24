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

Trust. A pull request is untrusted code, and nothing it runs may hold a
write-capable credential or feed a trusted run:

  - GitHub PR jobs use `pull_request` (never `pull_request_target`), hold
    `contents: read` + `actions: read`, and reference no secret. Only the
    separate SARIF upload job holds `security-events: write`, and it runs no
    scanner and no bootstrap. Every other job states its own permissions;
    the workflow default is none.
  - Each PR workflow ends in a `gate` job that ALWAYS runs and passes or
    fails from the event itself (tier applies? did the scan succeed?), so
    the check a branch rule requires is never a skipped job that a later
    unrelated event (a `labeled` for another label) can supersede. BOTH PR
    workflows trigger on `labeled` / `unlabeled` and decide their tier from
    the PR's current label set, so removing the security-scan label re-runs
    tier 1 on the head commit - a tier-2 gate that stops applying is never
    the last word on a head nothing scanned.
  - The endpoint workflow scans after `deployment_status` only when a
    secret-free `trust` job has confirmed the deployment: its environment
    is the configured staging environment, its ref names a trusted branch
    (the default branch or release/*), and its SHA is an ancestor of that
    branch's head in THIS repository (`git merge-base --is-ancestor`). A
    ref name alone proves nothing - a pull request can deploy a branch
    called release/anything. The scan jobs, the only ones holding a secret,
    `needs:` that job. After `workflow_run` it scans only when the run was
    for a trusted branch of this repository and not from a pull request.
    Anything else skips every secret-holding job - a neutral result.
  - Baselines come only from successful runs on the default branch that
    were not pull-request events, from this repository, and still carry
    the artifact (gizmoduck_ci.previous_run_id).
  - Caches are keyed by trust level: a pull-request run's cache key starts
    `gizmoduck-<name>-pr-` and a trusted run restores only
    `gizmoduck-<name>-trusted-`.
  - Bitbucket has no per-pipeline variable scoping, so every secret the
    pipeline knows (TRUSTED_SECRETS: GIZMODUCK_BB_TOKEN, SDP_*, NVD_API_KEY,
    GIZMODUCK_AUTH_HEADER_VALUE) is a deployment variable of the
    `gizmoduck-trusted` deployment environment, which only the custom
    pipelines' stages use. The PR step refuses to run if one of them is
    visible to it (that means it was made a repository variable), reads
    its baseline and draft state with the read-only
    GIZMODUCK_BB_READ_TOKEN, and uses its own `gizmoduck-pr-*` caches. A
    custom run on a branch that is not trusted refuses outright if any of
    them is visible - it never runs with a secret, not even a read-only
    one like NVD_API_KEY or the scan auth header.
    A PR that edits bitbucket-pipelines.yml itself runs whatever it
    writes - Bitbucket's own limit; deployment permissions (Premium)
    restricting `gizmoduck-trusted` to the default branch are what close it.

Action pinning: every third-party action is pinned to a full commit SHA with
the release it came from in a trailing comment. A tag - even a major tag like
`@v4` - is a mutable pointer that the action's owner (or anyone who takes over
the account) can move, and a security-scan workflow holds `security-events:
write` and reads repository secrets. A SHA cannot be moved. The cost is that
updates are manual; Dependabot's `github-actions` ecosystem updates SHA pins
and keeps the comment in step.
"""
import json
import re
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
BB_TRUSTED_ENV = "gizmoduck-trusted"
RELEASE_GLOB = "release/*"
WRITE_SECRETS = ("GIZMODUCK_BB_TOKEN", "SDP_API_KEY", "SDP_BASE_URL")
# Every secret the Bitbucket pipeline knows: no untrusted run may see any.
TRUSTED_SECRETS = WRITE_SECRETS + ("NVD_API_KEY", "GIZMODUCK_AUTH_HEADER_VALUE")
_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._/:@-]{0,254}")


def check_image(image):
    """The runner image reference: one line of registry/name[:tag][@digest]
    characters, nothing YAML or a shell could read as more than a string.
    The renderer also emits it quoted."""
    if not isinstance(image, str) or not _IMAGE_RE.fullmatch(image):
        raise ValueError(f"refusing unsafe image reference {image!r}: one line of lower-case "
                         f"letters, digits and ./_:@-")
    return image


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
_IS_SWEEP = "github.event_name == 'schedule'"


def _trusted_ref(expr, cfg):
    """`expr` names a trusted branch: the default branch or release/*, bare or
    as refs/heads/..."""
    d = cfg["default_branch"]
    return (f"({expr} == {_sq(d)} || {expr} == {_sq('refs/heads/' + d)} || "
            f"startsWith({expr}, 'release/') || startsWith({expr}, 'refs/heads/release/'))")


def _gh_header(title, cfg):
    return (f"# Rendered by /gizmoduck:ci (gizmoduck {cfg['version']}) - {title}.\n"
            f"# Re-render with gizmoduck_ci.py rather than hand-editing; the prod-refusal\n"
            f"# guard's staging origins are baked in below and re-checked at runtime.\n"
            f"# Actions are pinned by full commit SHA; the trailing comment names the release.\n"
            f"# Tiers: gizmoduck-pr.yml (1, light PR check), gizmoduck-full.yml (2 + weekly\n"
            f"# code sweep + manual), gizmoduck-endpoints.yml (2 after the staging deploy +\n"
            f"# weekly endpoint sweep + manual). Endpoint scans never run on a pull request.\n"
            f"# Branch protection: require the `gate` job of gizmoduck-pr.yml and of\n"
            f"# gizmoduck-full.yml - each always runs and decides from the event, so a\n"
            f"# later skipped run can never stand in for a failed scan. (A docs-only PR\n"
            f"# does not trigger gizmoduck-pr.yml at all, so its gate reports nothing.)\n")


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


_CACHE_KEY_SH = """\
if [ "$GITHUB_EVENT_NAME" = "pull_request" ]; then trust="pr"; else trust="trusted"; fi
suffix=""
if [ "$GITHUB_EVENT_NAME" = "schedule" ]; then suffix="-sweep-$GITHUB_RUN_ID"; fi
{ echo "trust=$trust"; echo "key=$(date -u +%G-%V)"; echo "suffix=$suffix"; } >> "$GITHUB_OUTPUT\""""


def _gh_caches(names, conditions=None):
    """Keys `gizmoduck-<name>-<trust>-<ISO week>[-sweep-<run>]`. The trust
    level (pr / trusted) is in the key AND the restore prefix, so a pull
    request's cache is never restored into a trusted run. Every run restores
    the newest copy for its trust level; the first run of a week saves one,
    and the weekly sweep always saves a fresh one under its own run-stamped
    key - an earlier run that week cannot pin the refreshed data out."""
    conditions = conditions or {}
    out = ["- name: Cache key (trust level, ISO week)\n  id: week\n  run: |\n" + _indent(_CACHE_KEY_SH, 4)]
    for name in names:
        label, path = _CACHES[name]
        cond = f"\n  if: {conditions[name]}" if name in conditions else ""
        prefix = f"gizmoduck-{name}-${{{{ steps.week.outputs.trust }}}}-"
        out.append(f"""\
- name: Cache {label}{cond}
  {uses('cache')}
  with:
    path: {path}
    key: {prefix}${{{{ steps.week.outputs.key }}}}${{{{ steps.week.outputs.suffix }}}}
    restore-keys: {prefix}""")
    return "\n".join(out)


def _gh_baseline(stage, workflow_file):
    """The newest successful non-PR run of `workflow_file` on the default
    branch, from this repository, that still has the artifact - never a run a
    pull request or an untrusted deploy could have produced."""
    lookup = (f'{CLI} gh-previous-run --workflow {workflow_file} --trusted "$GIZMODUCK_DEFAULT_BRANCH" '
              f'--artifact gizmoduck-{stage} >> "$GITHUB_OUTPUT"')
    return f"""\
- name: Find the baseline run (default branch, trusted runs only)
  id: prev
  env:
    GH_TOKEN: ${{{{ github.token }}}}
  run: {lookup}
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
    """SARIF is written here and uploaded by the separate `sarif` job - the
    only job that holds `security-events: write`."""
    run = (f'{CLI} sarif "$GIZMODUCK_OUT/findings.jsonl" --out "$GIZMODUCK_OUT/gizmoduck.sarif" '
           '--srcroot "$GITHUB_WORKSPACE"')
    return f"""\
- name: SARIF (uploaded by the sarif job)
  id: sarif
  if: always() && steps.scan.outcome == 'success'
  run: {run}"""


def _gh_sarif_job(label):
    return f"""\
  sarif:
    name: {label} (upload SARIF)
    needs: [scan, scan-bootstrap]
    if: always() && (needs.scan.outputs.sarif == 'true' || needs.scan-bootstrap.outputs.sarif == 'true')
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    permissions:
      contents: read
      security-events: write
    steps:
{_indent(_gh_checkout(), 6)}
      - name: Download the scan results
        {uses('download-artifact')}
        with:
          name: gizmoduck-code
          path: /tmp/gizmoduck-sarif
      - name: Upload SARIF to code scanning
        continue-on-error: ${{{{ github.event.pull_request.head.repo.fork == true }}}}
        {uses('upload-sarif')}
        with:
          sarif_file: /tmp/gizmoduck-sarif/gizmoduck.sarif
          category: gizmoduck-code"""


_GATE_JOB_SH = """\
if [ "$GIZMODUCK_APPLIES" != "true" ]; then
  echo "gizmoduck: this event is outside this workflow's tier - nothing to gate (pass)"
  exit 0
fi
echo "gizmoduck: scan jobs - runner image: $IMAGE_RESULT, inline bootstrap: $BOOT_RESULT"
if { [ "$IMAGE_RESULT" = "success" ] && [ "$BOOT_RESULT" = "skipped" ]; } \\
   || { [ "$IMAGE_RESULT" = "skipped" ] && [ "$BOOT_RESULT" = "success" ]; }; then
  echo "gizmoduck: gate PASS"
  exit 0
fi
echo "gizmoduck: gate FAIL - the scan this event requires did not pass"
exit 1"""


def _gh_gate_job(label, applies):
    return f"""\
  gate:
    name: {label} gate
    needs: [scan, scan-bootstrap]
    if: always()
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions: {{}}
    env:
      GIZMODUCK_APPLIES: ${{{{ {applies} }}}}
      IMAGE_RESULT: ${{{{ needs.scan.result }}}}
      BOOT_RESULT: ${{{{ needs.scan-bootstrap.result }}}}
    steps:
      - name: Gate (required check - always runs, decides from the event)
        run: |
{_indent(_GATE_JOB_SH, 10)}"""


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


_SCAN_PERMS = [("contents", "read"), ("actions", "read")]


def _gh_jobs(steps, label, condition, sarif=False, gate=False, trust=None):
    """The scan job twice (runner image / inline bootstrap - exactly one runs),
    each with read-only permissions; then, for code workflows, the SARIF
    upload job (the only `security-events: write`), and for PR-event
    workflows the always-running gate job. `trust`, when given, is a job
    rendered first that both scan jobs `needs:`."""
    perm = "\n".join(f"      {k}: {v}" for k, v in _SCAN_PERMS)
    outputs = ("    outputs:\n      sarif: ${{ steps.sarif.outcome == 'success' }}\n" if sarif else "")
    needs = "    needs: [trust]\n" if trust else ""
    image_job = f"""\
  scan:
    name: {label} (runner image)
{needs}    if: {condition.format(runner="vars.GIZMODUCK_RUNNER != 'bootstrap'")}
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    container:
      image: @@IMAGE@@
    permissions:
{perm}
{outputs}    steps:
{_indent(steps, 6)}"""
    boot_job = f"""\
  scan-bootstrap:
    name: {label} (inline bootstrap fallback)
{needs}    if: {condition.format(runner="vars.GIZMODUCK_RUNNER == 'bootstrap'")}
    runs-on: ubuntu-24.04
    timeout-minutes: 180
    permissions:
{perm}
{outputs}    steps:
{_indent(steps, 6)}"""
    jobs = ([trust] if trust else []) + [image_job, boot_job]
    if sarif:
        jobs.append(_gh_sarif_job(label))
    if gate:
        jobs.append(_gh_gate_job(label, condition.format(runner="true")))
    return "jobs:\n" + "\n\n".join(jobs) + "\n"


def _gh_file(title, name, triggers, group, env, jobs, cfg):
    text = "\n".join([
        _gh_header(title, cfg),
        f"name: {name}",
        "",
        "on:",
        *triggers,
        "",
        "permissions: {}",
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
    return text.replace("@@IMAGE@@", _yq(check_image(cfg["image"])))


def github_pr(cfg):
    """Tier 1. Every non-draft PR that tier 2 does not cover, docs-only
    changes excluded by path; blocks on a new Critical only."""
    steps = "\n".join([
        _gh_checkout(fetch_depth=0),
        _gh_bootstrap_step(),
        _gh_caches(["trivy"]),
        _gh_baseline("code", "gizmoduck-full.yml"),
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
    # labeled/unlabeled too: removing the security-scan label takes the PR
    # out of tier 2, and tier 1 must then scan the head commit rather than
    # leave tier 2's no-longer-applicable PASS as the only verdict on it.
    triggers = ["  pull_request:",
                "    types: [opened, synchronize, reopened, ready_for_review, labeled, unlabeled]",
                "    paths-ignore:",
                *[f"      - {_yq(p)}" for p in DOCS_ONLY]]
    env = _gh_env(cfg, CODE_OUT, "light", "critical", [("TRIVY_CACHE_DIR", _CACHES["trivy"][1])])
    return _gh_file("tier 1, light PR check (blocks on a new Critical only)", "gizmoduck PR check", triggers,
                    "gizmoduck-pr-${{ github.event.pull_request.number || github.ref }}", env,
                    _gh_jobs(steps, "gizmoduck PR check", condition, sarif=True, gate=True), cfg)


def github_full(cfg):
    """Tier 2 code scans (PRs into the default branch or release/*, or the
    security-scan label), the tier-3 weekly code sweep (schedule), and a
    manual full scan of any ref (workflow_dispatch)."""
    steps = "\n".join([
        _gh_checkout(fetch_depth=0, ref_input=True),
        _gh_bootstrap_step(),
        _gh_caches(["trivy", "nvd"], {"nvd": _IS_SWEEP}),
        _gh_baseline("code", "gizmoduck-full.yml"),
        f"""\
- name: Scan (Semgrep, Trivy fs, Checkov, gitleaks history; Dependency-Check on the weekly sweep)
  id: scan
  env:
    NVD_API_KEY: ${{{{ {_IS_SWEEP} && secrets.NVD_API_KEY || '' }}}}
  run: |
    git config --global --add safe.directory "$GITHUB_WORKSPACE"
    {CLI} code-stage --tier "$GIZMODUCK_TIER" --path "$GITHUB_WORKSPACE" --out "$GIZMODUCK_OUT\"""",
        _gh_sarif(),
        _gh_tail("code", "gizmoduck full code scan", tickets=True),
    ])
    # Tier 2 is decided from the PR's label SET, never from which label an
    # event added: any labeled/unlabeled event re-evaluates it, so an
    # unrelated label cannot skip a tier-2 PR's scan, and the gate job turns
    # the result into a check a skipped run cannot supersede.
    condition = ("{runner} && ((github.event_name == 'pull_request' && " + _NOT_DRAFT + " && " +
                 _tier2_pr(cfg) + ") || " + _IS_SWEEP +
                 " || github.event_name == 'workflow_dispatch')")
    triggers = ["  pull_request:",
                "    types: [opened, synchronize, reopened, ready_for_review, labeled, unlabeled]",
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
                    env, _gh_jobs(steps, "gizmoduck full code scan", condition, sarif=True, gate=True), cfg)


_DEPLOY_TRUST_SH = """\
neutral() {
  echo "gizmoduck: $1 - not a trusted deployment; the endpoint scan is skipped (neutral) and no secret is used"
  echo "trusted=false" >> "$GITHUB_OUTPUT"
  exit 0
}
if [ "$DEPLOY_ENVIRONMENT" != "$GIZMODUCK_STAGING_ENVIRONMENT" ]; then
  neutral "environment '$DEPLOY_ENVIRONMENT' is not the configured staging environment"
fi
branch="${DEPLOY_REF#refs/heads/}"
case "$branch" in
  "$GIZMODUCK_DEFAULT_BRANCH"|release/*) ;;
  *) neutral "ref '$DEPLOY_REF' is not a trusted branch" ;;
esac
if ! printf '%s' "$DEPLOY_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
  neutral "deployment SHA '$DEPLOY_SHA' is not a full commit SHA"
fi
# The ref is a name the deployer chose; the SHA is what was deployed. Trust it
# only when it is reachable from that trusted branch's head in THIS repository.
if ! git rev-parse -q --verify "refs/remotes/origin/$branch^{commit}" >/dev/null; then
  neutral "branch '$branch' does not exist in this repository"
fi
if ! git merge-base --is-ancestor "$DEPLOY_SHA" "refs/remotes/origin/$branch" 2>/dev/null; then
  neutral "deployed SHA $DEPLOY_SHA is not reachable from origin/$branch"
fi
echo "gizmoduck: deployed SHA $DEPLOY_SHA is on origin/$branch - trusted"
echo "trusted=true" >> "$GITHUB_OUTPUT\""""


def _gh_deploy_trust_job(cfg):
    """The secret-free job every deployment_status scan `needs:`. It fetches
    the repository's branches (read-only token, not persisted) and decides
    from git, never from the deployment's ref name alone."""
    return f"""\
  trust:
    name: gizmoduck deployment trust check (no secrets)
    if: github.event_name == 'deployment_status'
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    permissions:
      contents: read
    outputs:
      trusted: ${{{{ steps.check.outputs.trusted }}}}
    steps:
      - name: Check out every branch (history only; nothing is run from it)
        {uses('checkout')}
        with:
          persist-credentials: false
          fetch-depth: 0
          ref: {_yq(cfg['default_branch'])}
      - name: Is the deployed SHA on a trusted branch of this repository?
        id: check
        env:
          GIZMODUCK_STAGING_ENVIRONMENT: {_yq(cfg['staging_environment'])}
          DEPLOY_ENVIRONMENT: ${{{{ github.event.deployment.environment }}}}
          DEPLOY_REF: ${{{{ github.event.deployment.ref }}}}
          DEPLOY_SHA: ${{{{ github.event.deployment.sha }}}}
        run: |
{_indent(_DEPLOY_TRUST_SH, 10)}"""


def github_endpoints(cfg):
    """Tier 2 endpoint scans after the staging deploy, the tier-3 weekly
    endpoint sweep, and a manual scan of any guard-allowed URL. Never on a
    pull_request."""
    env_name = cfg["staging_environment"]
    triggers = ["  deployment_status:"]
    # A deploy event is trusted only once the secret-free `trust` job has
    # proved the deployed SHA is on a trusted branch of THIS repository; the
    # ref name alone is chosen by whoever deployed. Anything else skips the
    # scan jobs (a neutral result) before any of their steps - and so any
    # secret - is evaluated.
    conds = ["github.event_name == 'workflow_dispatch'", _IS_SWEEP,
             ("(github.event_name == 'deployment_status' && "
              "github.event.deployment_status.state == 'success' && "
              f"github.event.deployment.environment == {_sq(env_name)} && "
              f"{_trusted_ref('github.event.deployment.ref', cfg)} && "
              "needs.trust.outputs.trusted == 'true')")]
    if cfg.get("deploy_workflow"):
        triggers += ["  workflow_run:",
                     f"    workflows: [{_yq(cfg['deploy_workflow'])}]",
                     "    types: [completed]"]
        conds.append("(github.event_name == 'workflow_run' && "
                     "github.event.workflow_run.conclusion == 'success' && "
                     "github.event.workflow_run.head_repository.full_name == github.repository && "
                     "github.event.workflow_run.event != 'pull_request' && "
                     "github.event.workflow_run.event != 'pull_request_target' && "
                     f"{_trusted_ref('github.event.workflow_run.head_branch', cfg)})")
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
    # `!cancelled()` (not first - a leading `!` is a YAML tag): without a
    # status function a job whose `needs:` was skipped is skipped too, and
    # `trust` is skipped for every event but deployment_status.
    condition = "{runner} && !cancelled() && (" + " || ".join(conds) + ")"
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
        _gh_baseline("endpoints", "gizmoduck-endpoints.yml"),
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
                    "gizmoduck-endpoints-${{ github.event_name }}-${{ " +
                    ("github.event.workflow_run.head_branch || " if cfg.get("deploy_workflow") else "") +
                    "github.event.deployment.ref || github.ref }}", env,
                    _gh_jobs(steps, "gizmoduck staging endpoint scan", condition,
                             trust=_gh_deploy_trust_job(cfg)), cfg)


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
    """Read with the read-only token. A missing token or baseline leaves the
    file absent, and the gate fails closed on it (unless the first-run
    opt-in is set)."""
    return f"""\
mkdir -p /tmp/gizmoduck-baseline/{stage} "$GIZMODUCK_OUT"
if [ -n "${{GIZMODUCK_BB_READ_TOKEN:-}}" ]; then
  curl -fsSL -H "Authorization: Bearer $GIZMODUCK_BB_READ_TOKEN" -o /tmp/gizmoduck-baseline/{stage}/findings.jsonl \
"https://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/downloads/gizmoduck-{stage}-baseline.jsonl" \
|| {{ rm -f /tmp/gizmoduck-baseline/{stage}/findings.jsonl; echo "gizmoduck: no {stage} baseline in Downloads yet"; }}
else
  echo "gizmoduck: GIZMODUCK_BB_READ_TOKEN is not set - no baseline can be read; the gate fails closed on that"
fi"""


_BB_PR_TRUST = """\
# A pull request is untrusted code: no secret may be visible to it - not a
# write-capable secret, and not NVD_API_KEY or the scan auth header either.
# They belong to the gizmoduck-trusted deployment environment, which only the
# custom pipelines use - one visible here was made a repository variable.
for v in @@SECRETS@@; do
  if [ -n "$(printenv "$v" || true)" ]; then
    echo "gizmoduck: $v is visible to a pull-request pipeline - it is a repository variable. Move it to the" \
"@@TRUSTED_ENV@@ deployment environment (Repository settings -> Deployments); refusing to run with it."
    exit 1
  fi
done
unset @@SECRETS@@
# Tier 1 skips draft PRs. Bitbucket passes no draft flag to a pipeline, so it
# is read from the pull request with the read-only GIZMODUCK_BB_READ_TOKEN. A
# state this step cannot read fails the check - a draft is never guessed at.
if [ -z "${GIZMODUCK_BB_READ_TOKEN:-}" ]; then
  echo "gizmoduck: GIZMODUCK_BB_READ_TOKEN is not available (a fork's pull request never gets secured variables),"
  echo "so this check cannot tell a draft apart or read its baseline - failing rather than scanning blind."
  echo "A maintainer can run custom: @@BB_FULL@@ on the branch instead."
  exit 1
fi
draft="$(curl -fsS -H "Authorization: Bearer $GIZMODUCK_BB_READ_TOKEN" \
"https://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/pullrequests/${BITBUCKET_PR_ID:-0}" \
| python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("draft", False)).lower())' || echo unknown)"
case "$draft" in
  true) echo "gizmoduck: draft pull request - tier 1 is skipped until it is marked ready for review"; exit 0 ;;
  false) ;;
  *) echo "gizmoduck: could not read whether pull request ${BITBUCKET_PR_ID:-?} is a draft - failing closed"; exit 1 ;;
esac""".replace("@@SECRETS@@", " ".join(TRUSTED_SECRETS)).replace("@@TRUSTED_ENV@@", BB_TRUSTED_ENV) \
    .replace("@@BB_FULL@@", BB_FULL)


_BB_TRUSTED_REF = """\
# Secrets (gizmoduck-trusted deployment variables) are used only on a trusted
# branch: the default branch or release/*. A custom run on any other branch
# refuses if ANY of them is visible - dropping some and keeping the rest is how
# the deployment secrets reached a feature branch's staging code before.
case "${BITBUCKET_BRANCH:-}" in
  "$GIZMODUCK_DEFAULT_BRANCH"|release/*) ;;
  *) for v in @@SECRETS@@; do
       if [ -n "$(printenv "$v" || true)" ]; then
         echo "gizmoduck: '${BITBUCKET_BRANCH:-<none>}' is not a trusted branch and $v is visible to it -" \
"refusing to run. Run custom pipelines on the default branch or release/*, or (Premium) restrict the" \
"@@TRUSTED_ENV@@ deployment environment to them."
         exit 1
       fi
     done
     echo "gizmoduck: '${BITBUCKET_BRANCH:-<none>}' is not a trusted branch - running with no secrets"
     unset @@SECRETS@@ ;;
esac""".replace("@@SECRETS@@", " ".join(TRUSTED_SECRETS)).replace("@@TRUSTED_ENV@@", BB_TRUSTED_ENV)


def _bb_tail(stage, title, insights, trusted=True):
    """Publish, gate, Code Insights; then - trusted steps only - the baseline
    upload and tickets, the two things a write-capable secret is for. The
    pull-request step renders neither."""
    parts = [
        _publish_cmd(stage, title),
        f"gate_rc=0\n{_gate_cmd(stage)} || gate_rc=$?",
        "insights_rc=0",
    ]
    if insights:
        parts.append(f"""\
# Code Insights: a failure here fails the step (after the gate's own verdict),
# so a broken report or credential is never a green pipeline with no report.
{CLI} bb-insights "$GIZMODUCK_OUT/findings.jsonl" --gate "$GIZMODUCK_OUT/gate.json" \
--outdir "$GIZMODUCK_OUT/insights" --srcroot "$BITBUCKET_CLONE_DIR" || insights_rc=$?
rep="http://api.bitbucket.org/2.0/repositories/$BITBUCKET_REPO_FULL_NAME/commit/$BITBUCKET_COMMIT\
/reports/gizmoduck-{stage}"
if [ "$insights_rc" -eq 0 ]; then
  curl -fsS --proxy http://localhost:29418 -X PUT "$rep" -H "Content-Type: application/json" \
--data-binary @"$GIZMODUCK_OUT/insights/report.json" || insights_rc=$?
  for f in "$GIZMODUCK_OUT"/insights/annotations-*.json; do
    [ -f "$f" ] || continue
    curl -fsS --proxy http://localhost:29418 -X POST "$rep/annotations" -H "Content-Type: application/json" \
--data-binary @"$f" || insights_rc=$?
  done
fi""")
    if trusted:
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
&& [ -n "${{SDP_API_KEY:-}}" ] && [ -s "$GIZMODUCK_OUT/new-blocking.jsonl" ]; then
  {_TICKETS_CMD} || echo "gizmoduck: ticketing failed"
fi""")
    parts.append(f"""\
mkdir -p "$BITBUCKET_CLONE_DIR/gizmoduck-out"
cp -r "$GIZMODUCK_OUT" "$BITBUCKET_CLONE_DIR/gizmoduck-out/{stage}"
if [ "$gate_rc" -ne 0 ]; then exit "$gate_rc"; fi
if [ "$insights_rc" -ne 0 ]; then
  echo "gizmoduck: Code Insights report failed (exit $insights_rc) - failing the step"
  exit "$insights_rc"
fi""")
    return parts


def _bb_step(anchor, name, script_items, caches, max_time=120, pr_check=False, full_clone=False):
    items = "\n".join(_bb_item(s) for s in script_items)
    extra = ""
    if pr_check or full_clone:
        extra = "        clone:\n          depth: full\n"
    if pr_check:
        paths = "\n".join(f"              - {_yq(p)}" for p in DOCS_ONLY)
        extra += "        condition:\n          changesets:\n            excludePaths:\n" + paths + "\n"
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
    items.append(_BB_PR_TRUST if pr_check else _BB_TRUSTED_REF)
    items += [BOOTSTRAP_SH, _bb_baseline_download("code"), stage_cmd,
              *_bb_tail("code", title, insights=True, trusted=not pr_check)]
    return items


def _bb_endpoint_items(cfg, tier, block_at):
    return [
        _bb_exports(cfg, ENDPOINT_OUT, tier, block_at),
        _BB_TRUSTED_REF,
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
                 ["pr-trivy"], max_time=30, pr_check=True),
        _bb_step("gizmoduck-full-code", "gizmoduck tier 2: full code scan (Semgrep, Trivy, Checkov, gitleaks)",
                 _bb_code_items(cfg, "full", "high", code_tiered, "gizmoduck full code scan"), ["trivy"],
                 full_clone=True),
        _bb_step("gizmoduck-endpoint-scan", f"gizmoduck tier 2: staging endpoint scan ({ep})",
                 _bb_endpoint_items(cfg, "full", "high"), ["nuclei"]),
        _bb_step("gizmoduck-sweep-code", "gizmoduck tier 3: weekly code sweep incl. Dependency-Check (never blocks)",
                 _bb_code_items(cfg, "sweep", "never", code_tiered, "gizmoduck weekly code sweep"),
                 ["trivy", "nvd"], max_time=240, full_clone=True),
        _bb_step("gizmoduck-sweep-endpoints", f"gizmoduck tier 3: weekly endpoint sweep ({ep}; never blocks)",
                 _bb_endpoint_items(cfg, "sweep", "never"), ["nuclei"], max_time=240),
    ])
    # Trust-scoped caches: the PR step's is its own name, never restored by
    # a trusted step.
    caches = "\n".join([f"    gizmoduck-{k}: {v[1]}" for k, v in _CACHES.items()]
                       + [f"    gizmoduck-pr-trivy: {_CACHES['trivy'][1]}"])
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
# One-time setup for trust (the pull-request step refuses to run without it):
#   Repository settings -> Deployments -> add an environment named {BB_TRUSTED_ENV}
#   and put EVERY secret there as a deployment variable, never as a repository
#   variable: GIZMODUCK_BB_TOKEN (secured; uploads the baseline), SDP_BASE_URL +
#   SDP_API_KEY (secured; tickets), NVD_API_KEY (secured),
#   GIZMODUCK_AUTH_HEADER_VALUE (secured; only when gizmoduck-ci.json sets auth "header").
#   Only the custom pipelines' stages use that environment. A pull request, or a
#   custom run on a branch other than {default} or release/*, refuses to run if any
#   of those is visible to it. On Premium, restrict the environment's deployment
#   permissions to {default} - a pull request that edits this file runs whatever it
#   writes, and that restriction is what keeps it from the environment.
# Repository variables: GIZMODUCK_BB_READ_TOKEN (secured; a READ-only access token -
#   baselines and draft detection), GIZMODUCK_ALLOWED_PROD_ORIGINS + GIZMODUCK_ALLOW_PROD_SCAN,
#   GIZMODUCK_ALLOWED_IP_ORIGINS, GIZMODUCK_ALLOW_NO_BASELINE, GIZMODUCK_ALLOW_INCOMPLETE,
#   GIZMODUCK_TRUST_ASSIGNED_SEVERITY, GIZMODUCK_SDP_TICKETS (+ SDP_AUTH_HEADER).
# Caches: the PR step uses gizmoduck-pr-trivy only; trusted steps never restore it.
image: {_yq(check_image(cfg['image']))}

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
      - stage:
          name: gizmoduck tier 2 (trusted)
          deployment: {BB_TRUSTED_ENV}
          steps:
            - step: *gizmoduck-full-code
            # If this pipeline also deploys staging, put the deploy step here so the
            # endpoint scan runs against what was just deployed.
            - step: *gizmoduck-endpoint-scan
    {BB_WEEKLY}:
      - stage:
          name: gizmoduck tier 3 (trusted)
          deployment: {BB_TRUSTED_ENV}
          steps:
            - step: *gizmoduck-sweep-code
            - step: *gizmoduck-sweep-endpoints
    {BB_FULL}-bootstrap:
      - variables:
          - name: GIZMODUCK_TARGET_URL
            default: ""
            description: Base URL to scan instead of the configured staging URL (the guard still applies)
      - stage:
          name: gizmoduck tier 2 (trusted, inline bootstrap)
          deployment: {BB_TRUSTED_ENV}
          steps:
            - step:
                <<: *gizmoduck-full-code
                image: ubuntu:24.04
            - step:
                <<: *gizmoduck-endpoint-scan
                image: ubuntu:24.04
    {BB_WEEKLY}-bootstrap:
      - stage:
          name: gizmoduck tier 3 (trusted, inline bootstrap)
          deployment: {BB_TRUSTED_ENV}
          steps:
            - step:
                <<: *gizmoduck-sweep-code
                image: ubuntu:24.04
            - step:
                <<: *gizmoduck-sweep-endpoints
                image: ubuntu:24.04
"""


def render_all(cfg, platforms):
    check_image(cfg["image"])
    files = {}
    if "github" in platforms:
        files[PR_FILE] = github_pr(cfg)
        files[FULL_FILE] = github_full(cfg)
        files[ENDPOINTS_FILE] = github_endpoints(cfg)
    if "bitbucket" in platforms:
        files[cfg.get("bitbucket_out") or "bitbucket-pipelines.yml"] = bitbucket(cfg)
    return files

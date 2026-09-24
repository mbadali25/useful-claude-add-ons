# gizmoduck (Claude Code plugin)

**Gizmoduck** runs [Nuclei](https://github.com/projectdiscovery/nuclei) vulnerability
scans on websites and hosts, diffs them against previous scans, and turns findings
into triaged reports (Markdown + HTML + PDF) and ServiceDesk Plus tickets. Runs on
**WSL/Linux and Windows**.

Nuclei is MIT-licensed and self-hosted, so the CLI runs scans end-to-end — no export
step, no API restrictions. **Only scan assets you own or have written permission to test.**

## Commands
| Command | Does |
|---|---|
| `/gizmoduck:scan <target> [sev]` | Scan → report (md/html/pdf) → confirm batch → ticket Crit+High |
| `/gizmoduck:report <findings.jsonl> [sev]` | Rebuild a report from findings (no rescan) |
| `/gizmoduck:tickets <findings.jsonl> [sev]` | Confirm batch → open/sync SDP tickets from findings |
| `/gizmoduck:diff <old.jsonl> <new.jsonl> [sev]` | What's new since a previous scan |
| `/gizmoduck:update` | Update the Nuclei engine + templates |
| `/gizmoduck:doctor` | Check the toolchain (nuclei, templates, python, PDF) |
| `/gizmoduck:ci <github\|bitbucket\|both> <staging-url> [repo]` | Install CI security-scan pipelines into a repo (dry run first) |

## Install Nuclei (once)
**WSL / Linux:** `./bootstrap.sh`
**Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1`

Both fetch the latest prebuilt binary and community templates. PDF reports need
`wkhtmltopdf` (installed by bootstrap.sh; `winget install wkhtmltopdf` on Windows).

If your antivirus/EDR quarantines or deletes nikto, sqlmap, ZAP, or a Nuclei
template mid-install, see [`docs/antivirus-exclusions.md`](docs/antivirus-exclusions.md) - that's expected, not a broken install.

## Dependency-Check: NVD API key (optional)

dependency-check's first run downloads the entire NVD CVE corpus. Without an API
key, NIST rate-limits that sync to ~5 requests/30s — on a fresh machine, that
first run can take the better part of an hour with no progress output, which
looks like a hang but isn't. An API key raises the limit to ~50/30s, roughly 10x.

Get a free key at https://nvd.nist.gov/developers/request-an-api-key (just an
email + organization, no cost). NIST emails an **activation link**, not the key
itself — open that link; the key is shown on the page behind it.

Set it as an environment variable before scanning:
```bash
export NVD_API_KEY=<your key>          # Linux/WSL
$env:NVD_API_KEY = '<your key>'        # Windows PowerShell
```
It's optional — dependency-check runs fine without it, just slower on the first
sync. `bootstrap.sh`/`bootstrap.ps1` print this same reminder after installing
dependency-check; `/gizmoduck:doctor` reports whether the variable is set (never
the value itself), and an unset key is reported as a gap, not a failure.

## Layout
```
gizmoduck/
├── .claude-plugin/plugin.json
├── bootstrap.sh / bootstrap.ps1   # installers (Linux/WSL, Windows)
├── scripts/gizmoduck.py           # scan / report / tickets / diff / doctor / update
├── scripts/gizmoduck_ci.py        # /gizmoduck:ci - render pipelines, run their steps
├── scripts/ci_detect.py           # endpoint + staging-URL autodetection, setup decisions
├── scripts/ci_guard.py            # prod-refusal guard for endpoint scans
├── scripts/ci_gate.py             # fail only on new Critical/High
├── scripts/ci_render.py           # GitHub Actions / Bitbucket Pipelines templates
├── ci/Dockerfile                  # CI runner image (bootstrap.sh baked in)
├── scripts/report_template.py     # HTML+PDF rendering (read its docstring before
│                                  # editing the CSS - wkhtmltopdf is Qt WebKit 4.8)
├── skills/gizmoduck/SKILL.md
├── commands/                      # scan, report, tickets, diff, update, doctor, ci
└── README.md
```

## What the report shows

Critical, High and Medium findings are itemised in full. Low and Info are counted in
the severity table and then dropped: a signature scanner's low/info output is inventory
(version banners, DNS records, "a form exists"), and listing it buries the findings
somebody is expected to fix. The report states how many it suppressed, so nothing is
silently missing, and the complete detail stays in the JSONL.

`--min-severity` raises that floor but never lowers it.

## Ticketing is gated

`tickets` files REAL ServiceDesk Plus tickets, so it is confirmed by default whenever there
is anything to confirm. Without `--yes`, `gizmoduck.py tickets` prints the candidate list
(severity + subject), a digest over that exact batch, and the rerun command carrying it, then
exits 3 without emitting the JSON records a ticketing step would act on. Pass `--yes
<digest>` only after the whole batch has been shown to the user and approved — one
confirmation for the batch, not one per ticket — and only the digest the preview just printed:
a stale or mismatched one (a different findings file, a different `--min-severity`, findings
that changed in between) is refused with `GIZMODUCK_APPROVAL_MISMATCH` rather than silently
creating whatever the current batch turns out to be. Zero qualifying findings has nothing to
confirm: it prints `[]` and exits 0 either way, `--yes` or not.

## CI pipelines

`/gizmoduck:ci` installs three GitHub workflows (`gizmoduck-pr.yml`, `gizmoduck-full.yml`,
`gizmoduck-endpoints.yml`, `gizmoduck-inventory.yml`) or one `bitbucket-pipelines.yml`, split into
trigger tiers:

### Quick start

`/gizmoduck:ci` (interactive) or `gizmoduck_ci.py` directly, all in the target repo:

1. `gizmoduck_ci.py detect --repo .` - reads the repository only, writes nothing. Prints every
   endpoint/staging finding with its `path:line` and confidence, then a `**Decision needed:**`
   block per question it could not settle (staging URL, auth for protected endpoints, scope,
   which confidence to accept). `--detect` on the slash command re-runs just this step.
2. Answer every `Decision needed:` block yourself; a URL detection found is a candidate, never a
   default it applies for you.
3. `gizmoduck_ci.py setup --repo . --staging-url <url|none> --auth <none|header|exclude-protected>
   --accept <high|medium|low> (--scope all | --include GLOB ... --exclude GLOB ...)` - dry run by
   default (prints `gizmoduck-ci.json` and, with crew present, the `.crew/endpoints.json` records
   it would append). Add `--apply` only once you've reviewed that output; it is the only path that
   writes declared ledger records.
4. `gizmoduck_ci.py render --platform github|bitbucket|both --staging-url <url> --repo . \
   --authorized-by "<who authorised scanning staging>"` - dry run by default, prints every
   rendered file. An existing file is refused unless you pass `--force`; `--apply` writes.
5. `gizmoduck_ci.py inventory --repo . --stdout` to review `endpoints-inventory.md` before
   committing it, then run it again without `--stdout` so the file exists before `check` runs on
   the default branch.

| Tier | Trigger | Runs | Blocks |
|---|---|---|---|
| 1 light PR check | every non-draft PR not covered by tier 2; a docs-only PR passes its `gate` with "no scannable changes" (merge-base diff, not a path filter) | Semgrep diff-aware on the changed files; Trivy only if a lockfile/manifest changed; Checkov only if a `*.tf` changed; gitleaks over the PR's commits | a NEW Critical only; the rest goes to annotations + SARIF / Code Insights |
| 2 targeted full | PRs into the default branch or `release/*`, or the `security-scan` PR label (GitHub); Bitbucket: the manual `custom: security-full` pipeline | all code scans (Semgrep, Trivy, Checkov, gitleaks), plus Nuclei, ZAP baseline and testssl against staging after the staging deploy | a new Critical/High. No branch-name or path triggers |
| 3 weekly sweep | GitHub `schedule`, Sunday 23:00 UTC; Bitbucket a scheduled `custom: security-weekly` (one-time UI setup: Repository settings -> Pipelines -> Schedules) | everything, Dependency-Check with NVD included, against the default branch and staging; the weekly Nuclei template update | never; saves results as the next baseline, diffs against the last run, optional tickets |
| Manual | `workflow_dispatch` (any ref, or any base URL the prod-refusal guard allows); the Bitbucket custom pipelines | a full scan | per the tier-2 rule |

Controls: draft PRs are skipped; each workflow has a `concurrency` group per event and ref with
cancel-in-progress; the Trivy DB, NVD data and Nuclei templates are cached per ISO week, keyed by
trust level so a pull request's cache never reaches a trusted run; endpoint scans never run on a
pull request. The gate fails closed: no baseline (unless `GIZMODUCK_ALLOW_NO_BASELINE=true` for a
first run), a run manifest with no cells or any tool that did not run, an unknown severity in
either file, and duplicate findings judged at their highest severity.

Trust: pull-request jobs hold no write-capable secret or token; only a separate SARIF-upload job has
`security-events: write`. Require each PR workflow's always-running `gate` job in branch
protection - it decides from the event, so a later skipped run cannot stand in for a failed scan.
The endpoint workflow scans after a deploy only for the default branch or `release/*` of this
repository, and after `deployment_status` only once a secret-free `trust` job has confirmed the
deployed SHA is an ancestor of that branch's head - a ref name alone is not trusted; baselines come
only from trusted default-branch runs. On Bitbucket, every secret (`GIZMODUCK_BB_TOKEN`, `SDP_*`,
`NVD_API_KEY`, `GIZMODUCK_AUTH_HEADER_VALUE`) is a deployment variable of a `gizmoduck-trusted`
deployment environment used only by the custom pipelines; the PR step, and a custom run on any
branch other than the default branch or `release/*`, refuses to run if it can see one. The PR step
reads baselines and draft state with a read-only `GIZMODUCK_BB_READ_TOKEN` (without it,
as on a fork's PR, the check fails rather than scanning blind). Every endpoint scanner runs with
redirects disabled or scoped to the target origin, and the stage fails if any recorded request left
it; URLs with credentials are refused by the guard and redacted in every log and artifact.

### Repository variables and secrets

Everything below is read at runtime from the environment (`ci_guard.py`, `ci_gate.py`); the
staging URL, `--authorized-by`, `--enable` and the image reference are baked into the rendered
files at `render` time instead and are not repository settings.

**GitHub** (repository variable unless marked *secret*; Settings -> Secrets and variables -> Actions):

| Name | Required? | Visible to | If absent |
|---|---|---|---|
| `GIZMODUCK_RUNNER` | optional (`bootstrap` to disable the runner image) | every scan job (chooses which of the two duplicate jobs runs) | the runner-image job runs |
| `GIZMODUCK_ALLOWED_PROD_ORIGINS` | optional | endpoint-scan jobs only | every origin on it stays refused (R8) |
| `GIZMODUCK_ALLOW_PROD_SCAN` | optional (`true`) | endpoint-scan jobs only | production origins refused even if allow-listed (both are required together) |
| `GIZMODUCK_ALLOWED_IP_ORIGINS` | optional | endpoint-scan jobs only | an IP-literal or `localhost` origin is refused (R6) |
| `GIZMODUCK_ALLOW_NO_BASELINE` | optional (`true`) | the `gate` step, every workflow | a missing baseline fails the gate closed - set this for the first run only |
| `GIZMODUCK_ALLOW_INCOMPLETE` | optional (`true`) | the `gate` step | any tool that did not run (no coverage cell, or a status other than `ran`/`skipped-active`) fails the gate closed |
| `GIZMODUCK_TRUST_ASSIGNED_SEVERITY` | optional (`true`) | the `gate` step | a finding the tool gave no severity to (adapter-assigned) is treated as unknown severity and fails closed |
| `GIZMODUCK_SDP_TICKETS` | optional (`true`) | the tickets step, non-PR runs only | no tickets are opened (default off) |
| `SDP_AUTH_HEADER` | optional | the tickets step | defaults to `authtoken` |
| `GIZMODUCK_AUTH_HEADER_VALUE` *(secret)* | required only when `gizmoduck-ci.json` sets `auth: "header"` | endpoint-scan job only | protected endpoints are refused rather than scanned anonymously - `endpoint-stage` exits 2 |
| `NVD_API_KEY` *(secret)* | optional | the weekly sweep only (Dependency-Check) | NVD sync runs unauthenticated (much slower first sync; see "Dependency-Check" above) |
| `SDP_BASE_URL`, `SDP_API_KEY` *(secrets)* | required together to ticket | the tickets step, non-PR runs only | "SDP_BASE_URL / SDP_API_KEY secrets are not present - no tickets" |

`GITHUB_TOKEN` (`github.token`) needs no setup: read-only for the baseline-run lookup and the
SARIF upload, `contents: write` only inside the two self-commit jobs. See "Known limitation: the
self-commit's tip has no `gate` run" below for what using it as-is costs you.

**Bitbucket.** Every secret lives on the `gizmoduck-trusted` **deployment environment**
(Repository settings -> Deployments), never as a repository variable - the PR step and any custom
run on an untrusted branch refuse outright if one is visible to them:

| Name | Required? | If absent |
|---|---|---|
| `GIZMODUCK_BB_TOKEN` *(secured)* | required to upload the next baseline | "baseline upload failed - the next run compares against the previous baseline" |
| `SDP_BASE_URL`, `SDP_API_KEY` *(secured)* | required together to ticket | no ticket step runs |
| `NVD_API_KEY` *(secured)* | optional | weekly sweep syncs NVD unauthenticated |
| `GIZMODUCK_AUTH_HEADER_VALUE` *(secured)* | required only when `gizmoduck-ci.json` sets `auth: "header"` | protected endpoints refused, not scanned anonymously |

Repository variables (Repository settings -> Variables), read by both the PR step and trusted runs:

| Name | Required? | If absent |
|---|---|---|
| `GIZMODUCK_BB_READ_TOKEN` *(secured)* | required for the PR step (baselines, draft state) | the PR check fails rather than scanning blind |
| `GIZMODUCK_ALLOWED_PROD_ORIGINS`, `GIZMODUCK_ALLOW_PROD_SCAN`, `GIZMODUCK_ALLOWED_IP_ORIGINS` | optional | same guard defaults as GitHub, above |
| `GIZMODUCK_ALLOW_NO_BASELINE`, `GIZMODUCK_ALLOW_INCOMPLETE`, `GIZMODUCK_TRUST_ASSIGNED_SEVERITY` | optional | same gate defaults as GitHub, above |
| `GIZMODUCK_SDP_TICKETS`, `SDP_AUTH_HEADER` | optional | no tickets |
| `GIZMODUCK_REPORT_DOWNLOADS` (`true`) | optional | the weekly sweep's report stays only in run artifacts |
| `GIZMODUCK_RESULTS_BRANCH` | optional | the weekly sweep's report is not committed anywhere (never the default branch or `release/*` either way) |

### The prod-refusal guard

Every endpoint target is normalised and checked twice - once at `render` time against the
staging/production URLs you passed, and again at runtime, before any scanner starts
(`ci_guard.py`):

- the URL is lower-cased, IDNA-encoded, trailing dots stripped, and the port made explicit, so two
  spellings of one origin always compare equal;
- any whitespace (ASCII or Unicode), control/format character or backslash anywhere in the URL is
  **refused, never stripped** - a parser and a scanner disagreeing about where the host ends is
  how a lookalike gets through;
- userinfo (`user@`, `user:pass@`) and any query parameter whose name looks like it carries a
  credential (token, key, secret, password, signature, ...) are refused outright, not just
  redacted - a scan target is logged and uploaded as an artifact;
- an IP literal (any form Python's `inet_aton`/`ipaddress` accepts, IPv6 included) or `localhost`
  is refused unless its exact origin is on `GIZMODUCK_ALLOWED_IP_ORIGINS`, even if it is also a
  configured staging origin;
- the origin must equal a configured staging origin **exactly** - not a suffix or prefix match, so
  `staging.example.com.evil.test` is refused;
- an origin on the production allow-list (`GIZMODUCK_ALLOWED_PROD_ORIGINS`) is scanned only when
  `GIZMODUCK_ALLOW_PROD_SCAN=true` is *also* set - either alone refuses, and an origin listed as
  both staging and production is treated as production;
- every redacted URL - in logs, `targets.json`, findings and reports - masks userinfo as `***@`
  and a credential-named query value as `***`, judged after percent-decoding so an encoded `=` or
  a nested URL/query does not slip a credential through half-redacted.

That is a pre-check; a server can answer it differently than it answers a scanner. The actual
control is per scanner (`gizmoduck_ci.endpoint_manifest`): Nuclei runs with `-dr`
(disable-redirects), ZAP's scope is the target origin only (anchored, regex-escaped), testssl and
nmap have no redirect-follow option enabled, nikto needs `-followredirects` to leave the target
and never gets it, and sqlmap runs with `--ignore-redirects`. After the scan, `audit_findings`
re-checks the origin of every URL a scanner actually recorded and fails the endpoint stage if any
left the policy - a redirect a probe missed still fails the run, not just a warning.

### Baselines and the gate

The gate (`ci_gate.py`) fails only on a **new** Critical (tier 1) or new Critical/High (tier 2,
manual) finding, identified the same way `gizmoduck.py diff` does, so the gate and the published
`diff.md` never disagree about what counts as new.

- **First baseline.** There is none until a run produces one, so the very first tier-2/weekly run
  on a repository has nothing to diff against. Set `GIZMODUCK_ALLOW_NO_BASELINE=true` for that
  run; it is accepted and its findings become the baseline. Leave it unset afterward - a
  permanently-missing baseline would otherwise silently pass every scan.
- **Trusted-branch-only baselines.** A baseline can only come from a successful, non-pull-request
  run of the same workflow on the default branch (or `release/*`) of *this* repository -
  `gizmoduck_ci.previous_run_id` on GitHub, the Bitbucket Downloads upload gated the same way in
  `_bb_tail`. A pull request's own scan can never become the next baseline.
- **What fails closed, and its override:**
  | Case | Fails unless | Variable |
  |---|---|---|
  | No baseline found | first-run opt-in | `GIZMODUCK_ALLOW_NO_BASELINE=true` |
  | A baseline record has an unknown severity | never - always fails; an unreadable baseline entry could hide a new Critical/High under the same identity | none |
  | A current finding's severity cannot be read | never - always fails when it is new | none |
  | The tool gave no severity and the adapter assigned one (`severity-assigned` tag) | trust the assigned value | `GIZMODUCK_TRUST_ASSIGNED_SEVERITY=true` |
  | A scanner did not run (no coverage cell, or any manifest status other than `ran`/`skipped-active`) | incomplete-coverage opt-in | `GIZMODUCK_ALLOW_INCOMPLETE=true` |

  The tier-3 weekly sweep computes every one of these the same way but never blocks (`block_at:
  never`); it records, diffs and optionally tickets instead.

### Endpoints are detected, then confirmed

`gizmoduck_ci.py detect` reads `.crew/endpoints.json`,
OpenAPI/Swagger documents (including build output under `obj/`), ASP.NET controllers and
minimal-API `Map*` calls, Angular routes, FastAPI, Flask and Express. It looks for a staging URL
in appsettings and environment files, `.env.example`-style templates, Terraform outputs, GitHub
environments and Bitbucket deployments. Each finding has a `path:line` and a confidence. Whatever
it cannot settle is asked as a `**Decision needed:**` question: the staging URL, auth for
protected endpoints, the scope. It never guesses a URL. `setup --apply` writes the answers to a
committed `gizmoduck-ci.json`. When crew is present the endpoints go to `.crew/endpoints.json` as
declared records instead. Each endpoint run re-detects cheaply and can fetch the live OpenAPI
document through the guard. It scans what it finds, reports anything uncommitted as
"new, confirm at next setup", and fails UNVERIFIED ("run /gizmoduck:ci --detect") when there are
no endpoints, so an empty scan never passes.

**Monorepo inventory.** `gizmoduck_ci.py inventory` writes `endpoints-inventory.md` at the
repository root: one table per module (endpoint | source | staging URL). A module is a directory
holding a `public-endpoint.md` declaration or a project marker (`*.csproj`, `package.json`,
`pyproject.toml`, `main.tf`, `go.mod`, ...); the outermost one wins, `docs/` is excluded, and roots,
excludes and the file name are configurable (`--root`, `--exclude`, `--output`, or an `inventory`
block in `gizmoduck-ci.json`). A declared module is taken from its declaration's frontmatter
(`name`, `url`, `status`, `kind`, `additional_endpoints`, optional `staging_url`) and nothing is
detected there; any other module is autodetected, each row with its confidence and source file. A
staging URL that cannot be read from the repository is `undetermined`, never guessed. The file is a
pure function of the repository - no dates, stable order, credentials redacted - so
`gizmoduck_ci.py check` can fail when it is stale and print the command that regenerates it.

**Scan report.** After every endpoint scan, `gizmoduck_ci.py scan-report` writes
`security-scan-report.md`: Critical/High/Medium and new-since-baseline counts per module and
endpoint, UNVERIFIED where nothing scanned an endpoint, the scan date and commit, and a link to the
run's HTML/PDF artifacts. Counts only - no finding bodies.

**Publishing - branches only.** The generated files are committed on the branch a run was for and
never on the default branch, which only verifies (`check`). Self-commits carry `[skip ci]` and a
`[gizmoduck-self-commit]` mark; a regeneration that matches commits nothing, and one that still
differs on top of a self-commit refuses instead of looping. No publishing step holds a secret.

| | GitHub | Bitbucket |
|---|---|---|
| `endpoints-inventory.md` | `gizmoduck-inventory.yml`: push to a non-default branch regenerates and commits it (the only job with `contents: write`, guarded by `if:` and again at runtime); push to the default branch runs `check`; a PR gets a sticky comment saying whether it is current | `default:` step regenerates and commits on the branch - `default:`, not `pull-requests:`, whose pre-run merge would be pushed and can die on conflicts; `branches: <default>` runs `check` only |
| `security-scan-report.md` | the endpoint workflow's `publish-report` job commits it on a non-default branch (`contents: write`, no secret); on the default branch and for the weekly sweep it stays an artifact and the step summary | `custom: security-full` commits it from a step after the trusted stage (no deployment variables); the weekly sweep keeps it in artifacts, optionally uploads it to Downloads (`GIZMODUCK_REPORT_DOWNLOADS=true`) or commits it to a results branch (`GIZMODUCK_RESULTS_BRANCH`, never the default branch or `release/*`) |

### Known limitation: the self-commit's tip has no `gate` run

A self-commit's tip has no build of its own: `[skip ci]` on Bitbucket, and on GitHub the built-in
`GITHUB_TOKEN` a workflow pushes with does not trigger further workflow runs (this is GitHub's
own limitation, not gizmoduck's). So after `gizmoduck-inventory.yml`'s `publish` job commits the
regenerated `endpoints-inventory.md` onto a pull request's branch, that new tip commit never gets
a `gate` run, and a branch-protection rule requiring `gate` blocks the merge on a commit CI will
never check. **The rendered template's default is none of the options below** - it commits with
the plain `github.token` on every branch push, including a PR's, so this limitation is live out of
the box. Pick one:

- **(a) Use a GitHub App installation token or a fine-grained PAT for the self-commit instead of
  `github.token`.** A push made with a real user/app identity does trigger workflows. Scope it to
  `contents: write` on this repository only, and restrict it (App installation, or the PAT's
  fine-grained repo permissions) to non-default branches - it must never be able to push to the
  default branch. Store it as a secret and change `_gh_git_auth`'s `GH_TOKEN` env in
  `gizmoduck-inventory.yml` (and `gizmoduck-endpoints.yml`'s `publish-report` job) to read it,
  then re-render.
- **(b) Make the inventory job check-only on pull requests.** Drop the `publish` job's PR-branch
  commit behaviour and let it fail with the regenerate hint instead (`gizmoduck_ci.py check`
  already prints the exact command); the developer runs it locally and commits the result
  themselves, so the commit that needs a `gate` run is the developer's, which triggers normally.
- **(c) Don't require `gate` on the self-commit's own tip.** If your branch protection allows "the
  most recent applicable run" rather than "the tip commit exactly", a stale-but-passing `gate` from
  the commit before the self-commit is enough. This is a branch-protection setting in GitHub's UI,
  not something `/gizmoduck:ci` can render for you.

Whichever you pick, `gizmoduck_ci.py check` (or its Bitbucket `default:` step) always prints the
regenerate command as a fallback, so a stuck PR is never a dead end.

### Runner image

The scan jobs try the runner image first and fall back to installing every tool inline
(`bootstrap.sh`) only when it is unavailable - set `GIZMODUCK_RUNNER=bootstrap` (GitHub repository
variable) or run the `*-bootstrap` custom pipelines (Bitbucket) to skip the image path entirely.
Building one is optional but much faster (`ci/Dockerfile` bakes in every scanner `bootstrap.sh`
installs, so a run does not reinstall nine tools and the Nuclei template feed on every job):

```bash
cd plugin/gizmoduck
# Pin the base by digest, never by tag - a tag is a mutable pointer:
digest="$(docker buildx imagetools inspect ubuntu:24.04 --format '{{json .Manifest.Digest}}' | tr -d '"')"
# or: digest="$(crane digest ubuntu:24.04)"
docker build --build-arg GIZMODUCK_BASE_DIGEST="$digest" -f ci/Dockerfile \
  -t ghcr.io/<owner>/gizmoduck-ci:<version> .
echo "$GHCR_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
docker push ghcr.io/<owner>/gizmoduck-ci:<version>
```

`<version>` is the plugin version in `.claude-plugin/plugin.json`; push one tag per release and
never move it - the rendered pipelines reference exactly that tag (`gizmoduck_ci.py render
--image`). Docker Hub works the same way (`docker.io/<user>/gizmoduck-ci:<version>`); a private
image needs registry credentials on the runner (GitHub: `jobs.<id>.container.credentials`;
Bitbucket: `image.username`/`password`). The build fails without `GIZMODUCK_BASE_DIGEST` or with
anything but a `sha256:` digest, and its last step runs `gizmoduck_ci.py image-check` - `doctor`
plus every scanner adapter reporting itself runnable - so an image missing a tool fails the build
instead of shipping a scan that silently records that tool as skipped-missing.

Optional NVD pre-sync (Dependency-Check's first run otherwise downloads the whole NVD corpus,
which can exceed the weekly sweep's timeout on a cold image):

```bash
docker build --build-arg GIZMODUCK_NVD_PRESYNC=1 --secret id=nvd_api_key,env=NVD_API_KEY \
  -f ci/Dockerfile -t ghcr.io/<owner>/gizmoduck-ci:<version> .
```

The key is mounted for that one build step only and is never written to a layer.

### ServiceDesk Plus tickets

Opt-in and off by default: set the `GIZMODUCK_SDP_TICKETS` repository variable to `true` *and*
supply `SDP_BASE_URL`/`SDP_API_KEY` (Bitbucket: as `gizmoduck-trusted` deployment variables), or
nothing is ticketed. A ticket step never runs on a pull request. It drives `gizmoduck.py tickets`
exactly like an attended session: preview first, then rerun with `--yes <digest>` read back from
that same preview - never a digest computed independently - so what gets filed is exactly the
batch that was shown. `SdpClient` searches for an open request tagged `[Nuclei <template-id>]`
and adds a note to it rather than opening a duplicate.

### Pinning `--gizmoduck-ref`

`--gizmoduck-ref` defaults to `main` (unpinned): every pipeline run fetches gizmoduck's scripts
(and the inline-bootstrap fallback, and `bootstrap.sh` for the runner-image build) from whatever
that ref currently points at. `render` prints a warning when the value is not a 40-character commit
SHA, precisely because `main` can change under a pipeline between two runs with no diff in this
repository to explain it. Pin it to a commit SHA for anything beyond local experimentation; the
runner image's tag is already pinned (a version string), but this ref is not, unless you set it.

### Bitbucket one-time setup

Two things the pipeline file cannot declare for you, done once in the Bitbucket UI:

1. **The weekly sweep's schedule** (a `custom:` pipeline is never triggered by a `schedule:` key
   the way GitHub Actions is): Repository settings -> Pipelines -> Schedules -> New schedule,
   Branch: the default branch, Pipeline: `custom: security-weekly`, Interval: weekly (the render
   comment header gives Sunday 23:00 UTC to match the GitHub cron).
2. **The `gizmoduck-trusted` deployment environment**: Repository settings -> Deployments -> add an
   environment named `gizmoduck-trusted`, then add every secret in the table above to it as a
   **deployment variable** - never a repository variable, since only the custom pipelines' trusted
   stages read a deployment environment's variables, and the PR step and untrusted branches refuse
   to run at all if one of those names is visible to them as a repository variable instead.
   **Premium caveat:** restricting a deployment environment to specific branches (Repository
   settings -> Deployments -> Environment -> Restrict branches) requires a Premium plan. Without
   it, anyone who can edit `bitbucket-pipelines.yml` on a branch and trigger a custom pipeline on
   it can reach the `gizmoduck-trusted` variables from that branch - the environment scoping alone
   is not a substitute for branch permissions on who may edit the pipeline file.

## Manual CLI (Linux: `python3`, Windows: `python`)
```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --out report.pdf
python3 scripts/gizmoduck.py doctor
```

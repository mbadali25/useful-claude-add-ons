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
`gizmoduck-endpoints.yml`) or one `bitbucket-pipelines.yml`, split into trigger tiers:

| Tier | Trigger | Runs | Blocks |
|---|---|---|---|
| 1 light PR check | non-draft PRs, path-filtered (docs-only changes skipped), not covered by tier 2 | Semgrep diff-aware on the changed files; Trivy only if a lockfile/manifest changed; Checkov only if a `*.tf` changed; gitleaks over the PR's commits | a NEW Critical only; the rest goes to annotations + SARIF / Code Insights |
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
repository; baselines come only from trusted default-branch runs. On Bitbucket, the write-capable
secrets (`GIZMODUCK_BB_TOKEN`, `SDP_*`) are deployment variables of a `gizmoduck-trusted`
deployment environment used only by the custom pipelines; the PR step refuses to run if it can see
one, and reads baselines and draft state with a read-only `GIZMODUCK_BB_READ_TOKEN` (without it,
as on a fork's PR, the check fails rather than scanning blind). Every endpoint scanner runs with
redirects disabled or scoped to the target origin, and the stage fails if any recorded request left
it; URLs with credentials are refused by the guard and redacted in every log and artifact.

**Endpoints are detected, then confirmed.** `gizmoduck_ci.py detect` reads `.crew/endpoints.json`,
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

TODO: the rest of the CI guide (docs lane) - runner image build/push, repository variables and secrets, baseline bootstrap, the prod-refusal guard, SDP ticketing.

## Manual CLI (Linux: `python3`, Windows: `python`)
```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --out report.pdf
python3 scripts/gizmoduck.py doctor
```

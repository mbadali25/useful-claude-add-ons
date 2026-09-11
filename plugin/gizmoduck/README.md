# gizmoduck (Claude Code plugin)

**Gizmoduck** runs a suite of vulnerability scanners against websites, hosts and their
source trees, diffs results against previous scans, and turns findings into triaged
reports (Markdown + HTML + PDF) and ServiceDesk Plus tickets. Runs on **WSL/Linux and
Windows**.

Every tool is open-source and self-hosted, so the CLI runs scans end-to-end — no export
step, no API restrictions. **Only scan assets you own or have written permission to test.**

## What a scan actually runs

Five tools by default. Each adapter normalises its output into Nuclei's record shape, so
everything merges into **one findings file and one report** at the shared
Medium-and-above detail floor.

| Tool | Covers | Needs |
|---|---|---|
| [nuclei](https://github.com/projectdiscovery/nuclei) | known issues by template, against the live endpoint | the target |
| [sslyze](https://github.com/nabla-c0d3/sslyze) | TLS protocol, cipher and certificate posture | the target |
| [trivy](https://github.com/aquasecurity/trivy) `fs` | dependency CVEs, committed secrets | `--source` |
| trivy `config` | Terraform / IaC misconfiguration | `--source` |
| [semgrep](https://semgrep.dev) | source analysis — the only tool here that sees a *missing* authorization check | `--source` |

Opt-in: `--with-zap` (OWASP ZAP, crawler-driven DAST — minutes per target) and
`--with-checkov` (more IaC checks, but Checkov OSS emits no severity, so its findings are
floored at Low and stay out of a Medium-and-above report).

**Nuclei alone is not enough, and the gap is large.** Pointed at authenticated apps behind
a WAF, a real sweep of 18 endpoints returned 294 findings — every one Info-severity
fingerprinting. Running the full suite against one of those same modules produced 4 High
and 7 Medium, including live dependency CVEs with fixed versions available. A quiet Nuclei
report on an authenticated app is the expected result, not evidence of a secure
application.

Pass `--source <dir>` whenever the tree is available. Without it the three source tools
report as `skipped` — never silently omitted, because four quiet zero-finding tools beside
one clean Nuclei run would read as a clean bill of health.

## Commands
| Command | Does |
|---|---|
| `/gizmoduck:scan <target> [sev]` | Scan → report (md/html/pdf) → confirm batch → ticket Crit+High |
| `/gizmoduck:report <findings.jsonl> [sev]` | Rebuild a report from findings (no rescan) |
| `/gizmoduck:tickets <findings.jsonl> [sev]` | Confirm batch → open/sync SDP tickets from findings |
| `/gizmoduck:diff <old.jsonl> <new.jsonl> [sev]` | What's new since a previous scan |
| `/gizmoduck:update` | Update the Nuclei engine + templates |
| `/gizmoduck:doctor` | Check the whole toolchain, tool by tool |

## Install (once)
**WSL / Linux:** `./bootstrap.sh`
**Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1`

Both install the **entire suite** — nuclei plus community templates, trivy, sslyze,
semgrep, and wkhtmltopdf for PDF reports — then tell you which optional tools you can add.
Run `/gizmoduck:doctor` afterwards to confirm every tool resolved; it reports each one
separately, so a partial install cannot masquerade as a working one.

On Windows, winget installs `wkhtmltopdf` without putting it on PATH, which makes PDF
output vanish silently while HTML keeps working. The bootstrap adds that directory to the
user PATH.

## Layout
```
gizmoduck/
├── .claude-plugin/plugin.json
├── bootstrap.sh / bootstrap.ps1   # installers (Linux/WSL, Windows)
├── scripts/gizmoduck.py           # scan / report / tickets / diff / doctor / update
├── scripts/report_template.py     # HTML+PDF rendering (read its docstring before
│                                  # editing the CSS - wkhtmltopdf is Qt WebKit 4.8)
├── skills/gizmoduck/SKILL.md
├── commands/                      # scan, report, tickets, diff, update, doctor
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

## Manual CLI (Linux: `python3`, Windows: `python`)
```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --out report.pdf
python3 scripts/gizmoduck.py doctor
```

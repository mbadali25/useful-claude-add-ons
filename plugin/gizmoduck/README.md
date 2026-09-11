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

## Install Nuclei (once)
**WSL / Linux:** `./bootstrap.sh`
**Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1`

Both fetch the latest prebuilt binary and community templates. PDF reports need
`wkhtmltopdf` (installed by bootstrap.sh; `winget install wkhtmltopdf` on Windows).

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

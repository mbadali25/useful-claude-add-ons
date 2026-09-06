# gizmoduck (Claude Code plugin)

**Gizmoduck** runs [Nuclei](https://github.com/projectdiscovery/nuclei) vulnerability
scans on websites and hosts, diffs them against previous scans, and turns findings
into triaged reports (Markdown + HTML + PDF) and, once you confirm the previewed
list, ServiceDesk Plus tickets. Runs on
**WSL/Linux and Windows**.

Nuclei is MIT-licensed and self-hosted, so the CLI runs scans end-to-end — no export
step, no API restrictions. **Only scan assets you own or have written permission to test.**

## Commands
| Command | Does |
|---|---|
| `/gizmoduck:scan <target> [sev]` | Scan → report (md/html/pdf) → preview + confirm → ticket Crit+High |
| `/gizmoduck:report <findings.jsonl> [sev]` | Rebuild a report from findings (no rescan) |
| `/gizmoduck:tickets <findings.jsonl> [sev]` | Preview, then open/sync SDP tickets from findings |
| `/gizmoduck:diff <old.jsonl> <new.jsonl> [sev]` | What's new since a previous scan |
| `/gizmoduck:update` | Update the Nuclei engine + templates |
| `/gizmoduck:doctor` | Check the toolchain (nuclei, templates, python, PDF) |

## Install Nuclei (once)
**WSL / Linux:** `./bootstrap.sh`
**Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1`

Both fetch the latest prebuilt binary and community templates. PDF reports need
`wkhtmltopdf` (installed by bootstrap.sh; `winget install wkhtmltopdf` on Windows).

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

## Manual CLI (Linux: `python3`, Windows: `python`)
```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --out report.pdf
python3 scripts/gizmoduck.py doctor
```

## Ticket creation is opt-in

`gizmoduck.py tickets` returns a **preview** by default: each finding's subject,
severity and target count, and no `description`. Nothing in that output can be
filed, because the ticket body is never generated. `--create` generates the
bodies, and the shipped `/gizmoduck:scan` and `/gizmoduck:tickets` commands only
reach for it after showing the preview and getting an explicit yes.

The `[Nuclei <template-id>]` search that avoids duplicates is not the
confirmation. It picks between creating a request and adding a note to an open
one, and both of those write to ServiceDesk Plus.

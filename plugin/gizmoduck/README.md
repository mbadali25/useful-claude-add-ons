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
| `/gizmoduck:scan <target> [sev]` | Scan → report (md/html/pdf) → auto-ticket Crit+High |
| `/gizmoduck:report <findings.jsonl> [sev]` | Rebuild a report from findings (no rescan) |
| `/gizmoduck:tickets <findings.jsonl> [sev]` | Open/sync SDP tickets from findings |
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
├── skills/gizmoduck/SKILL.md
├── commands/                      # scan, report, tickets, diff, update, doctor
└── README.md
```

## Manual CLI (Linux: `python3`, Windows: `python`)
```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --min-severity high --out report.pdf
python3 scripts/gizmoduck.py doctor
```

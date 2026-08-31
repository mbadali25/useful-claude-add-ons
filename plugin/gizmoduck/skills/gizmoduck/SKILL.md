---
name: gizmoduck
description: >-
  Run a Nuclei vulnerability scan against a website, host, or list of targets,
  produce a triaged report, and auto-open ServiceDesk Plus tickets for the serious
  findings. Use whenever the user wants to scan a new site they deployed, check a
  host or their environment for vulnerabilities, mentions Nuclei, or points at a
  targets file or a Nuclei JSONL output. Works on WSL/Linux and Windows.
---

# Nuclei scan, report & triage

Nuclei is MIT-licensed and self-hosted, so this skill runs the scan end to end —
no export step. **Only scan assets the user owns or has explicit written permission
to test.** If the target looks like it isn't theirs, confirm authorization first.

Runs on Linux/WSL and Windows. On Linux call the CLI with `python3`; on Windows use
`python`. The path is `${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py`.

## Workflow

1. **Scan.** A target is a URL (`https://site`), a host/IP, or a file with one
   target per line. Filter to the severities that matter by default:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py scan <target|targets.txt> \
       --severity critical,high,medium --out findings.jsonl
   ```
   This writes JSONL and reports how many findings it captured. If `nuclei` isn't
   installed it will say so — run `bootstrap.sh` (Linux/WSL) or `bootstrap.ps1`
   (Windows) first.

2. **Summarize**, then lead with the counts:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py summary findings.jsonl
   ```

3. **Report.** Show Markdown inline, then write the file deliverables:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py report findings.jsonl --title "<target> scan <date>"
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py report findings.jsonl --format html --out <name>.html --title "..."
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py report findings.jsonl --format pdf  --out <name>.pdf  --title "..."
   ```
   **Reports itemise Critical, High and Medium only.** Low and Info are counted in
   the severity table and then dropped, because nobody works that queue - a
   signature scanner's low/info output is inventory (version banners, DNS records,
   "a form exists") and listing it buries what someone is expected to fix. The
   report says how many were suppressed, so the omission is visible rather than
   silent.

   `--min-severity` can **raise** that floor (`--min-severity high` reports High and
   Critical only) but never lower it. Passing `--min-severity info` gets you the
   counts it implies, not pages of noise.

   Findings are deduped across targets by `template-id` and numbered in severity
   order, so the number is the remediation order. PDF needs `wkhtmltopdf`; the tool
   falls back to HTML with a message if it's missing.

   Rendering lives in `scripts/report_template.py`, which gizmoduck.py delegates to.
   **Read its module docstring before touching the CSS** - wkhtmltopdf renders
   through Qt WebKit 4.8, which predates flexbox, grid and custom properties, and
   silently produces an unstyled column rather than an error. Verify any change in
   the PDF, not just a browser.

4. **Ticketing — one ticket per finding, auto-create Critical + High.** Get the
   SDP-ready records:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py tickets findings.jsonl --min-severity high
   ```
   Each record has a stable `[Nuclei <template-id>]` subject. For each, **before
   creating**, search ServiceDesk Plus for an existing **open** request whose
   subject contains that same tag:
   - exists → **add a note** updating the affected-target list;
   - none → **create** the request.

   This is auto-create — don't prompt per ticket. Do **not** reimplement ticketing;
   use the org `infra-work-ticketing` skill / the SDP tools. Print a created-vs-updated
   summary afterward. Medium/Low/Info never generate tickets.

## Notes
- Severity: critical/high/medium/low/info map to Critical…Info. Reports itemise
  Critical/High/Medium and count the rest; `summary`, `parse`, `diff` and
  `tickets` are unaffected and still honour `--min-severity` in full.
- Nuclei finds what a template exists for — it's a known-issue scanner, not a
  crawler-driven DAST. For custom app-logic flaws (auth journeys, business logic),
  note that a tool like OWASP ZAP is the right complement.
- Keep the template feed fresh: `nuclei -update-templates` before important scans.

## Other actions
These back the `/gizmoduck:*` commands; all use `gizmoduck.py`:
- **diff** — `gizmoduck.py diff <baseline.jsonl> <current.jsonl> --min-severity low`
  shows findings that are NEW since a previous scan (and which resolved). Use this
  as a deploy/regression check; offer to ticket new Critical/High items.
- **report** / **tickets** — regenerate a report or open tickets from an existing
  `findings.jsonl` without rescanning.
- **update** — `gizmoduck.py update` refreshes the Nuclei engine and templates.
- **doctor** — `gizmoduck.py doctor` verifies nuclei, templates, python, and
  wkhtmltopdf; if anything's missing, point the user at the bootstrap scripts.

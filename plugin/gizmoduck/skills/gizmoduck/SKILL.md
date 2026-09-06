---
name: gizmoduck
description: >-
  Run a Nuclei vulnerability scan against a website, host, or list of targets,
  produce a triaged report, and open ServiceDesk Plus tickets for the serious
  findings after one batch confirmation. Use whenever the user wants to scan a new site they deployed, check a
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

4. **Ticketing — one ticket per finding, one confirmation for the whole batch.**
   `tickets` files REAL ServiceDesk Plus tickets, so it is gated by default, and the
   rerun is bound to the exact batch the preview showed - a bare "yes" is not enough.
   First, get the preview (no `--yes`):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py tickets findings.jsonl --min-severity high
   ```
   Without `--yes` this prints the candidate list, a digest over that exact batch, and
   the rerun command carrying it, then exits 3 with `GIZMODUCK_CONFIRMATION_REQUIRED` —
   it does **not** emit the JSON records, so there is nothing yet that a ticketing step
   could act on. (Zero qualifying findings has nothing to confirm: it prints `[]` and
   exits 0 either way.) Each candidate has a stable `[Nuclei <template-id>]` subject.
   For each, search ServiceDesk Plus for an existing **open** request whose subject
   contains that same tag, to split the batch into:
   - exists → would **add a note** updating the affected-target list;
   - none → would **create** the request.

   Show the user the full batch in one message — severity + subject per line, plus
   the create-vs-update split — and get one explicit go-ahead for the whole batch.
   **Do not prompt per ticket**; that is unusable at N findings. Only after that
   go-ahead, run **the exact command the preview printed** — it already restates the
   identical `findings.jsonl` and `--min-severity`, plus `--yes` and the batch's
   digest, so there is nothing to retype and nothing to widen or narrow:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gizmoduck.py tickets findings.jsonl --min-severity high --yes <digest-from-the-preview>
   ```
   A `--yes` whose digest does not match what `tickets` recomputes right now — a
   different findings file, a different `--min-severity`, findings that changed in
   between — is refused with `GIZMODUCK_APPROVAL_MISMATCH`, never silently widened to
   whatever the current batch turns out to be. If the batch needs to change, get a
   fresh preview and a fresh digest, and confirm again — never edit the rerun's
   `--min-severity` or target file by hand.

   Act on the records — create or add-a-note per the split above. Do **not** reimplement
   ticketing; use the org `infra-work-ticketing` skill / the SDP tools. Print a
   created-vs-updated summary afterward. Medium/Low/Info never generate tickets.
   `--yes` is gated, not unattended-only: passing it *is* the documented attended
   flow, but only after the user has approved the exact batch shown in the preview
   — never pass it before that approval.

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

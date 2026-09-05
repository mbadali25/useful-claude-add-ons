# gizmoduck

anchor: useful-claude-add-ons@875c9c6f
verified: 2026-09-05

## Does

Runs Nuclei against a URL, host or targets file, then turns the JSONL output
into Markdown/HTML/PDF reports and ServiceDesk Plus tickets
(`plugin/gizmoduck/scripts/gizmoduck.py`, commands wired at
`plugin/gizmoduck/commands/scan.md:1-8`).

The scan/report/diff boundary is entirely inside `gizmoduck.py` (`cmd_scan`,
`cmd_report`, `cmd_diff`). **Ticket creation is not.** `cmd_tickets`
(`gizmoduck.py:289-306`) only emits JSON records; the actual SDP calls are
delegated to Claude following `skills/gizmoduck/SKILL.md:64-77`, which routes
through the org `infra-work-ticketing` skill and the SDP tools.

## Entry points

- `plugin/gizmoduck/scripts/gizmoduck.py` — the CLI: `cmd_scan` (`:55`),
  `cmd_report`, `cmd_diff`, `cmd_tickets` (`:289`).
- `plugin/gizmoduck/commands/` — `scan.md`, `report.md`, `tickets.md`,
  `diff.md`, `doctor.md`, `update.md`.
- `plugin/gizmoduck/skills/gizmoduck/SKILL.md` — the ticketing contract.

## Owns data

- Nuclei JSONL findings files and the generated report artifacts. A failed scan
  deliberately writes no findings file.
- No credentials. Grep of `gizmoduck.py` and `report_template.py` shows no
  `os.environ` or API-key handling anywhere in this plugin.

## Calls out to

- `nuclei`, as an external binary.
- ServiceDesk Plus, but only indirectly — via the SDP MCP tools that Claude
  invokes per `SKILL.md`, never from this plugin's own code.

## Landmines

- **Ticket creation is automatic, not gated per ticket.** `commands/scan.md:6-8`
  and `commands/tickets.md:5-7` both instruct auto-creating one SDP ticket per
  Critical/High finding and explicitly say not to prompt per ticket. De-dupe is
  by searching for an existing open `[Nuclei <template-id>]` subject first
  (`SKILL.md:68-77`). The default ticketing floor is `high` —
  `plugin/gizmoduck/scripts/gizmoduck.py:426`, `_FLOORS = {"report": "medium", "tickets": "high",
  "diff": "low"}`. A scan of a noisy target can therefore open real tickets in
  a real system without a per-item confirmation.
- **A failed scan intentionally writes no findings file**
  (`gizmoduck.py:68-80`), so a failure cannot be mistaken for a clean baseline.
  Stripping that check would silently turn errors into "no vulnerabilities".
- **Scanning is confined to what the user names.** `cmd_scan` (`:55-84`) builds
  only `-u <target>` or `-l <targets-file>` from the CLI argument; there is no
  discovery, expansion or crawling. Keep it that way — this plugin points a
  scanner at hosts.
- **It registers no hooks at all.** `plugin/gizmoduck/.claude-plugin/
  plugin.json` has no `hooks` field and there is no `hooks.json` under the
  plugin. So the marketplace's "a plugin registering hooks defaults to OFF"
  rule does not apply here, and nothing runs unasked. Adding a hook later would
  pull that rule in.

## Unverified

- Whether the `infra-work-ticketing` skill or the SDP MCP tools impose their own
  per-ticket confirmation gate. That skill's file was not read — file known,
  content unverified. This matters: it is the only thing that might sit between
  a Critical finding and a ticket.
- Where SDP credentials actually live. Not anywhere under `plugin/gizmoduck/`;
  presumably that skill's own config.

# Skill updates

New skills added under `skills/`, newest first. Each entry names when it landed,
so a reader can tell what their installed copy actually has. For fixes and
internal changes, see [`CHANGELOG.md`](../CHANGELOG.md); this file is only what is
newly *possible*.

Mirrored into [`skills/README.md`](README.md) and the root
[`README.md`](../README.md) by `scripts/sync-updates.py`. Edit here, then run it.

Skills bundled inside a plugin are listed in [`plugin/UPDATE.md`](../plugin/UPDATE.md)
instead — they install with their plugin, not on their own. `crew-house-style`
shipped in crew 0.15.1 and is recorded there.

## Unreleased

Nine new skills, taking the marketplace from 25 to 34.

- **`jira-manager`** — Jira Cloud over the REST API v3 with an email + API
  token, no MCP connector and no OAuth flow. JQL search, create, update fields,
  assign, transition, comment, log work. Sourcing the helper needs no
  credentials, so `jira_get_cloud_id` is usable during setup; each function
  that needs them checks at call time. Needs `curl` 7.76+ and `jq`.
- **`knowbe4-admin`** — KnowBe4 KSAT administration: diagnose SCIM user-sync
  against Microsoft Entra ID or Okta, pull Reporting API data, and route each
  change to the surface that actually owns it.
- **`power-automate-api`** — Power Automate cloud flows through the API instead
  of the maker portal. Flow definitions, expressions the designer mangles,
  trigger inputs, connection references, run history, and the Flow/BAP auth
  errors. Every write is preceded by a snapshot to
  `~/.pa-api-cache/snapshots` and by validation, both enforced in code.
- **`report-builder`** — human-facing reports authored as HTML and converted to
  `.docx`/`.pdf` by Word. The browser is not the target; Word's HTML parser is,
  and it drops correct CSS silently. Carries the five measured traps, a
  greyscale-safe palette, and a test that runs the checklist against an
  artifact the builder actually emitted.
- **`doc-builder`** — finished, human-facing documents as DOCX and PDF through
  Microsoft Word, in the installed brand pack's house style or a neutral one.
  Two pipelines behind one skill: findings-style reports (HTML through Word
  COM) and step-by-step procedures with screenshots (python-docx OOXML,
  because `add_picture()` writes neither the border nor the `effectExtent`
  Word needs to avoid clipping a screenshot border). Brand resolves
  automatically from any installed brand pack (for example
  `solomon-doc-builder`); `report-builder` and `solomon-sop-maker` are now
  deprecated stubs that redirect here.
- **`exchange-mailbox-cleanup`** — walks a non-technical operator, one step at
  a time, through the Exchange Online Mailbox Cleanup runbook for terminated
  users: applies a seven-year Litigation Hold, verifies the mail stays
  searchable, deletes the account, confirms the mailbox went inactive with the
  hold intact, and exports from Purview eDiscovery. The skill only prints
  commands for the operator's own Windows PowerShell 5.1 window; it never runs
  `Connect-ExchangeOnline` or any mutating cmdlet itself.
- **`exchange-mailbox-restore`** — the reverse walkthrough: triages what state
  a mailbox is really in, then takes exactly one of five paths — remove a
  Litigation Hold, restore an inactive mailbox's mail into a shared mailbox,
  recover an inactive mailbox for a returning employee, undelete an account
  inside the 30-day window, or remove the last hold for authorised permanent
  destruction. Same print-only contract as the cleanup skill; the destructive
  paths are gated by typed confirmations (`RECOVER 1`, `DESTROY 1`).
- **`solomon-doc-builder`** — a brand pack, not a builder: Solomon Associates'
  palette, fonts, footer, and SOP masters location for `doc-builder`. Contains
  no scripts; installing it alongside `doc-builder` applies Solomon styling to
  every document automatically from then on, with `--brand neutral` (or
  `DOC_BUILDER_BRAND=neutral`) as the always-wins off switch.
- **`solomon-sop-maker`** — deprecated 2026-09-10, split into `doc-builder`
  (the python-docx SOP pipeline, both conformance gates, the template spec,
  screenshot rules) and `solomon-doc-builder` (the Solomon brand values). A
  stub kept only so old references to the name still resolve; it contains no
  scripts and does nothing itself.

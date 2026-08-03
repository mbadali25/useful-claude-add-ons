# Skills

Each subdirectory here is a self-contained [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) — a `SKILL.md` plus any `references/`, `scripts/`, or `assets/` it needs. Claude auto-discovers a skill's `SKILL.md` frontmatter (`name` + `description`) and decides when to invoke it; you don't call these directly.

See [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md) for how a skill in this repo must be structured, and [`../Skill-Pipeline.md`](../Skill-Pipeline.md) for how a new or changed skill gets from a draft to something your team can install.

## Overview

| Skill | Category | What it does | Invocation |
|---|---|---|---|
| [`aws-opensearch`](aws-opensearch) | Cloud / Infra | Diagnose and remediate an Amazon OpenSearch Service managed domain over SigV4 — cluster health, unassigned shards, reindex, ISM/ILM, snapshots — with dry-run guards on destructive calls. | Automatic |
| [`bitbucket`](bitbucket) | SCM / DevOps | Git over HTTPS with Atlassian API tokens plus the Bitbucket Cloud REST API — PRs, pipelines, comments, branches. | Automatic |
| [`checkpoint-email`](checkpoint-email) | Security | Check Point Email Security (Harmony Email & Collaboration / Avanan) — search entities, triage phishing/malware/DLP/BEC, remediate with a dry-run gate. | Automatic |
| [`cisco-meraki`](cisco-meraki) | Cloud / Networking | Cisco Meraki Dashboard API v1 for a single org — inventory and device status, event and config-change logs, security/IDS events, Air Marshal, live diagnostics, and MX/MS/MR config changes gated behind snapshot → diff → confirm with rollback. | Automatic |
| [`claude-code-defaults`](claude-code-defaults) | Claude Code / Config | Configures how Claude Code itself behaves by default — `CLAUDE.md` instructions vs `settings.json` enforcement, permission allow/deny/ask rules and modes, hooks, default model, and which scope (user, project, local, managed) each belongs in. Inventories existing config and merges rather than clobbering. | Automatic |
| [`cloudflare`](cloudflare) | Cloud / Networking | Cloudflare v4 API — DNS, zones, cache purge, WAF/rulesets, page rules, SSL/TLS, Workers/KV/R2, Zero Trust, analytics. | Automatic |
| [`drata`](drata) | Compliance | Drata Public API — controls, monitoring tests, evidence, personnel, policies, frameworks, risks, vendors, assets across US/EU/APAC regions. | Automatic |
| [`i-have-adhd`](i-have-adhd) | Productivity | Reshapes Claude's output for ADHD-friendly reading — leads with the next action, numbers steps, suppresses tangents. Persists for the session once invoked. | Manual — `/i-have-adhd` |
| [`infra-work-ticketing`](infra-work-ticketing) | Ops / Ticketing | Makes sure infrastructure work gets a ticket and a work note in Zoho ServiceDesk Plus Cloud or Jira Cloud — asks whether a ticket exists, logs the work as it happens, opens one when there isn't. | Automatic |
| [`intune-graph`](intune-graph) | Endpoint Mgmt | Microsoft Intune via Microsoft Graph — device lookup/troubleshooting, compliance and configuration profiles, Win32/LOB app deployment, bulk report exports. | Automatic |
| [`mermaid-svg-bitbucket`](mermaid-svg-bitbucket) | Docs / DevOps | Pre-renders Mermaid diagrams to committed SVG so they display in Bitbucket Cloud, which never adopted native ```mermaid``` fences. | Automatic |
| [`repo-docs`](repo-docs) | Docs | Generates and refreshes a whole documentation set for a codebase — `CLAUDE.md`, root and per-directory READMEs, API/function reference, architecture doc, `TODO.md`, `SECURITY.md`, `CHANGELOG.md`, handoff notes — re-runnable without clobbering human edits. | Automatic |
| [`shipstation`](shipstation) | E-commerce / Logistics | ShipStation across its three APIs (V2, legacy V1, ShipEngine) — shipments, labels, rates, carriers, warehouses, inventory, products, orders, tracking, batches, manifests. | Automatic |
| [`sophos-central`](sophos-central) | Security | Sophos Central API — endpoint management (isolate, scan, tamper protection), alert triage, SIEM export, XDR/Live Discover, firewall management. | Automatic |
| [`terraform-docs-readme`](terraform-docs-readme) | IaC / Docs | Regenerates a Terraform module's `README.md` with `terraform-docs` — wires up `.terraform-docs.yml`, the `main.tf` header block, `footer.md`, and the `BEGIN_TF_DOCS`/`END_TF_DOCS` injection markers, and diagnoses why a variable, header, or footer isn't showing up. | Automatic |
| [`visio-diagrams`](visio-diagrams) | Docs / Diagrams | Generates native Visio `.vsdx` from a YAML/JSON spec with a stdlib-only writer (no Visio install, works in CI), or drives Visio over COM when real stencil masters, themes, or swimlanes are required — plus SVG preview, OPC verification, and reading/retitling an existing `.vsdx`. | Automatic |
| [`wazuh-onprem`](wazuh-onprem) | Security / SIEM | Self-hosted Wazuh across all four surfaces — Server API, Indexer API, Dashboard saved-objects API, and `ossec.conf` over SSH. | Automatic |
| [`web-testing-playwright`](web-testing-playwright) | Testing / QA | Drives a real browser with Playwright — screenshots at multiple viewports, console errors, failed network requests, form and login flows — plus browser setup for Windows and Linux. | Automatic |
| [`work-log-reporter`](work-log-reporter) | Productivity | Keeps a committed per-session `work-log/` of what was done and what was touched, then generates a formatted email report with a PDF attachment and sends it over SMTP. | Automatic |

"Automatic" means Claude decides to invoke the skill on its own when the conversation matches the skill's `description` trigger — no slash command needed. "Manual" means the skill sets `disable-model-invocation: true` and must be invoked explicitly (e.g. `/i-have-adhd`).

## Adding a new skill

1. Read [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md).
2. Create `skills/<skill-name>/SKILL.md` (kebab-case directory name matching the `name:` frontmatter field exactly).
3. Follow [`../Skill-Pipeline.md`](../Skill-Pipeline.md) to validate, review, and register the skill in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) so the team can install it.
4. Add a row to the table above.

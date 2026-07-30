# useful-claude-add-ons

An internal repository of [Claude Code](https://docs.claude.com/en/docs/claude-code) Skills, and eventually plugins, built for easy distribution to the team. It also doubles as a Claude Code **plugin marketplace** ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) — see [`MARKETPLACE.md`](MARKETPLACE.md) to add it and install skills directly.

## Quick Install

One-line bootstrap — no `git clone` needed. Pulls the prerequisite installer straight from GitHub and runs it. Review the script before running on a machine you don't fully control — see [`SECURITY.md`](SECURITY.md)'s install-script trust boundary.

**Windows** (elevated PowerShell):

```powershell
irm 'https://raw.githubusercontent.com/mbadali25/useful-claude-add-ons/8d0436410107c8880d18ee026b1fdbd3b56615fb/scripts/install-prerequisites.ps1' | iex
```

**Linux**:

```bash
curl -fsSL 'https://raw.githubusercontent.com/mbadali25/useful-claude-add-ons/8d0436410107c8880d18ee026b1fdbd3b56615fb/scripts/install-prerequisites.sh' | bash
```

Both links are pinned to a specific commit SHA rather than `main`, so the exact script you're running is fixed and auditable — it can't silently change between when you review it and when you run it. **Update the SHA above whenever `scripts/install-prerequisites.*` changes**: after merging to `main`, run `git rev-parse HEAD` and swap it into both URLs.

Prefer to clone and run locally instead? See [Get started](#get-started) below.

## Get started

New machine? Run the prerequisite installer for your OS, then install the skills you need:

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons

# Windows (elevated PowerShell)
.\scripts\install-prerequisites.ps1

# Linux
./scripts/install-prerequisites.sh
```

Both scripts are idempotent and **detect before they install** — an already-present Chocolatey package, marketplace, or plugin is reported and skipped rather than reinstalled. Re-running is cheap and safe. Each run ends with an `Installed / Updated / Already present` summary.

They prompt before the optional pieces (the `find-skills` skill, claude-mem, GSD, the VoltAgent subagent collection, the ClaudePluginHub set, and the AWS/Azure MCP servers), so you can take only what you want. Where something is already present, the prompt says so and offers a refresh instead of a fresh install.

| Switch (Windows / Linux) | Effect |
|---|---|
| `-NonInteractive` / `--non-interactive` | Accept the default answer for every prompt — for unattended or CI runs. |
| `-NoUpdate` / `--no-update` | Report already-installed plugins but never update them. |
| `-SkipBootstrap` / `--skip-bootstrap` | Skip all marketplace, plugin, and optional bootstrap steps. |
| `-PluginHubScope` / `--scope` | Scope for ClaudePluginHub installs: `user` (default here), `project`, or `local`. |

> On Windows, run from an **elevated** prompt for the full setup. Without elevation the script skips Chocolatey and its packages (git/awscli/nodejs/python) and does only the Claude Code CLI, marketplace, and plugin steps.

Full walkthrough, verification steps, and troubleshooting: [`INSTALLATION.md`](INSTALLATION.md).

## Add the marketplace & install skills

This repo is itself a Claude Code plugin marketplace ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) — every skill under [`skills/`](skills/) is an installable plugin. Once you have the `claude` CLI on `PATH` (see above), add the marketplace:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
```

Then install whichever skills you need — plugin names match the skill folder names in the [overview table](#overview) below:

```bash
claude plugin install aws-opensearch@useful-claude-add-ons
claude plugin install bitbucket@useful-claude-add-ons
claude plugin install cloudflare@useful-claude-add-ons
# ...repeat for any other skill you want.
```

Both commands also work as slash commands inside an interactive session: `/plugin marketplace add mbadali25/useful-claude-add-ons` and `/plugin install <skill-name>@useful-claude-add-ons`.

Manage it later with:

```bash
claude plugin marketplace list                                # marketplaces you've added
claude plugin marketplace update useful-claude-add-ons        # pull the latest marketplace.json
claude plugin list                                             # installed plugins
claude plugin uninstall aws-opensearch@useful-claude-add-ons   # remove a skill
claude plugin marketplace remove useful-claude-add-ons        # stop tracking this marketplace
```

Don't want the plugin machinery? See [`MARKETPLACE.md`](MARKETPLACE.md) §2 for the lightweight path (clone the repo, point your own `.claude/skills/` at the folders you want). Full details, including the other marketplaces the team's install scripts wire up (Superpowers, `frontend-design`, `excalidraw-generator`), are in [`MARKETPLACE.md`](MARKETPLACE.md).

## Documentation

| Doc | What's in it |
|---|---|
| [`INSTALLATION.md`](INSTALLATION.md) | Prerequisite install scripts (Windows/Linux), installing skills, verification, troubleshooting. |
| [`MARKETPLACE.md`](MARKETPLACE.md) | Adding this repo (and the team's other marketplaces) to Claude Code, installing/updating/removing plugins. |
| [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) | Required structure, frontmatter, and style for any skill in this repo. |
| [`Skill-Pipeline.md`](Skill-Pipeline.md) | Author → validate → review → merge → release → distribute lifecycle for a skill change. |
| [`SECURITY.md`](SECURITY.md) | Reporting a vulnerability, credential-handling policy, install-script trust boundary. |
| [`CHANGELOG.md`](CHANGELOG.md) | Notable changes to this repo, dated. |

## Skills

The canonical, always-current version of this section lives in [`skills/README.md`](skills/README.md) — it's reproduced here so it's visible without an extra click.

<!-- BEGIN skills/README.md -->

Each subdirectory in [`skills/`](skills/) is a self-contained [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) — a `SKILL.md` plus any `references/`, `scripts/`, or `assets/` it needs. Claude auto-discovers a skill's `SKILL.md` frontmatter (`name` + `description`) and decides when to invoke it; you don't call these directly.

See [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) for how a skill in this repo must be structured, and [`Skill-Pipeline.md`](Skill-Pipeline.md) for how a new or changed skill gets from a draft to something your team can install.

### Overview

| Skill | Category | What it does | Invocation |
|---|---|---|---|
| [`aws-opensearch`](skills/aws-opensearch) | Cloud / Infra | Diagnose and remediate an Amazon OpenSearch Service managed domain over SigV4 — cluster health, unassigned shards, reindex, ISM/ILM, snapshots — with dry-run guards on destructive calls. | Automatic |
| [`bitbucket`](skills/bitbucket) | SCM / DevOps | Git over HTTPS with Atlassian API tokens plus the Bitbucket Cloud REST API — PRs, pipelines, comments, branches. | Automatic |
| [`checkpoint-email`](skills/checkpoint-email) | Security | Check Point Email Security (Harmony Email & Collaboration / Avanan) — search entities, triage phishing/malware/DLP/BEC, remediate with a dry-run gate. | Automatic |
| [`cisco-meraki`](skills/cisco-meraki) | Cloud / Networking | Cisco Meraki Dashboard API v1 for a single org — inventory and device status, event and config-change logs, security/IDS events, Air Marshal, live diagnostics, and MX/MS/MR config changes gated behind snapshot → diff → confirm with rollback. | Automatic |
| [`cloudflare`](skills/cloudflare) | Cloud / Networking | Cloudflare v4 API — DNS, zones, cache purge, WAF/rulesets, page rules, SSL/TLS, Workers/KV/R2, Zero Trust, analytics. | Automatic |
| [`drata`](skills/drata) | Compliance | Drata Public API — controls, monitoring tests, evidence, personnel, policies, frameworks, risks, vendors, assets across US/EU/APAC regions. | Automatic |
| [`i-have-adhd`](skills/i-have-adhd) | Productivity | Reshapes Claude's output for ADHD-friendly reading — leads with the next action, numbers steps, suppresses tangents. Persists for the session once invoked. | Manual — `/i-have-adhd` |
| [`infra-work-ticketing`](skills/infra-work-ticketing) | Ops / Ticketing | Makes sure infrastructure work gets a ticket and a work note in Zoho ServiceDesk Plus Cloud or Jira Cloud — asks whether a ticket exists, logs the work as it happens, opens one when there isn't. | Automatic |
| [`intune-graph`](skills/intune-graph) | Endpoint Mgmt | Microsoft Intune via Microsoft Graph — device lookup/troubleshooting, compliance and configuration profiles, Win32/LOB app deployment, bulk report exports. | Automatic |
| [`mermaid-svg-bitbucket`](skills/mermaid-svg-bitbucket) | Docs / DevOps | Pre-renders Mermaid diagrams to committed SVG so they display in Bitbucket Cloud, which never adopted native ```mermaid``` fences. | Automatic |
| [`repo-docs`](skills/repo-docs) | Docs | Generates and refreshes a whole documentation set for a codebase — `CLAUDE.md`, root and per-directory READMEs, API/function reference, architecture doc, `TODO.md`, `SECURITY.md`, `CHANGELOG.md`, handoff notes — re-runnable without clobbering human edits. | Automatic |
| [`shipstation`](skills/shipstation) | E-commerce / Logistics | ShipStation across its three APIs (V2, legacy V1, ShipEngine) — shipments, labels, rates, carriers, warehouses, inventory, products, orders, tracking, batches, manifests. | Automatic |
| [`sophos-central`](skills/sophos-central) | Security | Sophos Central API — endpoint management (isolate, scan, tamper protection), alert triage, SIEM export, XDR/Live Discover, firewall management. | Automatic |
| [`terraform-docs-readme`](skills/terraform-docs-readme) | IaC / Docs | Regenerates a Terraform module's `README.md` with `terraform-docs` — wires up `.terraform-docs.yml`, the `main.tf` header block, `footer.md`, and the `BEGIN_TF_DOCS`/`END_TF_DOCS` injection markers, and diagnoses why a variable, header, or footer isn't showing up. | Automatic |
| [`wazuh-onprem`](skills/wazuh-onprem) | Security / SIEM | Self-hosted Wazuh across all four surfaces — Server API, Indexer API, Dashboard saved-objects API, and `ossec.conf` over SSH. | Automatic |
| [`web-testing-playwright`](skills/web-testing-playwright) | Testing / QA | Drives a real browser with Playwright — screenshots at multiple viewports, console errors, failed network requests, form and login flows — plus browser setup for Windows and Linux. | Automatic |
| [`work-log-reporter`](skills/work-log-reporter) | Productivity | Keeps a committed per-session `work-log/` of what was done and what was touched, then generates a formatted email report with a PDF attachment and sends it over SMTP. | Automatic |

"Automatic" means Claude decides to invoke the skill on its own when the conversation matches the skill's `description` trigger — no slash command needed. "Manual" means the skill sets `disable-model-invocation: true` and must be invoked explicitly (e.g. `/i-have-adhd`).

### Adding a new skill

1. Read [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md).
2. Create `skills/<skill-name>/SKILL.md` (kebab-case directory name matching the `name:` frontmatter field exactly).
3. Follow [`Skill-Pipeline.md`](Skill-Pipeline.md) to validate, review, and register the skill in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) so the team can install it.
4. Add a row to the table above **and** to [`skills/README.md`](skills/README.md) — keep both in sync.

<!-- END skills/README.md -->

## License

See [`LICENSE`](LICENSE).

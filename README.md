# useful-claude-add-ons

An internal repository of [Claude Code](https://docs.claude.com/en/docs/claude-code) Skills, and eventually plugins, built for easy distribution to the team. It also doubles as a Claude Code **plugin marketplace** ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) — see [`MARKETPLACE.md`](MARKETPLACE.md) to add it and install skills directly.

## Quick Install

One-line bootstrap — no `git clone` needed. Pulls the prerequisite installer straight from GitHub and runs it. Review the script before running on a machine you don't fully control — see [`SECURITY.md`](SECURITY.md)'s install-script trust boundary.

**Windows** (elevated PowerShell):

```powershell
irm 'https://raw.githubusercontent.com/mbadali25/useful-claude-add-ons/2e105b03faef78eedfef610ff9aea559e92ffbaa/scripts/install-prerequisites.ps1' | iex
```

**Linux**:

```bash
curl -fsSL 'https://raw.githubusercontent.com/mbadali25/useful-claude-add-ons/2e105b03faef78eedfef610ff9aea559e92ffbaa/scripts/install-prerequisites.sh' | bash
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

Both open with a **menu of everything they can install**, so you pick once up front and the rest of the run is unattended.

The menu is a cursor picker — **↑/↓ to move, Space to tick, Enter to start**:

```
  Select what to install
  ----------------------
    [x] Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)
    [x] Claude Code CLI (@anthropic-ai/claude-code) + PATH export
  > [x] This repo's marketplace + 19 of 19 skills  >
    [x] Team plugins: superpowers, frontend-design, excalidraw-generator
    ...
  ↑↓ move   Space toggle   Enter start   A all   N none   D defaults   Q cancel
  → on the repo row picks individual skills
```

`A` ticks everything, `N` clears it, `D` restores the default set, `Q` or Escape cancels without installing. On the repo's own row, **→ opens a second picker for the individual skills** so you can take three of them instead of all nineteen; ← or Enter comes back to the main menu.

Terminals that can't read a key press one at a time — no `stty`, `TERM=dumb`, PowerShell ISE, a redirected console, a window under ten lines — fall back to the original numbered prompt automatically: `[x]` marks the default set, and you answer `A`, `D` (or Enter), `N`, or numbers like `1,3,7-9`. Item keys work in `--select` either way, so `--select supabase,claude-mem` saves counting rows.

|  # | Item | Default |
|---:|---|:---:|
| 1 | Prerequisites — Chocolatey / `apt` etc. + git, node, python | x |
| 2 | Claude Code CLI + PATH export + **update check** | x |
| 3 | This repo's marketplace + its skills — **→ picks individual skills** | x |
| 4 | Team plugins — superpowers, frontend-design, excalidraw-generator | x |
| 5 | `find-skills` skill | x |
| 6 | Community marketplaces + plugins | x |
| 7 | `claude-code-setup` plugin | x |
| 8 | `task-observer` skill | x |
| 9 | claude-mem — also sets `CLAUDE_MEM_WORKER_PORT` in `settings.json` | x |
| 10 | VoltAgent subagents (10 plugins, 154 agents) | x |
| 11 | MCP server — AWS (`awslabs.aws-api-mcp-server`) | |
| 12 | MCP server — Azure (`@azure/mcp`) | |
| 13 | MCP server — Perplexity (needs `PERPLEXITY_API_KEY`) | |
| 14 | MCP server — Playwright (`@playwright/mcp`) | |
| 15 | Supabase plugin (`supabase@claude-plugins-official`) | |
| 16 | Context7 — up-to-date library docs (`npx ctx7 setup`) | |
| 17 | Playwright CLI (`@playwright/cli`) | |
| 18 | SkillUI + Playwright/Chromium — design system from a URL | |
| 19 | Strix — AI pentesting CLI (needs Docker + an LLM API key) | |

Menu numbers are identical on Windows and Linux, and an already-registered MCP server, marketplace, or plugin is reported and skipped rather than re-added. Numbers can shift as items are added, so scripted runs should prefer the stable keys (`--select supabase,strix`) over positions.

A few items need a word of explanation:

- **Claude Code CLI** (2) also checks for an update when `claude` is *already* installed: it compares the local version against the npm registry and runs `npm install -g @anthropic-ai/claude-code@latest` only when they differ. `--no-update` / `-NoUpdate` reports the installed version and skips the check.
- **claude-mem** (9) appends `"CLAUDE_MEM_WORKER_PORT": "37790"` after the `CLAUDE_MEM_PROVIDER` line in `~/.claude/settings.json`, backing the file up first and restoring it if the result doesn't parse — without the port the worker silently binds somewhere else.
- **Perplexity** (13) needs an API key. If `PERPLEXITY_API_KEY` is already exported the script uses it silently; otherwise it asks once, up front, alongside the menu. Press Enter to skip that server rather than register one that can't authenticate. Under `--non-interactive` / `--all` an unset key skips the server with a warning.
- **Context7** (16) runs `npx ctx7 setup`, which is an interactive wizard — the script hands it the terminal explicitly, and where there is no terminal (CI, a redirected console) it prints the command instead of hanging.
- **SkillUI** (18) installs the CLI, Playwright, and the Chromium build Playwright drives. Playwright goes in **globally** (`npm install -g playwright`) rather than into whatever directory you ran the script from. It asks up front whether to print the quick start when it's done; `--skillui-guide` / `-SkillUIGuide` answers yes without being asked.
- **Strix** (19) is a security tool, not a Claude Code plugin: it installs via upstream's own shell installer (`curl -sSL https://strix.ai/install | bash`). **It cannot run straight after installing** — it needs Docker running and an LLM API key (`STRIX_LLM` + `LLM_API_KEY`), which the script prints as next steps every time. On Windows the installer is POSIX-only, so the script runs it through WSL, falls back to Git Bash, and warns with the manual command if neither is present.

Everything that can be a plugin **is** installed as one, using the CLI's own `claude plugin marketplace add` / `claude plugin install` — there's no `npx claudepluginhub` wrapper and no `git clone` + shell-script step any more. That removes the Windows failure modes those introduced (the wrapper needed a writable per-repo checkout, and the VoltAgent installer needed Git Bash to run a `.sh`).

| Switch (Windows / Linux) | Effect |
|---|---|
| `-All` / `--all` | Select every menu item, no prompt. |
| `-Select '1,3,7-9'` / `--select 1,3,7-9` | Select these menu items, no prompt. Item keys work too: `--select supabase,claude-mem`. |
| `-Skills 'cloudflare,drata'` / `--skills cloudflare,drata` | Install only these of this repo's skills, no sub-picker. Also accepts `all`, `none`, and numbers (`1,4-6`). Composes with `-All` / `-NonInteractive`. |
| `-NonInteractive` / `--non-interactive` | Select the default set, no prompt — for unattended or CI runs. |
| `-SkillUIGuide` / `--skillui-guide` | Print the SkillUI quick start after installing it, without being asked. |
| `-NoUpdate` / `--no-update` | Report already-installed plugins but never update them. |
| `-SkipBootstrap` / `--skip-bootstrap` | Narrow whatever you selected down to the prerequisites and the Claude Code CLI. |
| `-InstallScope` / `--scope` | Scope for every marketplace and plugin install: `user` (default), `project`, or `local`. Windows still accepts the old `-PluginHubScope` name as an alias. |

> On Windows, run from an **elevated** prompt for the full setup. Without elevation the script skips menu item 1 (Chocolatey and its packages: git/awscli/nodejs/python) and runs everything else you selected.

### What each item actually installs

| Item | Pulls in | Source |
|---|---|---|
| 1 Prerequisites | Chocolatey + git, awscli, nodejs, python (Windows) / git, nodejs, npm, python3, pip3 via apt/dnf/yum/pacman/zypper/apk (Linux) | package manager |
| 2 Claude Code CLI | `@anthropic-ai/claude-code`, a persistent `PATH` entry for the npm global bin, and an update to the latest published version if one already exists | npm |
| 3 This repo | The `useful-claude-add-ons` marketplace and, by default, all 19 skills in [`skills/`](skills/) — narrow it with → in the menu or `--skills` | this repo |
| 4 Team plugins | `superpowers`, `frontend-design`, `excalidraw-generator` | 3 marketplaces |
| 5 find-skills | The `find-skills` skill, into the user skills dir | `vercel-labs/skills` |
| 6 Community | `adhd-output-style`, `azure-tools`, `anthropic-office-skills`, `agent-browser`, `ppt-master` | 4 marketplaces |
| 7 claude-code-setup | Analyses a codebase and recommends hooks/skills/MCP servers | `anthropics/claude-plugins-official` |
| 8 task-observer | Watches a session for reusable-skill opportunities | `rebelytics/one-skill-to-rule-them-all` |
| 9 claude-mem | Cross-session memory, plus `CLAUDE_MEM_WORKER_PORT` in `settings.json` | `thedotmack/claude-mem` |
| 10 VoltAgent | 10 plugins, ~154 subagents across dev, infra, QA, data, business | `VoltAgent/awesome-claude-code-subagents` |
| 11–14 MCP servers | AWS, Azure, Perplexity, Playwright | `claude mcp add` |
| 15 Supabase | The `supabase` plugin — project, database, and edge-function tooling | `anthropics/claude-plugins-official` |
| 16 Context7 | `ctx7 setup` — wires up version-accurate library docs for your agents | npx |
| 17 Playwright CLI | `@playwright/cli` (`playwright-cli` on `PATH`) | npm |
| 18 SkillUI | `skillui` + `playwright` + the Chromium browser build | npm |
| 19 Strix | The `strix` pentesting CLI | `curl -sSL https://strix.ai/install \| bash` |

Items 1–10 are the default set. Everything from 11 on is opt-in.

Full walkthrough, verification steps, and troubleshooting: [`INSTALLATION.md`](INSTALLATION.md).

## Add the marketplace & install skills

This repo is itself a Claude Code plugin marketplace ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) — every skill under [`skills/`](skills/) is an installable plugin. Once you have the `claude` CLI on `PATH` (see above), add the marketplace:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
```

The prerequisite installer can do this for you and let you pick which skills to take — either interactively (→ on the repo's row) or up front:

```bash
./scripts/install-prerequisites.sh --select own-skills --skills cloudflare,drata,repo-docs
```

```powershell
.\scripts\install-prerequisites.ps1 -Select own-skills -Skills 'cloudflare,drata,repo-docs'
```

To do it by hand instead, install whichever skills you need — plugin names match the skill folder names in the [overview table](#overview) below:

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

Don't want the plugin machinery? See [`MARKETPLACE.md`](MARKETPLACE.md) §2 for the lightweight path (clone the repo, point your own `.claude/skills/` at the folders you want). Full details, including the other marketplaces the team's install scripts wire up (Superpowers, `frontend-design`, `excalidraw-generator`, the VoltAgent subagents, and the community set), are in [`MARKETPLACE.md`](MARKETPLACE.md).

## Documentation

| Doc | What's in it |
|---|---|
| [`INSTALLATION.md`](INSTALLATION.md) | Prerequisite install scripts (Windows/Linux), installing skills, verification, troubleshooting. |
| [`MARKETPLACE.md`](MARKETPLACE.md) | Adding this repo (and the team's other marketplaces) to Claude Code, installing/updating/removing plugins. |
| [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) | Required structure, frontmatter, and style for any skill in this repo. |
| [`Skill-Pipeline.md`](Skill-Pipeline.md) | Author → validate → review → merge → release → distribute lifecycle for a skill change. |
| [`SECURITY.md`](SECURITY.md) | Reporting a vulnerability, credential-handling policy, install-script trust boundary. |
| [`CHANGELOG.md`](CHANGELOG.md) | Notable changes to this repo, dated. |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Session handoff notes — why things are built the way they are, what was verified, what's still open. |

## Skills

The canonical, always-current version of this section lives in [`skills/README.md`](skills/README.md) — it's reproduced here so it's visible without an extra click.

<!-- BEGIN skills/README.md -->

Each subdirectory in [`skills/`](skills/) is a self-contained [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) — a `SKILL.md` plus any `references/`, `scripts/`, or `assets/` it needs. Claude auto-discovers a skill's `SKILL.md` frontmatter (`name` + `description`) and decides when to invoke it; you don't call these directly.

See [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) for how a skill in this repo must be structured, and [`Skill-Pipeline.md`](Skill-Pipeline.md) for how a new or changed skill gets from a draft to something your team can install.

### Overview

| Skill | Category | What it does | Use cases | Invocation |
|---|---|---|---|---|
| [`aws-opensearch`](skills/aws-opensearch) | Cloud / Infra | Diagnose and remediate an Amazon OpenSearch Service managed domain over SigV4 — cluster health, unassigned shards, reindex, ISM/ILM, snapshots — with dry-run guards on destructive calls. | Red/yellow cluster with unassigned shards; reindexing a legacy index into a new mapping; a 403 from an `es.amazonaws.com` endpoint; standing up an ISM/ILM retention policy. | Automatic |
| [`bitbucket`](skills/bitbucket) | SCM / DevOps | Git over HTTPS with Atlassian API tokens plus the Bitbucket Cloud REST API — PRs, pipelines, comments, branches. | A push or clone failing 401/403/410 against `bitbucket.org`; opening and reviewing a PR; working out why a Pipelines build failed. | Automatic |
| [`checkpoint-email`](skills/checkpoint-email) | Security | Check Point Email Security (Harmony Email & Collaboration / Avanan) — search entities, triage phishing/malware/DLP/BEC, remediate with a dry-run gate. | A reported phishing message that needs quarantining across every mailbox; restoring a false positive; pulling a month of BEC/DLP detections for a report. | Automatic |
| [`cisco-meraki`](skills/cisco-meraki) | Cloud / Networking | Cisco Meraki Dashboard API v1 for a single org — inventory and device status, event and config-change logs, security/IDS events, Air Marshal, live diagnostics, and MX/MS/MR config changes gated behind snapshot → diff → confirm with rollback. | "Which APs are offline?"; "Who changed the firewall rules?"; cycling a flapping switch port; adding a VLAN; confirming a branch VPN came back up. | Automatic |
| [`claude-code-defaults`](skills/claude-code-defaults) | Claude Code / Config | Configures how Claude Code itself behaves by default — `CLAUDE.md` instructions vs `settings.json` enforcement, permission allow/deny/ask rules and modes, hooks, default model, and which scope (user, project, local, managed) each belongs in. Inventories existing config and merges rather than clobbering. | "Stop asking me for permission every time"; "Why is Claude ignoring my `CLAUDE.md`?"; standardizing Claude Code across a team or an MDM-managed fleet. | Automatic |
| [`cloudflare`](skills/cloudflare) | Cloud / Networking | Cloudflare v4 API — DNS, zones, cache purge, WAF/rulesets, page rules, SSL/TLS, Workers/KV/R2, Zero Trust, analytics. | Adding or correcting a DNS record; purging cache after a deploy; a WAF rule blocking legitimate traffic; auditing Zero Trust access policies. | Automatic |
| [`drata`](skills/drata) | Compliance | Drata Public API — controls, monitoring tests, evidence, personnel, policies, frameworks, risks, vendors, assets across US/EU/APAC regions. | SOC 2 or ISO 27001 audit prep; exporting evidence or a personnel roster for an auditor; chasing a failing monitor; a CI compliance gate. | Automatic |
| [`i-have-adhd`](skills/i-have-adhd) | Productivity | Reshapes Claude's output for ADHD-friendly reading — leads with the next action, numbers steps, suppresses tangents. Persists for the session once invoked. | A long debugging session that has turned into a wall of text; multi-step infra work where it's easy to lose your place between turns. | Manual — `/i-have-adhd` |
| [`infra-work-ticketing`](skills/infra-work-ticketing) | Ops / Ticketing | Makes sure infrastructure work gets a ticket and a work note in Zoho ServiceDesk Plus Cloud or Jira Cloud — asks whether a ticket exists, logs the work as it happens, opens one when there isn't. Prefers the ServiceDesk Plus MCP connector so the audit trail names a person, and falls back to the `ticketctl.py` API client when it refuses. | About to change a firewall, DNS record, or AD object with no ticket open; logging what was actually done onto an existing ticket; CAB-ready change documentation. | Automatic |
| [`intune-graph`](skills/intune-graph) | Endpoint Mgmt | Microsoft Intune via Microsoft Graph — device lookup/troubleshooting, compliance and configuration profiles, Win32/LOB app deployment, bulk report exports. | "Why is this laptop non-compliant?"; pushing a sync to a set of machines; packaging and deploying a Win32 app; exporting device inventory; a 403/429 from `graph.microsoft.com`. | Automatic |
| [`mermaid-svg-bitbucket`](skills/mermaid-svg-bitbucket) | Docs / DevOps | Pre-renders Mermaid diagrams to committed SVG so they display in Bitbucket Cloud, which never adopted native ```mermaid``` fences. | A README diagram that renders on GitHub but shows raw code in Bitbucket; diagram labels coming out blank; migrating docs from GitHub/GitLab to Bitbucket. | Automatic |
| [`repo-docs`](skills/repo-docs) | Docs | Generates and refreshes a whole documentation set for a codebase — `CLAUDE.md`, root and per-directory READMEs, API/function reference, architecture doc, `TODO.md`, `SECURITY.md`, `CHANGELOG.md`, handoff notes — re-runnable without clobbering human edits. | Handing a project off to someone else; "the docs are stale"; onboarding notes after a large refactor; wrapping up a substantial session. | Automatic |
| [`shipstation`](skills/shipstation) | E-commerce / Logistics | ShipStation across its three APIs (V2, legacy V1, ShipEngine) — shipments, labels, rates, carriers, warehouses, inventory, products, orders, tracking, batches, manifests. | A label or rate call returning 401/403/429; deciding between API V2 and V1; reconciling orders, shipments, or inventory across stores. | Automatic |
| [`sophos-central`](skills/sophos-central) | Security | Sophos Central API — endpoint management (isolate, scan, tamper protection), alert triage, SIEM export, XDR/Live Discover, firewall management. | Isolating a compromised endpoint; triaging an Intercept X alert; running a Live Discover/XDR hunt; exporting SIEM events into another platform. | Automatic |
| [`terraform-docs-readme`](skills/terraform-docs-readme) | IaC / Docs | Regenerates a Terraform module's `README.md` with `terraform-docs` — wires up `.terraform-docs.yml`, the `main.tf` header block, `footer.md`, and the `BEGIN_TF_DOCS`/`END_TF_DOCS` injection markers, and diagnoses why a variable, header, or footer isn't showing up. | A module README out of date after new variables or outputs; "the docs table is missing a variable"; a header or `footer.md` that isn't picked up; first-time terraform-docs setup. | Automatic |
| [`visio-diagrams`](skills/visio-diagrams) | Docs / Diagrams | Generates native Visio `.vsdx` from a YAML/JSON spec with a stdlib-only writer (no Visio install, works in CI), or drives Visio over COM when real stencil masters, themes, or swimlanes are required — plus SVG preview, OPC verification, and reading/retitling an existing `.vsdx`. | "Make a Visio of our prod network"; turning a subnet list into a topology diagram; a CAB/audit or as-built diagram someone else has to edit; converting Mermaid to `.vsdx`; retitling shapes in an approved corporate template. | Automatic |
| [`wazuh-onprem`](skills/wazuh-onprem) | Security / SIEM | Self-hosted Wazuh across all four surfaces — Server API, Indexer API, Dashboard saved-objects API, and `ossec.conf` over SSH. | Searching `wazuh-alerts` to build an incident timeline; wiring Slack/PagerDuty alerting into `ossec.conf`; onboarding an O365 or Cloudflare log feed; backing up or migrating dashboards. | Automatic |
| [`web-testing-playwright`](skills/web-testing-playwright) | Testing / QA | Drives a real browser with Playwright — screenshots at multiple viewports, console errors, failed network requests, form and login flows — plus browser setup for Windows and Linux. | "Is my site up?"; a page rendering blank with a JS error; verifying a login or checkout flow end to end; a layout that breaks at mobile viewport. | Automatic |
| [`work-log-reporter`](skills/work-log-reporter) | Productivity | Keeps a committed per-session `work-log/` of what was done and what was touched, then generates a formatted email report with a PDF attachment and sends it over SMTP. | End-of-day or standup writeup; "email my manager what I worked on"; a billable record of which systems, databases, and tables were touched. | Automatic |

"Automatic" means Claude decides to invoke the skill on its own when the conversation matches the skill's `description` trigger — no slash command needed. "Manual" means the skill sets `disable-model-invocation: true` and must be invoked explicitly (e.g. `/i-have-adhd`).

### Adding a new skill

1. Read [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md).
2. Create `skills/<skill-name>/SKILL.md` (kebab-case directory name matching the `name:` frontmatter field exactly).
3. Follow [`Skill-Pipeline.md`](Skill-Pipeline.md) to validate, review, and register the skill in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) so the team can install it.
4. Add a row to the table above **and** to [`skills/README.md`](skills/README.md) — keep both in sync. Fill all five columns; **Use cases** should be concrete scenarios that would send someone looking for the skill ("a 403 from `graph.microsoft.com`", "the docs are stale"), not a restatement of *What it does*.

<!-- END skills/README.md -->

## License

See [`LICENSE`](LICENSE).

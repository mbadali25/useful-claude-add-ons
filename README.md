# useful-claude-add-ons

An internal repository of [Claude Code](https://docs.claude.com/en/docs/claude-code) **Skills** ([`skills/`](skills/) — one `SKILL.md` each) and **plugins** ([`plugin/`](plugin/) — bundled subagents, slash commands, and hooks), built for easy distribution to the team. It also doubles as a Claude Code **plugin marketplace** ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) — see [`MARKETPLACE.md`](MARKETPLACE.md) to add it and install either directly.

## Quick Install

One-line bootstrap — no `git clone` needed. Pulls the prerequisite installer straight from GitHub and runs it. Review the script before running on a machine you don't fully control — see [`SECURITY.md`](SECURITY.md)'s install-script trust boundary.

**Windows** (elevated PowerShell):

```powershell
irm 'https://raw.githubusercontent.com/mbadali25/useful-claude-add-ons/bd3e9ad1daac89654e0134be1cc56c79612be535/scripts/install-prerequisites.ps1' | iex
```

**Linux**:

```bash
curl -fsSL 'https://raw.githubusercontent.com/mbadali25/useful-claude-add-ons/bd3e9ad1daac89654e0134be1cc56c79612be535/scripts/install-prerequisites.sh' | bash
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

Both scripts are idempotent and **detect before they install** — an already-present Chocolatey package, marketplace, or plugin is reported and skipped rather than reinstalled. Re-running is cheap and safe: a plugin whose marketplace has not moved since it was installed is skipped without launching `claude` at all, so a no-op re-run of the 25-skill item takes seconds rather than minutes. Each run ends with an `Installed / Updated / Already present` summary.

Both open with a **menu of everything they can install**, so you pick once up front and the rest of the run is unattended.

The menu is a cursor picker — **↑/↓ to move, Space to tick, Enter to start**:

<!-- claim: skills-count -->
```
  Select what to install
  ----------------------
    [x] Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)
    [x] Claude Code CLI (@anthropic-ai/claude-code) + PATH export
  > [x] This repo's marketplace + 35 of 35 skills  >
    [x] Team plugins: superpowers, frontend-design, excalidraw-generator
    ...
  ↑↓ move   Space toggle   Enter start   A all   N none   D defaults   Q cancel
  → on a row marked > picks the individual items inside it
```

`A` ticks everything, `N` clears it, `D` restores the default set, `Q` or Escape cancels without installing. Every row that installs **more than one thing** is marked `>`, and **→ opens a second picker for the items inside it** — so you can take three skills instead of all twenty-five, or one team plugin instead of three; ← or Enter comes back to the main menu, and `Q` there discards just that sub-selection. The row's label keeps a live count (`3 of 25`), and opening a sub-picker ticks its parent row so a careful selection can't be lost to an unticked parent.

Terminals that can't read a key press one at a time — no `stty`, `TERM=dumb`, PowerShell ISE, a redirected console, a window under ten lines — fall back to the original numbered prompt automatically: `[x]` marks the default set, and you answer `A`, `D` (or Enter), `N`, or numbers like `1,3,7-9`. Item keys work in `--select` either way, so `--select supabase,strix` saves counting rows.

|  # | Item | Default |
|---:|---|:---:|
| 1 | Prerequisites — Chocolatey / `apt` etc. + git, node, python | x |
| 2 | Claude Code CLI + PATH export + **update check** | x |
| 3 | This repo's marketplace + its skills — **→ picks individual skills** (`notify` asks about setup) | x |
| 4 | Team plugins — superpowers, frontend-design, excalidraw-generator — **→ picks which** | x |
| 5 | `find-skills` skill | x |
| 6 | Community marketplaces + plugins — **→ picks which** (adhd-output-style, azure-tools, anthropic-office-skills, agent-browser, ppt-master) | x |
| 7 | `claude-code-setup` plugin | x |
| 8 | `task-observer` skill | x |
| 9 | MCP server — AWS (`awslabs.aws-api-mcp-server`) | |
| 10 | MCP server — Azure (`@azure/mcp`) | |
| 11 | MCP server — Playwright (`@playwright/mcp`) | |
| 12 | MCP server — Obsidian vault server (Local REST API over an SSH tunnel) | |
| 13 | Supabase plugin (`supabase@claude-plugins-official`) | |
| 14 | Context7 — up-to-date library docs (`npx ctx7 setup`) | |
| 15 | Playwright CLI (`@playwright/cli`) | |
| 16 | SkillUI + Playwright/Chromium — design system from a URL | |
| 17 | Strix — AI pentesting CLI (needs Docker + an LLM API key) | |
| 18 | Obsidian desktop + `claude-obsidian` and `obsidian-skills` plugins | |
| 19 | This repo's plugins — `crew`, `gizmoduck`, `localgpu`, `obsidian-vault`, `rule-of-two` (agents, commands, **hooks**) — **→ picks which** | |
| 20 | `graphify` code graph (`uv tool install graphifyy`; per-repo, not global) | |
| 21 | Microsoft MCP servers (`mcp-servers/`) — Graph, Intune, Office 365 user/admin — **needs `az login` or tenant credentials** | |
| 22 | MCP server: **AWS Knowledge** — AWS docs, API references and regional availability, hosted by AWS. **No credentials** | |
| 23 | MCP server: **AWS Pricing** — the Price List API. **Needs AWS credentials whose role allows `pricing:*`**; the calls themselves are free | |
| 24 | MCP server: **Microsoft Learn** — Azure, SharePoint and Power Automate / Power Platform docs plus code samples. **No credentials** | |
| 25 | MCP server: **Perplexity** — web-grounded search, ask, research and reason; the server the [`web-research`](skills/web-research/) skill calls. **Needs a Perplexity API key** | |

Menu numbers are identical on Windows and Linux, and an already-registered MCP server, marketplace, or plugin is reported and skipped rather than re-added. Numbers can shift as items are added, so scripted runs should prefer the stable keys (`--select supabase,strix`) over positions.

A few items need a word of explanation:

- **Claude Code CLI** (2) also checks for an update when `claude` is *already* installed: it compares the local version against the npm registry and runs `npm install -g @anthropic-ai/claude-code@latest` only when they differ. `--no-update` / `-NoUpdate` reports the installed version and skips the check.
- **The `notify` skill** (in the item 3 sub-picker) is the one skill that needs machine-level setup, so when it's ticked the script prints its prerequisites — Python 3.8+, a `@BotFather` bot token, your `chat_id`, `TELEGRAM_BOT_TOKEN` exported, and a config file — then asks whether to scaffold `~/.config/notify/config.json` for you. `--notify-setup` / `-NotifySetup` answers yes without being asked. It never writes the bot token anywhere; an existing config is left alone. For the guided version, run `/notify-setup` in a Claude session.
- **Context7** (14) runs `npx ctx7 setup`, which is an interactive wizard — the script hands it the terminal explicitly, and where there is no terminal (CI, a redirected console) it prints the command instead of hanging.
- **SkillUI** (16) installs the CLI, Playwright, and the Chromium build Playwright drives. Playwright goes in **globally** (`npm install -g playwright`) rather than into whatever directory you ran the script from. It asks up front whether to print the quick start when it's done; `--skillui-guide` / `-SkillUIGuide` answers yes without being asked.
- **Strix** (17) is a security tool, not a Claude Code plugin: it installs via upstream's own shell installer (`curl -sSL https://strix.ai/install | bash`). **It cannot run straight after installing** — it needs Docker running and an LLM API key (`STRIX_LLM` + `LLM_API_KEY`), which the script prints as next steps every time. On Windows the installer is POSIX-only, so the script runs it through WSL, falls back to Git Bash, and warns with the manual command if neither is present.

- **The Obsidian vault-server MCP endpoint** (12) registers an HTTP MCP server rather than launching a command: the endpoint is the `obsidian-local-rest-api` plugin already running inside the vault-server container, listening on that **server's** loopback, so the URL is normally a port you forwarded over SSH. The API key is per-deployment and can't be baked in, so without `--obsidian-mcp-key` / `-ObsidianMcpKey` the item prints how to obtain one (`sudo ./obsidian-vault-server.sh apikey`) and skips instead of failing. See the [`obsidian-vault-server`](skills/obsidian-vault-server/) skill for the whole setup.

- **Obsidian** (18) is a desktop app, not a plugin, so it comes from a package manager: Chocolatey first on Windows (falling back to winget), flatpak first on Linux (falling back to snap) — distro repos generally don't carry it. Chocolatey needs an elevated prompt; without one the app is skipped and the two plugins still install. It then adds the `claude-obsidian` vault engine and [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills), Obsidian's own upstream skills for Markdown, Bases, JSON Canvas, the Obsidian CLI, and Defuddle. **The app and plugins are all this item does** — creating the vault is a separate, deliberately reviewed step, which the item prints as its next step and [`claude-obsidian-setup/`](claude-obsidian-setup/) performs. `--obsidian-repo-root` / `-ObsidianRepoRoot` changes the root it suggests (default `C:\repos` on Windows, `~/repos` on Linux).

- **This repo's plugins** (19) installs [`plugin/crew`](plugin/crew) from this same marketplace — so it works whether or not item 3 ran. It is **off by default, deliberately**: unlike a skill, `crew` registers **hooks**, and a hook is not advisory. Its `PreToolUse` hook blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, and any command that would print a secret into the transcript; its `Stop` hooks run the checks your changed paths map to (failing the turn on red) and watch context use; a `PreCompact`/`SessionStart` pair carries a handoff note across compaction, and that same `SessionStart` also runs a report-only PM brief — schema drift, a stale or missing code graph, review health — before you type anything. All of them start working the moment the plugin is enabled, so the item ends by printing the per-repository setup (`/crew:init`, `/crew:onboard`, `/crew:verify`) rather than leaving you to discover the gates by hitting them. This item also detects, but never removes, a separately-installed global copy of `find-skills` (item 5) that would collide with the one `crew` vendors. See [`plugin/README.md`](plugin/README.md) for the catalog and [`plugin/PLUGINS.md`](plugin/PLUGINS.md) for what each plugin actually contains.

- **`graphify` code graph** (20) installs the third-party `graphify` CLI (`uv tool install graphifyy` — package `graphifyy`, double-y; the CLI it installs is `graphify`) and registers it **per-repository** with `graphify install --project`, never globally. Off by default, no new flag — it reuses `--select` / `-Select` like every other item. This is what `crew`'s `/crew:upgrade` and the `crew-graph` skill build on; installing it alone does nothing until `crew` (19) or another workflow calls it.

- **Microsoft MCP servers** (21) is not one server but four — `mcp-msgraph`, `mcp-intune`, `mcp-o365-admin`, `mcp-o365-user` — built from [`mcp-servers/`](mcp-servers/) in this repo and **published to npm under `@badali404`**, so like items 9–12 this registers the npx form: `claude mcp add <name> -- npx -y @badali404/<pkg>@latest`, no clone or build needed. What it needs first is real Azure AD app registrations — `MS_ADMIN_TENANT_ID`/`MS_ADMIN_CLIENT_ID`/`MS_ADMIN_CLIENT_SECRET` (app-only, tenant-wide — registers `mcp-msgraph`, `mcp-intune`, `mcp-o365-admin`) and/or `MS_USER_CLIENT_ID` (delegated device-code — registers `mcp-o365-user`). Without any of those set, the item explains what's missing and skips rather than failing. Registration is bare, no `--env`, so no secret is ever written into `~/.claude.json`; the same env vars must also be set wherever the `claude` process itself gets launched, or the registered servers will fail to authenticate. Every tool in all four servers is read-only until `MCP_MS_ALLOW_WRITES=1` is also set there. See [`mcp-servers/README.md`](mcp-servers/README.md) for the full auth model, env vars, and the gated-tool list, and [`mcp-servers/PUBLISHING.md`](mcp-servers/PUBLISHING.md) for releasing new versions.

Everything that can be a plugin **is** installed as one, using the CLI's own `claude plugin marketplace add` / `claude plugin install` — there's no `npx claudepluginhub` wrapper and no `git clone` + shell-script step any more. That removes the Windows failure modes those introduced (the wrapper needed a writable per-repo checkout).

| Switch (Windows / Linux) | Effect |
|---|---|
| `-All` / `--all` | Select every menu item, no prompt. |
| `-Select '1,3,7-9'` / `--select 1,3,7-9` | Select these menu items, no prompt. Item keys work too: `--select supabase,strix`. |
| `-Skills 'cloudflare,drata'` / `--skills cloudflare,drata` | Install only these of this repo's skills, no sub-picker. Also accepts `all`, `none`, and numbers (`1,4-6`). Composes with `-All` / `-NonInteractive`. |
| `-Team` / `--team`, `-Community` / `--community`, `-Plugins` / `--plugins` | The same for the other multi-item rows — items 4, 6 and 19. Each takes names, numbers, `all` or `none`, skips that row's sub-picker, and implies its parent item. Names match either the plugin key or the short label the picker shows. |
| `-NonInteractive` / `--non-interactive` | Select the default set, no prompt — for unattended or CI runs. |
| `-SkillUIGuide` / `--skillui-guide` | Print the SkillUI quick start after installing it, without being asked. |
| `-NotifySetup` / `--notify-setup` | Scaffold `~/.config/notify/config.json` after installing the `notify` skill, without being asked. The prerequisites are printed either way. |
| `-NoUpdate` / `--no-update` | Report already-installed plugins but never update them. |
| `-ForceRefresh` / `--force-refresh` | Reinstall a plugin whose files changed in its marketplace but whose declared version did not. Without it such a plugin is reported and left alone — see [Content drift](#content-drift) below. |
| `-DryRun` / `--dry-run` | Work out the selection, print it, and stop — installs nothing. Useful for checking what a set of flags actually resolves to. |
| `-SkipBootstrap` / `--skip-bootstrap` | Narrow whatever you selected down to the prerequisites and the Claude Code CLI. |
| `-InstallScope` / `--scope` | Scope for every marketplace and plugin install: `user` (default), `project`, or `local`. Windows still accepts the old `-PluginHubScope` name as an alias. |
| `-ObsidianRepoRoot` / `--obsidian-repo-root` | Root that item 18 suggests for the Obsidian vault — `C:\repos` on Windows, `~/repos` on Linux. Only affects the printed next step; the vault itself is created by [`claude-obsidian-setup/`](claude-obsidian-setup/). |
| `-ObsidianMcpUrl` / `--obsidian-mcp-url` | MCP endpoint item 12 registers for the Obsidian vault server. Default `http://127.0.0.1:27123/mcp/` — loopback, because the endpoint is normally reached through an SSH tunnel. |
| `-ObsidianMcpKey` / `--obsidian-mcp-key` | Local REST API key for item 12. Per-deployment, so there is no default: without it the item explains how to get one and skips. |
| `-PerplexityApiKey` / `--perplexity-api-key` | Perplexity API key for item 25. Falls back to `PERPLEXITY_API_KEY` in the environment; with neither set the item explains how to get one and skips rather than registering a server that can never authenticate. |

> On Windows, run from an **elevated** prompt for the full setup. Without elevation the script skips menu item 1 (Chocolatey and its packages: git/awscli/nodejs/python) and runs everything else you selected.

### Content drift

`claude plugin update` decides whether to re-copy a plugin by comparing **declared versions**. A marketplace that edits a skill without bumping its `version` therefore leaves every already-installed copy silently stale: the CLI reports *"already at the latest version"* and copies nothing.

Both scripts detect this. For an installed plugin they compare the commit its marketplace is on now against the commit Claude Code recorded when it was installed, and:

- **same commit** — nothing to do, and no `claude` process is launched at all.
- **different commit, but this plugin's own files are unchanged** — also nothing to do. One commit anywhere in a marketplace moves `HEAD` for every plugin it publishes, so this is the common case.
- **this plugin's files changed** — run `claude plugin update`. If the version moved, it updates normally. If it did not, the script says so plainly instead of reporting the plugin as current, and `--force-refresh` / `-ForceRefresh` reinstalls it (`--keep-data`, so the plugin's persistent data survives).

If `git` is missing, the marketplace was added from somewhere without history, or the recorded commit has been pruned by a force-push, the check reports "cannot tell" and falls back to asking the CLI about every plugin — correct, just slower.

For this repo's own skills, [`scripts/check-marketplace.py`](scripts/check-marketplace.py) fails CI when a skill's files change without a version bump, so the drift never reaches anyone's machine in the first place.

### What each item actually installs

| Item | Pulls in | Source |
|---|---|---|
| 1 Prerequisites | Chocolatey + git, awscli, nodejs, python (Windows) / git, nodejs, npm, python3, pip3 via apt/dnf/yum/pacman/zypper/apk (Linux) | package manager |
| 2 Claude Code CLI | `@anthropic-ai/claude-code`, a persistent `PATH` entry for the npm global bin, and an update to the latest published version if one already exists | npm |
| 3 This repo | The `useful-claude-add-ons` marketplace and, by default, all 35 skills<!-- claim: skills-count --> in [`skills/`](skills/) — narrow it with → in the menu or `--skills` | this repo |
| 4 Team plugins | `superpowers`, `frontend-design`, `excalidraw-generator` | 3 marketplaces (only the ones behind a ticked plugin) |
| 5 find-skills | The `find-skills` skill, into the user skills dir | `vercel-labs/skills` |
| 6 Community | `adhd-output-style`, `azure-tools`, `anthropic-office-skills`, `agent-browser`, `ppt-master`, `voltagent-infra`, `voltagent-qa-sec` | 4 marketplaces (only the ones behind a ticked plugin) |
| 7 claude-code-setup | Analyses a codebase and recommends hooks/skills/MCP servers | `anthropics/claude-plugins-official` |
| 8 task-observer | Watches a session for reusable-skill opportunities | `rebelytics/one-skill-to-rule-them-all` |
| 9–11 MCP servers | AWS API, Azure, Playwright | `claude mcp add` |
| 12 Obsidian MCP | The `obsidian-server` HTTP MCP endpoint (`obsidian-local-rest-api`'s built-in MCP route), bearer-authenticated with `--obsidian-mcp-key` — skipped with instructions when no key is given | `claude mcp add` |
| 13 Supabase | The `supabase` plugin — project, database, and edge-function tooling | `anthropics/claude-plugins-official` |
| 14 Context7 | `ctx7 setup` — wires up version-accurate library docs for your agents | npx |
| 15 Playwright CLI | `@playwright/cli` (`playwright-cli` on `PATH`) | npm |
| 16 SkillUI | `skillui` + `playwright` + the Chromium browser build | npm |
| 17 Strix | The `strix` pentesting CLI | `curl -sSL https://strix.ai/install \| bash` |
| 18 Obsidian | The Obsidian desktop app (Chocolatey → winget on Windows, flatpak → snap on Linux), plus the `claude-obsidian` vault engine and [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) — Obsidian's own Markdown, Bases, JSON Canvas, CLI and Defuddle skills | choco/winget/flatpak/snap + 2 marketplaces |
| 19 This repo's plugins | The `crew` plugin from [`plugin/`](plugin/) — 4 subagents, 36 slash commands, 31 bundled skills<!-- claim: plugin-skills:crew -->, and 34 hook entries (13 scripts × `.sh`/`.ps1`) across 8 events — `obsidian-vault` — 2 agents, 11 slash commands, 3 skills, and 8 hook entries (3 scripts × `.sh`/`.ps1`) — `gizmoduck` — 6 slash commands and 1 skill, no hooks, no agents — `localgpu` — 6 slash commands, 1 skill, and a local MCP server, no hooks, no agents — and `rule-of-two` — 2 slash commands and 1 agent, no hooks, no skills. Off by default because hooks execute whether or not Claude agrees with them | this repo |
| 20 `graphify` | The `graphify` CLI (`graphifyy` on PyPI), registered per-repository with `graphify install --project`. Off by default; not installed globally | `uv tool install` |
| 21 Microsoft MCP servers | Registers up to 4 servers via npx — `mcp-msgraph`, `mcp-intune`, `mcp-o365-admin` (app-only via `MS_ADMIN_*`, OR delegated via an existing `az login` session, checked with `az account show` — no app registration required for the latter), `mcp-o365-user` (delegated device-code, needs `MS_USER_CLIENT_ID`). Skipped with instructions when neither an `az login` session nor credentials are found | npm (`@badali404/mcp-*`) + `claude mcp add` |
| 22 AWS Knowledge | A remote HTTP endpoint (`https://knowledge-mcp.global.api.aws/mcp`), not a launched command — nothing to install and no AWS account involved. Separate from row 9 on purpose: row 9's server reads a real account, this one reads published documentation, so a machine that may not have the first can still have the second. Public and rate-limited | `claude mcp add --transport http` |
| 23 AWS Pricing | `uvx awslabs.aws-pricing-mcp-server@latest`, installing `uv` first if it is absent — the same bootstrap row 9 does. The one of these three that **does** need credentials: the Price List API is an AWS API call, not a document fetch, and the role needs `pricing:*`. The calls are free of charge | `uvx` + `claude mcp add` |
| 24 Microsoft Learn | A remote HTTP endpoint (`https://learn.microsoft.com/api/mcp`). One server for three of this repo's domains — `learn.microsoft.com` carries the Azure, SharePoint and Power Automate / Power Platform documentation, so `intune-graph`, `power-automate-api` and the SharePoint skills all resolve against it rather than against three separate servers | `claude mcp add --transport http` |
| 25 Perplexity | `npx -y @perplexity-ai/mcp-server`, registered with `--env PERPLEXITY_API_KEY=<key>` so the CLI has the key when it launches the server. Unlike row 21 this **does** write the key into the MCP registration — so it lands on disk in `~/.claude.json`, the same place row 12's bearer token goes, and the server gets it whatever environment the `claude` process was launched from. The key comes from `--perplexity-api-key` / `-PerplexityApiKey` or `PERPLEXITY_API_KEY`, is never printed, and with neither set the row explains how to get one and skips. This is the server the [`web-research`](skills/web-research/) skill calls | `claude mcp add` |

Items 1–8 are the default set. Everything from 9 on is opt-in.

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

The same marketplace also carries this repo's own **plugins** — the ones under [`plugin/`](plugin/), which bundle subagents, slash commands, and hooks rather than a single `SKILL.md`. They install identically:

```bash
claude plugin install crew@useful-claude-add-ons
```

Or take it from the bootstrap script as **item 19**, which is off by default:

```bash
./scripts/install-prerequisites.sh --select repo-plugins
```

Both commands also work as slash commands inside an interactive session: `/plugin marketplace add mbadali25/useful-claude-add-ons` and `/plugin install <name>@useful-claude-add-ons`.

Manage it later with:

```bash
claude plugin marketplace list                                # marketplaces you've added
claude plugin marketplace update useful-claude-add-ons        # pull the latest marketplace.json
claude plugin list                                             # installed plugins
claude plugin uninstall aws-opensearch@useful-claude-add-ons   # remove a skill
claude plugin marketplace remove useful-claude-add-ons        # stop tracking this marketplace
```

Don't want the plugin machinery? See [`MARKETPLACE.md`](MARKETPLACE.md) §2 for the lightweight path (clone the repo, point your own `.claude/skills/` at the folders you want). Full details, including the other marketplaces the team's install scripts wire up (`claude-plugins-official` for Superpowers, `frontend-design`, `excalidraw-generator`, and the community set), are in [`MARKETPLACE.md`](MARKETPLACE.md).

## What's new

<!-- Generated from CHANGELOG.md by scripts/sync-updates.py. Edit the changelog, then run it. -->
<!-- BEGIN CHANGELOG.md -->

- **crew**: A vault write matches every directory from the vault down, not just the vault. A board or note directory inside the Obsidian vault that is swapped for another real directory between crew's checks and its write is now refused instead of written into.
- **crew 1.0.351, notify 1.1.2**: Notifications that failed, repeated, or said only "missing". Chat notifications now go through when the bot token was saved with a trailing space or newline, a missing setting is named along with where to set it, a refused send says Telegram's reason, and the notify skill's dispatcher no longer posts the same message again after a restart.

Full history: [CHANGELOG.md](CHANGELOG.md).

<!-- END CHANGELOG.md -->

## Documentation

| Doc | What's in it |
|---|---|
| [`VERIFYING.md`](VERIFYING.md) | **How to verify a change** — the commands, in order, for people and any AI agent: marketplace gate, smoke, crew's verify gate, the local CI suite, CI receipts, and what nothing runs. |
| [`INSTALLATION.md`](INSTALLATION.md) | Prerequisite install scripts (Windows/Linux), installing skills, verification, troubleshooting. |
| [`plugin/README.md`](plugin/README.md) | This repo's **plugins** — what a plugin adds over a skill, the overview table, and how to add one. |
| [`plugin/PLUGINS.md`](plugin/PLUGINS.md) | Per-plugin reference — every command, agent, bundled skill, and hook, and what starts running on enable. |
| [`MARKETPLACE.md`](MARKETPLACE.md) | Adding this repo (and the team's other marketplaces) to Claude Code, installing/updating/removing plugins. |
| [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) | Required structure, frontmatter, and style for any skill in this repo. |
| [`Skill-Pipeline.md`](Skill-Pipeline.md) | Author → validate → review → merge → release → distribute lifecycle for a skill change. |
| [`SECURITY.md`](SECURITY.md) | Reporting a vulnerability, credential-handling policy, install-script trust boundary. |
| [`CHANGELOG.md`](CHANGELOG.md) | Notable changes to this repo, dated. |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Session handoff notes — why things are built the way they are, what was verified, what's still open. |
| [`claude-obsidian-setup/`](claude-obsidian-setup/) | **Obsidian knowledge-vault setup** for Windows (WSL) and Linux — the deeper version of menu item 18. |
| [`plugin/obsidian-vault/`](plugin/obsidian-vault/) | **Self-feeding vault pipeline** — session-capture hooks, a bounded gardener that distills queued sessions, and portable conventions profiles. Replaces the retired Windows-only `vault-automation/` scripts. |

## Obsidian knowledge vault

[**`claude-obsidian-setup/`**](claude-obsidian-setup/) sets up a source-cited Obsidian vault driven from Claude Code, identically on Windows and Linux. Menu item 18 of the bootstrap installs the app and the plugins; these scripts also **create and verify the vault**.

| Platform | Script |
|---|---|
| Windows 10/11 + WSL | [`claude-obsidian-setup/setup-claude-obsidian.ps1`](claude-obsidian-setup/setup-claude-obsidian.ps1) |
| Linux (native) | [`claude-obsidian-setup/setup-claude-obsidian.sh`](claude-obsidian-setup/setup-claude-obsidian.sh) |

Both are **dry-run by default** — nothing changes without `-Apply` / `--apply`:

```powershell
# Windows (elevated for the Obsidian install)
.\claude-obsidian-setup\setup-claude-obsidian.ps1
.\claude-obsidian-setup\setup-claude-obsidian.ps1 -Apply

# Somewhere other than the C:\repos default
.\claude-obsidian-setup\setup-claude-obsidian.ps1 -Apply -RepoRoot D:\work
```

```bash
# Linux
bash claude-obsidian-setup/setup-claude-obsidian.sh
bash claude-obsidian-setup/setup-claude-obsidian.sh --apply

# Somewhere other than the ~/repos default
bash claude-obsidian-setup/setup-claude-obsidian.sh --apply --repo-root /srv/work
```

Everything hangs off one root — `C:\repos` on Windows, `~/repos` on Linux — so `-RepoRoot` / `--repo-root` relocates the vault *and* the product checkout together. `-VaultPath` / `--vault` and `-ProductRoot` / `--product` override either half.

On Windows they also fix four things that otherwise break claude-obsidian silently: native Windows cannot write to a vault at all (no `fcntl`), `python3` resolves to a Microsoft Store stub, `/mnt/c` mounts without the `metadata` option so every write fails `EPERM`, and git identity doesn't cross into WSL so `checkpoint` can't commit. See [`claude-obsidian-setup/README.md`](claude-obsidian-setup/README.md).

### Vault automation — the vault that feeds itself

Use the cross-platform [`obsidian-vault`](plugin/obsidian-vault) plugin (`claude plugin install obsidian-vault@useful-claude-add-ons`, then `/obsidian-vault:init`): capture hooks queue every session into the vault inbox, a gardener distills queued sessions into source-cited concept pages and daily digests, and portable conventions profiles under `plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/` replace the vault-specific `claude-memories-vault`/`claude-memories-canvas` skills this repo used to ship. The Windows-only `vault-automation/` installer that predated the plugin has been retired.

## Microsoft MCP servers

[**`mcp-servers/`**](mcp-servers/) is four local, stdio-based MCP servers for Microsoft
365 and Intune — `mcp-msgraph` (tenant directory), `mcp-intune` (device management),
`mcp-o365-admin` (mailboxes, licenses, password reset), and `mcp-o365-user` (the
signed-in user's own mail/calendar/files via device-code sign-in). They are **not**
marketplace plugins; they're npm packages built from one shared auth/HTTP workspace
package and registered with `claude mcp add`. Menu item 21 of the bootstrap installer
builds and registers them, off by default. The three admin-scope servers register with
just an existing `az login` session (no app registration needed) or with `MS_ADMIN_*`
credentials; `mcp-o365-user` always needs its own `MS_USER_CLIENT_ID` app registration.

Azure Resource Manager is deliberately **not** one of the four: the official
[`@azure/mcp`](https://www.npmjs.com/package/@azure/mcp) (menu item 10) already covers
ARM comprehensively, so this repo doesn't duplicate it. All five packages
(the shared core plus the four servers) are published to npm under `@badali404`,
so `npx -y @badali404/<pkg>@latest` is the install path — no clone needed.
[`.github/workflows/publish-mcp-servers.yml`](.github/workflows/publish-mcp-servers.yml)
publishes all five, core first, on a tagged `mcp-servers-v*` push
([`mcp-servers/PUBLISHING.md`](mcp-servers/PUBLISHING.md) is the walkthrough). See
[`mcp-servers/README.md`](mcp-servers/README.md) for that decision, the full auth model
(delegated vs. app-only, and why they're separate credentials), every environment
variable, the write/destructive tools gated behind `MCP_MS_ALLOW_WRITES=1` +
`confirm: true`, and registration one-liners for both platforms.

## Skills

The canonical, always-current version of this section lives in [`skills/README.md`](skills/README.md) — it's reproduced here so it's visible without an extra click.

<!-- BEGIN skills/README.md -->

Each subdirectory in [`skills/`](skills/) is a self-contained [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) — a `SKILL.md` plus any `references/`, `scripts/`, or `assets/` it needs. Claude auto-discovers a skill's `SKILL.md` frontmatter (`name` + `description`) and decides when to invoke it; you don't call these directly.

See [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) for how a skill in this repo must be structured, and [`Skill-Pipeline.md`](Skill-Pipeline.md) for how a new or changed skill gets from a draft to something your team can install.

### Overview

| Skill | Category | What it does | Use cases | Invocation |
|---|---|---|---|---|
| [`aws-opensearch`](skills/aws-opensearch) | Cloud / Infra | Diagnose and remediate an Amazon OpenSearch Service managed domain over SigV4 — cluster health, unassigned shards, reindex, ISM/ILM, snapshots — with dry-run guards on destructive calls. | Red/yellow cluster with unassigned shards; reindexing a legacy index into a new mapping; a 403 from an `es.amazonaws.com` endpoint; standing up an ISM/ILM retention policy. | Automatic |
| [`bitbucket`](skills/bitbucket) | SCM / DevOps | Git over HTTPS with Atlassian API tokens plus the Bitbucket Cloud REST API — PRs, pipelines, comments, branches. | A push or clone failing 401/403/410 against `bitbucket.org`; opening and reviewing a PR; adding reviewers when the repo has no default reviewers; a pipeline or deployment variable reading as absent; working out why a Pipelines build failed. | Automatic |
| [`checkpoint-email`](skills/checkpoint-email) | Security | Check Point Email Security (Harmony Email & Collaboration / Avanan) — search entities, triage phishing/malware/DLP/BEC, remediate with a dry-run gate. | A reported phishing message that needs quarantining across every mailbox; restoring a false positive; pulling a month of BEC/DLP detections for a report. | Automatic |
| [`cisco-meraki`](skills/cisco-meraki) | Cloud / Networking | Cisco Meraki Dashboard API v1 for a single org — inventory and device status, event and config-change logs, security/IDS events, Air Marshal, live diagnostics, and MX/MS/MR config changes gated behind snapshot → diff → confirm with rollback. | "Which APs are offline?"; "Who changed the firewall rules?"; cycling a flapping switch port; adding a VLAN; confirming a branch VPN came back up. | Automatic |
| [`cloudflare`](skills/cloudflare) | Cloud / Networking | Cloudflare v4 API — DNS, zones, cache purge, WAF/rulesets, page rules, SSL/TLS, Workers/KV/R2, Zero Trust, analytics. | Adding or correcting a DNS record; purging cache after a deploy; a WAF rule blocking legitimate traffic; auditing Zero Trust access policies. | Automatic |
| [`config-tuneup`](skills/config-tuneup) | Claude Code / Config | Audits an installation for what is making it slow or bloated — the same skill installed twice, hooks spawning a process on every tool call, `SessionStart` hooks injecting context, plugins installed but disabled, overlapping MCP servers, oversized `CLAUDE.md` and unscoped rules — and returns a ranked cleanup plan with the exact command per item. Read-only until you approve. | "Claude Code feels slow"; startup or every Bash call lagging; compacting far too early; a skill firing twice or the wrong one firing; tidying up after an install script added a dozen plugins at once. | Automatic |
| [`doc-builder`](skills/doc-builder) | Docs / Reporting | Finished documents as DOCX and PDF through Word, or LibreOffice where Word is absent, in the house style of whichever brand pack is installed. Two pipelines behind one routing rule: findings and tabular content go HTML-to-Word; step-by-step procedures with screenshots go python-docx OOXML, which is the only path that survives Word's `wp:effectExtent` border clipping. Also install [`solomon-doc-builder`](skills/solomon-doc-builder) for automatic Solomon branding; `--brand neutral` (or `DOC_BUILDER_BRAND=neutral`) always turns it back off. | "Write this up for management"; an SOP for setting up the VPN with screenshots; a findings report that came out unstyled black-on-white; "turn this into a Word doc I can send to the client". | Automatic |
| [`drata`](skills/drata) | Compliance | Drata Public API — controls, monitoring tests, evidence, personnel, policies, frameworks, risks, vendors, assets across US/EU/APAC regions. | SOC 2 or ISO 27001 audit prep; exporting evidence or a personnel roster for an auditor; chasing a failing monitor; a CI compliance gate. | Automatic |
| [`exchange-mailbox-cleanup`](skills/exchange-mailbox-cleanup) | M365 / Exchange | Walks a non-technical operator through Exchange Online mailbox cleanup and offboarding, one step at a time - preflight and module install under the user profile, SDP ticket, litigation hold, preservation baseline, account deletion, eDiscovery export. Typed confirmation naming the count on every irreversible step. | "Sarah left on Friday - put her mailbox on hold and free up the licence"; a `holdlist.csv` of leavers from HR; "delete the account but keep the email". | Automatic |
| [`exchange-mailbox-restore`](skills/exchange-mailbox-restore) | M365 / Exchange | Walks the same operator through restoring a mailbox or removing a hold. Triage on `MailboxState` first, then exactly one of five mutually exclusive paths - two of which destroy the preserved copy and are gated accordingly. Installs alongside `exchange-mailbox-cleanup`, whose preflight and references it shares. | "The manager needs to read the ex-employee's mail"; "we deleted someone by mistake last week"; "take Dave off litigation hold, he's staying". | Automatic |
| [`github`](skills/github) | SCM / DevOps | Branch protection and repository rulesets through `gh` — reads both gate surfaces, exports them to a file before touching anything, removes them, and restores from that export. | Clearing a merge gate for a release and putting it back exactly as it was; working out why a merge is still blocked after protection was "turned off"; a 403/404 from the branch-protection endpoint. | Automatic |
| [`i-have-adhd`](skills/i-have-adhd) | Productivity | Reshapes Claude's output for ADHD-friendly reading — leads with the next action, numbers steps, suppresses tangents. Persists for the session once invoked. | A long debugging session that has turned into a wall of text; multi-step infra work where it's easy to lose your place between turns. | Manual — `/i-have-adhd` |
| [`infra-work-ticketing`](skills/infra-work-ticketing) | Ops / Ticketing | Makes sure infrastructure work gets a ticket and a work note in Zoho ServiceDesk Plus Cloud or Jira Cloud — asks whether a ticket exists, logs the work as it happens, opens one when there isn't. Prefers the ServiceDesk Plus MCP connector so the audit trail names a person, and falls back to the `ticketctl.py` API client when it refuses. | About to change a firewall, DNS record, or AD object with no ticket open; logging what was actually done onto an existing ticket; CAB-ready change documentation. | Automatic |
| [`intune-graph`](skills/intune-graph) | Endpoint Mgmt | Microsoft Intune via Microsoft Graph — device lookup/troubleshooting, compliance and configuration profiles, Win32/LOB app deployment, bulk report exports. | "Why is this laptop non-compliant?"; pushing a sync to a set of machines; packaging and deploying a Win32 app; exporting device inventory; a 403/429 from `graph.microsoft.com`. | Automatic |
| [`jira-manager`](skills/jira-manager) | ITSM | Jira Cloud through the REST API v3 with an email + API token — JQL search, create, update fields, assign, transition, comment, log work. No MCP connector, no OAuth flow. | "What am I assigned this sprint?"; opening a ticket from the terminal; bulk-retitling or reprioritising a backlog; closing an issue and logging the time against it. | Automatic |
| [`knowbe4-admin`](skills/knowbe4-admin) | Security Awareness | KnowBe4 KSAT administration — diagnose SCIM user-sync against Microsoft Entra ID or Okta, pull Reporting API data, and route each change to the surface that actually owns it. | Users not provisioning or mass-archiving after a SCIM change; duplicate or quarantined accounts; attribute drift between the IdP and KSAT; exporting phishing or training results. | Automatic |
| [`mailgun`](skills/mailgun) | Email / Messaging | Operates a Mailgun account end to end through its API with one stdlib-only script — send (plain, HTML, templates, attachments, scheduled, test mode), receive and read inbound mail, pull events, delivery reports and stats, and configure domains, DNS verification, routes, webhooks, templates, suppressions, mailing lists, tracking, IPs, API keys and subaccounts. | Sending an email from a Mailgun domain; "was this email delivered, bounced or opened?"; checking an inbound route or inbox; pulling email stats; a 401 from the wrong region; changing domain, tracking or suppression settings. | Automatic |
| [`mermaid-svg-bitbucket`](skills/mermaid-svg-bitbucket) | Docs / DevOps | Pre-renders Mermaid diagrams to committed SVG so they display in Bitbucket Cloud, which never adopted native ```mermaid``` fences. | A README diagram that renders on GitHub but shows raw code in Bitbucket; diagram labels coming out blank; migrating docs from GitHub/GitLab to Bitbucket. | Automatic |
| [`notify`](skills/notify) | Productivity | Pings you out of band about a session or job — a two-way Telegram bot (a `question` blocks until you answer from your phone, with a topic-per-job dispatcher for concurrent jobs) or email over SMTP or an M365/Gmail MCP connector. Config-driven, global or per project. | "Tell me when this finishes"; "message me if it errors"; a long migration that needs a yes/no before it proceeds; overnight jobs you don't want to babysit. | Automatic |
| [`obsidian-canvas`](skills/obsidian-canvas) | Docs / Obsidian | Creates and edits Obsidian Canvas `.canvas` files directly as JSON (JSON Canvas spec) — architecture maps, decision trees, and boards with embedded live notes, text cards, groups, and labeled arrows; no plugin or REST bridge required. | "Map this out visually in Obsidian"; an infrastructure diagram the user can rearrange in their vault; a whiteboard view over existing notes; tweaking an existing `.canvas` without regenerating it. | Automatic |
| [`obsidian-vault-server`](skills/obsidian-vault-server) | Cloud / Infra | Self-hosted Obsidian vault on a headless Ubuntu host — containerised desktop app, obsidian.md Sync, GUI lockdown, and the Local REST API MCP endpoint reached over an SSH tunnel. | "This application requires a secure connection (HTTPS)" from an Obsidian web UI; an Obsidian MCP endpoint that will not answer on 27123; getting a workstation's plugin set onto a server vault. | Automatic |
| [`power-automate-api`](skills/power-automate-api) | Automation | Microsoft Power Automate cloud flows through the API instead of the maker portal — flow definitions, expressions the designer mangles, trigger inputs, connection references, and run history. | A flow definition that must change reliably; an expression the designer refuses; a connection reference running as the wrong identity; `InvalidAuthenticationAudience` or `AADSTS7000218` from `api.flow.microsoft.com`. | Automatic |
| [`repo-docs`](skills/repo-docs) | Docs | Generates and refreshes a whole documentation set for a codebase — `CLAUDE.md`, root and per-directory READMEs, API/function reference, architecture doc, `TODO.md`, `SECURITY.md`, `CHANGELOG.md`, handoff notes — re-runnable without clobbering human edits. | Handing a project off to someone else; "the docs are stale"; onboarding notes after a large refactor; wrapping up a substantial session. | Automatic |
| [`report-builder`](skills/report-builder) | Deprecated | **Deprecated 2026-09-10 - use [`doc-builder`](skills/doc-builder).** Redirect stub only; its report pipeline moved to `doc-builder` unchanged. | Nothing new. The stub exists so links and references to the old name still resolve. | Automatic |
| [`session-defaults`](skills/session-defaults) | Claude Code / Config | Configures how Claude Code itself behaves by default — `CLAUDE.md` instructions vs `settings.json` enforcement, permission allow/deny/ask rules and modes, hooks, default model, and which scope (user, project, local, managed) each belongs in. Inventories existing config and merges rather than clobbering. | "Stop asking me for permission every time"; "Why is Claude ignoring my `CLAUDE.md`?"; standardizing Claude Code across a team or an MDM-managed fleet. | Automatic |
| [`shipstation`](skills/shipstation) | E-commerce / Logistics | ShipStation across its three APIs (V2, legacy V1, ShipEngine) — shipments, labels, rates, carriers, warehouses, inventory, products, orders, tracking, batches, manifests. | A label or rate call returning 401/403/429; deciding between API V2 and V1; reconciling orders, shipments, or inventory across stores. | Automatic |
| [`solomon-doc-builder`](skills/solomon-doc-builder) | Docs / Reporting | Brand pack only - the Solomon Associates house style for `doc-builder`: palette, SOP template and footer. No logic of its own; installing it makes Solomon the default brand for every document. Not uninstalling it is not the off switch - `doc-builder --brand neutral` (or `DOC_BUILDER_BRAND=neutral`) is. | Installed alongside `doc-builder` so Solomon-branded output is automatic rather than something you have to remember to ask for. | Automatic |
| [`solomon-sop-maker`](skills/solomon-sop-maker) | Deprecated | **Deprecated 2026-09-10 - use [`doc-builder`](skills/doc-builder) with the [`solomon-doc-builder`](skills/solomon-doc-builder) brand pack.** Redirect stub only. | Nothing new. The stub exists so links and references to the old name still resolve. | Automatic |
| [`sophos-central`](skills/sophos-central) | Security | Sophos Central API — endpoint management (isolate, scan, tamper protection), alert triage, SIEM export, XDR/Live Discover, firewall management. | Isolating a compromised endpoint; triaging an Intercept X alert; running a Live Discover/XDR hunt; exporting SIEM events into another platform. | Automatic |
| [`terraform-docs-readme`](skills/terraform-docs-readme) | IaC / Docs | Regenerates a Terraform module's `README.md` with `terraform-docs` — wires up `.terraform-docs.yml`, the `main.tf` header block, `footer.md`, and the `BEGIN_TF_DOCS`/`END_TF_DOCS` injection markers, and diagnoses why a variable, header, or footer isn't showing up. | A module README out of date after new variables or outputs; "the docs table is missing a variable"; a header or `footer.md` that isn't picked up; first-time terraform-docs setup. | Automatic |
| [`visio-diagrams`](skills/visio-diagrams) | Docs / Diagrams | Generates native Visio `.vsdx` from a YAML/JSON spec with a stdlib-only writer (no Visio install, works in CI), or drives Visio over COM when real stencil masters, themes, or swimlanes are required — plus SVG preview, OPC verification, and reading/retitling an existing `.vsdx`. | "Make a Visio of our prod network"; turning a subnet list into a topology diagram; a CAB/audit or as-built diagram someone else has to edit; converting Mermaid to `.vsdx`; retitling shapes in an approved corporate template. | Automatic |
| [`wazuh-onprem`](skills/wazuh-onprem) | Security / SIEM | Self-hosted Wazuh across all four surfaces — Server API, Indexer API, Dashboard saved-objects API, and `ossec.conf` over SSH. | Searching `wazuh-alerts` to build an incident timeline; wiring Slack/PagerDuty alerting into `ossec.conf`; onboarding an O365 or Cloudflare log feed; backing up or migrating dashboards. | Automatic |
| [`web-research`](skills/web-research) | Research | Live-web research through the Perplexity MCP server — registered by hand or by menu row 25 of the install scripts, and routes each question to `perplexity_search`, `_ask`, `_research` or `_reason`, applies recency and domain filters, and hands library/API reference to Context7 instead. | "What's the latest on X?"; current pricing or a CVE for a product; "is this still true"; comparing vendors; anything where training data would be stale. | Automatic |
| [`web-testing-playwright`](skills/web-testing-playwright) | Testing / QA | Drives a real browser with Playwright — screenshots at multiple viewports, console errors, failed network requests, form and login flows — plus browser setup for Windows and Linux. | "Is my site up?"; a page rendering blank with a JS error; verifying a login or checkout flow end to end; a layout that breaks at mobile viewport. | Automatic |
| [`work-log-reporter`](skills/work-log-reporter) | Productivity | Keeps a committed per-session `work-log/` of what was done and what was touched, then generates a formatted email report with a PDF attachment and sends it over SMTP. | End-of-day or standup writeup; "email my manager what I worked on"; a billable record of which systems, databases, and tables were touched. | Automatic |

"Automatic" means Claude decides to invoke the skill on its own when the conversation matches the skill's `description` trigger — no slash command needed. "Manual" means the skill sets `disable-model-invocation: true` and must be invoked explicitly (e.g. `/i-have-adhd`).

### Adding a new skill

1. Read [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md).
2. Create `skills/<skill-name>/SKILL.md` (kebab-case directory name matching the `name:` frontmatter field exactly).
3. Follow [`Skill-Pipeline.md`](Skill-Pipeline.md) to validate, review, and register the skill in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) so the team can install it.
4. Add a row to the table above **and** to [`skills/README.md`](skills/README.md) — keep both in sync. Fill all five columns; **Use cases** should be concrete scenarios that would send someone looking for the skill ("a 403 from `graph.microsoft.com`", "the docs are stale"), not a restatement of *What it does*.

<!-- END skills/README.md -->

## Plugins

The canonical, always-current version of this section lives in [`plugin/README.md`](plugin/README.md) — it's reproduced here so it's visible without an extra click. The per-plugin detail lives in [`plugin/PLUGINS.md`](plugin/PLUGINS.md).

<!-- BEGIN plugin/README.md -->

Each subdirectory in [`plugin/`](plugin/) is a self-contained [Claude Code plugin](https://docs.claude.com/en/docs/claude-code/plugins) — a `.claude-plugin/plugin.json` manifest plus any `agents/`, `commands/`, `hooks/`, or `skills/` it bundles. Every one is registered in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) and installs the same way a skill from [`skills/`](skills/) does.

**A plugin is not a bigger skill.** A skill is a document Claude reads when the conversation matches its `description`. A plugin can also register **subagents** (their own context window and tool set), **slash commands** (you type them), and **hooks** (deterministic shell scripts the harness runs on tool use, on stop, or on notification — they execute whether or not Claude agrees with them). That last part is why plugins here are opt-in in the install scripts and skills are not: a hook can block a command you ran on purpose.

### Overview

| Plugin | Category | What it does | Use cases | Provides |
|---|---|---|---|---|
| [`crew`](plugin/crew) | Workflow / QA | A virtual dev team for multi-repo legacy work — file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure instead of offering an opinion. Hooks enforce unverified turns and unearned production deploys. The old PreToolUse command guard was removed in 0.19.52; since 0.20.22 an opt-in cloud/destructive guard (`guards.cloudGuard`, off by default) inspects Bash and PowerShell commands before they run. Roles exist only where they buy an isolated context window, a restricted tool set, or genuinely independent eyes — four agents in 1.0, with stack knowledge as on-demand skills — and BA/architecture stay files and commands. Codex QA, Jira or ServiceDesk Plus, an Obsidian Kanban board for tickets, Obsidian memory, a code graph, and Teams/Telegram notifications are all optional. | Several repositories, mixed stacks, legacy code, and almost no test coverage; a change that needs review by something that did not write it; a turn that should fail when the checks its changed paths map to go red; a production deploy that should be refused unless qa signed off on **that exact sha** and the rollback runbook is still verified; wanting to know what every endpoint and scheduled job actually does; losing the thread across a `/clear` or an auto-compact; wanting a plan approved before any edit and a scope audit before a ticket closes — bounded so it fixes only what blocks the job and tickets the rest. | 4 agents, 36 commands, 31 skills<!-- claim: plugin-skills:crew -->, 34 hook entries |
| [`gizmoduck`](plugin/gizmoduck) | Security | Runs [Nuclei](https://github.com/projectdiscovery/nuclei) vulnerability scans against hosts and websites you are authorised to test, or the whole scanner routine (checkov, trivy, dependency-check, semgrep, ZAP, testssl, nmap, nikto) from one manifest, then does the part that usually gets skipped: diffs the run against a previous baseline so you see what is genuinely new, renders a triaged report as Markdown, HTML or PDF, and opens or syncs ServiceDesk Plus tickets for Critical and High findings. Nuclei is MIT-licensed and self-hosted, so the whole loop runs locally with no export step and no API quota. Bootstrap scripts for WSL/Linux and Windows fetch the engine and the community template set; `/gizmoduck:doctor` tells you which half of the toolchain is missing rather than failing mid-scan. Registers no hooks and no agents — it is six commands over one Python CLI. | Wanting a scheduled external scan whose findings land in the ticket queue instead of a PDF nobody opens; needing to show an auditor what changed between this quarter's scan and last quarter's; a scan whose Critical and High findings should become tickets after one batch confirmation while the Mediums stay in the report; re-rendering a report at a different severity floor without paying for another scan; a scanner that stops working on a new machine and you want to know whether it is `nuclei`, the templates, `python`, or `wkhtmltopdf`. | 6 commands, 1 skill |
| [`localgpu`](plugin/localgpu) | Local models | Runs models on your own GPU through [Ollama](https://ollama.com) and puts a repository or folder behind them: `bootstrap.sh` / `bootstrap.ps1` install Ollama, a private virtualenv, the chat and embedding models, and a `localgpu` CLI, then an MCP server indexes a tree into a vector store on disk and exposes search and ask over it. Nothing is a service call — no prompt, no file, and no embedding leaves the machine, which is what makes it usable on code that is not allowed to reach a vendor API. `localgpu shell` goes further and runs a *whole separate* Claude Code session on the local model, through a bundled proxy that translates the Anthropic Messages API into Ollama's `/api/chat` — the two do not otherwise speak, and a client pointed straight at Ollama 404s on every request. `/localgpu:doctor` tells you which half of the toolchain is missing (Ollama, the venv, a pulled model, a built index) rather than failing mid-answer, and `/localgpu:crew` reports which `crew` roles a local 7B could take over and refuses, in writing, to point crew's gates at one. Registers no hooks and no agents — six commands, one bundled skill, an MCP server you register yourself in `/localgpu:setup`, and a `localgpu` CLI its bootstrap installs into the venv. | Code or documents that are not permitted to leave the network but still need a model over them; wanting to ask "where is this handled" against a repo too large to read into a context window; a laptop or workstation with a GPU sitting idle while every query bills a vendor; wanting a throwaway session that runs entirely on the local model for exploring and drafting; wanting an honest account of which `crew` work a local 7B could take over and which it must not; an offline machine, a flight, or an outage at the provider; a first-run failure where you want to know whether it is Ollama, the venv, the model pull, or the index. | 6 commands, 1 skill, 1 CLI — no agents, no hooks, plus one local MCP server `/localgpu:setup` registers |
| [`obsidian-vault`](plugin/obsidian-vault) | Memory | Makes one or more Obsidian vaults Claude Code's durable, token-efficient memory. Cross-platform, multi-vault setup for the Local REST API bridge and MCP registration (one server per vault, never one juggling two), a vault-contract guard hook whose frontmatter and ASCII rules ship off until a target vault's own `CLAUDE.md` says to turn them on, with only the canvas shape check on by default, gardening and reflection agents with no fabricated citations, canvas and Map-of-Content generation, and `graphify` wiring into a separate, dedicated codegraphs vault. No vault path is hardcoded — it detects from Obsidian's own vault registry or a config file. Named `obsidian-vault`, not `obsidian`, so it cannot collide with a third-party plugin of that name. | Wanting Claude Code sessions to remember architecture decisions and patterns across `/clear` without re-explaining them; a second machine-generated vault (a code graph running past 100k notes) that needs different defaults than a hand-curated one; an Obsidian Git plugin auto-committing on a timer into a directory that turns out not to be a git repo; a vault whose own `CLAUDE.md` has drifted from what the filesystem actually shows; wanting a canvas or Map of Content that stays a spatial/structural aid rather than a second, driftable copy of facts already in notes. | 11 commands, 2 agents, 3 skills, 8 hook entries |
| [`rule-of-two`](plugin/rule-of-two) | Review | Runs two adversarial reviewers from different model families — a Claude agent on Fable and a Codex agent on `gpt-6-astra` — over the same Claude Code agent, skill or plugin, against one shared rubric, with neither seeing the other's findings. Returns a viability verdict (VIABLE / VIABLE WITH CHANGES / NOT VIABLE AS WRITTEN), strengths, weaknesses, cited defects and the edits worth making. Its headline reports coverage rather than assuming it: if Codex is missing, unauthenticated or its model retired, the report says plainly that this is one review and not two, and if the two models cannot be resolved to families it says "could not tell" instead of claiming independence. | Wanting a genuinely adversarial second opinion on a skill or plugin before shipping it, rather than a polite reading from the same model family that wrote it; checking whether a new agent's description will actually trigger; deciding whether an artifact is worth shipping at all or duplicates something that already exists. | 2 commands, 1 agent |

**Provides** counts what the plugin registers with Claude Code. The per-item breakdown — every command, agent, bundled skill, and hook event — is in [`plugin/PLUGINS.md`](plugin/PLUGINS.md); the authoritative upstream guide is [`plugin/crew/README.md`](plugin/crew/README.md).

### Hooks only run where hooks run

Bundled **skills** work in Claude Code, Claude chat, Claude Desktop's Chat tab, and Cowork. Bundled **hooks and subagents** run only in Claude Code and Cowork — they are greyed out in chat. Installing a plugin on claude.ai does not install it in your terminal, and vice versa; the file format is shared, the installation is not. Since `crew` is mostly hooks, subagents, and slash commands operating on a local git repository, installing it on the web gives you the bundled skills' written guidance and nothing that executes.

### Adding a new plugin

Same four-place rule the skills follow, plus a couple. Full checklist in [`plugin/README.md`](plugin/README.md); the short version:

1. Create `plugin/<plugin-name>/.claude-plugin/plugin.json` — kebab-case directory name matching the `name` field exactly. No `marketplace.json` inside a plugin directory; the repo root's is the only marketplace here.
2. Think about the shell before registering a hook. A `hooks.json` entry's `shell` field (`"bash"` or `"powershell"`) is documented and Claude Code does read it, but a bare `command` with no `shell` field still goes to Git Bash on Windows by default (PowerShell only when Git Bash isn't installed) — so don't assume some other `bash` on `PATH` is what runs it. A hook that judges a *command* branches on `tool_name`, not OS. A blocking hook also needs a committed, sabotage-tested regression suite.
3. Register it in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) (`source` is `./plugin/<name>`), the table above, [`plugin/README.md`](plugin/README.md), [`plugin/PLUGINS.md`](plugin/PLUGINS.md), and both install scripts (`PLUGIN_KEYS` / `PLUGIN_NAME` in the `.sh`, `$script:PluginCatalog` in the `.ps1`).
4. Default its menu item to **off** if it registers hooks.

<!-- END plugin/README.md -->

## License

GNU GPL v2 (`GPL-2.0-only`) applies to every plugin in this marketplace — see [`LICENSE`](LICENSE). Each plugin's own `plugin.json` declares the same `license` field, and `scripts/check-marketplace.py`'s `check_license_consistency` gate fails the build if any plugin drifts from it.

`plugin/crew/NOTICE.md` records third-party MIT-licensed code copied into that plugin (from [superpowers](https://github.com/obra/superpowers), © 2025 Jesse Vincent). MIT-into-GPL-2 is a lawful direction of copy; that notice discharges the attribution obligation independently of the licence declared above.

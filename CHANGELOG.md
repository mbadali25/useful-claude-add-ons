# Changelog

All notable changes to this repository are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows the `version` field on each plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) rather than a single repo-wide version, since skills ship independently.

## [Unreleased]

### Removed

- `skills/ppt-master` — a vendored copy of the upstream `hugohe3/ppt-master` plugin
  (12,230 files, 88 MB) that was never registered in `marketplace.json`, either
  README, or either install script's skill catalog, so nothing here ever offered it.
  The installer already installs the same plugin from its own marketplace as part of
  menu item 6 (Community marketplaces + plugins), so removing the copy changes nothing
  for anyone running the bootstrap — it just stops the repo carrying 88 MB of upstream
  code it would have to re-sync by hand. This also clears the Pylint CI failure: 845
  of the 855 findings were in that tree.

### Fixed

- `skills/notify/scripts/*.py` — the four config reads now pass `encoding="utf-8"` to
  `Path.read_text()`. Without it Python picks the locale encoding, which is cp1252 on
  Windows, so a `config.json` containing any non-ASCII character (an em dash in a
  subject template, a non-Latin chat title) raised `UnicodeDecodeError` for Windows
  users only. Also split the comma-form imports and wrapped two over-length lines, so
  `pylint $(git ls-files '*.py')` is back to 10.00/10.

### Added

- `skills/notify` — a new skill (1.0.0) that pings you out of band about a session or
  job: a two-way Telegram bot (a `question` event blocks until you reply from your
  phone, and a `notifyd` dispatcher gives each concurrent job its own forum topic) or
  email over SMTP or an M365/Gmail MCP connector. Registered in `marketplace.json`,
  both READMEs, `INSTALLATION.md`, and both install scripts, taking this repo's
  catalog from 19 skills to 20.

- `scripts/install-prerequisites.ps1` / `.sh` — **the `notify` skill asks about setup.**
  It is the only skill here that needs anything on the machine, so ticking it prints
  its prerequisites alongside the menu (Python 3.8+, a `@BotFather` token, a `chat_id`,
  `TELEGRAM_BOT_TOKEN` exported, a config file, polling mode with no webhook) and then
  asks whether to scaffold `~/.config/notify/config.json`. Answering yes checks for
  Python and writes a starter config; it never overwrites an existing one and never
  writes the bot token anywhere. `--notify-setup` / `-NotifySetup` answers yes without
  asking; `--all` / `--non-interactive` prints the prerequisites and skips the
  scaffold. Because `notify` is a sub-picker entry rather than a top-level menu key,
  the gate reads the skill catalog (`skill_selected` / `Test-SkillSelected`) instead of
  `is_selected` / `Test-Selected`, which would never match.

- `CLAUDE.md` — repo-level instructions for Claude Code. Two documentation rules are
  stated as requirements rather than suggestions: an edit to either install script
  must update `README.md` (menu table, "what each item installs" table, switch table,
  and any prose that names an item by number) in the same change, and a new directory
  under `skills/` is not finished until it is registered in all four places —
  `marketplace.json`, `skills/README.md`, `README.md`, and both install scripts.

- `scripts/install-prerequisites.ps1` / `.sh` — **the Claude Code CLI row now checks
  for an update** when `claude` is already installed, instead of reporting the version
  and moving on. It compares the local version against the npm registry and runs
  `npm install -g @anthropic-ai/claude-code@latest` only when they differ. The version
  is read from the last line of `claude --version` (which prints
  `2.1.226 (Claude Code)`, and can be preceded by a wrapper's banner).
  `-NoUpdate` / `--no-update` reports the installed version and skips the check.

- `scripts/install-prerequisites.ps1` / `.sh` — **five new opt-in menu items**:
  - **Supabase** (15) — `supabase@claude-plugins-official`, through the same
    detect-then-install helper as every other plugin.
  - **Context7** (16) — `npx -y ctx7@latest setup`. The wizard is interactive, so bash
    hands it the terminal explicitly (under `curl | bash`, fd 0 is still the script);
    with no terminal at all both scripts print the command rather than hang.
  - **Playwright CLI** (17) — `npm install -g @playwright/cli@latest`, detected by
    whether `playwright-cli` already resolves on `PATH`.
  - **SkillUI** (18) — `skillui`, plus `playwright` and its Chromium build. Playwright
    is installed **globally**; upstream's `npm install playwright` would leave a
    `node_modules` tree in whatever directory the script was run from. Both Playwright
    steps warn rather than fail the item. A quick start is printed afterwards; you're
    asked up front, and `--skillui-guide` / `-SkillUIGuide` answers yes without asking.
  - **Strix** (19) — upstream's own installer, `curl -sSL https://strix.ai/install |
    bash`. Installing it is not enough to run it, so the next steps (Docker running,
    `STRIX_LLM`, `LLM_API_KEY`) print on every run, including one that skipped the
    install. Windows has no POSIX shell, so the script runs the installer through WSL,
    falls back to Git Bash, and warns with the manual command if neither exists.

- `scripts/install-prerequisites.ps1` / `.sh` — the install menu is now a **cursor
  picker**: ↑/↓ to move, Space to tick, Enter to start, `A`/`N`/`D` for all/none/
  defaults, `Q` or Escape to cancel. Rows scroll inside a viewport when the window
  is short, and every printed line is clipped to the window width, because a
  wrapped line breaks the redraw and smears the menu over whatever was above it.
  The numbered prompt is still there as the fallback and is chosen automatically
  when raw key input is not possible — no terminal, no `stty`, `TERM=dumb`,
  PowerShell ISE, a redirected console, or a window under ten lines. Bash restores
  the saved `stty` state and the cursor from an `EXIT`/`INT` trap so Ctrl-C in the
  menu cannot leave the user's shell with echo off.

- `scripts/install-prerequisites.ps1` / `.sh` — **individual skills can be
  installed instead of all nineteen**. Pressing → on the repo's row opens a second
  picker listing every skill in this repo; `-Skills 'cloudflare,drata'` /
  `--skills cloudflare,drata` does the same non-interactively and also accepts
  `all`, `none`, and positions (`1,4-6`). It composes with `-All` /
  `-NonInteractive`, so CI can install everything except the skills, or only the
  skills. The catalog (`SKILL_KEYS` in bash, `$script:SkillCatalog` in PowerShell)
  is now the single source of both the picker rows and the install loop, replacing
  the duplicated `own_plugins` / `$ownPlugins` arrays. The repo's menu row shows a
  live count (`+ 3 of 19 skills`) rather than a hardcoded nineteen.

- `skills/infra-work-ticketing` — `ticketctl.py` gained **`update`** and
  **`close`**, so the API fallback covers all four write verbs rather than just
  `create` and `note`. `update` sets title, status, priority, category,
  subcategory, group, technician, urgency, impact, type and (on SDP) the
  resolution and an `--update-reason` for the audit trail; `close` takes a closure
  comment, `--closure-code`, and `--requester-ack`. On Jira, `close` looks the
  transition up by name from the issue's own transition list rather than
  hardcoding an id, and `--category` maps to a component — the nearest equivalent
  Jira has. Both go through the same build/execute split as the existing verbs, so
  `--dry-run` covers them.

  Two limits are documented rather than papered over. **Closing through
  `ticketctl.py` is not equivalent to `sdp_close`**: SDP Cloud v3 has no close
  sub-resource, so the fallback PUTs a terminal status plus `closure_info` to the
  edit endpoint and a desk with mandatory closure rules can reject it. And
  **nothing can create or rename a category** — the v3 API documents no endpoint
  for the taxonomy and the connector's metadata tool is read-only, so that stays
  an SDP admin-UI job. Setting the category on a ticket works from either path.

- `skills/infra-work-ticketing` — an `mcp` block in the config file records how
  ticket writes are routed: connector name, endpoint, tool prefix, whether to
  prefer MCP, and which `ticketctl.py` provider takes over when it refuses.
  `ticketctl.py doctor` prints the resolved routing and probes the connector's
  `/health` (5-second timeout, `--no-mcp-probe` to skip). Routing metadata only —
  the connector authenticates per person through Claude Code, so no credential
  belongs in the block. `INFRA_TICKET_PREFER_MCP` and `INFRA_TICKET_MCP_ENDPOINT`
  override it per session.

### Removed

- `scripts/install-prerequisites.ps1` / `.sh` — **six menu items**: the Firecrawl,
  Chrome DevTools, and Glyphs MCP servers, the OmniRoute gateway, Headroom, and GSD.
  The helpers that existed only for them went with them: `tcp_port_open` and
  `add_mcp_http_server` in bash, `Test-TcpPort`, `Get-PythonLauncher`,
  `Add-UserScriptsToPath` and `Get-PipxPythonArgs` in PowerShell, along with the
  `FIRECRAWL_API_KEY` prompt, the OmniRoute guided-setup question, and the Headroom
  mode question. The `-HeadroomMode` / `--headroom-mode` switch is gone.

  The menu is 19 items rather than 20, and items 1–10 are the default set (was 1–11).
  Item numbers below 10 are unchanged; everything above shifted. Scripted runs should
  use the stable keys (`--select supabase,strix`) rather than positions.

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — the per-skill picker's descriptions are
  fuller: each of the nineteen rows now names what the skill actually does rather than
  restating its title (`cloudflare - Cloudflare v4: DNS, WAF, cache, Workers, Zero
  Trust`). Text is sourced from the skills table in `README.md`. The rows are written
  for a window of about 95 columns; narrower consoles clip them with an ellipsis, as
  they already did for the longest of the old labels.

### Fixed

- `skills/infra-work-ticketing` — a `ticketctl.py` write that failed while
  *planning* rather than sending was not queued, so the text was lost. Resolving
  `#40219` to an internal id is itself an API call, which means a down service desk
  failed in exactly that window. Planning is now inside the guarded region for
  `note`, `update` and `close`. `--dry-run` still never queues.

- `scripts/install-prerequisites.ps1` / `.sh` — a picker that failed *after* the
  capability gate passed did not fall back. In bash the failure return was ignored,
  leaving an empty selection that printed `Nothing to do.` and exited 0 — the same
  output as a deliberate cancel. In PowerShell, `$ErrorActionPreference = 'Stop'`
  meant a `SetCursorPosition` throw (a window shrunk between frames) killed the
  whole installer. Both now drop through to the numbered menu and say why. The
  capability gate only ever proved the picker could *start*.

- `scripts/install-prerequisites.sh` — the `/dev/tty` probe printed
  `No such device or address` to stderr on hosts without a controlling terminal.
  The redirection is now grouped so `2>/dev/null` actually covers it.

- `scripts/install-prerequisites.ps1` — hiding the cursor threw
  `"The handle is invalid"` on hosts that don't implement `Console.CursorVisible`,
  which would have taken the whole menu down with it. It is cosmetic, so it is now
  best-effort.

- `skills/visio-diagrams` — creates, edits, and verifies Microsoft Visio `.vsdx`
  files. Two paths from one spec: a stdlib-only writer (`vsdx_writer.py` +
  `diagram_from_spec.py`) that generates a native `.vsdx` plus an SVG preview
  with no Visio install and no third-party packages, so it runs in CI and on
  air-gapped boxes; and PowerShell COM automation (`New-VisioDiagram.ps1`) for
  real stencil masters, themes, containers, and swimlanes. Also covers reading
  and retitling an existing `.vsdx` via the `vsdx` package (the template + data
  pattern that preserves corporate stencils). Leads by challenging whether Visio
  is the right output at all, and refuses to call a file verified when
  `verify_vsdx.py` could only check OPC structure. Two reference files (`.vsdx`
  OOXML format and symptom → cause table, COM automation). Registered in
  `.claude-plugin/marketplace.json` and both install scripts — 19 skills total.

- `skills/claude-code-defaults` — configures how Claude Code itself behaves by
  default. Separates instructions (`CLAUDE.md`, `.claude/rules/`, loaded into
  context) from enforcement (`settings.json`, permission `allow`/`ask`/`deny`,
  hooks, applied by the client), and routes a request to the right file at the
  right scope — user, project, local, or managed. Inventories existing config
  and merges rather than clobbering, backs up before editing, validates the JSON,
  and verifies via `/status`, `/context`, and `/doctor`. Four reference files
  (permissions, CLAUDE.md, settings keys, copy-paste templates for solo/shared/
  locked-down/fleet). Refuses to hand out `bypassPermissions` as a default.
  Registered in `.claude-plugin/marketplace.json` and both install scripts —
  18 skills total.

- `scripts/install-prerequisites.ps1` / `.sh` — the VoltAgent
  [`awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents)
  collection is now installed as plugins from its own marketplace
  (`voltagent-subagents`), all ten category plugins: `voltagent-core-dev`,
  `-lang`, `-infra`, `-qa-sec`, `-data-ai`, `-dev-exp`, `-domains`, `-biz`,
  `-meta`, `-research`.

- `scripts/install-prerequisites.ps1` — `-InstallScope` (aliased to the old
  `-PluginHubScope`) now applies `--scope` to *every* marketplace and plugin
  install, not just the community set. Same for `--scope` on the Linux script.

- `skills/terraform-docs-readme` — regenerates a Terraform module's `README.md`
  with `terraform-docs`. Covers first-time setup (`.terraform-docs.yml`, the
  `main.tf` narrative header block, `footer.md`, the `BEGIN_TF_DOCS`/`END_TF_DOCS`
  injection markers) as well as re-runs after variables, outputs, or resources
  change, and diagnoses the usual failures — missing markers, a header that
  isn't picked up, a footer that isn't rendered, a version older than 0.16.
  Ships a stdlib-only, read-only preflight script and copy-ready assets.
  Registered in `.claude-plugin/marketplace.json` and in both install scripts.

- `skills/cisco-meraki` — Cisco Meraki Dashboard API v1 skill for a single
  organization, covering MX/MS/MR. Reads inventory, device status, the network
  event log, the org configuration change log, MX security/IDS events, and Air
  Marshal; runs live diagnostics (ping, cable test, throughput, ARP/MAC table,
  wake-on-LAN); and makes configuration changes behind a snapshot → diff →
  confirm gate with single-command rollback. Bulk changes route through staged
  Action Batches so Meraki validates the payload server-side before commit.
  Stdlib-only Python, no pip install. Includes the repo's first unit test suite
  (`python -m unittest discover -s skills/cisco-meraki/tests -p "test_*.py"`).

### Changed

- `scripts/install-prerequisites.ps1` / `.sh` — **all marketplace and plugin
  installs now use the native `claude plugin marketplace add` and `claude plugin
  install` commands.** The `npx -y claudepluginhub <repo>` wrapper is gone, along
  with the `Invoke-PluginHub` / `pluginhub` helpers that called it. The wrapper
  registered each repo as a *local directory* marketplace under a generated name
  (`cpd-<repo>-user`) that the scripts' own detection could not match, so those
  plugins were reinstalled on every run, and it was a recurring source of Windows
  failures. Marketplace names are now taken from each repo's own
  `.claude-plugin/marketplace.json` — notably `fcakyon/claude-codex-settings`
  publishes itself as `claude-settings`, which the old name-or-repo detection
  never matched either.
- `scripts/install-prerequisites.ps1` / `.sh` — claude-mem installs through its
  marketplace (`claude plugin marketplace add thedotmack/claude-mem` +
  `claude plugin install claude-mem@thedotmack`) instead of
  `npx claude-mem install`. Upstream documents both paths. `find-skills` and GSD
  still use `npx`: neither publishes a Claude Code marketplace.
- `MARKETPLACE.md` / `INSTALLATION.md` — bootstrap command lists rewritten to
  match, with the repo-name-vs-marketplace-name trap called out explicitly, and
  a troubleshooting row for leftover `cpd-*-user` marketplaces.

### Removed

- `scripts/install-prerequisites.ps1` — the `Resolve-GitRoot` and
  `Register-GitBash` helpers, plus the `C:\repos\awesome-claude-code-subagents`
  clone and its `bash install-agents.sh` invocation. Its Linux counterpart
  (`~/repos/...` clone) is gone too. That step needed Git Bash on Windows and so
  failed outright on a non-elevated run, where Chocolatey — and therefore `git` —
  had already been skipped. An existing checkout from an earlier run is now
  unused and safe to delete.
- `aiskillstore/marketplace` and its `xlsx` / `mcp-integration` entries. That
  repo is the Skill Store content repo, not a Claude Code marketplace (no
  `.claude-plugin/marketplace.json`), so there is no native
  `claude plugin install` for it. `anthropic-office-skills@claude-settings`
  replaces `xlsx`; either skill can still be installed by hand with
  `npx skillstore add aiskillstore/<skill>`.

- `scripts/install-prerequisites.ps1` / `.sh` — the `find-skills`
  (`vercel-labs/skills`) step is now prompted rather than unconditional, and is
  detected before it runs. It installs as a user-level skill, not a Claude Code
  plugin, so detection is a filesystem check on
  `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/find-skills/SKILL.md`. Already
  installed: the prompt offers a re-install for updates; `-NoUpdate` /
  `--no-update` skips it entirely. The step now also verifies the skill actually
  landed on disk instead of trusting the installer's exit code.

### Fixed

- `skills/terraform-docs-readme` arrived double-nested
  (`skills/<name>/<name>/SKILL.md`) with a leftover `terraform-docs.zip` and a
  zip-oriented `INSTALL.md` — the same layout problem fixed for `aws-opensearch`
  and `intune-graph` in the 2026-07-28 baseline. Flattened to the standard
  `skills/<name>/SKILL.md` layout; the duplicate tree, the archive, and the
  now-inaccurate `INSTALL.md` were removed (installation for this repo's skills
  is covered by `INSTALLATION.md` and `MARKETPLACE.md`).
- `INSTALLATION.md`'s "What the own-marketplace step installs" list was stale at
  10 skills and missing `cisco-meraki`, `infra-work-ticketing`, `repo-docs`,
  `shipstation`, `web-testing-playwright`, and `work-log-reporter`. Now lists all
  17, matching `marketplace.json`, `skills/`, and both install scripts.

## [2026-07-28]

### Added

- DevOps scaffolding for distributing skills to the team: `Skill-Authoring-Standard.md`, `Skill-Pipeline.md`, `SECURITY.md`, `INSTALLATION.md`, `MARKETPLACE.md`, this `CHANGELOG.md`.
- `.claude-plugin/marketplace.json` — registers this repo as a Claude Code plugin marketplace with one plugin entry per skill.
- `scripts/install-prerequisites.ps1` and `scripts/install-prerequisites.sh` — bootstrap Git, AWS CLI (Windows) / native package manager (Linux), Node.js, Python, the Claude Code CLI itself (with `PATH` export), and the team's standard marketplaces/plugins (Superpowers, find-skills, GSD, claude-mem, frontend-design, excalidraw-generator).
- Populated `skills/README.md` with a skill overview table (name, category, purpose, invocation mode) for all 10 skills.
- Root `README.md` now embeds the skills overview and links every new doc.
- Populated root `.gitignore`.

### Fixed

- `aws-opensearch` and `intune-graph` skill directories were double-nested (`skills/<name>/<name>/SKILL.md`), breaking the standard `skills/<name>/SKILL.md` discovery convention and marketplace `source` paths. Flattened to the standard layout.

### Skills present as of this baseline

`aws-opensearch`, `bitbucket`, `checkpoint-email`, `cloudflare`, `drata`, `i-have-adhd`, `intune-graph`, `mermaid-svg-bitbucket`, `sophos-central`, `wazuh-onprem` — see [`skills/README.md`](skills/README.md) for details on each.

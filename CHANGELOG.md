# Changelog

All notable changes to this repository are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows the `version` field on each plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) rather than a single repo-wide version, since skills ship independently.

## [Unreleased]

### Added

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

- `skills/infra-work-ticketing` — an `mcp` block in the config file records how
  ticket writes are routed: connector name, endpoint, tool prefix, whether to
  prefer MCP, and which `ticketctl.py` provider takes over when it refuses.
  `ticketctl.py doctor` prints the resolved routing and probes the connector's
  `/health` (5-second timeout, `--no-mcp-probe` to skip). Routing metadata only —
  the connector authenticates per person through Claude Code, so no credential
  belongs in the block. `INFRA_TICKET_PREFER_MCP` and `INFRA_TICKET_MCP_ENDPOINT`
  override it per session.

### Fixed

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

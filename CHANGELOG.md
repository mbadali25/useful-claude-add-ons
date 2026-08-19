# Changelog

All notable changes to this repository are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows the `version` field on each plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) rather than a single repo-wide version, since skills ship independently.

## [Unreleased]

### Added

- **`claude-memories-vault` and `claude-memories-canvas` skills — the conventions of the
  `claude-memories` Obsidian vault, written on the workstation during the 2026-08-19
  memory migration and only now given a canonical home.** `claude-memories-vault` covers
  the folder layout, the six required frontmatter fields, the `type`/`status` value sets
  the `HOME.md` Dataview queries filter on, how wikilinks resolve by *filename* on Windows
  (a `:` cannot appear in one, so the link must match the file and not the prose), the
  `vault-lock.ps1` write lock the nightly gardener respects, the single-writer rule on
  `inbox/pending-reflect.md`, and the decision rule for vault versus Claude Code
  auto-memory. `claude-memories-canvas` covers the `wiki/maps` node and edge schema
  actually in use, the colour and id styles, the column-and-group geometry, and the two
  rules that make a canvas findable at all: facts live in notes because a canvas-only fact
  is invisible to search, and every canvas is linked from its `Project - *.md` because
  canvases do not backlink.

  Both keep the concrete `C:\repos\claude-memories` path rather than a placeholder — the
  same choice `vault-automation/` already makes with its `-VaultPath` default — because
  these are the conventions of one real vault and a parameterised version has never been
  tested. Both name their siblings explicitly in the `description`: the generic
  `obsidian-canvas` for any other vault, and `obsidian-vault-server` for hosting one.
  `obsidian-canvas` gained a matching one-line pointer back.

- **`obsidian-vault-server` skill — a self-hosted Obsidian vault on a headless Ubuntu
  host.** The real Obsidian desktop app in a container (Sync has no headless client, so
  there is no other way), signed in to an obsidian.md account, with the
  `obsidian-local-rest-api` plugin's built-in MCP endpoint reached over an SSH tunnel —
  no separate MCP server process. Three references cover install, the Claude wiring, and
  getting a workstation's plugins onto the server. The safety rails are the point: the
  container's web GUI has a terminal with passwordless `sudo`, so the skill treats
  firewalling it and never overwriting the REST API key as non-negotiable rather than
  advisory.

- **`claude-obsidian-setup/` now installs the Obsidian community plugin set.** The setup
  scripts installed *Claude Code* plugins but never the Obsidian plugins a working vault
  needs. `obsidian-plugin-profile.json` pins 15 community plugins with their repos plus
  the 27 core plugins to enable, and `install-obsidian-plugins.ps1` / `.sh` install them
  from GitHub releases. Same house contract as the setup scripts: dry run by default,
  `--apply` / `-Apply` to write, PASS/FIX/FAIL against stable check ids, idempotent.
  Additive — `community-plugins.json` and `core-plugins.json` are unioned with whatever
  the vault already enables, in both the list and object-map shapes. Verified on both
  platforms: 15/15 at pinned versions, second run all PASS, pre-existing entries kept.

- **Menu item: `obsidian-mcp` — register the Obsidian vault server's MCP endpoint.** Off
  by default, on both scripts, with identical keys and order. Not a launched command: the
  endpoint is a plugin already running in the vault-server container, listening on the
  *server's* loopback, so the URL is a local port forwarded by SSH. The API key is
  per-deployment and cannot be baked in, so without `-ObsidianMcpKey` /
  `--obsidian-mcp-key` the item explains how to get one and skips rather than failing.
  `Add-McpServer` / `add_mcp_http_server` gained header support for the bearer token.

- **`vault-automation/` — self-feeding vault pipeline.** New component that automates
  the Obsidian memory loop end to end: Claude Code `SessionEnd`/`PreCompact` hooks
  queue every session into `inbox/pending-reflect.md`; a nightly `Claude Vault
  Gardener` scheduled task runs headless Claude to distill queued sessions into
  source-cited `wiki/concepts` pages and `wiki/daily` digests (with a provenance pass
  that promotes well-attested concepts); a `HOME.md` Dataview dashboard surfaces
  stale/unsourced concepts and the live queue; five community plugins installed
  file-level. Obsidian-Sync-aware: git is an optional layer (`-UseGit`/`-GitRemote`)
  and the gardener skips git operations on git-less vaults. Dry-run by default,
  idempotent, documented in `vault-automation/README.md` (incl. run-the-gardener-on-
  one-machine-only and cost/safety notes). Root README gained a "Vault automation"
  section with the run commands.

### Fixed

- **The installers' skill catalogs had fallen two skills behind the marketplace.**
  `obsidian-canvas` and `obsidian-vault-server` were registered in
  `.claude-plugin/marketplace.json` and `skills/README.md` but never added to
  `SKILL_KEYS`/`SKILL_NAME` in `install-prerequisites.sh` or `$script:SkillCatalog` in
  the `.ps1`, so the per-skill picker offered 21 of the 23 that existed and neither could
  be selected by name. Both were also missing from the `<!-- BEGIN skills/README.md -->`
  mirror in the root `README.md`, which had silently stopped being a mirror. Both are in
  the catalogs and the mirror now, alongside the two new
  `claude-memories-*` skills, and the hard-coded counts in `README.md` and
  `INSTALLATION.md` — plus the stale "all nineteen" in both installer headers — now read
  25, matching the directory count, the marketplace manifest, and both catalogs.

- **`claude-obsidian-setup` — a Python below the 3.11 floor is now repaired rather than
  only reported.** Both scripts previously stopped with "install python3.11+ yourself" on
  any distro whose `python3` predates 3.11. That was over-broad: it treated the hardest
  case as if it were the only one. They now, in order, (1) use a newer versioned
  interpreter that is already installed, (2) install one — `python3.13`/`3.12`/`3.11` —
  from the repositories **already configured on the machine** and use it alongside the
  untouched system `python3`, or (3) stop with the concrete remedy. `update-alternatives`
  is never touched and no third-party repository is ever added, so the original objection
  still applies to the only case it was ever true of.

  Every downstream invocation now runs through a selected-interpreter variable rather than
  a hardcoded `python3`. Verified by putting a stub `python3` reporting 3.10 first on
  `PATH`: the script found the real `python3.12`, used it, and produced a complete 14-file
  vault with `doctor ok` and `lint 0 issues`.

- **`claude-obsidian-setup/setup-claude-obsidian.sh` creates the product checkout's parent
  explicitly.** `git clone` does create missing parents — this was verified, and the review
  finding that claimed otherwise was wrong — so nothing was broken. The `mkdir -p` removes
  the dependency on that behaviour and makes an unwritable root fail obviously.

### Added

- **Menu item 19 — Obsidian desktop + `claude-obsidian` and `obsidian-skills`
  plugins.** Off by default, on both scripts, with identical keys, order, and default
  flags. The app is not on npm, so it installs from a package manager: Chocolatey then
  winget on Windows, flatpak then snap on Linux — distro repositories generally do not
  carry it. Chocolatey needs elevation; without it the app is skipped with a warning and
  the two plugins still install. The item then registers
  `AgriciDaniel/claude-obsidian` (the vault engine: transactional writes, provenance
  ledgers, deterministic lint, the `/claude-obsidian:*` skills) and
  [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills) (Obsidian's own
  upstream references for Obsidian Flavored Markdown, Bases, JSON Canvas, the Obsidian
  CLI, and Defuddle).

  The item deliberately stops there. Creating a vault writes to disk under a reviewed
  transaction, so it is a separate, explicitly previewed step rather than a side effect
  of a bootstrap run. `--obsidian-repo-root` / `-ObsidianRepoRoot` sets the root the item
  suggests for it (default `C:\repos` on Windows, `~/repos` on Linux).

- **`claude-obsidian-setup/` — vault setup for Windows (WSL) and Linux.** A matched pair
  of installers that bring both platforms to the same claude-obsidian standard, plus a
  README. Dry-run by default, idempotent, `PASS`/`FIX`/`FAIL` per check against stable
  check ids, non-zero exit on failure, and a closing `doctor` + `lint` against the new
  vault. Vault creation follows the product's own preview-then-apply contract: run the
  plan, read back its `approved_plan_sha256`, pass that exact hash to `--apply`.

  Everything hangs off one root — `C:\repos` / `~/repos` — so `-RepoRoot` /
  `--repo-root` relocates the vault and the product checkout together;
  `-VaultPath`/`--vault` and `-ProductRoot`/`--product` override either half.

  The Windows script exists mostly to repair four failures that are otherwise silent and
  hard to diagnose:

  1. **Native Windows cannot write to a vault at all.** Mutation safety is bound to POSIX
     directory descriptors and `fcntl.flock`; native Python has no `fcntl`, so the core
     refuses every write with `UNSUPPORTED_PLATFORM`. Reads and dry-runs work natively —
     writes are routed through WSL, which is why the vault is created from inside it.
  2. **`python3` resolves to a Microsoft Store stub.** Windows ships no `python3.exe`, so
     the name hits the App Execution Alias and prints an install advert instead of running
     Python — breaking the plugin's `SessionStart`/`Stop` hooks and every documented
     `python3 …` command. Fixed with a hard link `python3.exe → python.exe`.
  3. **`/mnt/c` mounts without `metadata`.** DrvFs then rejects `chmod` with `EPERM` and
     every apply dies with `CORRUPT_RUNTIME_STATE: cannot write confined bundle copy`.
     This cannot be fixed by remounting live; it needs an `[automount]` stanza in
     `/etc/wsl.conf` and a full `wsl --shutdown`. The existing file is backed up first.
  4. **Git identity does not cross the WSL boundary.** `checkpoint` runs inside WSL, where
     Windows' `git config --global` is invisible, so it fails `GIT_FAILED: Author identity
     unknown`. Fixed by setting identity repo-locally, which both environments read.

### Fixed

- **Both install scripts — Superpowers came from a second marketplace and could land
  disabled.** Item 4 registered `obra/superpowers-marketplace` unconditionally, but
  `install_plugin` / `Install-ClaudePlugin` detect plugins by *bare name*. On any machine
  that already had `superpowers@claude-plugins-official` — which items 6 and 7 register —
  the install was skipped, leaving an orphaned `superpowers-marketplace` registration and
  a second, disabled `superpowers@superpowers-marketplace` entry: exactly the duplicate
  [`skills/claude-code-tuneup`](skills/claude-code-tuneup/references/symptoms.md) tells you
  to clean up. Item 4 now takes Superpowers from `anthropics/claude-plugins-official`, the
  marketplace the scripts already register elsewhere, so there is one source for it.

  Superpowers for Claude Code is plugin-only by design and cannot be installed by copying
  `skills/` into `~/.claude/skills/`: its `SessionStart` hook resolves
  `${CLAUDE_PLUGIN_ROOT}`, which only exists for plugins, and that hook is what injects
  `using-superpowers` and makes the other skills fire. Six of the fourteen skills also
  cross-reference each other as `superpowers:<name>`, which unprefixed personal skills
  would break.

  Existing machines keep the stray `superpowers-marketplace` registration — the scripts
  deliberately do not remove marketplaces, since a bootstrap installer should not delete
  something a user may have added on purpose. Drop it with
  `claude plugin marketplace remove superpowers-marketplace`.

- **Both install scripts — an installed-but-disabled plugin is now switched back on.**
  Installing a plugin and having it load are different things: a plugin disabled in
  `settings.json` is installed, at the right scope, and completely inert. New
  `ensure_plugin_enabled` / `Enable-ClaudePlugin` run on the *already-installed* paths
  (update and already-current skip) and call `claude plugin enable --scope` when no enabled
  copy of the name exists. Best-effort by design — the plugin is installed either way, so a
  failure warns instead of failing the step.

  **Not** called after a fresh install: `claude plugin install` already enables what it
  installs. The first cut of this called it there too, which broke a brand-new machine —
  a just-installed plugin can still read as disabled in `claude plugin list --json`, so
  every plugin in the run got an enable attempt, and the CLI's benign "already enabled at
  user scope" reply was reported as a failed step. 18 of them on one run.

  Three separate defects behind that, all fixed:

  - `Enable-ClaudePlugin` used `2>$null` with no `try`/`catch`. Under
    `$ErrorActionPreference = 'Stop'` a native command's stderr line — or any non-zero exit
    when `$PSNativeCommandUseErrorActionPreference` is `$true` — becomes a *terminating*
    error, so `Invoke-Step` marked the step failed. The same hazard is already documented
    at the Claude Code update check. Both preference variables are now shadowed
    function-locally, and the whole call is wrapped, so this function cannot throw.
  - Success was judged from the CLI's message. It can't be: `claude plugin enable` reports
    "is already enabled at user scope" even for a plugin that does not exist. Both scripts
    now judge the outcome from `claude plugin list --json` instead.
  - The bash version was a silent no-op. `local spec="$1" name="${spec%%@*}"` doesn't work
    — bash declares every name in a `local` before expanding the values, so `$spec` read
    the empty new local and `name` was always empty. Assigned on its own line now, matching
    the existing style in `install_plugin`.

- **`install-prerequisites.ps1` — a disabled duplicate could mask an enabled plugin.**
  `Get-ClaudePlugins` keys its map on the bare name with last-write-wins, so with both
  `superpowers@claude-plugins-official` (enabled) and `superpowers@superpowers-marketplace`
  (disabled) installed, the disabled copy won on id sort order and the plugin was reported
  as disabled. An enabled entry now wins over a disabled one.

- **`install-prerequisites.sh` — `json_query` output is stripped of trailing `\r`.** Under
  Git Bash / WSL interop on Windows both `jq` and `python3` emit CRLF, leaving a stray
  carriage return on the last tab-separated field. Every caller compares that field exactly
  (`"$enabled" = "1"`, `"$repo" = "$id"`), so `marketplace_installed` could miss a
  marketplace matched by repo, and the new enablement check read every plugin as disabled.

### Added

- `skills/notify` — **two-way Telegram now works in both directions.** `--wait` only ever
  covered replies to a question Claude asked; a message the user sent on their own
  initiative was thrown away twice over. The dispatcher's `_on_message` dropped anything
  that matched no pending question, and direct mode fast-forwarded its `getUpdates`
  offset past everything already queued before it started listening — so a message typed
  while Claude was busy, or between questions, was silently discarded.

  New `scripts/inbox.py` is the store both halves share: `<spool>/inbox.jsonl` for
  inbound messages and `<spool>/state/offset.json` for the `getUpdates` offset. The
  offset has to be shared rather than per-process because Telegram answers a second
  concurrent `getUpdates` with `409 Conflict` — the daemon owns polling when it is up,
  the client polls only when it is not, and either way the next read resumes where the
  last one stopped.

  `notify.py --inbox` hands Claude what is waiting (exit 0 with messages, 5 without, so
  it works as a "did they say anything?" check in a loop), `--peek` leaves them
  unconsumed, `--wait` blocks for up to `--timeout` seconds, and `--job` filters to one
  topic. A read consumes what it returns, so no message is delivered twice. In topics
  mode the arriving thread is reversed through `topics.json` to attribute the message to
  the right job.

  Appends guard against a fused record: a write killed mid-line leaves no trailing
  newline, and appending onto it would produce one unparseable line and lose the *new*
  message as well as the broken one, so `append()` closes the dangling line first.

- `skills/claude-code-tuneup` — audits a Claude Code installation for what is making it
  slow or bloated and hands back a ranked cleanup plan. `scripts/cc_audit.py` (stdlib
  only, read-only) inventories every settings file in scope, loose skills in
  `~/.claude/skills/` against skills provided by installed plugins, `enabledPlugins`,
  hooks from both settings *and* every plugin's `hooks/hooks.json`, subagents, rules
  files, `CLAUDE.md` sizes, MCP servers, marketplaces, and the plugin cache.

  It catches the duplicate-install case in **both** plugin layouts — a plugin bundling
  `skills/<name>/SKILL.md`, and a plugin whose root *is* the skill, which is what this
  repo's own marketplace publishes. Missing the second layout is why a naive check finds
  none of this repo's skills duplicated. Duplicates are labelled
  `plugin@marketplace`, because the same plugin name published by two marketplaces is
  exactly the case worth catching, and a loose copy shadowing a *disabled* plugin is
  reported separately from one shadowing an enabled plugin — only the latter costs
  context.

- **Menu item 9 (claude-mem) now installs Bun.** claude-mem's hooks run its worker under
  Bun (`package.json` declares `engines.bun >= 1.0.0`) via `scripts/bun-runner.js`, which
  resolves the interpreter with `where`/`which bun` and only then falls back to
  `$HOME/.bun/bin/bun`. Neither install script ever installed it and the plugin's own
  hooks cannot bootstrap it, so on a fresh machine every claude-mem hook failed with
  "Bun not found". Windows uses `choco install bun` when Chocolatey is present *and* the
  run is elevated — the shim lands a real `bun.exe` on `PATH`, which is what
  `bun-runner.js` looks for first — and falls back to bun's per-user installer
  otherwise, since that needs no Administrator rights and writes the documented
  fallback path. Linux prefers `npm install -g bun` (keeping bun on the same `PATH` as
  node) and falls back to `bun.sh/install`; no distro ships a bun package, so there is
  no `as_root` path. Both halves detect first: an existing bun, however it was
  installed, is left alone.

### Removed

- **Perplexity MCP server** — dropped from both install scripts. It was menu item 13
  (off by default), the only row that needed an API key, so the whole up-front key
  prompt goes with it: `read_mcp_api_key` / `read_mcp_api_keys` and `PERPLEXITY_KEY`
  in the `.sh`, `Read-McpApiKey` / `Read-McpApiKeys` and `$script:ApiKeys` in the
  `.ps1`. Every remaining row now installs without asking for anything mid-menu.

  **Menu numbers below it shift by one on both platforms**: MCP servers are 11–13,
  Supabase 14, Context7 15, Playwright CLI 16, SkillUI 17, Strix 18. Scripted runs
  that pass positions (`--select 15,19`) need updating; the stable keys
  (`--select supabase,strix`) were unaffected and remain the better habit. The
  `perplexity-mcp` key itself is gone, so a run that names it now selects nothing for
  that token. An already-registered `perplexity` server is left alone — remove it by
  hand with `claude mcp remove perplexity` if you want it gone.

- `skills/ppt-master` — a vendored copy of the upstream `hugohe3/ppt-master` plugin
  (12,230 files, 88 MB) that was never registered in `marketplace.json`, either
  README, or either install script's skill catalog, so nothing here ever offered it.
  The installer already installs the same plugin from its own marketplace as part of
  menu item 6 (Community marketplaces + plugins), so removing the copy changes nothing
  for anyone running the bootstrap — it just stops the repo carrying 88 MB of upstream
  code it would have to re-sync by hand. This also clears the Pylint CI failure: 845
  of the 855 findings were in that tree.

### Added

- `skills/notify` — **a body over Telegram's 4096-character limit now splits across
  several messages** instead of failing the send. `tg.split_body()` breaks on a
  newline where it can, then a hard cut, and it splits the *raw* text before
  HTML-escaping so a break can never land inside an `&amp;` entity and invalidate
  the message. Whitespace is preserved exactly — rejoining the parts reproduces the
  input byte for byte. Parts are headed `(1/3)`, `(2/3)`, …

  The budget is computed against the **assembled** message, not the body chunk
  alone. Each part carries a `<b>subject (cont.) (2/3)</b>` header, the subject is
  caller-supplied, and escaping can grow it 5×, so a fixed reserve was not enough —
  a 300-character subject produced a 4,346-character message that Telegram would
  have rejected. The header cost is now measured per call and a pathological subject
  is truncated rather than eating the whole budget.

  Buttons go on the last part only, and `send_message()` returns that last message,
  so `notifyd`'s `message_id → req_id` correlation still resolves a button tap or a
  reply to the final part. Replying to an *earlier* part is not indexed and falls
  back to the newest open question in that topic. Parts are spaced one second apart
  to stay under Telegram's per-chat rate limit; `--dry-run` reports the part count.

### Fixed

- `skills/notify/scripts/notify.py` — stdout and stderr are reconfigured to UTF-8 with
  `errors="replace"` at startup. On a Windows console (cp1252) printing a body that
  contained any non-ASCII character — an em dash, an emoji, non-Latin text — raised
  `UnicodeEncodeError` and killed the run, which made `--dry-run` unusable for exactly
  the messages worth checking before sending.

- `skills/notify/scripts/*.py` — the four config reads now pass `encoding="utf-8"` to
  `Path.read_text()`. Without it Python picks the locale encoding, which is cp1252 on
  Windows, and a UTF-8 `config.json` then fails in one of two ways depending on the
  character. Most non-ASCII text decodes silently wrong: an em dash (`E2 80 94`)
  becomes `â€”` in the message that gets sent. Text whose UTF-8 bytes include one of
  the five undefined cp1252 positions (`81 8D 8F 90 9D`) raises `UnicodeDecodeError`
  and takes the run down — Japanese `あ` is `E3 81 82`, so a config with CJK in it
  crashes outright. Both are Windows-only. Also split the comma-form imports and
  wrapped two over-length lines, so `pylint $(git ls-files '*.py')` is back to
  10.00/10.

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

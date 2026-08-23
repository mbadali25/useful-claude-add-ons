# Installation

Three things live in this repo: **prerequisite tooling** (git, Node.js, Python, AWS CLI, the Claude Code CLI itself), **the skills** under `skills/`, and **the plugins** under `plugin/`. This doc covers all three.

## 1. Install prerequisites

One script per OS. Both are idempotent (safe to re-run) and, by default, also bootstrap the team's standard Claude Code plugin marketplaces (see step 3 and [`MARKETPLACE.md`](MARKETPLACE.md)), install every skill in this repo's own marketplace, install the [awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) collection, and optionally register the AWS/Azure MCP servers.

> **Everything is chosen up front, from one menu.** Neither script asks a yes/no question per item any more — you tick what you want, press Enter, and the rest of the run is unattended.

### The menu

```
  Select what to install
  ----------------------
    [x] Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)
    [x] Claude Code CLI (@anthropic-ai/claude-code) + PATH export + update check
  > [x] This repo's marketplace + 25 of 25 skills  >
    [x] Team plugins: superpowers, frontend-design, excalidraw-generator
    ...
    [ ] Strix AI pentesting CLI (needs Docker + an LLM API key)
    [ ] Obsidian desktop + claude-obsidian + obsidian-skills plugins
    [ ] This repo's plugins: crew (agents, commands, hooks)
  showing 1-21 of 21
  ↑↓ move   Space toggle   Enter start   A all   N none   D defaults   Q cancel
  → on the repo row picks individual skills
```

| Key | Does |
|---|---|
| ↑ / ↓ (or `k` / `j`) | Move the cursor |
| Space | Tick or untick the row |
| Enter | Start installing what's ticked |
| → | On the repo's row only: open the per-skill picker |
| ← | Back out of the per-skill picker |
| `A` / `N` / `D` | Tick all / clear all / restore the default set |
| `Q` or Escape | Cancel — nothing is installed |

**The per-skill picker** (→ on row 3) lists all 25 skills in this repo with the same controls. All 25 start ticked; untick the ones you don't want and press Enter or ← to go back. Opening it also ticks the parent row, so a careful sub-selection can't be lost to an unticked parent.

**When the picker isn't available**, both scripts fall back to the original numbered prompt — same items, same defaults, answered with `A`, `D`, `N`, or `1,3,7-9`. That happens when there is no usable terminal (`curl | bash` with no `/dev/tty`, CI), no `stty`, `TERM=dumb`, PowerShell ISE, a redirected console, or a window under ten lines. Nothing about the install differs; only how you choose.

**To skip choosing entirely**, use `-All` / `--all`, `-Select` / `--select`, `-Skills` / `--skills`, or `-NonInteractive` / `--non-interactive`. Any of those bypasses both the picker and the numbered prompt, which is what CI and the `curl | bash` one-liner rely on.

> **Native plugin commands only.** Marketplaces and plugins are installed with `claude plugin marketplace add` and `claude plugin install`. The previous `npx -y claudepluginhub <repo>` wrapper is gone: it synthesized a *local directory* marketplace per repo (registered under a generated name like `cpd-aiskillstore-marketplace-user`), which the scripts' own detection couldn't match — so those plugins were reinstalled on every run — and it was a frequent source of Windows failures. The VoltAgent subagents no longer need a `git clone` + Git Bash either; the repo publishes itself as a marketplace.

### Windows

An **elevated (Administrator)** PowerShell prompt is recommended but no longer required.

```powershell
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
.\scripts\install-prerequisites.ps1
```

It shows the menu, asks the SkillUI quick-start question up front, then installs what you ticked, in order:

1. **Prerequisites** — if elevated: installs [Chocolatey](https://chocolatey.org/) if not already present, then `choco install git awscli nodejs python -y`. **If not elevated, this item is skipped entirely** — the script prints a warning and continues with everything below using whatever `git`/`node`/`npm`/`python` are already on `PATH`.
2. **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code`, adds the npm global bin directory to your **User** `PATH` environment variable (persists across sessions), and sets a `CLAUDE_CODE_HOME` user env var pointing at the npm prefix. When `claude` is already installed it compares the local version against the npm registry instead and updates only if it's behind (`-NoUpdate` skips the check).
3. **This repo** — adds `mbadali25/useful-claude-add-ons` as a Claude Code marketplace, then installs the skills you ticked in the per-skill picker, all 25 by default (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs) below).
4. **Team plugins, community plugins, `find-skills`, `claude-code-setup`, `task-observer`, claude-mem, VoltAgent** — each is its own menu row; `-SkipBootstrap` narrows any selection back down to items 1 and 2.
5. **MCP servers** — AWS, Azure, Playwright. Off by default; see [Optional: MCP servers](#optional-mcp-servers).
6. **Supabase, Context7, Playwright CLI, SkillUI, Strix** — off by default; see [Optional: extra tooling](#optional-extra-tooling).

If `claude` isn't recognized immediately after the script finishes, open a new PowerShell window — the `PATH` change is written to the registry but doesn't retroactively apply to whichever shell you're still in from before Node.js/npm existed.

### Linux

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
./scripts/install-prerequisites.sh
```

Runs as your current user, escalating to `sudo` (or `root` directly if already root) only for the package-manager and global-npm-install steps. Same menu, same order:

1. **Prerequisites** — `git`, `nodejs`, `npm`, `python3` via whichever of `apt-get` / `dnf` / `yum` / `pacman` / `zypper` / `apk` it finds first. Only packages whose command is actually missing get installed.
2. **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code`, then a `PATH` export for the npm global bin directory appended to `~/.bashrc` and `~/.zshrc` (only if not already present) and exported in the current shell too. When `claude` is already installed it compares the local version against the npm registry instead and updates only if it's behind (`--no-update` skips the check).
3. **This repo** — adds `mbadali25/useful-claude-add-ons` as a Claude Code marketplace, then installs the skills you ticked in the per-skill picker, all 25 by default (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs) below).
4. **Team plugins, community plugins, `find-skills`, `claude-code-setup`, `task-observer`, claude-mem, VoltAgent** — each is its own menu row; `--skip-bootstrap` narrows any selection back down to items 1 and 2.
5. **MCP servers** — AWS, Azure, Playwright. Off by default; see [Optional: MCP servers](#optional-mcp-servers).
6. **Supabase, Context7, Playwright CLI, SkillUI, Strix** — off by default; see [Optional: extra tooling](#optional-extra-tooling).

Under the piped one-liner (`curl -fsSL … | bash`) the script itself arrives on stdin, so the menu reads the terminal through its own file descriptor. Where there is no terminal at all, it takes the default set rather than blocking.

Run `source ~/.bashrc` (or open a new shell) afterward to pick up the `PATH` change in shells you already had open.

### What the bootstrap step installs

Both scripts, unless skipped, run this exact sequence (documented in full in [`MARKETPLACE.md`](MARKETPLACE.md) section 3):

```
claude plugin marketplace add mbadali25/useful-claude-add-ons

claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install superpowers@claude-plugins-official
claude plugin marketplace add anthropics/claude-code
claude plugin install frontend-design@claude-code-plugins
claude plugin marketplace add lexiaoyao20/excalidraw-generator
claude plugin install excalidraw-generator@excalidraw-generator

npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code   # prompted

# Community set, prompted (default Yes). Source repo -> marketplace name is not
# mechanical: fcakyon/claude-codex-settings publishes itself as 'claude-settings'.
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace add vercel-labs/agent-browser
claude plugin marketplace add fcakyon/claude-codex-settings
claude plugin marketplace add hugohe3/ppt-master
claude plugin install adhd-output-style@claude-settings
claude plugin install azure-tools@claude-settings
claude plugin install anthropic-office-skills@claude-settings
claude plugin install agent-browser@agent-browser
claude plugin install ppt-master@ppt-master

# claude-mem, prompted (default Yes)
choco install bun -y              # Windows; npm install -g bun on Linux
claude plugin marketplace add thedotmack/claude-mem
claude plugin install claude-mem@thedotmack
```

Every install passes `--scope` (`user` by default; change it with `-InstallScope` / `--scope`).

Some things are *not* Claude Code plugins and so can't go through `claude plugin install`:

- **`find-skills`** — a user-level skill installed by the `skills` CLI (see below).
- **`task-observer`** — a plain skill directory cloned into `~/.claude/skills/`.
- **Context7, Playwright CLI, SkillUI, Strix** — ordinary CLI tools; see [Optional: extra tooling](#optional-extra-tooling).
- **`xlsx` / `mcp-integration`** — these were previously pulled from `aiskillstore/marketplace`, which is the [Skill Store](https://skillstore.io) content repo, **not** a Claude Code marketplace (it has no `.claude-plugin/marketplace.json`). They're no longer installed by the scripts. `anthropic-office-skills@claude-settings` covers the spreadsheet/document ground; if you specifically want the Skill Store versions, install them yourself with `npx skillstore add aiskillstore/xlsx` / `npx skillstore add aiskillstore/mcp-integration`.

`find-skills` is asked about before it runs (default **Yes**). It installs through the `skills` CLI as a plain user-level skill rather than as a Claude Code plugin, so it never shows up in `claude plugin list` — the scripts detect it on disk at `~/.claude/skills/find-skills/SKILL.md` (or `$CLAUDE_CONFIG_DIR/skills/...`). If it's already there, the prompt changes to offer a re-install for updates instead, and `-NoUpdate` / `--no-update` skips it outright.

The first line adds this repo's own skills as an installable marketplace — unlike the external marketplaces above, the scripts **do** auto-install every individual skill from it (see below), since it's this repo's own catalog.

### What the own-marketplace step installs

Immediately after adding `mbadali25/useful-claude-add-ons` as a marketplace, both scripts run `claude plugin install <name>@useful-claude-add-ons` for **each skill you ticked**. All 20 are ticked by default, so an untouched run installs everything currently in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json):

```
claude plugin install aws-opensearch@useful-claude-add-ons
claude plugin install bitbucket@useful-claude-add-ons
claude plugin install checkpoint-email@useful-claude-add-ons
claude plugin install cisco-meraki@useful-claude-add-ons
claude plugin install claude-code-defaults@useful-claude-add-ons
claude plugin install claude-code-tuneup@useful-claude-add-ons
claude plugin install cloudflare@useful-claude-add-ons
claude plugin install drata@useful-claude-add-ons
claude plugin install i-have-adhd@useful-claude-add-ons
claude plugin install infra-work-ticketing@useful-claude-add-ons
claude plugin install intune-graph@useful-claude-add-ons
claude plugin install mermaid-svg-bitbucket@useful-claude-add-ons
claude plugin install notify@useful-claude-add-ons
claude plugin install repo-docs@useful-claude-add-ons
claude plugin install shipstation@useful-claude-add-ons
claude plugin install sophos-central@useful-claude-add-ons
claude plugin install terraform-docs-readme@useful-claude-add-ons
claude plugin install visio-diagrams@useful-claude-add-ons
claude plugin install wazuh-onprem@useful-claude-add-ons
claude plugin install web-testing-playwright@useful-claude-add-ons
claude plugin install work-log-reporter@useful-claude-add-ons
```

An already-installed plugin is detected and skipped (or updated, unless `-NoUpdate` / `--no-update` is passed) rather than reinstalled.

#### The `notify` skill asks about setup

`notify` is the only skill here that needs anything set up on the machine, so when it's ticked the script prints its prerequisites alongside the menu and then asks whether to scaffold the config:

| Prerequisite | Notes |
|---|---|
| Python 3.8+ on `PATH` | The scripts are stdlib only — nothing to `pip install`. |
| A Telegram bot | `@BotFather` → `/newbot` → a token like `123456789:AAE...`. |
| Your `chat_id` | Message the bot once (it can't message you first), then run `scripts/telegram_get_chat_id.py`. |
| `TELEGRAM_BOT_TOKEN` exported | The config names the env var; the token itself is never written to a file. On Windows, `$env:TELEGRAM_BOT_TOKEN` for the session or `setx` for future shells — see the skill's `references/windows.md`. |
| A config file | `~/.config/notify/config.json` globally, or `./.notify.json` per project. On Windows that's `%USERPROFILE%\.config\notify\config.json` — not `%APPDATA%`. |
| Network + polling mode | Outbound HTTPS to `api.telegram.org`, no webhook set on the bot (a webhook makes `getUpdates` return 409), one poller per bot. |

Optional, only if you want them: **topics mode** (one Telegram thread per job) needs a forum supergroup with Topics enabled, the bot as an admin with Manage Topics, and `notifyd.py` running — and if you want to answer with bare free text in a topic rather than tapping a button or replying to the message, Group Privacy has to be turned off in BotFather and the bot re-added to the group; **email** needs `SMTP_USER`/`SMTP_PASS` (an app password on Gmail/M365) for the `smtp` backend, or an M365/Gmail MCP connector for the `connector` backend, which only works while a Claude session is driving.

Answering yes checks for Python, then writes a starter `config.json` — it never overwrites an existing one and never stores the bot token. `--notify-setup` / `-NotifySetup` answers yes up front; `--all` / `--non-interactive` prints the prerequisites and skips the scaffold. For the guided version, run `/notify-setup` inside a Claude session and it will walk you through the bot, the `chat_id`, and a test message.

To take a subset, either press → on the repo's row in the menu and untick what you don't want, or say so on the command line:

```powershell
.\scripts\install-prerequisites.ps1 -Select own-skills -Skills 'cloudflare,drata,repo-docs'
```

```bash
./scripts/install-prerequisites.sh --select own-skills --skills cloudflare,drata,repo-docs
```

`--skills` also takes `all`, `none`, and positions (`1,4-6`), and it composes with `--all` and `--non-interactive` — so a CI run can install everything *except* the skills, or the skills and nothing else. Selecting the repo row with zero skills ticked still registers the marketplace; the script warns and names the fix rather than installing nothing silently.

If a new skill is added to the marketplace, add it to the `SKILL_KEYS` / `SKILL_NAME` arrays in `install-prerequisites.sh` and to `$script:SkillCatalog` in `install-prerequisites.ps1`, plus this list — keeping `marketplace.json`, `skills/`, and the two scripts in sync. The catalogs are the single source of both the picker's rows and the install loop, so there is no second list to forget.

### Optional: MCP servers

Four MCP servers are menu rows, all off by default:

- **AWS** — ensures `uv`/`uvx` is on `PATH` (installing it via `pip install --user uv` if missing), then runs `claude mcp add aws-api -- uvx awslabs.aws-api-mcp-server@latest`. You still need your own AWS credentials configured (`aws configure`) for it to work at runtime.
- **Azure** — runs `claude mcp add azure -- npx -y @azure/mcp@latest server start`. You still need to run `az login` yourself for it to work at runtime.
- **Playwright** — runs `claude mcp add playwright -- npx @playwright/mcp@latest`. Playwright downloads its browsers on first use; `npx playwright install` does it ahead of time.
- **Obsidian vault server** (14) — the odd one out: it registers an **HTTP** endpoint rather than a command to launch, because the MCP server is the `obsidian-local-rest-api` plugin already running inside the vault-server container. That plugin listens on the *server's* loopback, so the URL is normally a local port you forwarded over SSH — hence the `http://127.0.0.1:27123/mcp/` default, overridable with `--obsidian-mcp-url` / `-ObsidianMcpUrl`. The key is per-deployment and cannot be baked into the script, so without `--obsidian-mcp-key` / `-ObsidianMcpKey` the item prints how to read it (`sudo ./obsidian-vault-server.sh apikey` on the vault host) and **skips rather than failing**. Never overwrite an existing key — everything already pointing at the vault stops working. Whole setup: the [`obsidian-vault-server`](skills/obsidian-vault-server/) skill.

The first three can be added later by hand with the same `claude mcp add` command; the Obsidian one takes a URL and an `Authorization` header instead. Any of them is removed with `claude mcp remove <name>`.

### Optional: extra tooling

Six more rows, also off by default. None of them are MCP servers.

- **Supabase** (15) — adds `anthropics/claude-plugins-official` (a no-op if the community or `claude-code-setup` row already registered it) and installs `supabase@claude-plugins-official`. Already-installed is detected and skipped or updated like any other plugin.
- **Context7** (16) — runs `npx -y ctx7@latest setup`, an interactive wizard that wires version-accurate library documentation into whichever agents it finds. The scripts hand it the terminal explicitly; with no terminal available (CI, `curl | bash` with no `/dev/tty`, a redirected console) they print the command to run by hand rather than hanging on a prompt nobody can see. The free tier needs no key.
- **Playwright CLI** (17) — `npm install -g @playwright/cli@latest`, detected by whether `playwright-cli` already resolves on `PATH`. `--no-update` / `-NoUpdate` leaves an existing install alone; otherwise it reinstalls `@latest`.
- **SkillUI** (18) — `npm install -g skillui`, then `npm install -g playwright` and `npx playwright install chromium`. Playwright is installed **globally on purpose**: the scripts can be run from anywhere, and a bare `npm install playwright` would leave a `node_modules` tree in whatever directory you happened to be in. Both Playwright steps warn rather than fail the item, since SkillUI installs fine without them and only screenshot capture breaks. You're asked up front whether to print the quick start afterwards (`--skillui-guide` / `-SkillUIGuide` answers yes without asking).
- **Strix** (19) — installs upstream's own shell installer, `curl -sSL https://strix.ai/install | bash`. **Installing it is not enough to run it**: Strix needs Docker running (the first scan pulls its sandbox image) and an LLM API key exported as `STRIX_LLM` + `LLM_API_KEY`. Both scripts print those next steps every time, including on a re-run that skipped the install. On Windows the installer is POSIX-only, so the script tries WSL first, then Git Bash, and warns with the manual command if neither is available — a WSL install is only usable from inside WSL.

- **Obsidian** (20) — the [Obsidian](https://obsidian.md) desktop app plus the two plugins that make Claude Code useful against a vault. The app is not on npm, so it comes from a package manager: Chocolatey on Windows (falling back to winget), flatpak on Linux (falling back to snap), since distro repositories generally don't carry it. Chocolatey needs an elevated prompt; without one the app is skipped with a warning and **the plugins still install**. Then two marketplaces are added and one plugin taken from each:

  ```bash
  claude plugin marketplace add AgriciDaniel/claude-obsidian
  claude plugin install claude-obsidian@agricidaniel-claude-obsidian

  claude plugin marketplace add kepano/obsidian-skills
  claude plugin install obsidian@obsidian-skills
  ```

  The first is the vault engine — transactional writes, provenance ledgers, deterministic lint, and the `/claude-obsidian:*` skills. The second is [`kepano/obsidian-skills`](https://github.com/kepano/obsidian-skills), maintained by Obsidian's own team: authoritative references for Obsidian Flavored Markdown, Bases (`.base`), JSON Canvas (`.canvas`), the Obsidian CLI, and Defuddle. Both are detected and skipped or updated like any other plugin.

  **This item stops at the app and the plugins.** It deliberately does not create a vault — that writes to disk under a reviewed transaction and belongs in its own step, which the item prints when it finishes and [`claude-obsidian-setup/`](claude-obsidian-setup/) performs. `--obsidian-repo-root` / `-ObsidianRepoRoot` changes the root it suggests (default `C:\repos` on Windows, `~/repos` on Linux).

### Optional: this repo's own plugins

- **This repo's plugins** (21) - installs everything under [`plugin/`](plugin/) from this repo's own marketplace. Today that is one plugin, [`crew`](plugin/crew): 9 subagents, 11 slash commands, 8 bundled skills, and 4 hooks. It adds the marketplace itself first, so the item works whether or not item 3 ran; both steps are no-ops when they are already present.

  ```bash
  claude plugin marketplace add mbadali25/useful-claude-add-ons
  claude plugin install crew@useful-claude-add-ons
  ```

  **It is off by default on purpose, and it is the only item here where that matters for safety.** Every other row installs something Claude *may* use. `crew` installs hooks, which the harness runs on its own:

  | Hook | Event | What it does the moment the plugin is enabled |
  |---|---|---|
  | `guard.sh` / `guard.ps1` | `PreToolUse` on Bash and PowerShell | Blocks `terraform apply`/`destroy`, destructive DDL, force push, hard reset, prod-targeted commands, and any command that would print a secret into the transcript |
  | `verify-gate.sh` | `Stop` | Runs the checks the changed paths map to and **fails the turn** on red, or on a changed path with no rule |
  | `notify.sh` | `Notification` | Sends a one-line outbound message to Teams or Telegram, if configured. Never reads |

  A hook cannot be argued out of blocking something - that is the point of it, and it is also why a bootstrap run should not add one to a machine without the box being ticked. The `Stop` gate in particular is a no-op until you build the change-to-check map, so the item finishes by printing the per-repository setup:

  ```bash
  cd <your repo> && claude
  /crew:init         # guided, resumable setup
  /crew:onboard      # build the code map
  /crew:verify       # build the change-to-check map the Stop gate needs
  ```

  Uninstall with `claude plugin uninstall crew@useful-claude-add-ons`; the hooks go with it. Full guide: [`plugin/crew/README.md`](plugin/crew/README.md), and [`plugin/README.md`](plugin/README.md) for how plugins differ from skills here.

Before running either script on a machine you don't fully control, note that these steps run third-party code from npm, from `strix.ai`, and from Chocolatey/flatpak/snap — see [`SECURITY.md`](SECURITY.md)'s install-script trust boundary.

### Optional: the Obsidian knowledge vault

Item 20 gets you the app and the plugins. Creating and verifying an actual vault is [`claude-obsidian-setup/`](claude-obsidian-setup/):

```powershell
# Windows - preview first, then apply
.\claude-obsidian-setup\setup-claude-obsidian.ps1
.\claude-obsidian-setup\setup-claude-obsidian.ps1 -Apply -RepoRoot C:\repos
```

```bash
# Linux
bash claude-obsidian-setup/setup-claude-obsidian.sh
bash claude-obsidian-setup/setup-claude-obsidian.sh --apply --repo-root ~/repos
```

Both are dry-run by default and idempotent, report `PASS`/`FIX`/`FAIL` per check, and end by running the product's own `doctor` and `lint` against the new vault. On Windows they additionally repair four things that break claude-obsidian silently — native Windows cannot write to a vault at all, `python3` resolves to a Microsoft Store stub, `/mnt/c` mounts without `metadata` so writes fail `EPERM`, and git identity does not cross into WSL. Full detail, including the cross-platform notes: [`claude-obsidian-setup/README.md`](claude-obsidian-setup/README.md).

### Optional: awesome-claude-code-subagents

Both scripts ask once (default **Yes**), then install [`VoltAgent/awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents) **as plugins**. The repo publishes itself as a marketplace named `voltagent-subagents`, with its 154 subagents grouped into ten category plugins:

```bash
claude plugin marketplace add VoltAgent/awesome-claude-code-subagents

claude plugin install voltagent-core-dev@voltagent-subagents    # core development
claude plugin install voltagent-lang@voltagent-subagents        # language specialists
claude plugin install voltagent-infra@voltagent-subagents       # infrastructure & DevOps
claude plugin install voltagent-qa-sec@voltagent-subagents      # quality & security
claude plugin install voltagent-data-ai@voltagent-subagents     # data & AI
claude plugin install voltagent-dev-exp@voltagent-subagents     # developer experience
claude plugin install voltagent-domains@voltagent-subagents     # specialized domains
claude plugin install voltagent-biz@voltagent-subagents         # business & product
claude plugin install voltagent-meta@voltagent-subagents        # meta & orchestration
claude plugin install voltagent-research@voltagent-subagents    # research & analysis
```

The scripts install all ten (matching what the old installer's "everything" path produced). Want fewer? Answer **n** to the prompt and run only the category lines you want — or `claude plugin uninstall voltagent-<category>@voltagent-subagents` afterwards.

This replaces the previous `git clone` + interactive `install-agents.sh` step. That step needed Git Bash on Windows (PowerShell can't execute a `.sh` directly) and therefore **failed outright on a non-elevated run**, where Chocolatey — and so `git` — had been skipped. There's no longer a checkout under `C:\repos` / `~/repos` to maintain; if you have one from an earlier run, it's now unused and safe to delete.

Before running either script on a machine you don't fully control, read [`SECURITY.md`](SECURITY.md)'s "Install-script trust boundary" section — these steps run third-party code from Chocolatey, npm, PyPI (`uv`), and GitHub-hosted marketplaces/repositories.

## 2. Install skills from this repo

The prerequisite scripts already install every skill in this repo's marketplace automatically (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs)). This step is only needed to add an individual skill by hand — e.g. on a machine that skipped the script, or a skill added to the marketplace after you last ran it:

```bash
claude plugin install aws-opensearch@useful-claude-add-ons
claude plugin install wazuh-onprem@useful-claude-add-ons
# ...whichever skills you need — see skills/README.md for the full list.
```

Prefer the lightweight path instead (clone the repo, point a project's `.claude/skills/` at the folders you want) if you're just trying a skill out — see [`MARKETPLACE.md`](MARKETPLACE.md) section 2.

## 3. Verify

```bash
git --version
node --version
python --version   # python3 --version on Linux
aws --version       # Windows only — installed via choco
claude --version
claude plugin marketplace list
claude plugin list
claude mcp list      # confirm aws-api / azure / playwright if you opted in

# Only if you ticked the matching rows:
playwright-cli --version
skillui --help
strix --help         # needs Docker running and STRIX_LLM / LLM_API_KEY set
```

If you opted into the awesome-claude-code-subagents step, `claude plugin list` should show ten `voltagent-*` plugins, and `claude plugin marketplace list` should show `voltagent-subagents`.

## 4. Updating later

```bash
claude plugin marketplace update useful-claude-add-ons
claude plugin update <skill-name>@useful-claude-add-ons
```

Or just re-run the OS install script — it's idempotent and will skip anything already installed.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `choco : The term 'choco' is not recognized` right after install (Windows) | PATH not refreshed in the current shell | Open a new PowerShell window |
| `claude: command not found` after the script finishes | Shell's `PATH` was cached before the script updated it | Open a new shell (Windows) / `source ~/.bashrc` (Linux) |
| `npm install -g` fails with `EACCES` (Linux) | npm global prefix not writable by your user | The script already falls back to `sudo` for this; if it still fails, see `npm config get prefix` and fix ownership, or configure a user-writable npm prefix |
| Chocolatey install script blocked | PowerShell execution policy | The script sets `Bypass` for its own process only — no machine-wide policy change needed; re-run from an elevated prompt if it still fails |
| `claude plugin marketplace add mbadali25/useful-claude-add-ons` fails | Repo is private and you're not authenticated to GitHub, or the CLI can't reach GitHub | Confirm `git ls-remote git@github.com:mbadali25/useful-claude-add-ons.git` works from the same machine first |
| Windows script skips Chocolatey/git/awscli/nodejs/python entirely | Not run from an elevated prompt | Expected behavior, not an error — re-run from an elevated PowerShell prompt if you need those installed; everything else (Claude Code CLI, marketplaces, skills, MCP prompts, subagents) still runs |
| `claude plugin install <name>@<marketplace>` fails with an unknown-plugin error | The marketplace name doesn't match the `name` field in that repo's own `.claude-plugin/marketplace.json` — it is **not** derived from the repo name (`fcakyon/claude-codex-settings` publishes itself as `claude-settings`) | Run `claude plugin marketplace list` to see the registered name, then install with that name |
| `claude mcp add aws-api -- uvx ...` fails with `uvx: command not found` | `uv` wasn't found or failed to install via `pip install --user uv` | Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) manually, ensure it's on `PATH`, then re-run the script (it's idempotent) or run the `claude mcp add` command yourself |
| AWS/Azure MCP server registered but tools fail when Claude tries to use them | No AWS credentials / no Azure login | Run `aws configure` (AWS) or `az login` (Azure) — `claude mcp add` only registers the server, it doesn't authenticate it |
| `strix` installed but every scan fails immediately | Docker isn't running, or `STRIX_LLM` / `LLM_API_KEY` aren't set | Start Docker, then export both variables (the script prints the exact lines). Providers: [docs.strix.ai](https://docs.strix.ai) |
| Windows: "no WSL or bash found to run the Strix installer" | Strix ships a POSIX shell installer only | `wsl --install`, or install Git for Windows (menu item 1 does this via Chocolatey), then re-run — a WSL install is only usable from inside WSL |
| `skillui` runs but produces no screenshots | `npm install -g playwright` or `npx playwright install chromium` failed — both warn rather than fail the item | Re-run those two commands by hand and read the error |
| `npx ctx7 setup` was skipped with "no interactive console" | The script had no terminal to hand the wizard (CI, redirected console, `curl \| bash` with no `/dev/tty`) | Run `npx ctx7 setup` yourself in a normal terminal |
| Older run left a `cpd-*-user` marketplace (e.g. `cpd-aiskillstore-marketplace-user`) in `claude plugin marketplace list` | Registered by the old `npx claudepluginhub` wrapper as a local directory marketplace | Harmless, but no longer used or refreshed — remove it with `claude plugin marketplace remove cpd-<name>-user` |

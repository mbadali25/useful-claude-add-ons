# Installation

Two things live in this repo: **prerequisite tooling** (git, Node.js, Python, AWS CLI, the Claude Code CLI itself) and **the skills**. This doc covers both.

## 1. Install prerequisites

One script per OS. Both are idempotent (safe to re-run) and, by default, also bootstrap the team's standard Claude Code plugin marketplaces (see step 3 and [`MARKETPLACE.md`](MARKETPLACE.md)), install every skill in this repo's own marketplace, install the [awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) collection, and optionally register the AWS/Azure MCP servers.

> **Everything is chosen up front, from one menu.** Neither script asks a yes/no question per item any more — you tick what you want, press Enter, and the rest of the run is unattended.

### The menu

```
  Select what to install
  ----------------------
    [x] Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)
    [x] Claude Code CLI (@anthropic-ai/claude-code) + PATH export
  > [x] This repo's marketplace + 19 of 19 skills  >
    [x] Team plugins: superpowers, frontend-design, excalidraw-generator
    ...
    [ ] Headroom: pipx + headroom-ai[all] + mode setup + doctor
  showing 1-20 of 20
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

**The per-skill picker** (→ on row 3) lists all 19 skills in this repo with the same controls. All 19 start ticked; untick the ones you don't want and press Enter or ← to go back. Opening it also ticks the parent row, so a careful sub-selection can't be lost to an unticked parent.

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

It shows the menu, collects any API keys and the Headroom mode question up front, then installs what you ticked, in order:

1. **Prerequisites** — if elevated: installs [Chocolatey](https://chocolatey.org/) if not already present, then `choco install git awscli nodejs python -y`. **If not elevated, this item is skipped entirely** — the script prints a warning and continues with everything below using whatever `git`/`node`/`npm`/`python` are already on `PATH`.
2. **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code`, adds the npm global bin directory to your **User** `PATH` environment variable (persists across sessions), and sets a `CLAUDE_CODE_HOME` user env var pointing at the npm prefix.
3. **This repo** — adds `mbadali25/useful-claude-add-ons` as a Claude Code marketplace, then installs the skills you ticked in the per-skill picker, all 19 by default (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs) below).
4. **Team plugins, community plugins, `find-skills`, `claude-code-setup`, `task-observer`, claude-mem, GSD, VoltAgent** — each is its own menu row; `-SkipBootstrap` narrows any selection back down to items 1 and 2.
5. **MCP servers** — AWS, Azure, Perplexity, Playwright, Firecrawl, Chrome DevTools, Glyphs. Off by default; see [Optional: MCP servers](#optional-mcp-servers). Perplexity and Firecrawl ask for their API key alongside the menu rather than mid-install.
6. **OmniRoute** and **Headroom** — off by default. Headroom's mode question is asked before the install starts, or answered with `-HeadroomMode`.

If `claude` isn't recognized immediately after the script finishes, open a new PowerShell window — the `PATH` change is written to the registry but doesn't retroactively apply to whichever shell you're still in from before Node.js/npm existed.

### Linux

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
./scripts/install-prerequisites.sh
```

Runs as your current user, escalating to `sudo` (or `root` directly if already root) only for the package-manager and global-npm-install steps. Same menu, same order:

1. **Prerequisites** — `git`, `nodejs`, `npm`, `python3` via whichever of `apt-get` / `dnf` / `yum` / `pacman` / `zypper` / `apk` it finds first. Only packages whose command is actually missing get installed.
2. **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code`, then a `PATH` export for the npm global bin directory appended to `~/.bashrc` and `~/.zshrc` (only if not already present) and exported in the current shell too.
3. **This repo** — adds `mbadali25/useful-claude-add-ons` as a Claude Code marketplace, then installs the skills you ticked in the per-skill picker, all 19 by default (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs) below).
4. **Team plugins, community plugins, `find-skills`, `claude-code-setup`, `task-observer`, claude-mem, GSD, VoltAgent** — each is its own menu row; `--skip-bootstrap` narrows any selection back down to items 1 and 2.
5. **MCP servers** — AWS, Azure, Perplexity, Playwright, Firecrawl, Chrome DevTools, Glyphs. Off by default; see [Optional: MCP servers](#optional-mcp-servers).
6. **OmniRoute** and **Headroom** — off by default, with the Headroom mode question asked before the install starts or answered with `--headroom-mode`.

Under the piped one-liner (`curl -fsSL … | bash`) the script itself arrives on stdin, so the menu reads the terminal through its own file descriptor. Where there is no terminal at all, it takes the default set rather than blocking.

Run `source ~/.bashrc` (or open a new shell) afterward to pick up the `PATH` change in shells you already had open.

### What the bootstrap step installs

Both scripts, unless skipped, run this exact sequence (documented in full in [`MARKETPLACE.md`](MARKETPLACE.md) section 3):

```
claude plugin marketplace add mbadali25/useful-claude-add-ons

claude plugin marketplace add obra/superpowers-marketplace
claude plugin install superpowers@superpowers-marketplace
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
claude plugin marketplace add thedotmack/claude-mem
claude plugin install claude-mem@thedotmack

npx -y @opengsd/gsd-core@latest   # prompted
```

Every install passes `--scope` (`user` by default; change it with `-InstallScope` / `--scope`).

Three things are *not* Claude Code plugins and so can't go through `claude plugin install`:

- **`find-skills`** — a user-level skill installed by the `skills` CLI (see below).
- **GSD** — an npm-distributed installer with no marketplace of its own.
- **`xlsx` / `mcp-integration`** — these were previously pulled from `aiskillstore/marketplace`, which is the [Skill Store](https://skillstore.io) content repo, **not** a Claude Code marketplace (it has no `.claude-plugin/marketplace.json`). They're no longer installed by the scripts. `anthropic-office-skills@claude-settings` covers the spreadsheet/document ground; if you specifically want the Skill Store versions, install them yourself with `npx skillstore add aiskillstore/xlsx` / `npx skillstore add aiskillstore/mcp-integration`.

`find-skills` is asked about before it runs (default **Yes**). It installs through the `skills` CLI as a plain user-level skill rather than as a Claude Code plugin, so it never shows up in `claude plugin list` — the scripts detect it on disk at `~/.claude/skills/find-skills/SKILL.md` (or `$CLAUDE_CONFIG_DIR/skills/...`). If it's already there, the prompt changes to offer a re-install for updates instead, and `-NoUpdate` / `--no-update` skips it outright.

The first line adds this repo's own skills as an installable marketplace — unlike the external marketplaces above, the scripts **do** auto-install every individual skill from it (see below), since it's this repo's own catalog.

### What the own-marketplace step installs

Immediately after adding `mbadali25/useful-claude-add-ons` as a marketplace, both scripts run `claude plugin install <name>@useful-claude-add-ons` for **each skill you ticked**. All 19 are ticked by default, so an untouched run installs everything currently in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json):

```
claude plugin install aws-opensearch@useful-claude-add-ons
claude plugin install bitbucket@useful-claude-add-ons
claude plugin install checkpoint-email@useful-claude-add-ons
claude plugin install cisco-meraki@useful-claude-add-ons
claude plugin install claude-code-defaults@useful-claude-add-ons
claude plugin install cloudflare@useful-claude-add-ons
claude plugin install drata@useful-claude-add-ons
claude plugin install i-have-adhd@useful-claude-add-ons
claude plugin install infra-work-ticketing@useful-claude-add-ons
claude plugin install intune-graph@useful-claude-add-ons
claude plugin install mermaid-svg-bitbucket@useful-claude-add-ons
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

After the bootstrap commands, both scripts ask two yes/no questions (default **No** — just press Enter to skip):

- **Install the AWS MCP server?** If yes: ensures `uv`/`uvx` is on `PATH` (installing it via `pip install --user uv` if missing), then runs `claude mcp add aws-api -- uvx awslabs.aws-api-mcp-server@latest`. You still need your own AWS credentials configured (`aws configure`) for it to work at runtime.
- **Install the Azure MCP server?** If yes: runs `claude mcp add azure -- npx -y @azure/mcp@latest server start`. You still need to run `az login` yourself for it to work at runtime.

Either can be added later by hand with the same `claude mcp add` command, or removed with `claude mcp remove <name>`.

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
claude mcp list      # confirm aws-api / azure if you opted in
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
| Older run left a `cpd-*-user` marketplace (e.g. `cpd-aiskillstore-marketplace-user`) in `claude plugin marketplace list` | Registered by the old `npx claudepluginhub` wrapper as a local directory marketplace | Harmless, but no longer used or refreshed — remove it with `claude plugin marketplace remove cpd-<name>-user` |

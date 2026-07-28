# Installation

Two things live in this repo: **prerequisite tooling** (git, Node.js, Python, AWS CLI, the Claude Code CLI itself) and **the skills**. This doc covers both.

## 1. Install prerequisites

One script per OS. Both are idempotent (safe to re-run) and, by default, also bootstrap the team's standard Claude Code plugin marketplaces (see step 3 and [`MARKETPLACE.md`](MARKETPLACE.md)), install every skill in this repo's own marketplace, optionally register the AWS/Azure MCP servers, and clone+run the [awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) installer as a final step.

### Windows

An **elevated (Administrator)** PowerShell prompt is recommended but no longer required.

```powershell
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
.\scripts\install-prerequisites.ps1
```

What it does, in order:

1. If elevated: installs [Chocolatey](https://chocolatey.org/) if not already present, then `choco install git awscli nodejs python -y`. **If not elevated, this step and the package installs are skipped entirely** — the script prints a warning and continues with everything below using whatever `git`/`node`/`npm`/`python` are already on `PATH`.
2. Installs the Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) and adds the npm global bin directory to your **User** `PATH` environment variable (persists across sessions), plus sets a `CLAUDE_CODE_HOME` user env var pointing at the npm prefix.
3. Adds this repo (`mbadali25/useful-claude-add-ons`) as a Claude Code marketplace, then installs every skill listed in it (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs) below).
4. Runs the team's plugin/marketplace bootstrap commands (skip with `-SkipBootstrap`).
5. Prompts (`y`/`N`) to register the AWS MCP server and, separately, the Azure MCP server with Claude Code — see [Optional: MCP servers](#optional-mcp-servers).
6. Clones (or pulls, if already cloned) `VoltAgent/awesome-claude-code-subagents` into `C:\repos\awesome-claude-code-subagents` and runs its interactive `install-agents.sh` via Git Bash — see [Optional: awesome-claude-code-subagents](#optional-awesome-claude-code-subagents).

If `claude` isn't recognized immediately after the script finishes, open a new PowerShell window — the `PATH` change is written to the registry but doesn't retroactively apply to whichever shell you're still in from before Node.js/npm existed.

### Linux

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
./scripts/install-prerequisites.sh
```

Runs as your current user, escalating to `sudo` (or `root` directly if already root) only for the package-manager and global-npm-install steps. What it does:

1. Installs `git`, `nodejs`, `npm`, `python3` via whichever of `apt-get` / `dnf` / `yum` / `pacman` / `zypper` / `apk` it finds first.
2. Installs the Claude Code CLI (`npm install -g @anthropic-ai/claude-code`).
3. Appends a `PATH` export for the npm global bin directory to `~/.bashrc` and `~/.zshrc` (only if not already present) and exports it in the current shell too.
4. Adds this repo (`mbadali25/useful-claude-add-ons`) as a Claude Code marketplace, then installs every skill listed in it (see [What the own-marketplace step installs](#what-the-own-marketplace-step-installs) below).
5. Runs the team's plugin/marketplace bootstrap commands (skip with `--skip-bootstrap`).
6. Prompts (`y`/`N`) to register the AWS MCP server and, separately, the Azure MCP server with Claude Code — see [Optional: MCP servers](#optional-mcp-servers).
7. Clones (or pulls, if already cloned) `VoltAgent/awesome-claude-code-subagents` into `~/repos/awesome-claude-code-subagents` and runs its interactive `install-agents.sh` — see [Optional: awesome-claude-code-subagents](#optional-awesome-claude-code-subagents).

Run `source ~/.bashrc` (or open a new shell) afterward to pick up the `PATH` change in shells you already had open.

### What the bootstrap step installs

Both scripts, unless skipped, run this exact sequence (documented in full in [`MARKETPLACE.md`](MARKETPLACE.md) section 3):

```
claude plugin marketplace add obra/superpowers-marketplace
claude plugin install superpowers@superpowers-marketplace

npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code
npx @opengsd/gsd-core@latest
npx claude-mem install

claude plugin marketplace add anthropics/claude-code
claude plugin install frontend-design@claude-code-plugins
claude plugin marketplace add lexiaoyao20/excalidraw-generator
claude plugin install excalidraw-generator@excalidraw-generator
claude plugin marketplace add obra/superpowers-marketplace
claude plugin install superpowers@claude-plugins-official

claude plugin marketplace add mbadali25/useful-claude-add-ons
```

The last line adds this repo's own skills as an installable marketplace — unlike the team bootstrap list above, the scripts **do** auto-install every individual skill from it (see below), since it's this repo's own catalog.

### What the own-marketplace step installs

Immediately after adding `mbadali25/useful-claude-add-ons` as a marketplace, both scripts run `claude plugin install <name>@useful-claude-add-ons` for every skill currently in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json):

```
claude plugin install aws-opensearch@useful-claude-add-ons
claude plugin install bitbucket@useful-claude-add-ons
claude plugin install checkpoint-email@useful-claude-add-ons
claude plugin install cloudflare@useful-claude-add-ons
claude plugin install drata@useful-claude-add-ons
claude plugin install i-have-adhd@useful-claude-add-ons
claude plugin install intune-graph@useful-claude-add-ons
claude plugin install mermaid-svg-bitbucket@useful-claude-add-ons
claude plugin install sophos-central@useful-claude-add-ons
claude plugin install wazuh-onprem@useful-claude-add-ons
```

If a new skill is added to the marketplace, add its `claude plugin install` line to both scripts (and to this list) to keep them in sync.

### Optional: MCP servers

After the bootstrap commands, both scripts ask two yes/no questions (default **No** — just press Enter to skip):

- **Install the AWS MCP server?** If yes: ensures `uv`/`uvx` is on `PATH` (installing it via `pip install --user uv` if missing), then runs `claude mcp add aws-api -- uvx awslabs.aws-api-mcp-server@latest`. You still need your own AWS credentials configured (`aws configure`) for it to work at runtime.
- **Install the Azure MCP server?** If yes: runs `claude mcp add azure -- npx -y @azure/mcp@latest server start`. You still need to run `az login` yourself for it to work at runtime.

Either can be added later by hand with the same `claude mcp add` command, or removed with `claude mcp remove <name>`.

### Optional: awesome-claude-code-subagents

As the final step, both scripts clone (or `git pull` if already present) [`VoltAgent/awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents) — to `C:\repos\awesome-claude-code-subagents` on Windows, `~/repos/awesome-claude-code-subagents` on Linux — and run its **interactive** `install-agents.sh`, which lets you browse categories and pick which subagents to install. On Windows this runs through Git Bash (`bash install-agents.sh`), since PowerShell can't execute a `.sh` file directly.

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

If you opted into the awesome-claude-code-subagents step, its clone lives at `C:\repos\awesome-claude-code-subagents` (Windows) or `~/repos/awesome-claude-code-subagents` (Linux) — re-run `install-agents.sh` from there any time to add or remove subagents.

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
| `claude mcp add aws-api -- uvx ...` fails with `uvx: command not found` | `uv` wasn't found or failed to install via `pip install --user uv` | Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) manually, ensure it's on `PATH`, then re-run the script (it's idempotent) or run the `claude mcp add` command yourself |
| AWS/Azure MCP server registered but tools fail when Claude tries to use them | No AWS credentials / no Azure login | Run `aws configure` (AWS) or `az login` (Azure) — `claude mcp add` only registers the server, it doesn't authenticate it |
| `bash (Git Bash) not found on PATH` during the awesome-claude-code-subagents step (Windows) | Git wasn't installed (script run non-elevated and Chocolatey was skipped) | Install [Git for Windows](https://git-scm.com/download/win) yourself, or re-run the script elevated so it installs `git` via Chocolatey, then re-run |

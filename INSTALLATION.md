# Installation

Two things live in this repo: **prerequisite tooling** (git, Node.js, Python, AWS CLI, the Claude Code CLI itself) and **the skills**. This doc covers both.

## 1. Install prerequisites

One script per OS. Both are idempotent (safe to re-run) and, by default, also bootstrap the team's standard Claude Code plugin marketplaces (see step 3 and [`MARKETPLACE.md`](MARKETPLACE.md)).

### Windows

Requires an **elevated (Administrator)** PowerShell prompt, since Chocolatey and system PATH changes need it.

```powershell
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
.\scripts\install-prerequisites.ps1
```

What it does, in order:

1. Installs [Chocolatey](https://chocolatey.org/) if not already present.
2. `choco install git awscli nodejs python -y`.
3. Installs the Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) and adds the npm global bin directory to your **User** `PATH` environment variable (persists across sessions), plus sets a `CLAUDE_CODE_HOME` user env var pointing at the npm prefix.
4. Runs the team's plugin/marketplace bootstrap commands (skip with `-SkipBootstrap`).

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
4. Runs the team's plugin/marketplace bootstrap commands (skip with `--skip-bootstrap`).

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

The last line adds this repo's own skills as an installable marketplace (see step 2 below) — the scripts add the marketplace automatically but do **not** auto-install every individual skill, since not everyone needs all of them.

Before running either script on a machine you don't fully control, read [`SECURITY.md`](SECURITY.md)'s "Install-script trust boundary" section — these steps run third-party code from Chocolatey, npm, and GitHub-hosted marketplaces.

## 2. Install skills from this repo

Once the CLI is installed and this repo added as a marketplace (done automatically by the scripts above, or manually per [`MARKETPLACE.md`](MARKETPLACE.md) section 1):

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
```

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

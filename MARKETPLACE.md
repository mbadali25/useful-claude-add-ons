# Claude Code Marketplace & Plugin Installation

This repo publishes itself as a Claude Code **plugin marketplace**: [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) lists every skill in [`skills/`](skills/) as an installable plugin. This doc covers adding *this* marketplace, adding the *other* marketplaces the team standardizes on, and the difference between the marketplace path and just cloning the repo.

If you haven't installed the Claude Code CLI itself yet, do that first — see [`INSTALLATION.md`](INSTALLATION.md), or run [`scripts/install-prerequisites.ps1`](scripts/install-prerequisites.ps1) / [`scripts/install-prerequisites.sh`](scripts/install-prerequisites.sh), which install the CLI and everything below in one pass.

## 1. Add this repo as a marketplace

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
```

This works from any machine with the `claude` CLI on PATH — no local clone required, since `claude plugin marketplace add` pulls `.claude-plugin/marketplace.json` straight from GitHub. Equivalent forms:

```bash
# Explicit git URL (works for any host, not just github.com)
claude plugin marketplace add https://github.com/mbadali25/useful-claude-add-ons.git

# Local clone, for testing changes before pushing
claude plugin marketplace add ./useful-claude-add-ons
```

Inside an interactive session you can run the same thing as a slash command: `/plugin marketplace add mbadali25/useful-claude-add-ons`.

### Install a skill from it

```bash
claude plugin install aws-opensearch@useful-claude-add-ons
claude plugin install bitbucket@useful-claude-add-ons
claude plugin install wazuh-onprem@useful-claude-add-ons
# ...one per skill you want. Plugin names match the skill directory names
# in skills/README.md.
```

Add `--scope project` to install into the current project's `.claude/` config instead of your user-level config, or `--scope local` for a machine-local, non-shared install.

### List, update, remove

```bash
claude plugin marketplace list                              # marketplaces you've added
claude plugin marketplace update useful-claude-add-ons       # pull latest marketplace.json
claude plugin marketplace remove useful-claude-add-ons       # stop tracking this marketplace

claude plugin list                                            # installed plugins
claude plugin uninstall aws-opensearch@useful-claude-add-ons
```

`claude plugin marketplace update` (or the `/plugin` slash-command equivalents inside a session) is how a teammate picks up a newly added or changed skill — it re-reads `marketplace.json` from the repo's current `main`.

## 2. Lightweight path: skip plugins entirely

Claude Code auto-discovers any `SKILL.md` under a `skills/` directory it can see — you don't strictly need the plugin/marketplace machinery to use a skill locally:

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
# then either:
#   a) point Claude at it directly by working inside this repo, or
#   b) copy/symlink individual skill folders into your own project's .claude/skills/
#      or your user-level ~/.claude/skills/
```

Use the marketplace path (section 1) for anything you want the whole team to install consistently and update centrally. Use the lightweight path for trying a skill out, or for a one-off project that only needs one or two of these.

## 3. Other marketplaces the team standardizes on

The prerequisite install scripts also wire up these external marketplaces and their plugins/tools, so every machine starts from the same baseline:

```bash
# Superpowers - process skills (brainstorming, TDD, systematic debugging, writing plans, etc.)
claude plugin marketplace add obra/superpowers-marketplace
claude plugin install superpowers@superpowers-marketplace

# find-skills - lets Claude discover and install skills from the community index on demand
npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code

# GSD (Get Stuff Done) - structured project/phase workflow tooling
npx @opengsd/gsd-core@latest

# claude-mem - persistent cross-session memory
npx claude-mem install

# Anthropic's official plugin marketplace - frontend-design skill
claude plugin marketplace add anthropics/claude-code
claude plugin install frontend-design@claude-code-plugins

# Excalidraw diagram generator
claude plugin marketplace add lexiaoyao20/excalidraw-generator
claude plugin install excalidraw-generator@excalidraw-generator

# Superpowers again, via Anthropic's official marketplace mirror
claude plugin marketplace add obra/superpowers-marketplace
claude plugin install superpowers@claude-plugins-official
```

> The last block installs `superpowers` a second time, from a differently-named marketplace target (`claude-plugins-official` instead of `superpowers-marketplace`). That's carried over verbatim from the team's baseline setup — if you only want it once, either line is sufficient; keeping both is harmless (`claude plugin install` no-ops if the plugin is already installed from an equivalent source).

These run automatically as part of the prerequisite install scripts (section 4 of [`INSTALLATION.md`](INSTALLATION.md)). Run them by hand only if you're patching an existing machine that already has the CLI.

## 4. Publishing a new or updated skill to this marketplace

1. Author the skill per [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) and validate/review per [`Skill-Pipeline.md`](Skill-Pipeline.md).
2. Add or update its entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) — `name`, `source` (`./skills/<name>`), `description`, and bump `version` on any change to an existing skill.
3. Add/update the row in [`skills/README.md`](skills/README.md) and log the change in [`CHANGELOG.md`](CHANGELOG.md).
4. Merge to `main`. Teammates pick it up with `claude plugin marketplace update useful-claude-add-ons` followed by `claude plugin install <name>@useful-claude-add-ons` (or `claude plugin update` if already installed).

## 5. Validating before you push

```bash
claude plugin validate .
```

Run this from the repo root before opening a PR that touches `.claude-plugin/marketplace.json` or any `skills/*/SKILL.md` — it catches malformed JSON, missing required frontmatter, and bad `source` paths before a teammate hits them.

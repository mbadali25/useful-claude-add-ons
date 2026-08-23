# Plugins

Each subdirectory here is a self-contained [Claude Code plugin](https://docs.claude.com/en/docs/claude-code/plugins) — a `.claude-plugin/plugin.json` manifest plus any `agents/`, `commands/`, `hooks/`, or `skills/` it bundles. Every one is registered in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and installs the same way a skill from [`../skills/`](../skills/) does.

**A plugin is not a bigger skill.** A skill is a document Claude reads when the conversation matches its `description`. A plugin can also register **subagents** (their own context window and tool set), **slash commands** (you type them), and **hooks** (deterministic shell scripts the harness runs on tool use, on stop, or on notification — they execute whether or not Claude agrees with them). That last part is why plugins here are opt-in in the install scripts and skills are not: a hook can block a command you ran on purpose.

See [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md) for the writing style bundled skills must follow, and [`../Skill-Pipeline.md`](../Skill-Pipeline.md) for how a change gets from a draft to something the team can install.

## Overview

| Plugin | Category | What it does | Use cases | Provides |
|---|---|---|---|---|
| [`crew`](crew) | Workflow / QA | A virtual dev team for multi-repo legacy work — file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure instead of offering an opinion. Roles exist only where they buy an isolated context window, a restricted tool set, or genuinely independent eyes; project management, BA, and architecture are files and commands, not agents. Codex QA, Jira, Obsidian memory, and Teams/Telegram notifications are all optional. | Several repositories, mixed stacks, legacy code, and almost no test coverage; a change that needs review by something that did not write it; wanting `terraform apply`, force-push, and destructive DDL blocked by a hook rather than by good intentions; a turn that should fail when the checks its changed paths map to go red. | 9 agents, 11 commands, 4 hooks, 8 skills |

**Provides** counts what the plugin registers with Claude Code. `crew`'s full breakdown — every command, agent, tool restriction, and hook event — is in [`crew/README.md`](crew/README.md) §19.

## Install

The plugins here come from this repo's own marketplace, so they install exactly like the skills do:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install crew@useful-claude-add-ons
```

Or pick **item 21, `This repo's plugins`**, in either bootstrap script — it is off by default:

```bash
./scripts/install-prerequisites.sh --select repo-plugins
```

```powershell
.\scripts\install-prerequisites.ps1 -Select repo-plugins
```

Both are also slash commands inside a session: `/plugin marketplace add mbadali25/useful-claude-add-ons`, then `/plugin install crew@useful-claude-add-ons`.

### Hooks only run where hooks run

Bundled **skills** work in Claude Code, Claude chat, Claude Desktop's Chat tab, and Cowork. Bundled **hooks and subagents** run only in Claude Code and Cowork — they are greyed out in chat. Installing a plugin on claude.ai does not install it in your terminal, and vice versa; the file format is shared, the installation is not. Since `crew` is mostly hooks, subagents, and slash commands operating on a local git repository, installing it on the web gives you the bundled skills' written guidance and nothing that executes.

## Adding a new plugin

1. Create `plugin/<plugin-name>/.claude-plugin/plugin.json` — kebab-case directory name matching the `name` field exactly, plus `version`, `description`, and an `author` block. Do **not** commit a `marketplace.json` inside the plugin directory; the repo root's is the only marketplace here.
2. Put its parts in the conventional subdirectories: `agents/`, `commands/`, `hooks/`, `skills/`. Any bundled `SKILL.md` still follows [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md).
3. Ship hook scripts in **both** flavours — a `.sh` for Linux/macOS and a `.ps1` registered with `shell: powershell` for Windows — or the plugin silently does nothing on half the team's machines.
4. Register it in all four places, the same rule skills follow:
   1. [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) — `name`, `source` (`./plugin/<name>`), `description`, `version`.
   2. The table above — all five columns. **Use cases** should be concrete situations that would send someone looking for it, not a restatement of *What it does*.
   3. [`../README.md`](../README.md), inside the `<!-- BEGIN plugin/README.md -->` block, plus the plugin count wherever it appears as a number.
   4. Both install scripts — `PLUGIN_KEYS` / `PLUGIN_NAME` in the `.sh`, `$script:PluginCatalog` in the `.ps1`. Keep the two in the same order, with the same text.
5. Default the menu item to **off** if the plugin registers hooks. A hook is not advisory, and a bootstrap run should not add one to someone's machine without them ticking a box.

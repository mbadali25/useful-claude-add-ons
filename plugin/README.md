# Plugins

Each subdirectory here is a self-contained [Claude Code plugin](https://docs.claude.com/en/docs/claude-code/plugins) — a `.claude-plugin/plugin.json` manifest plus any `agents/`, `commands/`, `hooks/`, or `skills/` it bundles. Every one is registered in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and installs the same way a skill from [`../skills/`](../skills/) does.

**A plugin is not a bigger skill.** A skill is a document Claude reads when the conversation matches its `description`. A plugin can also register **subagents** (their own context window and tool set), **slash commands** (you type them), and **hooks** (shell scripts the harness runs on tool use, on stop, on compact, on session start — they execute whether or not Claude agrees with them). That last part is why plugins here are opt-in in the install scripts and skills are not: a hook can block a command you ran on purpose.

See [`PLUGINS.md`](PLUGINS.md) for what each plugin actually contains — every command, agent, skill, and hook, and what starts running the moment it is enabled. See [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md) for the style bundled skills must follow, and [`../Skill-Pipeline.md`](../Skill-Pipeline.md) for how a change gets from a draft to something the team can install.

## Overview

| Plugin | Category | What it does | Use cases | Provides |
|---|---|---|---|---|
| [`crew`](crew) | Workflow / QA | A virtual dev team for multi-repo legacy work — file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure instead of offering an opinion. Hooks enforce unsafe commands, unverified turns, and unearned production deploys. Roles exist only where they buy an isolated context window, a restricted tool set, or genuinely independent eyes; the manager is the one role that can assign work rather than only reporting on it, opt-in via `pm.authority`, and BA/architecture stay files and commands. Codex QA, Jira or ServiceDesk Plus, an Obsidian Kanban board for tickets, Obsidian memory, a code graph, and Teams/Telegram notifications are all optional. | Several repositories, mixed stacks, legacy code, and almost no test coverage; a change that needs review by something that did not write it; wanting `terraform apply`, force-push, and destructive DDL blocked by a hook rather than by good intentions; a turn that should fail when the checks its changed paths map to go red; a production deploy that should be refused unless qa signed off on **that exact sha** and the rollback runbook is still verified; wanting to know what every endpoint and scheduled job actually does; losing the thread across a `/clear` or an auto-compact; wanting the crew to pick up the next thing itself when a ticket closes or the diagrams fall behind, instead of waiting to be asked — bounded so it fixes only what blocks the job and tickets the rest. | 10 agents, 21 commands, 16 skills, 20 hook entries |
| [`obsidian`](obsidian) | Memory | Makes an Obsidian vault Claude Code's durable, token-efficient memory. Cross-platform setup for the Local REST API bridge and MCP registration, a vault-contract guard hook that ships every check off until a target vault's own `CLAUDE.md` says to turn it on, gardening and reflection agents with no fabricated citations, canvas and Map-of-Content generation, and `graphify` wiring that keeps generated code graphs outside the vault. No vault path is hardcoded — it detects from Obsidian's own vault registry or a config file. | Wanting Claude Code sessions to remember architecture decisions and patterns across `/clear` without re-explaining them; a vault that has grown past casual browsing and needs gardening instead of manual curation; an Obsidian Git plugin auto-committing on a timer into a directory that turns out not to be a git repo; a vault whose own `CLAUDE.md` has drifted from what the filesystem actually shows; wanting a canvas or Map of Content that stays a spatial/structural aid rather than a second, driftable copy of facts already in notes. | 7 commands, 2 agents, 3 skills, 8 hook entries |

**Provides** counts what the plugin registers with Claude Code. The per-item breakdown is in [`PLUGINS.md`](PLUGINS.md); the authoritative upstream guide is [`crew/README.md`](crew/README.md).

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
3. Think about the shell before you register a hook. A `hooks.json` entry's `shell` field (`"bash"` or `"powershell"`) is documented and Claude Code does read it — setting `"powershell"` runs that entry via PowerShell on Windows without needing `CLAUDE_CODE_USE_POWERSHELL_TOOL`, since hooks spawn the interpreter directly. What is not configurable is the shell form's default: a bare `command` string (no `args`) goes to `sh -c` on macOS/Linux and to **Git Bash** on Windows — or to PowerShell only when Git Bash isn't installed. So a `bash` resolved from some non-MSYS parent process is not what actually runs a plain `command`. A hook that judges a *command* branches on `tool_name`, not on OS (a `Bash` tool call is bash syntax even on Windows); a hook that judges no command can be registered once per shell it needs, each with the matching `shell` field, or handed off from inside one script to its twin — assume nothing about which interpreter is running you. Any hook that can **block** also needs a committed regression suite with must-block and must-allow cases, sabotage-tested so you know it can go red — see `plugin/crew/hooks/scripts/_test/`.
4. Register it in all four places, the same rule skills follow:
   1. [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) — `name`, `source` (`./plugin/<name>`), `description`, `version`.
   2. The table above — all five columns. **Use cases** should be concrete situations that would send someone looking for it, not a restatement of *What it does*.
   3. [`PLUGINS.md`](PLUGINS.md) — a section with the full component breakdown.
   4. [`../README.md`](../README.md), inside the `<!-- BEGIN plugin/README.md -->` block, plus the plugin count wherever it appears as a number.
   5. Both install scripts — `PLUGIN_KEYS` / `PLUGIN_NAME` in the `.sh`, `$script:PluginCatalog` in the `.ps1`. Keep the two in the same order, with the same text.
5. Default the menu item to **off** if the plugin registers hooks. A hook is not advisory, and a bootstrap run should not add one to someone's machine without them ticking a box.

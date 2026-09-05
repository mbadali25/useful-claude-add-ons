# Plugins

Each subdirectory here is a self-contained [Claude Code plugin](https://docs.claude.com/en/docs/claude-code/plugins) — a `.claude-plugin/plugin.json` manifest plus any `agents/`, `commands/`, `hooks/`, or `skills/` it bundles. Every one is registered in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and installs the same way a skill from [`../skills/`](../skills/) does.

**A plugin is not a bigger skill.** A skill is a document Claude reads when the conversation matches its `description`. A plugin can also register **subagents** (their own context window and tool set), **slash commands** (you type them), and **hooks** (shell scripts the harness runs on tool use, on stop, on compact, on session start — they execute whether or not Claude agrees with them). That last part is why plugins here are opt-in in the install scripts and skills are not: a hook can block a command you ran on purpose.

See [`PLUGINS.md`](PLUGINS.md) for what each plugin actually contains — every command, agent, skill, and hook, and what starts running the moment it is enabled. See [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md) for the style bundled skills must follow, and [`../Skill-Pipeline.md`](../Skill-Pipeline.md) for how a change gets from a draft to something the team can install.

## What's new

Generated from [`UPDATE.md`](UPDATE.md) by `scripts/sync-updates.py`. Edit that file, not this block.

<!-- BEGIN plugin/UPDATE.md -->

### localgpu 0.1.0

A new plugin: the GPU in this machine, as a sidecar for one repository. Two
halves - a semantic index the session you are already in can search, and a
separate session that runs entirely on the local model.

| Added | What it does |
|---|---|
| `/localgpu:setup` | Six detect-then-act steps - resolve the install root, verify Ollama is installed *and* serving, pull the two models, run the bootstrap (venv, dependencies, the `localgpu` CLI), write the config, register the MCP server. Asks before writing anything, and will not install Ollama silently |
| `/localgpu:doctor` | Seven checks - Ollama, model tags, venv, config provenance, index freshness, MCP registration, VRAM - each reported whether or not it passes, ending in exactly one next step |
| `/localgpu:index` | Build or refresh the vector index. Incremental by default; a changed embedding model forces a full rebuild, because vectors from two models are not comparable |
| `/localgpu:search` | Semantic search of the repo - `file:line` plus a three-line excerpt, via the `search_code` MCP tool |
| `/localgpu:ask` | Retrieve first, then put the question and the excerpts to the local chat model. Always labelled `qwen2.5-coder:7b (local)`, always with its sources |
| `/localgpu:crew` | Report-only: which crew roles a local 7B could take over and which it must not, ending in the one supported route - `localgpu shell`. Writes nothing |
| `localgpu shell` | A **separate** Claude Code session on the local model. Starts the bundled proxy on a loopback port, launches a second `claude` against it, and leaves your current session and crew's config exactly as they were |
| `localgpu proxy` | The same proxy in the foreground, for debugging it or for pointing something other than Claude Code at the local model |
| `localgpu` skill | The paths, the two config layers and their precedence, the model tags, the VRAM rules, and the `mcp.json` template the commands render |

`localgpu shell` and `localgpu proxy` are a console script, not slash commands:
the bootstrap installs it into `$LOCALGPU_HOME/venv`, and you type it in a
terminal. What makes them possible is `cli/anthropic_proxy.py`, which speaks the
**Anthropic Messages API** on the front and Ollama's `/api/chat` on the back.
That translation is the feature, not plumbing: `ANTHROPIC_BASE_URL` makes a
client POST `/v1/messages`, while Ollama's OpenAI-compatible surface is
`/v1/chat/completions` with a different body, so pointing one straight at the
other 404s on every request.

- **What crosses intact**: system prompts, multi-turn text, tool definitions,
  tool calls, tool results, stop sequences, sampling options, and both reply
  modes - non-streaming and Anthropic's SSE event order.
- **What does not, and is reported rather than faked**: images (replaced with a
  visible placeholder, because a 7B coder model has no vision), thinking blocks,
  prompt caching (`cache_control` accepted and ignored, cache usage reported as
  zero), and token counts, which are Ollama's own and will not match Anthropic's
  tokenizer.
- **Tool calls the model writes as prose are recovered.** The shipped
  `qwen2.5-coder:7b-instruct-q4_K_M` answers a tools request by putting the call
  into `content` as JSON and leaving `tool_calls` empty. Claude Code reads that as
  prose: the tool never runs and nothing errors. The proxy promotes it to a real
  `tool_use` block under four narrow conditions, each with a must-not-fire test,
  so it cannot invent a call the user never asked for. Without it the shell could
  not drive a single tool.
- **The catch, printed on every launch because nothing enforces it**: everything
  in that session is the 7B, including any `/crew:*` command run inside it. Use it
  for exploring and drafting, not for gates - a 7B review is labelled exactly like
  a real one. The child process also has `ANTHROPIC_AUTH_TOKEN` and
  `ANTHROPIC_PROFILE` stripped, since either would outrank the API key and send the
  session back to the real API without saying so.

Also worth knowing before enabling it:

- **No hooks, so nothing starts running when it is enabled.** There is no
  background indexer and no watcher - the index goes stale until someone runs
  `/localgpu:index`. That is deliberate: GPU work firing on somebody else's
  schedule evicts whatever model was resident, which on an 8 GB card is the
  difference between a fast index run and a slow one.
- **Installing the plugin downloads nothing.** Ollama, the virtualenv and roughly
  5 GB of model weights come from `/localgpu:setup`, per repository, after it has
  shown the plan and asked.
- **Nothing leaves the machine.** No prompt, no file and no embedding reaches a
  vendor, which is the point - code that is not permitted to reach an API still
  gets search by meaning and a fast first-pass answer.
- **The local model is a triage tier, not a second opinion.** A 7B model at 4-bit
  quantization sits several tiers below the model reading these commands, so
  every command that reaches for it attributes the answer and prints the excerpts
  it was given.

### crew 0.15.1

Three new agents and a skill, taking crew to 14 agents and 17 bundled skills.

| Added | What it does |
|---|---|
| `infrastructure-architect` | Designs and reviews AWS network and account architecture — VPCs, routing, connectivity, DNS, ingress, landing zones. Returns the design with its tradeoffs. Never applies anything to a live account. |
| `scribe` | Keeps the durable record: ADRs, CHANGELOG entries, handoff notes, and what was tried and rejected. ADRs are append-only — a correction is a new ADR, never an edit to the old one. |
| `researcher` | External research only — library and SDK docs at the version actually pinned, API behaviour, vendor limits, standards. Every claim carries its source; it refuses to answer a version, a limit, or an API surface from memory. |
| `crew-house-style` skill | House style for documents a human will read: format choice, headings, capitalization, palette. Routes to the office and diagram skills rather than reimplementing generation. |

Also in 0.15.0:

- **`docs-writer` exports for humans.** Documentation a person will consume ships
  as HTML, DOCX or PDF, not raw markdown. The markdown under `docs/` stays the
  source of truth — the export is an additional artifact, so anything reading
  those paths keeps working. Repo-native files (`CHANGELOG.md`, `README.md`,
  `CLAUDE.md`, ADRs) stay markdown, because exporting one breaks the tool that
  reads it. `docs-writer` also gained the return contract it never had.
- **`dba` covers DynamoDB as its own model**, not as a row in a relational
  checklist — access-pattern-first, single-table design, partition-key
  cardinality, GSI backfill cost, the creation-time-only nature of LSIs, and the
  400KB item limit. Relational review is now split by engine, because lock
  behaviour under `ALTER TABLE` differs across Postgres, MySQL/InnoDB and SQL
  Server, and the old text applied Postgres vocabulary to all three.
- **`planner` asks what a decision forecloses** — whether it is one-way, what
  undoing it costs later, and the cheapest experiment that would settle it before
  committing.
- **Agents can now load the skills they cite.** Eight agents referenced a crew
  skill without declaring `skills:` frontmatter, so the reference was decoration:
  naming a skill does not load it. `browser-tester`, `docs-writer`,
  `infrastructure-architect`, `planner`, `pm`, `qa-reviewer`, `scribe` and
  `smoke-author` now declare what they cite.
- **`explorer` no longer orders a write it cannot perform.** It held
  `Read, Grep, Glob` and was told to append findings to memory; it now returns a
  `**Durable:**` block for its caller to persist.
- **The PM's guards apply on every path.** Removal needing an explicit yes was
  previously gated to `authority: act`, which switched it off exactly when a user
  told a `report-only` PM to go ahead.

<!-- END plugin/UPDATE.md -->

## Overview

| Plugin | Category | What it does | Use cases | Provides |
|---|---|---|---|---|
| [`crew`](crew) | Workflow / QA | A virtual dev team for multi-repo legacy work — file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure instead of offering an opinion. Hooks enforce unsafe commands, unverified turns, and unearned production deploys. Roles exist only where they buy an isolated context window, a restricted tool set, or genuinely independent eyes; the manager is the one role that can assign work rather than only reporting on it, opt-in via `pm.authority`, and BA/architecture stay files and commands. Codex QA, Jira or ServiceDesk Plus, an Obsidian Kanban board for tickets, Obsidian memory, a code graph, and Teams/Telegram notifications are all optional. | Several repositories, mixed stacks, legacy code, and almost no test coverage; a change that needs review by something that did not write it; wanting `terraform apply`, force-push, and destructive DDL blocked by a hook rather than by good intentions; a turn that should fail when the checks its changed paths map to go red; a production deploy that should be refused unless qa signed off on **that exact sha** and the rollback runbook is still verified; wanting to know what every endpoint and scheduled job actually does; losing the thread across a `/clear` or an auto-compact; wanting the crew to pick up the next thing itself when a ticket closes or the diagrams fall behind, instead of waiting to be asked — bounded so it fixes only what blocks the job and tickets the rest. | 14 agents, 21 commands, 17 skills, 20 hook entries |
| [`gizmoduck`](gizmoduck) | Security | Runs [Nuclei](https://github.com/projectdiscovery/nuclei) vulnerability scans against hosts and websites you are authorised to test, then does the part that usually gets skipped: diffs the run against a previous baseline so you see what is genuinely new, renders a triaged report as Markdown, HTML or PDF, and opens or syncs ServiceDesk Plus tickets for Critical and High findings. Nuclei is MIT-licensed and self-hosted, so the whole loop runs locally with no export step and no API quota. Bootstrap scripts for WSL/Linux and Windows fetch the engine and the community template set; `/gizmoduck:doctor` tells you which half of the toolchain is missing rather than failing mid-scan. Registers no hooks and no agents — it is six commands over one Python CLI. | Wanting a scheduled external scan whose findings land in the ticket queue instead of a PDF nobody opens; needing to show an auditor what changed between this quarter's scan and last quarter's; a scan whose Critical and High findings should become tickets automatically while the Mediums stay in the report; re-rendering a report at a different severity floor without paying for another scan; a scanner that stops working on a new machine and you want to know whether it is `nuclei`, the templates, `python`, or `wkhtmltopdf`. | 6 commands, 1 skill |
| [`localgpu`](localgpu) | Local models | Runs models on your own GPU through [Ollama](https://ollama.com) and puts a repository or folder behind them: `bootstrap.sh` / `bootstrap.ps1` install Ollama, a private virtualenv, the chat and embedding models, and a `localgpu` CLI, then an MCP server indexes a tree into a vector store on disk and exposes search and ask over it. Nothing is a service call — no prompt, no file, and no embedding leaves the machine, which is what makes it usable on code that is not allowed to reach a vendor API. `localgpu shell` goes further and runs a *whole separate* Claude Code session on the local model, through a bundled proxy that translates the Anthropic Messages API into Ollama's `/api/chat` — the two do not otherwise speak, and a client pointed straight at Ollama 404s on every request. `/localgpu:doctor` tells you which half of the toolchain is missing (Ollama, the venv, a pulled model, a built index) rather than failing mid-answer, and `/localgpu:crew` reports which `crew` roles a local 7B could take over and refuses, in writing, to point crew's gates at one. Registers no hooks and no agents — six commands, one bundled skill, an MCP server you register yourself in `/localgpu:setup`, and a `localgpu` CLI its bootstrap installs into the venv. | Code or documents that are not permitted to leave the network but still need a model over them; wanting to ask "where is this handled" against a repo too large to read into a context window; a laptop or workstation with a GPU sitting idle while every query bills a vendor; wanting a throwaway session that runs entirely on the local model for exploring and drafting; wanting an honest account of which `crew` work a local 7B could take over and which it must not; an offline machine, a flight, or an outage at the provider; a first-run failure where you want to know whether it is Ollama, the venv, the model pull, or the index. | 6 commands, 1 skill, 1 CLI — no agents, no hooks, plus one local MCP server `/localgpu:setup` registers |
| [`obsidian-vault`](obsidian-vault) | Memory | Makes one or more Obsidian vaults Claude Code's durable, token-efficient memory. Cross-platform, multi-vault setup for the Local REST API bridge and MCP registration (one server per vault, never one juggling two), a vault-contract guard hook that ships every check off until a target vault's own `CLAUDE.md` says to turn it on, gardening and reflection agents with no fabricated citations, canvas and Map-of-Content generation, and `graphify` wiring into a separate, dedicated codegraphs vault. No vault path is hardcoded — it detects from Obsidian's own vault registry or a config file. Named `obsidian-vault`, not `obsidian`, so it cannot collide with a third-party plugin of that name. | Wanting Claude Code sessions to remember architecture decisions and patterns across `/clear` without re-explaining them; a second machine-generated vault (a code graph running past 100k notes) that needs different defaults than a hand-curated one; an Obsidian Git plugin auto-committing on a timer into a directory that turns out not to be a git repo; a vault whose own `CLAUDE.md` has drifted from what the filesystem actually shows; wanting a canvas or Map of Content that stays a spatial/structural aid rather than a second, driftable copy of facts already in notes. | 8 commands, 2 agents, 3 skills, 8 hook entries |

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

# Plugins

Each subdirectory here is a self-contained [Claude Code plugin](https://docs.claude.com/en/docs/claude-code/plugins) — a `.claude-plugin/plugin.json` manifest plus any `agents/`, `commands/`, `hooks/`, or `skills/` it bundles. Every one is registered in [`../.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json) and installs the same way a skill from [`../skills/`](../skills/) does.

**A plugin is not a bigger skill.** A skill is a document Claude reads when the conversation matches its `description`. A plugin can also register **subagents** (their own context window and tool set), **slash commands** (you type them), and **hooks** (shell scripts the harness runs on tool use, on stop, on compact, on session start — they execute whether or not Claude agrees with them). That last part is why plugins here are opt-in in the install scripts and skills are not: a hook can block a command you ran on purpose.

See [`PLUGINS.md`](PLUGINS.md) for what each plugin actually contains — every command, agent, skill, and hook, and what starts running the moment it is enabled. See [`../Skill-Authoring-Standard.md`](../Skill-Authoring-Standard.md) for the style bundled skills must follow, and [`../Skill-Pipeline.md`](../Skill-Pipeline.md) for how a change gets from a draft to something the team can install.

## What's new

Generated from [`UPDATE.md`](UPDATE.md) by `scripts/sync-updates.py`. Edit that file, not this block.

<!-- BEGIN plugin/UPDATE.md -->

### crew 0.16.4

**`/crew:config` — see where every setting comes from, and set the ones that
belong to the machine.** The machine-global config at
`~/.claude/crew/config.json` sets defaults for every crew repo you have, and
until now nothing in crew wrote it, asked about it, or mentioned it existed.
Writing it by hand meant knowing the file existed, where it lived, which keys
it took and how it layered. `templates/global.template.json` is now the shape,
and `/crew:config` is the guided walkthrough.

The point of the command is the **source** column. `--explain` prints every
globally-settable key with its effective value and the layer that decided it —
`repo`, `global`, or `default`. That is the question the failure behind this
work could not answer: a global file that carried `tier`, `roles`, `qa` and
`sdp` but **no `pm` block** silently resolved every repo on the machine to
`pm.authority: report-only`, while the user believed the PM was autonomous.
Every file was valid. The behaviour was a default nobody chose, and nothing
surfaced it.

The global template is deliberately **not** a copy of the repo one. `tracker`,
`jira.project`, `obsidian.boardDir`, `graph.out` and `platform.*` are facts
about one checkout; shipping them globally invites a vault path set once that
every repo then inherits. What is left is what is genuinely a property of the
machine or the person: `pm.authority`, the `qa` and `dev` provider tables,
`secondOpinion`, `notify` and `memory.vaultPath`. It carries no `schema` at
all — that value is read from the repo file alone, so a global one can never
make an unmigrated repo look current.

Four rules the writer enforces in code rather than in prose. It **merges**, so
a key in an existing global file that the walkthrough never asked about
survives. It **refuses**, by name and with exit 2, any key that describes a
repository — which is also what makes `graph.obsidian.confirmed` un-grantable
from a guided flow, since that flag is consent to write into your own notes
outside the repo, not a capability. It is a **dry run by default**; `--apply`
is a second, deliberate call. And it **marks a widening of `pm.authority`** on
both the plan and the write, because that is the one value you cannot recover
from by noticing.

**`/crew:upgrade` migrates the whole config, and says what it changed.** It
brought `pm` and `graph` forward and stamped `schema` current regardless, so a
config predating 0.14.4 came out marked up to date while still missing
`qa.order` and the entire `dev` block — and an absent `qa.order` made
`/crew:model` report zero candidates and "no independent reviewer" for a setup
that reviews fine. `qa` and `dev` now migrate too.

So does `roles`: an upgrade **adds** the roles a later release put at a tier
the config already declares, rather than reporting them and leaving you to
re-derive the change. It cannot grow a crew past its own declared tier —
moving up is still `/crew:scale`, with evidence — and it never removes
anything, because `/crew:pm offboard` keeps its explicit-yes gate. The run
states the roles it added and the tier it moved from and to, at the CLI and in
`.crew/codemap/UPGRADE.md`, every time, including when the answer is none.

`schema` is now stamped only when every block actually migrated. A `pm`,
`graph`, `qa`, `dev` or `roles` value that arrived as the wrong type is left
exactly as you wrote it, named in the report, and the status is `upgraded with
unmigrated blocks` — so the repo still reports an upgrade as needed instead of
being marked done with a block nobody migrated. `/crew:upgrade` also reports
what is wrong with the machine-global file, and fixes none of it: that is
`/crew:config`'s job, and it asks first.

**The three agents added in 0.15.x joined the tier ladder**, at tier 2 beside
`dba` and `docs-writer`. `infrastructure-architect`, `scribe` and `researcher`
shipped as definitions with no tier row, so `/crew:scale` would not propose
them and `/crew:pm` would not onboard them from evidence. The ladder itself now
lives in `crew_state.ROLE_TIERS`, because computing a tier from a role list is
arithmetic and a heading in a skill file should not decide what an upgrade
writes; the two markdown tables that describe it are checked against that dict
by a committed test instead.

### obsidian-vault 0.3.0

**Vault profiles.** A vault is either authored, where a person reads it, or
generated, where only Claude greps it, and the right plugin set differs. One
definition in `hooks/scripts/vault_profiles.py` now decides both what to
install and what to strip — two lists would have drifted. `vault_ops.py
profile` reports the detected kind **with the evidence behind it**, never a
config flag you have to set, and always overridable.

The sets, read off working vaults rather than invented: `bridge` is
`obsidian-local-rest-api` alone, the floor for any vault Claude must reach at
all. `graph` adds `code-graph` and nothing else — omnisearch, dataview,
backlinks and text-extractor are the index-building cost, and nothing reads
their output in a vault only Claude greps. `authored` is the fuller human set,
with omnisearch and text-extractor only below 50,000 notes.

Two rules the profile work does not bend. A plugin is confirmed **one at a
time**, because any of them can be load-bearing for hundreds of notes through
a Dataview query, a Templater template or a Breadcrumbs edge — so a bare
`enable-plugin --apply` writes only the bridge floor and every other plugin
needs naming. And **splitting a vault is the last resort, not the first**: the
real limit is index-building plugins rather than note count, a split
permanently breaks every wikilink crossing it, and where one is genuinely
warranted the seam is provenance, not size. The report names the seam and
counts the wikilinks that would break; nothing moves without a yes.

**Note templates, because the contract was enforced but not served.**
`vault_guard.py` blocks a write that violates the six-key frontmatter
contract, and it is right to. But the plugin shipped no templates, so every
conforming note was written by hand and fixed afterwards — a wall with no
door. `templates/` now holds `memory`, `concept`, `decision`, `session`,
`source` and `design`, each verified to pass the guard on the first write, and
`/obsidian-vault:note` creates one. `design` ships as a `type: concept`
variant rather than a new type: the guard has no type enum, so a new type
would have passed while being invisible to the contract's own type keys and to
any Dataview query keyed on them.

**The bridge status tells four states apart.** A dead Obsidian window and a
misconfigured server both produce a silent port, and until now both rendered
as one line: down. They are now `NOT OPEN`, `NO SERVER`, `NOT ANSWERING YET`
and `UP`, plus an explicit `DOWN, CAUSE NOT DETERMINED`. The third matters
most on a large vault, where a socket that accepts but does not answer means
indexing is still running — not a fault to chase.

That last verdict is the point of the change. The previous diagnostic named a
cause with confidence and was wrong, which sent its reader to a file that was
already correct. Guidance is now derived only from evidence the script
actually checked, and where two causes cannot be separated it says so and
names the check that would separate them. Process attribution is honest about
its limits: window titles name a vault on Windows, and on macOS and Linux the
script reports presence and says attribution is undetermined rather than
guessing.

### obsidian-vault 0.2.0

The plugin can now **repair a vault bridge**, where before it could only
describe how. `hooks/scripts/vault_ops.py` is the action layer, dry-run by
default and writing only under `--apply`:

| Subcommand | Does |
|---|---|
| `scan` | Every vault on the machine — path, real ports, whether the REST plugin is installed, whether it is registered |
| `diagnose` | Health verdict per vault, port collisions named first |
| `fix-ports` | Assigns non-colliding ports and writes `data.json` |
| `reload` | `app:reload` over the REST API, so a `data.json` edit actually takes effect |
| `register` | Adds or refreshes each vault's MCP server registration |
| `enable-plugin` | Enables a plugin whose files are already on disk. It does not download one, and no longer claims to |
| `add-vault` | Names a vault in config so `--vault <name>` resolves - the first step of setting one up, not a record of it afterwards |
| `graph-health` | The codegraphs vault's `<org>/<repo>` layout, coverage and staleness |

Two new commands drive it: `/obsidian-vault:repair` acts, and
`/obsidian-vault:install` sets up a vault that has no REST plugin at all.
`/obsidian-vault:doctor` stays read-only and now enforces that with its tool
list rather than asserting it in prose.

**The diagnostic was wrong, and the fix is the point of this release.** Two
vaults declaring the same HTTPS port is not a partial failure: the loser's
plugin fails to start its server at all, which takes its HTTP listener down
with it. That produced three symptoms with one cause — the HTTP port never
listened, the HTTPS port answered with the *other* vault's API key, and it
served the *other* vault's files. The shipped hook blamed
`enableInsecureServer`, which was already on. It now compares ports across
every vault before it blames any flag, and reports a vault with no plugin and
a wrong-vault-answering server as distinct verdicts.

The hook also stopped deriving the HTTPS port as the HTTP port plus one. That
assumption is false in practice — one vault on this machine runs HTTPS *below*
its HTTP port. Both ports are read from the vault's own `data.json`, where
`port` is HTTPS and `insecurePort` is HTTP. The same correction was applied to
`init`, the setup skill and the README, which all taught the plus-one rule.

Two facts worth knowing before touching any of it: `curl -k` reaches the HTTPS
port where Claude Code's Node MCP client rejects the self-signed certificate,
and the plugin reads `data.json` only at load, so a stale instance disagrees
with disk on both the port and the API key until the window is reloaded.

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

## What's new

Generated from `UPDATE.md` in this directory by `scripts/sync-updates.py`. Edit that file, not this block.

<!-- BEGIN plugin/UPDATE.md -->

### crew 0.15.0

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
| [`crew`](crew) | Workflow / QA | A virtual dev team for multi-repo legacy work — file-backed tickets, one implementation session, an independent reviewer, and deterministic gates that block on failure instead of offering an opinion. Hooks enforce unsafe commands, unverified turns, and unearned production deploys. Roles exist only where they buy an isolated context window, a restricted tool set, or genuinely independent eyes; the manager is the one role that can assign work rather than only reporting on it, opt-in via `pm.authority`, and BA/architecture stay files and commands. Codex QA, Jira or ServiceDesk Plus, an Obsidian Kanban board for tickets, Obsidian memory, a code graph, and Teams/Telegram notifications are all optional. | Several repositories, mixed stacks, legacy code, and almost no test coverage; a change that needs review by something that did not write it; wanting `terraform apply`, force-push, and destructive DDL blocked by a hook rather than by good intentions; a turn that should fail when the checks its changed paths map to go red; a production deploy that should be refused unless qa signed off on **that exact sha** and the rollback runbook is still verified; wanting to know what every endpoint and scheduled job actually does; losing the thread across a `/clear` or an auto-compact; wanting the crew to pick up the next thing itself when a ticket closes or the diagrams fall behind, instead of waiting to be asked — bounded so it fixes only what blocks the job and tickets the rest. | 14 agents, 24 commands, 17 skills, 20 hook entries |
| [`gizmoduck`](gizmoduck) | Security | Runs [Nuclei](https://github.com/projectdiscovery/nuclei) vulnerability scans against hosts and websites you are authorised to test, then does the part that usually gets skipped: diffs the run against a previous baseline so you see what is genuinely new, renders a triaged report as Markdown, HTML or PDF, and opens or syncs ServiceDesk Plus tickets for Critical and High findings. Nuclei is MIT-licensed and self-hosted, so the whole loop runs locally with no export step and no API quota. Bootstrap scripts for WSL/Linux and Windows fetch the engine and the community template set; `/gizmoduck:doctor` tells you which half of the toolchain is missing rather than failing mid-scan. Registers no hooks and no agents — it is six commands over one Python CLI. | Wanting a scheduled external scan whose findings land in the ticket queue instead of a PDF nobody opens; needing to show an auditor what changed between this quarter's scan and last quarter's; a scan whose Critical and High findings should become tickets automatically while the Mediums stay in the report; re-rendering a report at a different severity floor without paying for another scan; a scanner that stops working on a new machine and you want to know whether it is `nuclei`, the templates, `python`, or `wkhtmltopdf`. | 6 commands, 1 skill |
| [`obsidian-vault`](obsidian-vault) | Memory | Makes one or more Obsidian vaults Claude Code's durable, token-efficient memory. Cross-platform, multi-vault setup for the Local REST API bridge and MCP registration (one server per vault, never one juggling two), a vault-contract guard hook that ships every check off until a target vault's own `CLAUDE.md` says to turn it on, gardening and reflection agents with no fabricated citations, canvas and Map-of-Content generation, and `graphify` wiring into a separate, dedicated codegraphs vault. No vault path is hardcoded — it detects from Obsidian's own vault registry or a config file. Named `obsidian-vault`, not `obsidian`, so it cannot collide with a third-party plugin of that name. | Wanting Claude Code sessions to remember architecture decisions and patterns across `/clear` without re-explaining them; a second machine-generated vault (a code graph running past 100k notes) that needs different defaults than a hand-curated one; an Obsidian Git plugin auto-committing on a timer into a directory that turns out not to be a git repo; a vault whose own `CLAUDE.md` has drifted from what the filesystem actually shows; wanting a canvas or Map of Content that stays a spatial/structural aid rather than a second, driftable copy of facts already in notes. | 11 commands, 2 agents, 3 skills, 8 hook entries |

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

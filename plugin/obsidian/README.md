# obsidian

Makes an Obsidian vault Claude Code's durable, token-efficient memory: code
choices, decisions, architecture, links between code, and patterns - captured
automatically, gardened into concepts, recalled cheaply, and mapped visually.
Cross-platform (Windows, Linux, macOS); no vault path is hardcoded.

## Install

```bash
claude plugin install obsidian@useful-claude-add-ons
```

Then run `/obsidian:init` once. It installs Obsidian if missing, configures
the Local REST API bridge, registers the `obsidian` MCP server, and writes
`~/.claude/obsidian/config.json` - the one file every hook and command here
reads for the vault path.

## What it registers

| Component | Count |
|---|---|
| Commands | 7: `init`, `doctor`, `optimize`, `canvas`, `map`, `graph`, `garden`, `reflect` |
| Agents | 2: `obsidian:gardener`, `obsidian:reflector` |
| Skills | 3: `obsidian-setup`, `obsidian-memory-contract`, `obsidian-scheduling` |
| Hooks | 8 entries (4 scripts x `.sh`/`.ps1`) across `SessionStart`, `PostToolUse`, `SessionEnd`, `PreCompact` |

**Read the Hooks section below before installing.** Commands and agents wait
to be asked; hooks do not.

## Hooks - the part that runs without being asked

| Script | Event | What it does |
|---|---|---|
| `bridge-status.sh`/`.ps1` | `SessionStart` | Probes the Local REST API bridge and states plainly whether `mcp__obsidian__*` will work this session - down, wrong port, or rejected key, each with the actual fix. Never blocks. |
| `vault-guard.sh`/`.ps1` | `PostToolUse` on `Edit`/`Write`/`MultiEdit` | Enforces the configured vault's frontmatter contract, ASCII rule, and canvas well-formedness - **all three OFF by default.** `/obsidian:init` turns one on only when it finds the matching rule stated in the target vault's own `CLAUDE.md`. Can block (exit 2) with the specific fix on stderr. |
| `vault-capture.sh`/`.ps1` | `SessionEnd`, `PreCompact` | Appends one line (session id, cwd, transcript path) to `<vault>/inbox/pending-reflect.md`. Costs nothing, cannot break a session. |

Every script delegates to one Python module shared by both the bash and
PowerShell wrapper, so the two flavours cannot drift from each other - the
pattern crew's `platform-sync.sh`/`.ps1` established. Vault path resolution
(`hooks/scripts/obsidian_common.py`) is: `OBSIDIAN_VAULT_PATH` env var, then
`~/.claude/obsidian/config.json`, then Obsidian's own vault registry, then
nothing - a hook that cannot resolve a vault stays silent rather than
guessing one.

**`vault-guard` is the one hook that can block**, and it ships a committed,
sabotage-tested regression suite: `hooks/scripts/_test/run-tests.sh` (12
cases, must-block and must-allow, plus a case proving the OFF-by-default
toggles actually gate the checks).

## Commands

| Command | Does |
|---|---|
| `/obsidian:init [vault-path]` | Install/configure Obsidian, the REST bridge, and plugin config |
| `/obsidian:doctor` | Diagnose the REST bridge, a git-configured-but-not-a-git-repo vault, `CLAUDE.md` drift against reality, gardener staleness, and empty structural folders - offers fixes, never applies one without confirmation |
| `/obsidian:optimize` | Reports per-plugin cost on a large vault; every install/removal proposed one at a time, never batched |
| `/obsidian:canvas <topic>` | Builds/refreshes a `.canvas` from a topic's wikilink neighborhood - canvases hold no facts |
| `/obsidian:map <area>` | Builds/refreshes a Map-of-Content note |
| `/obsidian:graph [repo]` | Wraps `graphify` for a repo's code graph, kept **outside** the vault with a stub note pointing to it |
| `/obsidian:garden` | Runs the gardener now instead of waiting for its schedule |
| `/obsidian:reflect <topic>` | Asks the vault what it knows, and what contradicts |

## Agents

`obsidian:gardener` distills queued sessions into concept/decision/daily
notes with provenance, never fabricating a citation. `obsidian:reflector` is
read-only recall plus contradiction-finding. Neither is scheduled by this
plugin - see the `obsidian-scheduling` skill for wiring one to Task Scheduler,
cron, or a systemd user timer, with the unattended-permissions tradeoff stated
plainly rather than buried in a script comment.

## Skills

- `obsidian-setup` - the steps `/obsidian:init` follows, in full, including
  per-OS install and the `enableInsecureServer`/port-27123-not-27124
  troubleshooting that a wrong guess here silently breaks.
- `obsidian-memory-contract` - the six-key frontmatter contract, evidence
  rules, tag discipline, and the canvas-holds-no-facts rule. A vault's own
  `CLAUDE.md` always wins where it differs; this is the generic starting
  shape.
- `obsidian-scheduling` - cross-platform scheduling reference. This plugin
  never installs a scheduled task itself.

## Configuration

`~/.claude/obsidian/config.json`:

```json
{
  "vaultPath": "C:\\repos\\claude-memories",
  "guard": {
    "asciiOnly": false,
    "requireFrontmatter": false,
    "checkCanvas": true,
    "notesPrefix": "wiki/"
  }
}
```

This is user-level, not per-repo config: a vault is one resource shared across
every project's sessions, unlike crew's `.crew/config.json`, which is scoped
to a single repo's ticket state. Never commit this file to a project repo.

## Related - read before assuming this replaces something

This repo already has several other pieces of Obsidian tooling, and **this
plugin does not consolidate or replace any of them** - that was out of scope
for the change that introduced this plugin, and each needs a deliberate look
before merging anything:

- **Naming collision.** `scripts/install-prerequisites.sh` menu item 18
  ("Obsidian desktop + claude-obsidian + obsidian-skills plugins") already
  installs a plugin literally named `obsidian`, from the third-party
  `obsidian-skills` marketplace (`kepano/obsidian-skills`). Claude Code
  namespaces plugins by marketplace, so `obsidian@useful-claude-add-ons` and
  `obsidian@obsidian-skills` can both be installed without conflict - but two
  things both called plainly "obsidian" in prose, README rows, and menu
  labels is a real footgun. Worth a rename (`obsidian-memory`?) before this
  ships, or an explicit decision that the collision is acceptable.
- **`claude-obsidian-setup/`** at the repo root already creates and verifies
  an Obsidian vault (`setup-claude-obsidian.sh`/`.ps1`) and manages a plugin
  profile (`install-obsidian-plugins.sh`/`.ps1`,
  `obsidian-plugin-profile.json`). This plugin's `/obsidian:init` and
  `/obsidian:optimize` were built without reading that directory in depth and
  likely overlap it substantially.
- **`vault-automation/`** at the repo root is Windows-only PowerShell prior
  art for capture hooks, a scheduled gardener, and a `HOME.md` dashboard. Its
  scheduling and dashboard design informed the `obsidian-scheduling` skill and
  the `obsidian:gardener` agent's prompt shape here, but the two were not
  reconciled - both can currently run side by side and would double-process
  the same session queue if both were configured against the same vault.
- **`skills/obsidian-canvas`** and **`skills/obsidian-vault-server`** are
  already-registered marketplace skills covering JSON Canvas authoring and a
  self-hosted Ubuntu vault + SSH-tunneled REST bridge respectively.
  `/obsidian:canvas` defers to `obsidian-canvas` where installed rather than
  reimplementing it (see that command's file); the vault-server skill was not
  otherwise cross-referenced.
- **`skills/claude-memories-vault`** and **`skills/claude-memories-canvas`**
  are vault-specific tuned versions of what `obsidian-memory-contract` teaches
  generically - that skill explicitly yields to them where installed.

None of this blocks using the plugin standalone against a vault that has none
of the above. It does mean this should not merge as "the" Obsidian plugin for
this repo without someone deciding how it fits alongside what already exists.

## Uninstall

```bash
claude plugin uninstall obsidian@useful-claude-add-ons
```

The hooks go with it. `~/.claude/obsidian/config.json` is not removed
automatically - delete it by hand if you want no trace.

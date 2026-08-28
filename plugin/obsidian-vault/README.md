# obsidian-vault

Makes one or more Obsidian vaults Claude Code's durable, token-efficient
memory: code choices, decisions, architecture, links between code, and
patterns - captured automatically, gardened into concepts, recalled cheaply,
and mapped visually. Cross-platform (Windows, Linux, macOS); no vault path is
hardcoded; supports multiple named vaults on one machine.

Named `obsidian-vault`, not `obsidian` - a third-party plugin literally named
`obsidian` (from the `obsidian-skills` marketplace) is already commonly
installed alongside this repo's tooling, and two things both called plainly
"obsidian" in prose and menus is a real footgun even though Claude Code
namespaces plugins by marketplace and the two can coexist without breaking.

## Install

```bash
claude plugin install obsidian-vault@useful-claude-add-ons
```

Then run `/obsidian-vault:init` once per vault. It installs Obsidian if
missing, configures the Local REST API bridge, registers a per-vault MCP
server, and writes `~/.claude/obsidian/config.json` - the one file every hook
and command here reads.

## Multiple vaults

A single machine can have more than one vault configured - the common case is
a hand-curated memory vault plus a separate, machine-generated one (a
`graphify` code-graph export, which can run into the hundreds of thousands of
notes). Local REST API is per-vault, live only while that vault is open in its
own Obsidian window, on its own port - so this plugin registers **one MCP
server per vault**, never one server juggling two, and models vaults as a
named map in config:

```json
{
  "vaults": {
    "memory":     { "path": "C:\\repos\\claude-memories", "port": 27123, "default": true },
    "codegraphs": { "path": "C:\\repos\\claude-memories-codegraphs", "port": 27125, "layout": "org/repo" }
  },
  "guard": { "asciiOnly": false, "requireFrontmatter": false, "checkCanvas": true }
}
```

Only the **default** vault gets the contract guard, session-capture hook, and
env-var/detection fallback - a second, machine-generated vault is
deliberately not held to a hand-authored vault's frontmatter contract (see
`obsidian-memory-contract`'s "Multiple vaults" section). `layout` is free-form
metadata a command like `/obsidian-vault:graph` reads to know a vault's
folder convention; it has no effect on resolution. A config file still in the
older single-vault shape (`"vaultPath"` at the top level) keeps working
unmodified.

**Past roughly 50,000 notes, prefer plain filesystem `Read`/`Grep` over
MCP** - Omnisearch and backlink resolution get slow at that scale, which is
routinely true of a code-graph vault. This is encoded in
`obsidian-memory-contract` and in `/obsidian-vault:graph`'s own guidance, not
just left to be discovered.

## What it registers

| Component | Count |
|---|---|
| Commands | 8: `init`, `doctor`, `optimize`, `canvas`, `map`, `graph`, `garden`, `reflect` |
| Agents | 2: `obsidian-vault:gardener`, `obsidian-vault:reflector` |
| Skills | 3: `obsidian-setup`, `obsidian-memory-contract`, `obsidian-scheduling` |
| Hooks | 8 entries (4 scripts x `.sh`/`.ps1`) across `SessionStart`, `PostToolUse`, `SessionEnd`, `PreCompact` |

**Read the Hooks section below before installing.** Commands and agents wait
to be asked; hooks do not.

## Hooks - the part that runs without being asked

| Script | Event | What it does |
|---|---|---|
| `bridge-status.sh`/`.ps1` | `SessionStart` | Probes **every** configured vault's Local REST API bridge and states plainly whether each `mcp__obsidian-<name>__*` will work this session - down, wrong port, or rejected key, each with the actual fix. Never blocks. |
| `vault-guard.sh`/`.ps1` | `PostToolUse` on `Edit`/`Write`/`MultiEdit` | Enforces the *default* vault's frontmatter contract, ASCII rule, and canvas well-formedness - **all three OFF by default.** `/obsidian-vault:init` turns one on only when it finds the matching rule stated in the target vault's own `CLAUDE.md`. Can block (exit 2) with the specific fix on stderr. Does not apply to a non-default vault. |
| `vault-capture.sh`/`.ps1` | `SessionEnd`, `PreCompact` | Appends one line (session id, cwd, transcript path) to the default vault's `inbox/pending-reflect.md`. Costs nothing, cannot break a session. |

Every script delegates to one Python module shared by both the bash and
PowerShell wrapper, so the two flavours cannot drift from each other - the
pattern crew's `platform-sync.sh`/`.ps1` established. Vault resolution
(`hooks/scripts/obsidian_common.py`) is documented in full in its own
docstring: env var and Obsidian's own registry apply only to the default
vault; a named non-default vault is only ever what config says it is.

**`vault-guard` is the one hook that can block**, and it ships a committed,
sabotage-tested regression suite: `hooks/scripts/_test/run-tests.sh` (12
cases, must-block and must-allow, plus a case proving the OFF-by-default
toggles actually gate the checks).

## Commands

| Command | Does |
|---|---|
| `/obsidian-vault:init [name] [path]` | Install/configure Obsidian, the REST bridge, and plugin config - for the default vault with no arguments, or add/update a named vault |
| `/obsidian-vault:doctor` | Diagnose every configured vault's REST bridge, a git-configured-but-not-a-git-repo default vault, `CLAUDE.md` drift against reality, gardener staleness, and empty structural folders - offers fixes, never applies one without confirmation |
| `/obsidian-vault:optimize` | Reports per-plugin cost on a large vault; every install/removal proposed one at a time, never batched |
| `/obsidian-vault:canvas <topic>` | Builds/refreshes a `.canvas` from a topic's wikilink neighborhood - canvases hold no facts |
| `/obsidian-vault:map <area>` | Builds/refreshes a Map-of-Content note |
| `/obsidian-vault:graph [repo] [vault-name]` | Builds a `graphify` code graph and exports it into a dedicated, separately-configured codegraphs vault laid out `<org>/<repo>/` - exact `graphify . --no-viz --code-only` / `graphify export obsidian` invocations, not `--obsidian`, which is silently ignored |
| `/obsidian-vault:garden` | Runs the gardener now instead of waiting for its schedule |
| `/obsidian-vault:reflect <topic>` | Asks the vault what it knows, and what contradicts |

## Agents

`obsidian-vault:gardener` distills queued sessions into concept/decision/daily
notes with provenance, never fabricating a citation. `obsidian-vault:reflector`
is read-only recall plus contradiction-finding. Neither is scheduled by this
plugin - see the `obsidian-scheduling` skill for wiring one to Task Scheduler,
cron, or a systemd user timer, with the unattended-permissions tradeoff stated
plainly rather than buried in a script comment.

## Skills

- `obsidian-setup` - the steps `/obsidian-vault:init` follows, in full,
  including per-OS install, per-vault Local REST API configuration and MCP
  registration, and the `enableInsecureServer`/HTTPS-port troubleshooting that
  a wrong guess here silently breaks.
- `obsidian-memory-contract` - the six-key frontmatter contract, evidence
  rules, tag discipline, the canvas-holds-no-facts rule, and the
  filesystem-over-MCP performance rule for a large vault. A vault's own
  `CLAUDE.md` always wins where it differs; this is the generic starting
  shape, and it explicitly does not apply one vault's contract to another.
- `obsidian-scheduling` - cross-platform scheduling reference. This plugin
  never installs a scheduled task itself.

## Companions

`/obsidian-vault:init` ends by offering three companion plugins, each its own
yes/no, never a batched install:

| Companion | What it adds | Install |
|---|---|---|
| [`obsidian@obsidian-skills`](https://github.com/kepano/obsidian-skills) | Kepano's workflow skills for working *inside* Obsidian - markdown conventions, Bases, JSON Canvas, templates. Complementary to this plugin's infrastructure (bridge, multi-vault MCP, memory contract, automation), not overlapping - it's the plugin whose name this one was renamed to avoid colliding with (install item 18 in this repo's own install script) | `claude plugin marketplace add kepano/obsidian-skills` (if not already added), then `claude plugin install obsidian@obsidian-skills` |
| `graphify` CLI | `/obsidian-vault:graph` depends on it directly | `uv tool install graphifyy` then `graphify install --project` (this repo's own install item 20) |
| `crew@useful-claude-add-ons` | Only mentioned when the vault holds ticket boards or code-graph output: crew 0.10+ has the Obsidian Kanban tracker, 0.11+ exports graphs into an org/repo-layout vault | `claude plugin install crew@useful-claude-add-ons` |

`/obsidian-vault:doctor` reports which of these are missing (once, not per
vault); it never installs one itself.

## Related - read before assuming this replaces something

This repo already has several other pieces of Obsidian tooling. This plugin
does not fully absorb any of them, and each was given a deliberate,
individually-stated decision rather than a blanket "not touched":

- **Naming.** Resolved by naming this plugin `obsidian-vault` rather than
  `obsidian` - a third-party plugin literally named `obsidian` (from the
  `obsidian-skills` marketplace) is already wired into
  `scripts/install-prerequisites.sh` item 18, and the two can now coexist
  with no ambiguity in prose, README rows, or menu labels.
- **`vault-automation/`** at the repo root (Windows-only PowerShell: capture
  hooks, a scheduled gardener, a `HOME.md` dashboard) is marked superseded for
  new setups in its own README, pointing here. Its scripts are left in place
  rather than deleted, because the root `README.md` still documents them as a
  runnable quickstart - retiring that path is a separate, deliberate change.
  The one thing it does that this plugin does not yet do is generate a
  `HOME.md` Dataview dashboard; `/obsidian-vault:init` offers the same starter
  plugin set it used to pre-enable (Dataview, Obsidian Git, Excalidraw,
  Omnisearch, Kanban), one at a time, confirmed.
- **`claude-obsidian-setup/`** at the repo root targets a different thing: it
  creates and verifies a vault for the third-party
  [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) plugin's
  own conventions, cross-platform (Windows/WSL + Linux) already. It was read
  only at the README level here, not gutted or absorbed - if you already use
  it, nothing about installing this plugin changes that setup.
- **`skills/obsidian-canvas`** and **`skills/obsidian-vault-server`** are
  already-registered marketplace skills covering JSON Canvas authoring and a
  self-hosted Ubuntu vault + SSH-tunneled REST bridge respectively.
  `/obsidian-vault:canvas` defers to `obsidian-canvas` where installed rather
  than reimplementing it; the vault-server skill was not otherwise
  cross-referenced.
- **`skills/claude-memories-vault`** and **`skills/claude-memories-canvas`**
  are vault-specific tuned versions of what `obsidian-memory-contract` teaches
  generically - that skill explicitly yields to them where installed.

## Uninstall

```bash
claude plugin uninstall obsidian-vault@useful-claude-add-ons
```

The hooks go with it. `~/.claude/obsidian/config.json` is not removed
automatically - delete it by hand if you want no trace.

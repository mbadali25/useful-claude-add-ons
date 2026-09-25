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

Only the **default** vault (the `primary`, once roles are set - see below) gets the contract guard, session-capture hook, and
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
| Commands | 10: `init`, `doctor`, `repair`, `install`, `optimize`, `canvas`, `map`, `graph`, `garden`, `reflect` |
| Agents | 2: `obsidian-vault:gardener`, `obsidian-vault:reflector` |
| Skills | 3: `obsidian-setup`, `obsidian-memory-contract`, `obsidian-scheduling` |
| Hooks | 8 entries (3 scripts x `.sh`/`.ps1`) across `SessionStart`, `PostToolUse`, `SessionEnd`, `PreCompact` |

**Read the Hooks section below before installing.** Commands and agents wait
to be asked; hooks do not.

## Hooks - the part that runs without being asked

| Script | Event | What it does |
|---|---|---|
| `bridge-status.sh`/`.ps1` | `SessionStart` | Probes **every** configured vault's Local REST API bridge and states plainly whether each `mcp__obsidian-<name>__*` will work this session. Both ports come from that vault's own `data.json` (`insecurePort` HTTP, `port` HTTPS), never derived from each other. It checks for a port collision across every vault **before** blaming any per-vault setting - `enableInsecureServer` is not the cause when the losing vault never started a server at all. Not-installed ("there is no bridge") and wrong-vault-answering (authenticates, serves someone else's files) are separate verdicts from down and rejected-key, each with its own fix. Never blocks. |
| `vault-guard.sh`/`.ps1` | `PostToolUse` on `Edit`/`Write`/`MultiEdit` | Enforces the *default* vault's frontmatter contract, ASCII rule, and canvas well-formedness - **the frontmatter and ASCII rules are OFF by default; the canvas shape check is ON** (`checkCanvas` defaults true - a `.canvas` that does not parse opens blank with no error, and checking costs nothing). `/obsidian-vault:init` turns one of the other two on only when it finds the matching rule stated in the target vault's own `CLAUDE.md`. Can block (exit 2) with the specific fix on stderr. Does not apply to a non-default vault. Four basenames - `CLAUDE.md`, `README.md`, `AGENTS.md`, `GEMINI.md` - are excused from *having* frontmatter, and from nothing else: if one of them does carry frontmatter it is still held to the required keys, the title/filename match and the updated date. The ASCII rule still applies to three of the four, because `CLAUDE.md` is separately ASCII-exempt by an older decision. The canvas rule never enters into it: all four are `.md`, and the canvas checks run only on a `.canvas` file. |
| `vault-capture.sh`/`.ps1` | `SessionEnd`, `PreCompact` | Appends one line (session id, cwd, transcript path) to the primary (default) vault's `inbox/pending-reflect.<host>.md` - one queue file per host, so two machines never append to one synced file. The legacy `inbox/pending-reflect.md` is no longer written but is still read, for de-duplication and by the gardener, so an old backlog drains. A payload with no usable session id AND no transcript path (an unparseable hook payload) is refused rather than queued, with the reason on stderr; a payload with a transcript but no session id is still queued, deduped on a hash of trigger+transcript so it is queued once, not once per invocation. This is the only capture owner. Costs nothing, cannot break a session. |

Every script delegates to one Python module shared by both the bash and
PowerShell wrapper, so the two flavours cannot drift from each other - the
pattern crew's `platform-sync.sh`/`.ps1` established. Vault resolution
(`hooks/scripts/obsidian_common.py`) is documented in full in its own
docstring: env var and Obsidian's own registry apply only to the default
vault; a named non-default vault is only ever what config says it is.

**`vault-guard` is the one hook that can block**, and it ships a committed,
sabotage-tested regression suite: `hooks/scripts/_test/run-tests.sh` (70
assertions, must-block and must-allow, including a case proving the config
toggles actually gate the checks, and three that hold the defaults above to a
config with no `guard` key at all).

## Commands

| Command | Does |
|---|---|
| `/obsidian-vault:init [name] [path]` | Install/configure Obsidian, the REST bridge, and plugin config - for the default vault with no arguments, or add/update a named vault |
| `/obsidian-vault:doctor [vault]` | Runs `vault_ops.py diagnose` and explains the verdicts: REST bridge state, port collisions across every vault, a git-configured-but-not-a-git-repo default vault, `CLAUDE.md` drift, gardener staleness, empty structural folders. **Read-only by design** - it has no `Write` or `Edit` and hands off to `repair` |
| `/obsidian-vault:repair [op] [vault]` | The acting counterpart: `fix-ports`, `reload`, `register`, for one vault or all. Shows the dry-run plan and requires a yes per operation before anything writes |
| `/obsidian-vault:install <vault>` | Installs and enables the Local REST API plugin in a vault that has none, assigns non-colliding ports, and registers its MCP server |
| `/obsidian-vault:optimize` | Reports per-plugin cost on a large vault; every install/removal proposed one at a time, never batched |
| `/obsidian-vault:canvas <topic>` | Builds/refreshes a `.canvas` from a topic's wikilink neighborhood - canvases hold no facts |
| `/obsidian-vault:map <area>` | Builds/refreshes a Map-of-Content note |
| `/obsidian-vault:graph [repo] [vault-name]` | Builds a `graphify` code graph and exports it into a dedicated, separately-configured codegraphs vault laid out `<org>/<repo>/` - exact `graphify . --no-viz --code-only` / `graphify export obsidian` invocations, not `--obsidian`, which is silently ignored |
| `/obsidian-vault:garden` | Runs the gardener now instead of waiting for its schedule |
| `/obsidian-vault:reflect <topic>` | Asks the vault what it knows, and what contradicts |

## Repairing the bridge

Every fix is performed by `hooks/scripts/vault_ops.py`, not typed out by hand.
It is dry-run by default and writes only with `--apply`; exit 0 means healthy or
applied, 1 means it found problems, 2 means a bad flag. The commands are thin
wrappers: `doctor` calls `diagnose` and never writes, `repair` calls
`fix-ports` / `reload` / `register`, `install` calls `install-plugin`, and
`init` calls `scan`, `install-plugin`, `fix-ports`, `register`, and `diagnose`
in that order - the only thing it still writes by hand is
`~/.claude/obsidian/config.json`, which no subcommand owns.

**The failure that looks like three failures.** Two vaults declaring the same
port is one cause with three symptoms: HTTP never listens, HTTPS answers with
the *other* vault's API key, and the bridge serves the *other* vault's files.
One plugin instance wins the bind; the loser fails to start its server at all,
which takes its HTTP listener down with it.

Find it by comparing `port` and `insecurePort` across **every** vault's
`.obsidian/plugins/obsidian-local-rest-api/data.json` - including vaults absent
from `~/.claude/obsidian/config.json`, because an unconfigured vault still binds
ports. `enableInsecureServer` is not the answer: on the machine that hit this,
that flag was already `true` everywhere.

Two things that mislead here:

- **`curl -k` proves less than it looks like.** It succeeds against the HTTPS
  port where Claude Code's Node MCP client rejects the same self-signed
  certificate. A green `curl -k` means the vault is serving; it does not mean
  MCP will connect.
- **An edit to `data.json` needs an Obsidian window reload.** The plugin reads
  that file only at load, so a stale instance disagrees with disk on both the
  port and the API key at once.

**There is no port arithmetic.** In `data.json`, `port` is the HTTPS port and
`insecurePort` is the HTTP one - not an offset. On this machine: memory is HTTPS
27124 / HTTP 27123, codegraphs 27128 / 27125, anew-codegraph 27126 / 27127. In
`~/.claude/obsidian/config.json` the key `port` means the *HTTP* port, the
opposite of the same word in `data.json`.

## Vault roles, import and gardening

Every vault `scan` finds gets one role, stored per vault in config as `"role"`:

| Role | Meaning |
|---|---|
| `primary` | Receives captures, gardening and imports. **Exactly one**; it is also `default`. |
| `recall` | Read by `recall` for injection into sessions. Never written. |
| `ignore` | Answered "no". Kept so a re-run does not ask again; never recalled, written, or included in `--all`. SessionStart's bridge report still lists it. |

`vault_ops.py adopt` lists them; `adopt --role NAME=ROLE ... --apply` writes
them, and refuses any result with zero or two primaries, or with any
discovered vault still unassigned, before writing a byte. A re-run with the
same roles changes nothing. A config with no roles at all still works exactly
as before: the default vault is the primary.

Writers - capture, import, `ack`, `garden-run`, `drain` - target the primary
and nothing else. If the primary is not on disk (an unmounted drive), they
refuse and say so; capture logs that on stderr and exits 0. No other vault,
recall or otherwise, is ever written in its place.

`vault_ops.py import --source <dir|vault>` copies Markdown notes into the
primary vault under `imported/<source name>/`, adding `imported_from` (absolute
source path) and `imported_at` (UTC date) to each note's frontmatter. Dry run
by default. It never overwrites: an existing destination is skipped and
reported as a collision, or written beside it as `<name> (imported).md` only
with `--suffix-collisions`. A re-run recognises its own earlier imports -
including suffixed ones with the same source and content - and writes nothing.
A destination reached through a symlinked folder, or resolving outside the
vault, is refused as `outside-vault`.

Gardening runs on **one designated host**, daily, through
`vault_ops.py garden-run`: at most 5 items or 10 minutes per run, each item
acknowledged (in `inbox/reflected.<host>.md`) only after its processor exited 0
and a before/after snapshot of the vault shows a file it created or changed -
wherever that file ended up, not the path the processor reported, since
Obsidian's auto-note-mover can move a note before the processor exits. A
failure keeps the processor's bounded stdout and stderr in the reason and the
log. An item whose session page (`session_id:` under `wiki/sessions/`) already
exists is acknowledged without being distilled again, and
`vault_ops.py reconcile` (dry run until `--apply`) does the same for the whole
queue. The processor runs `claude -p --settings '{"disableAllHooks":true}'`
with `CREW_HOOKS=off` and `OBSIDIAN_VAULT_GARDENER=1` in its environment, so no
hook - crew's, or this plugin's own capture - runs inside the vault. `drain`
works a backlog in the same bounded batches, dry run first.
`schedule --os cron|systemd|windows` prints the unit; nothing here installs
one. See the `obsidian-scheduling` skill.

**Finding and clearing pre-existing unusable `?` queue entries.** Before this
fix, a capture whose hook payload had neither a usable `session_id` nor a
`transcript_path` (both read as `?`) was queued anyway - one such line per
trigger per host, that the gardener can never distil since there is nothing
to read a session from and no transcript to fall back to. To find them in a
vault: `grep -n 'session=? .*transcript=?$' inbox/pending-reflect.*.md
inbox/pending-reflect.md` (a line matching this has *both* fields unusable;
a line with `session=?` but a real `transcript=` path is not one of these -
it is still gardenable from its transcript and this fix leaves it queued).
Each matched line is a checklist item (`- [ ] ...`); deleting the line removes
it from the queue, same as checking it off. This fix does not touch any
existing vault - it only stops new ones of this shape from being written -
so a live vault's current backlog needs this done by hand, once, per vault.

## Recall contract (for crew's context hook)

Stable read interface for any caller that injects vault context - crew's
context hook is the first. It is read-only: no network, no REST bridge, no
writes, no cache.

**Config.** `~/.claude/obsidian/config.json` (`%USERPROFILE%\.claude\obsidian\config.json`
on Windows; `HOME` is honoured first on every OS). `OBSIDIAN_VAULT_CONFIG=<path>`
overrides the whole path. The fields a caller may rely on:

```json
{ "vaults": { "<name>": { "path": "<abs path>", "role": "primary|recall|ignore", "default": true } } }
```

A vault whose `path` is not on disk is treated as absent. With no `role` on
any vault, the default vault is the only one read.

**CLI.**

```
python <plugin>/hooks/scripts/vault_ops.py recall --query "<text>" [--vaults A,B] [--max-chars N] [--timeout-ms MS] --json
```

- `--vaults` is priority order. Omitted: the primary, then every `recall`
  vault in config order. `ignore` vaults are never read.
- Ranking is vault priority first, then score, so when the budget runs out
  the lower-priority vault is the one that loses. Score is plain text matching
  per query term: title (frontmatter `title`, else filename) 6, each heading 3
  (max 3), each body line 1 (max 5).
- `--max-chars` (default 4000) bounds `sum(len(line) + 1)` over the results;
  the last result may be cut short to fit.
- `--timeout-ms` (default 1500) and 20,000 notes per vault bound the walk.
- Exit 0 on success (including zero results), 1 when any requested vault
  could not be read, 2 on a usage error. JSON is printed in every non-usage case.

**Output** (`--json`):

```json
{
  "query": "port collision",
  "terms": ["port", "collision"],
  "vaults": ["memory", "work"],
  "results": [
    { "vault": "memory", "path": "wiki/concepts/Port collisions break the bridge.md",
      "title": "Port collisions break the bridge", "score": 23,
      "snippet": "Two vaults on one port: the loser never binds.",
      "line": "[memory] wiki/concepts/Port collisions break the bridge.md: Two vaults on one port: the loser never binds." }
  ],
  "chars": 104, "max_chars": 4000, "truncated": false,
  "errors": [ { "vault": "nosuch", "error": "not a configured vault (or its path is not on disk)" } ]
}
```

`path` is vault-relative with forward slashes. `line` is the text to inject.
`truncated` is true when the budget, the timeout or the file cap cut anything.
A requested vault that is unknown or `ignore` is always named in `errors`,
never silently skipped.

## Agents

`obsidian-vault:gardener` distills queued sessions into concept/decision/daily
notes with provenance, never fabricating a citation, and acknowledges each item
through `vault_ops.py ack` only once its note exists. `obsidian-vault:reflector`
is read-only recall plus contradiction-finding. Neither is scheduled by this
plugin - `vault_ops.py schedule` prints a cron, systemd-timer or Task Scheduler
unit for `garden-run`, and the `obsidian-scheduling` skill covers the
unattended-permissions tradeoff.

## Skills

- `obsidian-setup` - the steps `/obsidian-vault:init` follows, in full,
  including per-OS install, per-vault Local REST API configuration and MCP
  registration, and the `vault_ops.py` subcommand table every command here
  wraps. Its Troubleshooting section carries the port-collision diagnosis
  below.
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
- **`vault-automation/`** (Windows-only PowerShell: capture hooks, a
  scheduled gardener, a `HOME.md` dashboard) has been retired now that this
  plugin covers the same ground cross-platform, with a committed test suite
  and no vault path baked in. `/obsidian-vault:init` offers the same starter
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
  are retired: their vault-specific conventions now ship as
  `obsidian-memory-contract`'s portable profiles
  (`profiles/memory-vault.md`, `profiles/canvas-maps.md`), adopted by naming
  the profile in a vault's own `CLAUDE.md` rather than installing a
  vault-specific skill.

## Uninstall

```bash
claude plugin uninstall obsidian-vault@useful-claude-add-ons
```

The hooks go with it. `~/.claude/obsidian/config.json` is not removed
automatically - delete it by hand if you want no trace.

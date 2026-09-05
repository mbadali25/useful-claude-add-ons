# Code map index

The only codemap file loaded by default. Everything else is read by path, on
demand, one subsystem at a time.

Subsystems derived from the graph's own community partition (`graphify-out/
graph.json`, `community` is a node-level key), grouped by area — 546 raw
communities over 5681 nodes is too fine to be a subsystem list on its own.

| Subsystem | Purpose | Anchor |
|---|---|---|
| [skills](skills.md) | 25 installable single-`SKILL.md` plugins. Largest area, least connected — a catalogue, not a system. | `875c9c6f` |
| [plugin/crew](plugin-crew.md) | The one full plugin: 24 commands, 17 agents, a Python hook layer, and the two guards that are its load-bearing part. | `875c9c6f` |
| [obsidian-vault](obsidian-vault.md) | Bridges Claude Code to Obsidian's Local REST API across multiple vaults. Discovery stays wide; acting stays scoped. | `875c9c6f` |
| [scripts](scripts.md) | The repo's own CI gates. Stop a stale plugin reaching other people's machines. | `875c9c6f` |
| [mcp-servers-core](mcp-servers-core.md) | Shared Azure/Graph auth and client for the four MCP server packages. The one area with real cross-file structure. | `875c9c6f` |
| [gizmoduck](gizmoduck.md) | Nuclei scanning, report generation, and SDP ticket records. | `875c9c6f` |

## Unmapped

`plugin/crew` was the entry here until that PR merged (#66, crew 0.16.7). It is
mapped now at `875c9c6f`, from a graph built on that same commit — 1937 nodes
over 142 files, up from the 1433 / 134 the note recorded at `fe538879`.

Smaller areas not yet mapped, in node order: `mcp-servers/` root (65),
`mcp-servers/graph` / `intune` / `o365-admin` / `o365-user` (54 each),
`claude-obsidian-setup/` (48), `vault-automation/` (22).

## Freshness

Every note carries `anchor: <repo>@<sha>`. Before relying on a claim, check
whether its anchor files moved:

```bash
git diff --name-only 875c9c6f..HEAD -- <paths>
```

All six notes are at `875c9c6f`. Every `path:line` in them is repo-relative,
which is what makes that command work — 10 anchors were written relative to
their subsystem root, resolved fine by eye, and could not be pasted into it.

Changed? Re-verify that section before using it. **Code always wins over
notes** — when a note and the code disagree, the note is wrong, full stop. Fix
the note; do not reason from it.

A stale note is confidently wrong in exactly the way a fresh search never is,
and it arrives with the authority of something written down deliberately.

## How these were built

Graph-derived sections (`Entry points`, `Owns data`, `Calls out to`) came from
`graphify-out/graph.json` directly. The judgment sections (`Does`,
`Landmines`, `Unverified`) came from one `crew:explorer` per subsystem, which
were told not to re-derive anything the AST parser already knew.

Every `path:line` citation in these notes has been opened and confirmed to
resolve, in range, at `875c9c6f` — 54 of 54. That check exists because an audit
agent earlier in the same session cited three line numbers that did not exist,
in files shorter than the lines it named.

The five `fe538879` notes were re-anchored to `875c9c6f` on 2026-09-05 after
re-verification, not on sight of an old sha: every path each note cites was
diffed from its own anchor to HEAD, every anchor re-opened, and for `skills.md`
and `scripts.md` — the two citing docs that genuinely moved — the falsifiable
structural claims (the `<!-- BEGIN -->` mirror blocks, the literal skill count,
the table shapes) were tested directly.

`plugin-crew.md` is the one exception to the split above: its `crew:explorer`
returned nothing usable on two attempts, so its judgment sections were written
from direct work on that subsystem during the 0.16.7 branch rather than from a
fresh read. Its own `## Unverified` says so.

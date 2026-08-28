---
description: Build or refresh a .canvas from a topic's wikilink neighborhood
argument-hint: <topic or note title>
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

Build a canvas for: $ARGUMENTS.

If the `obsidian-canvas` skill is installed (`skills/obsidian-canvas` in this
marketplace), invoke it for the JSON Canvas authoring mechanics - it already
covers groups, labeled arrows, and embedded live notes without needing the
REST bridge, and duplicating that here would be the second implementation of
the same JSON shape. This command's job is the neighborhood-discovery and
refresh logic around it.

**A canvas holds no facts.** Every fact lives in a note; the canvas is a
spatial arrangement of `file` nodes referencing notes, plus `edge`s and, where
genuinely needed, small `text` nodes that only label a grouping - never a text
node that states a claim no note also states. This is the vault's own rule
(commonly recorded as a decision like D-007); this command exists to enforce it
mechanically, not just by convention.

1. Find the topic note and its neighborhood: notes it links to, notes that link
   to it, one hop out. Use the vault's own search/backlink tooling rather than
   grepping raw text where the vault exposes it (e.g. `vault_get_document_map`
   or `search_query` over the MCP bridge, if it is up - fall back to `Grep` for
   `[[wikilink]]` patterns if not).
2. Lay out `file` nodes: the topic centered, first-hop links arranged around
   it, connected by `edge`s that follow the actual wikilink direction.
3. Write valid JSON Canvas: unique node ids, every edge's `fromNode`/`toNode`
   resolving to a real id, every `file` node's path resolving to a real note.
   The vault guard hook will catch a malformed canvas on write, but check this
   yourself first rather than relying on the hook to do your job.
4. Save to the vault's canvas location (commonly `wiki/canvases/` or
   `wiki/maps/` - check the vault's own `CLAUDE.md` for where it wants these).
5. If the canvas already exists, edit it surgically: preserve node positions
   for anything unchanged, add/remove only what the neighborhood actually
   gained or lost. Regenerating from scratch on every refresh destroys manual
   layout work.

Report the note count and edge count when done, and name anything you left out
because it looked like a fact rather than a link.

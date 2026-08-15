---
name: obsidian-canvas
description: >
  Create and edit Obsidian Canvas (.canvas) files directly as JSON (JSON Canvas spec) —
  visual maps, architecture diagrams, decision trees, kanban-style boards, and project
  overviews that render natively in Obsidian with embedded live notes, text cards,
  groups, and labeled arrows. Use this skill whenever the user asks for a canvas, a
  visual map or diagram "in Obsidian" or "in my vault", a whiteboard view of notes, an
  infrastructure/architecture map they can edit in Obsidian, or says things like "map
  this out visually", "make a board of these notes", or "draw how these connect" in an
  Obsidian context. Also use it when asked to read or modify an existing .canvas file.
---

# Obsidian Canvas authoring

A `.canvas` file is plain JSON (the open [JSON Canvas](https://jsoncanvas.org) spec). No plugin API or REST bridge is needed — author the file with normal file tools and Obsidian renders it natively (the core `canvas` plugin, enabled by default).

## Quick start

1. Resolve the vault path. Try the Obsidian CLI first, fall back to asking:
   ```
   "C:\Program Files\Obsidian\Obsidian.com" vault    # prints name, path, file count
   ```
2. Pick a home for canvases and keep it consistent — one folder per vault (e.g. `wiki/maps/` or `Canvas/`). Check for an existing folder of `.canvas` files before inventing a new one:
   ```
   Glob pattern="**/*.canvas" path="<vault>"
   ```
3. Write the JSON (schema below), then validate it parses: `python -c "import json; json.load(open('x.canvas'))"`.
4. Canvases do NOT participate in backlinks or graph view. After creating one, mention it from a related markdown note so grep/recall-style search can find it.
5. Tell the user to reload Obsidian (`Ctrl+R`) — open canvases hot-reload unreliably.

## File format

```json
{
  "nodes": [
    {"id": "n1", "type": "text", "x": 0, "y": 0, "width": 260, "height": 120, "text": "**Label**\nmarkdown works here", "color": "4"},
    {"id": "n2", "type": "file", "x": 400, "y": 0, "width": 400, "height": 400, "file": "notes/Some Note.md"},
    {"id": "n3", "type": "link", "x": 0, "y": 200, "width": 300, "height": 200, "url": "https://example.com"},
    {"id": "g1", "type": "group", "x": -40, "y": -40, "width": 900, "height": 520, "label": "Production"}
  ],
  "edges": [
    {"id": "e1", "fromNode": "n1", "toNode": "n2", "fromSide": "right", "toSide": "left", "label": "serves"}
  ]
}
```

Rules that bite:

| Rule | Detail |
|---|---|
| `id` | Any unique string per node/edge; short hex is fine |
| `x`/`y` | Node's TOP-LEFT corner; y grows downward; you do all layout math — nothing prevents overlap |
| `color` | `"1"` red, `"2"` orange, `"3"` yellow, `"4"` green, `"5"` cyan, `"6"` purple, or `"#rrggbb"` |
| `fromSide`/`toSide` | `top` / `right` / `bottom` / `left` |
| `type: "file"` | Vault-relative path, forward slashes; embeds render the live note (edits flow both ways) |
| `type: "group"` | Membership is purely geometric — the group rect must visually enclose its members |
| Markdown | Works inside `text` nodes, including `[[wikilinks]]` (render, but still don't create backlinks) |

## Layout heuristics

- Text cards: 240–300 wide, roughly 30 + 20 per line high. File embeds: 380–450 wide, 300–500 high.
- 60–100px gutters; a column per tier (clients | servers | storage) reads best for architecture maps.
- 8–15 nodes per canvas. Bigger topic → split into multiple canvases and cross-link.
- Prefer file nodes embedding real notes over long text cards: embedded notes stay searchable; text card content lives only inside the canvas JSON.

## Safety rails

- Read an existing `.canvas` before editing it — Obsidian may have rewritten node order/ids since you last touched it; never regenerate a canvas from scratch when asked to tweak it.
- Don't put facts *only* in text cards if the vault has a notes-based memory/recall workflow — canvases are a view over notes, not a store of record.

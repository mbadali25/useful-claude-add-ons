---
name: claude-memories-canvas
description: >
  Read, edit and create Obsidian Canvas (`.canvas`) files in the `claude-memories` vault at
  `C:\repos\claude-memories\wiki\maps` (Windows) / `/repos/claude-memories/wiki/maps` (Linux)
  — this vault's node/edge schema, its colour and id
  conventions, its column-and-group geometry, and the two rules that make a canvas findable
  (facts live in notes; every canvas is linked from its `Project - *.md`). Use this skill
  whenever a task involves a canvas, a visual map, an architecture or topology diagram, or a
  data-flow or process diagram in that vault, or the phrases "vault map", "wiki/maps",
  ".canvas", "JSON Canvas", or "show me the shape of". Also use it before drawing any new
  diagram into this vault, and when a note needs to point at its map. Do NOT use it for
  Excalidraw drawings, Mermaid, or Visio; for canvases in some other vault use
  `obsidian-canvas`, and for the vault's note and frontmatter conventions use
  `claude-memories-vault`.
---

# Obsidian Canvas in the claude-memories vault

Canvases live in **`C:\repos\claude-memories\wiki\maps\`** (Windows) / **`/repos/claude-memories/wiki/maps/`** (Linux) — 20 of them today.

`.canvas` files are plain JSON on the open **JSON Canvas** spec. There is no MCP
server and no special tool: Read, Write and Edit are sufficient and correct. Do not
go looking for a canvas API.

## Scope — read this first

This skill describes the canvas conventions of **one specific vault**. The generic
`obsidian-canvas` skill covers authoring JSON Canvas in any vault and is the right
choice everywhere else; this one adds the layout, colour and linking rules that keep
`claude-memories` consistent, plus the mistakes that have already cost time here.

## Three rules that are not style preferences

**1. Facts live in notes. Canvases only show shape.**
A fact that exists only on a canvas is invisible to text search. This has cost real
time here: the exec-insights JQL timezone trap sat on `exec-insights-data-flow.canvas`
for days, unfindable by `/recall`, until someone distilled it into a note. If you put
something load-bearing on a canvas, write it into a `wiki\concepts\` page too. The
canvas shows how the pieces relate; the note holds what is true.

**2. Canvases do not backlink.** Obsidian's graph and backlink panes ignore canvas
nodes, so a canvas nobody links to is orphaned. Every canvas must be mentioned from
its matching `wiki\concepts\Project - *.md`. The vault's convention is a small table:

```markdown
| Map | Answers |
|---|---|
| [[exec-insights.canvas]] | What the pieces are and how they connect |
| [[exec-insights-data-flow.canvas]] | How a sale becomes a number, and every place the meaning changes |
```

Link with the `.canvas` extension included. After creating a canvas, adding that row
is part of the same task, not a follow-up.

**3. Edit surgically. Never regenerate.**
Read the file, change the nodes you mean to change, write it back. A regenerated
canvas destroys hand-tuned coordinates and grouping — which is the entire value of a
canvas — and it silently drops nodes you did not know were there. Add a node by
appending to `nodes`; retire one by removing it and its edges.

## The actual schema in this vault

Top level is exactly two keys:

```json
{ "nodes": [ ... ], "edges": [ ... ] }
```

Files here are written with **1-space indent, one key per line**, in the key order the
examples below use (`id`, `type`, `x`, `y`, `width`, `height`, then the type-specific
keys). Match both, so a diff shows only what you changed. The JSON snippets in this
document are compacted onto fewer lines to stay readable — **the file on disk is not**;
copy the key order from them, not the line breaks.

### Nodes

Every node has `id`, `type`, `x`, `y`, `width`, `height`. Three types are in use:

| type | extra keys | count in vault | for |
|---|---|---|---|
| `text` | `text`, `color` (optional) | 320 | a labelled box of markdown |
| `file` | `file` | 71 | an embedded vault note |
| `group` | `label`, `color` (optional) | 78 | a titled frame around other nodes |

```json
{ "id": "srl_app", "type": "text", "x": 0, "y": -31, "width": 320, "height": 170,
  "color": "4",
  "text": "**SRL Liquidation**\nwww.srliquidation.com\nASP.NET Core MVC on **.NET 9**" }

{ "id": "lineage_file", "type": "file", "x": 0, "y": 992, "width": 320, "height": 380,
  "file": "wiki/concepts/SRL .NET Framework 4.8 and .NET 9 are diverged branch lineages - never merge either direction.md" }

{ "id": "g_app", "type": "group", "x": -44, "y": -91, "width": 408, "height": 1507,
  "label": "SRL application and lineages" }
```

- `file` paths are **vault-relative with forward slashes**, and include `.md`.
- `text` is markdown. `\n` for line breaks, `**bold**` for the node's headline,
  backticks for identifiers. Every node in this vault opens with a bold title line.
- A group contains a node **geometrically**, not by reference: the group's rectangle
  must enclose the members' rectangles. There is no child list. Move a node out of a
  group by moving its coordinates.

### Edges

```json
{ "id": "e1", "fromNode": "srl_app", "toNode": "processors",
  "fromSide": "bottom", "toSide": "top", "label": "sibling apps" }
```

`id`, `fromNode`, `toNode`, `fromSide`, `toSide` are always present; `label` on about
60% of them; `"toEnd": "arrow"` occasionally. Sides are `top`, `right`, `bottom`, `left`.
`fromNode`/`toNode` must match an existing node `id` — a dangling edge renders as
nothing and is invisible until someone opens the canvas.

### Colors

Colors are the **strings** `"1"`–`"6"`, not hex, and all six are in use. Keep a
canvas's existing colour meaning; do not introduce a seventh scheme.

### Ids

Either style works and both are present: readable slugs (`srl_app`, `g_build`, `e1`)
on hand-authored canvases, and 16-hex-char ids (`e4cb21d5f90d3c08`) on ones Obsidian
generated. When adding to an existing canvas, follow whichever style that file uses.
Ids only have to be unique within the file.

## Layout that stays readable

The vault's canvases follow a consistent geometry — copy it rather than inventing one:

- Text nodes **320 wide**, 120–210 tall. File nodes 250–380 tall, and **320 wide when
  they sit inside a standard group frame** — the 408-wide frame at `x = column - 44`
  only spans to `column + 364`, so a 380-wide file node pokes out of its own group and,
  since membership is geometric, silently stops being a member. Widen the frame to
  `width + 88` if you really need a wider file node.
- Group frames **408 wide**, offset to `x = column - 44`, `y = top - 60`, so the
  frame clears its contents. Height mirrors that clearance at the bottom:
  `height = (bottom of the lowest member) - (top of the highest member) + 120`.
- Columns at roughly **735–805 px** pitch and rows about **340 px** apart, both measured
  **top-left to top-left**, not as the gap between edges.
- One concern per column, framed by a group with a `label` that says what the column
  answers.
- On a brand-new canvas the colour scheme is yours to set, but set one and say what it
  means in the group labels or the note; on an existing canvas, inherit it. Same for ids:
  hand-authored canvases start with readable slugs, so prefer those on a new file.

## Workflow

1. **Read the canvas first.** List `wiki\maps\` and pick the one that already covers
   the subject. A second canvas on the same subject is worse than a crowded one.
2. **Parse before and after.** `python -c "import json;json.load(open(path,encoding='utf-8'))"` —
   a canvas that does not parse renders as an empty file in Obsidian with no error.
3. **Edit the nodes and edges you mean to change.** Keep everything else byte-identical.
4. **Verify referential integrity**: every `fromNode`/`toNode` resolves to a node id;
   every `file` node points at a file that exists.
5. **Write the facts into a note** in `wiki\concepts\` and cite it, per rule 1.
6. **Add or update the row in the matching `Project - *.md`**, per rule 2.
7. **Take the vault lock — if this host has one.** `-Status` only *reports* the holder
   — it does not take anything, so a run that stops there has no lock at all.
   **Resolve the interpreter and the vault root; never name either bare.** A bare
   `pwsh` is not on Git Bash's PATH on Windows, and its "command not found" is
   indistinguishable, from the exit code alone, from a lock that refused you:
   ```bash
   # Interpreter order is ported from .crew/verify.json:170 - under WSL the
   # reachable binary is the Windows one and is named pwsh.exe, so the .exe
   # suffix must be tried as well as omitted, at both known locations.
   PWSH=""
   for c in pwsh pwsh.exe \
            "/c/Program Files/PowerShell/7/pwsh" "/c/Program Files/PowerShell/7/pwsh.exe" \
            "/mnt/c/Program Files/PowerShell/7/pwsh.exe" "/mnt/c/Program Files/PowerShell/7/pwsh"; do
     if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then PWSH="$c"; break; fi
   done

   VAULT="/repos/claude-memories"                        # Linux / macOS
   [ -d "$VAULT" ] || VAULT="C:/repos/claude-memories"   # Windows
   LOCK="$VAULT/.claude/vault-lock.ps1"

   if [ -z "$PWSH" ] || [ ! -f "$LOCK" ]; then
     # THIRD OUTCOME, not a failure and not contention - see below.
     echo "NO VAULT LOCK: pwsh=${PWSH:-unresolved} lock=$LOCK" >&2
   else
     "$PWSH" -NoProfile -File "$LOCK" -Status
     "$PWSH" -NoProfile -File "$LOCK" -Acquire -Owner <who>
     "$PWSH" -NoProfile -File "$LOCK" -Release
   fi
   ```
   Non-zero from `-Acquire` means someone else holds it: stop, do not write anyway.
   Always `-Release`, including on the path where the write failed.

   **No lock on this host is a third outcome, not a refusal.** The lock is a
   host-local artifact: it lives in the vault's `.claude/`, which is outside the
   Obsidian Sync payload and absent from the vault's git history, so it reaches a
   machine only when that machine installs it. Measured 2026-09-22 on the Linux
   host: `/repos/claude-memories/.claude/` does not exist and there is no
   `vault-lock.ps1` anywhere in the vault. Both reflexes are wrong there —
   *stopping* leaves the vault unwritable over a hazard the lock never covered
   between hosts, and *writing as though you had taken it* reinstates the collision
   the lock exists to prevent.

   **The full branch, including what to do instead, is in the
   `claude-memories-vault` skill's "Writing into the vault" step 2.** Read it rather
   than improvising; it is the same vault and the same lock, and the two documents
   drifting apart is how one of them starts giving the unsafe answer. The short
   version, so an agent that loaded only this skill is not stranded: say out loud
   that this host has no vault lock, stage canvases by exact path (never `git add -A`),
   and bracket the write with `git status --porcelain` to catch another live writer.
   That is not a lock and must not be recorded as one — it bounds the blast radius
   and serializes nothing.

## When a canvas is the wrong answer

A canvas is for **shape**: topology, data flow, promotion pipelines, what-connects-to-what.
If the content is a sequence of claims, a decision, or a gotcha, the note is where it has
to live — do not reach for a canvas to record it. Reach for the `claude-memories-vault`
skill instead.

That is not a ban on ever naming the claim on a canvas. Rule 1 is the operative one: the
note is mandatory, the canvas node is optional and is a pointer, so a one-line label next
to a `file` node embedding the real note is fine. What is never acceptable is the claim
living **only** in canvas JSON, where `/recall` cannot see it.

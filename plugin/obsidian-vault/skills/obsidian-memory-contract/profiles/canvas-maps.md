# Profile: canvas-maps (JSON Canvas in a memory vault)

A portable conventions profile for `.canvas` files in a memory vault. It
carries what the `claude-memories-canvas` skill documents for one specific
vault, without that vault's paths or counts. For JSON Canvas authoring in
general, the `obsidian-canvas` skill covers the spec; this adds the rules that
keep a memory vault's maps findable and stable.

## Three rules that are not style

1. **Facts live in notes; canvases only show shape.** A fact stated only on a
   canvas is invisible to text search and to `vault_ops.py recall`, which reads
   `.md` files only. Anything load-bearing is written into a note too.
2. **Canvases do not backlink.** Obsidian's graph and backlinks ignore canvas
   nodes, so every canvas is linked from its project page - a small table of
   `| [[name.canvas]] | what it answers |`, extension included. Adding that row
   is part of creating the canvas.
3. **Edit surgically; never regenerate.** Read the file, change the nodes you
   mean to, write it back. Regenerating destroys hand-tuned coordinates and
   silently drops nodes you did not know were there.

## Schema

Top level is exactly `{ "nodes": [...], "edges": [...] }`. The guard's canvas
check (`checkCanvas`, on by default) rejects a file that does not parse or
does not have that shape.

- Every node: `id`, `type`, `x`, `y`, `width`, `height`. Types: `text`
  (`text`, optional `color`), `file` (`file`, vault-relative, forward slashes,
  `.md` included), `group` (`label`, optional `color`).
- A group contains nodes **geometrically** - its rectangle must enclose theirs.
  There is no child list; a node moved outside its group leaves it.
- Every edge: `id`, `fromNode`, `toNode`, `fromSide`, `toSide`; optional
  `label`, `toEnd`. `fromNode`/`toNode` must name existing node ids - a
  dangling edge renders as nothing.
- Colors are the strings `"1"`-`"6"`, not hex. Keep a canvas's existing
  color meaning; state a new canvas's scheme in its group labels.
- Ids are unique per file; follow the file's existing style (readable slugs or
  16-hex ids).
- Match the file's existing indentation and key order so a diff shows only
  what changed.

## Layout

Text nodes about 320 wide; group frames 88 wider than their widest member,
offset 44 left and 60 above the members; columns roughly 735-805 px apart and
rows about 340 px, measured top-left to top-left. One concern per column,
framed by a group whose label says what the column answers.

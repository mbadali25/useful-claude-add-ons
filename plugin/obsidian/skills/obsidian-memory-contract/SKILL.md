---
name: obsidian-memory-contract
description: The frontmatter contract, tag discipline, and canvas-vs-note rule for writing durable memory into an Obsidian vault. Use whenever a session is about to write, edit, or garden a note in a configured Obsidian vault.
---

# Obsidian memory contract

A generic starting contract for a vault used as Claude Code's durable memory.
If this marketplace already has a vault-specific skill installed (this repo
ships `claude-memories-vault` and `claude-memories-canvas` for one particular
vault), **that skill wins** - it is tuned to the actual vault's real
conventions, where this one is a starting shape for a vault that has none yet.
**A specific vault's own `CLAUDE.md` always wins where it differs from this
skill** - this teaches the shape; the vault states its own vocabulary and
thresholds. Read the vault's `CLAUDE.md` before writing a note. If it has none
yet, this skill is the template to write one from.

## Six-key frontmatter

Every memory note carries these. A note missing any of them is broken:

```yaml
---
type: concept          # concept | session | source | decision | daily | project-index | meta
title: "Exact title"   # matches the filename, quoted
created: 2026-08-20    # YYYY-MM-DD, never changes once set
updated: 2026-08-20    # bump on every edit
status: seed           # seed | developing | established
tags:
  - concept
---
```

Type-specific keys a vault's Dataview dashboards commonly read - do not drop
them once a vault's own contract names them:

- **concept** - `complexity`, `domain`, `aliases`, `related`, `sources`,
  `claim_ids`, `project`
- **session** - `session_id`, `store`, `observation_count`, `sources`
- **source** - `source_type`, `author`, `date_published`, `url`, `source_id`,
  `sha256`, `authority` (official|primary|secondary|community|synthetic|unknown),
  `independence_key`, `review_status`
- **decision** - `decision_id` (`D-NNN`), `decision_status`, `date_decided`,
  `deciders`, `supersedes`, `superseded_by`

## Evidence rules

- **Never invent a locator, quote, date, hash or confidence score.**
  `authority: unknown` is a correct value; a guessed one is not.
- `sources:` on a concept links the session or source pages it rests on. A
  concept with an empty `sources:` is claiming to be unsupported - only write
  that when it is true.
- If something was decided in conversation and recorded nowhere else, say
  exactly that rather than manufacturing a citation.
- A correction belongs in the note as a visible passage, not a silent
  overwrite - a note that quietly replaced what it used to say gives a future
  reader no way to know something changed.

## Tags

**Use the vocabulary that already exists in this vault before inventing a new
tag.** Check first:

```bash
grep -rh "^  - " --include="*.md" wiki/ | sort | uniq -c | sort -rn
```

A new, uncolored tag (if the vault assigns tag colors by family, commonly in an
`.obsidian/snippets/*.css` file) renders as an unfamiliar grey and is usually a
sign a tag from the existing vocabulary would have fit. If a genuinely new tag
is needed, add it to the vault's own tag-family scheme in the same change that
introduces it.

## Canvases hold no facts

A `.canvas` file is a spatial arrangement of `file` nodes (references to
notes) and `edge`s, plus text nodes that only label a grouping. **Anything
stated only inside a canvas and nowhere in a note does not exist as far as
recall is concerned** - `/obsidian:reflect` and the gardener both read notes,
not canvas contents. `/obsidian:canvas` enforces this mechanically; hold to it
by hand too.

## ASCII, if the vault requires it

Some vaults normalize to pure ASCII so search, diffing and cross-tool
compatibility stay simple. Check the vault's own `CLAUDE.md` - this is a
per-vault choice, not a default this plugin imposes (`guard.asciiOnly` in
`~/.claude/obsidian/config.json` ships `false`). Where a vault does require it,
common substitutions:

| Unicode | ASCII |
|---|---|
| `— –` (em/en dash) | ` - ` |
| `→ ← ↔` | `->` `<-` `<->` |
| `≤ ≥ ≠ ≈ ×` | `<=` `>=` `!=` `~=` `x` |
| `… ' ' " "` | `...` `'` `'` `"` `"` |
| `✅ ❌ ⚠` | `[x]` `[FAIL]` `[!]` |

A vault's own `CLAUDE.md` is normally exempt from its own ASCII rule, since it
has to be able to show the real characters it is teaching against.

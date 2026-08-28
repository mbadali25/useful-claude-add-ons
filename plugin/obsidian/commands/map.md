---
description: Build or refresh a Map-of-Content note for an area of the vault
argument-hint: <area, e.g. a project or subsystem name>
allowed-tools: Read, Write, Edit, Grep, Glob
---

Build or refresh the Map of Content for: $ARGUMENTS.

A map is a **note**, not a canvas - a curated, prose-and-links index into an
area of the vault, living in `wiki/maps/` (or wherever this vault's own
`CLAUDE.md` says maps live). Where `/obsidian:canvas` is spatial, a map is
structured and readable top to bottom.

1. Gather every note relevant to $ARGUMENTS: `Grep` the term across frontmatter
   `tags:`/`domain:`/`project:` and titles, not just body text - a map built
   from body-text grep alone misses notes that are relevant by classification
   but never mention the word.
2. Group by what the vault already uses to group (type: concept/decision/
   session/source, or a `domain:`/`project:` value) rather than inventing a new
   taxonomy for this one map.
3. Write the map as headed sections of `[[wikilinks]]`, each with a one-line
   gloss - not a bare link list. A map with no gloss is a worse search result
   than Obsidian's own search.
4. Carry the vault's frontmatter contract: `type: project-index` or the
   vault-specific type for a map note, all required keys, `tags:` from the
   vault's own vocabulary rather than a new tag invented for this map.
5. If the map already exists, diff against what it currently links and update
   in place - added notes get added sections, removed/renamed notes get their
   links fixed, everything else stays untouched so manual curation survives a
   refresh.

Report what changed: notes added, notes removed, whether this was a fresh map
or a refresh.

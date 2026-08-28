---
description: Report per-plugin cost on a large vault and propose community-plugin changes - every removal confirmed individually
allowed-tools: Read, Bash, PowerShell, Grep, Glob
---

Report on the configured vault's community-plugin set and propose changes.
This command **never removes or disables a plugin itself** - it writes a
report and, for each proposed change, asks one at a time. A batched "remove
these four, yes/no" is exactly the mistake this command exists to avoid: a
plugin can be load-bearing for hundreds of notes (a Dataview query, a Templater
template, a Breadcrumbs edge) and removing it under a single blanket yes is how
rendering silently breaks across the vault.

## 1. Size the vault

Note count and folder sizes (`du`-equivalent), so the recommendations below are
sized to this vault rather than generic advice. A 200-note vault and a
1,200-note vault do not want the same plugin set.

## 2. Cost each installed plugin

For each entry in `<vault>/.obsidian/community-plugins.json`:
- Index/cache size under `.obsidian/plugins/<name>/` where the plugin keeps one
  (Omnisearch and text-extractor are the usual large ones on a big vault).
- Whether it is a dependency of another enabled plugin (Templater templates
  that call `metadata-menu`, a Dataview query rendered by a Breadcrumbs view,
  etc.) - grep for the plugin's API surface across `wiki/templates/` and any
  `dataviewjs` blocks before ever proposing its removal.
- Whether Obsidian's own core plugins already cover the same job (core
  `bookmarks`/`backlink`/`graph` overlapping a community plugin that does the
  same thing worse is a real, if less common, finding).

## 3. Propose, don't batch

Structure the report as a table: plugin | cost | used by | proposal (keep /
remove / replace-with). Then walk removals one at a time with `AskUserQuestion`
or a plain question - never a single "apply all" confirmation for more than one
plugin. State what breaks if the removal is wrong (which notes/queries rely on
it) so the yes is informed.

## 4. Installs, same rule

A plugin recommended for a vault this size (e.g. suggesting `obsidian-git` be
either configured with real intervals or disabled once `/obsidian-vault:doctor` finds
it half-configured; suggesting a lighter search alternative if Omnisearch's
index is large relative to the vault) gets proposed with the same one-at-a-time
confirmation as a removal, because installing something also changes what a
vault depends on.

## Large-vault housekeeping to mention, not silently change

- **Session-note volume.** If `wiki/sessions/` (or the vault's equivalent) is
  the largest single folder by count, propose - do not perform - an archival
  policy: notes past N days with `status: established` and no recent backlinks
  move to a dated archive folder. State the tradeoff (Omnisearch stops indexing
  them unless configured otherwise) and let the user pick N.
- **Graphify output must stay outside the vault.** If any `codegraphs/`-style
  folder holds full generated graphs rather than stub notes pointing outward,
  flag it - that is the single largest inflation risk this session's own vault
  investigation found, and the fix (`/obsidian-vault:graph`) already does it right.
- **`.obsidian` index bloat.** Report total size of `.obsidian/plugins/*/`
  caches versus the vault's own content size as a ratio - useful context for
  whether Omnisearch or text-extractor need reindexing settings tightened.

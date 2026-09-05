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

## 1. Ask what kind of vault this is

Start here, not with a note count. The plugin set a vault should be running
depends on who reads it, and that is a question with an evidence-based answer:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" profile --vault <name>
```

It reports the detected kind (`bridge`, `graph` or `authored`), the evidence
behind the verdict, what the profile wants that the vault lacks, and - the half
this command acts on - **what the vault carries that the profile does not want**.
Exit 0 means the vault already matches its profile and there is nothing here to
propose; exit 1 means there is a gap in one direction or the other.

The distinction that does the work: an **authored** vault is read by a person,
so Dataview queries, Templater templates, Kanban boards and Breadcrumbs edges
all render something somebody looks at, and a full-text index is worth building
because a human types queries into it. A **generated** vault - a codegraph
export - is only ever grepped by Claude, so every index-building plugin there
spends disk, RAM and startup time producing an index nothing reads. That is why
the graph profile deliberately excludes omnisearch, dataview, backlinks and
text-extractor.

If detection is wrong, say so and use `--profile KIND` for one run or `--set
KIND --apply` to store it. Both keep printing what detection said, so an
override that has gone stale stays visible. Never set one to make the report
come out the way you expected.

Then size the vault: note count and folder sizes (`du`-equivalent), so the
recommendations below are sized to this vault rather than generic advice. Above
roughly 50,000 notes the authored profile drops omnisearch and text-extractor
by itself, and `profile` prints which side of that line the vault is on.

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
remove / replace-with). `profile`'s "carries" list is the candidate set for
removal; step 2's grep for who actually uses it is what turns a candidate into a
proposal. Then walk removals one at a time with `AskUserQuestion` or a plain
question - never a single "apply all" confirmation for more than one plugin.
State what breaks if the removal is wrong (which notes/queries rely on it) so the
yes is informed.

Nothing in this command disables a plugin itself. Obsidian's Community plugins
pane is where a removal happens, and it takes a relaunch to take effect - an
edit to `community-plugins.json` is read at launch, not at `app:reload`.

## 4. Installs, same rule

`profile`'s "lacks" list is the install side of the same decision, and it gets
the same treatment: one plugin, one confirmation.

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" install-plugin --vault <name> --plugin <id>
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" install-plugin --vault <name> --plugin <id> --apply
```

A bare `--apply` writes only the Local REST API floor and refuses to enable a
profile in bulk, for the reason at the top of this file: installing something
changes what a vault depends on just as removing something does. Anything else -
suggesting `obsidian-git` be either configured with real intervals or disabled
once `/obsidian-vault:doctor` finds it half-configured; suggesting a lighter
search alternative if Omnisearch's index is large relative to the vault - gets
proposed with the same one-at-a-time confirmation.

## 5. Splitting the vault is the last resort, and usually the wrong one

When a vault is big enough that someone suggests splitting it, say this first:
**the limit is the index-building plugins, not the note count.** Turning
Omnisearch and text-extractor off is reversible, buys more than a split does,
and breaks nothing permanently. A split breaks every wikilink that crossed the
cut, forever, and Obsidian gives no warning - the link just renders unresolved.

If a split is still warranted after the plugin set has been dealt with, the seam
is **provenance** (generated notes on one side, authored on the other), never
size. Get the damage figure before the conversation goes any further:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" profile --vault <name> --split-analysis
```

That reads every note, names the folders on each side of the seam, and counts
the wikilinks that would break. Report the recommendation, the seam and that
count together. **Never move a file without an explicit yes for that move** -
this command has no `--apply` that relocates anything, and it should not grow
one.

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

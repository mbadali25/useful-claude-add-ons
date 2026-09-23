# Profile: memory-vault (notes, frontmatter, wikilinks)

A portable conventions profile for a hand-curated memory vault. It carries the
conventions the `claude-memories-vault` skill documents for one specific vault,
with that vault's paths, counts and host-local tooling taken out, so any
primary vault can adopt them. The vault's own `CLAUDE.md` still wins wherever
it differs; write this profile into that file when the vault has none.

Applies to: the `primary` vault, and any `recall` vault that says it follows
this profile. Never to a generated vault (a code graph) - see the parent skill.

## Folder layout

```
inbox/pending-reflect.<host>.md  capture queue, one per host (written only by the capture hook)
inbox/reflected.<host>.md        gardener acknowledgements (written only by vault_ops.py ack)
wiki/index.md                    the human entry point
wiki/concepts/                   one distilled idea per file
wiki/sessions/                   provenance: "Session - <topic> <YYYY-MM-DD>.md"
wiki/daily/                      "YYYY-MM-DD.md"
wiki/sources/                    source records with provenance fields
wiki/decisions/                  "D-00N - <decision>.md"
wiki/maps/                       .canvas files - see canvas-maps.md
wiki/templates/                  one template per type
imported/<source>/               notes brought in by `vault_ops.py import`
```

## Frontmatter: six keys, always

`title` (quoted), `type`, `status`, `created`, `updated` (bare `YYYY-MM-DD`),
`tags` (block list). `sources:` is a list of real wikilinks; an empty one marks
the note unsupported, and recall should say so.

- `type` - one of `concept`, `source`, `entity`, `daily`, `project-index`,
  `meta`, `session`, `decision`, chosen by folder. Do not invent another: a
  dashboard that filters on type silently drops an unknown value.
- `status` - `seed`, `developing`, `established`. Promote deliberately; a
  vault states its own promotion threshold (commonly 3+ independent sessions).
- Imported notes additionally carry `imported_from` (absolute source path) and
  `imported_at` (UTC date). Keep both when editing the note later.
- Never invent a locator, quote, date, hash or confidence. `unknown` is honest.

## Filenames are the search index

Name a concept after the claim it makes, as a readable sentence -
`AWS OpenSearch balances shards by count not size.md`, not `Notes on shards.md`.
`vault_ops.py recall` scores the title highest, so a vague filename is close to
unfindable. Project index pages are `Project - <name>.md`, `type: project-index`.

## Wikilinks resolve by filename

1. `[[Some page]]` resolves against `Some page.md`, not a `title:` field.
2. A `:` cannot appear in a filename; substitute a hyphen and match the link
   to the file, not the prose.
3. **Match the filename's case exactly.** NTFS is case-insensitive and ext4 is
   not: a link that works on Windows can resolve to nothing on Linux, and it is
   not reported as broken on the host where it works.
4. Count references with exact boundaries: `[[X]]`, `[[X|` and `[[X#` are
   references to `X`; `[[X-something]]` is not. A count depends on the host it
   was taken on (point 3) - say which.

## Writing into the vault

1. Search before writing (`vault_ops.py recall --query ...`); extend an
   existing note rather than creating a near-duplicate.
2. One idea per page. Set `updated` when you touch one. Populate `sources:`.
3. Facts in notes, shape on canvases (canvas-maps.md).
4. Never hand-edit the queue or the ack ledger. Captures are appended by the
   capture hook; acknowledgements go through `vault_ops.py ack`, which refuses
   until the written note exists.
5. Commit by path, never by sweep: `git add -- <the files you wrote>`. Never
   `git add -A`, `git add .` or `git commit -a` - a sweep commits another
   writer's staged work. If the vault says another process owns commits,
   do not commit at all.
6. Never create a file named `nul` - Windows reserves it and git aborts on it.

Do not touch `.obsidian/` (per-machine plugin state) or a dashboard note that
a query plugin maintains.

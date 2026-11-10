# 6. The instruction surface is capped, and rationale lives outside the plugin

**Status:** accepted, 2026-10-19
**Decided by:** the owner (direction amendment and decisions OD1-OD3, 2026-10-08), on the L-0726 lane's recommendation

## Context

crew's command files, README and `.crew/verify.json` had grown by accretion: `promote.md` carried
394 lines of which most were rationale, `plugin/crew/README.md` was 5,212 lines, and every
`.crew/verify.json` rule carried a `why` averaging over a thousand characters. Every session that
loads a command pays for that text whether or not it needs the reasoning behind it. Slice 1 of
L-0726 cut `review.md` onto `review_run.py --prepare`; slice 2 (this decision) cuts the rest.

## Decision

1. **Command files are capped by bytes as well as lines.** `scripts/check_instructions.py` fails any
   command file over 120 lines or 12,288 bytes that is not listed in `plugin/crew/.budget-allowance.json`.
   Listed files may not grow, in lines or in bytes. `review.md` and `promote.md` lose their allowances.
2. **Rationale moves to `docs/crew/`.** `promote.md` keeps only the behaviour a test or a sabotage entry
   guards; the background goes to `docs/crew/promote.md`. Each `.crew/verify.json` rule gets a unique
   kebab-case `id` and a `why` of at most 300 characters; the full text is
   `docs/crew/verify-rationale.md`, one `## <id>` section per rule (checked, no orphan). `id` stays
   optional, and `why` uncapped, in other repos.
3. **The README is an entry point of at most 800 lines.** Sections that were reference material moved
   verbatim to `docs/crew/reference/`, and the README carries a "Moved sections" index (old title,
   new path). A `README.md section N` pointer anywhere in `plugin/crew/` must resolve to a README
   heading or an index entry.
4. **Repo-only.** `docs/crew/` is not shipped in the plugin, so a marketplace install no longer
   carries the rationale (an accepted breaking change, listed in the CHANGELOG).

## Rejected options

Trim the prose in place. It leaves the reasoning where every session loads it, and nothing stops it
growing back. A byte ceiling plus a moved-text index does.

## Consequences

Outside bookmarks to `README.md#...` anchors of moved sections break; in-repo pointers were repointed.
Tests that asserted moved prose now read the moved file.

## History moved from the README

No README sentence was deleted: history prose travelled verbatim with its section into
`docs/crew/reference/`, so nothing needed a home here. Deleting version-and-ticket narrative from the
moved files is a separate, optional pass.

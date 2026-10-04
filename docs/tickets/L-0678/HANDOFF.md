# Cloud handoff: L-0678

**crew_memory.py migrate and restore - convert existing native memories, previewed and opt-in, and undo it**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked until T-0084 and then L-0677 have merged: every write here goes through L-0677's `save` functions.

- **Role:** child ticket, split from T-0084, child 2 of 3 (slice 3 of the family's 4, counting the parent's own slice).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0678-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0678/direction.md`, `docs/tickets/L-0678/spec.md`
- **Size:** about 150 production lines in `plugin/crew/hooks/scripts/crew_memory.py` (migrate about 100, restore about 50).
- **Harness:** no. Feature PR; no harness path may be in it. Its sabotage entries are L-0679.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0084 | direction, spec ready, not built | Must merge first. The classifier and `resolve`. |
| L-0677 | direction, spec ready, not built | Must merge first. `save`'s plan and apply functions. |

The ticket facts name the second dependency as "T-0084 child 1"; that is L-0677. The facts and the spec agree.

This ticket blocks L-0679, for the mutations (n to p) that target `migrate` and `restore`.

Family order:
1. T-0084 (parent: pointer format, `resolve`, `check`; feature PR)
2. L-0677 (`save`; feature PR), after T-0084 has merged
3. L-0678 (`migrate` and `restore`; feature PR), after L-0677 has merged
4. L-0679 (sabotage entries; tooling-only PR), after L-0678 has merged. Its direction allows the entries for T-0084 and L-0677 to land first in one tooling PR, and L-0678's in a second, if L-0678 is delayed.

Related, no order forced: T-0083 (direction), T-0048 (spec), T-0046 (in-progress), as in the parent spec.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. `crew_memory.py` line numbers are read at plan time, after L-0677 merges.
- A stale plan.md is not published. The implementing session writes the plan.
- No new write path: every write goes through L-0677's `save` functions, or `restore`'s single native-file replace. A failure on one file never stops or undoes the others.
- Nothing runs automatically: no hook, no SessionStart call, no call from `/crew:init`, `/crew:migrate` or `/crew:upgrade`. `/crew:migrate` is a different feature (the 0.20-to-1.0 config move) and is not touched; this subcommand is documented under `crew-memory`.
- `restore` never edits or deletes the vault note. `MEMORY.md` is never edited.
- No state file and no migration log: the preview is recomputed from disk each run, which is what makes a re-run a no-op.
- Titles that are not portable file names are refused; the exact rule is settled at plan time with a table of names.
- The spec's Evidence cites the parent direction by its `.work/` path. In this publication that file is `docs/tickets/T-0084/direction.md` on branch `T-0084-build`.

## Open questions for the owner (recommended option taken)

1. One tag set for a whole batch (taken, with `--only` for several batches), or a per-file tag mapping? A mapping would be a follow-up.
2. `migrate` plus `restore` (taken), or migration only with no way back?

The parent's questions on the note folder, note type and update passage (see T-0084's HANDOFF.md) apply here through `save`.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0678/` in the final PR unless the owner wants it kept.

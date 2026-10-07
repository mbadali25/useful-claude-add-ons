# Cloud handoff: L-0665

**promote-gate reads the newest PROMOTIONS.md row for an environment and sha, not the first**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0062, slice 2 of 2. Independent of the parent: it needs nothing from T-0062 or T-0009.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0665-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0665/direction.md`, `docs/tickets/L-0665/spec.md`
- **Size:** about 15 changed production lines across `promote-gate.sh` and `promote-gate.ps1`. No new parser or guard. No harness path (`verify-gate.*` is harness and is not touched).

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0505 | merged (PR #296) | The effective-tree promote-gate whose `passed()` this changes. |

Nothing unmerged must land first. This ticket can be worked now. The facts file and the spec agree.

**This ticket blocks:** nothing. The spec notes that T-0045 hit this bug in planning; L-0647 (split from T-0045, draft PR #439) writes `not-run` rows and states that the first-row behaviour is this family's to change.

**Order of the family:**

1. L-0665 (first-row fix): independent. Needs nothing unmerged; it can land now.
2. T-0062 (shared reader and the Bash flavour): after T-0009 (PR #336) merges.
3. L-0664 (PowerShell twin): after T-0062.

All three edit `promote-gate.sh` or `promote-gate.ps1`, as do L-0564 (direction) and L-0648 (split from T-0045, draft PR #445, lands after T-0062). Whichever lands second merges main and re-checks its anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- There is no plan.md for this ticket. The implementing session writes the plan.
- Both flavours change together: the LAST matching row decides in `promote-gate.sh` and in `promote-gate.ps1`.
- This changes a guard's precondition. A later failure must revoke an earlier pass; that is the unsafe direction today. Mutations (each flavour put back to first-match) go in `promote_tree_mutations.py`; do not edit `plugin/crew/tests/sabotage*.py`.
- Do not touch `verify-gate.sh` or `verify-gate.ps1` (harness), the row format, or the 7-character sha prefix match.
- File order is the order. The `when` column is not used.
- The `ps1` cases skip without PowerShell 7 and must never fail for that reason; report them as NOT RUN where they skipped.
- The spec cites `.work/followups.md:40`. That file is local and gitignored; it is not published.
- `promote.md` is at its 380-line allowance; Touch allows `.budget-allowance.json` only if the one sentence does not fit.
- Touch includes `docs/guides/crew/**` rebuilt outputs (HTML, DOCX, PDF). Whether the cloud environment can rebuild DOCX and PDF: could not tell.

## Open questions for the owner (recommended option taken)

1. The newest row decides (taken), or any all-pass row admits?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0665/` in the final PR unless the owner wants it kept.

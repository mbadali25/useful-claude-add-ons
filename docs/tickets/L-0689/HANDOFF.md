# Cloud handoff: L-0689

**promote-gate matches a fragment of a declared deploy command and leaves a false in-flight marker**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0689-build`, new from origin/main `baf193aa`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0689/direction.md`, `docs/tickets/L-0689/spec.md`
- **Size:** about 25 production lines in `plugin/crew/hooks/scripts/promote-gate.sh` and `promote-gate.ps1`, plus about 150 lines of tests.
- **Harness:** no harness path. `promote-gate.*` and `test_promote*.py` are not in `HARNESS` (`scripts/check-tooling-pr.py`), so this is a feature PR. `verify-gate.*` and `plugin/crew/tests/sabotage*.py` ARE harness and must not be edited here.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0505 | merged (PR #296) | The effective-tree promote-gate whose match lines this ticket edits. |

Nothing open blocks this ticket and it blocks nothing. It can be worked now.

Same files, no required order (whichever lands second merges main and re-checks its anchors):

| Ticket | State | Overlap |
|---|---|---|
| T-0062 | draft PR #467, blocked on T-0009 | Adds a helper call next to the same match lines in `promote-gate.sh`. Its "containment stays unchanged" then means the match as this ticket left it. |
| L-0664 | draft PR #471, after T-0062 | The same in `promote-gate.ps1`. |
| L-0665 | draft PR #473 | `passed()` in both flavours; different lines. |
| L-0648 | draft PR #445 | Reads the `github` entry after a match; different lines. |
| T-0009 | PR #336, open | Does not touch `promote-gate.*`; changes `.crew/verify.json`. |

Recommended order: this ticket first (it needs nothing unmerged), then the others in their own order.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `baf193aa` and nothing was run. Re-check each anchor if main has moved.
- **The trigger is an inference.** The reporter did not reproduce it by piping a payload into the hook. The first acceptance check is that reproduction on the unfixed script. If it does not reproduce, stop and report; do not ship the change on the inference alone.
- Both flavours have the bug and must change together: `promote-gate.sh:140`, `:213` and `promote-gate.ps1:90`, `:134`.
- This is a fix to a guard. Dropping the reverse test means a shortened form of a declared command is no longer matched (spec U2). That is a breaking change: say so in CHANGELOG and the docs.
- The `-like` wildcard reading at `promote-gate.ps1:134` was not measured (spec U3). The acceptance check pins it.
- No sabotage mutation is added to `sabotage*.py` here. New mutations go in `plugin/crew/tests/promote_tree_mutations.py`; wiring them into `sabotage.py` is a separate tooling-only PR.
- A stale plan.md is not published; the implementing session writes the plan.

## Open questions for the owner (recommended option taken)

1. The reverse test is dropped outright. Alternative: a token rule that still matches a shortened command.
2. The `-like` to literal change in `promote-gate.ps1` rides in this ticket. Alternative: its own ticket.
3. A marker left by the old rule is documented only. Alternative: the gate clears it, which touches `verify-gate.*` (harness) and would be a separate tooling-only PR.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0689/` in the final PR unless the owner wants it kept.

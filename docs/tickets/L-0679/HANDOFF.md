# Cloud handoff: L-0679

**sabotage entries for crew_memory.py (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked until T-0084, L-0677 and L-0678 have merged: the anchor strings do not exist until those three feature slices are on main.

- **Role:** child ticket, split from T-0084, child 3 of 3 (slice 4 of the family's 4, counting the parent's own slice).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0679-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0679/direction.md`, `docs/tickets/L-0679/spec.md`
- **Size:** no production lines. About 90 lines in `plugin/crew/tests/sabotage_context.py` and about 30 in the anchor test.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a harness path, so this lands alone as a tooling-only PR. No production file, prompt or skill may ride with it.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0084 | direction, spec ready, not built | Must merge first. Mutations a to g target its code. |
| L-0677 | direction, spec ready, not built | Must merge first. Mutations h to m. |
| L-0678 | direction, spec ready, not built | Must merge first. Mutations n to p. |
| T-0087 | merged | The tooling-PRs-land-alone rule and `check-tooling-pr.py`. |

The ticket facts name these as "T-0084 child 1" (L-0677) and "T-0084 child 2" (L-0678). The facts and the spec agree.

This ticket blocks nothing.

Family order:
1. T-0084 (parent: pointer format, `resolve`, `check`; feature PR)
2. L-0677 (`save`; feature PR), after T-0084 has merged
3. L-0678 (`migrate` and `restore`; feature PR), after L-0677 has merged
4. L-0679 (sabotage entries; tooling-only PR), after L-0678 has merged. Its direction allows the entries for T-0084 and L-0677 to land first in one tooling PR, and L-0678's in a second, if L-0678 is delayed.

Related, re-check before planning:
- L-0608 (in-progress): makes platform-skipped mutations fail closed. Mutation m follows whatever shape it lands.
- T-0080 (direction): the sabotage harness memory bound. This ticket changes nothing of it.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. The mutation anchors are taken from `crew_memory.py` as merged, at plan time.
- A stale plan.md is not published. The implementing session writes the plan.
- Do not edit `plugin/crew/tests/sabotage.py` (3400 of 3400 lines at the spec's base). The entries go in the existing `sabotage_context.py`, folded into `CONTEXT_MUTATIONS`.
- No change to `crew_memory.py`. Where a mutation survives, the fix is a stronger test (a test file may ride along); a production fix goes back to a feature PR.
- No replacement may be size-preserving with a same-second restore: a stale `.pyc` then hides the mutation. If a mutation reads green, check the `.pyc` timestamp first.
- Mutation m (`newline="\n"` dropped) is red on Windows only. On POSIX it is reported as platform-skipped, by name, never as passed.
- The full sabotage run is heavy on a memory-bound host. Say in the PR body which entries were run where.
- A crew version bump and CHANGELOG entry are in Touch: a tests-only change under `plugin/crew/` still counts as plugin content for the version-drift check.

## Open questions for the owner (recommended option taken)

1. The mutations go in the existing `sabotage_context.py` (taken). A separate `sabotage_memory.py` needs lines freed in `sabotage.py` first. This is the parent's question 8.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0679/` in the final PR unless the owner wants it kept.

# Cloud handoff: L-0676

**T-0083 child 2: sabotage mutations prove the recall project tests (tooling-only)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked until L-0675 has merged (and so until T-0083 has merged): each mutation is anchored on a line L-0675 writes.

- **Role:** child ticket, split from T-0083, slice 2 of 2 children (slice 3 of the family's 3, counting the parent's own slice).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0676-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0676/direction.md`, `docs/tickets/L-0676/spec.md`
- **Size:** no production lines. About 60 lines in `plugin/crew/tests/sabotage_context.py` and about 15 in the test file.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a harness path, so this lands alone as a tooling-only PR. No production code may ride with it.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0675 | direction, spec ready, not built | Must merge first. It writes the code and the tests these mutations name. |
| T-0083 | direction, spec ready, not built | L-0675 depends on it. |
| T-0087 | merged | The rule that makes this a separate PR. |

The ticket facts name the first dependency as "T-0083 child 1"; that is L-0675. The facts and the spec agree.

This ticket blocks nothing.

Family order:
1. T-0083 (parent, feature PR, obsidian-vault only)
2. L-0675 (feature PR, crew), after T-0083 has merged
3. L-0676 (this ticket), after L-0675 has merged

## Read before writing code

- This ticket cannot be planned in detail until L-0675 has merged. Read `crew_recall.py` on origin/main then and copy each anchor line byte for byte.
- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md is not published. The implementing session writes the plan.
- The spec was not approved by the owner in person; the recommended option was taken.
- No production code. If a mutation needs a different anchor, the mutation changes, not the code. A behaviour gap found here is a finding for a new ticket.
- Do not edit `plugin/crew/tests/sabotage.py` (at the pylint module line limit). The mutations go in `sabotage_context.py`.
- If a mutation reads green, check the `.pyc` timestamp before changing the mutation: a same-size, same-second edit can leave a stale `.pyc` that hides it.
- The PR body carries `Docs: none - tests-only harness change, no behaviour or setting changes`.

## Open questions for the owner (recommended option taken)

1. Bump crew for a tests-only harness change (taken: yes, patch), or land with no bump?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0676/` in the final PR unless the owner wants it kept.

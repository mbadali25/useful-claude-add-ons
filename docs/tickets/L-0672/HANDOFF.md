# Cloud handoff: L-0672

**Sabotage mutations for crew_tracker's per-component identity check (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked: not workable until T-0081 has merged. The lines these mutations anchor on do not exist before then.

- **Role:** child, split from T-0081, slice 1 of 1 (the second of T-0081's two slices).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0672-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0672/direction.md`, `docs/tickets/L-0672/spec.md`
- **Size:** 0 production lines. About 40 lines in `plugin/crew/tests/sabotage_tracker.py` (5 mutations).
- **Harness:** yes. `plugin/crew/tests/sabotage_tracker.py` is a harness path, so this lands alone as a tooling-only PR. `scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0081 | spec, draft PR in this batch, not merged | Adds the lines these mutations anchor on and the tests they aim at. Hard dependency. |
| T-0087 | merged | The tooling-PR rule and `scripts/check-tooling-pr.py`. |
| T-0077 | merged | The existing tracker mutations this follows. |
| T-0021 | merged | The same. |

This ticket blocks nothing.

Family order: T-0081 (feature PR) -> L-0672 (this tooling PR).

Related, no order forced: T-0080 (sabotage harness memory bounds, a different sabotage file). L-0669 and PR #394's announced follow-up (T-0037 PR B) also add mutations to `sabotage_tracker.py`; that is not in this spec, and whichever lands second merges main and re-counts.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. Re-read `crew_tracker.py` on main after T-0081 merges, before planning.
- No plan.md exists for this ticket. The implementing session writes the plan.
- The mutation list follows T-0081 as merged. If both walks share one helper, removing the helper's comparison turns both platforms' tests red: that is one mutation with one named test, plus one per call site.
- No production code. If an anchor is not unique, that is fixed in a separate feature PR, not here.
- `plugin/crew/tests/sabotage.py` is not edited: it was at its 3400-line limit at `155fe6d8`.
- Both code maps state the mutation count. Read it from `len(TRACKER_MUTATIONS)` on the land branch; do not add 5 to 87 by hand, because other tickets change the same count.
- `plugin/crew/tests/` ships inside the plugin, so crew still gets a version bump.

## Open questions for the owner (recommended option taken)

None of its own. It rests on T-0081's question 2 (the guard lands first, the mutations follow). Taken: accepted.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0672/` in the final PR unless the owner wants it kept.

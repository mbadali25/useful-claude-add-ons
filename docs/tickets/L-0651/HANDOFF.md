# Cloud handoff: L-0651

**sabotage mutations for the sleep schedule overlay (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable until T-0053 has merged: the mutations edit code that T-0053 adds.

- **Role:** child, split from T-0053, slice 1 of 6.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0651-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0651/direction.md`, `docs/tickets/L-0651/spec.md`
- **Size:** 0 production lines. About 130 lines in `plugin/crew/tests/sabotage_autopilot.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a review/gate harness path, so this lands alone as a tooling-only PR. Tests, docs, version files, the code map and the graph may ride along; production code may not.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0053 | ready, not merged | Slice 1: the parser, resolver and overlay these mutations edit. Must be merged first. |
| T-0087 | merged | The tooling-PRs-land-alone rule. |

This ticket blocks: the spec says "nothing". L-0655's spec and direction, however, list L-0651 as required first (so that `SLEEP_MUTATIONS` exists); treat L-0655 as blocked by this ticket.

Family order (parent T-0053, six slices):

1. T-0053: the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and the anchors inside `crew_sleep.py` and `crew_autopilot.py` do not exist until T-0053 lands. Read them from the merged code at plan time.
- No plan.md is published. The implementing session writes the plan.
- No edit to `plugin/crew/tests/sabotage.py`: it is at the 3400-line pylint limit. `SLEEP_MUTATIONS` is appended to `AUTOPILOT_MUTATIONS`, which is already registered.
- No production change. If a mutation survives, the missing test is added here in `test_crew_autopilot_sleep.py` and the gap is named in the PR body.
- A harness change runs the harness rule's suites (the tooling checker, its suite, the golden replay, the seam contracts, the canary review).
- `.crew/verify.json`'s autopilot rule text states where to count the mutations, not a number.
- PR body: `Docs: none - tests and harness only` unless a code map line changed.

## Open questions for the owner (recommended option taken)

None of its own in the spec. Two unknowns are resolved at plan time: the exact anchors, and whether `SLEEP_MUTATIONS` targets a new file constant for `crew_sleep.py` (expected yes). The parent's open questions are in T-0053's handoff.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0651/` in the final PR unless the owner wants it kept.

# Cloud handoff: L-0655

**sabotage mutations for manual sleep, the sleep log and the deploy override (tooling-only PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable until L-0651, L-0652, L-0653 and L-0654 have merged (or been cut, and named as cut).

- **Role:** child, split from T-0053, slice 5 of 6.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0655-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0655/direction.md`, `docs/tickets/L-0655/spec.md`
- **Size:** 0 production lines. About 190 lines in `plugin/crew/tests/sabotage_autopilot.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a review/gate harness path, so this lands alone as a tooling-only PR. Tests, docs, version files, the code map and the graph may ride along; production code may not.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0053 | ready, not merged | Slice 1. Must be merged first. |
| L-0651 | direction, not merged | Adds `SLEEP_MUTATIONS`, which this extends. Must be merged first. |
| L-0652 | direction, not merged | Manual `sleep` / `wake`: mutations (a) to (i) edit its code. |
| L-0653 | direction, not merged | Sleep log: mutations (j) to (o) edit its code. |
| L-0654 | direction, not merged | Deploy override: mutations (p) to (s) edit its code. |
| T-0087 | merged | The tooling-PRs-land-alone rule. |

This ticket blocks nothing.

Family order (parent T-0053, six slices):

1. T-0053: the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`). Every anchor is read from the merged code of L-0651 to L-0654 at plan time.
- No plan.md is published. The implementing session writes the plan.
- If one of L-0652 to L-0654 was cut or delayed, land this for the ones that merged, cut the mutation list to match, and name what is left out in the PR body.
- No production change. No edit to `plugin/crew/tests/sabotage.py`.
- No mutation for L-0656's keys: it files its own tooling follow-up when it is unblocked.
- A harness change runs the harness rule's suites (the tooling checker, its suite, the golden replay, the seam contracts, the canary review).
- PR body: `Docs: none - tests and harness only` unless a code map line changed.

## Open questions for the owner (recommended option taken)

None of its own in the spec. The direction took one tooling-only PR for the three slices over one PR per slice. The parent's open questions are in T-0053's handoff.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0655/` in the final PR unless the owner wants it kept.

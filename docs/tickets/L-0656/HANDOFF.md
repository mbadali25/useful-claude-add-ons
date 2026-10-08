# Cloud handoff: L-0656

**sleep overrides for keys that do not exist yet (review policy, held pings)**

**BLOCKED. Do not implement yet.** The keys this overrides are not on main. The review half unblocks when `autopilot.reviewPolicy` is merged (T-0029 or T-0067); the notify half unblocks when T-0051 is merged. T-0053 and L-0653 must also have merged.

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0053, slice 6 of 6.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session once unblocked)
- **Branch:** `L-0656-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0656/direction.md`, `docs/tickets/L-0656/spec.md`
- **Size:** about 90 production lines when both halves are built (overlay keys about 25, notifier hold about 40 across both shell flavours, summary send about 25).
- **Harness:** could not tell yet. As specified it touches no harness path. If the reader of the review policy turns out to live in a harness file (`review_*.py`, `commands/review.md`), the review half becomes its own tooling-only PR. Its sabotage mutations land in a separate tooling-only PR afterwards in any case.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0053 | ready, not merged | Slice 1: the overlay these keys join. Must be merged first. |
| L-0653 | direction, not merged | The morning summary text that the notify half sends. Must be merged first. |
| T-0029 or T-0067 | in-progress / ready, not merged | Defines `autopilot.reviewPolicy`. Blocks the review half. |
| T-0051 | approved, not merged | Rebuilt notify. Blocks the notify half. |

Where the files disagree: the facts collected for this hand-off and direction.md list T-0011 (ship policy; approved, not merged) as a dependency. The spec lists it under "coordinates with", and excludes merging, opening a PR or landing a ticket from this ticket. The spec wins: T-0011 is not required first.

Coordinates with, no order forced: T-0011 (ship policy), T-0045 (direction; deploy results that ping), T-0073 (direction; `reviewAcceptance`), T-0070 (spec; inert settings are loud).

This ticket blocks: T-0054's "sleep mode" guide section being complete.

Family order (parent T-0053, six slices):

1. T-0053: the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's evidence was checked at origin/main `155fe6d8` and shows only what is absent. Main has moved since (the branch base is `ce235468`). When a dependency merges, re-read the merged code and rewrite Evidence and the key names before planning.
- No plan.md is published. The implementing session writes the plan.
- If only one half is unblocked, build that half and leave the other in this ticket. It may be planned as two tickets.
- The design section is "to confirm against the merged dependencies": the final name, values and reader of the review policy, and the notifier's entry point and event names, are unknown until T-0029 / T-0067 and T-0051 merge.
- No new review acceptance path and no edit to `review_ledger.py` or any `review_*.py`.
- The notifier on `155fe6d8` is a shell script pair (`notify.sh`, `notify.ps1`). A hold must be added to both flavours and read the sleep state through `crew_autopilot.py settings --json`, not re-derive it.
- Failure pings (a failed deploy, a failed gate) are never held.

## Open questions for the owner (recommended option taken)

1. Should sleep be stricter than day about review findings (the 2026-09-26 guardrail "never accept a review with any finding asleep")? Taken: leave L-0510's auto-accept alone; it is the later owner decision and applies at every hour.
2. Is a held ping dropped or queued? Taken: dropped and counted; the summary carries what the owner needs. It becomes an owner question if T-0051's design keeps a queue.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0656/` in the final PR unless the owner wants it kept.

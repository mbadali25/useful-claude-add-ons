# Cloud handoff: L-0653

**sleep log and morning summary (`.work/autopilot/sleep-log.md`, `sleep-note`, `sleep-summary`)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable until T-0053 and L-0652 have merged.

- **Role:** child, split from T-0053, slice 3 of 6.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0653-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0653/direction.md`, `docs/tickets/L-0653/spec.md`
- **Size:** about 140 production lines (`crew_sleep.py` about 85, `crew_autopilot.py` about 55). No harness path; `python3 scripts/check-tooling-pr.py` must exit 0.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0053 | ready, not merged | Slice 1: the sleep state the log entries depend on. Must be merged first. |
| L-0652 | direction, not merged | `wake`, which prints the summary, and the extended only-writer test. Must be merged first. |
| T-0010 | merged | `approve` and the `taken:` record. |

This ticket blocks: L-0655 (its mutations), L-0656 (sends this summary by Telegram), T-0054 (the guide's morning-summary example).

Family order (parent T-0053, six slices):

1. T-0053: the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor, and re-read T-0053's and L-0652's merged code before planning.
- No plan.md is published. The implementing session writes the plan.
- The log is opened in append mode with the full line already built (the repo's `open(p, "w")` landmine). One `write` call of one line under `O_APPEND`.
- Every field is folded to one line and `|` inside a field is replaced, so no field can forge a second entry or a `- reported` marker.
- A log that cannot be written does not undo an approval. A log that cannot be read never reads as "nothing to report".
- The log is local (`.work/` is ignored), is never committed, and is never read to make a decision.
- No Telegram or other send here (L-0656). No edit to a harness path; no sabotage mutations (L-0655).
- `autopilot.md`'s 110-line budget: reword inside it, else stop and ask.

## Open questions for the owner (recommended option taken)

1. Summary trigger. Taken (from the 2026-09-26 direction): at the first autopilot run after the window ends, and on `wake`.
2. Two worktrees of one repo have two `.work/` directories, so two logs. Accepted in the spec: each run reports what it did. Stated in CONFIG.md.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0653/` in the final PR unless the owner wants it kept.

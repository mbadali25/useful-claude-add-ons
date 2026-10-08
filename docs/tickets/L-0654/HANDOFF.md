# Cloud handoff: L-0654

**sleep deploy override, `nonprod` only; production always waits while asleep**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Not buildable until T-0053 has merged: it extends the settings overlay T-0053 adds.

- **Role:** child, split from T-0053, slice 4 of 6.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0654-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0654/direction.md`, `docs/tickets/L-0654/spec.md`
- **Size:** about 50 production lines. No new parser or state machine. No harness path; `python3 scripts/check-tooling-pr.py` must exit 0.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0053 | ready, not merged | Slice 1: the overlay this adds a key to. Must be merged first. |
| T-0072 | merged | `autopilot.deploy` and `deploy_allowed`, the policy this overlays. |
| T-0005 | merged | The environment classifier, unchanged. |

Not required first: T-0009 (in-progress; the deploy guard hook: `allow` here is necessary and never sufficient) and T-0045 (direction; the consumer that dispatches a deploy). Until T-0045 lands this policy is inert, and says so.

This ticket blocks: L-0655 (its mutations).

Family order (parent T-0053, six slices):

1. T-0053: the schedule, the resolver, the `approval` / `questions` overrides.
2. After T-0053, in any order: L-0651 (sabotage mutations for slice 1, tooling-only PR), L-0652 (manual `sleep` and `wake`), L-0654 (the `deploy` override).
3. L-0653 (sleep log and morning summary): after T-0053 and L-0652.
4. L-0655 (sabotage mutations for L-0652 to L-0654, tooling-only PR): after L-0651, L-0652, L-0653 and L-0654.
5. L-0656 (overrides for keys that do not exist yet): BLOCKED until T-0029 or T-0067 (review half) and T-0051 (notify half) merge; also needs L-0653.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor, and re-read `deploy_allowed` before planning.
- No plan.md is published. The implementing session writes the plan.
- `autopilot.sleep.deploy` accepts `null`, `nonprod` or `none`. `all`, or anything else, is refused with a warning and the day value stands.
- While asleep an effective value of `all` reads as `nonprod`: production is never unattended asleep.
- State `unknown` applies neither rule; the day value stands, including a day value of `all`. This is stated in the spec as a deliberate choice.
- The incident check, the one-root rule, the per-layer probes and the `ask` on any could-not-tell all still run first.
- Do not multiply the existing 324-case deploy matrix. A separate, smaller matrix goes in the sleep test file.
- No dispatch and no consumer (T-0045). No edit to a harness path; no sabotage mutations (L-0655).
- If T-0045 has landed by then, confirm with one end-to-end test that its consumer inherits this.

## Open questions for the owner (recommended option taken)

None of its own in the spec. The direction took option 1 (`sleep.deploy` accepts only `nonprod`, and `all` reads as `nonprod` asleep) over accepting any deploy value or waiting for T-0045. The parent's open questions are in T-0053's handoff.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0654/` in the final PR unless the owner wants it kept.

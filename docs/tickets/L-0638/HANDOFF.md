# Cloud handoff: L-0638

**Cross-session messaging: sabotage mutations for the bridge script (tooling PR)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: cannot start until T-0032, L-0636 and L-0637 are merged to main** (and, through them, T-0030 and T-0029). `crew_bridge.py` and its three test files do not exist yet.

- **Role:** child ticket, split from T-0032, slice 3 of 3 (the other children are L-0636 and L-0637).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0638-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0638/direction.md`, `docs/tickets/L-0638/spec.md`
- **Size:** 0 production lines; about 200 lines of tests, mostly a new `plugin/crew/tests/sabotage_bridge.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a harness path, so this lands alone as a tooling-only PR: tests, docs and version files may ride along, production code and prompts may not.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0032 | ready (PR in this hand-off) | `crew_bridge.py` and `test_crew_bridge.py`. |
| L-0636 | direction (PR in this hand-off) | The pending state and `test_crew_bridge_pending.py`. |
| L-0637 | direction (PR in this hand-off) | The lane refusal and `test_crew_bridge_hub.py`. |
| T-0030 | in-progress, not on main, not in this hand-off | Needed through the three above. |
| T-0029 | in-progress, not on main, not in this hand-off | Needed through L-0637. |

This ticket blocks nothing.

Order of the whole family:

1. T-0030 lands on main (not part of this hand-off). T-0029 must also be on main before L-0637.
2. T-0031 (PR in this hand-off): ordering only, the owner's order is T-0030, T-0031, T-0032.
3. T-0032: the doorbell grammar (`ring`, `receive`) and the untrusted-data rules.
4. L-0636: an unanswered doorbell reads `could not tell`.
5. L-0637: the hub rule, lanes never ring a peer. After L-0636, because both edit `crew_bridge.py` and `autopilot.md`.
6. L-0638: the sabotage mutations for the bridge script, as a tooling-only PR. Last.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan, after the three feature PRs merge. Each anchor is written against the merged `crew_bridge.py`, not against this spec.
- `plugin/crew/tests/sabotage.py` was measured at 3400 lines, which is `.pylintrc`'s `max-module-lines`. A registration line does not fit. How a per-area module is registered without growing that file was not checked; read the newest module's registration first.
- No change to `crew_bridge.py`, any command, prompt, hook or other production file. A missing test found by a mutation is added here; a production bug is a new ticket.
- No change to `review_*.py`, `verify-gate.*`, `crew_ticket.py`, `scope_guard.py` or `scripts/check-tooling-pr.py`.
- No crew version bump unless `scripts/check-marketplace.py` demands one for a tests-only change; if it does, the version files ride along.
- The full sabotage run is long and memory-heavy. Run one area only; confirm the runner's selection flag from `sabotage.py`'s own usage text. The spec says to use the host's heavy-run wrapper "if it has one"; whether the cloud session has one: could not tell.
- A harness change triggers `.crew/verify.json`'s harness rule: `scripts/check-tooling-pr.py`, `scripts/_test/tooling-pr.py`, the golden replay, the seam contracts and the canary review.

## Open questions for the owner (recommended option taken)

1. `sabotage.py` is exactly at the module line limit, so a registration line does not fit. Taken: register the way the newest per-area module does at implementation time; if every route needs a new line in `sabotage.py`, remove a line in the same change or stop for the owner.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0638/` in the final PR unless the owner wants it kept.

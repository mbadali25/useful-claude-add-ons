# Cloud handoff: L-0686

**Sabotage mutations for autopilot's hold, landing, needs-owner, closed and blocked stops**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Blocked: not workable until L-0550 has merged, because the mutations' `find` strings are taken from its merged code.

- **Role:** child, split from L-0550, slice 1 of 1. L-0550 was itself split from T-0037, which is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0686-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0686/direction.md`, `docs/tickets/L-0686/spec.md`
- **Size:** 0 production lines. About 50 lines in `plugin/crew/tests/sabotage_autopilot.py` and about 12 in `plugin/crew/tests/test_crew_autopilot.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage_autopilot.py` is a harness path, so this lands alone as a tooling-only PR. `scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## What PR #394 looks like it covers

Read from PR #394's title and body on 2026-10-04. It was open, not merged.

- "a header cancelled is re-driven" and "a needs-owner ticket is driven": probably covered elsewhere. PR #394 ran `HEADER_CLOSED = ("done",)` and "`needs-owner` branch made dead" by hand, with other test names, and says its follow-up PR B (`T-0037-sabotage`) registers them in `sabotage_autopilot.py`. Whether PR B exists yet: could not tell. If it has landed, do not register the same mutation twice.
- "a gate phase reads as autopilot's in status": partly. PR #394 lists a hand mutation on `WAITING`; for which phases: could not tell.
- The hold, landing, blocked and unknown-dependency mutations: not covered. Their targets are L-0550's code.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0550 | spec, draft PR in this batch, not merged | The code and tests the mutations target. Must be merged first. |
| T-0037 | open as PR #394, not merged | Needed through L-0550. |
| L-0639 | spec, draft PR in this batch, not merged | Needed through L-0550. |
| L-0640 | spec, draft PR in this batch, not merged | Needed through L-0550. |
| T-0087 | merged | The tooling-PR rule. |

Not required: L-0641 (it adds a different sabotage file).

This ticket blocks nothing.

Family order: T-0037 (PR #394) -> L-0639 -> L-0640 -> L-0550 (feature) -> L-0686 (this tooling PR, straight after).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and PR #394's PR B edits the same file; re-check each anchor.
- No plan.md exists for this ticket; a stale plan.md for T-0037 exists locally and is not published. The implementing session writes the plan, after L-0550 has merged.
- The mutation list follows L-0550 as merged. If L-0550 drops a stop because T-0037 already has it, drop its mutation here and update the pinned label set.
- `plugin/crew/tests/sabotage.py` is not edited: it was at its 3400-line limit at `155fe6d8`. The new tuple is appended to `AUTOPILOT_MUTATIONS` inside `sabotage_autopilot.py`.
- No production code and no command text. A production bug found here is a stop and a separate feature ticket.
- Run only through `sabotage.py`. If a mutation reports green, check the `.pyc` timestamp before calling the test weak.
- `plugin/crew/tests/` ships inside the plugin, so crew still gets a version bump.

## Open questions for the owner (recommended option taken)

1. Mutations in `sabotage_autopilot.py` as a `GATE_MUTATIONS` tuple (option 1), or in L-0641's `sabotage_ticket_state.py` (option 2)? Taken: option 1.

The parent's open questions (hold past its revisit date, blocked during review, `landing` and `/crew:done`) are in L-0550's HANDOFF.md; their answers decide which tests these mutations name.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0686/` in the final PR unless the owner wants it kept.

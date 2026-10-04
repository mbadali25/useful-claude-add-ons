# Cloud handoff: L-0641

**Sabotage mutations for ticket state (closed words, dependency state, next.md)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Not workable until L-0639 and L-0640 have merged.

- **Role:** child, split from T-0037, slice 3 of 3 (L-0639, L-0640, L-0641). T-0037 itself is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0641-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0641/direction.md`, `docs/tickets/L-0641/spec.md`
- **Size:** 0 production lines. About 60 lines of test harness in a new `plugin/crew/tests/sabotage_ticket_state.py` and a net-zero edit to `plugin/crew/tests/sabotage.py`.
- **Harness:** yes. `plugin/crew/tests/sabotage*.py` is a harness path, so this lands alone as a tooling-only PR. `scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## What PR #394 looks like it covers

Read from PR #394's title and body on 2026-10-04. It was open, not merged.

- The mutation "`cancelled` dropped from `_TABLE_DONE_WORDS`": probably covered elsewhere. PR #394 ran "`superseded` dropped from `_TABLE_DONE_WORDS`" and "`cancelled` dropped from `_DONE_RE`" by hand and says its follow-up PR B (`T-0037-sabotage`) registers them in `sabotage_tracker.py`, `sabotage_autopilot.py` and `sabotage_scope.py`. Whether PR B exists yet: could not tell. If it has landed, do not register the same mutation twice.
- The other seven mutations (dependency state, the review ledger, `next.md`): not covered. Their targets are L-0639's and L-0640's code.
- The test this spec names for the closed-words mutation, `test_cancelled_and_superseded_rows_are_closed`, is L-0639's. PR #394 uses other test names for the same rule. Use whichever test exists on main.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0639 | spec, draft PR in this batch, not merged | The code and tests the mutations target. Must be merged first. |
| L-0640 | spec, draft PR in this batch, not merged | The `next.md` code and tests the mutations target. Must be merged first. |
| T-0037 | open as PR #394, not merged | Needed through L-0639. |
| T-0087 | merged | The tooling-PR rule. |

This ticket blocks nothing. L-0686 (L-0550's mutations) does not need it: that spec puts its mutations in `sabotage_autopilot.py`.

Family order: T-0037 (PR #394) -> L-0639 (feature) -> L-0640 (feature) -> L-0641 (this tooling PR).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor, above all the `sabotage.py` lines `:67-88` and `:3064-3071`.
- A stale plan.md exists locally for T-0037 and is not published. The implementing session writes this ticket's plan.
- `sabotage.py` was exactly at the 3400-line pylint limit at `155fe6d8` and must not grow. The spec's net-zero edit joins two concatenation lines to free the line the new import needs; check that those lines are still as described.
- Take each `find` string from the merged code. Each must occur exactly once in its target.
- Run mutations only through the runner, never by hand. If a mutation reports green, check the `.pyc` timestamp before calling the test weak.
- No production code and no command text in this PR. A production bug found here is a stop and a separate feature ticket.
- `plugin/crew/tests/` ships inside the plugin, so crew still gets a version bump.

## Open questions for the owner (recommended option taken)

1. L-0550 and L-0551 need the same feature-then-tooling pairing for their own mutations. Taken in this spec: they append to `sabotage_ticket_state.py` later. L-0686's spec chose `sabotage_autopilot.py` instead; where they disagree, L-0686's spec decides for L-0686.
2. Until this ticket lands, L-0639's and L-0640's must-block tests are not mutation-proven. Accepted.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0641/` in the final PR unless the owner wants it kept.

# Cloud handoff: L-0551

**`/crew:status --owner` and the waiting line**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Every prerequisite of this slice is already on main, so it can be worked now, but it edits two files PR #394 also edits.

- **Role:** parent with one child, L-0687 (hold, blocked, landing and needs-owner in the owner list). This ticket was itself split from T-0037 on 2026-09-30. T-0037 is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction, priority high (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0551-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0551/direction.md`, `docs/tickets/L-0551/spec.md`
- **Size:** about 110 production lines: `plugin/crew/hooks/scripts/crew_autopilot.py` about 55, `plugin/crew/hooks/scripts/crew_status.py` about 40, `plugin/crew/commands/status.md` about 15. No harness path: a feature PR. The three files are seam paths, so the harness verify rule (golden replay, seam contracts, canary) still runs. `scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.

## What PR #394 looks like it covers

Read from PR #394's title, body and diff on 2026-10-04. It was open, not merged.

- The `--owner` flag, `owner_items`, `deep=False` and the `waiting` line: not covered. None of them is in the PR's added lines.
- Overlap to reconcile: PR #394 makes the default `/crew:status` report print a line `owner    <ids> (needs-owner)`, and edits `crew_status.py`, `commands/status.md` and `test_status.py`. This spec adds a `waiting` line to the same report, which must stay within 40 lines. Whether the two lines should be merged into one: could not tell; ask the owner.
- PR #394 adds a `needs-owner` stop phase to `_phase`. This spec has no action text for it, so it would be listed as `see /crew:autopilot status <id>` (the spec's stated fallback) until L-0687.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0004 | merged | `crew_autopilot.py` and its phase table. |
| T-0010 | merged | `policy=False`, the policy-free phase read the owner list uses. |
| T-0018 | merged | `/crew:autopilot status`, `WAITING`, `_reserved_round`. |
| L-0510 | done | `review_ledger.receipt_stands`, which decides the `accept-review` stop. |
| T-0087 | merged | The tooling-PR rule and the seam list. |

Not a dependency of this slice: T-0037 (PR #394), L-0639, L-0640, L-0641, L-0550. They are dependencies of L-0687.

The specs disagree here. L-0550's, L-0639's and L-0640's specs each list L-0551 as something they block. This spec says this slice needs none of them, because the parts that did were moved to L-0687. This spec wins for this ticket.

Same hot file, no order required, but never in parallel: L-0550, T-0043 (ready), T-0022 (approved) and PR #394 all edit `crew_autopilot.py`. Whichever lands second merges main first. Landing after PR #394 is the safer order because of the overlap above.

This ticket blocks L-0687.

Family order: L-0551 (this feature PR) -> L-0687, which also waits on T-0037 (PR #394) -> L-0639 -> L-0640 -> L-0550.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md exists for this ticket. T-0037's plan.md Step 6 (quoted in direction.md) is the old design, does not match this spec, and is not published. The implementing session writes the plan.
- `/crew:status` must stay read-only. `deep=False` exists so the owner list returns before `review_ledger.check_receipt`, which rebuilds the review bundle and writes under `.git`. Nothing may change in what `_phase` answers when `deep` is true.
- `/crew:done` check 2 runs the default report, so the `waiting` line must be cheap and can never fail the run. Measure it as the spec's Unknowns say; more than 2 seconds added is a stop to the owner.
- An unknown stays unknown: no INDEX.md, a `_phase` that raises, and a failed `crew_autopilot` import each print could-not-tell, never "nothing on you".
- Do not copy or move a sabotage-anchored line in `crew_status.py` or `crew_autopilot.py`. No `sabotage*.py` in this PR.
- This spec says `autopilot.md` is at a 120-line cap; L-0550's spec measured 109 lines against a 110-line limit. Which is right: could not tell. It does not matter here, because this ticket does not edit that file.

## Open questions for the owner (recommended option taken)

1. Two-slice order: the owner list from today's autopilot phases first, hold/blocked/needs-owner later in L-0687. Taken: yes.
2. Slice 1's waiting line is `waiting  N on you (/crew:status --owner)`, with unread and could-not-tell counts only when non-zero; `H held, B blocked` arrives with L-0687. Taken: yes.
3. A ticket with a finished review round (CLEAN or accepted) is reported as "in review, not read", pointing at `/crew:autopilot status <id>`. Should `--owner` pay for the bundle rebuild instead? Taken: never rebuild from `/crew:status`.
4. A ticket folder with no INDEX row is listed as `direction-approval`. Taken: list it.
5. `--owner` together with `--memory` is refused. Taken: refuse.
6. If the waiting line adds more than 2 seconds to the default report, should it leave the default report? Taken: stop and ask at implement time.
7. New, raised by PR #394: one line or two for PR #394's `owner` line and this ticket's `waiting` line? No option taken.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0551/` in the final PR unless the owner wants it kept.

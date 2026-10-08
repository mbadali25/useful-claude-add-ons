# Cloud handoff: L-0550

**autopilot stops on hold, landing, needs-owner, cancelled/superseded and blocked**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Blocked: not implementable until T-0037, L-0639 and L-0640 have merged.

- **Role:** parent with one child, L-0686 (the sabotage mutations for these stops, a tooling PR). This ticket was itself split from T-0037 on 2026-09-30. T-0037 is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction, priority high (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0550-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0550/direction.md`, `docs/tickets/L-0550/spec.md`
- **Size:** about 90 production lines, about 88 of them in `plugin/crew/hooks/scripts/crew_autopilot.py`; `plugin/crew/commands/autopilot.md` changes in place with no added line. No harness path: a feature PR. `scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.

## What PR #394 looks like it covers

Read from PR #394's title, body and diff on 2026-10-04. It was open, not merged.

| Part of this spec | In PR #394? |
|---|---|
| A header `cancelled` or `superseded` reads `closed`, and the reason names the successor | Looks covered: a new `HEADER_CLOSED`, `_closed` updated, the closed reason quotes a `split-into:` or `superseded-by:` line. It reads that line from spec.md line 2, not from `next.md` as this spec does. |
| An INDEX `needs-owner` row stops as phase `needs-owner`, waiting on the owner | Looks covered. Its reason names the unanswered `## Open questions`, not `next.md`'s `next:` line. |
| `WAITING` knows the new phase | Looks covered for `needs-owner`. |
| A header `status: needs-owner` | Contradicted. PR #394 records an owner decision that `needs-owner` never goes in a spec header. |
| `hold` (INDEX cell or header), `landing` | Not covered: neither word appears in the PR's added lines. |
| `blocked` from a `depends-on:` line | Not covered. |
| `hold`, `landing` and the rest as valid header statuses, so a header `status: hold` does not stale the approval | Not delivered. PR #394 leaves `crew_ticket.STATUS_VALUES` unchanged and says a header edit to the new words stales an approval on purpose. |
| Whether `needs-owner` is in `FIXED_STOPS` and named in `autopilot.md` | Could not tell from the body; `autopilot.md` is in the PR's file list. |

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0037 | open as PR #394, not merged | The status vocabulary. The spec also expects it to make the new words valid header values and to add `depends-on:`; PR #394 does neither (see above). |
| L-0639 | spec, draft PR in this batch, not merged | `crew_ticket_state.view`, `dependency_state`; the gate and blocked stops read `view`. |
| L-0640 | spec, draft PR in this batch, not merged | `next.md` in `view`: the hold reason and revisit date, the needs-owner `next:` line, the successor name. |
| T-0026 | merged | The approval digest the header statuses ride on. |
| T-0004, T-0018, T-0010 | merged | `next`, `status`, and the policies this edits around. |
| T-0087 | merged | The tooling-PR rule that moves the mutations to L-0686. |

Not required: L-0641.

Same hot files, serialise, no order forced: T-0022 (approved) and T-0043 (ready) also edit `crew_autopilot.py` and `autopilot.md`. Whichever lands second merges main and re-finds its anchors.

This ticket blocks L-0686, L-0551 and T-0054, per this spec. The published L-0551 spec says its first slice no longer depends on this ticket and that only its child L-0687 does; L-0551's spec decides for L-0551. Both still edit `crew_autopilot.py`, so do not run them in parallel.

Family order: T-0037 (PR #394) -> L-0639 -> L-0640 -> L-0550 (this feature PR) -> L-0686 (tooling PR, straight after).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`) and PR #394 edits the same functions; re-check each anchor by content.
- No plan.md exists for this ticket. A stale plan.md exists locally for T-0037 (its Step 5 is quoted in direction.md) and is not published. The implementing session writes the plan.
- Write the plan against `crew_ticket_state.py` as merged. The prerequisite specs fix `view`'s behaviour, not its key names. A fact `view` lacks is a stop and an amendment to L-0639 or L-0640, never an edit here.
- Start by diffing this spec's Design against merged T-0037. Drop what is already there, and take the conflicts listed above (header `needs-owner`, header `hold` and the approval digest, where `superseded-by` lives) to the owner before planning.
- `autopilot.md` was at 109 lines against a 110-line limit at `155fe6d8`, and PR #394 edits it too. Re-measure; it must not exceed the limit.
- No `plugin/crew/tests/sabotage*.py` and no `crew_ticket.py` in this PR. Keep the existing sabotage anchors (`"    if status in INDEX_DONE:\n"`, `"    if status not in DIRECTION_APPROVED:\n"`, the `_closed` anchor) matching exactly once; a moved anchor is fixed in L-0686 and reported.
- No `try` around the `view` call: a crash must print `stop=1`, never read as "no gate".
- The spec header carries no `depends-on:` line. Its reason ("two prerequisites have no ticket id") no longer holds: they are L-0639 and L-0640. Add the line at plan time if the field exists by then.

## Open questions for the owner (recommended option taken)

1. Should a hold whose `revisit:` date has passed still stop autopilot? Taken: yes, and the reason says the date has passed. Only the owner editing the status lifts a hold.
2. Should a blocked ticket already in review finish review and stop only at done? Taken: it stops at once.
3. Should `landing` let autopilot run `/crew:done` when the receipt is current? Taken: no, `landing` always stops.
4. Mutations go in `sabotage_autopilot.py` (L-0686), not in L-0641's `sabotage_ticket_state.py`. Confirm or redirect.
5. New, raised by PR #394: is a header `hold`, `landing` or `needs-owner` still wanted, given PR #394 keeps `STATUS_VALUES` unchanged and keeps `needs-owner` out of spec headers? No option taken; ask the owner.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0550/` in the final PR unless the owner wants it kept.

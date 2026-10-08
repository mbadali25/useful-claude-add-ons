# Cloud handoff: L-0687

**The owner list and the waiting line know hold, blocked, landing and needs-owner**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Blocked: not workable until L-0551, L-0550, L-0640, L-0639 and T-0037 have all merged.

- **Role:** child, split from L-0551, slice 1 of 1. L-0551 was itself split from T-0037, which is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0687-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0687/direction.md`, `docs/tickets/L-0687/spec.md`
- **Size:** about 45 production lines: `plugin/crew/hooks/scripts/crew_autopilot.py` about 28, `plugin/crew/hooks/scripts/crew_status.py` about 9, `plugin/crew/commands/status.md` about 8. No harness path: a feature PR. The three files are seam paths.

## What PR #394 looks like it covers

Read from PR #394's title, body and diff on 2026-10-04. It was open, not merged.

- `needs-owner` in the default `/crew:status` report: partly covered. PR #394 prints `owner    <ids> (needs-owner)`. It does not give the `next:` line; its autopilot stop names the unanswered `## Open questions` instead.
- `WAITING` for `needs-owner`: looks covered. For `hold`, `landing` and `blocked`: not covered.
- `H held, B blocked` on the waiting line, `revisit` for a due hold, skipping `landing`: not covered. Their inputs come from L-0550, L-0639 and L-0640.
- Closed words (`cancelled`, `superseded`) skipped by the list: looks covered, since PR #394 makes every reader treat them as closed.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0551 | spec, draft PR in this batch, not merged | `owner_items`, `--owner`, the waiting line: the code this ticket extends. |
| L-0550 | spec, draft PR in this batch, not merged, itself blocked | The autopilot stops `hold`, `landing`, `needs-owner`, `blocked`. |
| L-0640 | spec, draft PR in this batch, not merged | `next.md` and `revisit_due`. |
| L-0639 | spec, draft PR in this batch, not merged | `crew_ticket_state.view` and `blocked_by`. |
| T-0037 | open as PR #394, not merged | The status vocabulary. |

This ticket blocks nothing known.

Order of everything it waits on: T-0037 (PR #394) -> L-0639 -> L-0640 -> L-0550, and separately L-0551; then L-0687. L-0686 and L-0641 are tooling PRs it does not need.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md exists for this ticket; a stale plan.md for T-0037 exists locally and is not published. The implementing session writes the plan.
- Refresh the spec first. Its phase names and `view` keys are taken from other tickets' specs, not from code. Once L-0550 has merged, re-read `crew_autopilot._phase` and `crew_ticket_state.view` on main and correct the names with a "Refreshed" note. If L-0550 changed a name, this spec follows L-0550.
- If merged T-0037 keeps `needs-owner` out of `next.md` (PR #394 uses `## Open questions`), the `needs-owner` action text here needs the owner's decision before planning.
- `WAITING`: add the four phases here only if L-0550 did not.
- An unknown must not read as "not yet": a hold with no usable revisit date is listed, not held.
- `/crew:status` stays read-only and within 40 lines. No bundle rebuild, no policy read, no file written.
- No `sabotage*.py`, no edit to `autopilot.md` or `done.md`.

## Open questions for the owner (recommended option taken)

1. Should a blocked ticket appear in the `--owner` list at all? Taken: counted, not listed.
2. A hold with no `revisit:` line: listed as due now, or held? Taken: listed.

The parent's open questions are in L-0551's HANDOFF.md.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0687/` in the final PR unless the owner wants it kept.

# Cloud handoff: L-0640

**next.md: waiting-on, next, reason, revisit and superseded-by, read into the ticket view**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Not workable until T-0037 and L-0639 have merged.

- **Role:** child, split from T-0037, slice 2 of 3 (L-0639, L-0640, L-0641). T-0037 itself is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0640-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0640/direction.md`, `docs/tickets/L-0640/spec.md`
- **Size:** about 75 production lines in `plugin/crew/hooks/scripts/crew_ticket_state.py` (one new parser, `read_next`). No harness path: an ordinary feature PR.

## What PR #394 looks like it covers

Read from PR #394's title, body and diff on 2026-10-04. It was open, not merged.

- `next.md` and `read_next`: not covered. Nothing in the PR's diff names `next.md`.
- The successor of a superseded ticket: partly overlapping. PR #394 quotes a `split-into:` or `superseded-by:` line from line 2 of spec.md in autopilot's closed reason. This spec puts `superseded-by` in `next.md`. That gives two places for the same fact; which one wins: could not tell, ask the owner.
- What is asked of the owner on a `needs-owner` ticket: partly overlapping. PR #394's autopilot stop names the unanswered `## Open questions`. This spec uses `next:` in `next.md` and reports "cannot tell what is asked" without one. Whether both are wanted: could not tell.
- `waiting-on`, `next`, `reason`, `revisit`, `revisit_due`: not covered.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0639 | spec, draft PR in this batch, not merged | Adds `crew_ticket_state.py` and `view`, which this ticket extends. Must be merged first. |
| T-0037 | open as PR #394, not merged | Status vocabulary, needed through L-0639. |

This ticket blocks L-0641, L-0550 (hold reason and revisit date, the needs-owner `next:` line, `superseded-by`) and L-0551 (owner list actions), per the spec. The published L-0551 spec says its first slice needs nothing unlanded and that its child L-0687 is the part that needs this ticket; L-0551's own spec is the later, more specific one.

Family order: T-0037 (PR #394) -> L-0639 (feature) -> L-0640 (feature) -> L-0641 (tooling PR, sabotage mutations). Consumers after that: L-0550 -> L-0686, and L-0687.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md exists locally for T-0037 and is not published. The implementing session writes this ticket's plan.
- `view`'s real keys come from L-0639's merged code. Read it before planning.
- No writer: nothing in crew creates or edits `next.md` in this ticket, and no command text tells an agent to.
- `next.md` is not part of the contract: `crew_ticket.validate`, the approval digest and the scope guard never read it.
- A malformed or missing value is reported as a problem and never read as "nothing asked". `revisit_due` is `None`, not False, for a bad date.
- The must-block tests added here are not mutation-proven until L-0641 lands.

## Open questions for the owner (recommended option taken)

1. Who writes `next.md`? Taken: nobody automatically in this slice; a writer command is a later ticket if wanted.
2. `revisit:` format. Taken: ISO `YYYY-MM-DD` only.
3. The sabotage mutations land later in L-0641. Accepted.
4. New, raised by PR #394: `superseded-by` in spec.md line 2 (PR #394) or in `next.md` (this spec)? No option taken; ask the owner before planning.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0640/` in the final PR unless the owner wants it kept.

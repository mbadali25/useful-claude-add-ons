# Cloud handoff: L-0639

**cancelled and superseded close a ticket; blocked and needs-replan are derived (`crew_ticket_state.py`)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Check PR #394 first: it may already cover part of this ticket. Not workable until T-0037 has merged.

- **Role:** child, split from T-0037, slice 1 of 3 (L-0639, L-0640, L-0641). T-0037 itself is not published here: a cloud session already builds it in PR #394 (branch `T-0037-build`, "T-0037 (A)").
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0639-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0639/direction.md`, `docs/tickets/L-0639/spec.md`
- **Size:** about 130 production lines, about 120 of them in a new `plugin/crew/hooks/scripts/crew_ticket_state.py`. No harness path: an ordinary feature PR. `scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.

## What PR #394 looks like it covers

Read from PR #394's title, body and diff on 2026-10-04. It was open, not merged.

| Part of this spec | In PR #394? |
|---|---|
| `cancelled` and `superseded` in `crew_state._TABLE_DONE_WORDS` and `crew_autopilot.INDEX_DONE`, with tests that a cancelled or superseded INDEX row is closed | Looks covered. Its body says both lists gain the words and a new `test_status_vocabulary.py` holds every closed list to `crew_tracker.CLOSED_STATUSES`. |
| A header `cancelled` or `superseded` reads as closed in autopilot | Looks covered (`HEADER_CLOSED`). That was L-0550's scope, not this ticket's. |
| `crew_ticket_state.py` (`dependency_state`, `view`), derived `blocked` and `needs-replan` | Not covered. No such file is in the PR's diff. |
| The optional `depends-on:` line in `/crew:spec`'s template | Not covered. `plugin/crew/commands/spec.md` is not in the PR's file list. |
| The prerequisites this spec expects from T-0037: `crew_ticket.CLOSING_STATUSES`, `DERIVED_STATUSES`, `header_status`, `parse_depends_on` | Not delivered. PR #394 says `crew_ticket.py` is not edited and `STATUS_VALUES` is unchanged; the vocabulary lives in `crew_tracker.py` as `OWNER_STATUSES` and `CLOSED_STATUSES`. Whether a later T-0037 PR adds a `depends-on:` parser: could not tell. PR #394's announced follow-up (PR B, `T-0037-sabotage`) only registers sabotage mutations. |

So PR #394 is not the T-0037 this spec was written against. The spec assumed T-0037 changes only `crew_ticket.py`; PR #394 changes `crew_tracker.py`, `crew_state.py`, `crew_autopilot.py`, `crew_status.py` and their docs instead.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0037 | open as PR #394, not merged | The status vocabulary. Must be merged first. See the table above for what it does and does not deliver. |
| T-0026 | merged | Approval digest. Context. |
| T-0021 | merged | Tracker lanes. Context. |
| T-0087 | merged | Tooling-PR rule: why this slice holds no harness path. |

T-0043 is listed in the facts for the parent as no longer a dependency of this slice.

This ticket blocks L-0640, L-0641, L-0550, L-0551, T-0052 and T-0059 (the spec's list). The published L-0551 spec says its first slice needs nothing unlanded and that only its child L-0687 needs this ticket; the two specs disagree on that point and L-0551's own spec is the later, more specific one.

Family order: T-0037 (PR #394) -> L-0639 (feature) -> L-0640 (feature) -> L-0641 (tooling PR, sabotage mutations). Consumers after that: L-0550 -> L-0686, and L-0687.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`) and PR #394 moves it again; re-check each anchor after T-0037 merges.
- A stale plan.md exists locally for T-0037 and is not published. The implementing session writes this ticket's plan.
- Write the plan against the merged T-0037 code, not against the spec's "From T-0037" evidence line. Where the spec needs `parse_depends_on` or `header_status` and the merged code has neither, that is a question for the owner, not something to add to `crew_ticket.py` here: `crew_ticket.py` is a harness path and this ticket excludes it.
- If the closed-word edits are already on main, drop them from this PR and keep the tests that still add something. The spec's Exclusions say the only `crew_autopilot.py` change is the `INDEX_DONE` tuple.
- PR #394's body says `crew_state.py` stays at exactly 3400 lines, which is the pylint module limit. Any line this ticket adds to that file needs one removed.
- PR #394 reads `superseded-by:` and `split-into:` from line 2 of spec.md, and says `needs-owner` never goes in a spec header. This spec's `view` reads a gating status from the INDEX cell or the header. Reconcile with the merged code.
- Keep the sabotage anchors `"    if status in INDEX_DONE:\n"` and the `_closed` anchor matching exactly once. Their line numbers will have moved.
- `crew_ticket_state.py` writes no file and runs no subprocess.
- The must-block tests added here are not mutation-proven until L-0641 lands.

## Open questions for the owner (recommended option taken)

1. A dependency marked `done` but not yet `merged` unblocks. Kept from the approved T-0037 spec. Confirm.
2. The sabotage mutations for this slice land later in L-0641, so until then the must-block tests are not mutation-proven. Accepted.
3. The four-slice order T-0037 -> L-0639 -> L-0640 -> L-0641. Taken: yes.
4. Should a tracker-lane ticket be filed for the statuses `crew_tracker.LANE_FOR_STATUS` refuses? Taken: excluded from every slice. PR #394 appears to add lane rows for the closed words and `needs-owner`; whether that settles it: could not tell.
5. New, raised by PR #394: which ticket owns the `depends-on:` parser and the header status helpers now that T-0037 does not edit `crew_ticket.py`? No option taken; ask the owner before planning.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0639/` in the final PR unless the owner wants it kept.

# Cloud handoff: T-0032

**Cross-session messaging: the doorbell grammar, and inbound messages as untrusted data**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Blocked: implementation cannot start until T-0030 is merged to main.** `crew_bridge.py` imports from `crew_coord.py`, which is only on a local branch that is not on the shared remote; origin/main `ce235468` has no `crew_coord.py`.

- **Role:** parent ticket. Its children are L-0636, L-0637 and L-0638.
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0032-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0032/direction.md`, `docs/tickets/T-0032/spec.md`
- **Size:** about 180 production lines (a new `plugin/crew/hooks/scripts/crew_bridge.py` about 170, command front matter and the `.crew/verify.json` rule about 10). No harness path. `plugin/crew/commands/autopilot.md` is a `SEAM` path; the spec says that matters only in a PR that also changes a harness path, and this one does not. The sabotage mutations are L-0638, a tooling-only PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0030 | in-progress, not on main, not in this hand-off | Hard dependency. `crew_bridge.py` imports `crew_coord.Channel`, `safe`, `peer` and the exit codes. |
| T-0031 | ready (PR in this hand-off) | Ordering only: the owner's order is T-0030, T-0031, T-0032, and `kind=contract` names its files as a hint. This slice imports no T-0031 code. |
| T-0010 | merged | Context: the questions policy an inbound message must never answer. |
| T-0018 | merged | Context: the autopilot subcommand router; this slice adds no subcommand. |
| T-0004 | merged | Context: `/crew:autopilot` and its resume step. |

T-0029 (in-progress) is not needed by this ticket; it is needed by L-0637.

Where the documents disagree: this spec and the facts recorded for the hand-off say T-0031 "has no spec yet". A T-0031 spec dated 2026-10-04 now exists and is published in this same hand-off. Also, the specs of L-0633 and L-0634 (children of T-0031) each list T-0032 under "Blocks", while this spec names neither as a dependency. This spec wins for this ticket: only T-0030 is a hard dependency and T-0031 is ordering. Whether the owner wants L-0633 and L-0634 landed before T-0032 as well: could not tell.

This ticket blocks: L-0636, L-0637 and L-0638. L-0546 names `kind=finding` and `kind=question` but does not need this ticket to land.

Order of the whole family:

1. T-0030 lands on main (not part of this hand-off). T-0029 must also be on main before L-0637.
2. T-0031 (PR in this hand-off): ordering only, the owner's order is T-0030, T-0031, T-0032.
3. T-0032: the doorbell grammar (`ring`, `receive`) and the untrusted-data rules.
4. L-0636: an unanswered doorbell reads `could not tell`.
5. L-0637: the hub rule, lanes never ring a peer. After L-0636, because both edit `crew_bridge.py` and `autopilot.md`.
6. L-0638: the sabotage mutations for the bridge script, as a tooling-only PR. Last.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- Every `crew_coord.py` anchor is from the unmerged branch `T-0030-coord` at `ec9a28a2`, which had one review round left and is not on the shared remote, so a cloud session cannot read it. Re-check each name after T-0030 merges. If `Channel.fetch` no longer returns a fetched tip without moving a ref, stop and return to the owner.
- No plan.md is published (the spec says none exists). The implementing session writes the plan, after T-0030 lands.
- No call to `SendMessage` or `ListAgents` from Python; the script only composes and classifies text. No write to the record, no new hook, no config key, no new `/crew:autopilot` subcommand.
- `receive` never prints a next step taken from the message; the only next step it names is the fixed `crew_coord.py status` line.
- Never read, print or log the messaging token or any credential-shaped environment value. The doorbell never contains a URL.
- The stdin hand-off of an inbound message is a prose control (a per-call heredoc terminator); the README must say so.
- No edit to `crew_coord.py`, `crew_ticket.py`, `approval_hook.py`, `scope_guard.py`, `crew_autopilot.py` or any other `HARNESS` or `SEAM` script. No `sabotage*.py` file in this PR.
- The guide rebuild needs Word or LibreOffice. Without either, edit the `.md` source only and say in the PR body that the HTML, DOCX and PDF were not rebuilt.
- direction.md refers to `.work/tickets/T-0030/direction.md` as the approved direction. That file is not published here.

## Open questions for the owner (recommended option taken)

1. Fixed-grammar doorbell composed and classified by a script, or prose rules only in `autopilot.md`? Taken: the script.
2. Should the doorbell carry anything besides channel, tip, kind and ref? Taken: no (no URL, no question or answer text).
3. Add a `/crew:autopilot join <channel>` subcommand (open since T-0030's direction)? Taken: no subcommand; the channel is named on the command line.
4. Can T-0032 land before T-0031? Taken: keep the owner's order T-0030, T-0031, T-0032, although this slice only needs T-0030's code.

The children's own questions are in their hand-off notes (L-0636, L-0637, L-0638).

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0032/` in the final PR unless the owner wants it kept.

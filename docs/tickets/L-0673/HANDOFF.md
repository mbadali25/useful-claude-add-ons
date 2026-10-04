# Cloud handoff: L-0673

**T-0082 child 1: the CI receipt's per-command list never reads a missing failure line as PASS; verify.md documents "could not tell"**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked until T-0082 has merged: this ticket reads a log line that T-0082 creates.

- **Role:** child ticket, split from T-0082, slice 1 of 2 (the other is L-0674).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0673-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0673/direction.md`, `docs/tickets/L-0673/spec.md`
- **Size:** about 30 production lines, all in `plugin/crew/hooks/scripts/ci_receipt.py`.
- **Harness:** no. `ci_receipt.py` and `plugin/crew/commands/verify.md` are outside the harness list, which is why they were split out of T-0082's tooling-only PR. This is a feature PR and must contain no harness path.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0082 | direction, spec ready, not built | Must merge first. It creates the `verify-gate: COULD NOT TELL (<reason>): <cmd>` line this ticket reads. |
| L-0555 | done | The CI receipt, the module being changed. |

The ticket facts and the spec agree on these two. The parent's own prerequisites (T-0087, L-0513, L-0572, T-0076, T-0077) have all landed.

This ticket blocks nothing.

Family order:
1. T-0082 (parent, tooling-only PR)
2. L-0673 (this ticket), after T-0082 has merged
3. L-0674, after T-0082 has merged and an owner go. No order between L-0673 and L-0674.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`), and T-0082 will move it again; re-read every line number after T-0082 merges.
- A stale plan.md is not published. The implementing session writes the plan.
- The exact `COULD NOT TELL` line text is fixed by T-0082's merged code, not by its spec. Read it from origin/main and pin it with a fixture log captured from a real run of the merged gate.
- Acceptance of a receipt does not change: `build` and `check` accept and refuse exactly what they did. Only the informative per-command list gains the state UNKNOWN. No new receipt schema version.
- No sabotage module may be edited here (harness paths). The sabotage check is done by hand and stated in the PR.

## Open questions for the owner (recommended option taken)

1. Option 1 (add an UNKNOWN state and mark a log without the total line incomplete) was taken over docs-only. The owner was not available on 2026-10-04.

The parent's open questions 1 and 2 (completion record or label-only; whether a status above 128 prints "could not tell") decide the line this ticket parses. See T-0082's HANDOFF.md.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0673/` in the final PR unless the owner wants it kept.

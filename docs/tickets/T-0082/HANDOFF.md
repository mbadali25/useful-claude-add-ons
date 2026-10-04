# Cloud handoff: T-0082

**verify gate: a killed, hung or timed-out rule is FAILED (could not tell), never a pass for want of a VERIFY FAILED line**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket. Its children are L-0673 (child 1) and L-0674 (child 2, on hold). This ticket is itself the first slice of the work.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority high.
- **Branch:** `T-0082-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0082/direction.md`, `docs/tickets/T-0082/spec.md`
- **Size:** about 150 production lines (`verify-gate.sh` about 70, `verify-gate.ps1` about 75, `verify_record.py` about 5).
- **Harness:** yes. Every production path is a review/gate harness path (`verify-gate.sh`, `verify-gate.ps1`, `verify_record.py`, `plugin/crew/tests/sabotage_tooling.py`), so this lands alone as a tooling-only PR. Tests, docs, version files and the code map may ride along; no feature code may.

## Dependencies and work order

Must land first (all have):

| Ticket | State | Why |
|---|---|---|
| T-0087 | merged | The tooling-PRs-land-alone rule and the harness list this ticket lands under. |
| L-0513 | done | `scripts/gate-runner.py` already treats the gate's own death as could-not-tell; this ticket does not touch the runner. |
| L-0572 | done | Coverage credit reads `STATUS_AT` and accepts only `pass`; the new `unknown` status relies on that. |
| T-0076 | done | Owns the `uv-install.sh` hang that produced the original report. |
| T-0077 | merged | The lane whose native Windows gate run reported the problem. |
| L-0555 | done | The CI receipt (`ci_receipt.py`). `GATE_IMPL` means this branch must pass the gate locally. |

L-0555 is listed as a dependency in the ticket facts but not in the spec's "must land first" list; the spec names it only in Evidence and Unknowns. It is done either way, so nothing is waiting.

Nothing blocks this ticket. It can be worked now.

This ticket blocks:
- L-0673 (child 1): reads the `COULD NOT TELL` line this ticket creates.
- L-0674 (child 2): adds one reason to this ticket's decision table. Also on hold for an owner go.
- L-0618 (direction): its QA standard 23 cites this ticket as the gate twin.

Family order:
1. T-0082 (this ticket, tooling-only PR)
2. L-0673 (feature PR), after T-0082 has merged
3. L-0674 (tooling-only PR), after T-0082 has merged AND the owner says go. L-0673 and L-0674 do not depend on each other.

Related, same files, no order forced: T-0068, T-0095, T-0080 (also edits the sabotage harness), L-0618. Whichever lands second merges main and re-checks its anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md is not published. No plan.md existed for this ticket; the implementing session writes the plan.
- The design in the spec (completion record, one decision table in both flavours) is a default the owner has not confirmed. See the open questions.
- The spec requires a native Windows run of the new test file before review, including the case "the rule's process is ended by a native kill". The original Windows result (a pass after a native kill) was not reproduced on Linux. Whether a cloud session can get that Windows run: could not tell.
- Do not edit `plugin/crew/tests/sabotage.py` (at the pylint module line limit). New mutations go in `sabotage_tooling.py`.
- No timeout, deadline or watchdog here (that is L-0674), and no change to `ci_receipt.py` or `commands/verify.md` (that is L-0673; they are outside the harness list and cannot ride in this PR).
- Because the branch changes `verify-gate.sh` and `verify_record.py`, `ci_receipt.check` refuses a CI receipt for it. The branch must pass the gate locally.
- A new test file must be added to the gate's own rule in `.crew/verify.json` (the `run` list names its test files one by one).
- The direction file carries two older owner decisions that still apply: catch up with main by merge, never rebase; and run the suites with `-n 4` through the heavy-run wrapper.

## Open questions for the owner (recommended option taken)

1. Design: positive completion record (taken), or label-only (print "could not tell" when the status is above 128, leaving a kill that reports 0 as a pass)?
2. A rule's own exit status above 128 prints "could not tell" instead of a plain failure (it fails either way). Accept (taken), or call only a missing record unknown?
3. Should a signalled gate exit 2 so the Stop hook blocks the turn, instead of 128+N? Taken: keep 128+N; the marker not advancing covers it.
4. Build L-0674 (a gate-owned deadline for a hung rule) at all, given the crew 1.0.21 descope of process kill? Taken: hold.
5. Confirm a Windows machine is available for the native run the spec requires before review.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0082/` in the final PR unless the owner wants it kept.

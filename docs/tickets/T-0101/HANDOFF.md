# Cloud handoff: T-0101

**The review prompt says when a missing verify pass is a recorded override**

INDEX title (older than the spec): "review prompt's receipts block says 'not yet run (gate follows review)' instead of MISSING before a ticket reaches gate, so reviewers stop BLOCKing on the lifecycle's own order (T-0085 r1 standards proposal #1, owner-accepted 2026-09-28)". The spec dropped that wording and narrowed the ticket; see below.

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** new (the INDEX row was not updated; spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Priority:** med
- **Branch:** `T-0101-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0101/direction.md`, `docs/tickets/T-0101/spec.md`
- **Size:** about 12 added production lines, all in `plugin/crew/hooks/scripts/review_prompt.py` (one module constant, one `out.append`, docstring lines).
- **Harness:** yes. `review_prompt.py` and `plugin/crew/tests/sabotage_review.py` are review/gate harness paths, so this lands alone as a tooling-only PR. Every other Touch path is in `ALONGSIDE`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| Gate first, commit `ce4c951a` (PR #264, no ticket id) | merged 2026-09-29 | The refusal that the new prompt line describes. |
| T-0085 | merged | The source of the finding, and of GEN-12 and the standards checklist in the prompt. |
| T-0087 | merged | The tooling-PR rule, golden replay and canary this PR runs under. Its round 4 is the evidence that the BLOCK still happens after gate first. |
| T-0100 | INDEX says approved; merged on origin/main as PR #371 (`155fe6d8`) | Last change to `review_prompt.py`'s receipts block. The spec's line numbers are from after it. |
| L-0574 | done | The pre-review checks share exit 5 and `--allow-unverified`. The new line covers the gate override only. |

Everything above is already on origin/main. Nothing open blocks this ticket and it blocks nothing. It can be worked at any time.

Related, no ordering: T-0033 and L-0522 (review receipts; they do not touch `review_prompt.py`'s receipts block).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- **Build the spec, not the top of direction.md.** The first half of direction.md (Problem, Direction, Open questions) is the original 2026-09-28 ask. Its premise, that the gate runs after review, is false on main since gate first. Its "Direction check 2026-10-04" section and spec.md replace it: the wording `not yet run (gate follows review)` is dropped, and no ticket-state lookup is built.
- The change is one fixed line in the not-accepted branch of `_receipts_block`. The `MISSING` line, the `NOT been through the gate` line and the `Gate answer for HEAD` line are not reworded, reordered or removed. UNKNOWN stays UNKNOWN.
- The line is never printed when the gate is accepted (clean pass at HEAD, local VERIFIED, NO_GATE, or a CI receipt VERIFIED).
- No edit to `review_run.py`, `review_gate.py`, `review_ledger.py`, `ci_receipt.py`, `plugin/crew/commands/review.md`, `plugin/crew/skills/**` or `plugin/crew/tests/sabotage.py`. No golden file is edited.
- The exact sentence is settled at implement time; the spec has a proposed text and the tests pin only four tokens and that it is one line.
- The two "Owner decision 2026-09-30" sections in direction.md (merge main, never rebase; suites at `-n 4` through a heavy-run wrapper) were written for local lanes. The merge-never-rebase rule still applies. The wrapper is a local tool and is not in the repo; whether a cloud session needs an equivalent could not be told.
- Nothing was run when the spec was written (no pytest, sabotage or gate).

## Open questions for the owner (recommended option taken)

1. Build the narrowed fix. Alternative: close T-0101 as superseded by gate first (`ce4c951a`) and GEN-12, and accept that an override round always carries one BLOCK the owner accepts by hand.
2. The new line tells the reviewer not to report the missing pass on its own. Alternative: only state the facts and leave the severity to the reviewer. GEN-12 treats a missing pass as a real finding for an author.
3. `MISSING: no .crew/.verify-gate.record.json` also prints on a VERIFIED tree. Does that label need its own ticket? Left out of this spec.
4. INDEX still lists T-0101 as "new" and T-0100 as "approved" although T-0100 is merged on origin/main (PR #371). INDEX was not edited.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0101/` in the final PR unless the owner wants it kept.

# R-P4b: Money ledger and reservations: atomic reserve before dispatch, release only by reconciliation

Status: blocked: waits for R-P1.
Phase: Phase 5 — Plan of record (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-P1
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
the action that would pass a cap is refused; a race for the last of a cap has one winner; could-not-tell keeps the reservation

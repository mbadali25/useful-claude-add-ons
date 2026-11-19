# R-B2: Broker install and enrolment as a planned step, both install scripts untouched; removal path

Status: blocked: waits for R-B1.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: S
Model tier: Sonnet 5.5
Depends on: R-B1
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
install reports "already installed" on a second run; without it production writes go to the pipeline only

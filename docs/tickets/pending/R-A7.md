# R-A7: Admin need record and checks per reason code on provider evidence, exact operations with payload digests; report-only

Status: blocked: waits for R-A1, R-A2, R-P6.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-A1, R-A2, R-P6
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a probe that cannot tell is not a need; a conforming name or empty registry is not evidence; a need outside a plan of record is refused except the grantable-profile case

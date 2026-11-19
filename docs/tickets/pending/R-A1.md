# R-A1: Account registry, naming convention, workspace enrolment (checkout or authenticated CI workload), tier map references; existing `unattendedCloud` rows migrated

Status: blocked: waits for R-05, R-32.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-05, R-32
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a second checkout with the same remote is refused; a name off the convention is rejected

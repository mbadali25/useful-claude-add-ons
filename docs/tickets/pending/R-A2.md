# R-A2: Permission profiles and `crew_accounts.py verify`, AWS: effective permissions including inherited ones equal the profile; checked at issuance

Status: blocked: waits for R-A1.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-A1
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
drift, an inherited extra right and a write right on a read account give FAIL; an account not made from a profile gives COULD-NOT-TELL; neither is ever issued

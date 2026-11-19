# R-A6: Issuing read and dev and QA write credentials to a child: references, environment or `credential_process`, redactor on everything published

Status: blocked: waits for R-A1, R-A2, R-33.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-A1, R-A2, R-33
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
no credential in arguments; a credential planted in child stderr, a subprocess argument and an evidence post is caught before publication; nothing issued on FAIL or COULD-NOT-TELL

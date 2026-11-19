# R-AA: Temporary accounts: provider-enforced expiry, or broker-held credential refused after the deadline; sweep as clean-up from `/crew:status`, the pipeline and the broker timer

Status: blocked: waits for R-37, R-A1, R-A8b.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-37, R-A1, R-A8b
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
with the sweep switched off, an expired account and a credential issued before expiry do not work

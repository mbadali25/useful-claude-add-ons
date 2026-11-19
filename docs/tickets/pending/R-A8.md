# R-A8: Admin operations through the broker, AWS: each mechanism verified against the provider first; time box, source identity, session policy, permissions boundary; one operation per request with its payload digest

Status: blocked: waits for R-A7, R-B1, R-P8.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-A7, R-B1, R-P8
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
the right principal with a different policy, boundary or trust is refused; second use refused; an operation outside the list fails at the provider

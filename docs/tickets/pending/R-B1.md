# R-B1: `crew-broker`: local service under its own OS account, closed request protocol (one action of a plan, one operation of a need), no request that returns a credential; same-user fallback marked weak

Status: blocked: waits for R-A1, R-P8, R-43.
Phase: Phase 6 — Service accounts and admin use (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-A1, R-P8, R-43
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a request for a credential is refused; a second write needs its own request and checks; the session's user cannot read the broker's references

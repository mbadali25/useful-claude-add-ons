# R-P1: Plan-of-record template and validator (`crew_planrecord.py`): sections, research labels, typed operations (`payment`, `account-create`, `admin-identity-op`), per-kind envelope fields, exact-only kinds, generated Accounts, Permissions and Money views, expiry

Status: blocked: waits for R-30, R-P6.
Phase: Phase 5 — Plan of record (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-30, R-P6
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a missing section, a crossing wildcard, a free-text dispatch input, an unpinned dependency and an envelope on an exact-only kind are rejected; an execution matching zero or two actions refuses

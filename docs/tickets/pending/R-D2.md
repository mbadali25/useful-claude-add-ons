# R-D2: Decision classes in `crew_policy.py`: which asks are routine, closed outcomes per class, sticky denials, per-ticket cap

Status: blocked: waits for R-01, R-D1.
Phase: Phase 3 — Modes and the decider (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-01, R-D1
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
serious, one-way and unknown-tier classes are never decider-eligible

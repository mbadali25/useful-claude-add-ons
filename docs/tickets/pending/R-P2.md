# R-P2: The collaboration flow as states with a state record: planner run records (requested and reported model) and the owner's prompt ids, each bound to the draft digest

Status: blocked: waits for R-P1, R-73, R-D1, R-D3.
Phase: Phase 5 — Plan of record (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-P1, R-73, R-D1, R-D3
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a step cannot be skipped; a step done by an ineligible model is refused; a required "could not tell" blocks until accepted by name

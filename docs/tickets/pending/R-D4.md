# R-D4: Switch on: routine asks go to the person (`guided`) or the decider (`directive`)

Status: blocked: waits for R-D5, R-24, R-M1, R-P6, R-M4.
Phase: Phase 3 — Modes and the decider (new in revision 3)
Size: S
Model tier: Opus 5.5
Depends on: R-D5, R-24, R-M1, R-P6, R-M4
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
in `directive`, and in `guided` after a recorded "you decide", the owner inbox holds only one-way and plan items; in `guided` without it, routine questions wait for the person

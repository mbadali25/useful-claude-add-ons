# R-M4: Parity suite: one table run under both modes, ask rows followed through to the final grant and execution

Status: blocked: waits for R-M1, R-D2.
Phase: Phase 3 — Modes and the decider (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-M1, R-D2
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
every non-ask row gives the same outcome; the same answered request ends in the same grant ceiling and the same execution in both modes; a planted mode-dependent deny fails the suite

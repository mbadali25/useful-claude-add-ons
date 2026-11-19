# R-D5: Routine records in the approval store and the `decider` approval value in `crew_ticket.py`: one-step reply bound to the one request that was shown, letter required when several are pending, class fixed at request time

Status: blocked: waits for R-23, R-D2.
Phase: Phase 3 — Modes and the decider (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-23, R-D2
Harness-alone: yes. This ticket changes a harness path, so its PR lands alone with no feature work (CLAUDE.md, T-0087).
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a routine record is refused for a serious class; a genuine one-way receipt is refused for unplanned serious work; a bare `yes` with two pending requests mints nothing

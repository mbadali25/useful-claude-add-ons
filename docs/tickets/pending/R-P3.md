# R-P3: Approval of a plan of record in the prompt hook: refuses unless the R-P2 state is complete; structured repeat-back; receipt stored outside the plan, naming the plan digest

Status: blocked: waits for R-23, R-P1, R-P2.
Phase: Phase 5 — Plan of record (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-23, R-P1, R-P2
Harness-alone: yes. This ticket changes a harness path, so its PR lands alone with no feature work (CLAUDE.md, T-0087).
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
digest moved after the repeat-back refuses; decider and autopilot receipts refused; writing the receipt does not change the approved bytes

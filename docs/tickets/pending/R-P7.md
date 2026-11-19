# R-P7: Attestation issued at `confirm` over the plan digest (presence key), or recorded from the owner's forge review

Status: blocked: waits for R-07, R-P3.
Phase: Phase 5 — Plan of record (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-07, R-P3
Harness-alone: yes. This ticket changes a harness path, so its PR lands alone with no feature work (CLAUDE.md, T-0087).
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a receipt with no attestation is not eligible unattended; an attestation for another digest refuses

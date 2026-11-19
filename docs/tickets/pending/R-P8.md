# R-P8: Attestation verification library used by both executors

Status: blocked: waits for R-P7.
Phase: Phase 5 — Plan of record (new in revision 3)
Size: S
Model tier: Opus 5.5
Depends on: R-P7
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a fabricated receipt and hashes with no valid attestation are refused by the pipeline and by the broker

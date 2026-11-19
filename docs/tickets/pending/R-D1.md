# R-D1: `crew_decider.py`: launch with a pinned model, catalog of exact owner-confirmed ids, decision record with requested and reported model id; report-only

Status: blocked: waits for R-06, R-01.
Phase: Phase 3 — Modes and the decider (new in revision 3)
Size: M
Model tier: Opus 5.5
Depends on: R-06, R-01
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
Sonnet, Haiku, an older Opus and a mismatched or missing reported model give no decision

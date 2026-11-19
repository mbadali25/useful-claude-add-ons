# R-C6: Session-start line in `crew_hook.py` that prints a status file other tickets write to, plus the line for a missing or invalid config naming the guide

Status: blocked: waits for R-C5.
Phase: Phase 13 — Configuration guide shipped in the plugin (new in revision 3; starts right after Phase 0)
Size: S
Model tier: Opus 5.5
Depends on: R-C5
Harness-alone: yes. This ticket changes a harness path, so its PR lands alone with no feature work (CLAUDE.md, T-0087).
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
absent when nothing applies; later status lines need no harness change; harness suites pass

# R-C1: Registry completeness: every key has a plain-language line, allowed values, a layer class and its arrival version

Status: done (PR #795).
Phase: Phase 13 — Configuration guide shipped in the plugin (new in revision 3; starts right after Phase 0)
Size: S
Model tier: Sonnet 5.5
Depends on: none
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
a key missing any of the four fails the check

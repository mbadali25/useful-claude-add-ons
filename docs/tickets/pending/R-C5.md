# R-C5: Pointers from crew-setup, `/crew:init`, `/crew:help`, `/crew:config`; `crew_config.py --guide`

Status: blocked: waits for R-C3.
Phase: Phase 13 — Configuration guide shipped in the plugin (new in revision 3; starts right after Phase 0)
Size: S
Model tier: Sonnet 5.5
Depends on: R-C3
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
each surface names the path under `${CLAUDE_PLUGIN_ROOT}`

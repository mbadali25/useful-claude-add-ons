# R-C2: Generator writes `config.blank.json`, `global.blank.json`, `keys.json` and `template.annotated.md` into `plugin/crew/docs/configuration/`; `--check` covers them

Status: blocked: waits for R-C1.
Phase: Phase 13 — Configuration guide shipped in the plugin (new in revision 3; starts right after Phase 0)
Size: M
Model tier: Opus 5.5
Depends on: R-C1
Harness-alone: no (a ticket found at implement time to touch a HARNESS path gets a harness-only PR split off first)
Plan: `docs/plans/crew-revamp-2026-11-18.md` (revision 3, approved by the owner 2026-11-18), section 6. Design for this ticket is in section 4 of that file.

Labels follow the plan: VERIFIED means read or run, INFERRED means reasoned, not run. The acceptance text below is copied from the plan.

## Acceptance criteria
template keys equal registry keys per layer; each exclusion named with a reason; applying a blank to an empty layer leaves the effective policy unchanged; a one-byte edit fails `--check`

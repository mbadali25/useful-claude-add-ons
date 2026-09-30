---
paths:
  - "plugin/crew/**"
  - "_verify/smoke.sh"
  - "scripts/check-marketplace.py"
---
<!-- crew:generated source=.crew/codemap/verification-harness.md sha256=ff0d42a9c2e1a786 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# verification-harness
Code map anchor `a0c171c7`; if it is behind HEAD, re-check with `git diff --name-only a0c171c7..HEAD -- <cited paths>`.
Covers: _verify/smoke.sh, _verify/run-all.sh, scripts/check-marketplace.py, and .crew/verify.json — what each actually runs, and where they overlap or don't. .crew/verify.json is tracked; its own anchor field (:3) is stale at 5238be3d, independent of this note's anchor.
## Entry points
- `.crew/verify.json:169-174` (rule 9) — the whole-suite pytest rule and its 377s pricing.
- `.crew/verify.json:117-127` (rule 6) — the T-0005 cloud-guard suites.
- `.crew/verify.json:184-189` (rule 11) — the T-0026 approval-digest suite.
- `.crew/verify.json:198-202` (rule 13) — the crew-diagrams `render.sh` exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` / `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap, no-pipe fallback refusal.
- `.crew/verify.json:268` (rule 24) — the `.claude/rules/` sync check.
- `.crew/verify.json:269-287` (rule 25) — the T-0008 refresh-check suite; `plugin/crew/tests/sabotage.py:75`, `:3056` — `sabotage_refresh.py`'s registration.
- `.crew/verify.json:289-299` (rule 26) — the T-0006 auto-resume suite; `plugin/crew/tests/sabotage.py:76`, `:3057` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:300-308` (rule 27) — the T-0004/T-0018/T-0072 autopilot suite; `plugin/crew/tests/sabotage.py:77`, `:3057` — `sabotage_autopilot.py`'s registration.
- `.crew/verify.json:309-315` (rule 28) — the T-0010 policy suite; `plugin/crew/tests/sabotage.py:77`, `:3058` register its `POLICY_MUTATIONS`.
- `.crew/verify.json:316-323` (rule 29) — the T-0021 tracker suite; `plugin/crew/tests/sabotage.py:78`, `:3057` — `sabotage_tracker.py`'s registration.
- `.crew/verify.json:324-332` (rule 30) — the T-0023 plain-text routing suite; `plugin/crew/tests/sabotage.py:79`, `:3057` — `sabotage_route.py`'s registration.
- `.crew/verify.json:334-341` (rule 31) — the T-0024 group-approval suite; `plugin/crew/tests/sabotage.py:81`, `:3058` — `sabotage_approval.py`'s registration.
- `.crew/verify.json:342-349` (rule 32) — T-0094's refresh-admission suite, split out of rule 25.
- `.crew/verify.json:371-383` (rule 36) — the T-0085 standards suite; `plugin/crew/tests/sabotage.py:84`, `:3061` — `sabotage_standards.py`'s registration.
- `plugin/crew/hooks/scripts/verify-gate.sh:1493-1502` / `plugin/crew/CONFIG.md:2408-2415` — the descoped per-rule process-group kill, documented as a standing limitation.
- `plugin/crew/hooks/scripts/verify-gate.ps1:825-835`, `:1665-1674` — `Resolve-CrewBash` refusal rather than a re-resolving hang.
Full note: `.crew/codemap/verification-harness.md`.

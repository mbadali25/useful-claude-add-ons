---
paths:
  - "plugin/crew/**"
  - "_verify/smoke.sh"
  - "scripts/check-marketplace.py"
---
<!-- crew:generated source=.crew/codemap/verification-harness.md sha256=5d51e917557de4ab -- do not hand-edit; regenerate with crew_instructions.py rules -->
# verification-harness
Code map anchor `2bb0d198`; if it is behind HEAD, re-check with `git diff --name-only 2bb0d198..HEAD -- <cited paths>`.
Covers: _verify/smoke.sh, _verify/run-all.sh, scripts/check-marketplace.py, and .crew/verify.json — what each actually runs, and where they overlap or don't. .crew/verify.json is tracked; its own anchor field (:3) is stale at 5238be3d, independent of this note's anchor.
## Entry points
- `.crew/verify.json:170-175` (rule 9) — the whole-suite pytest rule and its 377s pricing.
- `.crew/verify.json:117-127` (rule 6) — the T-0005 cloud-guard suites.
- `.crew/verify.json:185-190` (rule 11) — the T-0026 approval-digest suite.
- `.crew/verify.json:199-203` (rule 13) — the crew-diagrams `render.sh` exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` / `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap, no-pipe fallback refusal.
- `.crew/verify.json:269` (rule 24) — the `.claude/rules/` sync check.
- `.crew/verify.json:270-286` (rule 25) — the T-0008 refresh-check suite; `plugin/crew/tests/sabotage.py:75`, `:3054` — `sabotage_refresh.py`'s registration.
- `.crew/verify.json:288-298` (rule 26) — the T-0006 auto-resume suite; `plugin/crew/tests/sabotage.py:76`, `:3055` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:299-307` (rule 27) — the T-0004/T-0018/T-0072 autopilot suite; `plugin/crew/tests/sabotage.py:77`, `:3055` — `sabotage_autopilot.py`'s registration.
- `.crew/verify.json:308-315` (rule 28) — the T-0021 tracker suite; `plugin/crew/tests/sabotage.py:78`, `:3055` — `sabotage_tracker.py`'s registration.
- `.crew/verify.json:316-324` (rule 29) — the T-0023 plain-text routing suite; `plugin/crew/tests/sabotage.py:79`, `:3055` — `sabotage_route.py`'s registration.
- `.crew/verify.json:326-333` (rule 30) — the T-0024 group-approval suite; `plugin/crew/tests/sabotage.py:81`, `:3055` — `sabotage_approval.py`'s registration.
- `plugin/crew/hooks/scripts/verify-gate.sh:1493-1502` / `plugin/crew/CONFIG.md:2373-2380` — the descoped per-rule process-group kill, documented as a standing limitation.
- `plugin/crew/hooks/scripts/verify-gate.ps1:822-832`, `:1665-1674` — `Resolve-CrewBash` refusal rather than a re-resolving hang.
- `scripts/check-marketplace.py:1639` — `main()`, sixteen checks.
- `scripts/check-marketplace.py:518` — `check_versions`.
- `scripts/check-marketplace.py:564`, `:673` — `count_crew_markdown_lines`, `check_self_claims`.
Full note: `.crew/codemap/verification-harness.md`.

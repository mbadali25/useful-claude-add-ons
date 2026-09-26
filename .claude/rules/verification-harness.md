---
paths:
  - "plugin/crew/**"
  - "_verify/smoke.sh"
  - "scripts/check-marketplace.py"
---
<!-- crew:generated source=.crew/codemap/verification-harness.md sha256=47ed9348e079ddd6 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# verification-harness
Code map anchor `c35edda5`; if it is behind HEAD, re-check with `git diff --name-only c35edda5..HEAD -- <cited paths>`.
Covers: _verify/smoke.sh, _verify/run-all.sh, scripts/check-marketplace.py, and .crew/verify.json — what each actually runs, and where they overlap or don't. .crew/verify.json is tracked; its own anchor field (:3) is stale at 5238be3d, independent of this note's anchor.
## Entry points
- `.crew/verify.json:152-157` (rule 8) — the whole-suite pytest rule and its 377s pricing.
- `.crew/verify.json:174-178` (rule 11) — the crew-diagrams `render.sh` exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` / `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap, no-pipe fallback refusal.
- `.crew/verify.json:244` (rule 22) — the `.claude/rules/` sync check.
- `.crew/verify.json:245-261` (rule 23) — the T-0008 refresh-check suite; `plugin/crew/tests/sabotage.py:75`, `:3046` — `sabotage_refresh.py`'s registration.
- `plugin/crew/hooks/scripts/verify-gate.sh:1493-1502` / `plugin/crew/CONFIG.md:1959-1966` — the descoped per-rule process-group kill, documented as a standing limitation.
- `plugin/crew/hooks/scripts/verify-gate.ps1:822-832`, `:1665-1674` — `Resolve-CrewBash` refusal rather than a re-resolving hang.
- `scripts/check-marketplace.py:1639` — `main()`, sixteen checks.
- `scripts/check-marketplace.py:518` — `check_versions`.
- `scripts/check-marketplace.py:564`, `:673` — `count_crew_markdown_lines`, `check_self_claims`.
- `scripts/check_instructions.py:685` — `main()`, nine checks.
- `.github/workflows/instruction-budgets.yml:40-62` — the `github.event.before` base-sha fix for a `push` to `main`.
Full note: `.crew/codemap/verification-harness.md`.

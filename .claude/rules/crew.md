---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/crew.md sha256=354ef1569b616639 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# crew
Code map anchor `fe80f69d`; if it is behind HEAD, re-check with `git diff --name-only fe80f69d..HEAD -- <cited paths>`.
Covers: The crew plugin after 1.0: hooks, the four agents, commands, skills inventory, config layering and leaf counts, and how crew_freshness.py reads this very directory.
## Entry points
- `plugin/crew/hooks/scripts/crew_state.py:999` — `TRIGGERS`, a 15-entry tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2904` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:241` / `:394` — `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2460` — `_RATCHETED`, the 14-key ratchet table (seven construction steps).
- `plugin/crew/hooks/scripts/role_write_guard.py:540` — `classify`, the decision function; `:685` — `main()`.
- `plugin/crew/hooks/scripts/role-write-guard.sh:348` — where the strict private-resolver result feeds the guard's fail-closed fallback.
- `plugin/crew/hooks/scripts/event_claim.py` — no single entry point read this pass beyond the module docstring; called from `notify.sh` and `handoff-write.sh` only.
- `plugin/crew/hooks/scripts/crew_context.py:122` — `load_crew_config`, the one function that reads `crew.json` before `config.json`.
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py` — no single `main()` confirmed at a specific line this pass; called with subcommands (`plan-windows-default`, `apply-migrate`) from the three sites named above.
- `plugin/crew/hooks/scripts/crew_resume.py:668` — `decide`, read-only; `main()` is the `decide` / `record` / `precompact` CLI.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:577` — `ticket_freshness`, the library entry point; `main()` at `:677`.
- `plugin/crew/hooks/scripts/crew_autopilot.py:501` — `next_phase`, read-only; `main()` at `:1226` is the `next` / `resume` / `settings` / `stops` / `route` / `status` / `deploy-allowed` CLI `plugin/crew/commands/autopi...
- `plugin/crew/hooks/scripts/crew_route.py:211` — `decide`, read-only route / ask / none for a prompt; `main()` at `:333` is the `settings` / `decide` CLI.
- `plugin/crew/hooks/scripts/crew_endpoints.py:566` — `declare_endpoint`, the only writer of *declared* records.
Full note: `.crew/codemap/crew.md`.

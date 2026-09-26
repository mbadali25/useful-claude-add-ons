---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/crew.md sha256=e02cb17dc57191d3 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# crew
Code map anchor `d2085450`; if it is behind HEAD, re-check with `git diff --name-only d2085450..HEAD -- <cited paths>`.
Covers: The crew plugin after 1.0: hooks, the four agents, commands, skills inventory, config layering and leaf counts, and how crew_freshness.py reads this very directory.
## Entry points
- `plugin/crew/hooks/scripts/crew_state.py:986` — `TRIGGERS`, a 15-entry tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2883` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:240` / `:374` — `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2418` — `_RATCHETED`, the 14-key ratchet table (six construction steps).
- `plugin/crew/hooks/scripts/role_write_guard.py:539` — `classify`, the decision function; `:684` — `main()`.
- `plugin/crew/hooks/scripts/role-write-guard.sh:348` — where the strict private-resolver result feeds the guard's fail-closed fallback.
- `plugin/crew/hooks/scripts/event_claim.py` — no single entry point read this pass beyond the module docstring; called from `notify.sh` and `handoff-write.sh` only.
- `plugin/crew/hooks/scripts/crew_context.py:121` — `load_crew_config`, the one function that reads `crew.json` before `config.json`.
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py` — no single `main()` confirmed at a specific line this pass; called with subcommands (`plan-windows-default`, `apply-migrate`) from the three sites named above.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:576` — `ticket_freshness`, the library entry point; `main()` at `:676`.
- `plugin/crew/hooks/scripts/crew_endpoints.py:566` — `declare_endpoint`, the only writer of *declared* records.
Full note: `.crew/codemap/crew.md`.

---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/crew.md sha256=e2dda2e4f64c82b6 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# crew
Code map anchor `908c03af`; if it is behind HEAD, re-check with `git diff --name-only 908c03af..HEAD -- <cited paths>`.
Covers: The crew plugin after 1.0: hooks, the four agents, commands, skills inventory, config layering and leaf counts, and how crew_freshness.py reads this very directory.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 5ab63076 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines); re-anchored to 805b0a25 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place); re-anchored to 7ecbdc7f (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only); re-anchored to a9c0d9ab (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place); re-anchored to 083cda66 (L-0516 merges main 64b04c6b (W-0116 #292: crew_refresh_check.py gains the Windows _FINAL_PATH check, test_refresh_admission.py two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place); re-anchored to 908c03af (L-0516 review round 1 fixes: poll_until reads the clock before each probe after the first, test_poll_fixtures.py reaps its children with wait(timeout=10), CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place)
## Entry points
- `plugin/crew/hooks/scripts/crew_state.py:999` — `TRIGGERS`, a 15-entry tuple, unchanged in membership and order from the previous anchor.
- `plugin/crew/hooks/scripts/crew_state.py:2942` — `evaluate_triggers`.
- `plugin/crew/hooks/scripts/crew_config.py:244` / `:397` — `default_config()` / `default_global_config()`.
- `plugin/crew/hooks/scripts/crew_config.py:2498` — `_RATCHETED`, the 14-key ratchet table (seven construction steps).
- `plugin/crew/hooks/scripts/crew_config.py:3093` / `:3119` — `plan_repo_write` / `write_repo_config`, the one repo-layer writer (T-0075); `:2893` / `:2912` — the machine pair.
- `plugin/crew/hooks/scripts/crew_config_files.py:364` — `update_json`, the lock and compare-and-swap both writers stand on (T-0075).
- `plugin/crew/hooks/scripts/crew_config_menu.py:1051` — `main()`, the `spec` / `save` / `delete-repo` / `restore-repo` CLI the `/crew:config` menu calls.
- `plugin/crew/hooks/scripts/role_write_guard.py:540` — `classify`, the decision function; `:685` — `main()`.
- `plugin/crew/hooks/scripts/role-write-guard.sh:348` — where the strict private-resolver result feeds the guard's fail-closed fallback.
- `plugin/crew/hooks/scripts/event_claim.py` — no single entry point read this pass beyond the module docstring; called from `notify.sh` and `handoff-write.sh` only.
- `plugin/crew/hooks/scripts/crew_context.py:122` — `load_crew_config`, the one function that reads `crew.json` before `config.json`.
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py` — no single `main()` confirmed at a specific line this pass; called with subcommands (`plan-windows-default`, `apply-migrate`) from the three sites named above.
- `plugin/crew/hooks/scripts/crew_resume.py:668` — `decide`, read-only; `main()` is the `decide` / `record` / `precompact` CLI.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:1306` — `ticket_freshness`, the library entry point; `main()` at `:1406`; `artifact_verdicts` at `:1013`, the admission judgement (T-0094) that L-0540 wires into the au...
- `plugin/crew/hooks/scripts/crew_autopilot.py:559` — `next_phase`, read-only; `main()` at `:1635` is the `next` / `resume` / `settings` / `stops` / `route` / `status` / `deploy-allowed` / `approve` / `questions-check`...
- `plugin/crew/hooks/scripts/crew_route.py:211` — `decide`, read-only route / ask / none for a prompt; `main()` at `:333` is the `settings` / `decide` CLI.
- `plugin/crew/hooks/scripts/crew_endpoints.py:566` — `declare_endpoint`, the only writer of *declared* records.
Full note: `.crew/codemap/crew.md`.

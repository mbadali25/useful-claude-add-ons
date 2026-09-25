---
paths:
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/crew.md sha256=a36a58670c5a10ba -- do not hand-edit; regenerate with crew_instructions.py rules -->
# crew
Code map anchor `5d1fc5fd`; if it is behind HEAD, re-check with `git diff --name-only 5d1fc5fd..HEAD -- <cited paths>`.
Covers: The crew plugin: hooks, agents, commands, skills inventory, and how crew_state.py reads this very directory.
## Entry points
- `plugin/crew/hooks/scripts/crew_state.py:2891` - `worktree_root(cfg, repo_root)`, the one resolver for `worktree.root`.
- `plugin/crew/hooks/scripts/crew_state.py:2921` - `worktree_path(cfg, repo_root, branch)`, `<worktree_root>/<repo>-<branch>`, flattening every separator so a branch name cannot add a directory level.
- `plugin/crew/hooks/scripts/crew_state.py:3158` - `main`, carrying the `--worktree-path BRANCH` flag.
- `plugin/crew/hooks/scripts/crew_state.py:3049` - `collect`, the one function that assembles the whole state a SessionStart brief renders.
- `plugin/crew/hooks/scripts/crew_state.py:2972` - `evaluate_triggers`, the fifteen-entry `fired` dict.
- `plugin/crew/hooks/scripts/crew_state.py:530` - `read_verify_health`, the source of the three verify triggers.
- `plugin/crew/hooks/scripts/crew_config.py:715` - `resolve_config`, and `:1476` `explain_config`.
- `plugin/crew/hooks/scripts/crew_config.py:620` - `filter_global`, the read-side gate; `:2296` `plan_global_write`, the write-side gate.
- `plugin/crew/hooks/scripts/crew_freshness.py:375` - `read_knowledge`; `:473` `read_diagrams` - both called from `crew_state.collect`.
- `plugin/crew/hooks/scripts/role_write_guard.py:732` — `main()`; `:587` `classify`, the decision function.
- `plugin/crew/hooks/scripts/crew_change.py:278` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/crew_incident.py:416` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/crew_platform.py:481` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/hook_once.py:94` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/pm_brief.py:718` — module entry point (`main()`), moved from `:657`
- `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1018` — cited as a `main()` entry point by the previous anchor; at this anchor that line is inside a string literal.
- `scripts/_test/crew-ignore-policy.py:560` — module entry point (`main()`)
- `scripts/_test/version-drift.py:296` — module entry point (`main()`)
- `scripts/check-marketplace.py:1006` — cited as `main()` by the previous anchor; at this anchor that line is inside `check_crew_ignore_policy` (`:929-1091`).
- `plugin/crew/hooks/scripts/_test/validate-prompts.py:283` and `plugin/crew/hooks/scripts/pm_pulse.py:247` — both cited as `main()` by the previous anchor; both lines now hold other code.
Full note: `.crew/codemap/crew.md`.

---
paths:
  - "plugin/crew/**"
  - "_verify/smoke.sh"
  - "scripts/check-marketplace.py"
---
<!-- crew:generated source=.crew/codemap/verification-harness.md sha256=1537283dbaa94067 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# verification-harness
Code map anchor `5d1fc5fd`; if it is behind HEAD, re-check with `git diff --name-only 5d1fc5fd..HEAD -- <cited paths>`.
Covers: _verify/smoke.sh, _verify/run-all.sh, scripts/check-marketplace.py, and .crew/verify.json — what each actually runs, and where they overlap or don't. .crew/verify.json does not exist; see below.
## Entry points
- `plugin/crew/tests/test_crew_config.py:1491` (moved from `:1488`) — `test_resolve_config_inherits_a_global_through_the_init_template`, the END-TO-END null-shadow test.
- `plugin/crew/tests/test_crew_state.py:1291` (moved from `:1016`) — `test_a_backslash_in_a_branch_name_is_flattened_too`, which catches the `[\/]+` character class that matched `/` alone.
- `plugin/crew/tests/test_crew_state.py:1325` (moved from `:1050`) — `test_two_repos_with_the_same_basename_do_not_share_a_leaf`, the cross-repo worktree collision the security review raised.
- `scripts/check-marketplace.py:929` (moved from `:780`) — `check_crew_ignore_policy`: the `.crew/` ignore-policy gate, sabotage-tested by `scripts/_test/crew-ignore-policy.py` (see above).
- `scripts/check-marketplace.py:579` (moved from `:430`) — `check_self_claims`, whose scope is unchanged beyond the `plugin-skills:<name>` marker type `f9bb78a6` (#169) added (see above).
- `plugin/crew/tests/sabotage.py:3265` (moved from `:2484`) — module entry point (`main()`).
Full note: `.crew/codemap/verification-harness.md`.

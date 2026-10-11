# L-0777 /crew:done waivers (2026-10-11)

- Check 4, diagrams: waived, owner 2026-10-11 (Matthew, via AskUserQuestion, relayed by the coordinator), for
  diagrams already stale on main before PR #600 and not created by it. Redraw ticket: L-0791. The nine:
  data-flow-crew-config-autoclear, data-flow-crew-config-menu, data-flow-crew-config-read,
  data-flow-crew-config-shell-route, data-flow-crew-config-split, data-flow-crew-config-two-files,
  data-flow-crew-config-unattended, data-flow-crew-config-write, process-crew-brief-crew-context.
  Not covered: process-crew-kimi-agent (this ticket's own; re-anchored), data-flow-crew-config and
  data-flow-crew-config-ratchet (L-0789, PR #604).
- Check 4, code maps and graphify-out: L-0764.
- Check 2: environment-blocked on the L-0753 precedent, exactly two failures,
  `test_crew_context_wrappers.py::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false[config0-False]`
  and `[None-False]`, reproduced identically on an origin/main 987ea4fb8 worktree (2026-10-11). rules[28]
  (ai-connect): not run, blocked on L-0790.

## Sabotage on ee19528bf (gate run4, 2026-10-11): 2995 entries, 2961 RED (good), 17 platform-only (win)

Evidence: `.work/tickets/L-0777/gate-ee19528bf/sabotage-nonred.txt` (every line that is not `RED (good)`),
`sabotage-subset17-main-987ea4fb.log` (all 17 labels below re-run on a throwaway worktree of origin/main
987ea4fb8, through heavy-run, with lane A's `sabotage_subset.py`: 17 of 17 the same verdict as on ee19528bf),
`labels17.txt`.

### 12 STILL GREEN = exactly L-0766's closed list of 12 (accepted under L-0766, lead via coordinator, 2026-10-11)

L-0766 direction.md, quoted: "The 12 entries (label, file that defines it):" - each matched to this run's line:

1. the promote gate reads an unparseable map as `not a deployment` (sabotage.py) - STILL GREEN here and on main
2. auto-accept defaults a missing ignored_lines to 0 (sabotage_review.py) - STILL GREEN here and on main
3. the context hook stays silent with memory.inject unset (sabotage_context.py) - STILL GREEN here and on main
4. cloud guard r5: PowerShell never unseen (sabotage_cloud.py) - STILL GREEN here and on main
5. cloud guard r5: PowerShell launchers not read (sabotage_cloud.py) - STILL GREEN here and on main
6. cloud guard r7: a lone quoted PowerShell string read as a program (sabotage_cloud.py) - STILL GREEN here and on main
7. cloud guard r7: PowerShell's colon-bound values not read (sabotage_cloud.py) - STILL GREEN here and on main
8. cloud guard r7: a string piped into Invoke-Expression not read (sabotage_cloud.py) - STILL GREEN here and on main
9. the scope base record loses its protection (sabotage_scope.py) - STILL GREEN here and on main
10. the marker's shape check is dropped (sabotage_limit_worktree.py) - STILL GREEN here and on main
11. a round of true passes for round 1 (sabotage_limit_worktree.py) - STILL GREEN here and on main
12. sabotage bound: a timed-out entry counts as RED (sabotage_tooling.py) - STILL GREEN here and on main

None of this run's 12 STILL GREEN lines is outside that list.

### 5 RED BUT UNPROVEN: reproduced on main 987ea4fb8; accepted by the owner 2026-10-11, follow-up L-0766

Decision as relayed to this lane (not seen first-hand): Matthew, 2026-10-11, through AskUserQuestion, relayed by
the lead, then by coordinator ac5b48330c1347c0d. Accepted on #600 as pre-existing on main 987ea4fb with the
per-entry facts below; added to L-0766 direction.md ("Added 2026-10-11") to be repaired or retired with the 12.
Evidence: `.work/tickets/L-0777/gate-ee19528bf/sabotage-nonred.txt`, `sabotage-subset17-main-987ea4fb.log`.

- `RED BUT UNPROVEN -- exit 4, not a test failure the deploy default is all` - mutates crew_state.py
  (`AUTOPILOT_DEFAULTS` line), target `tests/test_crew_autopilot_deploy.py::test_deploy_only_in_machine_layer_reads_none`.
  No test of that name exists under plugin/crew/tests. #600 changes crew_state.py but not the `AUTOPILOT_DEFAULTS`
  line; it does not touch the test file or the entry.
- `RED BUT UNPROVEN -- exit 4, not a test failure approve writes beside the receipt` - mutates crew_autopilot.py,
  target `tests/test_crew_autopilot_policy.py::test_approve_is_the_only_writing_subcommand`. #600 touches none of
  the mutated file, the test or the entry.
- `RED BUT UNPROVEN -- exit 1, partial: 2 skipped the gate does not export CLAUDE_PLUGIN_ROOT to its rule commands`
- `RED BUT UNPROVEN -- exit 1, partial: 1 skipped the gate replaces a CLAUDE_PLUGIN_ROOT its caller set`
- `RED BUT UNPROVEN -- exit 1, partial: 2 skipped the gate keeps an empty CLAUDE_PLUGIN_ROOT`
  All three mutate verify-gate.sh, targets in `tests/test_verify_gate_plugin_root.py`. #600 touches none of the
  mutated file, the tests or the entries.

## pytest-combined path note

The log prints the two failure ids as `plugin/gizmoduck/test_crew_context_wrappers.py::...` because the step
runs with `-c plugin/gizmoduck/pytest.ini --rootdir plugin/gizmoduck`. No such file exists under plugin/gizmoduck;
the tracebacks read `plugin/crew/tests/test_crew_context_wrappers.py:89: AssertionError`.

## WIND-DOWN STATE 2026-10-11 15:05 CDT (session moving to another computer)

- Branch L-0777-kimi-agents, local head = pushed head = 46d015a35. Worktree clean. NOT merged.
- origin/main moved to a656ef84f (#605 merged) after 46d015a35 was pushed, so #600 is CONFLICTING again
  (CHANGELOG.md and README.md only, by `git merge-tree`). 46d015a35 is therefore NOT the final head.
- gate-runner on 46d015a35 (finished about 14:55 CDT; summary in `gate-46d015a35/`): overall FAIL, 44 PASS,
  2 FAIL, 0 SKIP ("all 46 steps of the repo gate ran; none SKIPPED").
  - pytest-combined: `2 failed, 20992 passed, 283 skipped`, the two test_crew_context_wrappers cases.
  - wallclock: `74 passed, 6 skipped`.
  - sabotage: 2985 RED (good); the non-red set is identical to the ee19528bf run (12 STILL GREEN, 5 RED BUT
    UNPROVEN, 17 platform-only), so no verdict differs and no re-run under quiet load was needed. The run
    overlapped the 14:13-14:22 and 14:36-14:47 CDT load windows.
  - mcp-servers-npm-test: PASS.
- NOT run on any head: a true `verify-gate.sh --all` (check 2 reads its record, not gate-runner's), the separate
  wallclock pytest for it, rules[28] (ai-connect), /crew:done on a post-merge head.
- Next step for whoever resumes: fetch; merge origin/main again (bookkeeping only; re-check the next free crew
  version, 1.2.33 was free at 13:10 CDT); re-anchor process-crew-kimi-agent only if a cited file moved; push;
  CI green on the new head; gate-runner, then `verify-gate.sh --all` in lane B1's form after
  `npm --prefix mcp-servers ci`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock`; rules[28] by the
  coordinator's procedure; /crew:done; wait for the coordinator's go. If data-flow-crew-config and -ratchet
  are still listed by check 4 and #604 has not merged, add them here with #604 named beside L-0791.

## Post-accept commits (merges, bumps, refreshes only)

- b1cb69ec3: merge origin/main 987ea4fb8, crew 1.2.33. Hand resolutions in marketplace.json, plugin.json,
  PLUGINS.md, CHANGELOG.md, README.md (regenerated), BUDGETS.md (re-measured 27,832 / 139) only.
- 46d015a35: process-crew-kimi-agent header sha 932e4c3b -> b1cb69ec, no other byte.
- mcp-servers-npm-test on ee19528bf after `npm ci`: PASS (69 tests, 0 fail).

Check 1 (receipt accepted on bundle 941c8b78a4c0 at ee19528bf): standing staleness waiver, measured 2026-10-11:

- `git diff --name-only 46d015a35^ 46d015a35`: docs/diagrams/process-crew-kimi-agent.mmd only.
- `git show --remerge-diff b1cb69ec3 --name-only`: .claude-plugin/marketplace.json, CHANGELOG.md, README.md,
  plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json, plugin/crew/BUDGETS.md. No code or test file is
  among these hand-resolved paths. Everything else in the merge came from main unedited.
- The PR's own delta is unchanged since the accept: all 14 of its code, test, agent, command and skill files
  are the same blob at ee19528bf and 46d015a35 (crew_config.py, crew_kimi_agent.py, crew_state.py, kimi_probe.py,
  kimi_fixtures.py, test_crew_kimi_agent.py, test_kimi_agent_routing.py, test_provider_table.py, agents/explorer.md,
  agents/researcher.md, agents/security.md, commands/model.md, crew-providers/SKILL.md,
  crew-providers/alternative-providers.md).

## CI on 46d015a35: one unexplained failure, then green on re-run (2026-10-11)

- First attempt: `Pytest / test (3.12)` failed, run 38162614845 job 114538511973, one test:
  `test_promote_gate_literal_match.py::test_both_flavours_pick_the_same_environment[map0]`, "'deploy target=prod':
  promote-gate.sh chose qa,production, promote-gate.ps1 chose BLOCKED qa,production". ONE UNEXPLAINED occurrence
  on 46d015a35. Not cleared, not shown to be flaky. `test (3.11)` and `test (3.13)` passed on the same sha.
- Saved logs (main checkout and lane worktree): `.work/tickets/L-0777/evidence/ci-run38162614845-job114538511973-attempt1.log`
  and `...-attempt1-failed.log`.
- Re-run: `gh run rerun 38162614845 --failed`, started 14:31:55 CDT by the coordinator; new job 114555708928
  passed. #600 then showed 30 pass, verify-gate skipping.
- #600's diff has no promote-gate path. Follow-up: L-0793 (timing-fragile tests).

Lane A's measurement on bdc7bc55 for two of the five RED BUT UNPROVEN: `the deploy default is all` has a dangling
target (the test was renamed to `test_deploy_only_in_machine_layer_is_the_default_since_t0050`); `approve writes
beside the receipt` exits 4 because its mutation produces a SyntaxError in crew_autopilot.py (a line inserted
between a `try:` body and its `finally:`), so the red is a collection error.

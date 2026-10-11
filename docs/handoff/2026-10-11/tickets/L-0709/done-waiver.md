# L-0709 /crew:done waivers and evidence (PR #584)

Head bdc7bc55ae1de17b3c7620571c08d45d1054832d (crew 1.2.32), worktree /repos/personal/uca-L-0709, clean.
origin/main 987ea4fb89087bfe35fcc5f2883ba37fd69d26ba. Written 2026-10-11 by lane A. Nothing here is a merge approval.
Rulings quoted below were relayed by coordinator ac5b48330c1347c0d (lead's rulings, 2026-10-11) and are for use only
after #605 (L-0790) has landed and rules[28] has run on #584's final head (how it runs: owner decision 2 below, which
replaced the earlier "as nobody").

## WIND-DOWN 2026-10-11 15:00 CDT: the head moved; everything below was measured on bdc7bc55, not on the new head

- New head 344dd3a6e85a06d4dfc0eef7adafb02d808158aa, pushed 15:00 CDT: merge of origin/main a656ef84 (#605, L-0790,
  ai-connect 0.1.5). Hand-resolved (`git show --remerge-diff --name-only`): CHANGELOG.md (both entries kept), README.md
  (main's file, then scripts/sync-updates.py). No code or test file. plugin/ai-connect is identical to main.
  check-marketplace: `all checks passed`. crew stays 1.2.32 (main 1.2.30; #597 holds 1.2.31).
- NOT done on 344dd3a6: CI not read; no gate of any kind; rules[28] not run (no venv built, nothing installed, the
  ai-connect suite was not run as root); `npm --prefix mcp-servers ci` not run; /crew:done not run; check 4 not re-run.
- Stopped here on the coordinator's instruction (session moving to another computer). Next step for whoever resumes:
  confirm CI green on 344dd3a6; `npm --prefix mcp-servers ci`; build the rules[28] venv per owner decision 2 below and do
  the first root run of rules[28] ALONE with the ufw files saved and diffed and the journal checked; report; then the
  true `verify-gate.sh --all`; /crew:done; re-measure this file for the new head; coordinator's go before any merge.

## Owner decisions 2026-10-11 (Matthew, through AskUserQuestion; relayed lead -> coordinator ac5b48330c1347c0d -> lane A)

Recorded here as relayed; lane A did not hear either from the owner directly.

1. The five RED BUT UNPROVEN sabotage entries: accepted on #584 as pre-existing on main 987ea4fb, with the per-entry
   facts below; follow-up L-0766 (.work/tickets/L-0766/direction.md, section "Added 2026-10-11"), to be repaired or
   retired with its 12 in a harness-only PR later.
2. rules[28] (ai-connect) after #605 merges: run as root with a venv. Only after #605 is on main AND #584 has merged
   main. The venv is built from plugin/ai-connect/requirements.txt and requirements-dev.txt, outside the worktrees (for
   example under /root/crew-tmp/), nothing installed into system python, its bin first on PATH so the true `--all` gate
   runs rules[28]. /root/crew-tmp/l-0768/aic-venv is not reused. For the first such run: save /etc/ufw/user.rules and
   /etc/ufw/user6.rules before, diff them after, and check the journal for any sudo or ufw line during the run; if
   anything touched the firewall, stop everything and tell the coordinator at once.
   NOT STARTED. Nothing starts until the coordinator says #605 has merged.

## Checks 1 and 3: receipt stale after the accept (standing staleness waiver, owner 2026-10-03)

- Receipt: round 6, Codex gpt-6-sol, FINDINGS 0 BLOCK / 1 FIX / 1 NIT, owner-accepted 2026-10-10T09:14:12+00:00 by
  Matthew Badali, bundle eef049089f63, head 6fca4d1c.
- `review_ledger.py --root . --ticket L-0709 --check-receipt` on bdc7bc55, rc 1, verbatim: `review-ledger: receipt is
  stale: round 6 accepted bundle eef049089f63, the tree now builds 1af2d5c8f381; the change was edited after review; delta
  gate: could not tell: no train entry binds the integration ref (absent:
  /repos/personal/useful-claude-add-ons/.git/crew/train/state.json does not exist); merged main: 987ea4fb8908 (175 path(s)
  identical to it left out)`
- Non-merge commits after the accept (`git log --first-parent --no-merges 6fca4d1c..bdc7bc55`, 11 of them),
  each with `git diff --name-only <sha>^ <sha>`:
  - bdc7bc55a: .claude-plugin/marketplace.json, CHANGELOG.md, README.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  - 442de382a: plugin/crew/BUDGETS.md
  - bc7e5924a: .claude-plugin/marketplace.json, CHANGELOG.md, README.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  - 5138faace: plugin/crew/BUDGETS.md
  - 37b53eea6: .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  - f9d2f01ec: .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  - 96c7b3d01: plugin/crew/BUDGETS.md
  - 2204dd048: .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  - 4f02942f7: .claude-plugin/marketplace.json, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  - 4744b2d20: CHANGELOG.md, README.md
  - 472222be5: .claude/rules/verification-harness.md
  No .py, .sh, .ps1 or .yml path is among them. The two .json paths are the version files.
  `.claude/rules/verification-harness.md` is a refresh artifact (regenerated from the code map).
- Merges of origin/main after the accept (5), with the hand-resolved paths
  (`git show --remerge-diff --name-only`):
  - f34587258 (main 987ea4fb8): .claude-plugin/marketplace.json, .claude/rules/verification-harness.md, CHANGELOG.md, README.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json, plugin/crew/BUDGETS.md
  - 9d202bb70 (main a192c68e6): none
  - e7e6d89ef (main 2a26b27b9): .claude-plugin/marketplace.json, CHANGELOG.md, README.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json, plugin/crew/BUDGETS.md
  - fd96a6846 (main c972653ad): .claude-plugin/marketplace.json, .claude/rules/verification-harness.md, .crew/codemap/verification-harness.md, CHANGELOG.md, README.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json, plugin/crew/BUDGETS.md
  - 00185636f (main 2b10c0607): .claude-plugin/marketplace.json, CHANGELOG.md, README.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json
  `.claude/rules/verification-harness.md` and `.crew/codemap/verification-harness.md` are refresh artifacts. No code or
  test file was hand-resolved.
- What that does NOT say: `git diff --name-only 6fca4d1c bdc7bc55` over the whole range lists 187 paths, 108 of them
  .py/.sh/.ps1/.yml, because the five merges bring main's own changes in. Those are main's commits, not this lane's.
- The PR's own delta on its code and test files is unchanged since the accept. Five of the six
  (conftest.py, crew_fixtures.py, test_hermetic_home.py, test_review_checks.py, test_upgrade.py) are the same blob at
  6fca4d1c and bdc7bc55. test_ps1_python_probe.py differs as a blob because main changed it (1 commit since merge-base
  d8de3daf) and git merged it without conflict; its own delta has the same `git patch-id --stable` then
  (`git diff d8de3daf 6fca4d1c`) and now (`git diff origin/main bdc7bc55`): f8ab5af96d10. Same for plugin/crew/README.md
  (69d0664e68cf both times; main changed it in 8 commits).
- `git diff --name-only origin/main...bdc7bc55` (17 paths) is inside the spec's Touch list.

### The delta gate line: recorded as could-not-tell, never as pass

- Printed by plugin/crew/hooks/scripts/review_delta.py:318-322, `integration_ref`:
  `state, where, why = crew_train.load(top)` / `if where != "ok": raise Stale(f"{COULD_NOT_TELL}: no train entry binds
  the integration ref ({where}: {why})")`. crew_train.load returns `absent` only for a state.json proven missing;
  /repos/personal/useful-claude-add-ons/.git/crew/train does not exist, so no merge train is in use on this host.
- What it means for a PR not on the train: the delta gate is the only path that can KEEP a receipt whose bundle hash
  changed (review_ledger.py check_receipt: `kept, why, detail = review_delta.judge(...)` / `if not kept: return False,
  f"{stale}; delta gate: {why}..."`). With no train entry it cannot name the integration ref, so it keeps nothing.
- It is not informational: check_receipt returns False and `--check-receipt` exits 1, and commands/done.md check 1
  "Rebuilds the bundle and fails if anything changed since the receipt was written." So /crew:done check 1 REFUSES on
  this head by the tool's own reading. It is not a second failure beside the stale receipt; it is the reason the stale
  receipt was not kept. What stands in for it is the standing staleness waiver above, on the measurements above.
  Lead's ruling, relayed by the coordinator 2026-10-11: this is the ordinary standing staleness waiver case. The waiver
  stands in for check 1 because the receipt could not be kept (no train entry on this host). The line stays
  could-not-tell; this is NOT a kept receipt and is not recorded as one.

## Check 2: gate

- STATUS: NOT SATISFIED. Coordinator, 2026-10-11: a gate-runner run does not satisfy /crew:done check 2
  (commands/done.md check 2 reads the verify-gate record, the GATE marker and the CI receipt, not gate-runner's
  status.json). Owed on the FINAL head, after #605 has landed and main is merged, after `npm --prefix mcp-servers ci`:
  `env -u TMPDIR CLAUDE_PROJECT_DIR=/repos/personal/uca-L-0709 /root/crew-tmp/heavy-run bash
  plugin/crew/hooks/scripts/verify-gate.sh --all </dev/null`; if rules[16]'s first half fails, run
  `python3 -m pytest plugin/crew/tests/ -q -m wallclock` separately. Not run yet. On bdc7bc55 there is no
  .crew/.verify-verified-at marker in the worktree. Everything below is gate-runner evidence only.
- The five RED BUT UNPROVEN entries and rules[28]: see "Owner decisions 2026-10-11" at the top. As of this note nothing
  is installed, no venv is built and the suite has not been run as root.

- CI on bdc7bc55: 30 pass, verify-gate skipping (not a pass).
- Local `python3 scripts/gate-runner.py` on bdc7bc55 via heavy-run: overall FAIL, 46 steps, 45 PASS, 1 FAIL, 0 SKIP.
  Evidence: gate-bdc7bc55/status.json, run.log, sabotage.log.
- The one FAIL: `FAIL sabotage rc=1 secs=4379.0 ... -- exit 1`. `SABOTAGE SUITE: FAIL (17 platform-only, not exercised on
  linux)`: 2991 RED, 17 PLATFORM-ONLY, 16 not RED (11 STILL GREEN, 5 RED BUT UNPROVEN), 0 timeouts.
- All 16, same labels and same states, come out of an origin/main worktree run with gate-bc7e5924/sabotage_subset.py: at
  987ea4fb (current main, 2026-10-11 13:05 CDT, gate-bdc7bc55/sabotage-subset-main-987ea4fb.log) and earlier at a192c68e
  (gate-bc7e5924/sabotage-subset-main-a192c68e.log). `diff` of state+label lines, timings stripped: identical.

### 11 STILL GREEN: L-0766 form (lead's ruling 2026-10-11, with the 987ea4fb evidence)

- L-0766 direction.md, quoted: "`plugin/crew/tests/sabotage.py` in the local gate at L-0753 head `1b4c8f8f` [...]
  reported `SABOTAGE SUITE: FAIL` with 12 entries `STILL GREEN -- TEST IS VACUOUS`. Exactly those 12 entries were re-run
  on a clean origin/main `d8de3daf` worktree [...] and all 12 stayed green there too." Its list, quoted: "1. the promote
  gate reads an unparseable map as `not a deployment` 2. auto-accept defaults a missing ignored_lines to 0 3. the context
  hook stays silent with memory.inject unset 4. cloud guard r5: PowerShell never unseen 5. cloud guard r5: PowerShell
  launchers not read 6. cloud guard r7: a lone quoted PowerShell string read as a program 7. cloud guard r7: PowerShell's
  colon-bound values not read 8. cloud guard r7: a string piped into Invoke-Expression not read 9. the scope base record
  loses its protection 10. the marker's shape check is dropped 11. a round of true passes for round 1 12. sabotage bound:
  a timed-out entry counts as RED". Precedent, L-0753 done-waiver.md: "12 sabotage entries STILL GREEN on origin/main
  d8de3daf too (control entries go red): L-0766."
- This PR's 11 are that list minus #3. #3 is `RED (good)` here (gate-bdc7bc55/sabotage.log line 452), as L-0766's
  Unknowns expected ("very likely the host `~/.claude/crew/config.json` leak that L-0709 removes").
- Verbatim, main 987ea4fb:

```
STILL GREEN -- TEST IS VACUOUS           the promote gate reads an unparseable map as `not a deployment` [0.7s]
STILL GREEN -- TEST IS VACUOUS           auto-accept defaults a missing ignored_lines to 0 [0.8s]
STILL GREEN -- TEST IS VACUOUS           cloud guard r5: PowerShell never unseen [0.6s]
STILL GREEN -- TEST IS VACUOUS           cloud guard r5: PowerShell launchers not read [0.7s]
STILL GREEN -- TEST IS VACUOUS           cloud guard r7: a lone quoted PowerShell string read as a program [0.7s]
STILL GREEN -- TEST IS VACUOUS           cloud guard r7: PowerShell's colon-bound values not read [0.7s]
STILL GREEN -- TEST IS VACUOUS           cloud guard r7: a string piped into Invoke-Expression not read [0.7s]
STILL GREEN -- TEST IS VACUOUS           the scope base record loses its protection [0.7s]
STILL GREEN -- TEST IS VACUOUS           the marker's shape check is dropped [2.5s]
STILL GREEN -- TEST IS VACUOUS           a round of true passes for round 1 [1.0s]
STILL GREEN -- TEST IS VACUOUS           sabotage bound: a timed-out entry counts as RED [0.4s]
```

### 5 RED BUT UNPROVEN: reproduced on main 987ea4fb; accepted by the owner 2026-10-11, follow-up L-0766

- Accepted by the owner 2026-10-11 (decision 1 at the top, as relayed). They were not in L-0766's original list of 12;
  the coordinator added them to L-0766 in its section "Added 2026-10-11".
- Before that decision, no ticket or owner-accepted waiver naming these five was found. L-0766 and L-0753's waiver list STILL GREEN entries
  only. A grep of .work/tickets and HANDOFF.md for the five labels and "RED BUT UNPROVEN" hits older specs and evidence
  (L-0510, L-0516, L-0525, L-0557, L-0564, L-0621, L-0682, T-0046, T-0049, T-0072, T-0080, T-0090, T-0094; the list was
  cut at 20 files) and lane D's L-0777/gate-ee19528bf files. Those hits were not read in full, so "none found" is a
  search result, not a proof that none exists.
- #584's diff touches none of the mutated files (crew_state.py, crew_autopilot.py, verify-gate.sh), none of the target
  tests (test_crew_autopilot_deploy.py, test_crew_autopilot_policy.py, test_verify_gate_plugin_root.py) and no
  sabotage*.py file (`git diff --name-only origin/main...bdc7bc55 -- <those paths>`: empty).
- Verbatim, main 987ea4fb:

```
RED BUT UNPROVEN -- exit 4, not a test failure the deploy default is all [0.6s]
RED BUT UNPROVEN -- exit 4, not a test failure approve writes beside the receipt [0.6s]
RED BUT UNPROVEN -- exit 1, partial: 2 skipped the gate does not export CLAUDE_PLUGIN_ROOT to its rule commands [1.8s]
RED BUT UNPROVEN -- exit 1, partial: 1 skipped the gate replaces a CLAUDE_PLUGIN_ROOT its caller set [1.1s]
RED BUT UNPROVEN -- exit 1, partial: 2 skipped the gate keeps an empty CLAUDE_PLUGIN_ROOT [1.9s]
```

- Why, per entry (measured on bdc7bc55, tree clean after):
  1. `the deploy default is all` (sabotage_autopilot.py:221-224): its target id
     `tests/test_crew_autopilot_deploy.py::test_deploy_only_in_machine_layer_reads_none` does not exist; the function at
     test_crew_autopilot_deploy.py:673 is `test_deploy_only_in_machine_layer_is_the_default_since_t0050`. Unmutated,
     pytest prints `(no match in any of [<Module test_crew_autopilot_deploy.py>])` and `no tests ran`, so the entry
     exits 4 whatever the mutation does. A dangling target.
  2. `approve writes beside the receipt` (sabotage_autopilot.py:856): the target test exists and passes unmutated
     (`1 passed`). The mutation inserts an `open(...)` line between the `try:` body and its `finally:` in
     crew_autopilot.py; compiling the mutated text gives `SyntaxError: expected 'except' or 'finally' block
     (crew_autopilot.py, line 2392)`. So the red is an import/collection error (exit 4), not the test's assertion.
  3-5. The three CLAUDE_PLUGIN_ROOT entries (sabotage_tooling.py:654 on; verify-gate.sh mutated; targets in
     test_verify_gate_plugin_root.py): each target is parametrized over the sh and ps1 gates. Unmutated on Linux the
     file gives `4 passed, 3 skipped`, with `SKIPPED [2] tests/test_verify_gate_plugin_root.py:81: the .ps1 gate is the
     native-Windows flavour` and `SKIPPED [1] tests/test_verify_gate_plugin_root.py:110: the .ps1 gate is the
     native-Windows flavour`. Under the mutation the run exits 1 with the ps1 case(s) skipped, hence
     `partial: N skipped`: the sh half goes red, the ps1 half cannot be exercised on Linux.

### Not run

- verify.json rules[28] (ai-connect): not run; blocked on L-0790 (#605) landing, then run per owner decision 2 at the top.
  fastmcp is not importable here and gate-runner's table has no ai-connect step.
- scripts/_test/drift-detection.sh (needs the real claude CLI).
- The 17 PLATFORM-ONLY sabotage entries were not exercised on linux.

### The two on-main failures this PR removes

- On bdc7bc55, `python3 -m pytest plugin/crew/tests/test_crew_context_wrappers.py -v -p no:cacheprovider -k
  "inject_is_false"`:
  `...::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false[config0-False] PASSED`,
  `...::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false[None-False] PASSED`,
  `2 passed, 20 deselected in 1.37s`. pytest-combined in the gate: `20936 passed, 283 skipped, 14 subtests passed in
  1347.17s (0:22:27)`. Run as root with the host's ~/.claude/crew/config.json in place. Not re-run on main by this lane.

## Check 4: code maps and graph stale -> L-0764. Diagrams: no diagram lines.

- `crew_refresh_check.py --root . --ticket L-0709` on bdc7bc55, tree clean before and after, rc 1 (check4-bdc7bc55.txt).
- No diagram lines, so the L-0791 diagram waiver (owner 2026-10-11) has nothing to cover on this PR. No line says "unknown".
- Verbatim:

```
refresh-check L-0709: stale - scope base f3ccccc36fff ((fallback) recorded as the merge-base with origin/main because HEAD was already past it when L-0709 was first recorded here, so the true start is unknown and this shows MORE); changed set: merged origin/main at 987ea4fb8908; paths identical to it are left out
  codemap crew: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh crew
  codemap install-scripts: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh install-scripts
  codemap localgpu: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh localgpu
  codemap marketplace-registration: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh marketplace-registration
  codemap mcp-servers: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh mcp-servers
  codemap obsidian-vault: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh obsidian-vault
  codemap repo-docs: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh repo-docs
  codemap verification-harness: stale - README.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md, plugin/crew/tests/conftest.py (+5 more) changed since its anchor 09e31dba [fallback base]; refresh with /crew:onboard --refresh verification-harness
  graph graphify-out: stale - README.md, VERIFYING.md, plugin/crew/README.md, plugin/crew/skills/crew-qa-standards/references/harness.md (+6 more) changed since its anchor 76b06812aba7; graphify's manifest.json is missing or unreadable, so not usable [fallback base]; refresh with /crew:graph --refresh
  documents: not measured - /crew:docs is judgement
```

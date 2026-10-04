# L-0688 plan            spec: docs/tickets/L-0688/spec.md

Written by the implementing session on 2026-10-04 against origin/main `baf193aa` (crew 1.0.325), under the orchestrator's standing hand-off; the spec's recommended option is taken (HANDOFF.md, open question 1).

Preconditions: T-0094 (#285) and W-0117 (`e51f9db7`) are ancestors of origin/main (checked). Re-checked anchors at `baf193aa`: `_on_disk` at plugin/crew/hooks/scripts/crew_refresh_check.py:786, its diff loop at :821-833, `ls-files -s` at :834-842, the L-0540 docstring sentence at :122-127. No harness path is touched (`scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`). No hook, no config key, no command-file change.

Unknowns settled by real git before step 1 (git 2.x, throwaway repo): after `git rm --cached <rel>` with the file left on disk, BOTH the worktree diff and the `--cached` diff against the base print `:100644 000000 <oid> 0000000 D`. A new file prints `:000000 100644 ... A` once staged and nothing while untracked. So the refusal keys on the `--cached` pass (the index is what `git commit` records) with `old != 000000` and `new == 000000`; a file absent on disk never gets that far (lstat refuses it with `deleted` first).

Crew version: one patch past main, set in the last commit only (placeholder 1.0.397, re-bumped at landing).

### Step 1: tests first, red
Files: plugin/crew/tests/test_refresh_admission.py
Test: python3 -m pytest plugin/crew/tests/test_refresh_admission.py -q -k "removed_from_the_index or new_untracked_rendered or new_staged_artifact"
- [ ] `test_an_artifact_removed_from_the_index_but_left_on_disk_is_refused`, parametrised over map, diagram source and graph file: admitted bytes on disk, `git rm --cached`, verdict `(False, reason naming the index)`. Red on main.
- [ ] must-allow `test_a_new_untracked_rendered_file_beside_its_source_is_still_admitted`: no base copy, no index entry, source re-anchored -> `True` (green on main, stays green)
- [ ] must-allow `test_a_new_staged_artifact_is_still_admitted`: a new rendered file staged (`000000 -> 100644`) -> `True` (green on main, stays green)

### Step 2: the refusal in `_on_disk`
Files: plugin/crew/hooks/scripts/crew_refresh_check.py
Test: python3 -m pytest plugin/crew/tests/test_refresh_admission.py -q; python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_refresh_check.py -q
- [ ] in the `--cached` pass, a record going from a non-zero mode to `000000` returns `(False, "removed from the index, so the commit would delete it ...")`
- [ ] `_on_disk` docstring and the module docstring's `_on_disk` paragraph name the case
- [ ] the "What is admitted without Touch" paragraph stops naming L-0540: `completion_audit.audit` is the caller, its docstring states what it admits (true before and after L-0540)
- [ ] sabotage by hand: remove the refusal, see the step-1 test red, restore with `git checkout --`; record in the PR body (the permanent entry is L-0540's)

### Step 3: docs
Files: plugin/crew/README.md, docs/guides/crew/src/daily-workflow-scope.md, docs/guides/crew/crew-1.0-daily-workflow.{html,docx,pdf}, .crew/codemap/crew.md, .crew/codemap/INDEX.md, CHANGELOG.md, .claude/rules/crew.md (regenerated), graphify-out/** if the background rebuild changes it
- [ ] README and the guide's refusal list name "an artifact removed from the index but left on disk"; rebuild the guide with `python3 docs/guides/crew/src/build.py`
- [ ] codemap: DERIVED cite for the new refusal at HEAD; re-anchor; regenerate rules
- [ ] CHANGELOG entry; delete docs/tickets/L-0688/ in the final content commit

### Step 4: version (last commit, version only)
Files: plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, CHANGELOG.md heading
- [ ] crew 1.0.397 everywhere stated; `python3 scripts/check-marketplace.py` after the commit; verify.json's rule for crew_refresh_check.py; ruff + pylint on changed .py

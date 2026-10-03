# L-0526 plan            spec: .work/tickets/L-0526/spec.md

Cut from origin/main after L-0520's PR 1 merges, in worktree `/repos/personal/uca-l0526` on branch
`L-0526-review-train` (merge main to catch up, never rebase). The work is restored from
`b7fe895a` file by file against the new main and re-read, never copied blind. Heavy commands run
through `/root/crew-tmp/heavy-run` with `TMPDIR=/root/crew-tmp/l-0520`.

### Step 1: the gate round takes the train (`review_run.py` exit 6)
Files: plugin/crew/hooks/scripts/review_run.py, plugin/crew/tests/test_review_run_train.py, plugin/crew/tests/test_crew_train.py
Where: restore `test_review_run_train.py` from `b7fe895a` and see it RED on main; then add `EXIT_TRAIN = 6`, `train_gate`, `preflight` = `_receipt_and_gate` then `train_gate`, the docstring's question 3 and exit codes, keeping T-0087's docstring; `test_crew_train.py`'s structural test back to equality
Test: `python3 -m pytest plugin/crew/tests/test_review_run_train.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_crew_train.py -q`
Risk: high - a new refusal in the review path; an unarmed clone must be unchanged and any failure must refuse, never reserve
Standards: GEN
- [ ] Tests first (RED), then the code, then green.

### Step 2: the reviewer's rerere block
Files: plugin/crew/hooks/scripts/review_prompt.py, plugin/crew/tests/test_review_prompt.py
Where: restore the three catch-up tests (RED), then `_catch_up_block` in `build`'s tuple before the standards checklist
Test: `python3 -m pytest plugin/crew/tests/test_review_prompt.py -q`
Risk: med - a missing block hides a replayed resolution from the reviewer
Standards: GEN
- [ ] Tests first, then the code.

### Step 3: sabotage rows S1-S19
Files: plugin/crew/tests/sabotage_train.py, plugin/crew/tests/sabotage.py
Where: restore `sabotage_train.py` and append S16-S19 from `/root/crew-tmp/l-0520/tools/s16_s19.py` (anchors re-read against the merged crew_train.py); register `TRAIN_MUTATIONS` in `sabotage.py`; every anchor re-checked unique on the new tree
Test: `python3 plugin/crew/tests/sabotage.py` through heavy-run; every S row RED
Risk: med - a lost anchor is a harness error, not a RED
Standards: GEN
- [ ] Restore, register, run.

### Step 4: `/crew:review` exit 6 and the docs
Files: plugin/crew/commands/review.md, plugin/crew/tests/test_lifecycle_commands.py, plugin/crew/README.md, docs/guides/crew/src/working-with-codex.md, docs/guides/crew/src/daily-workflow.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/crew-1.0-working-with-codex.html, docs/guides/crew/crew-1.0-working-with-codex.docx, docs/guides/crew/crew-1.0-working-with-codex.pdf, docs/guides/crew/crew-1.0-daily-workflow.html, docs/guides/crew/crew-1.0-daily-workflow.docx, docs/guides/crew/crew-1.0-daily-workflow.pdf, docs/guides/crew/crew-1.0-troubleshooting.html, docs/guides/crew/crew-1.0-troubleshooting.docx, docs/guides/crew/crew-1.0-troubleshooting.pdf, CHANGELOG.md, TODO.md, plugin/crew/BUDGETS.md, .crew/verify.json
Where: `review.md` `:441` comment and the exit paragraph, in place (551 lines); README's train bullets say the gate round refuses with exit 6 and the prompt lists replays; guides rebuilt with `build.py`; `verify.json` train rule adds `test_review_run_train.py` and `sabotage_train.py`, rules for review_run name L-0526
Test: `python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_troubleshooting_guide.py plugin/crew/tests/test_docs_routing.py -q`; `python3 scripts/check_instructions.py`; `python3 scripts/check-tooling-pr.py`
Risk: low - prose; review.md cannot grow
Standards: GEN
- [ ] Edit, rebuild, run.

### Step 5: version, refresh artifacts, suites
Files: plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, .crew/codemap/*.md, .claude/rules/*.md, docs/diagrams/*.mmd, graphify-out/graph.json, graphify-out/GRAPH_REPORT.md
Where: code maps re-anchored (the Gate paragraph and the merge-train section's callers), the lifecycle diagram's train node in review, rules, `graphify update .`; version one past origin/main as the last commit touching `plugin/crew/`
Test: `crew_refresh_check.py --ticket L-0526` fresh; full suite, wallclock, pylint, ruff-no-new, verify gate and sabotage through heavy-run; `check-marketplace.py`
Risk: med - the version must follow the last plugin change or the drift check fails
Standards: GEN
- [ ] Refresh, bump, run everything, stamp the self-check.

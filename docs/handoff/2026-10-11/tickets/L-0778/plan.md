# L-0778 plan - crew:reviewer dispatcher and committed sabotage

Spec: `spec.md`. Base: origin/main after #600. HARNESS paths: `agents/reviewer.md`, `commands/review.md`,
`tests/sabotage*.py`; everything else rides along as tests/docs/version.

## Steps

### Step 1 - reviewer.md dispatcher
Files: `plugin/crew/agents/reviewer.md`, `plugin/crew/tests/test_crew_kimi_agent.py`, `plugin/crew/tests/agent_frontmatter_snapshot.json`
Test: `test_each_dispatcher_carries_its_instructions_after_the_marker[reviewer]`, the delimiter/exit-2 test and a
new `CREW-REVIEW:` rule test; `test_agent_examples.py`, `validate-prompts.py`.
Risk: med. The reviewer's tests that used a fixture agents dir keep it; one reads the real file.

### Step 2 - review.md step 2c
Files: `plugin/crew/commands/review.md`, `plugin/crew/tests/test_crew_kimi_agent.py`
Test: a test that step 2c names the exact `CREW-REVIEW:` line; `test_review_contracts.py`, golden replay.
Risk: low.

### Step 3 - committed sabotage
Files: `plugin/crew/tests/sabotage_kimi_agent.py`, `plugin/crew/tests/sabotage.py`
Test: `test_sabotage_harness.py` (anchors exactly once); each entry run through the sabotage runner, red.
Risk: med. `sabotage.py` stays under max-module-lines (import plus one name in the sum).

### Step 4 - docs, gates, review, land
Files: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/PLUGINS.md`, `.crew/codemap/**`, `.claude/rules/**`, `docs/diagrams/**`, `CHANGELOG.md`, `README.md`, `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
Test: harness rule commands, gate-runner via heavy-run, `/crew:review` (Codex, `--authors claude`), `/crew:done`.
Risk: low. Version: next free right before merge; `gh pr merge --merge`.

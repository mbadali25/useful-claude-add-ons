# T-0027 autopilot status prints no policy-value warning, and approve names an unreadable config          status: spec   risk: med
## Written 2026-10-04
First spec for this ticket (there was no earlier spec.md and there is no plan.md). Written against origin/main 155fe6d8, crew 1.0.322. The owner was not available; every choice that would have been a question took the recommended option and is listed under "Open questions for the owner". T-0027 was already split on 2026-09-30 (L-0542, L-0543), so this spec covers only the two `crew_autopilot.py` findings and is not split again.
## Intent
`crew_autopilot.py status` prints the same lines whatever `autopilot.approval` and `autopilot.questions` hold, including a value that is not a policy: the per-key "is 'bogus', not one of human|self|risk" warning stays in `settings`, `approval_policy` and `question_policy`, and leaves `status`. `crew_autopilot.py approve`, when `.crew/config.json` cannot be read or its `autopilot` block is not an object, refuses with that cause instead of "autopilot.mode is not plan". Both are T-0010 review round 6 findings the owner accepted as a follow-up (1 FIX, 1 NIT).
## Design (taken as recommended, 2026-10-04)
- `_settings_at` collects the warnings `_policy_setting` returns into a second list as well, and returns it as a new key `policyWarnings`. Every entry is also still in `warnings`, in the same position as today. `settings`' could-not-tell branch returns `policyWarnings: []`.
- `status` returns `warnings` without the entries of `policyWarnings` (read with `.get`, so a settings dict without the key filters nothing: the loud direction). `status_text` and `--json` need no change; they print what `status` returns.
- `status` keeps every other warning: the mode typo, `maxPhases`, `deploy`, the `.crew/crew.json` one, and the single could-not-tell warning for an unreadable config or a non-object block. That last one explains why the mode line reads off and is the same whatever the policy keys say.
- `approve` keeps the line `    if not settings(top)["armed"]:` byte for byte (a sabotage anchor). Inside that branch it asks `_unreadable_autopilot(top)`; with a cause it returns exit 2 and `refused: <cause>, so autopilot could not tell whether it is armed and approves nothing; the human types /crew:approve <ticket>`. With no cause the message is today's, unchanged.
- No filtering by matching warning text. The policy warnings are identified where they are made.
## Exclusions
- No edit to any `HARNESS` path of `scripts/check-tooling-pr.py`: not `plugin/crew/tests/sabotage*.py`, not `plugin/crew/hooks/scripts/crew_ticket.py` (its own "autopilot is not armed" refusal at `:1495` stays), not `scope_guard.py`, `review_*.py` or `verify-gate.*`. No new sabotage mutation. No `Tooling-seam:` trailer: this is a feature PR that touches a seam file and no harness file.
- No rename, re-parametrisation or weakening of `test_route_and_status_unaffected_by_approval_policy` (a sabotage mutation names its `[self]` case) or of `test_autopilot_approve_refuses_unarmed`.
- No change to what `settings`, `next`, `approval_policy`, `question_policy` or `questions-check` print or return, other than the added `policyWarnings` key in `settings`.
- No change to `deploy-allowed` (`_decide`'s "autopilot.mode is not plan" at `:907` stays; it has its own per-layer checks).
- `approve` does not start naming other reasons for being unarmed (a mode typo, an absent file). Only the could-not-tell cause.
- Not L-0542's work (`plugin/PLUGINS.md` approve row text, the daily-workflow guide recipe) and not L-0543's (a verify rule for `crew_ticket.py`'s policy refusal, the codemap rule-numbering NITs).
- No new hook, no new config key, no `.crew/verify.json` rule change.
## Evidence
All at origin/main 155fe6d8, read on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autopilot.py:1523-1556 `status`. `:1528-1530` docstring: "It reads no approval or questions policy (`policy=False`): its lines are the same under every setting". `:1532` `conf = settings(top)`. `:1547` returns `"warnings": conf["warnings"]`.
- plugin/crew/hooks/scripts/crew_autopilot.py:1562-1587 `status_text`. `:1581` prints one `warning:` line per entry. `main` prints the same dict for `--json` (`:1760-1762`).
- plugin/crew/hooks/scripts/crew_autopilot.py:788-826 `_settings_at`. `:819-822` appends `_policy_setting`'s warning for `approval` and `questions` to the one `warnings` list. `:995-1003` `_policy_setting` builds "autopilot.<key> is <value>, not one of human|self|risk; it reads as human, which always stops".
- plugin/crew/hooks/scripts/crew_autopilot.py:759-785 `settings`. `:775-785` the could-not-tell branch: `armed: False`, both policies `UNKNOWN`, one warning. `:739-756` `_unreadable_autopilot` returns the cause text or "".
- plugin/crew/hooks/scripts/crew_autopilot.py:1022-1026 `_decision` picks a key's warnings out of `settings` by the substring `autopilot.<key> `; it is the reader that must keep seeing them.
- plugin/crew/hooks/scripts/crew_autopilot.py:1129-1151 `approve`. `:1139-1141` refuses with "refused: autopilot.mode is not plan, so autopilot approves nothing; the human types /crew:approve <ticket>" for every unarmed reading. `:1143` is a second, different refusal line that is also a sabotage anchor.
- plugin/crew/tests/sabotage_autopilot.py:752-755 anchors `'    if not settings(top)["armed"]:\n'` (test `test_autopilot_approve_refuses_unarmed`). `:856-859` anchors `        return 2, f"refused: {got['reason']}; {human}"\n`. `:861-866` "status reads the policy" names `test_route_and_status_unaffected_by_approval_policy[self]`. The anchor tests are `test_every_policy_sabotage_anchor_is_present_exactly_once` (plugin/crew/tests/test_crew_autopilot_policy.py:636) and `test_every_status_sabotage_anchor_is_present_exactly_once` (plugin/crew/tests/test_crew_autopilot_status.py:1105): each anchor must occur exactly once.
- plugin/crew/tests/test_crew_autopilot_status.py:1121-1135 `test_route_and_status_unaffected_by_approval_policy` compares only the `waiting on` field, under `human`, `self`, `risk`. `:1138-1143` `_status_under` is a ready helper that sets one `autopilot.<key>` and returns the status text.
- plugin/crew/tests/test_crew_autopilot_policy.py:52-71 `_repo` fixture (writes `.crew/config.json` with `scope` and `autopilot`). `:77-80` `_cli`. `:343-349` `test_autopilot_approve_refuses_unarmed` asserts exit 2, "autopilot.mode" in stdout, no receipt. `:839`, `:851` existing settings tests for the unreadable file and the non-object block.
- scripts/check-tooling-pr.py: `HARNESS` holds `plugin/crew/tests/sabotage*.py` and `plugin/crew/hooks/scripts/crew_ticket.py`; the docstring names `crew_autopilot.py` as a `SEAM` consumer. Exit 0 when no harness path changed.
- .crew/verify.json (52 rules, zero-indexed): rule 28 maps `crew_autopilot.py` to `test_crew_autopilot.py`, `test_crew_autopilot_deploy.py`, `test_crew_autopilot_status.py`, `test_lifecycle_commands.py`, `test_crew_ticket_mint.py`, `test_crew_autopilot_assign.py`; rule 29 maps it to `test_crew_autopilot_policy.py` and `test_scope_guard.py`; rule 39 (the harness rule) lists it as a seam path and runs `scripts/check-tooling-pr.py`.
- Docs that state the behaviour: plugin/crew/CONFIG.md:2658-2664 ("`route` and `status` read no policy of their own: `status`'s lines ... read the same under every setting"); plugin/crew/README.md:859 (the one-writer paragraph); plugin/crew/commands/autopilot.md:30-36 (status: "Print its lines as they are") and `:46` (`settings` is where `warning:` lines are read when arming); .crew/codemap/crew.md:733-741 (status reads no policy) and `:693` (the could-not-tell reading).
- `git grep "crew_autopilot.py status\|autopilot status" origin/main -- docs/guides/crew/src` is empty: no guide source describes status's warning lines.
- Version-bearing lines: plugin/crew/.claude-plugin/plugin.json:3, .claude-plugin/marketplace.json:224, plugin/PLUGINS.md:14, CHANGELOG.md:7 (newest entry heading).
## Unknowns
- Whether any doc lists `settings`' keys one by one and so needs `policyWarnings` added. Resolved at implement: `git grep -n '"saw"\|deploySaw' -- plugin/crew docs .crew/codemap` and update each hit that lists the key set (the `settings` docstring at `:760-761` is one).
- Whether `plugin/crew/commands/autopilot.md` needs a word. It is under the 120-line command budget rule, where growth can be a hard fail. Resolved at implement: change it only if a sentence there becomes false; if so keep its line count the same. Expected: no edit.
- The next free crew patch version is chosen at implement time (other lanes hold versions above 1.0.322).
- A caller that monkeypatches `settings` with a dict lacking `policyWarnings`: `status` reads the key with `.get`, so nothing is filtered. Accepted.
- Refresh artifacts (`.crew/codemap/` re-anchor, `graphify-out/`, `docs/diagrams/`) are in scope without a Touch line by the owner's standing rule; `.crew/codemap/crew.md` is listed anyway because its text about `status` changes.
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py` - the only production file; _settings_at, settings, status, approve and their docstrings
- `plugin/crew/tests/test_crew_autopilot_status.py` - new status tests
- `plugin/crew/tests/test_crew_autopilot_policy.py` - new approve and settings tests
- `plugin/crew/CONFIG.md` - the status sentence near line 2658 and the approve refusal
- `plugin/crew/README.md` - the one-writer paragraph near line 859, only if it needs the refusal wording
- `plugin/crew/commands/autopilot.md` - only if a sentence becomes false; line count unchanged
- `plugin/crew/BUDGETS.md` - the markdown line count, if a crew .md file changes size
- `.crew/codemap/crew.md` - the status and settings paragraphs, re-anchored
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json` - version
- `.claude-plugin/marketplace.json` - version
- `plugin/PLUGINS.md` - the version cell on line 14 only
## Acceptance checks
Run the suites one at a time (under the host's heavy-run wrapper where it exists). Rule numbers are `.crew/verify.json`'s zero-indexed positions at 155fe6d8.
- [ ] Red first: each new test below is committed failing before the production change, and the commit message or PR body names the failing run.
- [ ] `test_status_prints_no_policy_value_warning` (in `test_crew_autopilot_status.py`, parametrised over `approval` and `questions` and over a bad string, a bool and a list): with `autopilot.mode: plan` and the key set to the bad value, `status`'s text and its `--json` output equal the outputs with that key removed, and no line contains `autopilot.approval` or `autopilot.questions`. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_status.py -q` (rule 28).
- [ ] `test_status_keeps_a_non_policy_warning`: with `autopilot.mode: "Plan"` and `autopilot.approval: "bogus"`, status prints the mode warning and not the approval one. Same command.
- [ ] `test_status_keeps_the_could_not_tell_warning` (parametrised: `.crew/config.json` is `{bad`; `"autopilot": ["x"]`): status prints exactly one `warning:` line and it names `.crew/config.json`. Same command.
- [ ] `test_settings_still_reports_a_policy_value_warning` (in `test_crew_autopilot_policy.py`): `settings` returns the bad-value warning in both `warnings` and `policyWarnings`, the `settings` CLI prints it, and `approval_policy` still carries it in its `warnings`. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_scope_guard.py -q` (rule 29).
- [ ] `test_autopilot_approve_names_a_config_it_could_not_read` (parametrised: `{bad`; a top-level JSON list; `"autopilot": ["x"]`): `crew_autopilot.py approve --ticket <id>` exits 2, stdout starts `refused:`, names the cause (`could not be read` or `not an object`), does not contain `autopilot.mode is not plan`, contains `/crew:approve <id>`, and no approval receipt exists. Same command as the previous check.
- [ ] Unchanged tests still pass with no edit to them: `test_autopilot_approve_refuses_unarmed`, `test_route_and_status_unaffected_by_approval_policy` (all three cases), `test_status_at_approve_reads_the_same_under_an_allowing_policy`, `test_every_policy_sabotage_anchor_is_present_exactly_once`, `test_every_status_sabotage_anchor_is_present_exactly_once`. Covered by the two commands above.
- [ ] The whole of rule 28 passes: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_deploy.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_ticket_mint.py plugin/crew/tests/test_crew_autopilot_assign.py -q`.
- [ ] No harness path changed: `python3 scripts/check-tooling-pr.py` exits 0, and `git diff --name-only origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py' plugin/crew/hooks/scripts/crew_ticket.py` prints nothing (rule 39).
- [ ] Reproduction from the finding now reads clean: in a throwaway repo with `autopilot.mode=plan` and `autopilot.approval=bogus`, `python3 -B plugin/crew/hooks/scripts/crew_autopilot.py status --root <repo>` prints the same text as with the approval key removed; `... settings --root <repo>` still prints the `warning: autopilot.approval is 'bogus' ...` line.
- [ ] Docs: `plugin/crew/CONFIG.md` says status prints no policy-value warning (settings does) and that approve names a config it could not read; `.crew/codemap/crew.md` says the same with current `path:line` anchors; the PR body lists each doc in the repo's crew doc set as changed or `Docs: none - <why>` (the guides: no guide source describes status's warning lines; diagrams: no flow changes).
- [ ] Crew is bumped to the next free patch in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md:14`, with a CHANGELOG entry; after committing, `python3 scripts/check-marketplace.py` passes.
## Dependencies
Must land first:
- T-0010 (merged, PR #261, crew 1.0.61): the approval and questions policies these findings are about. Satisfied on origin/main.

Related, no ordering required:
- L-0542 (direction, split from T-0027): doc text. It edits the approve row of `plugin/PLUGINS.md`; this ticket edits only that file's version cell, so the two can land in either order with a mechanical merge.
- L-0543 (direction, split from T-0027): verify rule for `crew_ticket.py`, codemap numbering NITs. It edits `.crew/codemap/crew.md` and harness paths; land it as its own tooling PR. Whichever lands second merges main and re-reads its codemap line anchors.
- Any ticket in flight on `crew_autopilot.py` (T-0019 / L-0611, T-0029, T-0049 are in-progress): same file, different functions. No dependency; the later one merges main, bumps one patch past it and re-checks that the sabotage anchors still occur exactly once.

Blocks: nothing. T-0054 (the autopilot guide, ready) describes `status` and `approve`; if it lands after this ticket it should describe the new wording, but it does not wait on it.
## Size
About 20 added production lines, all in `plugin/crew/hooks/scripts/crew_autopilot.py`. No new parser, guard or state machine. No harness path. Not split.
## Open questions for the owner
Each took the recommended option on 2026-10-04; say so if you want another.
1. Sabotage coverage. Taken: none in this ticket, because `sabotage*.py` is harness and may not ride with a `crew_autopilot.py` feature change. Alternative: a later tooling-only ticket adds two mutations (status returns the policy warnings; approve drops the cause).
2. Under an unreadable config, does `status` keep the could-not-tell warning? Taken: yes, it is the reason the mode reads off and does not vary with the policy keys. Alternative: status prints no warning that mentions a policy key at all, and the mode line alone says off.
3. How `status` tells a policy warning from the rest. Taken: `settings` returns them separately as `policyWarnings` (an additive key in `settings --json`). Alternative: no new key, and `status` re-derives them, at the cost of reading the config block twice.
4. The NIT. Taken: fixed. Alternative: declined, as the direction allows for NITs.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

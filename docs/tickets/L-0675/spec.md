# L-0675: crew passes the repo's project to vault recall and falls back cleanly on an older CLI          status: spec   risk: med
Split from T-0083 (2026-10-04). Not approved. Written against origin/main `155fe6d8` (crew 1.0.322). Read T-0083's spec.md first: it defines `--project` in the obsidian-vault CLI.

## Intent
On every recall, crew tells the CLI which project the session is in, so notes of this repo's project rank first. The project comes from the repo's crew config, or from the main checkout's directory name. With an obsidian-vault that does not know `--project`, recall still works exactly as it does today, and the log says the project was not used.

## Exclusions
- No ranking, filtering or scoring in crew. crew still "does not search vaults itself" (crew_recall.py:4). Order inside a vault stays the CLI's.
- No file under `plugin/obsidian-vault/` changes.
- No edit to `plugin/crew/tests/sabotage_context.py` or any other harness path (scripts/check-tooling-pr.py:58-87). The sabotage mutations are L-0676.
- No new hook, no new hook event, no change to the injected line format (`- [vault:<name>] <note>: <text>`) or to the `<vault-recall>` block.
- No change to the four rules in crew_recall.py:11-26 (never block, every snippet names its vault, only the vaults asked for, priority is the repo's).
- `memory.recall.projects` is repo-only, like the other `memory.recall` keys. No machine-level setting.
- No query rewriting. The prompt is still sent as the query; stop words are the CLI's job.

## Design
- `crew_recall.projects(crew_cfg, root)` returns a list. `memory.recall.projects`, when it is a non-empty list, gives the names: non-string and empty entries are dropped, the rest trimmed and de-duplicated. Otherwise the list is the one directory name of the main checkout: the parent of `git rev-parse --git-common-dir` resolved against `root`, so a linked worktree reports the main checkout's name, not its own. When git cannot answer, or the common dir is not named `.git`, the list is empty.
- A name carrying a comma, a control character or a line break is dropped. A leading `-` is safe because the value is passed as `--project=<names>`.
- `recall()` gains `root=None`. With a non-empty list it appends `--project=<a,b>` to the argv. With an empty list it sends today's argv.
- Fallback. When the call with `--project` exits 2, crew runs the same argv once without it. Both runs share one `CLI_TIMEOUT_SECONDS` deadline; with less than 0.5 s left there is no retry and the result is the miss `cli-exit-2`. No other exit code and no timeout is retried.
- The result dict gains `project` (the list sent) and `projectUsed`: `true` when the answer came from a call that carried `--project`, `false` when it came from the retry, `null` when no project was sent or no call answered. The context log's `recall` record carries both.
- `crew_context.recall_items` gains a `root` parameter; both callers pass it.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_recall.py:39 `CLI_TIMEOUT_SECONDS = 4`. :132-150 how `vault_order` and `max_chars` read `memory.recall`. :218 `recall(query, crew_cfg, crew_root=None, budget=None, runner=None)`. :224 the result dict. :244-245 the argv. :246-256 the run and its timeout. :257-259 a non-zero exit is the miss `cli-exit-<n>`.
- plugin/crew/hooks/scripts/crew_context.py:604-606 `recall_items`. :1190 and :1313 its callers, both in functions that hold `root`. :112-117 `state_dir` already resolves `--git-common-dir` against `root`. :1221-1224 and :1321-1323 the `recall` log record (status, reason, snippets, dropped, vaults).
- plugin/crew/hooks/scripts/crew_config.py:298-304 `memory.recall` defaults and the repo-only comment. plugin/crew/templates/config.template.json:80-83. plugin/crew/skills/crew-setup/SKILL.md:209 the shipped example.
- plugin/crew/CONFIG.md:828-829 the two existing rows. :166 "`leaf_paths(default_config())` yields **130**, so **58** are repo-only"; :789 "Repo-only keys — 58 leaves". plugin/crew/tests/test_crew_config.py:351 pins 130. A new list leaf makes these 131 and 59.
- plugin/crew/tests/test_crew_context.py:172-186 `test_snippets_follow_the_repo_vault_priority_not_the_cli_order` reads the stub's recorded argv; :200-209 `test_a_broken_cli_is_a_logged_miss_not_a_failure` pins the exact `recall` record for a stub that always exits 2. plugin/crew/tests/context_fixtures.py:95 `make_stub_cli`.
- The obsidian-vault CLI exits 2 on a usage error (plugin/obsidian-vault/hooks/scripts/vault_recall.py:38; argparse's own exit code for an unknown option is also 2).
- docs/guides/crew/src/memory-recall-proof.md:47-54 describes the config keys and the CLI call; :150-152 lists the miss reasons.

## Unknowns
- Whether the main checkout's directory name matches the `project:` values in a given vault. It will not always. Resolved by the config key, and the guide says to set it. Accepted as risk for repos that set nothing: a wrong name promotes nothing and hides nothing.
- `test_a_broken_cli_is_a_logged_miss_not_a_failure` compares the whole record with `==`. Adding two keys changes that expectation. Resolved at implement: update the expected dict in the same commit.
- Whether the config leaf-count tests name the count in more places than test_crew_config.py:351. Resolved at implement: `git grep -n "130" -- plugin/crew/tests plugin/crew/CONFIG.md`.
- The next free crew patch version is set at implement time.

## Touch
- `plugin/crew/hooks/scripts/crew_recall.py`
- `plugin/crew/hooks/scripts/crew_context.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/templates/config.template.json`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/tests/test_crew_recall_project.py` - new
- `plugin/crew/tests/test_crew_context.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/context_fixtures.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `docs/guides/crew/src/memory-recall-proof.md`
- `docs/guides/crew/src/memory-and-obsidian.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script
- `.crew/codemap/crew.md`

Not in Touch, stated: `plugin/crew/tests/sabotage_context.py` (L-0676); `docs/diagrams/` (the recall edge already exists; a regenerated anchor is a refresh artifact); `.crew/verify.json` (the rule at :378-383 already maps `crew_context.py` to `test_crew_context.py`; the new test file sits under the crew-suite rule).

## Acceptance checks
Commands run from the repo root, through the heavy-run wrapper on a memory-bound host. New tests are in `plugin/crew/tests/test_crew_recall_project.py` unless stated.
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_recall_project.py plugin/crew/tests/test_crew_context.py plugin/crew/tests/test_crew_config.py -q` passes.
- [ ] `test_the_main_checkout_name_is_sent_as_the_project`: a repo at `<tmp>/acme-app` with no config key sends `--project=acme-app`.
- [ ] `test_a_linked_worktree_sends_the_main_checkout_name`: from `git worktree add <tmp>/lane-7`, the argv carries `--project=acme-app`, not `lane-7`.
- [ ] `test_the_config_list_wins_over_the_directory_name`: `memory.recall.projects: ["crew", "Crew Plugin"]` sends `--project=crew,Crew Plugin`.
- [ ] `test_unusable_project_names_are_dropped` (parametrized): a name with a comma, a newline or a control character, a non-string and an empty string are dropped; when none is left and the config list was non-empty, no `--project` is sent.
- [ ] `test_no_git_answer_sends_no_project`: a directory that is not a git repo sends today's argv, and the record has `project == []` and `projectUsed is None`.
- [ ] `test_an_older_cli_is_asked_again_without_the_project`: a stub that exits 2 when it sees `--project` and answers otherwise yields `status == "hit"`, `projectUsed is False`, and exactly two recorded calls, the second without `--project`.
- [ ] `test_only_exit_2_is_retried` (parametrized over exit 1, exit 3, a timeout and bad JSON): one call, and the existing miss reason.
- [ ] `test_the_retry_shares_one_time_budget`: a runner whose first call uses the whole budget before exiting 2 gets no second call.
- [ ] `test_a_cli_that_exits_2_both_times_is_the_same_miss_as_today`: reason `cli-exit-2`, `projectUsed is None`.
- [ ] `test_the_context_log_records_the_project`: after a `UserPromptSubmit`, the last log record's `recall` has `project` and `projectUsed`. The `SubagentStart` record has them too.
- [ ] End to end against the real CLI, skipped when `plugin/obsidian-vault/hooks/scripts/vault_recall.py` has no `--project` option: `test_this_repos_concept_outranks_another_projects_note` builds a vault with two concept notes, sets `CREW_VAULT_OPS` to the checkout's `vault_ops.py`, and asserts the matching project's note is the first injected line.
- [ ] Existing behaviour holds: `test_snippets_follow_the_repo_vault_priority_not_the_cli_order`, `test_every_recall_snippet_names_its_vault_and_unlabelled_items_are_dropped` and `test_a_cli_timeout_is_a_miss` pass with no change to what they assert; `python3 plugin/crew/tests/sabotage.py` still turns every existing context mutation red (anchors in crew_recall.py unchanged: :209 and the `label` line at :215).
- [ ] Config: `test_crew_config.py` pins the new leaf count; CONFIG.md has a `memory.recall.projects` row and the 130/58 figures at :166 and :789 are updated to the measured values.
- [ ] `python3 scripts/check-tooling-pr.py` reports that this branch touches no harness path.
- [ ] Docs: plugin/crew/README.md, CONFIG.md, crew-setup SKILL.md:209, memory-recall-proof.md (the key, the fallback and the `projectUsed` field) and memory-and-obsidian.md state the behaviour; the guide outputs are rebuilt with `python3 docs/guides/crew/src/build.py`; .crew/codemap/crew.md describes the project argument with a fresh anchor. crew is bumped to the next free patch in plugin.json, marketplace.json and PLUGINS.md, with a CHANGELOG entry. After the commit, `python3 scripts/check-marketplace.py` passes.

## Size
About 70 added production lines: `crew_recall.py` about 55 (`projects`, the argv, the retry and its deadline, two result keys), `crew_context.py` about 10, `crew_config.py` and the template about 5. Under the 300-line rule. One retry branch, no new parser, no fail-closed state machine, no harness path.

## Dependencies
Must land first:
- T-0083 (spec, slice 1): adds `--project` to the CLI. Without it this slice ships only the fallback path, and the end-to-end test skips.
- T-0088 (merged): linked worktrees read the main checkout's repo config, which is where `memory.recall.projects` lives.
- T-0087 (merged): the rule that keeps the sabotage mutations out of this PR.

Blocks: L-0676.

## Open questions for the owner
Defaults already taken above.
1. Default project name: the main checkout's directory name (taken), or nothing until the repo sets `memory.recall.projects`?
2. On an older CLI: retry once without `--project` (taken), or log the miss and inject nothing?

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

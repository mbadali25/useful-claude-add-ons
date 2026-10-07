# T-0106 apply-migrate finds the other opted-in repos with --scan-root, and its notes name their file          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md and there is no plan.md. Written against origin/main `155fe6d8` (crew 1.0.322) from direction.md's "Direction check 2026-10-04", option 1, taken under the owner's standing authority. Every `path:line` below was read at that commit. The module has one commit on main (`6c497a14`), so re-check the line numbers only if `git diff --name-only 155fe6d8..origin/main -- plugin/crew/hooks/scripts/crew_autoclear_setup.py` prints the file.

## Intent
`crew_autoclear_setup.py apply-migrate --scan-root <dir>` looks under the named directories for other repos whose `.crew/config.json` or `.crew/crew.json` still carries `context.autoClear.enabled: true`, and adds them to the proposed `onlyRepos` list beside the current repo, so nobody has to search the disk by hand (report item 7). Each note `apply-migrate` prints says which of the two repo files it is about, so two files with the same legacy block no longer read as duplicate output (item 15). `--yes-widen` no longer writes an empty list, which would turn auto-clear off on the whole machine.

## Design
Decisions the implementer keeps; change one only by amending this spec.

**The scan**
- New flags on `apply-migrate` only: `--scan-root <dir>` (repeatable) and `--scan-depth <n>` (integer, default 3, minimum 1). `--scan-depth` without `--scan-root` is a usage error (exit 2).
- A scan root that does not exist or is not a directory: exit 1, message on stderr naming the path, nothing written anywhere.
- Each root is resolved with `os.path.realpath`, then walked top-down. Depth 1 is the root's direct children. A directory is a **candidate** when it holds `.crew/config.json` or `.crew/crew.json`. The root itself can be a candidate.
- Pruning: a candidate is not descended into. Directories whose name starts with `.`, directories named `node_modules`, and symlinked directories are not entered. Nothing below `--scan-depth` is read.
- A candidate is **opted in** when either of its two files parses to a JSON object whose `context.autoClear.enabled` is exactly `true`. This is the same test `had_repo_local_opt_in` applies to the current repo, and either file counts, as it does there.
- A candidate is **unreadable** when either file exists but cannot be opened, is not valid JSON, or is not a JSON object, or when a directory inside the depth limit cannot be listed. Unreadable is its own result. It is never counted as "not opted in".
- The scan is read-only. It never writes, converts or strips another repo's files. Only the repo named by `--root` is converted, as today.
- The current repo is recognised by realpath and is not listed twice. Its own opt-in still comes from its own files, read before they are converted.

**The proposal**
- `proposedOnlyRepos` = the current repo (when it opted in) plus every opted-in candidate, each as `os.path.realpath`, de-duplicated, sorted.
- The result gains `widening.scan`, present only when `--scan-root` was given:
  `{"roots": [...], "depth": n, "found": [<realpath>, ...], "unreadable": [{"path": ..., "reason": ...}, ...]}`.
- `widening.message` changes when a scan ran: it names the roots and the depth, says how many opted-in repos were found, lists the unreadable ones, and states the two limits: repos outside the roots are not seen, and a repo that was already converted no longer carries the opt-in and cannot be found. Without `--scan-root` the message is unchanged except for one added sentence naming `--scan-root`.
- When there is no widening (`enabled` is not `true` machine-wide, or `onlyRepos` is already a list) the scan does not run and `widening.scan` is absent.

**`--yes-widen`**
- With an empty `proposedOnlyRepos`: refused. Exit 1, stderr says that an empty list would turn auto-clear off in every repo, and names `--scan-root` and `crew_config.py --set 'context.autoClear.onlyRepos=<list>' --apply`. Nothing is written, neither the machine file nor the repo files, so the repo's opt-in signal is still on disk for the next run.
- With one or more unreadable candidates: refused the same way, naming each unreadable path. Without `--yes-widen` the same run exits 0 and reports them.
- Otherwise unchanged: the machine-file write still happens before either repo file is touched (`:544-553`).

**The notes**
- In `apply_migrate_to_repo`, every per-file note is prefixed with its file: `.crew/config.json: ` or `.crew/crew.json: `. This covers the method-rename note, which has no label today, and the strip notes.
- `plan-migrate`, `plan_migrate_context`, `strip_repo_duplication` and `convert_method_windows_literal` keep their current output: they work on one context block, not on a file.

**Layout**
- All new code goes in `crew_autoclear_setup.py`, standard library only, below `had_repo_local_opt_in`. Keep the function names `detect_onlyRepos_widening` and `apply_migrate_to_repo`, and keep their existing positional parameters; new parameters are keyword-only with defaults that give today's behaviour.
- New messages are added to `check_no_forbidden_words`'s samples (`:679-692`).

## Exclusions
- No scan without `--scan-root`. No default roots, no walk of the home directory or of the current repo's parent.
- No write to any repo other than `--root`. No conversion of scanned repos; each is migrated by its own `/crew:migrate` run.
- No new machine-file key, no record of past opt-ins, no recovery of repos that were already converted (direction.md option 3).
- No change to `plan-migrate`, `plan-windows-default`, `apply-method`, `apply-enabled`, or to `apply_onlyRepos_narrowing`'s consent rule.
- No change to how `onlyRepos` is read or compared: `crew_autocycle.py`, `auto-clear.sh`, `auto-clear.ps1`, `crew_config.py` and `crew_state.py` are not edited.
- No change to `crew_migrate.py` (T-0105's file) or to `/crew:migrate`'s other steps.
- Not the TODO.md deferral at `TODO.md:4281` (the second read of the machine file inside `write_global_config`).
- No hook, no edit to any path in `HARNESS` (`scripts/check-tooling-pr.py:58-87`), no edit to `plugin/crew/tests/sabotage*.py`.
- No worktree-specific handling: a linked worktree under a scan root is treated like any other directory.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:344-381 `detect_onlyRepos_widening`. :360-361 no widening unless the machine file has `enabled` true and `onlyRepos` null. :362 the proposal is the current repo or `[]`. :371-373 and :377-379 the "add by hand" messages.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:336-341 `had_repo_local_opt_in`: `enabled is True`.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:493 `apply_migrate_to_repo`. :595-608 each file converted from its own content. :603 the opt-in is the OR of both files. :610 the notes of both files joined into one list. :612 the widening call. :615-618 `--yes-widen` writes `proposedOnlyRepos` as it is, empty or not. :544-553 the machine write precedes the repo writes. :568-576 a second run cannot see the stripped opt-in.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:315-332 the strip notes, each starting with the repo label only. :285-288 the method-rename note, with no label.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:466-490 `_read_json_if_present`: `None` when absent, raises on a broken or non-object file.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:727-732 the `apply-migrate` parser: `--repo-label`, `--yes-widen`. :769-777 its handler: `GlobalConfigUnreadable`, `OSError`, `ValueError` give exit 1 with the message on stderr.
- plugin/crew/hooks/scripts/crew_autoclear_setup.py:674-695 `check_no_forbidden_words`.
- plugin/crew/hooks/scripts/crew_autocycle.py:276-284 `_scope`: a list narrows, a non-list narrows to nothing. :287-297 `in_scope`: a repo not in the list is out. :229-273 `normalise_repo_path`: entries are compared realpath-resolved.
- plugin/crew/CONFIG.md:743 the `onlyRepos` row: "`[]` or a non-list arms nothing".
- plugin/crew/commands/migrate.md:73-83 the auto-clear step: the command at :78, the `widening` paragraph at :83. The file is 111 lines; the budget is 120 (plugin/crew/BUDGETS.md:34) and migrate.md has no entry in `plugin/crew/.budget-allowance.json`.
- plugin/crew/tests/test_autoclear_setup.py (705 lines): :113-156 the widening tests, :264-293 the `yes_widen` tests, :162 `test_no_forbidden_words_anywhere`, :207 and :300 the `_write_crew_json` / `_write_config_json` helpers.
- plugin/crew/tests/test_worktree_config.py:201 `"crew_autoclear_setup.py": (2, ...)`; :242-260 what is counted (an `os.path.join` with `".crew"` followed by a config name or by any non-constant, and whole-string `.crew/config.json` / `.crew/crew.json` constants outside docstrings); :263-277 the test fails when the count differs.
- docs/guides/crew/src/auto-cycle.md:99-138 the user guide's `onlyRepos` section.
- .crew/codemap/crew.md:596-602 and :1498-1501 describe the module's call sites and subcommands; :543, :582, :589 cite line ranges inside it. `.claude/rules/crew.md:21` is generated from the code map.
- docs/diagrams/data-flow-crew-config-autoclear.mmd:32 cites `:239-269` and `:107-114` in the module.
- .crew/verify.json:203-207 runs the full crew suite for `plugin/crew/tests/**` changes; :236-239 runs `validate-prompts.py` for `plugin/crew/commands/**`; :256 runs the Python lint rule for `**/*.py`.
- Nothing on main implements this: `git grep -n "scan-root\|scan_root" origin/main -- plugin/crew` prints nothing.
- docs/handoff/cloud/T-0106.md and docs/handoff/cloud/README.md:28 exist on main and carry a required-cleanup rule.

## Unknowns
- Whether a walk of a large root is slow. Resolved at implement by the depth limit and pruning; the test tree is small. Accepted as risk beyond that: the scan runs once, during a migration, only when asked.
- Windows paths. `os.path.realpath` and `os.walk` are used as the module already uses them; the proposal is compared by the senders after their own normalisation. Resolved at implement by running the new tests on the Windows CI leg; no Windows-only code is expected.
- Whether any existing test asserts the exact text of an `apply_migrate_to_repo` note. Resolved at implement: run `test_autoclear_setup.py` after the prefix change and update only assertions on note text.
- The exact wording of the new messages. Left to the implementer, inside the rules in Design and the forbidden-words check.
- The next free crew patch version is set at push time (one past origin/main; 1.0.323 against `155fe6d8`).
- The five open questions in direction.md. Each has a default taken; an owner answer that differs is a spec amendment.

## Size and split
- Estimate: about 120 added production lines, all in `plugin/crew/hooks/scripts/crew_autoclear_setup.py` (the walker about 60, the proposal and message about 25, the two refusals about 15, the CLI flags about 15, the note prefix about 5).
- One new walker. The two `--yes-widen` refusals are conditions before an existing write, not a new state machine.
- No harness path is touched, so the tooling-PR rule does not apply.
- Not split.

## Touch
- `plugin/crew/hooks/scripts/crew_autoclear_setup.py`
- `plugin/crew/tests/test_autoclear_setup.py`
- `plugin/crew/tests/test_worktree_config.py` - only the count and reason on the crew_autoclear_setup.py line of ALLOWED
- `plugin/crew/commands/migrate.md`
- `plugin/crew/CONFIG.md` - one sentence on the onlyRepos row or beside it, pointing at the migrate scan
- `docs/guides/crew/src/auto-cycle.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- `.crew/codemap/crew.md`
- `.claude/rules/crew.md` - regenerated from the code map
- `docs/diagrams/**` - regenerated only if the cited line ranges move
- `docs/handoff/cloud/T-0106.md` - deleted
- `docs/handoff/cloud/README.md` - the T-0106 row removed
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `graphify-out/**` - refreshed by graphify update

Not in Touch, stated: `plugin/crew/README.md` (it does not describe `apply-migrate` or the migration proposal; `git grep -n "crew_autoclear_setup\|proposedOnlyRepos" origin/main -- plugin/crew/README.md` prints nothing); `plugin/crew/skills/crew-setup/phases.md` and `plugin/crew/commands/onboard.md` (they call `plan-windows-default`, which does not change); `.crew/verify.json` (the existing rules cover every touched path); `plugin/crew/.budget-allowance.json` (migrate.md stays inside 120 lines).

## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's heavy-run wrapper. New tests live in `plugin/crew/tests/test_autoclear_setup.py` and build their repos under `tmp_path`; none reads a real config.
- [ ] Scan finds the others. A root holding three repos (one opted in through `config.json`, one through `crew.json` only, one with `enabled: false`) plus the current repo: `proposedOnlyRepos` is the sorted realpaths of the current repo and the two opted-in ones; `widening.scan.found` lists the two. `python3 -m pytest plugin/crew/tests/test_autoclear_setup.py -q -k test_scan_root_adds_every_opted_in_repo_to_the_proposal`
- [ ] The reporter's case. The current repo has no local opt-in, the machine file is `enabled: true` / `onlyRepos: null`, and the root holds opted-in repos: the proposal is those repos, not `[]`. `-k test_scan_root_proposes_other_repos_when_this_repo_never_opted_in`
- [ ] No flag, no scan. Without `--scan-root` the result has no `widening.scan`, the proposal is what it is today, and no directory outside `--root` is read. `-k test_no_scan_without_scan_root`
- [ ] Pruning and depth, one test each:
  - a repo deeper than `--scan-depth` is not found, and is found when the depth is raised: `-k test_scan_depth_limits_the_walk`
  - a repo nested inside a candidate, inside a dot-directory, inside `node_modules`, or behind a symlinked directory is not found (the symlink case is skipped where the platform cannot create one): `-k test_scan_skips_nested_hidden_vendored_and_symlinked_directories`
  - the current repo under a scan root appears once: `-k test_scan_does_not_list_the_current_repo_twice`
  - two roots that overlap give each repo once: `-k test_overlapping_scan_roots_deduplicate`
- [ ] Unknown stays unknown. A candidate whose `config.json` is not valid JSON, and one whose file is a JSON list, appear in `widening.scan.unreadable` with a reason, are not in the proposal, and the message names them. `-k test_unreadable_candidate_is_reported_not_treated_as_not_opted_in`
- [ ] `--yes-widen` refuses with an unreadable candidate: exit 1 through `setup.main([...])`, the paths on stderr, the machine file and both repo files byte-identical to before. `-k test_yes_widen_refuses_when_a_candidate_could_not_be_read`
- [ ] `--yes-widen` refuses an empty proposal: exit 1, stderr names `--scan-root`, the machine file has no `onlyRepos: []`, and the repo files are unchanged. `-k test_yes_widen_refuses_an_empty_proposal`
- [ ] `--yes-widen` with a scan writes the full list, before the repo files: the machine file's `onlyRepos` equals the proposal. `-k test_yes_widen_with_scan_root_writes_the_scanned_list`
- [ ] The scan writes nothing elsewhere: every file under the scan root other than the current repo's two files is byte-identical after a run with `--yes-widen`. `-k test_scan_never_writes_to_a_scanned_repo`
- [ ] Bad input: a missing scan root gives exit 1 with nothing written; `--scan-depth 0` and `--scan-depth` without `--scan-root` give exit 2. `-k test_scan_root_and_depth_usage_errors`
- [ ] The scan does not run when there is no widening (machine `onlyRepos` already a list): no `widening.scan`. `-k test_scan_skipped_when_there_is_no_widening`
- [ ] Item 15. With the same legacy block in both files, every note in `plan["notes"]` starts with `.crew/config.json: ` or `.crew/crew.json: `, and no two notes are equal. `-k test_apply_migrate_notes_name_their_file`
- [ ] `plan-migrate` output is unchanged: `-k test_migrate_` (the existing `plan_migrate_context` tests at `:60-110`) passes without edits.
- [ ] The new messages are covered by the forbidden-words check: `-k test_no_forbidden_words_anywhere` passes, and `check_no_forbidden_words` builds a sample with a scan result that has both a found and an unreadable entry.
- [ ] The whole file passes: `python3 -m pytest plugin/crew/tests/test_autoclear_setup.py -q`.
- [ ] The config-reader count matches: `python3 -m pytest plugin/crew/tests/test_worktree_config.py -q -k test_no_module_reads_repo_config_outside_the_resolver`, with the `crew_autoclear_setup.py` line of `ALLOWED` stating the new count and why (or unchanged, if the scan reuses the existing joins).
- [ ] Self-check that each new test can fail (no sabotage.py edit; done by hand and reported in the PR body): removing the unreadable refusal turns `test_yes_widen_refuses_when_a_candidate_could_not_be_read` red; removing the empty-proposal refusal turns `test_yes_widen_refuses_an_empty_proposal` red; removing the candidate prune turns the nested case red.
- [ ] Full crew suite, `.crew/verify.json` rule at :203-207: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"` then `python3 -m pytest plugin/crew/tests/ -q -m wallclock`.
- [ ] Lint, no new findings against the merge-base: `python3 -m ruff check plugin/crew/hooks/scripts/crew_autoclear_setup.py plugin/crew/tests/test_autoclear_setup.py` and `python3 -m pylint plugin/crew/hooks/scripts/crew_autoclear_setup.py`.
- [ ] Docs:
  - `plugin/crew/commands/migrate.md` shows `--scan-root`, says the scan is read-only, that unreadable repos are listed and block `--yes-widen`, and that already-converted repos cannot be found; `wc -l plugin/crew/commands/migrate.md` is at most 120; `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)` passes.
  - `docs/guides/crew/src/auto-cycle.md` gains a short "finding the repos to list" paragraph in the `onlyRepos` section, and the guide outputs are rebuilt with `python3 docs/guides/crew/src/build.py`.
  - `plugin/crew/CONFIG.md` points from the `onlyRepos` row to the migrate scan.
  - `.crew/codemap/crew.md` names the new flags at :596-602 and :1498-1501 and its cited line ranges in the module are re-read; `.claude/rules/crew.md` is regenerated; `docs/diagrams/` is regenerated if `:107-114` or `:239-269` moved.
  - `docs/handoff/cloud/T-0106.md` is deleted and its row removed from `docs/handoff/cloud/README.md`: `git grep -n "T-0106.md" -- docs/handoff/cloud` prints nothing.
- [ ] Release: crew is one patch past origin/main in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`; `CHANGELOG.md` has a `### Changed` entry for that version naming T-0106 and the `--yes-widen` behaviour change; `plugin/crew/BUDGETS.md` counts are current; after the commit, `python3 scripts/check-marketplace.py` passes.
- [ ] Breaking change stated in the PR body and the CHANGELOG: `apply-migrate --yes-widen` now exits 1 instead of writing `onlyRepos: []`, and `apply-migrate` notes carry a file prefix.

## Dependencies
Must land first: none open.
- T-0088 (merged): added the config-reader count in `test_worktree_config.py` that this change has to keep true.
- T-0006 (merged): auto-clear and auto-resume, the feature `onlyRepos` narrows.

Related, no order forced:
- T-0105 (direction, handed to cloud): `crew_migrate.py` key mapping. Same command (`/crew:migrate`), different file. Whichever lands second re-bumps the crew version and merges `commands/migrate.md` if both edit it.
- T-0038 (approved): folds `/crew:upgrade` into `/crew:migrate` and edits `commands/migrate.md`. A text merge at most; re-check the 120-line budget after it.
- T-0096 (direction): worktree config inheritance for the shell readers. It does not touch this module.
- T-0048 (spec) and T-0054 (ready): the full crew and autopilot guides. If T-0048 lands first, its configuration reference also needs the `--scan-root` sentence.
- T-0046 (in-progress): BUDGETS.md bookkeeping. Until it lands, the BUDGETS.md count update is in scope here by standing rule.
- T-0104 (approved), T-0107 (done), T-0108 (direction): siblings from the same report, no shared files.

Blocks: nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

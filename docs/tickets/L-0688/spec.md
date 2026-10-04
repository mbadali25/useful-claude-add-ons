# L-0688 refresh admission refuses an artifact removed from the index          status: spec   risk: med
Split from L-0540 on 2026-10-04. Written against origin/main `155fe6d8` (crew 1.0.322). Filed as L-0688. Feature PR; lands before L-0540.

## Intent
`artifact_verdicts` never returns `True` for an artifact whose base copy exists and which the index no longer holds, even when a file with a forward re-anchor is still on disk. The verdict is `False` with a reason that says the commit would delete it. The module docstring stops naming L-0540 as pending.

## Exclusions
- No edit to completion_audit.py, scope_guard.py or any `plugin/crew/tests/sabotage*.py` (harness paths). The sabotage entry for this check lands with L-0540.
- No change to the verdict for a new artifact that has no base copy (untracked or staged): it is judged as today.
- No change to W-0116's or W-0117's checks, to the mode loop's other refusals, or to `ticket_freshness`.
- No comparison of index bytes with disk bytes.
- No config key, no hook, no command-file change.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_refresh_check.py:786 `_on_disk(top, base, rel, deleted)`. :821-833 the loop over `()` and `("--cached",)` running `git diff --no-ext-diff --raw --no-renames -z [--cached] <base> -- <rel>`; :831-833 a record is judged only when neither mode is `000000`. :834-842 `ls-files -s`: only link modes refuse; empty output falls to `return None, data`.
- `_on_disk` callers: :675 `_texts` (maps, diagram sources and INDEX.md read through it), :941 `_rule_verdict`, :1084 `_rendered_verdict`, :1104 `_graph_verdict`. The docstring at :130-135 says every kind that reads or admits a working-tree file asks it first, so one check covers all kinds.
- :122-127 the docstring sentence "wired by L-0540 ... until it lands the audit admits the whole dirs as since 1.0.36".
- plugin/crew/tests/test_refresh_admission.py has no case for `git rm --cached` (`git grep -nE "rm.*--cached" origin/main -- plugin/crew/tests/test_refresh_admission.py` prints nothing). Neighbours to copy the shape from: :1243 `test_an_index_only_mode_change_under_file_mode_true_is_refused`, :1255 `test_an_index_mode_check_that_cannot_run_is_could_not_tell`.
- plugin/crew/tests/refresh_fixtures.py:88 `anchored_repo`, :127 `re_anchor_map`, :151 `re_anchor_diagram`, :159 `rebuild_graph`.
- scripts/check-tooling-pr.py:58-87: crew_refresh_check.py is not in `HARNESS`, so this PR prints `tooling-pr: no harness path changed`.
- .crew/verify.json:397-405 runs `python3 -m pytest plugin/crew/tests/test_refresh_admission.py -q` for this file.
- Docs that list the refusals: plugin/crew/README.md:826, docs/guides/crew/src/daily-workflow-scope.md:103-105 ("A deleted rendered diagram or graph file, a symlink at or along an artifact's path, or a file whose git mode changed never passes").

## Unknowns
- The raw record git prints for a path in the base, absent from the index and present on disk, under `--cached`: expected `:100644 000000 <oid> <zeros> D`. Resolved at implement: the new test uses real git and asserts the refusal.
- Whether the worktree (non-cached) diff prints the same deletion record. If it does, the refusal must come from the `--cached` pass only when the file exists on disk; a file absent on disk is already refused earlier with `deleted`. Resolved at implement with the test.
- The next free crew patch version is set at implement time.

## Touch
- `plugin/crew/hooks/scripts/crew_refresh_check.py`
- `plugin/crew/tests/test_refresh_admission.py`
- `plugin/crew/tests/refresh_fixtures.py` - only if a helper is needed
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/src/daily-workflow-scope.md`
- `docs/guides/crew/crew-1.0-daily-workflow.html`
- `docs/guides/crew/crew-1.0-daily-workflow.docx`
- `docs/guides/crew/crew-1.0-daily-workflow.pdf`
- `.crew/codemap/crew.md`
- `.crew/codemap/INDEX.md`
- `.claude/rules/crew.md` - regenerated
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `graphify-out/**`

Docs checked and not touched: `plugin/crew/CONFIG.md`, `plugin/crew/commands/*.md` (they do not list the individual refusals), `docs/diagrams/` (no node or edge changes).

## Acceptance checks
- [ ] New `test_an_artifact_removed_from_the_index_but_left_on_disk_is_refused` in test_refresh_admission.py, parametrised over a map, a diagram source and a graph file: `git rm --cached <rel>`, the file left on disk in admissible shape; the verdict is `(False, <reason naming the index>)`. It fails on origin/main `155fe6d8`.
- [ ] New must-allow neighbour `test_a_new_untracked_rendered_file_beside_its_source_is_still_admitted`: no base copy, no index entry, source re-anchored; verdict `True`.
- [ ] New `test_a_new_staged_artifact_is_still_admitted` (record `000000 -> 100644`): verdict unchanged from main.
- [ ] `python3 -m pytest plugin/crew/tests/test_refresh_admission.py -q` passes (verify.json's admission rule), and `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_refresh_check.py -q` passes.
- [ ] Hand-run RED once, recorded in the PR body: remove the new refusal, run the first test above, see it fail, restore with `git checkout --`. The permanent sabotage entry is L-0540's.
- [ ] `git grep -n "L-0540" -- plugin/crew/hooks/scripts/crew_refresh_check.py` prints nothing; the paragraph says `completion_audit.audit` is the caller and that its docstring states what it admits, which is true before and after L-0540.
- [ ] README.md:826 and the guide's refusal list name the new case; `python3 docs/guides/crew/src/build.py` run and the three daily-workflow outputs committed.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`.
- [ ] Version: crew one patch past main in plugin.json, marketplace.json and PLUGINS.md, with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.
- [ ] `python3 scripts/gate-runner.py` is green; `scripts/_test/drift-detection.sh` is reported as not run.

## Dependencies
- T-0094, merged (#285): ships `_on_disk`.
- W-0117, merged (`e51f9db7`): the `--cached` pass this check extends.
- Blocks: L-0540.
- Related: L-0624 (direction), which adds W-0117's sabotage entry next to the same lines.

## Size
About 20 added production lines (the check and its reason in `_on_disk`, the docstring paragraph). No new parser or state machine. No further split.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

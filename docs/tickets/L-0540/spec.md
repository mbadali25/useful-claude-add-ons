# L-0540 completion audit admits a refresh artifact only on artifact_verdicts' True (T-0094 tooling half)          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket; there was no spec.md or plan.md before. Written against origin/main `155fe6d8` (crew 1.0.322) from direction.md and its "Direction check 2026-10-04". Owner not available, so the recommended options there are taken.

What differs from the 2026-09-30 seed direction:
- The ticket is split. **L-0688 lands first** (feature PR: the `:795` fix in crew_refresh_check.py). This ticket is the tooling-only PR that follows. Reason: crew_refresh_check.py is outside `HARNESS` and `ALONGSIDE`, so the fix cannot ride with completion_audit.py.
- MUST-FIX `:706` is already fixed on main by W-0116. This ticket only adds its missing sabotage entry.
- The seed's completion_audit.py is not copied. T-0100 changed the same function on main, so the seed's four admission functions are ported onto main's file.
- Reach after a catch-up merge is decided: un-narrowed.
- No plan.md exists. Plan after L-0688 has merged, against main at that time.

## Intent
`completion_audit.audit` (the Stop hook and `/crew:done` check 3) admits a changed refresh artifact of an approved ticket without Touch only when `crew_refresh_check.artifact_verdicts` returns `True` for it. A refused or could-not-tell artifact is judged against Touch and, when outside it, listed with its reason in brackets. The interim sentences that say "once L-0540 lands" leave the README, the guide and the code map.

## Design (decided here)
- **What is judged.** The artifacts are taken from the narrowed list the audit already uses (`changed_paths(top, base, merged)`), so a path byte-identical to merged main is never judged.
- **Reach.** `artifact_verdicts` gets the un-narrowed list (`changed_paths(top, base)`) as `reach`. A merged-in main path can reach a map, as README.md:826 states and as `ticket_freshness` measures. When no merge applies the two lists are the same and one listing is made. When a merge applies the audit already makes the second listing for its count (completion_audit.py:281); reuse it, do not add a third.
- **Approval gate first.** Without a current approval nothing is exempt and `artifact_verdicts` is not called.
- **Fail closed.** A raise from `refresh_artifact_paths`, `is_refresh_artifact` or `artifact_verdicts` gives every affected artifact `(None, "could not tell: <ExceptionName> ...")`. When the configured dirs cannot be resolved, the affected set is the artifacts under the default dirs, or every path if that raises too. An artifact with no verdict is not admitted.
- **Message.** `_entry` prints `path [reason]` for a listed artifact, through `shown`. The merged-main line (`*extra`) and the six-physical-line cap stay as on main.
- **Guard.** scope_guard.py changes in its rule-6 docstring only. It stays a path test.

## Exclusions
- No edit to crew_refresh_check.py or any file outside `HARNESS` and `ALONGSIDE` (scripts/check-tooling-pr.py). The `:795` fix and the docstring at crew_refresh_check.py:122-127 are L-0688's.
- No edit to `plugin/crew/commands/done.md` or `implement.md`. They already describe this rule and are outside `ALONGSIDE`.
- No change to scope_guard.py's behaviour, to `artifact_verdicts`, to the merged-main rule (`merged_main.py`, `_as_merged`), to `worktree_changes` (L-0553's), or to the approval gate.
- No sabotage entry for W-0117's index-only mode refusal. That is L-0624's, unless the owner folds it in. The one seed entry W-0117 broke is re-pointed, because the file cannot land with a dead anchor.
- No change to `check-tooling-pr.py` (L-0539's).
- No new hook, no new config key, no CONFIG.md change.
- No edit to `plugin/crew/tests/sabotage.py` (at the pylint module-line limit); entries go in sabotage_refresh.py.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/completion_audit.py:255-265 `_outside_refresh_artifacts`: path test, returns `paths` minus every artifact when approved. :268 `audit`. :277-281 `merged_main.resolve`, the narrowed listing and the second listing for `dropped`. :290-291 approval read, then the allowance. :303-313 the outside-Touch listing through `shown`, with `*extra`. :250-252 `physical` caps at `MAX_LINES` (:92). :53-64 the docstring paragraph that describes the allowance.
- plugin/crew/hooks/scripts/crew_refresh_check.py:1019 `artifact_verdicts(top, base, reach, artifacts, cfg=None)`, returns `{rel: (True|False|None, reason)}`; :1034-1036 removes the artifact dirs and `.work` from `reach` itself. :491 `COULD_NOT_TELL`. :434 `refresh_artifact_paths`, :466 `is_refresh_artifact`. :1332 `ticket_freshness` calls `completion_audit.changed_paths(top, base)` with no `merged`.
- `git grep -n artifact_verdicts origin/main -- plugin/crew/hooks/scripts` matches crew_refresh_check.py only: no hook calls it.
- plugin/crew/hooks/scripts/scope_guard.py:30-38 the rule-6 docstring the seed extends.
- scripts/check-tooling-pr.py:58-87 `HARNESS` holds completion_audit.py, scope_guard.py and `plugin/crew/tests/sabotage*.py`; :99-118 `ALONGSIDE` holds `plugin/crew/tests/**`, README, BUDGETS, version files, CHANGELOG, `docs/**`, `.crew/codemap/**`, `.claude/rules/**`, `.crew/verify.json`, `graphify-out/**`. crew_refresh_check.py and `plugin/crew/commands/*.md` are in neither.
- Seed, under `.work/tickets/L-0540/seed/`: completion_audit.py differs from main by the whole T-0100 block as well as the admission functions (diff taken 2026-10-04); scope_guard.py differs by the docstring lines only; test_completion_audit_refresh_artifacts.py has 22 tests against main's 10 and imports `refresh_fixtures` names that exist on main (plugin/crew/tests/refresh_fixtures.py:29-30, :45, :49, :88, :127, :159, :163) and `crew_fixtures.head_sha` (:1356).
- Seed sabotage_refresh.py, static check against main's files: 137 entries (117 crew_refresh_check.py, 15 completion_audit.py, 4 scope_guard.py, 1 verify.json). 116 of the 117 are found exactly once; `git diff --raw failing reads as unchanged` (seed :630-633) is found 0 times, because W-0117 moved that return into the loop at crew_refresh_check.py:821-828. 11 of the 15 completion_audit.py entries are found 0 times until the port. Main's file has 51 entries. Not run.
- W-0116's check: crew_refresh_check.py:753-759; its tests: plugin/crew/tests/test_refresh_admission.py:1462, :1473, :1484. No sabotage entry mutates it.
- plugin/crew/tests/test_refresh_check.py:566 `test_every_refresh_sabotage_anchor_is_present_exactly_once`; plugin/crew/tests/sabotage.py:75 and :3065 import and append `REFRESH_MUTATIONS`.
- Interim sentences: plugin/crew/README.md:821 ("the audit applies it once L-0540 lands, and until then admits the whole artifact dirs under approval, as since 1.0.36") and :826 ("applied by the audit once L-0540 lands"); docs/guides/crew/src/daily-workflow-scope.md:109-111; .crew/codemap/crew.md:1192-1199, :1244, :1250, :1260, :1506; .claude/rules/crew.md:23 (generated); docs/diagrams/process-crew-lifecycle.mmd:298-301 (comment); test comments at plugin/crew/tests/test_refresh_admission.py:18, :593, :668, :1000 and plugin/crew/tests/refresh_fixtures.py:2.
- .crew/verify.json:314-334 maps completion_audit.py, scope_guard.py, sabotage_refresh.py and the audit suite to one pytest rule; :397-405 is the admission rule; :453-473 is the harness rule that runs `check-tooling-pr.py`.
- Round-2 test: seed test file :213-228 asserts `[could not tell:` for a dangling symlink; main refuses a symlink first (crew_refresh_check.py:782, :808-809), and T-0094's unit test stubs `_read_regular` instead (test_refresh_admission.py:552-564).

## Unknowns
- Line numbers move when L-0688 lands. Resolved at plan time: re-read `_on_disk` and re-run the static anchor check before writing steps.
- Whether every seed entry still goes RED. The static check proves the anchors, not the result. Resolved at implement: each entry this ticket adds is hand-run (Acceptance).
- Cost of `artifact_verdicts` at Stop on a large refresh (git calls per artifact). Not measured. Resolved at implement: time the audit suite and re-price verify.json's rule if it moves; accepted as risk for a repo with hundreds of changed artifacts.
- Whether L-0553 or L-0624 lands first. Both touch files in this Touch. Accepted: merge main, never rebase; re-run the anchor test.
- The next free crew patch version is set at implement time.

## Touch
- `plugin/crew/hooks/scripts/completion_audit.py`
- `plugin/crew/hooks/scripts/scope_guard.py` - docstring only
- `plugin/crew/tests/test_completion_audit_refresh_artifacts.py`
- `plugin/crew/tests/sabotage_refresh.py`
- `plugin/crew/tests/test_refresh_check.py` - only if the anchor or count assertions need the new entries
- `plugin/crew/tests/test_refresh_admission.py` - comments that say landing with L-0540
- `plugin/crew/tests/refresh_fixtures.py` - docstring, and a merged-main fixture helper if needed
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/src/daily-workflow-scope.md`
- `docs/guides/crew/crew-1.0-daily-workflow.html`
- `docs/guides/crew/crew-1.0-daily-workflow.docx`
- `docs/guides/crew/crew-1.0-daily-workflow.pdf`
- `.crew/codemap/crew.md` - the refresh-artifact bullet, the test list and the entry-point line are claims, not only an anchor
- `.crew/codemap/INDEX.md`
- `.claude/rules/crew.md` - regenerated
- `docs/diagrams/process-crew-lifecycle.mmd` - provenance comment
- `.crew/verify.json` - only if the rule's price moves
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `graphify-out/**`

Docs checked and not touched: `plugin/crew/CONFIG.md` (no config change), `plugin/crew/commands/done.md` and `implement.md` (already state the rule).

## Acceptance checks
Run from the repo root on the build branch, after L-0688 is on main and merged in.
- [ ] Precondition: `git grep -n "test_an_artifact_removed_from_the_index_but_left_on_disk_is_refused" origin/main -- plugin/crew/tests/test_refresh_admission.py` prints one line, and `python3 -m pytest plugin/crew/tests/test_refresh_admission.py -q` passes. If not, stop: L-0688 has not landed.
- [ ] `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_completion_audit_refresh_artifacts.py plugin/crew/tests/test_completion_audit.py plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_scope_guard_refresh_artifacts.py plugin/crew/tests/test_merged_main.py -q` passes (verify.json's refresh rule). The audit suite holds the seed's 22 tests, adjusted, plus the new ones below.
- [ ] Must-block, each by name in test_completion_audit_refresh_artifacts.py, each failing on main's completion_audit.py: `test_a_map_edited_without_moving_its_anchor_fails_the_audit` (listing holds `[anchor did not move]`), `test_a_refresh_that_no_changed_path_reaches_fails_the_audit`, `test_a_hand_edited_rule_fails_the_audit`, `test_a_graph_rebuild_with_no_code_change_fails_the_audit`, `test_a_could_not_tell_verdict_fails_the_audit_and_says_so`, `test_a_verdict_step_that_raises_fails_the_audit_closed`, `test_artifact_dirs_that_cannot_be_resolved_fail_the_audit_as_could_not_tell`, `test_an_unapproved_ticket_is_never_judged_for_reach_or_shape`.
- [ ] `test_an_unreadable_rule_fails_the_audit_as_could_not_tell` stubs `crew_refresh_check._read_regular` and asserts `[could not tell:`; new `test_a_symlinked_rule_fails_the_audit_as_a_symlink` asserts `.claude/rules/ghost.md [a symlink, which no refresh writes]`.
- [ ] New `test_an_artifact_removed_from_the_index_fails_the_audit`: `git rm --cached` of a re-anchored map left on disk; the audit fails and the listing carries L-0688's reason.
- [ ] New, merged main: `test_a_merged_in_main_path_reaches_a_re_anchored_map` (must-allow: the only path that reaches the map came in with the merge; audit passes), `test_an_artifact_identical_to_merged_main_is_not_judged` (the `artifacts` argument seen by a stubbed `artifact_verdicts` omits it), `test_a_refused_artifact_keeps_the_merged_main_line` (the failure holds both the bracketed reason and the `merged main` line, in at most six physical lines).
- [ ] Must-allow: `test_an_approved_ticket_passes_with_a_real_refresh`, `test_committed_refreshes_pass_too`, `test_a_refused_artifact_named_in_touch_passes`, `test_the_stop_hook_lets_an_approved_refresh_through` (every flavour) pass.
- [ ] `python3 -m pytest plugin/crew/tests/test_refresh_check.py::test_every_refresh_sabotage_anchor_is_present_exactly_once plugin/crew/tests/test_sabotage_harness.py -q` passes: every entry of sabotage_refresh.py, the seed's included, matches exactly once.
- [ ] sabotage_refresh.py holds the seed's entries with `git diff --raw failing reads as unchanged` re-pointed at the loop's could-not-tell return, plus new entries: L-0688's index-deletion refusal removed (red: L-0688's unit test), W-0116's final-path comparison removed (red: `test_a_descriptor_whose_final_path_is_elsewhere_is_refused`), W-0116's `where is None` branch removed (red: `test_a_descriptor_whose_final_path_cannot_be_read_is_could_not_tell`), reach passed narrowed (red: `test_a_merged_in_main_path_reaches_a_re_anchored_map`), artifacts taken from the un-narrowed list (red: `test_an_artifact_identical_to_merged_main_is_not_judged`).
- [ ] Hand-run RED, recorded in `.work/tickets/L-0540/sabotage-run.md` with the command and result per entry: every completion_audit.py, scope_guard.py and verify.json entry, the re-pointed entry and the new entries. Per entry: apply `find` -> `replace`, run `PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest plugin/crew/<test> -q`, expect a failure, then `git checkout -- <target>`. The crew_refresh_check.py entries already run RED on T-0094 are re-run only where their target lines changed since `42d5ef58` (`git diff 42d5ef58 origin/main -- plugin/crew/hooks/scripts/crew_refresh_check.py`).
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK - <n> harness path(s), nothing outside tooling` and exits 0; `python3 scripts/_test/tooling-pr.py` passes (verify.json's harness rule).
- [ ] `git grep -nE "once L-0540 lands|until L-0540|landing with L-0540|land with L-0540|L-0540 wires" -- plugin/crew docs/guides/crew/src .crew/codemap .claude/rules docs/diagrams` prints nothing.
- [ ] `python3 docs/guides/crew/src/build.py` was run and the three daily-workflow outputs are committed; `git grep -n "L-0540" -- docs/guides/crew/crew-1.0-daily-workflow.html` prints nothing.
- [ ] README.md:821 and :826 and the guide state the rule in the present tense; completion_audit.py's docstring states what is admitted, the bracketed reason and the reach rule after a merge.
- [ ] Version: crew is one patch past main in plugin.json, marketplace.json and PLUGINS.md, with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.
- [ ] `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --ticket L-0540` prints `fresh` after the refresh commit, and `python3 plugin/crew/hooks/scripts/completion_audit.py --check --ticket L-0540` passes with the new audit judging this ticket's own refresh.
- [ ] `python3 scripts/gate-runner.py` is green; `scripts/_test/drift-detection.sh` is reported as not run.

## Dependencies
Must land first:
- L-0688 (filed 2026-10-04): the `:795` fix. Owner rule of 2026-09-30: both holes closed before the audit calls `artifact_verdicts`.
- T-0094, merged (#285, `42d5ef58`): ships `artifact_verdicts`.
- W-0116, merged (`7de96ec1`): closes MUST-FIX `:706`.
- T-0100, INDEX says approved, code is on origin/main (completion_audit.py:19-34): the merged-main narrowing this port sits on.
- W-0117, merged (`e51f9db7`): the `_on_disk` loop the re-pointed entry targets.

Related, not blocking: L-0624 (direction; same sabotage file), L-0539 (direction; would let a feature's sabotage entries ride with it), L-0553 (direction; edits `worktree_changes` in the same harness file), L-0511 and L-0522 (direction, in-progress; when the refresh runs).

Blocks: nothing in INDEX names L-0540 as a dependency. The docs already describe the narrower rule, so they are wrong until this lands.

## Size and split
- This ticket: about 80 added production lines (completion_audit.py about 70 with docstrings, scope_guard.py 7 of docstring). Tests and sabotage entries are about 560 lines, mostly the seed. No new parser or state machine; one fail-closed wrapper.
- Split reason: harness paths mixed with feature work, not size. One child, `children/1/`, about 20 production lines.

## Split
- L-0688 (child 1 of L-0540, filed 2026-10-04): refresh admission refuses an artifact removed from the index (lands before L-0540)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

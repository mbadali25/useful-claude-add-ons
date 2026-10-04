# L-0643 sabotage mutations for T-0043's autopilot fixes and the fence parser (tooling PR, lands alone)          status: spec   risk: med
Split from T-0043 (2026-10-04). A complete ticket on its own; it is filed as L-0643. This is a review/gate harness change under the owner's rule of 2026-09-28: no feature work in the same PR.
## Intent
Every fix T-0043 and L-0642 made to autopilot's stops has a committed mutation in `plugin/crew/tests/sabotage_autopilot.py` that goes red on a named test, so a later edit that reintroduces one of those bugs is caught by `sabotage.py` rather than by a reviewer. The PR changes the harness table and nothing it tests.
## Exclusions
- No production file: nothing under `plugin/crew/hooks/`, `plugin/crew/commands/`, `plugin/crew/agents/` or `scripts/` changes, and no `Tooling-seam:` trailer is used. If a mutation cannot be anchored without editing `crew_autopilot.py`, stop and report it; do not edit the target.
- No new test of behaviour. Each mutation names a test that T-0043 or L-0642 already added. The only test-file edit allowed is to the anchor test's allowed prefixes, and only if a new test file needs one (none is expected).
- No change to `plugin/crew/tests/sabotage.py`'s runner, to the golden corpus, or to any other mutation's anchor.
- No mutation for code outside T-0043 and L-0642.
## Evidence
All line numbers are origin/main at `155fe6d8`, read on 2026-10-04; the anchors themselves do not exist until the two feature PRs land and are re-read then.
- The table: `AUTOPILOT_MUTATIONS` `plugin/crew/tests/sabotage_autopilot.py:28-165`, tuples of label, target, find, replace, test (`:1-5`). Test ids use the prefix `_T` (`:24`). It is registered in `plugin/crew/tests/sabotage.py:77` and `:3066-3067`.
- Neighbouring mutations that stay untouched: "an INCOMPLETE round is rerun unattended" `:58-61`, "open questions do not stop" `:74-77`, "any unknown artifact is refreshed" `:78-82`.
- The anchor rule: `test_every_autopilot_sabotage_anchor_is_present_exactly_once` (`plugin/crew/tests/test_crew_autopilot.py:1336-1351`) asserts each `find` occurs exactly once in its target and each test id starts with an allowed prefix.
- The harness list and what may ride along: `scripts/check-tooling-pr.py:58-88`, with `plugin/crew/tests/sabotage*.py` at `:79`.
- The harness verify rule: `.crew/verify.json:457-473`, running `python3 scripts/check-tooling-pr.py` and the suites listed at `:469`.
- The `_settles` line a mutation targets is on main today: `        return artifact.get("refreshable", True) is not False\n` (`plugin/crew/hooks/scripts/crew_autopilot.py:346`).
- A floor on the table's size: `plugin/crew/tests/test_sabotage_harness.py:397` asserts `len(sabotage.MUTATIONS) > 100`; adding rows cannot break it.
## Unknowns
- The exact `find` strings. Resolved at plan time by reading the merged `crew_autopilot.py`: each must be unique in the file, and the plan quotes each with `grep -c` output of 1.
- Which named test each fence mutation reddens first. Resolved by running each mutation and naming the measured test, not the expected one.
- Sabotage wall time and memory: `sabotage.py` is a heavy suite. Resolved by running it once, serially, and reporting the wall time; quote any failure verbatim.
- Any document that states a mutation count for autopilot. Resolved by `git grep -n -i "mutation" -- plugin/crew/README.md CHANGELOG.md .crew/codemap` at plan time; a stated count is re-measured, never incremented by hand.
- Version number: `sabotage_autopilot.py` ships inside the plugin directory, so crew needs a bump. Resolved at land, one patch above origin/main's.
## Touch
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot.py` - the anchor test's prefix list only, if needed
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `.crew/codemap/**` - refresh only
- `.claude/rules/**` - refresh only
- `docs/diagrams/**` - refresh only
- `graphify-out/**` - refresh only, built with graphify update
## Acceptance checks
- [ ] T-0043's fixes, three mutations appended to `AUTOPILOT_MUTATIONS`, each red on its test: "an accepted FINDINGS round reads as INCOMPLETE" (the new FINDINGS branch's condition becomes `if False:`; test `test_next_accepted_findings_then_an_edit_goes_through_refresh`); "the FINDINGS stop names no refresh" (the refresh clause leaves the reason; test `test_next_accept_review_names_the_refresh_before_the_next_round`); "a stale artifact marked not refreshable settles" (`:346`'s line becomes `        return True\n`; test `test_refresh_stale_artifact_marked_not_refreshable_stops`).
- [ ] L-0642's parser, seven mutations, each red on a named test from L-0642: "main's parser is no longer the floor" (the union drops the legacy items); "an ambiguous fence reads as no questions" (the `UNCLEAR_FENCE` append is unreachable); "an indented fence line opens a fence"; "an indented closer closes a fence"; "an unclosed fence at the end is settled"; "only an unindented heading names a section" (`_names_open_questions` loses `lstrip()`); and the must-allow side, "ambiguity stops even with no section" (`_names_open_questions` forced true; test `test_open_questions_ambiguous_fence_without_a_section_does_not_stop`).
- [ ] The existing mutations at `sabotage_autopilot.py:58-61` and `:74-77` are unchanged and still red on their tests.
- [ ] `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -p no:cacheprovider -k sabotage_anchor` passes: every new `find` occurs exactly once.
- [ ] `python3 plugin/crew/tests/sabotage.py`, run once and serially, reports every autopilot mutation red on its named test; the set of non-red labels equals origin/main's; `git status --short` shows no `.bak` afterwards. Wall time reported.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0, and `git diff --name-only origin/main...HEAD` lists only the Touch paths. The harness rule `.crew/verify.json:457-473` is run in full and its result quoted; any step that did not run is named as not verified.
- [ ] Land: crew is one patch above origin/main in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md`; `CHANGELOG.md` has an entry under Unreleased naming the ten mutations; `python3 scripts/check-marketplace.py` passes after commit; the PR body says `Docs: none - harness table only, no behaviour or documented count changed` unless the Unknowns grep found a stated count.
## Dependencies
Must land first:
- T-0043, ready: adds the FINDINGS branch, the reworded reason and the three tests the first three mutations name.
- L-0642, new: adds the parser and the tests the seven fence mutations name.
- T-0087, merged: the tooling-PR rule and the harness verify rule this PR runs under.
- T-0004, merged: `sabotage_autopilot.py` itself.

This ticket blocks nothing.
## Size
0 added production lines. About 60 lines in `sabotage_autopilot.py` (ten table rows). Harness only, no feature path, one PR.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

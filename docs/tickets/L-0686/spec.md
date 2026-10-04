# L-0686: sabotage mutations for autopilot's hold, landing, needs-owner, closed and blocked stops          status: spec   risk: med
Split from L-0550 (2026-10-04). Tooling PR; lands after L-0550. Written against origin/main `155fe6d8`.
## Intent
Each must-stop branch L-0550 adds to `crew_autopilot.py` is mutation-proven: a `GATE_MUTATIONS` tuple in `plugin/crew/tests/sabotage_autopilot.py`, appended to `AUTOPILOT_MUTATIONS`, holds one mutation per branch, and each goes red on a named L-0550 test through `sabotage.py`. No production behaviour changes.
## Exclusions
- No production code and no command text. Only `HARNESS` and `ALONGSIDE` paths of `scripts/check-tooling-pr.py`. No `Tooling-seam:` trailer: `crew_autopilot.py` and `autopilot.md` are not edited.
- `plugin/crew/tests/sabotage.py` is not edited (3400 lines, at `.pylintrc:140`'s limit). No new sabotage file.
- No mutation for `crew_ticket_state.py`, `next.md` parsing or the closed words (L-0641), and none for `/crew:status --owner` (L-0551).
- A branch found unguarded gets a test here (tests are `ALONGSIDE`). A production bug found is a STOP and a separate feature ticket, never a fix in this PR.
- No change to how the sabotage runner works.
## Evidence
At origin/main `155fe6d8`, read 2026-10-04.
- `plugin/crew/tests/sabotage_autopilot.py` is 1118 lines. Tuple shape `(label, target, find, replace, test)` at `:1-5`; `AUTOPILOT = os.path.join(SCRIPTS, "crew_autopilot.py")` `:19`; `_T`, `_S` test prefixes `:24-26`; the append pattern `AUTOPILOT_MUTATIONS += STATUS_MUTATIONS` `:674` and `+= ASSIGN_MUTATIONS` `:1118`.
- `plugin/crew/tests/sabotage.py:77` imports `AUTOPILOT_MUTATIONS`; `:3066` concatenates it into `MUTATIONS`.
- `plugin/crew/tests/test_crew_autopilot.py:1336` `test_every_autopilot_sabotage_anchor_is_present_exactly_once` walks `AUTOPILOT_MUTATIONS` and requires each `find` exactly once and each `test` under a known file prefix (`:1341-1343`). `:1359-1365` `test_status_sabotage_is_registered_with_sabotage_py` is the registration-test pattern, with a pinned count.
- `scripts/check-tooling-pr.py:58-87` `HARNESS` holds `plugin/crew/tests/sabotage*.py`; `:99-118` `ALONGSIDE` holds `plugin/crew/tests/**`, `README.md`, `BUDGETS.md`, the version files, `CHANGELOG.md`, `.crew/codemap/**`, `.crew/verify.json`, `graphify-out/**`.
- `.crew/verify.json:348-359` (the autopilot rule) lists `plugin/crew/tests/sabotage_autopilot.py` in its paths; the harness rule that runs `scripts/check-tooling-pr.py`, the golden replay and the canary is at `:459-473`.
- Targets exist only after L-0550: the gate read, the blocked stop, the `WAITING` rows and the `_closed` header test in `crew_autopilot.py`, and the L-0550 tests named below.
## Unknowns
- The exact `find` strings. Taken from L-0550's merged code on the land branch; each must occur exactly once, which `test_every_autopilot_sabotage_anchor_is_present_exactly_once` holds.
- Whether one mutation can be killed by more than one test. Each entry names the one test that must go red; the runner reports that one.
- A stale `.pyc` after an in-place mutation of equal size can hide a red. Run only through `sabotage.py` (it restores from `.bak`); if a mutation reports green, check the `.pyc` timestamp before calling the test weak.
- Run time of the sabotage suite grows by about eight mutations. Re-measure and update the rule's `seconds` and `why` in `.crew/verify.json` if it moves; write no host name in it.
- Version: `plugin/crew/tests/` ships inside the plugin, so crew is bumped one patch above origin/main's at land time.
## Touch
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `.crew/verify.json`
- `.crew/codemap/**`
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
## Acceptance checks
Commands run from the repo root; the sabotage run goes through the repo's heavy-run wrapper on a memory-bound host.
- [ ] `GATE_MUTATIONS` in `sabotage_autopilot.py`, each red on its test:
  - "a hold in the INDEX cell is driven" on `test_next_hold_stops` (the INDEX case);
  - "a hold in the spec header is driven" on `test_next_hold_stops` (the header case);
  - "a landing ticket is driven to done" on `test_next_landing_stops`;
  - "a needs-owner ticket is driven" on `test_next_needs_owner_stops_with_the_next_line`;
  - "a header cancelled is re-driven" on `test_next_header_cancelled_is_closed`;
  - "a blocked ticket is implemented" on `test_next_blocked_stops_before_implement`;
  - "an unknown dependency reads as closed" on `test_next_blocked_with_an_unknown_dependency_stops`;
  - "a gate phase reads as autopilot's in status" on `test_status_waiting_on_a_gate_is_never_autopilot`.
  Command: `python3 plugin/crew/tests/sabotage.py`; every label above reported red, `SABOTAGE SUITE: PASS`, no `.bak` left, any failure quoted verbatim.
- [ ] New test `test_gate_sabotage_is_registered_with_sabotage_py` in `test_crew_autopilot.py`: every `GATE_MUTATIONS` entry is in `sabotage.MUTATIONS`, and the label set equals a pinned set written in the test. `test_every_autopilot_sabotage_anchor_is_present_exactly_once` passes. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_sabotage_harness.py -q`.
- [ ] `git diff --stat origin/main...HEAD -- plugin/crew/tests/sabotage.py plugin/crew/hooks plugin/crew/commands` is empty.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and the harness rule's other commands (`.crew/verify.json:459-473`) pass.
- [ ] `python3 -m pylint plugin/crew/tests/sabotage_autopilot.py` reports no `too-many-lines` and no `line-too-long`.
- [ ] Docs: the PR body says `Docs: none - test harness only` for the guides, diagrams, `CONFIG.md` and command files. `.crew/codemap/verification-harness.md` or `crew.md` names `GATE_MUTATIONS` where it lists the autopilot mutation groups; `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket <id>` prints every line `fresh`.
- [ ] `python3 scripts/check-marketplace.py` passes after the commit that bumps crew one patch in the three version files with a `CHANGELOG.md` entry; `python3 scripts/gate-runner.py` is green, and the PR body names what ran and that `scripts/_test/drift-detection.sh` did not.
## Dependencies
Must land first:
- L-0550 (INDEX: `direction`; spec written 2026-10-04): the code and tests the mutations target.
- Through L-0550: T-0037 (`ready`), L-0639 and L-0640 (specs written, not merged).
- T-0087 (merged): the tooling-PR rule.

Not required: L-0641 (it adds a different sabotage file).

Blocks: nothing.
## Size
0 added production lines. About 50 lines of test harness in `sabotage_autopilot.py` and about 12 in `test_crew_autopilot.py`. No parser, guard or state machine. One PR, harness only.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

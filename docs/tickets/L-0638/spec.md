# Cross-session messaging: sabotage mutations for the bridge script (tooling PR)          status: spec   risk: med
Split from T-0032 (L-0638), 2026-10-04. Filed as L-0638. This is a tooling PR: it changes harness paths and no production code.
## Intent
`plugin/crew/tests/sabotage_bridge.py` holds one mutation per fail-closed decision in `crew_bridge.py`, each anchored on exactly one line of the script and each naming the test in `test_crew_bridge.py`, `test_crew_bridge_pending.py` or `test_crew_bridge_hub.py` that it turns red. The mutations are registered with the sabotage runner so the full run includes them.
## Exclusions
- No change to `crew_bridge.py`, any command, prompt, hook or other production file. If a mutation shows a missing test, the test is added here; if it shows a production bug, that is a new ticket.
- No change to `review_*.py`, `verify-gate.*`, `crew_ticket.py`, `scope_guard.py` or `scripts/check-tooling-pr.py`.
- No version bump of crew unless `scripts/check-marketplace.py` demands one for a tests-only change; if it does, the version files ride along (they are allowed beside a harness change).
## Evidence
Checked at origin/main 155fe6d8.
- `scripts/check-tooling-pr.py:58-87` is `HARNESS`; `:79` is `plugin/crew/tests/sabotage*.py`. The docstring `:10-14` lists what may ride along: tests, docs, version files, code map, graph, ticket records.
- `plugin/crew/tests/sabotage.py` is 3400 lines and `.pylintrc:140` is `max-module-lines=3400`.
- Per-area modules exist beside it, for example `plugin/crew/tests/sabotage_review.py`, `sabotage_tracker.py`, `sabotage_tooling.py`, and `plugin/crew/tests/test_sabotage_harness.py` tests the runner.
- `.crew/verify.json`'s harness rule runs `scripts/check-tooling-pr.py`, `scripts/_test/tooling-pr.py`, the golden replay, the seam contracts and the canary review when a harness path changes (repo CLAUDE.md, "A change to the review/gate harness lands alone").
- `crew_bridge.py` and its three test files do not exist on origin/main; they come from T-0032 and its children L-0636 and L-0637.
## Unknowns
- **How a per-area module is registered without growing `sabotage.py`.** Read the newest module's registration at implementation time. Not checked here.
- **Running one area.** The full sabotage run is long and memory-heavy. The acceptance command below assumes the runner can select mutations by name or module, as other per-area work has; confirm the flag from `sabotage.py`'s own usage text.
- **Anchors move.** Each anchor is written against the merged `crew_bridge.py`, not against this spec.
## Touch
- `plugin/crew/tests/sabotage_bridge.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/tests/test_sabotage_harness.py`
- `plugin/crew/tests/test_crew_bridge.py`
- `plugin/crew/tests/test_crew_bridge_pending.py`
- `plugin/crew/tests/test_crew_bridge_hub.py`
- `.crew/verify.json`
- `.crew/codemap/verification-harness.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
## Acceptance checks
- [ ] Each mutation below is in `sabotage_bridge.py`, anchors on exactly one line, and turns its named test red when run through the sabotage runner (one area only, under the host's heavy-run wrapper if it has one):
  - `receive` uses a prefix match in place of a full match
  - `receive` accepts any `crew-doorbell/<n>` version
  - `receive` skips the channel comparison
  - `receive` reads a failed fetch as "re-read the record"
  - `receive` reads a non-ancestor tip as confirmed
  - `receive` prints the message without `safe`
  - `ring` prints a doorbell after a failed fetch
  - `pending` reads a failed fetch as `no pending doorbells`
  - `pending` clears a ring on this holder's own later line
  - `pending` skips a corrupt log line
  - `ring` in a lane is allowed
  - `ring` with an unreadable lane marker is allowed
- [ ] A test asserts every anchor is present exactly once in the merged `crew_bridge.py` (`python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q`, or the per-area equivalent the newest module uses).
- [ ] `python3 -m pylint plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_bridge.py` reports no `too-many-lines`.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 on the branch: every changed path is a harness path or allowed alongside one. `python3 scripts/_test/tooling-pr.py` passes. `python3 scripts/check-marketplace.py` passes after the commit.
- [ ] The PR body states `Docs: none - tests only, no behaviour change` or lists the doc it changed.
## Dependencies
Must land first: T-0032 (ready), L-0636, L-0637, and through them T-0030 and T-0029 (both in-progress). Blocks nothing.
## Size
0 added production lines; about 200 lines of tests. Harness paths only, so it lands alone.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

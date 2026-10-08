# L-0687: the owner list and the waiting line know hold, blocked, landing and needs-owner          status: spec   risk: med
Split from L-0551 (2026-10-04). Feature PR; lands after L-0551 and L-0550.
## Intent
`/crew:status --owner` stops treating a parked ticket as a generic stop. A hold that is not yet due and a blocked ticket leave the list and are counted on the waiting line (`H held, B blocked`); a hold that is due is listed as `revisit` with its reason; a `needs-owner` ticket is listed with the `next:` line from its next.md. The phase still comes from autopilot's `_phase`, so the list and `/crew:autopilot` keep agreeing.
## Exclusions
- No new stop, phase or status value: L-0550 and T-0037 own those. `_phase`'s answers are read, never changed.
- No next.md writer and no change to `crew_ticket_state.py`.
- No bundle rebuild, no policy read, no file written (as L-0551).
- No `HARNESS` path of `scripts/check-tooling-pr.py`, no `sabotage*.py`, no edit to `plugin/crew/commands/autopilot.md` or `done.md`.
- No Obsidian lane or tracker change for the new statuses.
- Blocked tickets are not listed in `--owner`, only counted.
## Evidence
At origin/main `155fe6d8` unless marked "after".
- Nothing to extend exists yet: `git grep -nE "owner_items|crew_ticket_state|next\.md" origin/main -- plugin/crew/hooks/scripts` returns nothing.
- `WAITING` (`plugin/crew/hooks/scripts/crew_autopilot.py:1350-1354`) has no entry for `hold`, `landing`, `needs-owner` or `blocked`; `/crew:autopilot status` prints `unknown (phase ... is not one status maps)` for a phase missing from it (`:1391-1392`). Whether L-0550 adds them is checked at spec refresh.
- After L-0551: `crew_autopilot.owner_items(root)` returning `items`, `unread`, `unknown`; `OWNER_ACTIONS`; `_phase(..., deep=False)`; the `waiting` line and `--owner` in `plugin/crew/hooks/scripts/crew_status.py`; tests in `plugin/crew/tests/test_crew_autopilot_status.py` and `plugin/crew/tests/test_status.py`.
- After L-0550 (its direction.md, 2026-09-30): `_phase` stops with phases `hold`, `landing`, `needs-owner`, `blocked` and `closed`, read from `crew_ticket_state.view(top, ticket, today)`.
- After L-0639 and L-0640 (their spec.md, 2026-10-04): `view` carries `blocked_by`, the gating status, `next`, `reason`, `revisit`, `revisit_due` (True, False, or None when absent or unparsable) and `problems`.
- `crew_status.py` must stay read-only and within `MAX_LINES = 40` (`plugin/crew/hooks/scripts/crew_status.py:41`; `plugin/crew/tests/test_status.py:59`, `:84`).
## Unknowns
- The exact phase names and `view` keys. Resolved before plan: re-read `crew_autopilot._phase` and `crew_ticket_state.view` on origin/main once L-0550 has merged, and correct this spec's names with a "Refreshed" note. If L-0550 changed a name, this spec follows L-0550.
- `revisit_due is None` (no date, or one that does not parse): listed as `revisit`, with "revisit date: cannot tell". Decided; a must-block test holds it, because unknown must not read as "not yet due".
- `needs-owner` with no `next:`: listed, action `cannot tell what is asked (no next: in next.md)`. Decided; tested.
- `today` for `revisit_due`: `owner_items` takes `today=None` and passes it through, so tests are deterministic.
- Whether `/crew:autopilot status`'s `WAITING` should also learn the four phases. If L-0550 did not add them, add them here (hold and needs-owner: owner; blocked and landing: a fixed "nobody - <why>" text) with a test each; otherwise leave.
- Version: one patch above origin/main's crew version at land time.
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_status.py`
- `plugin/crew/commands/status.md`
- `plugin/crew/tests/test_status.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/PLUGINS.md`
- `docs/guides/crew/**` - src/daily-workflow.md and the HTML, DOCX and PDF rebuilt by src/build.py
- `docs/diagrams/**`
- `.crew/codemap/**`
- `.crew/verify.json` - only a re-measured seconds and why
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
## Acceptance checks
Commands run from the repo root; on a memory-bound host each pytest command goes through the repo's heavy-run wrapper.
- [ ] In `test_crew_autopilot_status.py`, `owner_items` gains `held` and `blocked` lists, and:
  - must-allow `test_owner_items_skips_a_future_hold` (in `held`, not in `items`), `test_owner_items_counts_a_blocked_ticket_without_listing_it`, `test_owner_items_skips_landing`;
  - `test_owner_items_lists_a_due_hold_as_revisit` (action carries next.md's `reason:`), parametrised over revisit today and revisit in the past;
  - must-block `test_owner_items_hold_without_a_usable_revisit_is_listed` (no next.md; `revisit: soon`);
  - `test_owner_items_needs_owner_gives_the_next_line` and `test_owner_items_needs_owner_without_next_says_cannot_tell`;
  - `test_owner_items_agree_with_phase` (from L-0551) extended over the new fixtures: every listed, held or blocked ticket is a `_phase(policy=False)` stop with the matching phase.
  - Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q`.
- [ ] In `test_status.py`: `test_waiting_line_counts_held_and_blocked` expects `waiting  1 on you (/crew:status --owner), 2 held, 1 blocked`; `test_waiting_line_with_nothing_on_you_still_shows_held_and_blocked`; `test_owner_view_is_read_only` and `test_owner_view_fits_forty_lines` (from L-0551) pass with a next.md present in the fixture. Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_status.py plugin/crew/tests/test_crew_shell.py -q`.
- [ ] `plugin/crew/commands/status.md`: the `waiting` row and the `## --owner` section name held, blocked, `revisit` and `needs-owner`; the file stays at 120 lines or fewer (`python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_lifecycle_commands.py -q`).
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`; `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_sabotage_harness.py -q` passes.
- [ ] Docs: `plugin/crew/README.md`'s "What is waiting on me" paragraph and its Ticket statuses table (from T-0037) say how each parked status shows in the list; `plugin/PLUGINS.md` row checked; `docs/guides/crew/src/daily-workflow.md` updated and `python3 docs/guides/crew/src/build.py` re-run; the status diagram and `.crew/codemap/crew.md` refreshed. `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket <id>` prints every line `fresh`.
- [ ] Crew bumped one patch in the three version files with a `CHANGELOG.md` entry; commit, then `python3 scripts/check-marketplace.py` passes; `python3 scripts/gate-runner.py` is green, and the PR body names what ran and that `scripts/_test/drift-detection.sh` did not.
## Dependencies
Must land first:
- L-0551 (direction; spec written 2026-10-04): `owner_items`, `--owner`, the waiting line.
- L-0550 (direction): the autopilot stops on hold, landing, needs-owner, blocked.
- L-0640 (spec): next.md and `revisit_due`. L-0639 (spec): `crew_ticket_state.view`, `blocked_by`. T-0037 (ready): the status vocabulary. All three are also L-0550's dependencies.

Blocks: nothing known.
## Size
About 45 added production lines: `crew_autopilot.py` about 28 (the four phase branches in `owner_items`, two lists, `today`), `crew_status.py` about 9 (two counts, the `revisit` rendering), `status.md` about 8 prompt lines. No parser, no guard, no `HARNESS` path. One PR.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

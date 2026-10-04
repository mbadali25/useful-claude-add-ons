# T-0037 plan            spec: .work/tickets/T-0037/spec.md

Reconstructed 2026-10-04 (see HANDOFF.md); the owner approves direction and plan before build. Owner approves (risk: high), or T-0010's policy path once it lands. Preconditions: none unmerged (T-0019's `mint` is on main). Re-grep every anchor in the spec on main before step 1. Crew version: one patch past main at merge, set last. Merge commit (D-028).

**Two PRs, because of the tooling-PR rule (`scripts/check-tooling-pr.py`).** OWNER CHECK.
- **PR A** (steps 1-5, `T-0037-build`): the feature. It changes no `HARNESS` path, so `crew_autopilot.py`, `crew_status.py`, `status.md` and `autopilot.md` ride as ordinary files and need no `Tooling-seam:` trailer.
- **PR B** (step 6, `T-0037-sabotage`, after A merges): registers A's sabotage in `sabotage_*.py` (`HARNESS`), with tests and version files only.

Downstream T-0052, T-0058 and T-0059 wait for PR A. PR B changes no behaviour they read.

### Step 1: the vocabulary and the tracker moves
Files: plugin/crew/hooks/scripts/crew_tracker.py, plugin/crew/tests/test_crew_tracker.py
Test: python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q -k "status or lane or reopen or backwards or closed or owner"
Risk: high. A closed word that moves back without `--reopen` silently revives a cancelled ticket on a board a human is reading.
- [ ] tests first (must-block): `test_move_out_of_cancelled_needs_reopen`, `test_move_out_of_superseded_needs_reopen`, `test_done_to_cancelled_needs_reopen`, `test_closed_to_needs_owner_needs_reopen`; each refusal writes nothing (INDEX bytes and board bytes unchanged)
- [ ] tests first (must-allow): `test_move_to_superseded_from_each_open_status` (parametrized `direction`..`review`, `needs-owner`; files and obsidian), `test_move_to_cancelled_obsidian_done_lane_checked`, `test_needs_owner_round_trip_without_reopen`, `test_needs_owner_obsidian_backlog`, `test_jira_sdp_new_words_push_nothing` (exit 0, "nothing to push")
- [ ] `OWNER_STATUSES = ("needs-owner",)` and `CLOSED_STATUSES = ("cancelled", "superseded")` beside `STATUS_ORDER` (`crew_tracker.py:91`), each with a comment naming T-0037. `LANE_FOR_STATUS` gains `"needs-owner": "backlog"`, `"cancelled": "done"`, `"superseded": "done"` (OWNER CHECK: lanes). `STATUS_ORDER` and `_PUSH_AT` are unchanged
- [ ] `_backwards` (`:654-664`): `current == status` stays None. If `current` is in `CLOSED_STATUSES` or is `done`, and `status` differs, the move needs `--reopen`. A target in `CLOSED_STATUSES` from an open status (including `needs-owner`) is forward. `needs-owner` <-> any `STATUS_ORDER` word before `done` is never backwards. Everything else keeps today's `STATUS_ORDER` rule and its "could not tell" branch
- [ ] module docstring `## Backends` and the table comment `:86-90` name the three words

### Step 2: the closed readers
Files: plugin/crew/hooks/scripts/crew_state.py, plugin/crew/tests/test_crew_state.py, plugin/crew/tests/test_crew_ticket.py
Test: python3 -m pytest plugin/crew/tests/test_crew_state.py plugin/crew/tests/test_crew_ticket.py -q -k "done or closed or cancelled or superseded or precheck"
Risk: high. `_index_closed` feeds approval precheck, which a blocking hook runs. Widening "closed" refuses more, never less. That direction is safe, but a typo in the words would silently reopen a ticket.
- [ ] tests first (must-block): `test_cancelled_row_is_not_the_open_ticket`, `test_superseded_row_is_not_the_open_ticket`, `test_prose_cancelled_colon_closes` (`- Cancelled: T-1`, `1. superseded: T-1`), and in `test_crew_ticket.py` the `test_precheck_closed_index_row` parametrization gains `cancelled` and `superseded` (`:727`)
- [ ] tests first (must-allow): `test_needs_owner_row_is_open`, `test_title_saying_cancelled_does_not_close_an_open_row` (the `test_crew_state.py:370` shape), `test_cancel_the_flag_prose_stays_open` (`- Cancel the T-8 flag` has no colon)
- [ ] `_TABLE_DONE_WORDS` (`crew_state.py:238-240`) gains `cancelled` and `superseded`. `_DONE_RE` (`:218-221`) gains them in the keyword-colon alternation, keeping `re.IGNORECASE`. Its comment block names T-0037. `crew_ticket.py` is not edited: `_index_closed` reads both through `crew_state`

### Step 3: autopilot
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_status.py
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py -q -k "closed or needs_owner or superseded or cancelled"
Risk: high. A superseded parent that autopilot re-drives implements a contract the owner replaced.
- [ ] tests first: `test_superseded_parent_is_closed` (INDEX row, and separately header only, with a `split-into: T-2, T-3` line quoted in the reason), `test_cancelled_header_is_closed`, `test_merged_header_does_not_close` (unchanged), `test_needs_owner_stops_for_owner` (phase `needs-owner`, `WAITING` `owner`, lists the open questions), `test_needs_owner_without_questions_says_none`, `test_open_index_tickets_drops_closed_words`, `status` rendering of `needs-owner` within `STATUS_MAX_LINES`
- [ ] `INDEX_DONE` (`crew_autopilot.py:183`) gains `cancelled` and `superseded`. A new `HEADER_CLOSED = ("done", "cancelled", "superseded")` is used by `_phase` (`:442-446`) and `_closed` (`:1442-1456`) in place of `== "done"`. The closed reason appends the spec's `split-into:` / `superseded-by:` line when present
- [ ] `_phase`: after the `direction` check (`:425-427`) and before `INDEX_DONE`, `status == "needs-owner"` -> `answer("needs-owner", True, ...)` naming `_open_questions(folder)` or "no open question recorded - the owner says what is needed". `WAITING["needs-owner"] = "owner"` (`:1350-1354`). `DIRECTION_APPROVED` and `HEADER_STATUSES` are unchanged

### Step 4: status, commands and docs
Files: plugin/crew/hooks/scripts/crew_status.py, plugin/crew/commands/status.md, plugin/crew/commands/autopilot.md, plugin/crew/commands/obsidian-sync.md, plugin/crew/tests/test_status.py, plugin/crew/tests/test_status_vocabulary.py, plugin/crew/README.md, plugin/crew/CONFIG.md
Test: python3 -m pytest plugin/crew/tests/test_status.py plugin/crew/tests/test_status_vocabulary.py plugin/crew/tests/test_lifecycle_commands.py -q
Risk: med. A command file that grows past its budget fails CI.
- [ ] tests first: `test_status_lists_needs_owner_line`, `test_status_hides_closed_words`, `test_status_unchanged_without_new_words` (byte-identical on a fixture with only today's words); `test_status_vocabulary.py` per spec Acceptance 8
- [ ] `crew_status._ticket_lines` (`crew_status.py:105-122`): collect `needs-owner` rows into `owner    <ids> (needs-owner)`, using the same five-id truncation as `open`. The open tuple at `:116` is unchanged
- [ ] `obsidian-sync.md:63-73`: add `needs-owner` to the `backlog` row and a `cancelled`, `superseded` -> `done` row, edited in place within `MAX_LINES` (`test_lifecycle_commands.py:287-290`, no allowance). `status.md` names the `owner` line. `autopilot.md` names the `needs-owner` stop and that `cancelled`/`superseded` read `closed`. Both edit lines in place (`.budget-allowance.json`)
- [ ] README: a "Ticket statuses" table under the autopilot/lifecycle section beside `README.md:905` (word, open/closed, where it is written, approval kept/staled, Obsidian lane, Jira/SDP), plus the `split-into:` / `superseded-by:` line grammar and "cancel with `crew_tracker.py move --to cancelled`". CONFIG.md `obsidian.columns.backlog` / `.done` rows (`CONFIG.md:809-813`) name the new words

### Step 5: PR A evidence, hand sabotage, CHANGELOG, version last
Files: CHANGELOG.md, plugin/crew/BUDGETS.md, .crew/codemap/crew.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md
Test: python3 scripts/gate-runner.py
Risk: med. A version that is not bumped leaves every installed copy on the old vocabulary.
- [ ] hand sabotage, one at a time on a scratch commit and then reverted, each recorded with the red test name: `cancelled` added to `crew_ticket.STATUS_VALUES` -> `test_approval_digest` cancelled case; `superseded` removed from `_TABLE_DONE_WORDS` -> `test_superseded_row_is_not_the_open_ticket`; `cancelled` removed from `_DONE_RE` -> `test_prose_cancelled_colon_closes`; `superseded` removed from `INDEX_DONE` -> `test_superseded_parent_is_closed`; `HEADER_CLOSED = ("done",)` -> `test_cancelled_header_is_closed`; the closed `--reopen` branch removed -> `test_move_out_of_cancelled_needs_reopen`; the `needs-owner` branch removed -> `test_needs_owner_stops_for_owner`
- [ ] approval tests in `test_approval_digest.py` (tests only, so not harness): `in-progress` keeps; `cancelled`, `superseded` and `needs-owner` stale; `STATUS_VALUES` equals main's tuple literally
- [ ] code map: re-derive the `crew.md` citations into the four changed scripts (`/crew:onboard --refresh crew`); BUDGETS re-measured
- [ ] CHANGELOG entry: the three words, what closes, approval unchanged, lanes, Jira/SDP push nothing, two-PR note
- [ ] remove `docs/tickets/T-0037/` before the version commit unless the owner wants it kept
- [ ] commit, then the version one patch past main in `plugin.json`, `marketplace.json` and `PLUGINS.md` as the LAST commit, then `python3 scripts/check-marketplace.py` and `python3 scripts/check-tooling-pr.py` (expect exit 0: no harness path)

### Step 6: PR B, register the sabotage (tooling PR, lands alone)
Files: plugin/crew/tests/sabotage_tracker.py, plugin/crew/tests/sabotage_autopilot.py, plugin/crew/tests/sabotage_scope.py, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md
Test: python3 plugin/crew/tests/sabotage.py
Risk: med. A mutation whose anchor text no longer matches reads as "survived", not as a missing mutation.
- [ ] branch `T-0037-sabotage` from main after PR A merges. Each step 5 hand mutation becomes a registered entry: tracker ones in `sabotage_tracker.py`; `INDEX_DONE`, `HEADER_CLOSED`, `needs-owner` and the `crew_state` words in `sabotage_autopilot.py`; `STATUS_VALUES` in `sabotage_scope.py` beside the "APPROVAL DIGEST" entries (from `:273`). A run shows each one red on its named test
- [ ] `.crew/verify.json`'s harness rule runs (check-tooling-pr, its suite, golden replay, seam contracts, canary). `check-tooling-pr.py` exits 0 with only `HARNESS` + `ALONGSIDE` paths. Version set last, then `check-marketplace.py`

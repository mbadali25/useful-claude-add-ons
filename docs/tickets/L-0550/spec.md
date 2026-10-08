# L-0550 autopilot stops on hold, landing, needs-owner, cancelled/superseded and blocked          status: spec   risk: high
Split from T-0037 (2026-09-30). Feature PR. Written 2026-10-04 against origin/main `155fe6d8` (crew 1.0.322).
## Refreshed 2026-10-04
- First spec for this ticket; before today the folder held only the seed direction.md. No plan.md exists.
- Decisions kept from T-0037's approved plan Step 5: the phase names, that a blocked ticket still gets spec and plan, that `landing` is not `done`, and that an unknown dependency stops.
- Changed against that step, each because origin/main contradicts it:
  - One gate read instead of two. `crew_ticket_state.view` (L-0639) already reads the INDEX cell first and then the header, so `_phase` asks once.
  - `cancelled` and `superseded` INDEX rows are closed by L-0639 (`INDEX_DONE`). Left here: the header case and the successor in the reason.
  - `autopilot.md`'s budget is 110 lines, not 120, and the file is at 109.
  - `WAITING` and `_closed` (T-0018, in the same file) need the new phases. The old step did not know them.
  - The sabotage mutations moved to L-0686: `plugin/crew/tests/sabotage*.py` is a `HARNESS` path and cannot share a PR with `crew_autopilot.py`.
- No `depends-on:` line is written in this header yet: the field arrives with T-0037, and two of the three prerequisites have no ticket id. Add it at plan time.
## Intent
`crew_autopilot.py next` stops, with a true reason, on a ticket whose INDEX cell or spec header says `hold`, `landing` or `needs-owner`, reads a header `cancelled` or `superseded` as `closed` and names the successor, and stops as `blocked` before implement when a `depends-on:` ticket is not closed or cannot be told. `/crew:autopilot status` says who each of those stops waits on. Today a header-only `hold` and a blocked ticket are driven, and an INDEX `hold` stops under the false reason "cannot tell whether the direction is approved".
## Exclusions
- No `HARNESS` path of `scripts/check-tooling-pr.py`: no `crew_ticket.py`, no `plugin/crew/tests/sabotage*.py`. The mutations are L-0686. `python3 scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.
- No change to `crew_ticket_state.py`, `crew_state.py`, the status vocabulary, `depends-on:` parsing or `next.md` parsing. If `view` lacks something this spec needs, that is a STOP and an amendment to the T-0037 child that owns it, not an edit here.
- No `/crew:status --owner`, no `owner_items`, no `crew_status.py` or `commands/status.md` edit (L-0551).
- Nothing writes a status. Autopilot never sets `hold`, `landing`, `needs-owner`, `cancelled` or `superseded`, never writes `next.md`, and never lifts a gate. `next` stays read-only.
- No new policy setting, no `CONFIG.md` key. The gate stops hold at every `autopilot.approval` and `autopilot.questions` setting.
- No change to `_review_phase`, the approve phase, `resume_target`, `open_index_tickets`, `route`, `crew_route.py` or the Obsidian lanes. A `hold` row stays an open row.
- `revisit:` never lifts a hold. It is printed.
- `autopilot.md` does not grow: 110 lines or fewer.
## Evidence
All read at origin/main `155fe6d8` on 2026-10-04 with `git show origin/main:<path>`.
- `plugin/crew/hooks/scripts/crew_autopilot.py:406` `_phase`. Its order: no direction.md `:420-422`; `_index_status` `:424`; `direction` `:425-427`; no row `:428-432`; `if status in INDEX_DONE:` `:433-435`; `if status not in DIRECTION_APPROVED:` `:436-440`; header `status: done` `:443-446`; open questions `:447-452`; spec `:453-459`; plan `:460-466`; approve `:467-479`; `return _review_phase(top, ticket, evidence, answer)` `:480`.
- `DIRECTION_APPROVED` `crew_autopilot.py:181-182` holds none of the new words, so an INDEX cell of `hold` stops today at `:436-440` as `direction-approval`, "cannot tell".
- `INDEX_DONE` `crew_autopilot.py:183`. `_index_status` `:254-263`. `_header_status` `:284-291`. `HEADER_STATUSES = crew_ticket.STATUS_VALUES + (...)` `:175`.
- `FIXED_STOPS` `crew_autopilot.py:186-200`, nine entries. `stops()` `:1283-1288`. The module docstring's phase table is `:62-83`.
- `_review_phase` `crew_autopilot.py:491`; the `implement` answer is at `:504-505`.
- `next_phase` `crew_autopilot.py:568-601` returns a stop result unchanged (`:583-584`), before the active-ticket, max-phases and no-progress checks.
- `WAITING` `crew_autopilot.py:1350-1354`: thirteen phases map to `owner`, `closed` to `nobody`. `_waiting` `:1388-1409` prints `unknown (phase ... is not one status maps)` for a phase outside it, `owner - types <command>` or `owner - see the phase reason` for a stop.
- `_closed` `crew_autopilot.py:1442-1455` reads `INDEX_DONE` and a header `done` only. `_repoint` `:1412-1430` uses it.
- `crew_route._continue` (`plugin/crew/hooks/scripts/crew_route.py:191-200`) turns any stop into `ask` with the phase and reason. No edit needed.
- `plugin/crew/commands/autopilot.md` is 109 lines. The code-enforced stop list is `:94-96`. `:69-70` already says any other `stop=1` prints the phase, the reason and the command, then stops.
- `plugin/crew/tests/test_lifecycle_commands.py:112` `AUTOPILOT_MAX_LINES = 110`, asserted at `:118`.
- `plugin/crew/tests/test_crew_autopilot.py` (1448 lines): fixtures `_ticket` `:56`, `_approved` `:70`, `_ledger` `:77`, `_round` `:88`, `_receipt_ok` `:100`, `_refresh` `:105`, `_next` `:110`. `test_next_index_status_that_does_not_say_approved_stops` `:617-626` (def at `:618`) (parametrised over `""`, `brainstorm`, `parked`, `rejected`, `**ready**`). `test_next_index_status_done_stops_as_closed` `:637-644`. `test_command_names_every_fixed_and_human_stop` `:1256-1260` requires every `FIXED_STOPS` slug in backticks in `autopilot.md`. `test_code_enforced_stops_are_not_procedure_stops` `:1310`.
- `plugin/crew/README.md`: the phase table `:882-903`; the **Stops** paragraph `:915`, which lists the nine code-enforced slugs; the `status` paragraph `:880`.
- `.crew/codemap/crew.md:686-700` describes `next_phase` and says "`FIXED_STOPS` (`:186`, nine)".
- `.crew/verify.json:348-359` is the autopilot rule: paths include `crew_autopilot.py`, `commands/autopilot.md` and `test_crew_autopilot.py`; run line `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_deploy.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_ticket_mint.py plugin/crew/tests/test_crew_autopilot_assign.py -q`.
- `scripts/check-tooling-pr.py:58-87` `HARNESS` (holds `plugin/crew/tests/sabotage*.py` and `crew_ticket.py`); `:89-95` `SEAM` (holds `crew_autopilot.py` and `commands/autopilot.md`); `:99-118` `ALONGSIDE`.
- No guide source states the phase table: `git grep -nE "direction-approval|stale-after-review" origin/main -- docs/guides/crew/src docs/diagrams` returns nothing. `docs/diagrams/process-crew-lifecycle.mmd` anchors `crew_autopilot.py` lines in comments (`:105-115`).
- Not on main, from the prerequisite specs: `crew_ticket.CLOSING_STATUSES`, `header_status`, `parse_depends_on` (T-0037); `crew_ticket_state.view(top, ticket, today)` with the gate, the not-closed dependencies with a state and reason each, and `problems` (L-0639); `reason`, `revisit`, `revisit_due`, `next`, `superseded-by` and the "cannot tell what is asked" problem (L-0640).
## Unknowns
- The exact keys `view` returns. The prerequisite specs fix the behaviour, not the names. Resolved before plan: read `crew_ticket_state.py` on origin/main once L-0640 has merged, and write the plan against the real keys. A missing fact is a STOP (see Exclusions).
- `view` raising. `next`'s existing boundary prints `stop=1` with the exception (module docstring `:120-122`). No `try` is added around the call, so a crash is never read as "no gate". Held by `test_next_stops_when_the_ticket_view_raises`.
- `view` reporting a problem with no gate and no blocker. Decided: a problem that concerns the gate or the dependencies stops as `blocked`, reason "cannot tell", quoting the problem. A problem that concerns only the review ledger is ignored here, because `_review_phase` reads the ledger itself and stops on UNKNOWN. If `view` does not let the two be told apart, every problem stops. Held by `test_next_blocked_with_an_unknown_dependency_stops`.
- A typed derived status. An INDEX cell of `blocked` or `needs-replan` keeps stopping at `direction-approval` ("cannot tell"); a header one fails `crew_ticket.validate` (T-0037) and stops at `spec`. No new code; `blocked` joins the existing parametrisation.
- Does a README or status test pin the stop list or `WAITING`? `git grep -n "WAITING" origin/main -- plugin/crew/tests` returns nothing, and `sabotage_autopilot.py` holds `README` anchors (`:685`). Resolved at implement by running the verify rule after the README edit; a moved sabotage anchor is fixed in L-0686, not here, and reported.
- `docs/diagrams/process-crew-lifecycle.mmd` cites `crew_autopilot.py` line numbers that will move. A regenerated anchor is a refresh artifact. Whether a node is added for the new stops is the diagram command's readability check to decide; default no new node.
- Version: one patch above origin/main's crew version at land time.
- Reviewer independence follows the standing rule (a same-family reviewer is announced).
## Design
- `_phase`, after the `INDEX_DONE` branch and before the `DIRECTION_APPROVED` test: read `crew_ticket_state.view(top, ticket)` once and append `next.md`'s path to `evidence` when it exists. A gate of `hold`, `landing` or `needs-owner` returns `answer(<the value>, True, reason)` with an empty command, except `needs-owner`, whose command is empty and whose reason quotes `next:`. A gate of `cancelled` or `superseded` (reachable here only from the header) returns `answer("closed", True, reason)`.
- Reasons, each naming where the gate was read (INDEX cell or spec header):
  - `hold`: the `reason:` text, or "no reason given"; the `revisit:` date, with "(passed)" when it is due, or "no revisit date".
  - `landing`: "accepted; the land step owns it from here".
  - `needs-owner`: the `next:` text, or "cannot tell what is asked (no next: in next.md)".
  - `closed`: the word, and for `superseded` the successor id or "successor not named".
- The existing `INDEX_DONE` branch's reason gains the successor id when the cell is `superseded`.
- Immediately before `return _review_phase(...)`: when a dependency is not closed, or the dependency read reported a problem, return `answer("blocked", True, reason)`, naming each dependency with its state (`open`, `unknown`, `cancelled`, `superseded`) and reason. Empty command.
- `FIXED_STOPS` gains `hold`, `landing`, `needs-owner` and `blocked`. The docstring phase table gains their rows in match order.
- `WAITING`: `hold` and `needs-owner` map to `owner`; `landing` prints `the land step - see the phase reason`; `blocked` prints `another ticket - see the phase reason`. Neither is ever `autopilot`.
- `_closed` also returns True for a header `cancelled` or `superseded`.
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/**` - only if a guide source states the stops by then; the HTML, DOCX and PDF are rebuilt with it
- `docs/diagrams/**`
- `.crew/verify.json` - the autopilot rule's measured seconds and why, if the run time moves
- `.crew/codemap/**`
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting), `plugin/crew/commands/status.md` and `crew_status.py` (L-0551), `plugin/crew/tests/sabotage_autopilot.py` (L-0686), `crew_ticket_state.py` (T-0037 children).
## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's heavy-run wrapper.
- [ ] Must-block, new tests in `plugin/crew/tests/test_crew_autopilot.py`, each asserting `(phase, stop)` and the reason:
  - `test_next_hold_stops`, parametrised over an INDEX cell `hold` and a header `status: hold` under INDEX `ready`, on an approved ticket with no rounds: `("hold", True)`, the reason holding `next.md`'s `reason:` and `revisit:`.
  - `test_next_hold_without_next_md_stops`: `("hold", True)`, the reason says no reason and no revisit date were given.
  - `test_next_hold_past_its_revisit_still_stops`: `("hold", True)`, the reason says the date has passed.
  - `test_next_landing_stops`: approved, a CLEAN current receipt, fresh artifacts: `("landing", True)`, never `done`.
  - `test_next_needs_owner_stops_with_the_next_line`: the reason holds `next:`; with no `next.md` it holds "cannot tell".
  - `test_next_header_cancelled_is_closed` and `test_next_superseded_names_its_successor`: `("closed", True)`; the second has the successor id in the reason, and "successor not named" without one.
  - `test_next_blocked_stops_before_implement`: approved, no rounds, one open dependency: `("blocked", True)`, naming it.
  - `test_next_blocked_with_an_unknown_dependency_stops`: a dependency with no INDEX row and no spec: `("blocked", True)`, "cannot tell" in the reason.
  - `test_next_blocked_by_a_cancelled_dependency_stops`.
  - `test_next_blocked_stops_a_ticket_already_in_review`: approved, one completed round: `("blocked", True)`.
  - `test_next_stops_when_the_ticket_view_raises`: `crew_ticket_state.view` monkeypatched to raise; the CLI prints `stop=1`.
  - `blocked` and `needs-replan` added to `test_next_index_status_that_does_not_say_approved_stops`.
- [ ] Must-allow, same file:
  - `test_next_dependencies_closed_reaches_implement` (rows `done` and `merged`): `("implement", False)`.
  - `test_next_blocked_ticket_still_gets_spec_and_plan`: no spec gives `("spec", False)`, then no plan gives `("plan", False)`.
  - `test_next_ticket_without_a_gate_is_unchanged`: no `depends-on:`, no `next.md`: `("implement", False)`.
  - `test_next_index_status_done_stops_as_closed` and `test_next_index_status_after_direction_approval_proceeds` pass with no edit.
- [ ] `test_next_gate_stops_are_read_only`: the file snapshot (`_snapshot`, `test_crew_autopilot.py:114`) is equal before and after `next` on a hold, a blocked and a needs-owner ticket.
- [ ] Stop list: `crew_autopilot.py stops --json` lists `hold`, `landing`, `needs-owner` and `blocked` under `fixed`; `autopilot.md` names each in backticks (`test_command_names_every_fixed_and_human_stop`) and `wc -l plugin/crew/commands/autopilot.md` prints 110 or less (`test_lifecycle_commands.py:112-119`).
- [ ] `status`, new tests in `plugin/crew/tests/test_crew_autopilot_status.py`: `test_status_waiting_on_a_gate_is_never_autopilot`, parametrised over the four phases, asserts the `waiting on:` line starts with `owner`, `the land step` or `another ticket` and never with `autopilot` or `unknown`; `test_closed_reads_a_cancelled_header` asserts `_closed` is True for a header `status: cancelled`.
- [ ] Command for all of the above, the verify rule at `.crew/verify.json:348`: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_deploy.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_lifecycle_commands.py plugin/crew/tests/test_crew_ticket_mint.py plugin/crew/tests/test_crew_autopilot_assign.py -q`. Also `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_route.py plugin/crew/tests/test_module_split.py -q` passes with no edit.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`, and `git diff --name-only origin/main...HEAD -- plugin/crew/tests/ | grep sabotage` prints nothing.
- [ ] Docs: `plugin/crew/README.md`'s phase table (`:882-903`) gains the rows for `hold`, `landing`, `needs-owner`, header `cancelled`/`superseded` and `blocked` in match order; the **Stops** paragraph (`:915`) names the four new slugs; the `status` paragraph says what `waiting on:` prints for them. `.crew/codemap/crew.md` states the new order and re-measures the `FIXED_STOPS` count instead of restating "nine" by hand. The PR body carries `Docs: none - <why>` for each of `CONFIG.md`, the guides and the diagrams that did not change. `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0550` prints every line `fresh`.
- [ ] `python3 scripts/check-marketplace.py` passes after the commit that bumps crew one patch in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, with a `CHANGELOG.md` entry naming the four stops and the closed reading.
- [ ] `python3 scripts/gate-runner.py` is green; the PR body names the suites that ran and states that `scripts/_test/drift-detection.sh` did not, and that the sabotage mutations for these stops are L-0686.
## Dependencies
Must land first:
- T-0037 (INDEX: `ready`, not merged): `hold`, `needs-owner`, `landing`, `cancelled`, `superseded` as valid header values, and `depends-on:`. Without it a header `status: hold` stales the approval.
- L-0639 (spec written 2026-10-04, not merged): `crew_ticket_state.view`, `dependency_state`, and `cancelled`/`superseded` in `INDEX_DONE`.
- L-0640 (spec written 2026-10-04, not merged): `next.md`, for the hold reason and revisit date, the needs-owner `next:` line and `superseded-by`.
- T-0026 (merged): the approval digest the header statuses ride on.
- T-0004, T-0018, T-0010 (merged): `next`, `status` and the policies this edits around.
- T-0087 (merged): the tooling-PR rule that moves the mutations to L-0686.

Not required: L-0641 (sabotage for ticket state; a tooling PR that touches neither file edited here).

Same hot files, serialise, no order forced: `crew_autopilot.py` and `autopilot.md` are edited by T-0022 (`approved`; docs and tracker phases) and T-0043 (`ready`). Whichever lands second merges main and re-finds its anchors; `autopilot.md` has one spare line for all of them.

Blocks:
- L-0686 (the sabotage mutations for these stops).
- L-0551 (`direction`): its `test_owner_view_agrees_with_autopilot` compares the owner list with these phases.
- T-0054 (`ready`): the autopilot guide documents every stop.
## Size and split
- About 90 added production lines: `crew_autopilot.py` about 88 (the gate read and its reasons 40, the blocked stop 15, `FIXED_STOPS` 10, docstring table 8, `WAITING` and `_waiting` 10, `_closed` 5), `autopilot.md` 0 net lines (two prompt lines rewritten in place). Under the 300-line rule.
- No new parser. One fail-closed addition (the gate and blocked stops in an existing phase table).
- Split made for the harness rule only: the mutations are `plugin/crew/tests/sabotage_autopilot.py`, a `HARNESS` path, so they are L-0686 (`children/1/`), a tooling PR that lands straight after this one.

## Split
- L-0686 (child 1 of L-0550, filed 2026-10-04): sabotage mutations for autopilot's hold, landing, needs-owner, closed and blocked stops

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

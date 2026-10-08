# L-0551 /crew:status --owner and the waiting line: what waits on the owner, from autopilot's own phase read          status: spec   risk: med
Split from T-0037 (2026-09-30). Narrowed on 2026-10-04 to the first of two slices; the rest is L-0687.
## Refreshed 2026-10-04
- First spec for this ticket; there was only a seed direction.md. Checked against origin/main `155fe6d8` (crew 1.0.322). See direction.md, "Direction check 2026-10-04".
- Kept from T-0037's approved plan Step 6: the `--owner` flag, one line per ticket with the command to type, the `waiting` line in the default report, read-only, 40 lines, and "the list must agree with autopilot".
- Changed, with the reason:
  - `owner_items` lives in `crew_autopilot.py`, not `crew_ticket_state.py`. That file is not on main, and autopilot's `_phase(policy=False)` (T-0010, T-0018) already is the answer the seed wanted to re-derive.
  - The kinds are autopilot's stop phases, not the seed's seven. `hold`, `blocked`, `landing`, `needs-owner` and `revisit` moved to L-0687, because their inputs (L-0639 and L-0640, L-0550) are not on main.
  - The waiting line carries no `H held, B blocked` yet (L-0687).
- There is no plan.md for L-0551. T-0037's plan.md Step 6 is the old design and does not match this spec; run `/crew:plan L-0551`.
- Feature PR. No `HARNESS` path of `scripts/check-tooling-pr.py` is touched.
## Intent
`/crew:status --owner` lists every open ticket that is stopped on a person, one line each, with the command to type or the question to answer. The default `/crew:status` report gains one `waiting` line with the count. Both come from one function, `crew_autopilot.owner_items`, which asks autopilot's own phase table about each ticket, so the list cannot disagree with what `/crew:autopilot` would do. It writes nothing and runs no review bundle rebuild.
## Exclusions
- No `hold`, `blocked`, `landing`, `needs-owner`, `revisit`, next.md or `depends-on:` handling, and no `crew_ticket_state.py` (L-0687, after L-0550).
- No change to what `_phase` answers when `deep` is true (the default). `next`, `resume`, `status` and `run` behave exactly as before; no phase, reason or command string of theirs changes.
- No bundle rebuild from `/crew:status`: `review_ledger.check_receipt` and `crew_refresh_check` are never reached with `deep=False`.
- No approval or questions policy is read (`policy=False`), so the list is the same under every `autopilot.*` setting.
- No file written, no ticket moved, no tracker call, no command run on the owner's behalf.
- No `HARNESS` path: no `crew_ticket.py`, `review_*.py`, `plugin/crew/tests/sabotage*.py`. No new sabotage mutation (this is a report, not a guard). The existing mutations that target `crew_status.py` and `crew_autopilot.py` must keep matching exactly once.
- No edit to `plugin/crew/commands/autopilot.md` (it is at its 120-line cap) or `plugin/crew/commands/done.md`.
- No new config key; `plugin/crew/CONFIG.md` is not touched.
- No change to the existing `tickets` / `open` lines of the report.
## Evidence
All read at origin/main `155fe6d8` on 2026-10-04 with `git show origin/main:<path>`.
- `plugin/crew/hooks/scripts/crew_status.py` (253 lines): `MAX_LINES = 40` at `:41`; `_ticket_lines` at `:105-122`, its `open` filter at `:116`; `collect` at `:211-240`, the clip at `:238-239`; `main` at `:243-249` with `--root` and `--memory`; `sys.dont_write_bytecode = True` at `:24` before the sibling imports (`:32-39`), which do not include `crew_autopilot`.
- `plugin/crew/hooks/scripts/crew_autopilot.py` (1768 lines):
  - `_index_rows` `:244`, `_index_status` `:254`, `open_index_tickets` `:273-281` (open rows whose folder exists, in INDEX order, once each).
  - `_phase(root, ticket, policy=True)` `:406`. Stops a person clears, in table order: `brainstorm` `:421`, `direction-approval` `:426` / `:429` / `:437`, `closed` `:434` / `:445`, `open-questions` `:449`, `spec` (validate) `:458`, `plan` (validate) `:465`, `approve` `:479`.
  - `_review_phase` `:491`: ledger UNKNOWN `:495`, `replan` `:498`, `implement` (no stop) `:504`, reserved round `:508`, `accept-review` for FINDINGS with no standing receipt `:515-524`. The bundle rebuild is the next statement, `ok, message = review_ledger.check_receipt(top, ticket)` at `:525`; everything after it (`:526-565`) depends on it.
  - `POLICY_FREE_APPROVE` `:1106`, `WAITING` `:1350-1354`, `_reserved_round` `:1363`, `_waiting` `:1388` (a reserved round waits on the reviewer, not the owner, `:1395-1396`), `status` `:1523`.
- `review_ledger.check_receipt` (`plugin/crew/hooks/scripts/review_ledger.py:855`) calls `_current_hash` (`:824-831`), which calls `review_patch.compute`. That runs `git add -A` and `write-tree` under a temporary index (`plugin/crew/hooks/scripts/review_patch.py:397-413`). `review_ledger.receipt_stands` (`:710`) reads only the ledger and review.json.
- `/crew:done` check 2 runs `crew_status.py --root .` and reads its `verify` line (`plugin/crew/commands/done.md:27`, `:30`); `test_lifecycle_commands.py:150-154` pins that command string.
- Tests: `plugin/crew/tests/test_status.py` (330 lines): `_stat_tree` `:23`, `_busy_repo` `:33` (60 `open` rows), `test_status_is_read_only` `:59`, `test_status_output_fits_forty_lines_on_a_busy_repo` `:84`. `plugin/crew/tests/test_crew_autopilot_status.py:28-30` imports the fixtures `_approved`, `_index`, `_ledger`, `_round`, `_ticket`, `_two_tickets` from `test_crew_autopilot.py`; `test_status_waiting_on_owner_at_approve` is at `:242`, `test_status_reserved_round_waits_on_reviewer` at `:252`.
- Sabotage anchors inside the files this ticket edits: four in `crew_status.py` (`plugin/crew/tests/sabotage_migrate.py:86-121`), one more at `plugin/crew/tests/sabotage_tooling.py:104-107`; `crew_autopilot.py` anchors are in `plugin/crew/tests/sabotage_autopilot.py`.
- `scripts/check-tooling-pr.py:58-87` `HARNESS` does not list `crew_status.py`, `crew_autopilot.py` or `commands/status.md`; they are `SEAM` (`:89-95`). `:189` prints `tooling-pr: no harness path changed`.
- verify rules that fire: `.crew/verify.json:348-359` (autopilot; runs `test_crew_autopilot_status.py` and `test_lifecycle_commands.py`), `:508-513` (`crew_status.py`, `test_status.py`), and the harness rule `:459-473`, whose `paths` list the three SEAM files and `test_status.py`.
- Docs that describe the command today: `plugin/crew/commands/status.md` (58 lines; `argument-hint` `:3`, the table `:25-38`); `plugin/crew/README.md:2815` (command table row) and `:880` (autopilot `status`); `plugin/PLUGINS.md:158`; `docs/guides/crew/src/daily-workflow.md` (no section on what waits on the owner); `docs/diagrams/process-crew-brief-status.mmd:13` (cites `crew_status.py:211-240`); `.crew/codemap/crew.md`.
- `.pylintrc:109` `max-line-length=120`, `:140` `max-module-lines=3400`.
- This repo's own `.work/INDEX.md` has more `direction` rows than any other status, none of which the `open` line shows.
## Unknowns
- Cost of the `waiting` line. `_phase` runs `crew_ticket.toplevel` (one `git rev-parse`) per ticket. Resolve before the PR: run `time python3 plugin/crew/hooks/scripts/crew_status.py --root .` on a checkout with a large real `.work/`, on the branch and on its merge-base, and put both numbers in the PR body. More than 2 seconds added is a STOP to the owner (see direction.md's open questions), not something to tune around.
- Does any test pin the set of phase names `_phase` can return, or the docstring's phase table? The new `review-unread` answer exists only with `deep=False`. Resolved by running the autopilot verify rule (`.crew/verify.json:348`); if a test pins the set, the sentinel is added there with its reason, not hidden.
- Sabotage anchors must still match exactly once after the edit. Resolved by `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_sabotage_harness.py -q` and, in the gate, the full `sabotage.py` run through the repo's heavy-run wrapper. Do not copy an anchored line.
- A stale `.pyc` can hide a red after an in-place mutation; never hand-mutate, use the runner.
- `crew_autopilot` import failure inside `crew_status` (a broken install): the waiting line reads `waiting  unknown (<reason>)` and `--owner` prints that line and exits 0. Decided; covered by a test that monkeypatches the import.
- A ticket whose `_phase` raises: it is counted and listed as could-not-tell with the exception's type name, never dropped and never counted as "on you". Decided; covered by a test.
- No `.work/INDEX.md` at all: `waiting  unknown (no .work/INDEX.md)`. Jira and ServiceDesk Plus modes write no rows, so "nothing waiting" would be a guess. Decided; covered by a test.
- Version: one patch above origin/main's crew version at land time.
- L-0550 will add stop phases to `_phase`. Until L-0687 lands, a phase this ticket has no action text for is still listed, with `see /crew:autopilot status <id>`. Accepted.
## Design (for the plan; decisions, not code)
- `_phase` and `_review_phase` take `deep=True`. With `deep=False`, `_review_phase` returns `answer("review-unread", True, <fixed reason>)` at the point where `check_receipt` would be called (`crew_autopilot.py:525`). Nothing before that point changes.
- `crew_autopilot.owner_items(root)` returns `{"state": "ok" | "unknown", "why": str, "items": [(ticket, phase, action)], "unread": [ticket], "unknown": [(ticket, why)]}`.
  - Tickets, in order: `open_index_tickets(top)`, then every folder under `.work/tickets/` whose name passes `crew_ticket.check_ticket` and that no INDEX line names.
  - For each, `_phase(top, ticket, policy=False, deep=False)`. Not a stop, or phase `closed`: skipped (autopilot drives it, or nobody does). `review-unread`: goes to `unread`. Phase `review` with `_reserved_round` true: skipped (the reviewer has it). Any other stop: an item. An exception: an `unknown` entry.
  - `action` comes from one table, `OWNER_ACTIONS`, keyed by phase:
    - `brainstorm`, `direction-approval`: `/crew:brainstorm <id>`
    - `open-questions`: `answer: <file>: <first item>`
    - `spec`, `plan`: the phase's own `command`
    - `approve`: `/crew:approve <id>`
    - `replan`: `/crew:plan <id>, then /crew:approve <id>`
    - `accept-review`: `review_ledger.py --accept --ticket <id> --by <owner>, or fix then /crew:review <id>`
    - `review` (unreadable ledger) and any phase not in the table: `see /crew:autopilot status <id>`
- `crew_status.py`: `crew_autopilot` is imported inside the function that needs it, under `try`. `collect` appends one line after the ticket lines:
  - `waiting  N on you (/crew:status --owner)`, then `, C in review not read` and `, U could not tell` only when non-zero;
  - `waiting  nothing on you` when all three are zero;
  - `waiting  unknown (<why>)` when `state` is `unknown`.
- `--owner` (mutually exclusive with `--memory`) prints the count line first, then one line per item `<id>  <phase>  <action>`, then the unread ids as `<id>  review-unread  /crew:autopilot status <id>`, then the could-not-tell ones. Each line is folded to one line and clipped to 160 characters. The whole output is clipped to `MAX_LINES`, the last line reading `... N more`.
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
- `.crew/verify.json` - only a re-measured seconds and why on the two rules named in Evidence
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting), `plugin/crew/commands/autopilot.md` and `done.md` (excluded above), any `sabotage*.py`.
## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's heavy-run wrapper.
- [ ] `test_owner_items_lists_each_stop_with_its_action` in `test_crew_autopilot_status.py`: one fixture ticket per phase, each asserted as `(ticket, phase, action)`:
  - no direction.md gives `brainstorm`, `/crew:brainstorm <id>`
  - INDEX `direction` gives `direction-approval`, `/crew:brainstorm <id>`
  - an unanswered `## Open questions` item gives `open-questions`, `answer: spec.md: <item>`
  - a spec failing `validate` gives `spec`, `/crew:spec <id>`
  - spec and plan with no approval give `approve`, `/crew:approve <id>`
  - a NEEDS_REPLAN ledger gives `replan`, `/crew:plan <id>, then /crew:approve <id>`
  - a completed FINDINGS round with no receipt gives `accept-review` and an action containing `--accept --ticket <id>`
  - a corrupt ledger gives `review`, `see /crew:autopilot status <id>`
- [ ] Must-allow, same file: `test_owner_items_skips_what_autopilot_drives` (approved with no round; no spec yet with INDEX `ready`), `test_owner_items_skips_closed_tickets` (INDEX `merged`; header `status: done`), `test_owner_items_skips_a_reserved_round`.
- [ ] `test_owner_items_agree_with_phase`: over every fixture above, a ticket is in `items` exactly when `crew_autopilot._phase(root, ticket, policy=False)` stops with the same phase, the phase is not `closed`, and no round is reserved.
- [ ] `test_owner_items_never_rebuilds_a_bundle`: with `review_ledger.check_receipt` and `review_patch.compute` monkeypatched to raise, a ticket with a completed CLEAN round and a clean receipt lands in `unread`, and `owner_items` raises nothing.
- [ ] Could-not-tell cases, one test each: `test_owner_items_phase_that_raises_is_unknown_not_dropped`, `test_owner_items_without_an_index_is_unknown`, `test_owner_items_lists_a_folder_with_no_index_row` (`direction-approval`).
- [ ] `test_phase_deep_default_is_unchanged`: for the CLEAN-receipt fixture, `_phase(root, ticket)` returns the same dict as before this change (phase `done` or `refresh` as the fixture gives today), and `next_phase` has no `deep` parameter. Command for the checks above: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q` (verify rule `.crew/verify.json:348`).
- [ ] In `test_status.py`:
  - `test_default_report_has_a_waiting_line`: a fixture with two tickets awaiting approval prints exactly one line `waiting  2 on you (/crew:status --owner)`.
  - `test_waiting_line_says_nothing_on_you`, `test_waiting_line_names_unread_and_unknown_counts`, `test_waiting_line_is_unknown_when_autopilot_cannot_be_imported`.
  - `test_owner_view_lists_one_line_per_ticket_with_its_command` (through the CLI, `--owner`).
  - `test_owner_view_is_read_only`: `_stat_tree` before and after `--owner` on a fixture holding a ticket at each of approve, accept-review and a completed CLEAN round with an uncommitted file in the tree. Equal.
  - `test_status_is_read_only` (`:59`) still passes unchanged, now with the waiting line computed.
  - `test_owner_view_fits_forty_lines`: 60 tickets awaiting approval print 40 lines (the count line, 38 tickets, and a last line `... 22 more`).
  - `test_owner_and_memory_together_are_refused`: exit code 2, nothing on stdout.
  - Command: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_status.py plugin/crew/tests/test_crew_shell.py -q` (verify rule `.crew/verify.json:508`).
- [ ] `plugin/crew/commands/status.md`: `argument-hint: "[--memory] [--owner]"`, a `waiting` row in the table (source: `crew_autopilot.owner_items`; unknown when: no INDEX.md, or autopilot's module cannot be read), and a `## --owner` section saying it lists what waits on the owner with the command to type, runs nothing, does not read a finished review (it names `/crew:autopilot status <id>` for that), and is not offered unasked. `wc -l plugin/crew/commands/status.md` is 120 or less.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`. `git diff --stat origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py' plugin/crew/commands/autopilot.md plugin/crew/commands/done.md` is empty. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_sabotage_harness.py -q` passes (every existing anchor still matches once).
- [ ] The harness verify rule (`.crew/verify.json:459-473`) passes as written: its paths include the three SEAM files, so the golden replay, the seam contracts and the canary run.
- [ ] Docs, per the repo rule for a `plugin/crew/` change:
  - `plugin/crew/README.md`: the command row at `:2815` reads `/crew:status [--memory] [--owner]` and names the owner list; the autopilot section near `:880` gains a short paragraph, "What is waiting on me", with a sample of the output and the three counts explained.
  - `plugin/PLUGINS.md:158` row updated.
  - `docs/guides/crew/src/daily-workflow.md` gains the same in guide form, and `python3 docs/guides/crew/src/build.py` is re-run so the HTML, DOCX and PDF match.
  - `docs/diagrams/process-crew-brief-status.mmd` and its generated README and index entries show the `waiting` line and its source; `.crew/codemap/crew.md` describes `owner_items` and `deep`.
  - `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0551` prints every line `fresh`.
- [ ] Crew is bumped one patch in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, with a `CHANGELOG.md` entry; `plugin/crew/BUDGETS.md` counts are current. Commit, then `python3 scripts/check-marketplace.py` passes.
- [ ] `python3 scripts/gate-runner.py` is green. The PR body names the suites that ran, states that `scripts/_test/drift-detection.sh` did not, and carries the two timings from Unknowns.
## Dependencies
Must land first (all on main already):
- T-0004 (merged): `crew_autopilot.py` and its phase table.
- T-0010 (merged): `policy=False`, the policy-free read.
- T-0018 (merged): `/crew:autopilot status`, `WAITING`, `_reserved_round`.
- L-0510 (done): `review_ledger.receipt_stands`, which decides `accept-review`.
- T-0087 (merged): the tooling-PR rule and the SEAM list.

Not a dependency for this slice any more: T-0037 and its children L-0639 to L-0641 (ready / spec, not landed) and L-0550 (direction). They are dependencies of L-0687.

Same hot file, no order required, but do not run in parallel lanes: L-0550, T-0043 (ready), T-0022 (approved) all edit `crew_autopilot.py`. Whichever lands second merges main first.

Blocks: L-0687. T-0052 and T-0059 name T-0037 in INDEX, not this ticket.
## Size and split
- About 110 added production lines: `crew_autopilot.py` about 55 (`deep` 8, `OWNER_ACTIONS` 14, `owner_items` 33), `crew_status.py` about 40 (the waiting line 18, the `--owner` output 15, `main` 7), `status.md` about 15 prompt lines.
- No parser, no blocking guard, no fail-closed state machine, no `HARNESS` path. Under every split threshold.
- Split anyway, by dependency: the T-0037 kinds are L-0687 (`children/1/`), about 45 lines, written so it can be minted as its own ticket once L-0550 is on main.

## Split
- L-0687 (child 1 of L-0551, filed 2026-10-04): the owner list and the waiting line know hold, blocked, landing and needs-owner

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.

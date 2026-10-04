# L-0551 direction - /crew:status --owner and the waiting line

Status: seed (not yet approved).

Split from T-0037 (owner 2026-09-30 "Triage pass now"). Owner decision 2026-09-30 ~11:30: work the oldest tickets first; a ticket with more than 1-2 separate deliverables has the extra ones split out so each ticket is a small PR.

## Original text (verbatim, from T-0037 spec.md ## Intent and plan.md Step 6)

> `/crew:status --owner` lists everything waiting on the owner, with the exact command to type.
>
> ### Step 6: /crew:status --owner and the waiting line
> Files: plugin/crew/tests/test_status.py, plugin/crew/hooks/scripts/crew_ticket_state.py, plugin/crew/hooks/scripts/crew_status.py, plugin/crew/commands/status.md
> Test: python3 -m pytest plugin/crew/tests/test_status.py plugin/crew/tests/test_ticket_state.py -q -p no:cacheprovider
> Risk: med. `crew_status` must stay read-only (`test_status.py:57`) and within 40 lines (`:66`). An owner list that disagrees with autopilot sends the owner to the wrong command.
> - [ ] Write the tests:
>   - `test_owner_lists_each_kind`: one fixture ticket per kind, each line checked for its exact command.
>     - needs-replan gives `/crew:plan <id>`, then `/crew:approve <id>`.
>     - Explicit needs-owner gives next.md's `next:`.
>     - Approval pending gives `/crew:approve <id>`.
>     - FINDINGS unaccepted gives `review_ledger.py --accept --ticket <id> --by <owner>`, or a fix then `/crew:review <id>`.
>     - Open questions gives the first item.
>     - INDEX `direction` gives `/crew:brainstorm <id>`.
>     - A hold past its revisit gives `revisit`.
>   - Must-allow: `test_owner_skips_tickets_autopilot_drives` (an approved ticket with no rounds is not listed) and `test_owner_skips_future_holds`.
>   - `test_owner_view_agrees_with_autopilot`: for every fixture ticket listed as approve, accept-review, needs-replan or open-questions, `crew_autopilot.next_phase` stops with phase approve, accept-review, replan or open-questions respectively.
>   - `test_owner_view_is_read_only`: the mtime snapshot, as `:57`.
>   - `test_owner_view_fits_forty_lines`: 60 tickets pending approval. Expect 40 lines, the last reading `... N more`.
>   - `test_default_report_has_a_waiting_line`: `waiting  N on you (/crew:status --owner), H held, B blocked`.
> - [ ] Implement `owner_items` in `crew_ticket_state.py`. Walk INDEX rows in order, skip closed rows and rows with no folder, and compute each kind from `view`, `crew_ticket.accepted` (only when spec.md and plan.md exist and `validate` is empty), `review_ledger.status` (latest current round FINDINGS without an owner-accepted receipt for that round, the condition at `crew_autopilot.py:416-418`) and `crew_autopilot._open_questions(folder)`, imported lazily to avoid a cycle. It returns `[(kind, ticket, action)]`. It never calls `_refresh_state`, so it stays cheap.
> - [ ] In `crew_status.py`, add `--owner` to `main` (`:212-218`). With it, print the header line and then `owner_items` clipped to `MAX_LINES`. Without it, `collect` (`:185-209`) appends the one `waiting` line after `_ticket_lines`.
> - [ ] In `status.md`: set `argument-hint: "[--memory] [--owner]"`, add a `waiting` row to the table, and add a `## --owner` section saying it lists what waits on the owner, one line per ticket, with the command to type, and runs nothing. Stay within 120 lines.
> - [ ] Run the Test command.

## Dependencies

- T-0037 (crew_ticket_state.view and the derived statuses)
- test_owner_view_agrees_with_autopilot needs L-0550 (autopilot stops, split from T-0037) for the hold/blocked rows

## Evidence carried over

- crew_status stays read-only (test_status.py:57) and within 40 lines (:66), as T-0037's plan recorded

## Next

/crew:spec L-0551: re-find every line number by content on origin/main; the quoted anchors are as T-0037's plan recorded them.

## Direction check 2026-10-04

Checked against origin/main `155fe6d8` (crew `1.0.322` in `plugin/crew/.claude-plugin/plugin.json`). The owner was not available; where a choice was needed the recommended option was taken and is listed under "Open questions for the owner".

### Still true
- Nothing of this ticket is on main. `plugin/crew/hooks/scripts/crew_status.py:243-249` takes `--root` and `--memory` only, `plugin/crew/commands/status.md:3` has `argument-hint: "[--memory]"`, and `git log origin/main --grep` for L-0551, T-0037 and `--owner` returns nothing.
- `/crew:status` reports one repo in at most 40 lines (`crew_status.py:41`, `:238-239`) and says nothing about what waits on the owner. Its `open` line (`:113-121`) lists only INDEX rows whose status is `open`, `in-progress` or `review`, so a `direction` or `ready` row is invisible there.
- The read-only and 40-line properties are still tested (`plugin/crew/tests/test_status.py:59`, `:84`).

### What changed since the seed (2026-09-30) and T-0037's plan (2026-09-26)
- **`crew_ticket_state.py` does not exist** and will not until L-0639 lands. The seed put `owner_items` in that file. T-0037 was re-split on 2026-10-04 into four slices (T-0037, L-0639, L-0640, L-0641); `view`, `next.md` and the derived `blocked` arrive with L-0639 and L-0640, and the autopilot stops with L-0550. That is five tickets ahead of the seed's design.
- **Autopilot already answers "who acts" per ticket.** T-0018 (merged) added `crew_autopilot.status` and the `WAITING` map (`plugin/crew/hooks/scripts/crew_autopilot.py:1350-1354`). T-0010 (merged) added `policy=False`, "status's read", to `_phase` (`:406-409`): the same phase table with no approval or questions policy consulted. The seed's `owner_items` re-derived each kind beside autopilot and needed a test that the two agree. Folding over `_phase` makes them agree by construction.
- **The owner stops grew.** The seed named seven kinds. `_phase` now has more stops a person clears: `brainstorm` (`:421`), `direction-approval` (`:426`, `:429`, `:437`), `open-questions` (`:449`), `spec` and `plan` failing `validate`, `approve` (`:479`), `replan` (`:498`), `review` on an unreadable ledger, `accept-review` (`:522`, auto-accept aware since L-0510).
- **Reading past `accept-review` is not read-only.** `_review_phase` calls `review_ledger.check_receipt` at `crew_autopilot.py:525`, which rebuilds the review bundle: `review_patch.compute` runs `git add -A` and `write-tree` against a temporary index (`plugin/crew/hooks/scripts/review_patch.py:397-413`). `/crew:status` snapshots every mtime under the repo, `.git` included, so the owner list must stop before that call. Every stop above is decided before it.
- **`/crew:done` check 2 runs the default report** (`plugin/crew/commands/done.md:27`). A `waiting` line there has to be cheap and can never fail the run.
- `crew_status.py`, `crew_autopilot.py` and `commands/status.md` are `SEAM` paths in `scripts/check-tooling-pr.py`, not `HARNESS` ones. With no `HARNESS` path in the branch the checker prints `tooling-pr: no harness path changed`, so this is an ordinary feature PR.
- Every line number in the quoted Step 6 moved: `main` is `crew_status.py:243`, `collect` is `:211-240`, the read-only test is `test_status.py:59` and the 40-line test `:84`.

### Options
1. **Recommended, taken: fold over autopilot's own phase read, and split the T-0037 kinds out.**
   - This ticket: `crew_autopilot.owner_items` walks the open INDEX tickets and asks `_phase(top, ticket, policy=False, deep=False)` for each. `deep=False` returns before the bundle rebuild. `/crew:status --owner` prints the result, and the default report gains one `waiting` line. It needs nothing that is not on main, so it can be built now.
   - L-0687: once L-0550 and L-0639 and L-0640 are on main, `hold`, `blocked`, `landing` and `needs-owner` get their own handling (`H held, B blocked` on the waiting line, `revisit` for a hold that is due, next.md's `next:` for needs-owner).
2. Build the seed as written, in `crew_ticket_state.py`. Rejected: blocked behind five unlanded tickets, and it keeps a second derivation of autopilot's phase table.
3. Call `crew_autopilot.status` per ticket. Rejected: it rebuilds a review bundle for every reviewed ticket, which writes under `.git` and is slow.

### Not a split forced by size
The whole ticket is about 155 production lines with no parser and no blocking guard. The split is by dependency: slice 1 is useful today (most open rows in this repo's INDEX are `direction` rows waiting on one person), and slice 2 cannot be written until its inputs exist.

## Open questions for the owner
- Is the two-slice order acceptable: owner list from today's autopilot phases first, hold/blocked/needs-owner later? (Default taken: yes.)
- Slice 1's waiting line is `waiting  N on you (/crew:status --owner)`, with `, C in review not read` and `, U could not tell` only when non-zero. The seed's `, H held, B blocked` arrives with L-0687. Acceptable? (Default taken: yes.)
- A ticket with a finished review round whose FINDINGS are accepted or CLEAN is reported as "in review, not read", pointing at `/crew:autopilot status <id>`, because telling more means rebuilding the bundle. Acceptable, or should `--owner` (not the default report) pay for the rebuild? (Default taken: never rebuild from `/crew:status`.)
- A ticket folder with no INDEX row is listed as `direction-approval` (autopilot's own answer, "cannot tell"). The seed skipped it. (Default taken: list it.)
- `--owner` together with `--memory` is refused by the argument parser. (Default taken: refuse; the owner list is its own report.)
- If the measured cost of the `waiting` line on this repo's real `.work/` is above 2 seconds, should the line leave the default report? (Default taken: stop and ask at implement time.)

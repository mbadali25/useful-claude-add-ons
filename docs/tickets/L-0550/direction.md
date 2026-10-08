# L-0550 direction - autopilot stops on hold, landing, needs-owner, cancelled/superseded and blocked

Status: seed (not yet approved).

Split from T-0037 (owner 2026-09-30 "Triage pass now"). Owner decision 2026-09-30 ~11:30: work the oldest tickets first; a ticket with more than 1-2 separate deliverables has the extra ones split out so each ticket is a small PR.

## Original text (verbatim, from T-0037 spec.md ## Intent and plan.md Step 5)

> `/crew:autopilot` stops on each of them with a reason.
>
> ### Step 5: autopilot stops on hold, landing, needs-owner, cancelled and blocked
> Files: plugin/crew/tests/test_crew_autopilot.py, plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/commands/autopilot.md
> Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q -p no:cacheprovider
> Risk: high. A stop placed after `_review_phase` is entered, or one that reads only one of the two sources, drives a parked ticket. `autopilot.md` has no spare line.
> - [ ] Write the must-block tests, each asserting `(phase, stop)`:
>   - `test_next_hold_stops`, parametrised over the INDEX cell `hold` and the header `status: hold` on an approved ticket. Expect `("hold", True)`, with next.md's `reason:` and `revisit:` in the reason.
>   - `test_next_landing_stops`, on an approved ticket with a CLEAN current receipt. Expect `("landing", True)`, not `done`.
>   - `test_next_needs_owner_stops_with_the_next_line`: the reason contains next.md's `next:`, and without one it contains "cannot tell".
>   - `test_next_cancelled_is_closed` and `test_next_superseded_names_its_successor`: `("closed", True)`, with `superseded-by` in the reason.
>   - `test_next_blocked_stops_before_implement`: approved, no rounds, and an open dependency. Expect `("blocked", True)`, naming the dependency.
>   - `test_next_blocked_with_an_unknown_dependency_stops`.
> - [ ] Write the must-allow tests:
>   - `test_next_dependencies_closed_reaches_implement`.
>   - `test_next_blocked_ticket_still_gets_spec_and_plan`: no spec gives `spec`, then no plan gives `plan`, both stop=0.
>   - Keep `test_next_index_status_that_does_not_say_approved_stops` (`:516`) green with `parked`, and add `blocked` to its parametrisation.
> - [ ] Watch them fail. Then in `_phase` (`crew_autopilot.py:314-385`):
>   - After the `INDEX_DONE` branch (`:339-341`), and before it for `cancelled` and `superseded` so the reason names them, read `crew_ticket_state.view(top, ticket, today=None)`. When `gate` is set, return `answer(gate_phase, True, reason)`, where `gate_phase` is `closed` for the closing values and the value itself otherwise.
>   - After the header `done` check (`:349-352`), repeat the gate check for the header value, which covers a header gate with an INDEX cell that is not gated.
>   - Immediately before `return _review_phase(...)` (`:385`), stop `blocked` when `view["blocked_by"]` is non-empty.
> - [ ] Add `("hold", ...)`, `("landing", ...)`, `("needs-owner", ...)` and `("blocked", ...)` to `FIXED_STOPS` (`:116-129`). Add rows to the module docstring's phase table (`:17-40`).
> - [ ] In `autopilot.md:90-93`, rewrite the "Enforced by `next` from disk" paragraph in place to also name `hold`, `landing`, `needs-owner` and `blocked` in backticks. Tighten wording elsewhere in that paragraph so `wc -l plugin/crew/commands/autopilot.md` stays at 120 or less.
> - [ ] Run the Test command.

## Dependencies

- T-0037 (status vocabulary, depends-on, crew_ticket_state.view)
- crew_autopilot.py and autopilot.md are hot files (lane-groups-2026-09-30.md): serialise with the autopilot chain

## Evidence carried over

- Anchors in the quoted step (`crew_autopilot.py:314-385`, `:116-129`, `autopilot.md:90-93`) predate T-0010/T-0019 merges; re-find by content

## Next

/crew:spec L-0550: re-find every line number by content on origin/main; the quoted anchors are as T-0037's plan recorded them.

## Direction check 2026-10-04

Checked against origin/main `155fe6d8` (crew `1.0.322` in `plugin/crew/.claude-plugin/plugin.json`). The owner was not available; where a brainstorm would ask, the recommended option is taken and the question is listed at the end.

### Still true
- Nothing of this ticket has landed. `git log origin/main --grep` for L-0550, L-0551, T-0037, `crew_ticket_state` and `needs-owner` returns nothing; no `plugin/crew/hooks/scripts/crew_ticket_state.py` exists; `git grep -nE "needs-owner|landing|superseded|depends-on" origin/main -- plugin/crew/hooks/scripts/crew_autopilot.py` returns nothing.
- `_phase` (`plugin/crew/hooks/scripts/crew_autopilot.py:406-480`) reads the INDEX status cell and the header only for `direction`, the `INDEX_DONE` words and `status: done`. A ticket whose spec header says `status: hold` under an INDEX cell of `ready` is driven straight to `/crew:implement`. A ticket with an open dependency is driven too: nothing reads `depends-on:`.
- `FIXED_STOPS` (`crew_autopilot.py:186-200`) has nine entries, none of them a ticket status.

### What changed since the seed (2026-09-30)
- **Part of the problem is already a stop, with the wrong name.** An INDEX cell of `hold`, `landing`, `needs-owner`, `cancelled` or `superseded` is not in `DIRECTION_APPROVED` (`crew_autopilot.py:181`), so `_phase` stops at `direction-approval` with "cannot tell whether the direction is approved" (`:436-440`). That is fail-closed, but the reason is false for a parked ticket and `status` then tells the owner to set the row to `ready`. The gaps that are not stops at all are the header-only gate and `blocked`.
- **The prerequisites were re-split on 2026-10-04.** T-0037 is now only the vocabulary in `crew_ticket.py` (a tooling PR). `crew_ticket_state.py` (`view`, `dependency_state`, the closed words) is L-0639, and `next.md` (`reason`, `revisit`, `next`, `superseded-by`) is L-0640. None is on main. This ticket needs all three.
- **L-0639 already makes a `cancelled` or `superseded` INDEX row read `closed`** (it widens `INDEX_DONE`, and adds `test_next_cancelled_index_row_is_closed`). What is left here for the closing words is the header case and naming the successor in the reason.
- **The tooling-PR rule (T-0087, merged).** `plugin/crew/tests/sabotage*.py` is in `HARNESS` of `scripts/check-tooling-pr.py`, and `crew_autopilot.py` and `commands/autopilot.md` are not in `ALONGSIDE` (they are `SEAM`). So the stops and their sabotage mutations cannot share a PR. The mutations move to L-0686.
- **`autopilot.md` has one spare line, not eleven.** It is 109 lines against `AUTOPILOT_MAX_LINES = 110` (`plugin/crew/tests/test_lifecycle_commands.py:112`), not 120. The stop list in section 4 (`autopilot.md:94-96`) is rewritten in place.
- **`status` maps phases to who acts** (`WAITING`, `crew_autopilot.py:1350-1354`, T-0018). A phase not in it prints `unknown (phase 'hold' is not one status maps)`. The seed did not mention it; the new phases need rows.
- **`_closed`** (`crew_autopilot.py:1442-1455`) repeats the two facts `next` closes a ticket on. A header `cancelled` or `superseded` has to be added to both, or `status` offers to drive a cancelled ticket.
- Every anchor in the quoted Step 5 moved: `_phase` is `:406`, `FIXED_STOPS` `:186`, the module's phase table `:63-84`, `test_next_index_status_that_does_not_say_approved_stops` `:618`.

### Options
1. **(Recommended, taken) One gate read in `_phase`, plus a blocked stop before the review phase; mutations in a separate tooling child.** `_phase` asks `crew_ticket_state.view` once, right after the `INDEX_DONE` branch and before the `DIRECTION_APPROVED` test. A set gate stops as `hold`, `landing`, `needs-owner`, or `closed` for a header `cancelled`/`superseded`. Immediately before `_review_phase`, a non-empty `blocked_by` stops as `blocked`. About 90 production lines, no new parser. Cost: waits on three unmerged tickets.
2. Do it without `crew_ticket_state.py`: read the header and INDEX cell in `crew_autopilot.py` directly and drop `blocked` and the `next.md` reasons. Lands sooner, but duplicates the gate read that L-0551 must agree with, and an owner list that disagrees with autopilot is the risk L-0551's seed names.
3. Fix only the reason text of the existing `direction-approval` stop. Smallest, but a header-only `hold` and a blocked ticket are still driven.

### Recommendation
Option 1. This ticket is the feature PR (the stops, `autopilot.md`, docs). L-0686 is the tooling PR with the sabotage mutations.

### Decisions taken without the owner (recommended option each time)
- A `blocked` ticket still gets its spec and plan written; it stops only once it is approved, before implement, review and done. A blocked ticket already in review stops too.
- `landing` stops autopilot outright, even with a current receipt and fresh artifacts: the land step owns the ticket from there.
- When both the INDEX cell and the header carry a gate, the INDEX cell wins (as `view` reads it). An INDEX `done` row is `closed` whatever the header says.
- A future `revisit:` date does not lift a hold, and a past one does not either: it is printed in the reason. Only the owner editing the status lifts a hold.

### Open questions for the owner
- Should a `hold` whose `revisit:` date has passed still stop, or should autopilot resume it? Taken: still stop, and say the date has passed.
- Should a `blocked` ticket that is already in review be allowed to finish review and stop only at done? Taken: stop at once.
- Should `landing` let autopilot run `/crew:done` when the receipt is current? Taken: no, it stops.
- The mutations go in `sabotage_autopilot.py` (already registered, so `sabotage.py`, at its line limit, is not edited) rather than L-0641's `sabotage_ticket_state.py`. Say if you want them in the other file.

## Next (2026-10-04)

/crew:plan L-0550 once T-0037, L-0639 and L-0640 are merged. spec.md was written 2026-10-04 against origin/main `155fe6d8`.

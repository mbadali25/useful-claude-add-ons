# Cloud handoff: L-0642

**Autopilot's open-questions stop sees through code fences, and stops when it cannot tell**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child, split from T-0043, slice 1 of 2 (the family is T-0043, L-0642, L-0643). The spec calls it a complete ticket on its own.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0642-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0642/direction.md`, `docs/tickets/L-0642/spec.md`
- **Size:** about 90 production lines in `plugin/crew/hooks/scripts/crew_autopilot.py`, about 200 lines of tests. One new parser with one fail-closed rule. Risk is high in the spec. No harness path (`crew_autopilot.py` is a seam path, which counts as feature work here); the committed mutations are L-0643.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0043 | ready, not started | Land it first. Not a content dependency, but it edits `crew_autopilot.py` and `test_crew_autopilot.py`; landing it first means this ticket merges main once. |
| T-0004 | merged | `_open_items` and the `open-questions` stop. |
| T-0010 | merged | The questions policy the stop's reason carries. |
| T-0087 | merged | The tooling-PR rule that keeps the mutations out of this PR. |

Wait for T-0043 to merge, then merge main in (a merge commit, never a rebase).

This ticket blocks L-0643 (sabotage mutations for this parser).

Family order:

1. **T-0043**: the FINDINGS-stop fixes. Feature PR.
2. **L-0642** (this ticket): the fence parser. Feature PR.
3. **L-0643**: sabotage mutations for 1 and 2. Tooling-only PR, lands alone. After both.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch starts at `ce235468`); re-check each anchor. The parent's hand-off notes that child spec evidence was spot-checked only, not re-verified line by line.
- There is no plan.md and none is published. The implementing session writes the plan.
- The design is fixed by the spec's Acceptance section: main's parser is the floor (a union, so the result cannot fall below main), a strict column-0 fence view adds what main misses, and anything else fence-shaped is "could not tell", which stops. The stop can only gain stops relative to main.
- No CommonMark emulation. An earlier build tried it and was rejected after two review rounds; the direction's History section says why. The round-1 and round-2 findings are in two golden review files on main that the spec names. Read them; do not edit them (they are harness goldens).
- The floor test holds a verbatim, never-edited copy of main's parser at `155fe6d8`. The spec pins that copy to that commit. If the parser on current main differs from it, could not tell from these files which one the floor should be; ask before choosing.
- The anchor `    if questions:\n` stays byte-identical and unique. No edit to any harness path.
- Two measurements go in the PR body: the cost on today's ticket files (files read, stops under main, stops under the new parser, each newly stopping file) and the verify rule's re-measured seconds. Ticket files are untracked, so a cloud clone may not hold the corpus the spec measured; say which files were measured.
- If the corpus test pushes the verify rule past 20 seconds, cut the product; do not mark the test slow.
- Sabotage evidence for this PR is by hand in a scratch copy, quoted in the PR body.
- Nothing was executed for this spec; the quoted measurements are from a 2026-09-27 prototype and are re-run by the plan.

## Open questions for the owner (recommended option taken)

1. Under `autopilot.questions: self`, the could-not-tell item reaches the same policy route as a real question, so autopilot may "answer" it by rewriting the fence. Allowed, because the item text says exactly what to fix and the result is re-parsed on the next `next`. Alternative: a could-not-tell item is always a person's.
2. Accepted cost, stated in the direction: a file with an answered Open-questions section and a valid but indented fence stops until the fence is moved to column 0.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0642/` in the final PR unless the owner wants it kept.
